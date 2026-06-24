import json
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from fastapi import FastAPI, Header, HTTPException

from app.auth import AuthStore
from app.core.config import AppSettings
from app.repositories.json_repository import JsonAppRepository
from app.repositories.protocols import AppRepository
from app.routers.ai import create_ai_router
from app.routers.auth import create_auth_router
from app.routers.files import create_files_router
from app.routers.planning import create_planning_router
from app.routers.review import create_review_router
from app.routers.routes import create_routes_router
from app.routers.trip_results import create_trip_results_router
from app.routers.tts import create_tts_router
from app.schemas import (
    BaiduRoutePlanSummariesRequest,
    PlaceSearchRequest,
    ReverseGeocodeRequest,
    RouteAdviceRequest,
    RoutePlanRequest,
)
from app.services import baidu_map, tencent_tts
from app.services.ai_collection_assistant import generate_collection_plan
from app.services.ai_photo_reviewer import review_step_photo
from app.services.ai_route_advisor import advise_route
from app.services.ai_step_writer import generate_step_copy
from app.services.ai_trip_analyzer import analyze_trip_failures
from app.services.route_engine.route_plan_summarizer import summarize_route_plans
from app.services.route_review import refresh_route_review as refresh_route_review_with_clock
from app.services.route_review_center import build_route_review_center


