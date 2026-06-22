from typing import Any


RESULT_KEYS = ("FOUND", "NOT_FOUND", "HELP")


def _empty_counts() -> dict[str, int]:
    return {"FOUND": 0, "NOT_FOUND": 0, "HELP": 0}


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0


def _health_level(found_rate: float, help_rate: float) -> str:
    if found_rate >= 0.85 and help_rate <= 0.05:
        return "GOOD"
    if found_rate < 0.6 or help_rate > 0.15:
        return "BAD"
    return "WARNING"


def _problem_level(found: int, not_found: int, help_count: int) -> str:
    if help_count >= 2 or not_found >= 3:
        return "SERIOUS"
    if not_found >= 1 or help_count >= 1:
        return "NEEDS_ATTENTION"
    return "NORMAL"


def _suggested_action(step: dict[str, Any], problem_level: str) -> str:
    if problem_level == "NORMAL":
        return "暂时不需要处理，继续观察。"
    if step.get("riskLevel") == "HIGH":
        return "高风险步骤出现问题，请重新审核照片、地标和真人语音。"
    if step.get("imageStatus") != "FAMILY":
        return "建议补充或重拍家属实景照片。"
    if not step.get("landmarkHint"):
        return "建议补充固定地标，让语音和照片更容易对应。"
    voice = step.get("voice") or {}
    has_custom = any(
        voice.get(f"{moment}VoiceType") == "CUSTOM" and voice.get(f"{moment}AudioUrl")
        for moment in ("enter", "repeat", "near", "arrived", "offRoute")
    )
    if not has_custom:
        return "建议为这一步录制真人语音，尤其是接近和偏航提醒。"
    return "建议家属陪同复测，记录老人卡住的位置。"


def build_route_review_center(route: dict[str, Any], trip_results: list[dict[str, Any]]) -> dict[str, Any]:
    route_id = route.get("id")
    route_results = [item for item in trip_results if item.get("routeId") == route_id]
    trip_ids = {item.get("tripId") for item in route_results if item.get("tripId")}
    completed_trip_ids = {
        item.get("tripId")
        for item in route_results
        if item.get("tripId") and item.get("stepResult") in RESULT_KEYS
    }
    totals = _empty_counts()
    step_counts: dict[str, dict[str, int]] = {}
    for item in route_results:
        result = item.get("stepResult")
        if result not in RESULT_KEYS:
            continue
        totals[result] += 1
        for key in (item.get("stepId"), item.get("stepNo")):
            if key is None:
                continue
            entry = step_counts.setdefault(str(key), _empty_counts())
            entry[result] += 1

    total_events = sum(totals.values())
    found_rate = _rate(totals["FOUND"], total_events)
    not_found_rate = _rate(totals["NOT_FOUND"], total_events)
    help_rate = _rate(totals["HELP"], total_events)
    step_stats = []
    for step in route.get("steps", []):
        counts = _empty_counts()
        for key in (step.get("stepNo"), step.get("id")):
            source = step_counts.get(str(key))
            if not source:
                continue
            for result in RESULT_KEYS:
                counts[result] = max(counts[result], source[result])
        step_total = sum(counts.values())
        problem_level = _problem_level(counts["FOUND"], counts["NOT_FOUND"], counts["HELP"])
        step_stats.append(
            {
                "stepId": step.get("id"),
                "stepNo": step.get("stepNo"),
                "type": step.get("type"),
                "title": step.get("title"),
                "elderShortAction": step.get("elderShortAction") or step.get("shortAction"),
                "riskLevel": step.get("riskLevel", "LOW"),
                "foundCount": counts["FOUND"],
                "notFoundCount": counts["NOT_FOUND"],
                "helpCount": counts["HELP"],
                "foundRate": _rate(counts["FOUND"], step_total),
                "notFoundRate": _rate(counts["NOT_FOUND"], step_total),
                "helpRate": _rate(counts["HELP"], step_total),
                "problemLevel": problem_level,
                "suggestedAction": _suggested_action(step, problem_level),
            }
        )
    problem_steps = [
        item for item in step_stats if item["problemLevel"] != "NORMAL"
    ]
    severity = {"SERIOUS": 2, "NEEDS_ATTENTION": 1, "NORMAL": 0}
    risk_weight = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    problem_steps.sort(
        key=lambda item: (
            severity[item["problemLevel"]],
            item["helpCount"],
            item["notFoundCount"],
            risk_weight.get(item["riskLevel"], 0),
        ),
        reverse=True,
    )
    return {
        "routeId": route_id,
        "routeName": route.get("name", ""),
        "totalTrips": len(trip_ids),
        "completedTrips": len(completed_trip_ids),
        "foundCount": totals["FOUND"],
        "notFoundCount": totals["NOT_FOUND"],
        "helpCount": totals["HELP"],
        "foundRate": found_rate,
        "notFoundRate": not_found_rate,
        "helpRate": help_rate,
        "routeHealthLevel": _health_level(found_rate, help_rate),
        "problemSteps": problem_steps,
        "stepStats": step_stats,
    }
