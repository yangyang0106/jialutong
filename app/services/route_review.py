from typing import Any

from app.services.voice import VOICE_MOMENTS, normalize_route_voices, normalize_voice, voice_field


def get_step_blocking_issues(step: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    voice = normalize_voice(step)
    if any(not voice.get(voice_field(moment, "VoiceText"), "").strip() for moment in VOICE_MOMENTS):
        issues.append("缺少完整语音文案")
    location = step.get("location") or {}
    if location.get("latitude") is None or location.get("longitude") is None:
        issues.append("缺少锚点坐标")
    if step.get("requiresFamilyReview") and step.get("reviewStatus") != "APPROVED":
        issues.append("等待家属确认")
    if step.get("aiConfidence") == "LOW" and step.get("reviewStatus") != "APPROVED":
        issues.append("低置信度 AI 文案需要家属确认")
    if step.get("riskLevel") == "HIGH":
        if step.get("reviewStatus") != "APPROVED":
            issues.append("高风险步骤未确认")
        if step.get("imageStatus") != "FAMILY":
            issues.append("高风险步骤需要家属实拍照片")
        if step.get("type") in {"LEFT", "RIGHT", "STRAIGHT"} and not step.get("landmarkHint", "").strip():
            issues.append("高风险路口需要填写地标提示")
    if step.get("type") in {"BUS_ON", "BUS_OFF"}:
        transit = step.get("transit") or {}
        if not transit.get("lineName") or not transit.get("stationName"):
            issues.append("公交线路或站点不完整")
    return issues


def build_review_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_steps = []
    if not steps:
        blocking_steps.append(
            {"stepNo": 0, "type": "ROUTE", "issues": ["路线没有锚点"]}
        )
    for step in steps:
        issues = get_step_blocking_issues(step)
        if issues:
            blocking_steps.append(
                {"stepNo": step["stepNo"], "type": step["type"], "issues": issues}
            )
    return {
        "totalSteps": len(steps),
        "pendingReviewSteps": len(blocking_steps),
        "highRiskSteps": sum(step.get("riskLevel") == "HIGH" for step in steps),
        "missingPhotoSteps": sum(step.get("imageStatus") == "NONE" for step in steps),
        "blockingSteps": blocking_steps,
        "ready": not blocking_steps,
    }


def _derive_lifecycle_status(route: dict[str, Any], summary: dict[str, Any]) -> str:
    status = route.get("status")
    if status == "PUBLISHED":
        return "PUBLISHED"
    if status == "DISABLED":
        return "DISABLED"
    if status == "ARCHIVED":
        return "ARCHIVED"
    if summary["blockingSteps"]:
        return "WAITING_REVIEW"
    return "DRAFT"


def _derive_review_level(route: dict[str, Any], summary: dict[str, Any]) -> str:
    if route.get("reviewLevel") == "SELF_REVIEWED":
        return "SELF_REVIEWED"
    if route.get("status") == "PUBLISHED" and summary["ready"]:
        return route.get("reviewLevel") or "GUARDIAN_REVIEWED"
    steps = route.get("steps", [])
    if steps and summary["ready"] and all(
        step.get("reviewStatus") == "APPROVED" and step.get("reviewedByRole") == "FAMILY_ADMIN"
        for step in steps
    ):
        return "GUARDIAN_REVIEWED"
    return "UNREVIEWED"


def refresh_route_review(route: dict[str, Any], now_iso) -> dict[str, Any]:
    normalize_route_voices(route)
    summary = build_review_summary(route.get("steps", []))
    route["reviewSummary"] = summary
    if route.get("status") not in {"PUBLISHED", "DISABLED", "ARCHIVED"}:
        route["status"] = "READY" if summary["ready"] else "NEEDS_REVIEW"
    route["lifecycleStatus"] = _derive_lifecycle_status(route, summary)
    route["reviewLevel"] = _derive_review_level(route, summary)
    route["updatedAt"] = now_iso()
    return route
