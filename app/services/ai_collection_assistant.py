import json
import math
import re
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PHOTO_MUST_TYPES = {
    "START",
    "DESTINATION",
    "LEFT",
    "RIGHT",
    "BUS_ON",
    "BUS_OFF",
    "SUBWAY_IN",
    "SUBWAY_OUT",
    "TRANSFER",
}
PHOTO_OPTIONAL_TYPES = {"STRAIGHT"}
TRANSIT_TYPES = {"BUS_ON", "BUS_OFF", "SUBWAY_IN", "SUBWAY_OUT", "TRANSFER"}
VOICE_MOMENTS = ("enter", "repeat", "near", "arrived", "offRoute")
PRIORITIES = {"MUST", "SHOULD", "OPTIONAL"}
VOICE_TYPES = {"enter", "repeat", "near", "arrived", "offRoute"}
BAD_PHOTO_EXAMPLES = ["不要只拍地面", "不要背对行进方向拍", "不要只拍地图截图"]
UNGROUNDED_ASSERTION_TERMS = (
    "和平饭店",
    "海关大楼",
    "沈大成",
    "老字号",
    "蓝色顶棚",
    "历史建筑",
    "历史建筑群",
    "黄浦江",
    "江面",
    "观景平台",
    "东方明珠",
    "栏杆",
    "江水声",
    "江的方向",
    "朝着江",
    "跟着人群",
    "红绿灯",
    "红色",
    "黄色",
    "蓝色",
    "绿色",
)

SYSTEM_PROMPT = """你是家路通的 AI 采集助手。

你的任务是根据已经生成的 RouteStep，生成真实路线采集清单，帮助家属降低实地采集成本。
你只能基于输入中的步骤、风险、交通信息和已有文案做建议。

严格禁止：
- 修改路线、坐标、步骤数量或步骤类型
- 编造公交线路、地铁线路、站名、出口、建筑、店名或颜色
- 自动通过审核或建议自动发布
- 把 OPTIONAL 任务描述为发布阻断

必须考虑：
- START、DESTINATION、HIGH 风险、LEFT/RIGHT、公交上下车、地铁进出站、换乘点通常需要照片
- HIGH 风险、连续相似转弯、缺少地标、AI 置信度低的步骤需要家属重点确认
- HIGH 风险、偏航求助、公交下车、终点确认更适合真人录音
- 照片拍摄指导必须具体说明站位和拍摄方向
- 建议必须口语化、可执行，不能说空话

只输出 JSON：
{"summary":"","photoTasks":[],"landmarkTasks":[],"voiceTasks":[],"reviewTasks":[],"testTasks":[]}

photoTasks 字段：
{"stepId":"","stepNo":1,"priority":"MUST|SHOULD|OPTIONAL","reason":"","shootingGuide":"","badExamples":[]}

landmarkTasks 字段：
{"stepId":"","stepNo":1,"priority":"MUST|SHOULD","reason":"","suggestedLandmarkTypes":[],"exampleText":""}

voiceTasks 字段：
{"stepId":"","stepNo":1,"voiceType":"enter|repeat|near|arrived|offRoute","priority":"MUST|SHOULD","reason":"","script":""}

reviewTasks 字段：
{"stepId":"","stepNo":1,"priority":"MUST|SHOULD","checkItem":"","reason":""}

testTasks 字段：
{"order":1,"title":"","description":""}"""


def _clean_text(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _route_context(route: dict[str, Any]) -> str:
    steps = []
    for step in route.get("steps") or []:
        steps.append(
            {
                "id": step.get("id"),
                "stepNo": step.get("stepNo"),
                "type": step.get("type"),
                "title": step.get("title"),
                "shortAction": step.get("shortAction"),
                "elderShortAction": step.get("elderShortAction"),
                "roadName": step.get("roadName"),
                "landmarkHint": step.get("landmarkHint"),
                "transit": step.get("transit"),
                "source": step.get("source"),
            }
        )
    return json.dumps(
        {
            "routeName": route.get("name"),
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "steps": steps,
        },
        ensure_ascii=False,
    )


def _task_text(task: dict[str, Any]) -> str:
    values = []
    for key in (
        "reason",
        "shootingGuide",
        "exampleText",
        "script",
        "checkItem",
        "description",
    ):
        values.append(str(task.get(key) or ""))
    values.extend(str(item) for item in task.get("badExamples") or [])
    return " ".join(values)


def _has_ungrounded_assertion(task: dict[str, Any], context: str) -> bool:
    text = _task_text(task)
    return any(term in text and term not in context for term in UNGROUNDED_ASSERTION_TERMS)


def _location(step: dict[str, Any]) -> tuple[float, float] | None:
    location = step.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        return None
    return float(latitude), float(longitude)


def _distance_meters(a: dict[str, Any], b: dict[str, Any] | None) -> int:
    start = _location(a)
    end = _location(b or {})
    if not start or not end:
        return 0
    lat1, lon1 = start
    lat2, lon2 = end
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return int(round(radius * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))))


