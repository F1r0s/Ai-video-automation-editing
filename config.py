"""
config.py — Centralised configuration loader.

All secrets are read from environment variables (or a local .env file).
Never hard-code API keys in source code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env automatically when running locally
load_dotenv(Path(__file__).parent / ".env")


class Config:
    # ── Output directories ────────────────────────────────────────────────────
    RAW_DIR      = Path(os.getenv("RAW_DIR",    "downloads/raw"))
    EDITED_DIR   = Path(os.getenv("EDITED_DIR", "downloads/edited"))

    # ── Video constraints ─────────────────────────────────────────────────────
    MAX_DURATION    = int(os.getenv("MAX_DURATION", 30))   # seconds
    TARGET_RATIO    = (9, 16)                               # width : height
    TARGET_WIDTH    = 1080
    TARGET_HEIGHT   = 1920

    # ── TTS / AI ──────────────────────────────────────────────────────────────
    ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pqHfZKP75CvOlQylNhV4")  # Adam (male)
    GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")        # for fast Llama scripts and Whisper STT
    OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")      # for fallback Whisper captions

    # ── YouTube ───────────────────────────────────────────────────────────────
    YOUTUBE_CLIENT_SECRET_FILE = os.getenv("YOUTUBE_CLIENT_SECRET", "secrets/youtube_client_secret.json")
    YOUTUBE_TOKEN_FILE         = os.getenv("YOUTUBE_TOKEN",         "secrets/youtube_token.json")

    # ── TikTok ────────────────────────────────────────────────────────────────
    TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    # ── Instagram / Facebook ─────────────────────────────────────────────────
    INSTAGRAM_ACCESS_TOKEN  = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    INSTAGRAM_USER_ID       = os.getenv("INSTAGRAM_USER_ID", "")
    FACEBOOK_ACCESS_TOKEN   = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    FACEBOOK_PAGE_ID        = os.getenv("FACEBOOK_PAGE_ID", "")

    # ── Telegram Notifications ────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── X (Twitter) ──────────────────────────────────────────────────────────
    X_API_KEY            = os.getenv("X_API_KEY", "")
    X_API_SECRET         = os.getenv("X_API_SECRET", "")
    X_ACCESS_TOKEN       = os.getenv("X_ACCESS_TOKEN", "")
    X_ACCESS_TOKEN_SECRET= os.getenv("X_ACCESS_TOKEN_SECRET", "")

    # ── Scraping ──────────────────────────────────────────────────────────────
    YT_DLP_COOKIES = os.getenv("YT_DLP_COOKIES", "")  # path to cookies.txt (optional)

    def __init__(self):
        # Create output dirs on first run
        self.RAW_DIR.mkdir(parents=True, exist_ok=True)
        self.EDITED_DIR.mkdir(parents=True, exist_ok=True)
        Path("secrets").mkdir(exist_ok=True)
