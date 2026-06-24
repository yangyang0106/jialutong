import json
from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.auth import family_guard, require_family_admin
from app.services.voice import VOICE_MOMENTS, normalize_route_voices, normalize_voice, voice_field


def create_ai_router(
    *,
    require_token,
    engine_routes_lock: Lock,
    load_engine_routes: Callable[[], dict[str, Any]],
    save_engine_routes: Callable[[dict[str, Any]], None],
    refresh_route_review: Callable[[dict[str, Any]], dict[str, Any]],
    build_step_result_history: Callable[[str], dict[str, dict[str, int]]],
    generate_step_copy,
    generate_collection_plan,
    ai_config: Callable[[], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/engine/routes/{route_id}/ai-generate-voices",
    )
    def ai_generate_route_voices(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        require_family_admin(principal)
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            if route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route is immutable")
        suggestions = generate_step_copy(route, **ai_config())
        if suggestions is None:
            return {
                "route": normalize_route_voices(route),
                "generated": False,
                "message": "AI文案暂不可用，已保留原有系统文案。",
            }
        suggestions_by_id = {item["stepId"]: item for item in suggestions}
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route or route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="route changed while generating")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            for step in route.get("steps", []):
                suggestion = suggestions_by_id.get(step["id"])
                if not suggestion:
                    continue
                normalize_voice(step)
                voice = step["voice"]
                for moment in VOICE_MOMENTS:
                    text_key = voice_field(moment, "VoiceText")
                    audio_key = voice_field(moment, "AudioUrl")
                    type_key = voice_field(moment, "VoiceType")
                    if voice.get(type_key) == "CUSTOM":
                        continue
                    voice[text_key] = suggestion[text_key]
                    if voice.get(type_key) == "TTS":
                        voice[audio_key] = ""
                    voice[type_key] = "SYSTEM"
                step["voice"] = voice
                step["elderShortAction"] = suggestion["elderShortAction"]
                step["landmarkSuggestion"] = suggestion["landmarkSuggestion"]
                step["photoSuggestion"] = suggestion["photoSuggestion"]
                step["familyReviewFocus"] = suggestion["familyReviewFocus"]
                step["aiConfidence"] = suggestion["aiConfidence"]
                step["needsReview"] = suggestion["needsReview"]
                if suggestion["needsReview"]:
                    step["requiresFamilyReview"] = True
                    step["reviewStatus"] = "PENDING"
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return {"route": route, "generated": True, "message": "AI语音建议已生成，请家属审核。"}

    @router.post(
        "/api/engine/routes/{route_id}/collection-plan",
    )
    def generate_route_collection_plan(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            route_copy = json.loads(json.dumps(route, ensure_ascii=False))
        route_copy = normalize_route_voices(route_copy)
        history = build_step_result_history(route_id)
        return generate_collection_plan(route_copy, history, **ai_config())

    return router