class AppContainer:
    """Application composition root.

    Routers receive stable service functions from here instead of importing
    storage paths, settings or third-party HTTP details directly.
    """

    def __init__(self, settings: AppSettings, repository: AppRepository | None = None) -> None:
        self.settings = settings
        self.repository = repository or JsonAppRepository(
            route_config_file=settings.routes_file,
            engine_routes_file=settings.engine_routes_file,
            trip_results_file=settings.trip_results_file,
        )
        self.routes_lock = Lock()
        self.engine_routes_lock = Lock()
        self.trip_results_lock = Lock()
        self.auth_store = AuthStore(settings.auth_db_file, settings.upload_token)
        self.advise_route = advise_route
        self.generate_step_copy = generate_step_copy
        self.generate_collection_plan = generate_collection_plan
        self.analyze_trip_failures = analyze_trip_failures
        self.review_step_photo = review_step_photo

    def require_token(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return self.auth_store.authenticate(authorization)

    def load_routes(self) -> dict:
        return self.repository.load_route_configs()

    def save_routes(self, routes: dict) -> None:
        self.repository.save_route_configs(routes)

    def load_engine_routes(self) -> dict[str, Any]:
        return self.repository.load_engine_routes()

    def save_engine_routes(self, routes: dict[str, Any]) -> None:
        self.repository.save_engine_routes(routes)

    def load_trip_results(self) -> list[dict[str, Any]]:
        return self.repository.load_trip_results()

    def save_trip_results(self, results: list[dict[str, Any]]) -> None:
        self.repository.save_trip_results(results)

    def build_step_result_history(self, route_id: str) -> dict[str, dict[str, int]]:
        history: dict[str, dict[str, int]] = {}
        for item in self.load_trip_results():
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

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def refresh_route_review(self, route: dict[str, Any]) -> dict[str, Any]:
        return refresh_route_review_with_clock(route, self.now_iso)

    def request_json(self, url: str, service_name: str) -> dict[str, Any]:
        try:
            with urlopen(url, timeout=10, context=self.settings.ssl_context) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("message")
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = None
            raise HTTPException(
                status_code=502,
                detail=detail or f"{service_name}暂时无法访问，请稍后重试",
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=502,
                detail=f"{service_name}暂时无法访问，请稍后重试",
            ) from error
        return result

    def request_baidu_json(self, url: str) -> dict[str, Any]:
        result = self.request_json(url, "百度地图服务")
        if result.get("status") != 0:
            message = result.get("message") or "百度地图返回错误"
            if result.get("status") == 220:
                message = "当前百度 AK 不是可用的服务端 AK，请在百度地图控制台创建服务端应用并配置服务器 IP 白名单"
            raise HTTPException(status_code=502, detail=message)
        return result

    def request_wechat_code_session(self, code: str) -> dict[str, Any]:
        if not self.settings.wechat_appid or not self.settings.wechat_secret:
            raise HTTPException(status_code=503, detail="微信登录尚未配置，请联系管理员")
        url = (
            "https://api.weixin.qq.com/sns/jscode2session"
            f"?appid={self.settings.wechat_appid}"
            f"&secret={self.settings.wechat_secret}"
            f"&js_code={code}"
            "&grant_type=authorization_code"
        )
        result = self.request_json(url, "微信登录服务")
        if result.get("errcode"):
            raise HTTPException(status_code=401, detail="微信登录失败，请重新打开小程序再试")
        if not result.get("openid"):
            raise HTTPException(status_code=401, detail="微信登录未返回用户标识，请重试")
        return result

    def request_baidu_route_plan(self, route_request: RoutePlanRequest) -> dict[str, Any]:
        return baidu_map.request_baidu_route_plan(
            route_request,
            api_key=self.settings.baidu_map_key,
            request_json=self.request_baidu_json,
        )

    def request_baidu_place_search(self, search_request: PlaceSearchRequest) -> dict[str, Any]:
        return baidu_map.request_baidu_place_search(
            search_request,
            api_key=self.settings.baidu_map_key,
            request_json=self.request_baidu_json,
        )

    def request_baidu_reverse_geocode(self, reverse_request: ReverseGeocodeRequest) -> dict[str, Any]:
        return baidu_map.request_baidu_reverse_geocode(
            reverse_request,
            api_key=self.settings.baidu_map_key,
            request_json=self.request_baidu_json,
        )

    def summarize_baidu_route_plans(self, request: BaiduRoutePlanSummariesRequest) -> dict:
        plans = summarize_route_plans(
            request.planResponse,
            {"origin": request.origin, "destination": request.destination},
        )
        if not plans:
            raise HTTPException(status_code=422, detail="百度地图未返回可用路线")
        return {"plans": plans}

    def advise_engine_routes(self, advice_request: RouteAdviceRequest) -> dict:
        return self.advise_route(
            advice_request.originName,
            advice_request.destinationName,
            [plan.model_dump() for plan in advice_request.plans],
            **self.ai_config(),
        )

    def ai_config(self) -> dict[str, Any]:
        return {
            "api_key": self.settings.deepseek_api_key,
            "base_url": self.settings.deepseek_base_url,
            "model": self.settings.deepseek_model,
            "ssl_context": self.settings.ssl_context,
        }

    def request_tencent_tts(self, text: str) -> bytes:
        return tencent_tts.request_tencent_tts(
            text,
            secret_id=self.settings.tencent_secret_id,
            secret_key=self.settings.tencent_secret_key,
            region=self.settings.tencent_tts_region,
            voice_type=self.settings.tencent_tts_voice_type,
            ssl_context=self.settings.ssl_context,
        )

    def save_step_tts(self, route_id: str, step: dict[str, Any], moment: str, text: str) -> str:
        return tencent_tts.save_step_tts(
            upload_dir=self.settings.upload_dir,
            public_base_url=self.settings.public_base_url,
            route_id=route_id,
            step=step,
            moment=moment,
            text=text,
            synthesize=self.request_tencent_tts,
        )

    def include_routers(self, app: FastAPI) -> None:
        app.include_router(
            create_auth_router(
                auth_status=self.auth_store.status,
                auth_wechat_login=lambda code, family_name: self.auth_store.wechat_login(
                    self.request_wechat_code_session(code)["openid"],
                    family_name,
                ),
                auth_wechat_bind_elder=lambda code, bind_code: self.auth_store.wechat_bind_elder(
                    self.request_wechat_code_session(code)["openid"], bind_code
                ),
                auth_logout=self.auth_store.logout,
                auth_me=self.auth_store.me,
                require_token=self.require_token,
                list_elders=self.auth_store.list_elders,
                create_elder=self.auth_store.create_elder,
                update_elder=self.auth_store.update_elder,
                create_elder_bind_code=self.auth_store.create_elder_bind_code,
                bind_elder=self.auth_store.bind_elder,
                get_emergency_contact=self.auth_store.get_emergency_contact,
                save_emergency_contact=self.auth_store.save_emergency_contact,
            )
        )
        app.include_router(
            create_files_router(
                require_token=self.require_token,
                upload_dir=self.settings.upload_dir,
                public_base_url=self.settings.public_base_url,
                routes_lock=self.routes_lock,
                load_routes=self.load_routes,
                save_routes=self.save_routes,
            )
        )
        app.include_router(
            create_routes_router(
                require_token=self.require_token,
                engine_routes_lock=self.engine_routes_lock,
                load_engine_routes=self.load_engine_routes,
                save_engine_routes=self.save_engine_routes,
                now_iso=self.now_iso,
                refresh_route_review=self.refresh_route_review,
            )
        )
        app.include_router(
            create_trip_results_router(
                require_token=self.require_token,
                trip_results_lock=self.trip_results_lock,
                load_engine_routes=self.load_engine_routes,
                load_trip_results=self.load_trip_results,
                save_trip_results=self.save_trip_results,
                build_route_review_center=build_route_review_center,
                now_iso=self.now_iso,
            )
        )
        app.include_router(
            create_planning_router(
                require_token=self.require_token,
                request_baidu_route_plan=self.request_baidu_route_plan,
                request_baidu_place_search=self.request_baidu_place_search,
                request_baidu_reverse_geocode=self.request_baidu_reverse_geocode,
                advise_engine_routes=self.advise_engine_routes,
                summarize_baidu_route_plans=self.summarize_baidu_route_plans,
            )
        )
        app.include_router(
            create_ai_router(
                require_token=self.require_token,
                engine_routes_lock=self.engine_routes_lock,
                load_engine_routes=self.load_engine_routes,
                save_engine_routes=self.save_engine_routes,
                refresh_route_review=self.refresh_route_review,
                build_step_result_history=self.build_step_result_history,
                generate_step_copy=lambda route, **kwargs: self.generate_step_copy(route, **kwargs),
                generate_collection_plan=lambda route, history, **kwargs: self.generate_collection_plan(
                    route, history, **kwargs
                ),
                ai_config=self.ai_config,
            )
        )
        app.include_router(
            create_review_router(
                require_token=self.require_token,
                engine_routes_lock=self.engine_routes_lock,
                load_engine_routes=self.load_engine_routes,
                save_engine_routes=self.save_engine_routes,
                load_trip_results=self.load_trip_results,
                refresh_route_review=self.refresh_route_review,
                build_route_review_center=build_route_review_center,
                analyze_trip_failures=lambda route, review_center, **kwargs: self.analyze_trip_failures(
                    route, review_center, **kwargs
                ),
                review_step_photo=lambda *args, **kwargs: self.review_step_photo(*args, **kwargs),
                ai_config=self.ai_config,
            )
        )
        app.include_router(
            create_tts_router(
                require_token=self.require_token,
                engine_routes_lock=self.engine_routes_lock,
                load_engine_routes=self.load_engine_routes,
                save_engine_routes=self.save_engine_routes,
                refresh_route_review=self.refresh_route_review,
                save_step_tts=self.save_step_tts,
                request_tencent_tts=lambda text: self.request_tencent_tts(text),
                upload_dir=self.settings.upload_dir,
                public_base_url=self.settings.public_base_url,
            )
        )
