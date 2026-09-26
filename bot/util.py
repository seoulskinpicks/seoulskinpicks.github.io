"""Small shared helpers: logging, GitHub Actions outputs, text checks."""
from __future__ import annotations

import hashlib
import os
import re
import sys

_HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    # Shows up as a yellow annotation in the GitHub Actions run page.
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{msg}", flush=True)
    else:
        print(f"[경고] {msg}", file=sys.stderr, flush=True)


def set_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def add_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def has_hangul(text: str | None) -> bool:
    return bool(text) and bool(_HANGUL.search(text))


def short_hash(*parts: str) -> str:
    joined = "|".join(p.strip().lower() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def clean_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_http_url(value: str | None) -> bool:
    return bool(value) and bool(re.match(r"^https?://\S+\.\S+", value.strip()))


def scrub(text: str, *secrets: str | None) -> str:
    """Remove secrets (tokens, keys) from any text before it is logged or saved."""
    out = str(text)
    for s in secrets:
        if s:
            out = out.replace(s, "***")
    return re.sub(r"(access_token=)[^&\s\"']+", r"\1***", out)
