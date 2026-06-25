import os
import ssl
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import certifi
from dotenv import load_dotenv


@dataclass(frozen=True)
class AppSettings:
    base_dir: Path
    data_dir: Path
    upload_dir: Path
    engine_routes_file: Path
    trip_results_file: Path
    auth_db_file: Path
    public_base_url: str
    super_admin_openids: str
    baidu_map_key: str
    tencent_secret_id: str
    tencent_secret_key: str
    tencent_tts_region: str
    tencent_tts_voice_type: int
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    wechat_appid: str
    wechat_secret: str

    @cached_property
    def ssl_context(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=certifi.where())


def load_settings() -> AppSettings:
    base_dir = Path(__file__).resolve().parents[2]
    load_dotenv(base_dir / ".env")
    data_dir = Path(os.getenv("JIALUTONG_DATA_DIR", base_dir / "data"))
    return AppSettings(
        base_dir=base_dir,
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        engine_routes_file=data_dir / "engine-routes.json",
        trip_results_file=data_dir / "trip-results.json",
        auth_db_file=data_dir / "auth.db",
        public_base_url=os.getenv("JIALUTONG_PUBLIC_BASE_URL", "http://127.0.0.1:8090").rstrip("/"),
        super_admin_openids=os.getenv("JIALUTONG_SUPER_ADMIN_OPENIDS", ""),
        baidu_map_key=os.getenv("JIALUTONG_BAIDU_MAP_KEY", ""),
        tencent_secret_id=os.getenv("JIALUTONG_TENCENT_SECRET_ID", ""),
        tencent_secret_key=os.getenv("JIALUTONG_TENCENT_SECRET_KEY", ""),
        tencent_tts_region=os.getenv("JIALUTONG_TENCENT_TTS_REGION", "ap-shanghai"),
        tencent_tts_voice_type=int(os.getenv("JIALUTONG_TENCENT_TTS_VOICE_TYPE", "101001")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        wechat_appid=os.getenv("JIALUTONG_WECHAT_APPID", ""),
        wechat_secret=os.getenv("JIALUTONG_WECHAT_SECRET", ""),
    )
