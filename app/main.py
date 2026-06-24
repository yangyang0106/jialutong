import json
import os
import ssl
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import certifi
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from app.auth import AuthStore
from app.routers.ai import create_ai_router
from app.routers.auth import create_auth_router
from app.routers.files import create_files_router
from app.routers.planning import create_planning_router
from app.routers.review import create_review_router
from app.routers.routes import create_routes_router
from app.routers.trip_results import create_trip_results_router
from app.routers.tts import create_tts_router
from app.schemas import PlaceSearchRequest, ReverseGeocodeRequest, RouteAdviceRequest, RoutePlanRequest
from app.services.ai_collection_assistant import generate_collection_plan
from app.services.ai_photo_reviewer import review_step_photo
from app.services.ai_route_advisor import advise_route
from app.services.ai_step_writer import generate_step_copy
from app.services.ai_trip_analyzer import analyze_trip_failures
from app.services import baidu_map
from app.services.route_review import refresh_route_review as refresh_route_review_with_clock
from app.services.route_review_center import build_route_review_center
from app.services import tencent_tts
from app.storage import load_json, load_routes as load_routes_file, save_json, save_routes as save_routes_file

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("JIALUTONG_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
ROUTES_FILE = DATA_DIR / "routes.json"
ENGINE_ROUTES_FILE = DATA_DIR / "engine-routes.json"
TRIP_RESULTS_FILE = DATA_DIR / "trip-results.json"
AUTH_DB_FILE = DATA_DIR / "auth.db"
PUBLIC_BASE_URL = os.getenv("JIALUTONG_PUBLIC_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
API_TOKEN = os.getenv("JIALUTONG_UPLOAD_TOKEN", "")
BAIDU_MAP_KEY = os.getenv("JIALUTONG_BAIDU_MAP_KEY", "")
TENCENT_SECRET_ID = os.getenv("JIALUTONG_TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("JIALUTONG_TENCENT_SECRET_KEY", "")
TENCENT_TTS_REGION = os.getenv("JIALUTONG_TENCENT_TTS_REGION", "ap-shanghai")
TENCENT_TTS_VOICE_TYPE = int(os.getenv("JIALUTONG_TENCENT_TTS_VOICE_TYPE", "101001"))
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
WECHAT_APPID = os.getenv("JIALUTONG_WECHAT_APPID", "")
WECHAT_SECRET = os.getenv("JIALUTONG_WECHAT_SECRET", "")
HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())

routes_lock = Lock()
engine_routes_lock = Lock()
trip_results_lock = Lock()
auth_store = AuthStore(AUTH_DB_FILE, API_TOKEN)


def require_token(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return auth_store.authenticate(authorization)


def load_routes() -> dict:
    return load_routes_file(ROUTES_FILE)


def save_routes(routes: dict) -> None:
    save_routes_file(ROUTES_FILE, routes)


def load_engine_routes() -> dict[str, Any]:
    return load_json(ENGINE_ROUTES_FILE, {})


def save_engine_routes(routes: dict[str, Any]) -> None:
    save_json(ENGINE_ROUTES_FILE, routes)


def load_trip_results() -> list[dict[str, Any]]:
    return load_json(TRIP_RESULTS_FILE, [])


def save_trip_results(results: list[dict[str, Any]]) -> None:
    save_json(TRIP_RESULTS_FILE, results)


def build_step_result_history(route_id: str) -> dict[str, dict[str, int]]:
    history: dict[str, dict[str, int]] = {}
    for item in load_trip_results():
        if item.get("routeId") != route_id:
            continue
        result = item.get("stepResult")
        if result not in {"FOUND", "NOT_FOUND", "HELP"}:
            continue
        for key in (item.get("stepId"), item.get("stepNo")):
            if key is None:
                continue
            entry = history.setdefault(str(key), {"FOUND": 0, "NOT_FOUND": 0, "HELP": 0})
            entry[result] += 1
    return history


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def request_tencent_tts(text: str) -> bytes:
    return tencent_tts.request_tencent_tts(
        text,
        secret_id=TENCENT_SECRET_ID,
        secret_key=TENCENT_SECRET_KEY,
        region=TENCENT_TTS_REGION,
        voice_type=TENCENT_TTS_VOICE_TYPE,
        ssl_context=HTTPS_CONTEXT,
    )


def save_step_tts(route_id: str, step: dict[str, Any], moment: str, text: str) -> str:
    return tencent_tts.save_step_tts(
        upload_dir=UPLOAD_DIR,
        public_base_url=PUBLIC_BASE_URL,
        route_id=route_id,
        step=step,
        moment=moment,
        text=text,
        synthesize=request_tencent_tts,
    )


def refresh_route_review(route: dict[str, Any]) -> dict[str, Any]:
    return refresh_route_review_with_clock(route, now_iso)


def request_baidu_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10, context=HTTPS_CONTEXT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("message")
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = None
        raise HTTPException(
            status_code=502,
            detail=detail or "百度地图服务暂时无法访问，请稍后重试",
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=502,
            detail="百度地图服务暂时无法访问，请稍后重试",
        ) from error
    if result.get("status") != 0:
        message = result.get("message") or "百度地图返回错误"
        if result.get("status") == 220:
            message = "当前百度 AK 不是可用的服务端 AK，请在百度地图控制台创建服务端应用并配置服务器 IP 白名单"
        raise HTTPException(
            status_code=502,
            detail=message,
        )
    return result


def request_wechat_code_session(code: str) -> dict[str, Any]:
    if not WECHAT_APPID or not WECHAT_SECRET:
        raise HTTPException(status_code=503, detail="微信登录尚未配置，请联系管理员")
    url = (
        "https://api.weixin.qq.com/sns/jscode2session"
        f"?appid={WECHAT_APPID}"
        f"&secret={WECHAT_SECRET}"
        f"&js_code={code}"
        "&grant_type=authorization_code"
    )
    try:
        with urlopen(url, timeout=10, context=HTTPS_CONTEXT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="微信登录服务暂时不可用，请稍后重试") from error
    if result.get("errcode"):
        raise HTTPException(status_code=401, detail="微信登录失败，请重新打开小程序再试")
    if not result.get("openid"):
        raise HTTPException(status_code=401, detail="微信登录未返回用户标识，请重试")
    return result


def request_baidu_route_plan(route_request: RoutePlanRequest) -> dict[str, Any]:
    return baidu_map.request_baidu_route_plan(
        route_request,
        api_key=BAIDU_MAP_KEY,
        request_json=request_baidu_json,
    )


def request_baidu_place_search(search_request: PlaceSearchRequest) -> dict[str, Any]:
    return baidu_map.request_baidu_place_search(
        search_request,
        api_key=BAIDU_MAP_KEY,
        request_json=request_baidu_json,
    )


def request_baidu_reverse_geocode(reverse_request: ReverseGeocodeRequest) -> dict[str, Any]:
    return baidu_map.request_baidu_reverse_geocode(
        reverse_request,
        api_key=BAIDU_MAP_KEY,
        request_json=request_baidu_json,
    )


def advise_engine_routes(advice_request: RouteAdviceRequest) -> dict:
    return advise_route(
        advice_request.originName,
        advice_request.destinationName,
        [plan.model_dump() for plan in advice_request.plans],
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_MODEL,
        ssl_context=HTTPS_CONTEXT,
    )


def ai_config() -> dict[str, Any]:
    return {
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
        "ssl_context": HTTPS_CONTEXT,
    }


def create_app() -> FastAPI:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="家路通文件与路线配置服务", version="0.1.0")
    app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")
    app.include_router(
        create_auth_router(
            auth_status=auth_store.status,
            auth_wechat_login=lambda code, family_name: auth_store.wechat_login(
                request_wechat_code_session(code)["openid"],
                family_name,
            ),
            auth_wechat_bind_elder=lambda code, bind_code: auth_store.wechat_bind_elder(
                request_wechat_code_session(code)["openid"], bind_code
            ),
            auth_logout=auth_store.logout,
            auth_me=auth_store.me,
            require_token=require_token,
            list_elders=auth_store.list_elders,
            create_elder=auth_store.create_elder,
            update_elder=auth_store.update_elder,
            create_elder_bind_code=auth_store.create_elder_bind_code,
            bind_elder=auth_store.bind_elder,
            get_emergency_contact=auth_store.get_emergency_contact,
            save_emergency_contact=auth_store.save_emergency_contact,
        )
    )
    app.include_router(
        create_files_router(
            require_token=require_token,
            upload_dir=UPLOAD_DIR,
            public_base_url=PUBLIC_BASE_URL,
            routes_lock=routes_lock,
            load_routes=load_routes,
            save_routes=save_routes,
        )
    )
    app.include_router(
        create_routes_router(
            require_token=require_token,
            engine_routes_lock=engine_routes_lock,
            load_engine_routes=load_engine_routes,
            save_engine_routes=save_engine_routes,
            now_iso=now_iso,
            refresh_route_review=refresh_route_review,
        )
    )
    app.include_router(
        create_trip_results_router(
            require_token=require_token,
            trip_results_lock=trip_results_lock,
            load_engine_routes=load_engine_routes,
            load_trip_results=load_trip_results,
            save_trip_results=save_trip_results,
            build_route_review_center=build_route_review_center,
            now_iso=now_iso,
        )
    )
    app.include_router(
        create_planning_router(
            require_token=require_token,
            request_baidu_route_plan=lambda route_request: request_baidu_route_plan(route_request),
            request_baidu_place_search=lambda search_request: request_baidu_place_search(search_request),
            request_baidu_reverse_geocode=lambda reverse_request: request_baidu_reverse_geocode(reverse_request),
            advise_engine_routes=lambda advice_request: advise_engine_routes(advice_request),
        )
    )
    app.include_router(
        create_ai_router(
            require_token=require_token,
            engine_routes_lock=engine_routes_lock,
            load_engine_routes=load_engine_routes,
            save_engine_routes=save_engine_routes,
            refresh_route_review=refresh_route_review,
            build_step_result_history=build_step_result_history,
            generate_step_copy=lambda route, **kwargs: generate_step_copy(route, **kwargs),
            generate_collection_plan=lambda route, history, **kwargs: generate_collection_plan(
                route, history, **kwargs
            ),
            ai_config=ai_config,
        )
    )
    app.include_router(
        create_review_router(
            require_token=require_token,
            engine_routes_lock=engine_routes_lock,
            load_engine_routes=load_engine_routes,
            save_engine_routes=save_engine_routes,
            load_trip_results=load_trip_results,
            refresh_route_review=refresh_route_review,
            build_route_review_center=build_route_review_center,
            analyze_trip_failures=lambda route, review_center, **kwargs: analyze_trip_failures(
                route, review_center, **kwargs
            ),
            review_step_photo=review_step_photo,
            ai_config=ai_config,
        )
    )
    app.include_router(
        create_tts_router(
            require_token=require_token,
            engine_routes_lock=engine_routes_lock,
            load_engine_routes=load_engine_routes,
            save_engine_routes=save_engine_routes,
            refresh_route_review=refresh_route_review,
            save_step_tts=save_step_tts,
            request_tencent_tts=lambda text: request_tencent_tts(text),
            upload_dir=UPLOAD_DIR,
            public_base_url=PUBLIC_BASE_URL,
        )
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
