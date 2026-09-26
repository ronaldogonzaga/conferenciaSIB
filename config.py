import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

_VERSION_FILE = BASE_DIR / "VERSION"
APP_VERSION = (
    _VERSION_FILE.read_text(encoding="utf-8").strip()
    if _VERSION_FILE.exists()
    else "0.0.0"
)


class Config:
    DB_HOST = os.getenv("DB_HOST", "10.0.2.15")
    DB_PORT = int(os.getenv("DB_PORT", "6441"))
    DB_USER = os.getenv("DB_USER", "WARELINE")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "BENEF")
    DB_NAME = os.getenv("DB_NAME", "Plano_Saude")
    DB_SCHEMA = os.getenv("DB_SCHEMA", "WARELINE")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
    APP_VERSION = APP_VERSION