def _voice_key(moment: str, suffix: str) -> str:
    return f"{moment}{suffix}"


def _has_custom_voice(step: dict[str, Any], moment: str | None = None) -> bool:
    voice = step.get("voice") or {}
    moments = [moment] if moment else VOICE_MOMENTS
    return any(
        voice.get(_voice_key(item, "VoiceType")) == "CUSTOM"
        and bool(voice.get(_voice_key(item, "AudioUrl")))
        for item in moments
    )


def _has_tts(step: dict[str, Any]) -> bool:
    voice = step.get("voice") or {}
    return any(
        voice.get(_voice_key(moment, "VoiceType")) == "TTS"
        and bool(voice.get(_voice_key(moment, "AudioUrl")))
        for moment in VOICE_MOMENTS
    )


def _step_history(history: dict[str, Any] | None, step: dict[str, Any]) -> dict[str, int]:
    history = history or {}
    empty = {"FOUND": 0, "NOT_FOUND": 0, "HELP": 0}
    by_id = history.get(str(step.get("id")))
    by_no = history.get(str(step.get("stepNo")))
    result = empty.copy()
    for source in (by_no, by_id):
        if not isinstance(source, dict):
            continue
        for key in result:
            result[key] = max(result[key], int(source.get(key, 0) or 0))
    return result


def _step_input(
    step: dict[str, Any],
    next_step: dict[str, Any] | None,
    history: dict[str, Any] | None,
) -> dict[str, Any]:
    source = step.get("source") or {}
    return {
        "stepId": step.get("id"),
        "stepNo": step.get("stepNo"),
        "type": step.get("type"),
        "title": step.get("title"),
        "elderShortAction": step.get("elderShortAction") or step.get("shortAction"),
        "riskLevel": step.get("riskLevel", "LOW"),
        "imageStatus": step.get("imageStatus", "NONE"),
        "landmarkHint": step.get("landmarkHint", ""),
        "voiceType": (step.get("voice") or {}).get("voiceType", "SYSTEM"),
        "hasCustomVoice": _has_custom_voice(step),
        "hasTts": _has_tts(step),
        "requiresFamilyReview": bool(step.get("requiresFamilyReview")),
        "aiConfidence": step.get("aiConfidence", ""),
        "distanceToNextStep": _distance_meters(step, next_step),
        "transit": step.get("transit"),
        "originalInstruction": source.get("instruction", ""),
        "history": _step_history(history, step),
    }


def _photo_reason(step: dict[str, Any], history: dict[str, int]) -> str:
    step_type = step.get("type")
    if history["HELP"] or history["NOT_FOUND"]:
        return "这里曾经出现找不到或求助，需要补充更清楚的照片。"
    if step.get("riskLevel") == "HIGH":
        return "这里是高风险点，老人需要靠照片先停下确认。"
    if step_type in {"LEFT", "RIGHT"}:
        return f"这里是{step_type == 'LEFT' and '左转' or '右转'}点，老人容易走错。"
    if step_type == "START":
        return "这里是出发位置，第一张照片会决定老人是否能顺利开始。"
    if step_type == "DESTINATION":
        return "这里是终点入口，需要确认老人找到的是实际入口。"
    if step_type == "BUS_ON":
        return "这里是公交上车站，需要拍清楚站牌和乘车方向。"
    if step_type == "BUS_OFF":
        return "这里是公交下车站，需要拍清楚下车后的停留位置。"
    if step_type in {"SUBWAY_IN", "SUBWAY_OUT", "TRANSFER"}:
        return "这里涉及地铁或换乘，MVP 阶段必须由家属现场确认。"
    return "这里可以作为长直行中的安心确认点。"


