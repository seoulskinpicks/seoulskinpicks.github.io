"""AI text for card copy, with retries and backup providers.

Order (only the ones that are set up are used):
  1. Claude  (ANTHROPIC_API_KEY, paid)          — only if you add the key
  2. Gemini  (GEMINI_API_KEY, free AI Studio key)
  3. GitHub Models (the workflow's own GITHUB_TOKEN, free, no sign-up)

Each provider gets a few tries when the error looks temporary (busy server, rate limit,
network): wait 5 s → 1 min → 5 min (config [copy] retry_delays). If it still fails, the next
provider is tried. If every provider fails, the caller falls back to the built-in templates,
so a post is never blocked by AI.
"""
from __future__ import annotations

import time

import requests

from .util import scrub, warn

TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
DEFAULT_RETRY_DELAYS = [5, 60, 300]

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_FALLBACK_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
PROVIDER_NAMES = {"claude": "Claude", "gemini": "Gemini", "github": "GitHub Models"}


class AITemporary(Exception):
    """Worth retrying later (overloaded, rate limited, network)."""


class AIUnavailable(Exception):
    """Retrying won't help (bad key, unknown model, no access) → go to the next provider."""


def providers(cfg) -> list[str]:
    ready = {"claude": bool(cfg.anthropic_key), "gemini": bool(cfg.gemini_key), "github": bool(cfg.github_models_token)}
    order = cfg.copy.get("ai_order", ["claude", "gemini", "github"])
    return [p for p in order if ready.get(p)]


def describe(cfg) -> str:
    return " → ".join(PROVIDER_NAMES[p] for p in providers(cfg))


def _error_text(resp) -> str:
    try:
        err = resp.json().get("error", "")
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:
        msg = ""
    return f"HTTP {resp.status_code} {msg}".strip()[:160]


def _post(http, url, headers, body, timeout, secrets=()):
    try:
        resp = http.post(url, headers=headers, json=body, timeout=timeout)
    except Exception as exc:  # timeouts, connection resets, DNS …
        raise AITemporary(scrub(str(exc), *secrets)[:160]) from None
    if resp.status_code in TRANSIENT_STATUS:
        raise AITemporary(scrub(_error_text(resp), *secrets))
    if resp.status_code >= 400:
        raise AIUnavailable(scrub(_error_text(resp), *secrets))
    try:
        return resp.json()
    except Exception:
        raise AITemporary("응답을 읽지 못했어요") from None


# ---- one attempt per provider -------------------------------------------------
def _claude_once(system, user, cfg, http) -> str:
    data = _post(http, "https://api.anthropic.com/v1/messages",
                 {"x-api-key": cfg.anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                 {"model": cfg.copy.get("ai_model", "claude-haiku-4-5-20251001"), "max_tokens": 700,
                  "system": system, "messages": [{"role": "user", "content": user}]},
                 60, (cfg.anthropic_key,))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not text:
        raise AITemporary("빈 응답")
    return text


def _gemini_models(cfg) -> list[str]:
    out = []
    for m in [str(cfg.copy.get("gemini_model", "")).strip(), *GEMINI_FALLBACK_MODELS]:
        if m and m not in out:
            out.append(m)
    return out


def _gemini_once(system, user, cfg, http) -> str:
    """Tries each Gemini model name once. Model names change often, and a busy model
    doesn't mean the others are busy, so move on to the next name before waiting."""
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7, "maxOutputTokens": 8192},
    }
    temporary = unavailable = ""
    for model in _gemini_models(cfg):
        try:
            data = _post(http, GEMINI_URL.format(model=model),
                         {"x-goog-api-key": cfg.gemini_key, "content-type": "application/json"},
                         body, 45, (cfg.gemini_key,))
        except AITemporary as exc:
            temporary = f"{model}: {exc}"
            warn(f"Gemini {model} 일시 오류 ({exc}) → 다른 모델 시도")
            continue
        except AIUnavailable as exc:
            unavailable = f"{model}: {exc}"
            warn(f"Gemini {model} 사용 불가 ({exc}) → 다른 모델 시도")
            continue
        cands = data.get("candidates") or []
        parts = (cands[0].get("content", {}).get("parts") if cands else None) or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if text:
            return text
        temporary = f"{model}: 빈 응답"
    if temporary:
        raise AITemporary(temporary)
    raise AIUnavailable(unavailable or "사용할 수 있는 모델 없음")


def _github_once(system, user, cfg, http) -> str:
    token = cfg.github_models_token
    data = _post(http, GITHUB_MODELS_URL,
                 {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                  "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
                 {"model": cfg.copy.get("github_model", "openai/gpt-4.1-mini"), "temperature": 0.7, "max_tokens": 800,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                 60, (token,))
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise AITemporary("빈 응답")
    return text


ONCE = {"claude": _claude_once, "gemini": _gemini_once, "github": _github_once}


# ---- retries + fallback -------------------------------------------------------
def ask(system: str, user: str, cfg, session=None, sleep=time.sleep) -> tuple[str, str]:
    """Returns (text, provider name). Raises RuntimeError if every provider failed."""
    http = session or requests
    delays = [float(d) for d in cfg.copy.get("retry_delays", DEFAULT_RETRY_DELAYS)]
    failures = []
    for p in providers(cfg):
        name = PROVIDER_NAMES[p]
        for attempt in range(len(delays) + 1):
            if attempt:
                wait = delays[attempt - 1]
                warn(f"{name} 다시 시도 {attempt}/{len(delays)} — {wait:g}초 뒤")
                sleep(wait)
            try:
                return ONCE[p](system, user, cfg, http), name
            except AITemporary as exc:
                last = f"{name}: {exc}"
                continue
            except AIUnavailable as exc:
                last = f"{name}: {exc}"
                break
        failures.append(last)
        warn(f"{name} 실패 ({last}) → 다음 AI로 넘어가요")
    raise RuntimeError("모든 AI 실패: " + " | ".join(failures) if failures else "설정된 AI 없음")


def check(cfg, session=None) -> list[str]:
    """Light connection check for `python -m bot check` (Gemini: no text generated)."""
    http = session or requests
    lines = []
    for p in providers(cfg):
        name = PROVIDER_NAMES[p]
        try:
            if p == "gemini":
                resp = http.get("https://generativelanguage.googleapis.com/v1beta/models",
                                headers={"x-goog-api-key": cfg.gemini_key}, params={"pageSize": 200}, timeout=30)
                if resp.status_code != 200:
                    raise AIUnavailable(scrub(_error_text(resp), cfg.gemini_key))
                names = [m.get("name", "").split("/")[-1] for m in resp.json().get("models", [])]
                flash = [n for n in names if "flash" in n and not any(x in n for x in ("image", "tts", "live", "audio"))]
                lines.append(f"{name}: 키 확인됨 (Flash 모델 {len(flash)}개)")
            elif p == "github":
                text = _github_once("Reply with the single word OK.", "ping", cfg, http)
                lines.append(f"{name}: 연결됨 ({text.strip()[:10]})")
            else:
                lines.append(f"{name}: 키 있음")
        except Exception as exc:
            lines.append(f"❌ {name}: {exc}")
    return lines
