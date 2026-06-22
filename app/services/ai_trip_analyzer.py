import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """你是家路通的路线失败分析助手。

你只能根据已有 Route、RouteStep、照片/地标/语音状态和 FOUND/NOT_FOUND/HELP 统计，给家属生成优化建议。

严格禁止：
- 修改路线坐标
- 新增、删除或合并路线步骤
- 编造现场不存在的地标
- 在没有 landmarkHint 时写具体地标名称
- 自动通过审核或发布路线

输出 JSON：
{"routeSummary":"","problemSteps":[{"stepId":"","stepNo":1,"problem":"","possibleReasons":[],"suggestedFixes":[],"priority":"HIGH|MEDIUM|LOW"}]}

建议要具体、短句、适合家属执行。"""


def _voice_texts(step: dict[str, Any]) -> dict[str, str]:
    voice = step.get("voice") or {}
    return {
        "enterVoiceText": voice.get("enterVoiceText", ""),
        "nearVoiceText": voice.get("nearVoiceText", ""),
        "arrivedVoiceText": voice.get("arrivedVoiceText", ""),
        "offRouteVoiceText": voice.get("offRouteVoiceText", ""),
    }


def _has_custom_voice(step: dict[str, Any]) -> bool:
    voice = step.get("voice") or {}
    return any(
        voice.get(f"{moment}VoiceType") == "CUSTOM" and voice.get(f"{moment}AudioUrl")
        for moment in ("enter", "repeat", "near", "arrived", "offRoute")
    )


def _has_tts(step: dict[str, Any]) -> bool:
    voice = step.get("voice") or {}
    return any(
        voice.get(f"{moment}VoiceType") == "TTS" and voice.get(f"{moment}AudioUrl")
        for moment in ("enter", "repeat", "near", "arrived", "offRoute")
    )


def _step_input(step: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "stepId": step.get("id"),
        "stepNo": step.get("stepNo"),
        "type": step.get("type"),
        "title": step.get("title"),
        "elderShortAction": step.get("elderShortAction") or step.get("shortAction"),
        "riskLevel": step.get("riskLevel", "LOW"),
        "landmarkHint": step.get("landmarkHint", ""),
        "imageStatus": step.get("imageStatus", "NONE"),
        "hasPhoto": bool(step.get("imageUrl")),
        "hasCustomVoice": _has_custom_voice(step),
        "hasTts": _has_tts(step),
        **_voice_texts(step),
        "foundCount": stats.get("foundCount", 0),
        "notFoundCount": stats.get("notFoundCount", 0),
        "helpCount": stats.get("helpCount", 0),
    }


def fallback_trip_analysis(route: dict[str, Any], review_center: dict[str, Any]) -> dict[str, Any]:
    problem_steps = []
    by_id = {item["stepId"]: item for item in review_center.get("stepStats", [])}
    for step in route.get("steps", []):
        stats = by_id.get(step.get("id"), {})
        not_found = int(stats.get("notFoundCount", 0) or 0)
        help_count = int(stats.get("helpCount", 0) or 0)
        if not not_found and not help_count:
            continue
        possible_reasons = []
        suggested_fixes = []
        if not_found:
            possible_reasons.extend(["照片可能不够明确", "语音或文字缺少可识别地标"])
            suggested_fixes.extend(["重新拍摄面向行进方向的照片", "请家属补充固定地标"])
        if help_count:
            possible_reasons.extend(["该锚点可能风险较高", "老人可能在这里无法判断下一步"])
            suggested_fixes.extend(["录制真人语音", "提高风险等级并重新审核", "必要时缩短前后锚点距离"])
        if step.get("riskLevel") == "HIGH":
            suggested_fixes.append("高风险步骤必须重新审核照片、地标和语音")
        priority = "HIGH" if help_count or step.get("riskLevel") == "HIGH" else "MEDIUM"
        problem_steps.append(
            {
                "stepId": step.get("id"),
                "stepNo": step.get("stepNo"),
                "problem": f"该步骤出现 {not_found} 次找不到、{help_count} 次求助。",
                "possibleReasons": list(dict.fromkeys(possible_reasons)),
                "suggestedFixes": list(dict.fromkeys(suggested_fixes)),
                "priority": priority,
            }
        )
    summary = (
        "这条路线暂时没有明显失败步骤。"
        if not problem_steps
        else f"这条路线有 {len(problem_steps)} 个步骤需要优化，请家属优先处理高风险和求助步骤。"
    )
    return {"routeSummary": summary, "problemSteps": problem_steps}


def _validate_analysis(value: Any, route: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    step_ids = {step.get("id") for step in route.get("steps", [])}
    result = {
        "routeSummary": str(value.get("routeSummary") or "请家属结合行程结果复盘路线。")[:160],
        "problemSteps": [],
    }
    for item in (value.get("problemSteps") or [])[:30]:
        if not isinstance(item, dict) or item.get("stepId") not in step_ids:
            continue
        priority = item.get("priority")
        if priority not in {"HIGH", "MEDIUM", "LOW"}:
            priority = "MEDIUM"
        result["problemSteps"].append(
            {
                "stepId": item.get("stepId"),
                "stepNo": item.get("stepNo"),
                "problem": str(item.get("problem") or "")[:120],
                "possibleReasons": [str(text)[:80] for text in (item.get("possibleReasons") or [])[:5]],
                "suggestedFixes": [str(text)[:80] for text in (item.get("suggestedFixes") or [])[:6]],
                "priority": priority,
            }
        )
    return result


def analyze_trip_failures(
    route: dict[str, Any],
    review_center: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    fallback = fallback_trip_analysis(route, review_center)
    if not api_key:
        return fallback
    by_id = {item["stepId"]: item for item in review_center.get("stepStats", [])}
    problem_steps = [
        _step_input(step, by_id.get(step.get("id"), {}))
        for step in route.get("steps", [])
        if by_id.get(step.get("id"), {}).get("notFoundCount", 0)
        or by_id.get(step.get("id"), {}).get("helpCount", 0)
    ]
    if not problem_steps:
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
                            "tripSummary": review_center,
                            "problemSteps": problem_steps,
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
        return _validate_analysis(json.loads(content), route) or fallback
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
        return fallback