def _shooting_guide(step: dict[str, Any]) -> str:
    step_type = step.get("type")
    if step_type in {"LEFT", "RIGHT"}:
        action = "左转方向" if step_type == "LEFT" else "右转方向"
        return f"请站在老人走来的方向，拍清楚路口和{action}。"
    if step_type == "BUS_ON":
        return "请站在候车位置，拍清楚公交站牌、线路号和车来方向。"
    if step_type == "BUS_OFF":
        return "请在下车后站稳的位置拍照，拍清楚站牌和接下来要走的方向。"
    if step_type == "DESTINATION":
        return "请站在老人最后走来的方向，拍清楚门牌、入口和可识别标志。"
    if step_type == "START":
        return "请站在出门后老人面向前方的位置，拍清楚出口和第一段行进方向。"
    return "请面向老人接下来要走的方向拍摄，画面里保留路口或固定参照物。"


def _task_key(task: dict[str, Any], kind: str) -> tuple:
    return (
        kind,
        str(task.get("stepId", "")),
        str(task.get("voiceType", "")),
        str(task.get("checkItem", "")),
        str(task.get("title", "")),
    )


def _append_unique(target: list[dict[str, Any]], task: dict[str, Any], kind: str) -> None:
    key = _task_key(task, kind)
    for index, item in enumerate(target):
        if _task_key(item, kind) != key:
            continue
        if task.get("priority") == "MUST" and item.get("priority") != "MUST":
            target[index] = task
        return
    target.append(task)


