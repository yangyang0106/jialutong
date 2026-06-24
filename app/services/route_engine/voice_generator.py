from typing import Any


def _is_road_crossing(step: dict[str, Any]) -> bool:
    instruction = ((step.get("source") or {}).get("instruction") or "")
    return any(
        keyword in instruction
        for keyword in ("过马路", "穿过马路", "横穿", "人行横道", "红绿灯")
    )


def _turn_voice(step: dict[str, Any], direction: str) -> dict[str, str]:
    target = f"{direction}进入{step['roadName']}" if step.get("roadName") else direction
    landmark = f"看到{step['landmarkHint']}后，" if step.get("landmarkHint") else ""
    if _is_road_crossing(step):
        return {
            "enterVoice": f"请往前走，{landmark}到前面过马路的位置停下。",
            "nearVoice": f"快到路口了，{landmark}请先停一下，确认安全后过马路，再{target}。",
            "repeatVoice": "请继续往前走，我会提醒您转弯。",
        }
    return {
        "enterVoice": f"请往前走，{landmark}暂时不用转弯。",
        "nearVoice": f"快到了，{landmark}请{target}。",
        "repeatVoice": "请继续往前走，我会提醒您转弯。",
    }


def _direction_voice(direction: str) -> str:
    if not direction:
        return ""
    return f"，{direction}" if direction.startswith("开往") else f"，开往{direction}"


def _base_voice(step: dict[str, Any], destination_name: str) -> dict[str, str]:
    transit = step.get("transit") or {}
    transit_direction = _direction_voice(transit.get("direction", ""))
    entrance = transit.get("accessName") or "家人确认过的入口"
    exit_name = transit.get("accessName") or "家人确认过的出口"
    step_type = step.get("type")
    if step_type == "START":
        return {
            "enterVoice": f"现在带您去{destination_name}，请先从这里出发。",
            "nearVoice": "已经准备好了，请看照片确认方向。",
            "repeatVoice": "请按照照片中的方向继续走。",
        }
    if step_type == "LEFT":
        return _turn_voice(step, "左转")
    if step_type == "RIGHT":
        return _turn_voice(step, "右转")
    if step_type == "STRAIGHT":
        title = step.get("title") or ""
        return {
            "enterVoice": f"请{title}。" if title else "请继续往前走。",
            "nearVoice": "快到了，请看照片确认前方地点。",
            "repeatVoice": f"请继续{title}。" if title else "请继续往前走。",
        }
    if step_type == "BUS_ON":
        return {
            "enterVoice": f"请走到{transit.get('stationName') or '公交站'}，等待{transit.get('lineName') or '公交车'}{transit_direction}。",
            "nearVoice": f"已经到公交站附近，请确认是{transit.get('lineName') or '要乘坐的公交车'}{transit_direction}再上车。",
            "repeatVoice": f"请在这里等待{transit.get('lineName') or '公交车'}{transit_direction}，不要走开。",
        }
    if step_type == "BUS_OFF":
        return {
            "enterVoice": "请安心坐车，还没有到站。",
            "nearVoice": f"下一站{transit.get('stationName') or ''}，请准备下车。",
            "repeatVoice": "请继续坐车，不要提前下车。",
        }
    if step_type == "SUBWAY_IN":
        return {
            "enterVoice": f"请前往{transit.get('stationName') or '地铁站'}，从{entrance}进站{transit_direction}。",
            "nearVoice": f"已经到地铁站附近，请先停一下，确认从{entrance}进站。",
            "repeatVoice": f"请找到{entrance}，不要从其他入口进站。",
        }
    if step_type == "SUBWAY_OUT":
        return {
            "enterVoice": f"请在{transit.get('stationName') or '目标站'}下车。",
            "nearVoice": f"到站后请从{exit_name}出站。",
            "repeatVoice": f"请找到{exit_name}，不要走错出口，找不到就联系家人。",
        }
    if step_type == "TRANSFER":
        return {
            "enterVoice": f"请在{transit.get('stationName') or '当前站'}下车，站内换乘{transit.get('lineName') or '下一条线路'}{transit_direction}，不要出站。",
            "nearVoice": f"请跟着站内指示，换乘{transit.get('lineName') or '下一条线路'}{transit_direction}，不要走到出站口。",
            "repeatVoice": "这是站内换乘，不要出站。找不到请联系家人。",
        }
    if step_type == "DESTINATION":
        return {
            "enterVoice": f"快到{destination_name}了，请继续找照片里的地方。",
            "nearVoice": "您已经到达目的地。",
            "repeatVoice": "请在这里等家人。",
        }
    return {
        "enterVoice": "请继续往前走。",
        "nearVoice": "快到了，请看照片。",
        "repeatVoice": "请按照照片继续走。",
    }


def _strengthen_high_risk(voice: dict[str, str], step: dict[str, Any]) -> dict[str, str]:
    is_walking_turn = step.get("type") in {"LEFT", "RIGHT"}
    repeat_voice = (
        voice["repeatVoice"]
        if "找不到" in voice["repeatVoice"] and "联系家人" in voice["repeatVoice"]
        else f"{voice['repeatVoice']}找不到请联系家人。"
    )
    return {
        "enterVoice": voice["enterVoice"]
        if is_walking_turn or voice["enterVoice"].startswith("请先停一下")
        else f"请先停一下。{voice['enterVoice']}",
        "nearVoice": voice["nearVoice"]
        if "确认安全" in voice["nearVoice"]
        else f"{voice['nearVoice']}确认安全后再继续。",
        "repeatVoice": repeat_voice,
    }


def generate_step_voice(step: dict[str, Any], destination_name: str) -> dict[str, str]:
    base = _base_voice(step, destination_name)
    generated = _strengthen_high_risk(base, step) if step.get("riskLevel") == "HIGH" else base
    return {
        "voiceType": "SYSTEM",
        "audioUrl": "",
        **generated,
        "arrivedVoiceText": f"您已经到达{destination_name}。"
        if step.get("type") == "DESTINATION"
        else "您已接近目标地点，请看照片确认。",
        "offRouteVoiceText": "好像走远了，请先停一下，不要继续走。需要帮助请联系家人。",
        "enterVoiceText": generated["enterVoice"],
        "repeatVoiceText": generated["repeatVoice"],
        "nearVoiceText": generated["nearVoice"],
        "enterAudioUrl": "",
        "repeatAudioUrl": "",
        "nearAudioUrl": "",
        "arrivedAudioUrl": "",
        "offRouteAudioUrl": "",
        "enterVoiceType": "SYSTEM",
        "repeatVoiceType": "SYSTEM",
        "nearVoiceType": "SYSTEM",
        "arrivedVoiceType": "SYSTEM",
        "offRouteVoiceType": "SYSTEM",
    }
