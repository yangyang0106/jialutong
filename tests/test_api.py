import importlib
import sqlite3
from urllib.error import URLError

from fastapi.testclient import TestClient


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("JIALUTONG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JIALUTONG_PUBLIC_BASE_URL", "https://files.example.com")
    monkeypatch.setenv("JIALUTONG_UPLOAD_TOKEN", "test-token")
    import app.main

    module = importlib.reload(app.main)
    return TestClient(module.create_app())


def test_upload_and_route_config(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    upload = client.post(
        "/api/files",
        headers=headers,
        data={"routeId": "to-mom", "stepNo": "1", "kind": "image"},
        files={"file": ("step.jpg", b"fake-image", "image/jpeg")},
    )
    assert upload.status_code == 200
    image_url = upload.json()["url"]

    update = client.put(
        "/api/routes/to-mom/steps/1",
        headers=headers,
        json={"image": image_url, "desc": "看到大门后右转", "direction": "右转"},
    )
    assert update.status_code == 200

    route = client.get("/api/routes/to-mom")
    assert route.json()["steps"]["1"]["image"] == image_url


def test_upload_requires_token(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/files",
        data={"routeId": "to-mom", "stepNo": "1", "kind": "audio"},
        files={"file": ("step.mp3", b"audio", "audio/mpeg")},
    )
    assert response.status_code == 401


def build_engine_route():
    return {
        "id": "route-engine-test",
        "name": "去妈妈家",
        "elderSlot": "TO_MOM",
        "origin": {"name": "我家", "latitude": 31.25, "longitude": 121.32},
        "destination": {"name": "妈妈家", "latitude": 31.3, "longitude": 121.45},
        "travelModes": ["WALKING", "BUS"],
        "steps": [
            {
                "id": "step-start",
                "routeId": "route-engine-test",
                "stepNo": 1,
                "type": "START",
                "title": "从家出发",
                "shortAction": "准备出发",
                "location": {"latitude": 31.25, "longitude": 121.32},
                "requiresFamilyReview": True,
                "reviewStatus": "PENDING",
            },
            {
                "id": "step-bus",
                "routeId": "route-engine-test",
                "stepNo": 2,
                "type": "BUS_ON",
                "title": "乘坐887路",
                "shortAction": "等887路",
                "location": {"latitude": 31.26, "longitude": 121.33},
                "transit": {"lineName": "887路", "stationName": "临洮路站"},
                "requiresFamilyReview": True,
                "reviewStatus": "PENDING",
            },
            {
                "id": "step-destination",
                "routeId": "route-engine-test",
                "stepNo": 3,
                "type": "DESTINATION",
                "title": "到达妈妈家",
                "shortAction": "已经到达",
                "location": {"latitude": 31.3, "longitude": 121.45},
                "requiresFamilyReview": True,
                "reviewStatus": "PENDING",
            },
        ],
    }


def build_engine_route_with_id(route_id: str, name: str = "去妈妈家"):
    route = build_engine_route()
    route["id"] = route_id
    route["name"] = name
    for index, step in enumerate(route["steps"], start=1):
        suffix = step["id"].removeprefix("step-")
        step["id"] = f"{route_id}-{suffix}"
        step["routeId"] = route_id
        step["stepNo"] = index
    return route


def baidu_location(latitude: float, longitude: float) -> dict:
    return {"lat": latitude, "lng": longitude}


def baidu_walking_step(
    instruction: str,
    turn_type: str,
    road_name: str,
    start: dict,
    end: dict,
    distance: int = 100,
) -> dict:
    return {
        "instruction": instruction,
        "turn_type": turn_type,
        "road_name": road_name,
        "distance": distance,
        "start_location": start,
        "end_location": end,
        "path": f"{start['lng']},{start['lat']};{end['lng']},{end['lat']}",
    }


def build_baidu_walking_response() -> dict:
    return {
        "status": 0,
        "result": {
            "routes": [
                {
                    "distance": 500,
                    "duration": 480,
                    "steps": [
                        baidu_walking_step(
                            "沿丰庄路直行",
                            "直行",
                            "丰庄路",
                            baidu_location(31.25, 121.32),
                            baidu_location(31.251, 121.321),
                        ),
                        baidu_walking_step(
                            "前方右转进入临洮路",
                            "右转",
                            "临洮路",
                            baidu_location(31.251, 121.321),
                            baidu_location(31.252, 121.322),
                        ),
                        baidu_walking_step(
                            "继续直行到终点",
                            "直行",
                            "临洮路",
                            baidu_location(31.252, 121.322),
                            baidu_location(31.32, 121.47),
                            300,
                        ),
                    ],
                }
            ]
        },
    }


def build_baidu_transit_response(vehicle: str = "BUS", line_name: str = "887路") -> dict:
    return {
        "status": 0,
        "result": {
            "routes": [
                {
                    "distance": 4000,
                    "duration": 2100,
                    "steps": [
                        [
                            baidu_walking_step(
                                "步行到临洮路站",
                                "直行",
                                "",
                                baidu_location(31.25, 121.32),
                                baidu_location(31.251, 121.321),
                            ),
                            {
                                "instructions": f"乘坐{line_name}",
                                "distance": 3800,
                                "start_location": baidu_location(31.251, 121.321),
                                "end_location": baidu_location(31.3, 121.45),
                                "vehicle_info": {
                                    "type": vehicle,
                                    "detail": {
                                        "uid": "line-1",
                                        "name": line_name,
                                        "direction": "高境路恒高路方向",
                                        "stop_num": 6,
                                        "departure_station": {
                                            "name": "临洮路站",
                                            "location": baidu_location(31.251, 121.321),
                                        },
                                        "arrive_station": {
                                            "name": "江湾镇站",
                                            "location": baidu_location(31.3, 121.45),
                                        },
                                    },
                                },
                            },
                            baidu_walking_step(
                                "步行到终点",
                                "直行",
                                "",
                                baidu_location(31.3, 121.45),
                                baidu_location(31.32, 121.47),
                            ),
                        ]
                    ],
                }
            ]
        },
    }


def create_route_from_baidu(client, headers, route_id: str, plan_response: dict, route_index: int = 0):
    return client.post(
        "/api/engine/routes/from-baidu",
        headers=headers,
        json={
            "id": route_id,
            "name": "测试路线",
            "elderSlot": "TO_MOM",
            "origin": {"name": "富友嘉园一期", "latitude": 31.25, "longitude": 121.32},
            "destination": {"name": "彩虹湾墨翠里", "latitude": 31.32, "longitude": 121.47},
            "planResponse": plan_response,
            "routeIndex": route_index,
        },
    )


def approve_and_publish_route(client, headers, route):
    created = client.post("/api/engine/routes", headers=headers, json=route)
    assert created.status_code == 200
    for step in created.json()["steps"]:
        reviewed = client.put(
            f"/api/engine/routes/{created.json()['id']}/steps/{step['id']}/review",
            headers=headers,
            json={"reviewStatus": "APPROVED"},
        )
        assert reviewed.status_code == 200
    published = client.post(f"/api/engine/routes/{created.json()['id']}/publish", headers=headers)
    assert published.status_code == 200
    return published.json()


def test_engine_route_review_and_publish(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}

    created = client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    assert created.status_code == 200
    assert created.json()["status"] == "NEEDS_REVIEW"

    blocked = client.post("/api/engine/routes/route-engine-test/publish", headers=headers)
    assert blocked.status_code == 409

    for step_id in ["step-start", "step-bus", "step-destination"]:
        reviewed = client.put(
            f"/api/engine/routes/route-engine-test/steps/{step_id}/review",
            headers=headers,
            json={"reviewStatus": "APPROVED", "reviewNote": "家属已确认"},
        )
        assert reviewed.status_code == 200

    published = client.post("/api/engine/routes/route-engine-test/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["lifecycleStatus"] == "PUBLISHED"
    assert published.json()["reviewLevel"] == "GUARDIAN_REVIEWED"
    assert published.json()["reviewedByRole"] in {"ADMIN", "FAMILY_ADMIN", "SUPER_ADMIN"}

    elderly_route = client.get("/api/engine/elder-routes/TO_MOM", headers=headers)
    assert elderly_route.status_code == 200
    assert elderly_route.json()["id"] == "route-engine-test"

    immutable = client.put(
        "/api/engine/routes/route-engine-test",
        headers=headers,
        json=published.json(),
    )
    assert immutable.status_code == 409


def test_create_route_from_baidu_generates_backend_decision_points(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    response = create_route_from_baidu(
        client,
        headers,
        "backend-walking-test",
        build_baidu_walking_response(),
    )
    assert response.status_code == 200
    route = response.json()
    assert route["sourceProvider"] == "BAIDU_MAP"
    assert route["travelModes"] == ["WALKING"]
    assert [step["type"] for step in route["steps"]] == [
        "START",
        "RIGHT",
        "STRAIGHT",
        "DESTINATION",
    ]
    right_turn = route["steps"][1]
    assert right_turn["shortAction"] == "前面右转"
    assert "右转" not in right_turn["voice"]["enterVoice"]
    assert "右转" in right_turn["voice"]["nearVoice"]
    assert route["steps"][-1]["location"] == {"latitude": 31.32, "longitude": 121.47}


def test_create_route_from_baidu_handles_bus_and_subway_anchors(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    bus_response = create_route_from_baidu(
        client,
        headers,
        "backend-bus-test",
        build_baidu_transit_response(),
    )
    assert bus_response.status_code == 200
    bus_route = bus_response.json()
    assert [step["type"] for step in bus_route["steps"]] == [
        "START",
        "STRAIGHT",
        "BUS_ON",
        "BUS_OFF",
        "STRAIGHT",
        "DESTINATION",
    ]
    assert bus_route["steps"][2]["transit"]["lineName"] == "887路"
    assert bus_route["steps"][2]["transit"]["direction"] == "高境路恒高路方向"

    subway_plan = build_baidu_transit_response("SUBWAY", "14号线")
    subway_plan["result"]["routes"][0]["steps"][0][0]["instruction"] = "步行到临洮路站，从1号口进站"
    subway_plan["result"]["routes"][0]["steps"][0][2]["instruction"] = "从3号口出站后步行到终点"
    subway_response = create_route_from_baidu(
        client,
        headers,
        "backend-subway-test",
        subway_plan,
    )
    assert subway_response.status_code == 200
    subway_route = subway_response.json()
    assert [step["type"] for step in subway_route["steps"]] == [
        "START",
        "STRAIGHT",
        "SUBWAY_IN",
        "SUBWAY_OUT",
        "STRAIGHT",
        "DESTINATION",
    ]
    assert subway_route["steps"][2]["transit"]["accessName"] == "1号口"
    assert subway_route["steps"][3]["transit"]["accessName"] == "3号口"
    assert subway_route["steps"][2]["requiresFamilyReview"] is True


def test_unpublished_route_can_be_deleted_but_published_route_cannot(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())

    deleted = client.delete("/api/engine/routes/route-engine-test", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/api/engine/routes/route-engine-test", headers=headers).status_code == 404

    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    for step_id in ["step-start", "step-bus", "step-destination"]:
        client.put(
            f"/api/engine/routes/route-engine-test/steps/{step_id}/review",
            headers=headers,
            json={"reviewStatus": "APPROVED"},
        )
    client.post("/api/engine/routes/route-engine-test/publish", headers=headers)

    blocked = client.delete("/api/engine/routes/route-engine-test", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "published route cannot be deleted"


def test_high_risk_step_requires_family_photo(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["steps"][1]["riskLevel"] = "HIGH"

    client.post("/api/engine/routes", headers=headers, json=route)
    for step_id in ["step-start", "step-bus", "step-destination"]:
        client.put(
            f"/api/engine/routes/route-engine-test/steps/{step_id}/review",
            headers=headers,
            json={"reviewStatus": "APPROVED"},
        )

    blocked = client.post("/api/engine/routes/route-engine-test/publish", headers=headers)
    assert blocked.status_code == 409
    assert "高风险步骤需要家属实拍照片" in str(blocked.json())

    reviewed = client.put(
        "/api/engine/routes/route-engine-test/steps/step-bus/review",
        headers=headers,
        json={
            "reviewStatus": "APPROVED",
            "imageStatus": "FAMILY",
            "imageUrl": "https://files.example.com/bus-stop.jpg",
        },
    )
    assert reviewed.json()["status"] == "READY"


def test_high_risk_walking_decision_requires_landmark_hint(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    step = route["steps"][1]
    step["type"] = "RIGHT"
    step["riskLevel"] = "HIGH"
    step["transit"] = None

    client.post("/api/engine/routes", headers=headers, json=route)
    for step_id in ["step-start", "step-bus", "step-destination"]:
        client.put(
            f"/api/engine/routes/route-engine-test/steps/{step_id}/review",
            headers=headers,
            json={
                "reviewStatus": "APPROVED",
                "imageStatus": "FAMILY" if step_id == "step-bus" else "NONE",
            },
        )

    blocked = client.post("/api/engine/routes/route-engine-test/publish", headers=headers)
    assert blocked.status_code == 409
    assert "高风险路口需要填写地标提示" in str(blocked.json())

    reviewed = client.put(
        "/api/engine/routes/route-engine-test/steps/step-bus/review",
        headers=headers,
        json={"landmarkHint": "红色便利店"},
    )
    assert reviewed.json()["status"] == "READY"


def test_step_review_saves_and_removes_custom_voice(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())

    saved = client.put(
        "/api/engine/routes/route-engine-test/steps/step-start/review",
        headers=headers,
        json={
            "voice": {
                "voiceType": "CUSTOM",
                "audioUrl": "https://files.example.com/start.mp3",
                "enterVoice": "请从这里出发。",
                "nearVoice": "快到了。",
                "repeatVoice": "请继续走。",
            }
        },
    )
    assert saved.status_code == 200
    assert saved.json()["steps"][0]["voice"]["voiceType"] == "CUSTOM"
    assert saved.json()["steps"][0]["voice"]["audioUrl"].endswith("start.mp3")
    assert saved.json()["steps"][0]["reviewStatus"] == "PENDING"

    removed = client.put(
        "/api/engine/routes/route-engine-test/steps/step-start/review",
        headers=headers,
        json={
            "voice": {
                "voiceType": "SYSTEM",
                "audioUrl": "",
                "enterVoice": "请从这里出发。",
                "nearVoice": "快到了。",
                "repeatVoice": "请继续走。",
            }
        },
    )
    assert removed.status_code == 200
    assert removed.json()["steps"][0]["voice"]["voiceType"] == "SYSTEM"
    assert removed.json()["steps"][0]["voice"]["audioUrl"] == ""

    landmark = client.put(
        "/api/engine/routes/route-engine-test/steps/step-start/review",
        headers=headers,
        json={"landmarkHint": "红色便利店"},
    )
    assert landmark.json()["steps"][0]["landmarkHint"] == "红色便利店"


def test_generate_step_tts_saves_audio_and_updates_voice(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    import app.main

    monkeypatch.setattr(app.main, "request_tencent_tts", lambda _text: b"fake-mp3")
    generated = client.post(
        "/api/engine/routes/route-engine-test/steps/step-start/tts",
        headers=headers,
        json={"moment": "near", "text": "快到起点了。"},
    )
    assert generated.status_code == 200
    voice = generated.json()["steps"][0]["voice"]
    assert voice["nearVoiceType"] == "TTS"
    assert voice["nearVoiceText"] == "快到起点了。"
    assert voice["nearAudioUrl"].endswith(".mp3")


def test_ai_step_writer_updates_copy_without_changing_route_structure(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["steps"][0]["voice"] = {
        "enterVoiceText": "家属真人语音",
        "enterAudioUrl": "https://files.example.com/custom.mp3",
        "enterVoiceType": "CUSTOM",
    }
    client.post("/api/engine/routes", headers=headers, json=route)
    import app.main

    monkeypatch.setattr(
        app.main,
        "generate_step_copy",
        lambda *_args, **_kwargs: [
            {
                "stepId": step["id"],
                "elderShortAction": f"老人动作{step['stepNo']}",
                "enterVoiceText": "请先往前走。",
                "repeatVoiceText": "请继续往前走。",
                "nearVoiceText": "快到了，请看照片。",
                "arrivedVoiceText": "已经接近，请确认后点我找到了。",
                "offRouteVoiceText": "请先停下，不要继续走，可以求助家人。",
                "landmarkSuggestion": "需要家属确认并补充地标。",
                "photoSuggestion": "建议补充实景照片。",
                "familyReviewFocus": "确认老人能否理解。",
                "aiConfidence": "MEDIUM",
                "needsReview": step.get("riskLevel") == "HIGH",
            }
            for step in route["steps"]
        ],
    )
    generated = client.post(
        "/api/engine/routes/route-engine-test/ai-generate-voices", headers=headers
    )
    assert generated.status_code == 200
    result = generated.json()["route"]
    assert [step["id"] for step in result["steps"]] == [
        "step-start",
        "step-bus",
        "step-destination",
    ]
    assert result["steps"][0]["location"] == route["steps"][0]["location"]
    assert result["steps"][0]["type"] == "START"
    assert result["steps"][1]["transit"] == route["steps"][1]["transit"]
    assert result["steps"][0]["voice"]["enterVoiceText"] == "家属真人语音"
    assert result["steps"][0]["voice"]["enterVoiceType"] == "CUSTOM"
    assert result["steps"][1]["voice"]["nearVoiceText"] == "快到了，请看照片。"


def test_ai_step_writer_failure_preserves_system_copy(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    created = client.post("/api/engine/routes", headers=headers, json=build_engine_route()).json()
    import app.main

    monkeypatch.setattr(app.main, "generate_step_copy", lambda *_args, **_kwargs: None)
    response = client.post(
        "/api/engine/routes/route-engine-test/ai-generate-voices", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["generated"] is False
    assert response.json()["route"]["steps"][0]["voice"] == created["steps"][0]["voice"]


def test_collection_plan_falls_back_and_does_not_change_route(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["steps"][1]["type"] = "RIGHT"
    route["steps"][1]["riskLevel"] = "HIGH"
    route["steps"][1]["imageStatus"] = "NONE"
    created = client.post("/api/engine/routes", headers=headers, json=route).json()

    response = client.post(
        "/api/engine/routes/route-engine-test/collection-plan", headers=headers
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["summary"]
    assert any(
        task["stepId"] == "step-start" and task["priority"] == "MUST"
        for task in plan["photoTasks"]
    )
    assert any(
        task["stepId"] == "step-bus" and task["priority"] == "MUST"
        for task in plan["photoTasks"]
    )
    assert any(
        task["stepId"] == "step-bus" and task["voiceType"] == "offRoute"
        for task in plan["voiceTasks"]
    )
    unchanged = client.get("/api/engine/routes/route-engine-test", headers=headers).json()
    assert unchanged["status"] == created["status"]
    assert unchanged["steps"][1]["reviewStatus"] == created["steps"][1]["reviewStatus"]


def test_collection_plan_uses_ai_but_keeps_required_rule_tasks(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["steps"][1]["riskLevel"] = "HIGH"
    client.post("/api/engine/routes", headers=headers, json=route)
    import app.main

    monkeypatch.setattr(
        app.main,
        "generate_collection_plan",
        lambda *_args, **_kwargs: {
            "summary": "AI 已生成采集清单。",
            "photoTasks": [
                {
                    "stepId": "step-start",
                    "stepNo": 1,
                    "priority": "MUST",
                    "reason": "起点需要拍照。",
                    "shootingGuide": "拍清楚出口。",
                    "badExamples": ["不要只拍地面"],
                }
            ],
            "landmarkTasks": [],
            "voiceTasks": [],
            "reviewTasks": [],
            "testTasks": [{"order": 1, "title": "测试", "description": "陪同走一遍。"}],
        },
    )
    response = client.post(
        "/api/engine/routes/route-engine-test/collection-plan", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["summary"] == "AI 已生成采集清单。"
    assert response.json()["photoTasks"][0]["stepId"] == "step-start"


def test_batch_tts_preserves_custom_and_continues_after_failure(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["steps"][0]["voice"] = {
        "enterVoiceText": "真人语音",
        "enterAudioUrl": "https://files.example.com/custom.mp3",
        "enterVoiceType": "CUSTOM",
    }
    client.post("/api/engine/routes", headers=headers, json=route)
    import app.main

    calls = []

    def fake_tts(text):
        calls.append(text)
        if "887" in text:
            raise app.main.HTTPException(status_code=502, detail="测试失败")
        return b"fake"

    monkeypatch.setattr(app.main, "request_tencent_tts", fake_tts)
    response = client.post(
        "/api/engine/routes/route-engine-test/tts/batch",
        headers=headers,
        json={"regenerateTts": False},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["route"]["steps"][0]["voice"]["enterVoiceType"] == "CUSTOM"
    statuses = [
        moment["status"]
        for step in result["steps"]
        for moment in step["moments"]
    ]
    assert "SKIPPED_CUSTOM" in statuses
    assert "SUCCESS" in statuses
    assert "FAILED" in statuses


def test_route_has_five_voice_moments_and_system_render_is_cached(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    created = client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    voice = created.json()["steps"][0]["voice"]
    for moment in ["enter", "repeat", "near", "arrived", "offRoute"]:
        assert voice[f"{moment}VoiceText"]

    import app.main

    calls = []
    monkeypatch.setattr(app.main, "request_tencent_tts", lambda text: calls.append(text) or b"fake")
    payload = {
        "routeId": "route-engine-test",
        "stepId": "step-start",
        "moment": "offRoute",
        "text": "请先停一下。",
    }
    first = client.post("/api/engine/voice/render", headers=headers, json=payload)
    second = client.post("/api/engine/voice/render", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["audioUrl"] == second.json()["audioUrl"]
    assert calls == ["请先停一下。"]


def test_empty_engine_route_cannot_publish(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    route = build_engine_route()
    route["id"] = "empty-route"
    route["steps"] = []
    created = client.post("/api/engine/routes", headers=headers, json=route)
    assert created.json()["status"] == "NEEDS_REVIEW"
    published = client.post("/api/engine/routes/empty-route/publish", headers=headers)
    assert published.status_code == 409


def test_published_route_can_be_disabled(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    for step_id in ["step-start", "step-bus", "step-destination"]:
        client.put(
            f"/api/engine/routes/route-engine-test/steps/{step_id}/review",
            headers=headers,
            json={"reviewStatus": "APPROVED"},
        )
    client.post("/api/engine/routes/route-engine-test/publish", headers=headers)
    disabled = client.post("/api/engine/routes/route-engine-test/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert client.get("/api/engine/elder-routes/TO_MOM", headers=headers).status_code == 404


def test_trip_results_summary(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    for result in ["FOUND", "HELP"]:
        response = client.post(
            "/api/engine/trip-results",
            headers=headers,
            json={
                "tripId": "trip-1",
                "routeId": "route-engine-test",
                "stepId": "step-1",
                "stepNo": 1,
                "stepResult": result,
            },
        )
        assert response.status_code == 200

    unauthenticated = client.get("/api/engine/routes/route-engine-test/trip-summary")
    assert unauthenticated.status_code == 401

    result = client.get(
        "/api/engine/routes/route-engine-test/trip-summary",
        headers=headers,
    ).json()
    assert result["summary"] == {"total": 2, "FOUND": 1, "NOT_FOUND": 0, "HELP": 1}
    assert result["routeHealthLevel"] == "BAD"
    assert result["foundCount"] == 1
    assert result["helpCount"] == 1
    assert result["problemSteps"][0]["problemLevel"] == "NEEDS_ATTENTION"


def test_help_result_records_contact_metadata(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())

    response = client.post(
        "/api/engine/trip-results",
        headers=headers,
        json={
            "tripId": "trip-help",
            "routeId": "route-engine-test",
            "stepId": "step-start",
            "stepNo": 1,
            "stepResult": "HELP",
            "helpReason": "USER_REQUEST",
            "emergencyContactName": "小王",
            "emergencyRelation": "女儿",
            "emergencyPhone": "13800000000",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["id"].startswith("trip-result-")
    assert result["helpStatus"] == "REQUESTED"
    assert result["emergencyContactName"] == "小王"
    assert result["emergencyRelation"] == "女儿"
    assert result["emergencyPhone"] == "13800000000"

    events = client.get(
        "/api/engine/routes/route-engine-test/help-events",
        headers=headers,
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["id"] == result["id"]

    resolved = client.put(
        f"/api/engine/routes/route-engine-test/help-events/{result['id']}",
        headers=headers,
        json={"helpStatus": "RESOLVED", "handledNote": "家属已回电"},
    )
    assert resolved.status_code == 200
    resolved_result = resolved.json()
    assert resolved_result["helpStatus"] == "RESOLVED"
    assert resolved_result["handledNote"] == "家属已回电"
    assert resolved_result["handledByUserId"] == "legacy"
    assert resolved_result["handledAt"]


def test_route_review_center_and_trip_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    for payload in [
        {"tripId": "trip-1", "stepId": "step-start", "stepNo": 1, "stepResult": "FOUND"},
        {"tripId": "trip-1", "stepId": "step-bus", "stepNo": 2, "stepResult": "NOT_FOUND"},
        {"tripId": "trip-2", "stepId": "step-bus", "stepNo": 2, "stepResult": "HELP"},
    ]:
        client.post(
            "/api/engine/trip-results",
            headers=headers,
            json={"routeId": "route-engine-test", **payload},
        )

    center = client.get("/api/engine/routes/route-engine-test/review-center", headers=headers)
    assert center.status_code == 200
    result = center.json()
    assert result["routeHealthLevel"] == "BAD"
    assert result["foundCount"] == 1
    assert result["notFoundCount"] == 1
    assert result["helpCount"] == 1
    assert result["problemSteps"][0]["stepId"] == "step-bus"
    assert result["problemSteps"][0]["problemLevel"] == "NEEDS_ATTENTION"

    analysis = client.post(
        "/api/engine/routes/route-engine-test/trip-analysis", headers=headers
    )
    assert analysis.status_code == 200
    assert analysis.json()["problemSteps"][0]["stepId"] == "step-bus"
    assert "重新拍摄" in str(analysis.json())


def test_photo_review_rule_based_result_is_saved(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())
    response = client.post(
        "/api/engine/routes/route-engine-test/steps/step-bus/photo-review",
        headers=headers,
        json={
            "imageUrl": "https://files.example.com/staticimage/step.jpg",
            "imageStatus": "AUTO",
            "fileSize": 1024,
        },
    )
    assert response.status_code == 200
    assert response.json()["photoReview"]["status"] == "REJECT"
    step = response.json()["route"]["steps"][1]
    assert step["photoReview"]["needRetake"] is True


def test_wechat_account_login_and_route_scope(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    status = client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json() == {"bootstrapped": False}

    login = client.post(
        "/api/auth/wechat-login",
        json={"code": "family-admin", "familyName": "阳阳家"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["familyName"] == "阳阳家"
    assert login.json()["user"]["role"] == "FAMILY_ADMIN"
    assert client.get("/api/auth/status").json() == {"bootstrapped": True}
    family_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    route = build_engine_route()
    saved = client.post("/api/engine/routes", headers=family_headers, json=route)
    assert saved.status_code == 200
    assert saved.json()["familyId"] == login.json()["user"]["familyId"]

    listed = client.get("/api/engine/routes", headers=family_headers)
    assert [item["id"] for item in listed.json()["routes"]] == ["route-engine-test"]

    blocked = client.get("/api/engine/routes")
    assert blocked.status_code == 401

    me = client.get("/api/auth/me", headers=family_headers)
    assert me.status_code == 200
    assert me.json()["user"]["wechatBound"] is True


def test_wechat_login_creates_family_user_and_elder_binding(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    login = client.post(
        "/api/auth/wechat-login",
        json={"code": "abc123", "familyName": "阳阳家"},
    )
    assert login.status_code == 200
    result = login.json()
    assert result["token"]
    assert result["user"]["familyName"] == "阳阳家"
    assert result["user"]["wechatBound"] is True
    assert result["user"]["accessibleElderIds"]
    assert result["user"]["role"] == "FAMILY_ADMIN"
    assert "session_key" not in str(result)

    headers = {"Authorization": f"Bearer {result['token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["elders"][0]["name"] == "默认老人"

    second_login = client.post(
        "/api/auth/wechat-login",
        json={"code": "abc123", "familyName": "另一个家庭名不会覆盖"},
    )
    assert second_login.status_code == 200
    assert second_login.json()["user"]["familyId"] == result["user"]["familyId"]


def test_two_wechat_families_have_isolated_elder_routes(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    family_a = client.post(
        "/api/auth/wechat-login",
        json={"code": "family-a", "familyName": "A家"},
    ).json()
    family_b = client.post(
        "/api/auth/wechat-login",
        json={"code": "family-b", "familyName": "B家"},
    ).json()
    headers_a = {"Authorization": f"Bearer {family_a['token']}"}
    headers_b = {"Authorization": f"Bearer {family_b['token']}"}

    route_a = approve_and_publish_route(
        client, headers_a, build_engine_route_with_id("route-family-a", "A家路线")
    )
    route_b = approve_and_publish_route(
        client, headers_b, build_engine_route_with_id("route-family-b", "B家路线")
    )

    assert route_a["status"] == "PUBLISHED"
    assert route_b["status"] == "PUBLISHED"

    elder_route_a = client.get("/api/engine/elder-routes/TO_MOM", headers=headers_a)
    elder_route_b = client.get("/api/engine/elder-routes/TO_MOM", headers=headers_b)
    assert elder_route_a.status_code == 200
    assert elder_route_b.status_code == 200
    assert elder_route_a.json()["id"] == "route-family-a"
    assert elder_route_b.json()["id"] == "route-family-b"

    listed_a = client.get("/api/engine/routes", headers=headers_a).json()["routes"]
    listed_b = client.get("/api/engine/routes", headers=headers_b).json()["routes"]
    assert [route["id"] for route in listed_a] == ["route-family-a"]
    assert [route["id"] for route in listed_b] == ["route-family-b"]

    public_read = client.get("/api/engine/elder-routes/TO_MOM")
    assert public_read.status_code == 401


def test_session_user_cannot_access_unowned_legacy_route_without_family_id(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )
    login = client.post(
        "/api/auth/wechat-login",
        json={"code": "legacy-reader", "familyName": "A家"},
    ).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    legacy_headers = {"Authorization": "Bearer test-token"}
    legacy_route = build_engine_route_with_id("legacy-route", "旧路线")
    legacy_route.pop("familyId", None)
    created = client.post("/api/engine/routes", headers=legacy_headers, json=legacy_route)
    assert created.status_code == 200

    listed = client.get("/api/engine/routes", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["routes"] == []
    assert client.get("/api/engine/routes/legacy-route", headers=headers).status_code == 404


def test_family_member_cannot_manage_route(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    login = client.post(
        "/api/auth/wechat-login",
        json={"code": "member-user", "familyName": "成员家庭"},
    ).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    with sqlite3.connect(tmp_path / "auth.db") as conn:
        conn.execute(
            "UPDATE family_members SET role = 'FAMILY_MEMBER' WHERE user_id = ?",
            (login["user"]["id"],),
        )

    created = client.post(
        "/api/engine/routes",
        headers=headers,
        json=build_engine_route_with_id("member-route", "成员创建路线"),
    )
    assert created.status_code == 200
    step_id = created.json()["steps"][0]["id"]

    reviewed = client.put(
        f"/api/engine/routes/member-route/steps/{step_id}/review",
        headers=headers,
        json={"reviewStatus": "APPROVED"},
    )
    assert reviewed.status_code == 403

    updated_route = created.json()
    updated_route["name"] = "成员修改路线"
    updated = client.put(
        "/api/engine/routes/member-route",
        headers=headers,
        json=updated_route,
    )
    assert updated.status_code == 403

    deleted = client.delete("/api/engine/routes/member-route", headers=headers)
    assert deleted.status_code == 403

    disabled = client.post("/api/engine/routes/member-route/disable", headers=headers)
    assert disabled.status_code == 403

    published = client.post("/api/engine/routes/member-route/publish", headers=headers)
    assert published.status_code == 403

    ai_voices = client.post("/api/engine/routes/member-route/ai-generate-voices", headers=headers)
    assert ai_voices.status_code == 403

    tts = client.post(
        f"/api/engine/routes/member-route/steps/{step_id}/tts",
        headers=headers,
        json={"moment": "enter", "text": "请继续往前走。"},
    )
    assert tts.status_code == 403

    batch_tts = client.post(
        "/api/engine/routes/member-route/tts/batch",
        headers=headers,
        json={"regenerateTts": False},
    )
    assert batch_tts.status_code == 403

    photo_review = client.post(
        f"/api/engine/routes/member-route/steps/{step_id}/photo-review",
        headers=headers,
        json={"imageUrl": "https://files.example.com/photo.jpg", "imageStatus": "FAMILY", "fileSize": 1024},
    )
    assert photo_review.status_code == 403

    help_result = client.post(
        "/api/engine/trip-results",
        headers=headers,
        json={
            "tripId": "trip-member-help",
            "routeId": "member-route",
            "stepId": step_id,
            "stepNo": 1,
            "stepResult": "HELP",
        },
    )
    assert help_result.status_code == 200

    help_events = client.get("/api/engine/routes/member-route/help-events", headers=headers)
    assert help_events.status_code == 200

    resolved = client.put(
        f"/api/engine/routes/member-route/help-events/{help_result.json()['id']}",
        headers=headers,
        json={"helpStatus": "RESOLVED", "handledNote": "普通成员尝试处理"},
    )
    assert resolved.status_code == 403



def test_elder_wechat_binding_uses_family_member_role(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    admin_login = client.post(
        "/api/auth/wechat-login",
        json={"code": "guardian", "familyName": "阳阳家"},
    ).json()
    admin_headers = {"Authorization": f"Bearer {admin_login['token']}"}
    elder_id = admin_login["user"]["accessibleElderIds"][0]

    bind_code = client.post(
        "/api/auth/elder-bind-codes",
        headers=admin_headers,
        json={"elderId": elder_id, "relation": "本人"},
    )
    assert bind_code.status_code == 200

    elder_login = client.post(
        "/api/auth/wechat-bind-elder",
        json={"code": "elder-phone", "bindCode": bind_code.json()["code"]},
    )
    assert elder_login.status_code == 200
    result = elder_login.json()
    assert result["user"]["familyId"] == admin_login["user"]["familyId"]
    assert result["user"]["role"] == "ELDER_USER"
    assert result["user"]["accessibleElderIds"] == [elder_id]
    assert result["elder"]["id"] == elder_id

    elder_headers = {"Authorization": f"Bearer {result['token']}"}
    create_route = client.post(
        "/api/engine/routes",
        headers=elder_headers,
        json=build_engine_route_with_id("elder-created-route", "老人尝试创建"),
    )
    assert create_route.status_code == 200
    publish = client.post("/api/engine/routes/elder-created-route/publish", headers=elder_headers)
    assert publish.status_code == 403


def test_emergency_contact_is_family_scoped_and_elder_readable(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    admin_login = client.post(
        "/api/auth/wechat-login",
        json={"code": "contact-admin", "familyName": "联系人家庭"},
    ).json()
    admin_headers = {"Authorization": f"Bearer {admin_login['token']}"}
    elder_id = admin_login["user"]["accessibleElderIds"][0]

    empty = client.get("/api/auth/emergency-contact", headers=admin_headers)
    assert empty.status_code == 200
    assert empty.json()["phone"] == ""
    assert empty.json()["elderId"] == elder_id

    saved = client.put(
        "/api/auth/emergency-contact",
        headers=admin_headers,
        json={"name": "小王", "relation": "女儿", "phone": "13800000000"},
    )
    assert saved.status_code == 200
    assert saved.json()["elderId"] == elder_id
    assert saved.json()["name"] == "小王"
    assert saved.json()["phone"] == "13800000000"

    missing_relation = client.put(
        "/api/auth/emergency-contact",
        headers=admin_headers,
        json={"name": "小王", "relation": "", "phone": "13800000000"},
    )
    assert missing_relation.status_code == 400

    bind_code = client.post(
        "/api/auth/elder-bind-codes",
        headers=admin_headers,
        json={"elderId": elder_id, "relation": "本人"},
    ).json()["code"]
    elder_login = client.post(
        "/api/auth/wechat-bind-elder",
        json={"code": "contact-elder", "bindCode": bind_code},
    ).json()
    elder_headers = {"Authorization": f"Bearer {elder_login['token']}"}

    readable = client.get("/api/auth/emergency-contact", headers=elder_headers)
    assert readable.status_code == 200
    assert readable.json()["phone"] == "13800000000"

    blocked = client.put(
        "/api/auth/emergency-contact",
        headers=elder_headers,
        json={"name": "老人修改", "relation": "本人", "phone": "13900000000"},
    )
    assert blocked.status_code == 403


def test_super_admin_openid_can_access_other_family_for_testing(tmp_path, monkeypatch):
    monkeypatch.setenv("JIALUTONG_SUPER_ADMIN_OPENIDS", "openid-super")
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "request_wechat_code_session",
        lambda code: {"openid": f"openid-{code}", "session_key": "secret-session-key"},
    )

    normal = client.post(
        "/api/auth/wechat-login",
        json={"code": "normal", "familyName": "普通家庭"},
    ).json()
    normal_headers = {"Authorization": f"Bearer {normal['token']}"}
    client.post(
        "/api/engine/routes",
        headers=normal_headers,
        json=build_engine_route_with_id("normal-family-route", "普通家庭路线"),
    )

    super_login = client.post(
        "/api/auth/wechat-login",
        json={"code": "super", "familyName": "测试管理员家庭"},
    ).json()
    assert super_login["user"]["role"] == "SUPER_ADMIN"
    super_headers = {"Authorization": f"Bearer {super_login['token']}"}
    assert client.get("/api/engine/routes/normal-family-route", headers=super_headers).status_code == 200

def test_route_plan_requires_server_side_baidu_key(tmp_path, monkeypatch):
    monkeypatch.setenv("JIALUTONG_BAIDU_MAP_KEY", "")
    client = create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/engine/route-plans",
        headers={"Authorization": "Bearer test-token"},
        json={
            "mode": "WALKING",
            "origin": {"latitude": 31.25, "longitude": 121.32},
            "destination": {"latitude": 31.3, "longitude": 121.45},
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "请先配置百度地图服务端 AK"

    place_response = client.post(
        "/api/engine/places/search",
        headers={"Authorization": "Bearer test-token"},
        json={"keyword": "富友嘉园一期", "region": "上海"},
    )
    assert place_response.status_code == 503
    assert place_response.json()["detail"] == "请先配置百度地图服务端 AK"


def test_route_advisor_falls_back_without_ai_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    client = create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/engine/routes/advise",
        headers={"Authorization": "Bearer test-token"},
        json={
            "originName": "富友嘉园一期",
            "destinationName": "星荟中心",
            "plans": [
                {
                    "index": 0,
                    "distance": 1642,
                    "duration": 1482,
                    "description": "步行到临洮路站",
                    "walkDistance": 1642,
                    "transferCount": 0,
                    "riskPointCount": 5,
                    "decisionPointCount": 18,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["recommendedPlanIndex"] == 0
    assert "AI路线建议暂不可用" in response.json()["reason"]


def test_route_advisor_falls_back_when_provider_fails(monkeypatch):
    from app.services import ai_route_advisor

    monkeypatch.setattr(
        ai_route_advisor,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    advice = ai_route_advisor.advise_route(
        "富友嘉园一期",
        "星荟中心",
        [{"index": 0, "description": "步行到临洮路站"}],
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
    )
    assert advice["recommendedPlanIndex"] == 0
    assert "AI路线建议暂不可用" in advice["reason"]


def test_route_advisor_removes_ungrounded_landmark_examples():
    from app.services.ai_route_advisor import _validate_advice

    advice = _validate_advice(
        {
            "recommendedPlanIndex": 0,
            "summary": "推荐方案1",
            "reason": "步行更少。",
            "risks": ["需要确认站点"],
            "photoSuggestions": ["拍摄站点"],
            "landmarkSuggestions": ["请补充固定地标（如红色商店、玻璃幕墙）"],
            "familyReviewFocus": ["确认站点"],
        },
        [{"index": 0}],
    )
    assert advice["landmarkSuggestions"] == ["请补充固定地标。"]


def test_route_advisor_removes_incorrect_shorter_duration_claim():
    from app.services.ai_route_advisor import _validate_advice

    advice = _validate_advice(
        {
            "recommendedPlanIndex": 1,
            "summary": "推荐方案2，比方案1节省约5分钟，步行更少。",
            "reason": "方案2比方案1用时更短（1800秒 vs 1482秒）；步行距离更少。",
            "risks": [],
            "photoSuggestions": [],
            "landmarkSuggestions": [],
            "familyReviewFocus": [],
        },
        [{"index": 0, "duration": 1482}, {"index": 1, "duration": 1800}],
    )
    assert "用时更短" not in advice["reason"]
    assert "步行距离更少" in advice["reason"]
    assert "节省约5分钟" not in advice["summary"]
    assert "步行更少" in advice["summary"]


def test_route_advisor_returns_structured_advice(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(
        app.main,
        "advise_route",
        lambda *_args, **_kwargs: {
            "recommendedPlanIndex": 1,
            "summary": "推荐方案2",
            "reason": "换乘少。",
            "risks": ["需要过马路"],
            "photoSuggestions": ["拍摄小区出口"],
            "landmarkSuggestions": ["红绿灯"],
            "familyReviewFocus": ["确认过马路位置"],
        },
    )
    response = client.post(
        "/api/engine/routes/advise",
        headers={"Authorization": "Bearer test-token"},
        json={
            "originName": "富友嘉园一期",
            "destinationName": "星荟中心",
            "plans": [
                {"index": 0, "description": "方案一"},
                {"index": 1, "description": "方案二"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["recommendedPlanIndex"] == 1
    assert response.json()["risks"] == ["需要过马路"]


def test_reverse_geocode_returns_named_place(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    import app.main

    monkeypatch.setattr(app.main, "BAIDU_MAP_KEY", "test-key")
    monkeypatch.setattr(
        app.main,
        "request_baidu_json",
        lambda _url: {
            "status": 0,
            "result": {
                "formatted_address": "上海市虹口区四川北路",
                "sematic_description": "星荟中心一座附近",
                "addressComponent": {"street": "四川北路"},
                "pois": [{"uid": "poi-1", "name": "星荟中心一座", "addr": "四川北路"}],
            },
        },
    )
    response = client.post(
        "/api/engine/places/reverse-geocode",
        headers={"Authorization": "Bearer test-token"},
        json={"location": {"latitude": 31.246, "longitude": 121.487}},
    )
    assert response.status_code == 200
    assert response.json()["place"]["name"] == "星荟中心一座"
    assert response.json()["place"]["address"] == "上海市虹口区四川北路"
