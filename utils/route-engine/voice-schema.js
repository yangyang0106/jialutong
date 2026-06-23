const VOICE_MOMENTS = Object.freeze(["enter", "repeat", "near", "arrived", "offRoute"]);

const VOICE_MOMENT_LABELS = Object.freeze({
  enter: "进入语音",
  repeat: "途中重复语音",
  near: "接近语音",
  arrived: "到达语音",
  offRoute: "偏航语音"
});

const LEGACY_TEXT_FIELDS = Object.freeze({
  enter: "enterVoice",
  repeat: "repeatVoice",
  near: "nearVoice"
});

function upperFirst(value) {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
}

function getTextField(moment) {
  return `${moment}VoiceText`;
}

function getAudioField(moment) {
  return `${moment}AudioUrl`;
}

function getTypeField(moment) {
  return `${moment}VoiceType`;
}

function normalizeVoiceConfig(input = {}, fallbackText = "") {
  const voice = { ...input };
  const fallbackTexts = {
    enter: fallbackText || "请继续前进。",
    repeat: fallbackText || "请继续前进。",
    near: "快到了，请看照片确认。",
    arrived: "您已接近目标地点，请看照片确认。",
    offRoute: "好像走远了，请先停一下，不要继续走。需要帮助请联系家人。"
  };
  VOICE_MOMENTS.forEach((moment) => {
    const textField = getTextField(moment);
    const audioField = getAudioField(moment);
    const typeField = getTypeField(moment);
    const legacyText = LEGACY_TEXT_FIELDS[moment] && voice[LEGACY_TEXT_FIELDS[moment]];
    voice[textField] = voice[textField] || legacyText || fallbackTexts[moment];
    voice[audioField] =
      voice[audioField] || (moment === "enter" ? voice.audioUrl || "" : "");
    voice[typeField] =
      voice[typeField] || (voice[audioField] ? voice.voiceType || "TTS" : "SYSTEM");
  });
  voice.enterVoice = voice.enterVoiceText;
  voice.repeatVoice = voice.repeatVoiceText;
  voice.nearVoice = voice.nearVoiceText;
  voice.audioUrl = voice.enterAudioUrl;
  voice.voiceType = voice.enterVoiceType;
  return voice;
}

function getVoiceMoment(voice, moment, fallbackText = "") {
  const normalized = normalizeVoiceConfig(voice, fallbackText);
  return {
    moment,
    label: VOICE_MOMENT_LABELS[moment] || upperFirst(moment),
    text: normalized[getTextField(moment)] || fallbackText,
    audioUrl: normalized[getAudioField(moment)] || "",
    voiceType: normalized[getTypeField(moment)] || "SYSTEM"
  };
}

function setVoiceMoment(voice, moment, updates) {
  const normalized = normalizeVoiceConfig(voice);
  if (updates.text != null) normalized[getTextField(moment)] = updates.text;
  if (updates.audioUrl != null) normalized[getAudioField(moment)] = updates.audioUrl;
  if (updates.voiceType != null) normalized[getTypeField(moment)] = updates.voiceType;
  return normalizeVoiceConfig(normalized);
}

function listVoiceMoments(voice, fallbackText = "") {
  return VOICE_MOMENTS.map((moment) => getVoiceMoment(voice, moment, fallbackText));
}

module.exports = {
  VOICE_MOMENTS,
  VOICE_MOMENT_LABELS,
  getAudioField,
  getTextField,
  getTypeField,
  getVoiceMoment,
  listVoiceMoments,
  normalizeVoiceConfig,
  setVoiceMoment
};
