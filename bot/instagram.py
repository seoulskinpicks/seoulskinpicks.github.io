"""Publishes a carousel through the Instagram Graph API (Instagram Login flavor by default).

Flow: create one container per image -> carousel container -> wait until FINISHED
-> media_publish. Images must be reachable at public URLs (GitHub Pages).
"""
from __future__ import annotations

import time

import requests

from .util import log, scrub


class IGError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, host: str = "graph.instagram.com", version: str = "v24.0", session=None, sleep=time.sleep):
        self.token = token
        self.base = f"https://{host}/{version}"
        self.host = host
        self.http = session or requests.Session()
        self.sleep = sleep

    def _req(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        last = None
        for attempt in range(3):
            try:
                if method == "GET":
                    r = self.http.get(url, params=params, timeout=60)
                else:
                    r = self.http.post(url, data=params, timeout=60)
                data = r.json() if r.content else {}
            except Exception as exc:  # network hiccup -> retry
                last = scrub(str(exc), self.token)
                self.sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                self.sleep(5 * (attempt + 1))
                continue
            if "error" in data:
                err = data["error"]
                raise IGError(scrub(f"{err.get('message')} (code {err.get('code')}/{err.get('error_subcode', '-')})", self.token))
            if r.status_code >= 400:
                raise IGError(f"HTTP {r.status_code}")
            return data
        raise IGError(f"Instagram API에 연결하지 못했어요: {last}")

    # ------------------------------------------------------------------
    def account_id(self) -> tuple[str, str]:
        try:
            data = self._req("GET", "me", fields="user_id,username")
        except IGError as exc:
            if "190" in str(exc):  # invalid/expired token: no point retrying
                raise
            data = self._req("GET", "me", fields="id,username")
        return str(data.get("user_id") or data["id"]), data.get("username", "")

    def wait_ready(self, container_id: str, timeout: int = 300) -> None:
        waited = 0
        while True:
            data = self._req("GET", container_id, fields="status_code,status")
            code = data.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"컨테이너 처리 실패: {data.get('status', code)}")
            if waited >= timeout:
                raise IGError("인스타 처리 시간이 너무 오래 걸려요 (5분 초과)")
            self.sleep(5)
            waited += 5

    def publish_carousel(self, ig_id: str, image_urls: list[str], caption: str) -> dict:
        if not 2 <= len(image_urls) <= 10:
            raise IGError("캐러셀은 이미지 2~10장이어야 해요")
        children = []
        for url in image_urls:
            data = self._req("POST", f"{ig_id}/media", image_url=url, is_carousel_item="true")
            children.append(data["id"])
        for cid in children:
            self.wait_ready(cid)
        carousel = self._req("POST", f"{ig_id}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)
        self.wait_ready(carousel["id"])
        published = self._req("POST", f"{ig_id}/media_publish", creation_id=carousel["id"])
        media_id = published["id"]
        permalink = ""
        try:
            permalink = self._req("GET", media_id, fields="permalink").get("permalink", "")
        except IGError:
            pass
        log(f"인스타 게시 완료: {permalink or media_id}")
        return {"media_id": media_id, "permalink": permalink}

    def refresh_token(self) -> dict:
        """Extends a long-lived Instagram token by another 60 days."""
        r = self.http.get(
            f"https://{self.host}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": self.token},
            timeout=60,
        )
        data = r.json()
        if "error" in data or "access_token" not in data:
            raise IGError(scrub(str(data.get("error", data)), self.token))
        return data


def wait_for_urls(urls: list[str], timeout: int = 300, session=None, sleep=time.sleep) -> None:
    """GitHub Pages can take a minute after deploy; make sure every image is live first."""
    http = session or requests
    waited = 0
    pending = list(urls)
    while pending:
        still = []
        for u in pending:
            try:
                r = http.get(u, timeout=20)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                    continue
            except Exception:
                pass
            still.append(u)
        pending = still
        if not pending:
            return
        if waited >= timeout:
            raise IGError(f"이미지 주소가 열리지 않아요: {pending[0]}")
        sleep(10)
        waited += 10
