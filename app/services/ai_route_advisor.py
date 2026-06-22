import json
import re
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """你是老人出行路线顾问。

用户对象是 50 岁以上、识字能力较弱、不熟悉城市、害怕迷路的老人。
你只能基于百度地图提供的候选路线摘要做判断。

禁止：
- 自己编新路线
- 编造站点、公交线路、地铁线路或不存在的出口
- 编造建筑外观、颜色、招牌、店铺、道路设施或附近地标
- 修改坐标
- 直接让老人独立出行

必须输出 JSON，字段为：
recommendedPlanIndex, summary, reason, risks, photoSuggestions,
landmarkSuggestions, familyReviewFocus。
recommendedPlanIndex 必须是候选方案中真实存在的 index。
所有建议必须能从候选摘要中得到依据；不确定时应要求家属审核，不得编造。
候选摘要没有提供具体公交线路、站名、出口或地标时，只能写“请家属现场确认并补充”，
不得猜测或使用“例如、比如、如”等方式举例虚构的具体名称和外观。
比较数字时必须检查大小：duration 数值更小才是用时更短，distance 数值更小才是距离更短。
familyReviewFocus 至少输出一项。
输出前检查每个专有名词和具体外观描述是否来自候选摘要；不是则删除。"""


def fallback_advice(plans: list[dict[str, Any]]) -> dict[str, Any]:
    first_index = plans[0].get("index", 0) if plans else 0
    return {
        "recommendedPlanIndex": first_index,
        "summary": "默认使用百度第一条路线",
        "reason": "AI路线建议暂不可用，请家属人工审核。",
        "risks": ["请家属确认路线中的过马路、上下车和换乘位置"],
        "photoSuggestions": ["请为关键转弯、过马路和上下车位置补充照片"],
        "landmarkSuggestions": ["请补充容易辨认且长期不变的地标"],
        "familyReviewFocus": ["请完整核对路线步骤后再发布"],
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _remove_ungrounded_examples(value: str) -> str:
    cleaned = re.sub(r"[（(](?:例如|比如|如)[^）)]*[）)]", "", value)
    cleaned = re.sub(r"(?:例如|比如|如)[：:][^；;。]*", "", cleaned)
    return cleaned.strip(" ；;。") + ("。" if cleaned.strip(" ；;。") else "")


def _remove_incorrect_duration_claim(text: str, recommended_index: int, plans: list[dict[str, Any]]) -> str:
    recommended = next(
        (plan for plan in plans if int(plan.get("index", -1)) == recommended_index),
        {},
    )
    durations = [int(plan.get("duration") or 0) for plan in plans if int(plan.get("duration") or 0) > 0]
    recommended_duration = int(recommended.get("duration") or 0)
    if not durations or not recommended_duration or recommended_duration <= min(durations):
        return text
    cleaned = re.sub(r"[^，,。；;]*用时更短[^，,。；;]*[，,。；;]?", "", text)
    cleaned = re.sub(r"[^，,。；;]*节省[^，,。；;]*分钟[^，,。；;]*[，,。；;]?", "", cleaned)
    cleaned = re.sub(r"[^，,。；;]*更快[^，,。；;]*[，,。；;]?", "", cleaned).strip(" ，,。；;")
    return cleaned or "该方案不是用时最短，但可结合步行负担和风险点由家属审核。"


def _validate_advice(value: Any, plans: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("advisor response is not an object")
    valid_indexes = {int(plan.get("index", index)) for index, plan in enumerate(plans)}
    recommended_index = int(value.get("recommendedPlanIndex"))
    if recommended_index not in valid_indexes:
        raise ValueError("advisor recommended an unknown plan")
    risks = _string_list(value.get("risks")) or ["请家属完整确认候选路线中的风险点"]
    photo_suggestions = _string_list(value.get("photoSuggestions")) or [
        "请家属为关键转弯和上下车位置补充实景照片"
    ]
    landmark_suggestions = [
        _remove_ungrounded_examples(item)
        for item in _string_list(value.get("landmarkSuggestions"))
    ] or [
        "请家属现场确认并补充容易辨认的固定地标"
    ]
    family_review_focus = _string_list(value.get("familyReviewFocus")) or [
        "请家属完整核对路线步骤后再发布"
    ]
    reason = _remove_incorrect_duration_claim(
        str(value.get("reason") or "请家属结合实地情况审核。").strip(),
        recommended_index,
        plans,
    )
    summary = _remove_incorrect_duration_claim(
        str(value.get("summary") or f"推荐方案{recommended_index + 1}").strip(),
        recommended_index,
        plans,
    )
    return {
        "recommendedPlanIndex": recommended_index,
        "summary": summary,
        "reason": reason,
        "risks": risks,
        "photoSuggestions": photo_suggestions,
        "landmarkSuggestions": landmark_suggestions,
        "familyReviewFocus": family_review_focus,
    }


def advise_route(
    origin_name: str,
    destination_name: str,
    plans: list[dict[str, Any]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    fallback = fallback_advice(plans)
    if not api_key or not plans:
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
                            "originName": origin_name,
                            "destinationName": destination_name,
                            "plans": plans,
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
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=25, context=ssl_context) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        return _validate_advice(json.loads(content), plans)
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
        return fallback
