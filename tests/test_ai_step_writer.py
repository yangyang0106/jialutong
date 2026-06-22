from app.services.ai_step_writer import validate_step_output


def build_step():
    return {
        "id": "step-1",
        "type": "BUS_ON",
        "title": "乘坐887路公交车",
        "shortAction": "乘坐887路",
        "riskLevel": "MEDIUM",
        "transit": {
            "lineName": "887路",
            "stationName": "临洮路站",
            "direction": "开往嘉怡路方向",
        },
        "source": {"instruction": "在临洮路站乘坐887路公交车"},
        "voice": {},
    }


def build_output(**updates):
    result = {
        "stepId": "step-1",
        "elderShortAction": "乘坐887路",
        "enterVoiceText": "请在这里等待887路公交车。",
        "repeatVoiceText": "请继续在这里等待。",
        "nearVoiceText": "车快到了，请看清887路再上车。",
        "arrivedVoiceText": "已经到上车地点，请确认站牌。",
        "offRouteVoiceText": "好像走远了，请先停下并联系家人。",
        "landmarkSuggestion": "建议补充临洮路站站牌。",
        "photoSuggestion": "建议拍摄887路公交车和站牌。",
        "familyReviewFocus": "确认乘车方向和站牌。",
        "aiConfidence": "HIGH",
    }
    result.update(updates)
    return result


def test_voice_text_is_limited_to_sixty_characters():
    result = validate_step_output(build_output(enterVoiceText="请" * 80), build_step())
    assert len(result["enterVoiceText"]) == 60


def test_invented_transit_name_is_rejected_and_requires_review():
    result = validate_step_output(
        build_output(nearVoiceText="快到了，请乘坐999路公交车。"),
        build_step(),
    )
    assert result["nearVoiceText"] == ""
    assert result["needsReview"] is True


def test_uncertain_word_requires_family_review():
    result = validate_step_output(
        build_output(landmarkSuggestion="可能需要补充公交站牌。"),
        build_step(),
    )
    assert result["needsReview"] is True


def test_turn_is_only_allowed_in_near_voice():
    step = build_step()
    step["type"] = "RIGHT"
    result = validate_step_output(
        build_output(
            enterVoiceText="现在右转。",
            repeatVoiceText="请右转。",
            nearVoiceText="快到了，请准备右转。",
            arrivedVoiceText="到了，请右转。",
        ),
        step,
    )
    assert "右转" not in result["enterVoiceText"]
    assert "右转" not in result["repeatVoiceText"]
    assert "右转" in result["nearVoiceText"]
    assert "右转" not in result["arrivedVoiceText"]
    assert result["needsReview"] is True


def test_invented_visual_landmark_is_rejected():
    result = validate_step_output(
        build_output(landmarkSuggestion="公交站有蓝色站牌和电子屏。"),
        build_step(),
    )
    assert result["landmarkSuggestion"] == "需要家属确认并补充固定地标。"
    assert result["needsReview"] is True


def test_destination_does_not_announce_arrival_before_confirmation():
    step = build_step()
    step["type"] = "DESTINATION"
    result = validate_step_output(
        build_output(
            enterVoiceText="您已到达目的地。",
            repeatVoiceText="已经到了。",
        ),
        step,
    )
    assert "到达" not in result["enterVoiceText"]
    assert "到了" not in result["repeatVoiceText"]
    assert result["needsReview"] is True


def test_bus_off_does_not_tell_elder_to_stand_before_stopping():
    step = build_step()
    step["type"] = "BUS_OFF"
    result = validate_step_output(
        build_output(nearVoiceText="快到站了，请站起来扶好。"),
        step,
    )
    assert result["nearVoiceText"] == "快到站了，请先坐稳，准备下车。"
    assert result["needsReview"] is True
