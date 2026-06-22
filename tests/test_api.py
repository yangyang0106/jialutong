import importlib
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

    elderly_route = client.get("/api/engine/elder-routes/TO_MOM")
    assert elderly_route.status_code == 200
    assert elderly_route.json()["id"] == "route-engine-test"

    immutable = client.put(
        "/api/engine/routes/route-engine-test",
        headers=headers,
        json=published.json(),
    )
    assert immutable.status_code == 409


def test_unpublished_route_can_be_deleted_but_published_route_cannot(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer test-token"}
    client.post("/api/engine/routes", headers=headers, json=build_engine_route())

    deleted = client.delete("/api/engine/routes/route-engine-test", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/api/engine/routes/route-engine-test").status_code == 404

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
    unchanged = client.get("/api/engine/routes/route-engine-test").json()
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
    assert client.get("/api/engine/elder-routes/TO_MOM").status_code == 404


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

    result = client.get("/api/engine/routes/route-engine-test/trip-summary").json()
    assert result["summary"] == {"total": 2, "FOUND": 1, "NOT_FOUND": 0, "HELP": 1}
    assert result["routeHealthLevel"] == "BAD"
    assert result["foundCount"] == 1
    assert result["helpCount"] == 1
    assert result["problemSteps"][0]["problemLevel"] == "NEEDS_ATTENTION"


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

    center = client.get("/api/engine/routes/route-engine-test/review-center")
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
