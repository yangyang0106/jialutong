from typing import Any

VOICE_MOMENTS = ("enter", "repeat", "near", "arrived", "offRoute")


def voice_field(moment: str, suffix: str) -> str:
    return f"{moment}{suffix}"


def default_voice_texts(step: dict[str, Any]) -> dict[str, str]:
    action = step.get("shortAction") or step.get("title") or "继续前进"
    return {
        "enter": f"请{action}。",
        "repeat": f"请继续{action}。",
        "near": "快到了，请看照片确认。",
        "arrived": "您已接近目标地点，请看照片确认。",
        "offRoute": "好像走远了，请先停一下，不要继续走。需要帮助请联系家人。",
    }


def normalize_voice(step: dict[str, Any]) -> dict[str, Any]:
    voice = dict(step.get("voice") or {})
    defaults = default_voice_texts(step)
    legacy_texts = {
        "enter": voice.get("enterVoice"),
        "repeat": voice.get("repeatVoice"),
        "near": voice.get("nearVoice"),
    }
    for moment in VOICE_MOMENTS:
        text_key = voice_field(moment, "VoiceText")
        audio_key = voice_field(moment, "AudioUrl")
        type_key = voice_field(moment, "VoiceType")
        uses_legacy_enter_audio = (
            moment == "enter" and not voice.get(audio_key) and bool(voice.get("audioUrl"))
        )
        voice[text_key] = voice.get(text_key) or legacy_texts.get(moment) or defaults[moment]
        voice[audio_key] = voice.get(audio_key) or (
            voice.get("audioUrl", "") if moment == "enter" else ""
        )
        if uses_legacy_enter_audio:
            voice[type_key] = voice.get("voiceType", "SYSTEM")
        else:
            voice[type_key] = voice.get(type_key) or (
                voice.get("voiceType", "SYSTEM") if voice[audio_key] else "SYSTEM"
            )
    voice["enterVoice"] = voice["enterVoiceText"]
    voice["repeatVoice"] = voice["repeatVoiceText"]
    voice["nearVoice"] = voice["nearVoiceText"]
    voice["audioUrl"] = voice["enterAudioUrl"]
    voice["voiceType"] = voice["enterVoiceType"]
    step["voice"] = voice
    return voice


def normalize_route_voices(route: dict[str, Any]) -> dict[str, Any]:
    for step in route.get("steps", []):
        normalize_voice(step)
    return route
