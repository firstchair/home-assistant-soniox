"""Constants for the Soniox integration."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "soniox"
TITLE = "Soniox"

# Config entry data (set once, changed via reauth/reconfigure).
CONF_API_KEY = "api_key"
CONF_REGION = "region"

# Options (editable via Configure).
CONF_LANGUAGE = "language"
CONF_STT_MODEL = "stt_model"
CONF_CONTEXT_TERMS = "context_terms"
CONF_CONTEXT_TEXT = "context_text"
CONF_SPEAKER_ID_URL = "speaker_id_url"
CONF_SPEAKER_THRESHOLD = "speaker_threshold"
CONF_TTS_MODEL = "tts_model"
CONF_TTS_VOICE = "tts_voice"
CONF_TTS_SPEED = "tts_speed"
CONF_TTS_EMOTION = "tts_emotion"

AUTO_LANGUAGE = "auto"

REGION_US = "us"
REGION_EU = "eu"
REGIONS = (REGION_US, REGION_EU)

DEFAULT_REGION = REGION_US
DEFAULT_STT_MODEL = "stt-rt-v5"
DEFAULT_TTS_MODEL = "tts-rt-v2"
DEFAULT_TTS_SPEED = 1.0
DEFAULT_TTS_EMOTION = "neutral"
DEFAULT_SPEAKER_THRESHOLD = 0.5

TTS_SPEED_MIN = 0.7
TTS_SPEED_MAX = 1.3
TTS_STREAM_SAMPLE_RATE = 24000

# Soniox TTS v2 audio tags (docs: /docs/tts/concepts/emotion-and-tone). Tags are
# always English, placed before the text they affect. "neutral" = no tag.
# Users can also write any tag inline in the message; text is passed verbatim.
TTS_EMOTIONS: tuple[str, ...] = (
    "neutral",
    # emotions
    "happy",
    "sad",
    "angry",
    "excited",
    "nervous",
    "fearful",
    "surprised",
    "annoyed",
    "relieved",
    "disappointed",
    "curious",
    "delighted",
    "calm",
    # tone & manner
    "warm",
    "stern",
    "serious",
    "playful",
    "sarcastic",
    "flirty",
    "deadpan",
    "sincerely",
    "reassuringly",
    "dramatically",
    "mockingly",
    # volume & pace
    "whispering",
    "softly",
    "loudly",
    "slowly",
    "quickly",
    "hesitantly",
)

# tts.speak option keys (match the CONF_* names so one string works in both places).
ATTR_SPEED = "speed"
ATTR_EMOTION = "emotion"

# Endpoints per region. Data residency is set per Soniox project; the API key
# of an EU project only works against the EU hosts.
ENDPOINTS: dict[str, dict[str, str]] = {
    REGION_US: {
        "api": "https://api.soniox.com/v1",
        "stt_ws": "wss://stt-rt.soniox.com/transcribe-websocket",
        "tts": "https://tts-rt.soniox.com/tts",
        "tts_ws": "wss://tts-rt.soniox.com/tts-websocket",
    },
    REGION_EU: {
        "api": "https://api.eu.soniox.com/v1",
        "stt_ws": "wss://stt-rt.eu.soniox.com/transcribe-websocket",
        "tts": "https://tts-rt.eu.soniox.com/tts",
        "tts_ws": "wss://tts-rt.eu.soniox.com/tts-websocket",
    },
}

# Soniox base language codes → Home Assistant locale tags Assist may send.
LANGUAGE_TAGS: dict[str, tuple[str, ...]] = {
    "ar": ("ar", "ar-SA"),
    "be": ("be", "be-BY"),
    "bg": ("bg", "bg-BG"),
    "bn": ("bn", "bn-BD"),
    "ca": ("ca", "ca-ES"),
    "cs": ("cs", "cs-CZ"),
    "cy": ("cy", "cy-GB"),
    "da": ("da", "da-DK"),
    "de": ("de", "de-DE", "de-AT", "de-CH"),
    "el": ("el", "el-GR"),
    "en": ("en", "en-US", "en-GB", "en-AU", "en-CA", "en-IE", "en-NZ"),
    "es": ("es", "es-ES", "es-MX", "es-AR"),
    "et": ("et", "et-EE"),
    "eu": ("eu", "eu-ES"),
    "fa": ("fa", "fa-IR"),
    "fi": ("fi", "fi-FI"),
    "fr": ("fr", "fr-FR", "fr-CA", "fr-BE", "fr-CH"),
    "ga": ("ga", "ga-IE"),
    "gl": ("gl", "gl-ES"),
    "gu": ("gu", "gu-IN"),
    "he": ("he", "he-IL"),
    "hi": ("hi", "hi-IN"),
    "hr": ("hr", "hr-HR"),
    "hu": ("hu", "hu-HU"),
    "hy": ("hy", "hy-AM"),
    "id": ("id", "id-ID"),
    "it": ("it", "it-IT", "it-CH"),
    "ja": ("ja", "ja-JP"),
    "kk": ("kk", "kk-KZ"),
    "kn": ("kn", "kn-IN"),
    "ko": ("ko", "ko-KR"),
    "lt": ("lt", "lt-LT"),
    "lv": ("lv", "lv-LV"),
    "mi": ("mi", "mi-NZ"),
    "mk": ("mk", "mk-MK"),
    "mr": ("mr", "mr-IN"),
    "ms": ("ms", "ms-MY"),
    "ne": ("ne", "ne-NP"),
    "nl": ("nl", "nl-NL", "nl-BE"),
    "no": ("no", "nb-NO", "nn-NO"),
    "pa": ("pa", "pa-IN"),
    "pl": ("pl", "pl-PL"),
    "pt": ("pt", "pt-PT", "pt-BR"),
    "ro": ("ro", "ro-RO"),
    "ru": ("ru", "ru-RU"),
    "sk": ("sk", "sk-SK"),
    "sl": ("sl", "sl-SI"),
    "sr": ("sr", "sr-RS"),
    "sv": ("sv", "sv-SE"),
    "sw": ("sw", "sw-KE"),
    "ta": ("ta", "ta-IN"),
    "te": ("te", "te-IN"),
    "th": ("th", "th-TH"),
    "tl": ("tl", "tl-PH", "fil-PH"),
    "tr": ("tr", "tr-TR"),
    "uk": ("uk", "uk-UA"),
    "ur": ("ur", "ur-PK"),
    "vi": ("vi", "vi-VN"),
    "zh": ("zh", "zh-CN", "zh-TW", "zh-HK"),
}
