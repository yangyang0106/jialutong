import json
import re
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VOICE_FIELDS = (
    "enterVoiceText",
    "repeatVoiceText",
    "nearVoiceText",
    "arrivedVoiceText",
    "offRouteVoiceText",
)
OUTPUT_FIELDS = (
    "elderShortAction",
    *VOICE_FIELDS,
    "landmarkSuggestion",
    "photoSuggestion",
    "familyReviewFocus",
)
UNCERTAIN_WORDS = ("可能", "大概", "随便")
TURN_WORDS = ("左转", "右转", "左前方转", "右前方转")
UNGROUNDED_VISUAL_WORDS = (
    "红色",
    "黄色",
    "蓝色",
    "绿色",
    "金色",
    "银色",
    "大铁门",
    "铁艺门",
    "石碑",
    "喷泉",
    "大草坪",
    "顶棚",
    "电子屏",
    "便利店",
    "银行",
    "小店",
    "门卫室",
)

SYSTEM_PROMPT = """你是老人出行语音导航文案助手。

用户对象是 50 岁以上、识字能力弱、不熟悉城市、主要靠语音和照片出行的老人。
你只能根据已有 RouteStep 和百度 originalInstruction 生成文案与家属建议。

严格禁止：
- 修改路线坐标、步骤类型或交通信息
- 新增、删除、合并路线步骤
- 编造公交线路、地铁线路、站名、出口、道路、建筑或地标
- 使用东南西北

文案规则：
- 每句话只表达一个动作，使用自然口语和短句
- enterVoice 只告诉老人现在先继续走、等待或乘车，不提前说左转或右转
- 只有 nearVoice 可以告诉老人准备左转或右转
- arrivedVoice 告诉老人已接近目标，确认后点“我找到了”
- offRouteVoice 告诉老人先停下、不要继续走，并建议求助
- 车辆未停稳时不得提示老人站起来或走动车内
- HIGH 风险步骤必须加入“先停一下，看清楚再走”
- 信息不足时写“需要家属确认”，禁止猜测

只输出 JSON：
{"steps":[{"stepId","elderShortAction","enterVoiceText","repeatVoiceText",
"nearVoiceText","arrivedVoiceText","offRouteVoiceText","landmarkSuggestion",
"photoSuggestion","familyReviewFocus","aiConfidence"}]}
aiConfidence 只能是 HIGH、MEDIUM、LOW。每条语音文案不超过 60 个汉字。"""