def fallback_collection_plan(
    route: dict[str, Any], history: dict[str, Any] | None = None
) -> dict[str, Any]:
    photo_tasks: list[dict[str, Any]] = []
    landmark_tasks: list[dict[str, Any]] = []
    voice_tasks: list[dict[str, Any]] = []
    review_tasks: list[dict[str, Any]] = []
    steps = route.get("steps") or []
    first_turn_seen = False
    first_transit_seen = False

    for index, step in enumerate(steps):
        step_type = step.get("type")
        risk = step.get("riskLevel", "LOW")
        step_history = _step_history(history, step)
        distance_to_next = _distance_meters(step, steps[index + 1] if index + 1 < len(steps) else None)
        missing_photo = step.get("imageStatus", "NONE") != "FAMILY"
        history_problem = step_history["NOT_FOUND"] > 0 or step_history["HELP"] > 0
        needs_photo = (
            risk == "HIGH"
            or step_type in PHOTO_MUST_TYPES
            or history_problem
        )
        if missing_photo and needs_photo:
            photo_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "MUST",
                    "reason": _photo_reason(step, step_history),
                    "shootingGuide": _shooting_guide(step),
                    "badExamples": BAD_PHOTO_EXAMPLES,
                }
            )
        elif missing_photo and step_type in PHOTO_OPTIONAL_TYPES and distance_to_next >= 180:
            photo_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "OPTIONAL",
                    "reason": "这是较长直行中的停留点，可以拍一张让老人确认方向。",
                    "shootingGuide": _shooting_guide(step),
                    "badExamples": BAD_PHOTO_EXAMPLES,
                }
            )

        previous = steps[index - 1] if index > 0 else {}
        next_step = steps[index + 1] if index + 1 < len(steps) else {}
        consecutive_turn = (
            step_type in {"LEFT", "RIGHT"}
            and (previous.get("type") == step_type or next_step.get("type") == step_type)
        )
        vague_instruction = "前面路口" in json.dumps(step.get("voice") or {}, ensure_ascii=False)
        missing_landmark = not step.get("landmarkHint")
        if missing_landmark and (risk == "HIGH" or consecutive_turn or vague_instruction or step.get("aiConfidence") == "LOW"):
            landmark_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "MUST" if risk == "HIGH" or consecutive_turn else "SHOULD",
                    "reason": "这一步只靠方向不够明确，需要固定地标帮助老人确认。",
                    "suggestedLandmarkTypes": ["红绿灯", "公交站牌", "地铁入口", "门牌", "便利店"],
                    "exampleText": "看到家属确认过的地标后，再按语音提示继续。",
                }
            )

        if risk == "HIGH" and not _has_custom_voice(step, "near"):
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "near",
                    "priority": "MUST",
                    "reason": "这里需要老人先停下确认，真人声音更容易让老人信任。",
                    "script": "先停一下，看清楚照片里的地方，确认安全以后再继续。",
                }
            )
        if risk == "HIGH" and not _has_custom_voice(step, "offRoute"):
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "offRoute",
                    "priority": "MUST",
                    "reason": "高风险点走偏时必须立刻停下并联系家人。",
                    "script": "好像走远了，先停下，不要继续走。长按求助联系家人。",
                }
            )
        if step_type == "BUS_OFF" and not _has_custom_voice(step, "near"):
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "near",
                    "priority": "MUST",
                    "reason": "下车点容易错过，真人提醒更稳。",
                    "script": "快到站了，先坐稳，准备下车。下车后看照片确认位置。",
                }
            )
        if step_type == "DESTINATION" and not _has_custom_voice(step, "arrived"):
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "arrived",
                    "priority": "MUST",
                    "reason": "终点确认最好用家人的声音，让老人放心。",
                    "script": "已经快到了，请看照片确认入口。找到了就点我找到了。",
                }
            )
        if step_type == "START" and not _has_custom_voice(step, "enter"):
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "enter",
                    "priority": "SHOULD",
                    "reason": "第一句话由家人来说，老人更容易开始行动。",
                    "script": "现在出发，先看照片，找到这个地方后再继续。",
                }
            )
        if step_type in {"LEFT", "RIGHT"} and not first_turn_seen and not _has_custom_voice(step, "near"):
            first_turn_seen = True
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "near",
                    "priority": "SHOULD",
                    "reason": "第一次转弯建议用真人语音降低紧张感。",
                    "script": "快到转弯的地方了，先看照片，确认后再转。",
                }
            )
        if step_type in TRANSIT_TYPES and not first_transit_seen and not _has_custom_voice(step, "enter"):
            first_transit_seen = True
            voice_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "voiceType": "enter",
                    "priority": "SHOULD",
                    "reason": "第一次乘坐公共交通，建议用真人语音解释要做什么。",
                    "script": "现在到坐车这一步了，先确认站牌和方向，不着急。",
                }
            )

        if risk == "HIGH":
            review_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "MUST",
                    "checkItem": "高风险点是否有实拍照片和地标",
                    "reason": "高风险步骤必须让家属确认照片、地标和语音一致。",
                }
            )
        if step_type in {"LEFT", "RIGHT"}:
            review_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "SHOULD",
                    "checkItem": "转弯语音是否只在接近时提示方向",
                    "reason": "过早提示左转或右转会让老人提前转错。",
                }
            )
        if step_type in {"BUS_ON", "BUS_OFF"}:
            review_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "MUST",
                    "checkItem": "公交站名、线路和方向是否正确",
                    "reason": "公交步骤必须避免坐反方向或提前下车。",
                }
            )
        if step_type == "DESTINATION":
            review_tasks.append(
                {
                    "stepId": step.get("id"),
                    "stepNo": step.get("stepNo"),
                    "priority": "MUST",
                    "checkItem": "终点是否是实际入口",
                    "reason": "地图 POI 中心不一定是老人能进入的门口。",
                }
            )

    test_tasks = [
        {"order": 1, "title": "家属先走一遍", "description": "确认照片、地标、语音和现场方向一致。"},
        {"order": 2, "title": "陪老人走一遍", "description": "家属跟在旁边，不主动提示，观察老人是否能靠语音和照片前进。"},
        {"order": 3, "title": "记录每一步结果", "description": "每个锚点记录 FOUND、NOT_FOUND 或 HELP。"},
        {"order": 4, "title": "优化找不到的点", "description": "NOT_FOUND 的步骤优先补照片、地标或真人语音。"},
        {"order": 5, "title": "重审求助点", "description": "HELP 的步骤按高风险重新审核，再进行下一次测试。"},
    ]
    estimate_minutes = max(10, len(photo_tasks) * 2 + len(landmark_tasks) + len(voice_tasks))
    summary = (
        f"本路线建议采集 {len(photo_tasks)} 张照片、补充 {len(landmark_tasks)} 个地标、"
        f"录制 {len(voice_tasks)} 段真人语音，预计耗时 {estimate_minutes} 分钟。"
    )
    return {
        "summary": summary,
        "photoTasks": photo_tasks,
        "landmarkTasks": landmark_tasks,
        "voiceTasks": voice_tasks,
        "reviewTasks": review_tasks,
        "testTasks": test_tasks,
    }


