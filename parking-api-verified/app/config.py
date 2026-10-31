"""Shared environment loading; existing process variables take precedence."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_NAMES = ("QWEN_BASE_URL", "QWEN_MODEL", "QWEN_API_KEY", "QWEN_TIMEOUT", "QWEN_MAX_TOKENS")


def load_env(path=None):
    path = Path(path) if path is not None else ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in ENV_NAMES:
                    os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))