def step_input(step: dict[str, Any]) -> dict[str, Any]:
    source = step.get("source") or {}
    location = step.get("location") or {}
    return {
        "stepId": step.get("id"),
        "type": step.get("type"),
        "title": step.get("title"),
        "shortAction": step.get("shortAction"),
        "originalInstruction": source.get("instruction", ""),
        "riskLevel": step.get("riskLevel"),
        "landmarkHint": step.get("landmarkHint"),
        "roadName": step.get("roadName"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "transit": step.get("transit"),
        "distance": source.get("distance", 0),
        "direction": step.get("direction"),
    }


def fallback_step(step: dict[str, Any]) -> dict[str, Any]:
    voice = step.get("voice") or {}
    return {
        "stepId": step["id"],
        "elderShortAction": step.get("elderShortAction") or step.get("shortAction") or "",
        **{field: voice.get(field, "") for field in VOICE_FIELDS},
        "landmarkSuggestion": step.get("landmarkSuggestion") or "需要家属确认并补充固定地标。",
        "photoSuggestion": step.get("photoSuggestion") or "建议家属补充面向行进方向的实景照片。",
        "familyReviewFocus": step.get("familyReviewFocus") or "需要家属确认这一步是否容易理解。",
        "aiConfidence": "LOW",
        "needsReview": True,
    }


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", "", str(value or "")).strip()
    return text[:limit]


def _source_context(step: dict[str, Any]) -> str:
    source = step.get("source") or {}
    transit = step.get("transit") or {}
    return json.dumps(
        {
            "title": step.get("title"),
            "shortAction": step.get("shortAction"),
            "instruction": source.get("instruction"),
            "roadName": step.get("roadName"),
            "landmarkHint": step.get("landmarkHint"),
            "transit": transit,
        },
        ensure_ascii=False,
    )


def _has_ungrounded_transit_name(text: str, step: dict[str, Any]) -> bool:
    context = _source_context(step)
    terms = re.findall(
        r"(?:乘坐|等待|换乘|开往|从|在|到)([\u4e00-\u9fffA-Za-z0-9]+?(?:号线|路|站|口))",
        text,
    )
    generic = {"公交站", "地铁站", "目标站", "路口", "入口", "出口"}
    return any(term not in generic and term not in context for term in terms)


def _has_ungrounded_visual_detail(text: str, step: dict[str, Any]) -> bool:
    context = _source_context(step)
    return any(word in text and word not in context for word in UNGROUNDED_VISUAL_WORDS)


def _safe_voice_fallback(
    field: str, step: dict[str, Any], fallback: str, *, invalid_turn_timing: bool = False
) -> str:
    if invalid_turn_timing:
        return {
            "enterVoiceText": "请先继续往前走，暂时不用转弯。",
            "repeatVoiceText": "请继续往前走，我会提醒您下一步。",
            "arrivedVoiceText": "您已接近目标地点，请确认后点我找到了。",
        }.get(field, fallback)
    step_type = step.get("type")
    if step_type == "DESTINATION":
        if field == "enterVoiceText":
            return "快到目的地了，请继续找照片里的地方。"
        if field == "repeatVoiceText":
            return "请继续找照片里的地方，还没有确认到达。"
    if step_type == "BUS_OFF" and field == "nearVoiceText":
        return "快到站了，请先坐稳，准备下车。"
    if step_type in {"LEFT", "RIGHT"}:
        if field == "enterVoiceText":
            return "请先继续往前走，暂时不用转弯。"
        if field == "repeatVoiceText":
            return "请继续往前走，我会提醒您转弯。"
        if field == "arrivedVoiceText":
            return "您已接近目标地点，请确认后点我找到了。"
    if step_type == "BUS_ON" and field == "arrivedVoiceText":
        return "您已到上车地点，请确认站牌和乘车方向。"
    return fallback


def validate_step_output(value: Any, step: dict[str, Any]) -> dict[str, Any]:
    fallback = fallback_step(step)
    if not isinstance(value, dict) or value.get("stepId") != step.get("id"):
        return fallback
    result = {"stepId": step["id"]}
    needs_review = step.get("riskLevel") == "HIGH"
    for field in OUTPUT_FIELDS:
        limit = 60 if field in VOICE_FIELDS else 100
        text = _clean_text(value.get(field), limit)
        invalid_turn_timing = (
            field in {"enterVoiceText", "repeatVoiceText", "arrivedVoiceText"}
            and any(word in text for word in TURN_WORDS)
        )
        premature_arrival = (
            step.get("type") == "DESTINATION"
            and field in {"enterVoiceText", "repeatVoiceText"}
            and any(word in text for word in ("已到达", "已经到达", "到了"))
        )
        unsafe_bus_movement = (
            step.get("type") == "BUS_OFF"
            and field in VOICE_FIELDS
            and any(word in text for word in ("站起来", "起身", "走到车门"))
        )
        if (
            not text
            or invalid_turn_timing
            or premature_arrival
            or unsafe_bus_movement
            or _has_ungrounded_transit_name(text, step)
            or _has_ungrounded_visual_detail(text, step)
        ):
            text = _safe_voice_fallback(
                field,
                step,
                fallback[field],
                invalid_turn_timing=invalid_turn_timing,
            )
            needs_review = True
        if any(word in text for word in UNCERTAIN_WORDS):
            needs_review = True
        result[field] = text
    confidence = value.get("aiConfidence")
    result["aiConfidence"] = confidence if confidence in {"HIGH", "MEDIUM", "LOW"} else "LOW"
    result["needsReview"] = needs_review or result["aiConfidence"] == "LOW"
    return result


def generate_step_copy(
    route: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    ssl_context: ssl.SSLContext | None = None,
) -> list[dict[str, Any]] | None:
    steps = route.get("steps") or []
    if not api_key or not steps:
        return None
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
                            "routeName": route.get("name"),
                            "originName": (route.get("origin") or {}).get("name"),
                            "destinationName": (route.get("destination") or {}).get("name"),
                            "steps": [step_input(step) for step in steps],
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
            result = json.loads(response.read().decode("utf-8"))
        raw_steps = json.loads(result["choices"][0]["message"]["content"]).get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) > len(steps):
            return None
        by_id = {item.get("stepId"): item for item in raw_steps if isinstance(item, dict)}
        if len(by_id) != len(raw_steps):
            return None
        return [validate_step_output(by_id.get(step["id"]), step) for step in steps]
    except (
        HTTPError,
        URLError,
        TimeoutError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
