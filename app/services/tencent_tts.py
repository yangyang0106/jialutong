import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from ssl import SSLContext
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


def sign_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def request_tencent_tts(
    text: str,
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    voice_type: int,
    ssl_context: SSLContext,
) -> bytes:
    if not secret_id or not secret_key:
        raise HTTPException(status_code=503, detail="请先配置腾讯云 TTS 密钥")
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="语音文字不能为空")

    host = "tts.tencentcloudapi.com"
    service = "tts"
    action = "TextToVoice"
    version = "2019-08-23"
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    payload = json.dumps(
        {
            "Text": clean_text,
            "SessionId": uuid.uuid4().hex,
            "ModelType": 1,
            "VoiceType": voice_type,
            "Codec": "mp3",
            "SampleRate": 16000,
            "Speed": 0,
            "Volume": 0,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            f"content-type:application/json; charset=utf-8\nhost:{host}\n",
            "content-type;host",
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        ]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    secret_date = sign_sha256(f"TC3{secret_key}".encode("utf-8"), date)
    secret_service = sign_sha256(secret_date, service)
    secret_signing = sign_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        "TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        "SignedHeaders=content-type;host, "
        f"Signature={signature}"
    )
    request = Request(
        f"https://{host}",
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": version,
            "X-TC-Region": region,
            "X-TC-Timestamp": str(timestamp),
        },
    )
    try:
        with urlopen(request, timeout=20, context=ssl_context) as response:
            result = json.loads(response.read().decode("utf-8")).get("Response") or {}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="腾讯云语音合成暂时不可用") from error
    if result.get("Error"):
        message = result["Error"].get("Message") or "腾讯云语音合成失败"
        if "resource pack allowance has been exhausted" in message.lower():
            message = "腾讯云语音合成额度已用完，请充值或购买资源包"
        raise HTTPException(status_code=502, detail=message)
    try:
        return base64.b64decode(result["Audio"])
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=502, detail="腾讯云未返回有效语音") from error


def save_step_tts(
    *,
    upload_dir: Path,
    public_base_url: str,
    route_id: str,
    step: dict,
    moment: str,
    text: str,
    synthesize: Callable[[str], bytes],
) -> str:
    audio = synthesize(text)
    route_dir = upload_dir / route_id / str(step["stepNo"])
    route_dir.mkdir(parents=True, exist_ok=True)
    destination = route_dir / f"tts-{moment}-{uuid.uuid4().hex}.mp3"
    destination.write_bytes(audio)
    relative_path = destination.relative_to(upload_dir).as_posix()
    return f"{public_base_url}/files/{relative_path}"


def render_cached_system_voice(
    *,
    upload_dir: Path,
    public_base_url: str,
    moment: str,
    text: str,
    synthesize: Callable[[str], bytes],
) -> dict[str, str]:
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="voice text is required")
    cache_key = hashlib.sha256(f"{moment}:{clean_text}".encode("utf-8")).hexdigest()
    route_dir = upload_dir / "system-voice"
    route_dir.mkdir(parents=True, exist_ok=True)
    destination = route_dir / f"{cache_key}.mp3"
    if not destination.exists():
        destination.write_bytes(synthesize(clean_text))
    relative_path = destination.relative_to(upload_dir).as_posix()
    return {"audioUrl": f"{public_base_url}/files/{relative_path}", "voiceType": "SYSTEM"}
