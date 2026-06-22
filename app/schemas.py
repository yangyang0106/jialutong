from typing import Any, Literal

from pydantic import BaseModel, Field


class StepConfig(BaseModel):
    image: str | None = None
    audio: str | None = None
    desc: str | None = None
    direction: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    verificationRequired: bool | None = None
    distanceTracking: bool | None = None


class Location(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class VoiceConfig(BaseModel):
    voiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"
    audioUrl: str = ""
    enterVoice: str = ""
    nearVoice: str = ""
    repeatVoice: str = ""
    enterVoiceText: str = ""
    repeatVoiceText: str = ""
    nearVoiceText: str = ""
    arrivedVoiceText: str = ""
    offRouteVoiceText: str = ""
    enterAudioUrl: str = ""
    repeatAudioUrl: str = ""
    nearAudioUrl: str = ""
    arrivedAudioUrl: str = ""
    offRouteAudioUrl: str = ""
    enterVoiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"
    repeatVoiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"
    nearVoiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"
    arrivedVoiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"
    offRouteVoiceType: Literal["SYSTEM", "CUSTOM", "TTS"] = "SYSTEM"


class RouteStep(BaseModel):
    id: str
    routeId: str
    stepNo: int
    type: Literal[
        "START",
        "STRAIGHT",
        "LEFT",
        "RIGHT",
        "BUS_ON",
        "BUS_OFF",
        "SUBWAY_IN",
        "SUBWAY_OUT",
        "TRANSFER",
        "DESTINATION",
    ]
    title: str = ""
    shortAction: str = ""
    location: Location
    arriveRadius: int = 30
    showDirectionDistance: int = 30
    direction: str = ""
    roadName: str = ""
    landmarkHint: str = ""
    riskLevel: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    imageUrl: str = ""
    imageStatus: Literal["NONE", "AUTO", "FAMILY"] = "NONE"
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    transit: dict[str, Any] | None = None
    requiresFamilyReview: bool = False
    reviewStatus: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    reviewNote: str = ""
    elderShortAction: str = ""
    landmarkSuggestion: str = ""
    photoSuggestion: str = ""
    familyReviewFocus: str = ""
    aiConfidence: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    needsReview: bool = False
    photoReview: dict[str, Any] | None = None
    stepResult: Literal["FOUND", "NOT_FOUND", "HELP"] | None = None
    source: dict[str, Any] | None = None


class EngineRoute(BaseModel):
    id: str
    name: str
    elderSlot: Literal["TO_MOM", "TO_HOME"] | None = None
    origin: dict[str, Any]
    destination: dict[str, Any]
    travelModes: list[str] = Field(default_factory=list)
    status: Literal["DRAFT", "NEEDS_REVIEW", "READY", "PUBLISHED", "DISABLED"] = "DRAFT"
    version: int = 1
    distance: int = 0
    estimatedDuration: int = 0
    sourceProvider: str = "BAIDU_MAP"
    sourceRouteId: str = ""
    sourcePolyline: list[float] = Field(default_factory=list)
    steps: list[RouteStep] = Field(default_factory=list)
    reviewSummary: dict[str, Any] | None = None
    createdAt: str = ""
    updatedAt: str = ""
    publishedAt: str = ""


class StepReview(BaseModel):
    reviewStatus: Literal["APPROVED", "REJECTED"] | None = None
    reviewNote: str | None = None
    imageUrl: str | None = None
    imageStatus: Literal["NONE", "AUTO", "FAMILY"] | None = None
    landmarkHint: str | None = None
    voice: VoiceConfig | None = None
    elderShortAction: str | None = None
    landmarkSuggestion: str | None = None
    photoSuggestion: str | None = None
    familyReviewFocus: str | None = None
    aiConfidence: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    needsReview: bool | None = None
    photoReview: dict[str, Any] | None = None


class StepExecution(BaseModel):
    tripId: str
    routeId: str
    stepId: str
    stepNo: int
    stepResult: Literal["FOUND", "NOT_FOUND", "HELP"]
    occurredAt: str = ""
    helpReason: str = ""


class RoutePlanRequest(BaseModel):
    mode: Literal["WALKING", "TRANSIT"]
    origin: Location
    destination: Location
    policy: str = "LEAST_TIME"


class RoutePlanSummary(BaseModel):
    index: int
    distance: int = 0
    duration: int = 0
    description: str = ""
    walkDistance: int = 0
    transferCount: int = 0
    riskPointCount: int = 0
    decisionPointCount: int = 0


class RouteAdviceRequest(BaseModel):
    originName: str
    destinationName: str
    plans: list[RoutePlanSummary] = Field(min_length=1, max_length=10)


class PlaceSearchRequest(BaseModel):
    keyword: str
    region: str = "上海"


class ReverseGeocodeRequest(BaseModel):
    location: Location


class TtsRequest(BaseModel):
    text: str = ""
    moment: Literal["enter", "repeat", "near", "arrived", "offRoute"] = "enter"


class BatchTtsRequest(BaseModel):
    regenerateTts: bool = False


class PhotoReviewRequest(BaseModel):
    imageUrl: str = ""
    imageStatus: Literal["NONE", "AUTO", "FAMILY"] = "FAMILY"
    fileSize: int = 0


class VoiceRenderRequest(BaseModel):
    routeId: str
    stepId: str
    moment: Literal["enter", "repeat", "near", "arrived", "offRoute"]
    text: str