def _safe_task(value: Any, kind: str, step_ids: set[str], step_nos: set[int]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    step_id = str(value.get("stepId") or "")
    if kind != "test" and step_id not in step_ids:
        return None
    step_no = value.get("stepNo")
    if kind != "test" and step_no not in step_nos:
        return None
    priority = value.get("priority")
    if kind != "test" and priority not in PRIORITIES:
        return None
    if kind in {"landmark", "voice", "review"} and priority == "OPTIONAL":
        return None
    if kind == "photo":
        return {
            "stepId": step_id,
            "stepNo": step_no,
            "priority": priority,
            "reason": _clean_text(value.get("reason"), 100),
            "shootingGuide": _clean_text(value.get("shootingGuide"), 120),
            "badExamples": [
                _clean_text(item, 40)
                for item in (_list_value(value.get("badExamples")) or BAD_PHOTO_EXAMPLES)[:3]
            ],
        }
    if kind == "landmark":
        return {
            "stepId": step_id,
            "stepNo": step_no,
            "priority": priority,
            "reason": _clean_text(value.get("reason"), 100),
            "suggestedLandmarkTypes": [
                _clean_text(item, 20)
                for item in _list_value(value.get("suggestedLandmarkTypes"))[:5]
            ],
            "exampleText": _clean_text(value.get("exampleText"), 80),
        }
    if kind == "voice":
        voice_type = value.get("voiceType")
        if voice_type not in VOICE_TYPES:
            return None
        return {
            "stepId": step_id,
            "stepNo": step_no,
            "voiceType": voice_type,
            "priority": priority,
            "reason": _clean_text(value.get("reason"), 100),
            "script": _clean_text(value.get("script"), 80),
        }
    if kind == "review":
        return {
            "stepId": step_id,
            "stepNo": step_no,
            "priority": priority,
            "checkItem": _clean_text(value.get("checkItem"), 80),
            "reason": _clean_text(value.get("reason"), 100),
        }
    if kind == "test":
        return {
            "order": int(value.get("order") or 0),
            "title": _clean_text(value.get("title"), 40),
            "description": _clean_text(value.get("description"), 120),
        }
    return None


def _validate_plan(value: Any, route: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    steps = route.get("steps") or []
    step_ids = {str(step.get("id")) for step in steps}
    step_nos = {step.get("stepNo") for step in steps}
    context = _route_context(route)
    plan = {
        "summary": _clean_text(value.get("summary"), 220),
        "photoTasks": [],
        "landmarkTasks": [],
        "voiceTasks": [],
        "reviewTasks": [],
        "testTasks": [],
    }
    for output_key, input_key, kind in (
        ("photoTasks", "photoTasks", "photo"),
        ("landmarkTasks", "landmarkTasks", "landmark"),
        ("voiceTasks", "voiceTasks", "voice"),
        ("reviewTasks", "reviewTasks", "review"),
        ("testTasks", "testTasks", "test"),
    ):
        for item in (value.get(input_key) or [])[:80]:
            task = _safe_task(item, kind, step_ids, step_nos)
            if task and not _has_ungrounded_assertion(task, context):
                plan[output_key].append(task)
    if not plan["summary"]:
        plan["summary"] = "已生成真实路线采集清单，请家属现场确认。"
    return plan


def _merge_required(ai_plan: dict[str, Any], fallback_plan: dict[str, Any]) -> dict[str, Any]:
    for key, kind in (
        ("photoTasks", "photo"),
        ("landmarkTasks", "landmark"),
        ("voiceTasks", "voice"),
        ("reviewTasks", "review"),
    ):
        for task in fallback_plan.get(key, []):
            if task.get("priority") == "MUST":
                _append_unique(ai_plan[key], task, kind)
    if not ai_plan.get("testTasks"):
        ai_plan["testTasks"] = fallback_plan["testTasks"]
    return ai_plan


def generate_collection_plan(
    route: dict[str, Any],
    history: dict[str, Any] | None = None,
    *,
    api_key: str,
    base_url: str,
    model: str,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    fallback = fallback_collection_plan(route, history)
    steps = route.get("steps") or []
    if not api_key or not steps:
        return fallback
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "route": {
                                "id": route.get("id"),
                                "name": route.get("name"),
                                "origin": route.get("origin"),
                                "destination": route.get("destination"),
                            },
                            "steps": [
                                _step_input(
                                    step,
                                    steps[index + 1] if index + 1 < len(steps) else None,
                                    history,
                                )
                                for index, step in enumerate(steps)
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=45, context=ssl_context) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        plan = _validate_plan(json.loads(content), route)
        if not plan:
            return fallback
        return _merge_required(plan, fallback)
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
        return fallback
