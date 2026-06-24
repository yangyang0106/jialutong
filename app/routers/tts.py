from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.auth import family_guard, require_family_admin
from app.schemas import BatchTtsRequest, TtsRequest, VoiceRenderRequest
from app.services import tencent_tts
from app.services.voice import VOICE_MOMENTS, normalize_voice, voice_field


def create_tts_router(
    *,
    require_token,
    engine_routes_lock: Lock,
    load_engine_routes: Callable[[], dict[str, Any]],
    save_engine_routes: Callable[[dict[str, Any]], None],
    refresh_route_review: Callable[[dict[str, Any]], dict[str, Any]],
    save_step_tts: Callable[[str, dict[str, Any], str, str], str],
    request_tencent_tts: Callable[[str], bytes],
    upload_dir,
    public_base_url: str,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/engine/routes/{route_id}/steps/{step_id}/tts",
    )
    def generate_engine_route_step_tts(
        route_id: str,
        step_id: str,
        tts_request: TtsRequest,
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
            step = next((item for item in route["steps"] if item["id"] == step_id), None)
            if not step:
                raise HTTPException(status_code=404, detail="step not found")
            normalize_voice(step)
            voice = step["voice"]
            moment = tts_request.moment
            text_key = voice_field(moment, "VoiceText")
            audio_key = voice_field(moment, "AudioUrl")
            type_key = voice_field(moment, "VoiceType")
            text = tts_request.text.strip() or voice.get(text_key, "").strip()
            voice[text_key] = text
            voice[audio_key] = save_step_tts(route_id, step, moment, text)
            voice[type_key] = "TTS"
            step["voice"] = voice
            normalize_voice(step)
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.post(
        "/api/engine/routes/{route_id}/tts/batch",
    )
    def batch_generate_route_tts(
        route_id: str,
        batch_request: BatchTtsRequest,
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
        results = []
        for step in route.get("steps", []):
            normalize_voice(step)
            voice = step["voice"]
            moments = []
            for moment in VOICE_MOMENTS:
                text_key = voice_field(moment, "VoiceText")
                audio_key = voice_field(moment, "AudioUrl")
                type_key = voice_field(moment, "VoiceType")
                voice_type = voice.get(type_key, "SYSTEM")
                if voice_type == "CUSTOM":
                    moments.append({"moment": moment, "status": "SKIPPED_CUSTOM"})
                    continue
                if voice_type == "TTS" and voice.get(audio_key) and not batch_request.regenerateTts:
                    moments.append({"moment": moment, "status": "SKIPPED_EXISTING"})
                    continue
                try:
                    voice[audio_key] = save_step_tts(
                        route_id, step, moment, voice.get(text_key, "").strip()
                    )
                    voice[type_key] = "TTS"
                    moments.append({"moment": moment, "status": "SUCCESS"})
                except HTTPException as error:
                    moments.append(
                        {"moment": moment, "status": "FAILED", "message": str(error.detail)}
                    )
            step["voice"] = voice
            normalize_voice(step)
            results.append({"stepId": step["id"], "stepNo": step["stepNo"], "moments": moments})
        with engine_routes_lock:
            routes = load_engine_routes()
            current = routes.get(route_id)
            if not current or current.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="route changed while generating")
            if not family_guard(principal, current):
                raise HTTPException(status_code=404, detail="route not found")
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return {"route": route, "steps": results}

    @router.post("/api/engine/voice/render")
    def render_system_voice(
        render_request: VoiceRenderRequest,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict[str, str]:
        return tencent_tts.render_cached_system_voice(
            upload_dir=upload_dir,
            public_base_url=public_base_url,
            moment=render_request.moment,
            text=render_request.text,
            synthesize=request_tencent_tts,
        )

    return router
