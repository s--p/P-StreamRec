"""
Configuration centralisée de l'application P-StreamRec
"""

import os
from pathlib import Path
from typing import Optional

# Chemins de base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "data")))

# Configuration FFmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
HLS_TIME = int(os.getenv("HLS_TIME", "4"))
HLS_LIST_SIZE = int(os.getenv("HLS_LIST_SIZE", "6"))

# Configuration Chaturbate
CB_RESOLVER_ENABLED = os.getenv("CB_RESOLVER_ENABLED", "false").lower() in {"1", "true", "yes"}
CB_COOKIE: Optional[str] = os.getenv("CB_COOKIE")

# Chaturbate Authentication
CHATURBATE_USERNAME: Optional[str] = os.getenv("CHATURBATE_USERNAME")
CHATURBATE_PASSWORD: Optional[str] = os.getenv("CHATURBATE_PASSWORD")

# Backward-compatible cookie env vars (fallback)
CHATURBATE_CSRFTOKEN: Optional[str] = os.getenv("CHATURBATE_CSRFTOKEN")
CHATURBATE_SESSIONID: Optional[str] = os.getenv("CHATURBATE_SESSIONID")

# FlareSolverr
FLARESOLVERR_URL: str = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191")
FLARESOLVERR_MAX_TIMEOUT: int = int(os.getenv("FLARESOLVERR_MAX_TIMEOUT", "60000"))

# Chaturbate request settings
CB_REQUEST_DELAY: float = float(os.getenv("CB_REQUEST_DELAY", "1.0"))

# Configuration serveur
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

# Configuration auto-record
AUTO_RECORD_INTERVAL = int(os.getenv("AUTO_RECORD_INTERVAL", "120"))  # secondes
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "3600"))  # secondes

# Recording settings (defaults, overridden by DB settings at runtime)
AUTO_CONVERT = os.getenv("AUTO_CONVERT", "true").lower() in {"1", "true", "yes"}
KEEP_TS = os.getenv("KEEP_TS", "false").lower() in {"1", "true", "yes"}
AUTO_CONVERT_WHILE_RECORDING = os.getenv("AUTO_CONVERT_WHILE_RECORDING", "false").lower() in {"1", "true", "yes"}

# Conversion profile
# - reencode: software x264 (best compatibility)
# - copy: remux TS->MP4 without re-encode (lowest CPU)
# - qsv: Intel QuickSync H.264 encode (requires ffmpeg qsv support + iGPU access)
# - vaapi: Intel VAAPI encode (hardware fallback on Linux)
CONVERT_MODE = os.getenv("CONVERT_MODE", "reencode").strip().lower()
CONVERT_PRESET = os.getenv("CONVERT_PRESET", "medium")
CONVERT_CRF = os.getenv("CONVERT_CRF", "23")
CONVERT_AUDIO_BITRATE = os.getenv("CONVERT_AUDIO_BITRATE", "128k")
CONVERT_COPY_AUDIO = os.getenv("CONVERT_COPY_AUDIO", "true").lower() in {"1", "true", "yes"}
CONVERT_QSV_DEVICE = os.getenv("CONVERT_QSV_DEVICE", "/dev/dri/renderD128")

# Timezone
TZ = os.getenv("TZ", "UTC")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Créer les répertoires nécessaires
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "sessions").mkdir(exist_ok=True)
(OUTPUT_DIR / "records").mkdir(exist_ok=True)
(OUTPUT_DIR / "thumbnails").mkdir(exist_ok=True)
(OUTPUT_DIR / "cookies").mkdir(exist_ok=True)

# Fichiers de données
MODELS_FILE = OUTPUT_DIR / "models.json"

# Configuration CORS
CORS_ORIGINS = ["*"]
CORS_CREDENTIALS = False
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]
