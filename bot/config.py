"""Loads config.toml and secrets from environment variables."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    raw: dict
    root: Path = ROOT

    # ---- sections -------------------------------------------------------
    @property
    def account(self) -> dict:
        return self.raw.get("account", {})

    @property
    def handle(self) -> str:
        return self.account.get("handle", "your.handle").lstrip("@")

    @property
    def brand_name(self) -> str:
        return self.account.get("brand_name", "K-beauty Picks")

    @property
    def tagline(self) -> str:
        return self.account.get("tagline", "")

    @property
    def timezone(self) -> str:
        return self.account.get("timezone", "Asia/Seoul")

    @property
    def mode(self) -> str:
        return self.raw.get("schedule", {}).get("mode", "alternate")

    @property
    def kbeauty(self) -> dict:
        return self.raw.get("kbeauty", {})

    @property
    def sheet_csv_url(self) -> str:
        return (self.kbeauty.get("sheet_csv_url") or os.environ.get("KBEAUTY_SHEET_CSV_URL") or "").strip()

    @property
    def queue_file(self) -> Path:
        return self.root / "data" / "kbeauty_queue.csv"

    @property
    def state_file(self) -> Path:
        return self.root / "data" / "state.json"

    @property
    def ali(self) -> dict:
        return self.raw.get("aliexpress", {})

    @property
    def copy(self) -> dict:
        return self.raw.get("copy", {})

    @property
    def instagram(self) -> dict:
        return self.raw.get("instagram", {})

    # ---- secrets ----------------------------------------------------------
    @property
    def ali_keys(self) -> tuple[str, str, str] | None:
        key = os.environ.get("ALI_APP_KEY", "").strip()
        secret = os.environ.get("ALI_APP_SECRET", "").strip()
        tracking = os.environ.get("ALI_TRACKING_ID", "").strip()
        if key and secret and tracking:
            return key, secret, tracking
        return None

    @property
    def anthropic_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "").strip()

    @property
    def gemini_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY", "").strip()

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_key or self.gemini_key)

    @property
    def ai_name(self) -> str:
        return "Claude" if self.anthropic_key else "Gemini" if self.gemini_key else ""

    @property
    def ig_token(self) -> str:
        return os.environ.get("IG_ACCESS_TOKEN", "").strip()

    @property
    def ig_user_id(self) -> str:
        return os.environ.get("IG_USER_ID", "").strip()


def load_config(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    with open(path, "rb") as fh:
        return Config(raw=tomllib.load(fh))
