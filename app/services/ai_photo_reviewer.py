from typing import Any


def review_step_photo(
    step: dict[str, Any],
    *,
    image_url: str = "",
    image_status: str = "",
    file_size: int = 0,
) -> dict[str, Any]:
    status = image_status or step.get("imageStatus", "NONE")
    url = image_url or step.get("imageUrl", "")
    issues: list[str] = []
    suggestions: list[str] = []

    if status == "AUTO" or "staticimage" in url or "panorama" in url:
        issues.append("这可能不是家属实拍照片，不能直接用于真实出行。")
        suggestions.append("请家属到现场重新拍一张老人行进方向的实景照片。")
    if not url:
        issues.append("还没有照片。")
        suggestions.append("请补充实地照片。")
    if file_size and file_size < 50 * 1024:
        issues.append("照片文件较小，可能不够清晰。")
        suggestions.append("请确认照片没有压缩过度，最好重新拍摄。")
    if step.get("type") in {"BUS_ON", "BUS_OFF"}:
        suggestions.append("请拍清楚公交站牌上的站名、线路号和方向。")
    elif step.get("type") in {"LEFT", "RIGHT"}:
        suggestions.append("请站在老人走来的方向，拍清楚路口和转弯方向。")
    elif step.get("type") == "DESTINATION":
        suggestions.append("请拍清楚实际入口，不要只拍远景或地图截图。")
    else:
        suggestions.append("请家属人工确认照片是否能一眼看出目标。")

    if any("不是家属实拍" in issue or "还没有照片" in issue for issue in issues):
        result_status = "REJECT"
    elif issues:
        result_status = "WARNING"
    else:
        result_status = "PASS"
        issues.append("照片清晰度需由家属现场确认。")
        suggestions = ["照片可以使用，但建议确认老人能否看懂照片里的目标。"]
    return {
        "status": result_status,
        "issues": list(dict.fromkeys(issues)),
        "suggestions": list(dict.fromkeys(suggestions)),
        "needRetake": result_status == "REJECT",
        "mode": "RULE",
    }
