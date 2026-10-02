from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_DIR / "config.toml"
ENV_PATH = PROJECT_DIR / ".env"
CREDENTIALS_PATH = PROJECT_DIR / "credentials.json"

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "email-triage"
TOKEN_PATH = APP_SUPPORT_DIR / "token.json"

LOG_DIR = Path.home() / "Library" / "Logs" / "email-triage"
LOG_PATH = LOG_DIR / "triage.log"
