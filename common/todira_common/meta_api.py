"""Todira's own Facebook Page and Instagram account, through Meta's official Graph API (2026-11-11, owner: "build a
social media manager", after Facebook stopped his personal account from commenting).

Only the official, allowed uses: publishing on our own Page and Instagram account, and answering comments people
leave on them. Nothing here touches anyone's personal account, groups, or scrapes anything. Every call is a no-op
until the owner sets the keys (set-meta-secret.yaml, values typed into the GitHub form, never into a chat):
  META_PAGE_ID, META_PAGE_TOKEN       the Page and a long-lived Page access token
  META_IG_USER_ID                     the Instagram professional account linked to the Page (optional)
  META_APP_SECRET, META_VERIFY_TOKEN  the webhook's signature check and subscription check (website/main.py)
  META_GRAPH_VERSION                  optional, the Graph API version (default below)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v23.0"
_TIMEOUT = 60.0


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def page_enabled() -> bool:
    return bool(_env("META_PAGE_ID") and _env("META_PAGE_TOKEN"))


def instagram_enabled() -> bool:
    return page_enabled() and bool(_env("META_IG_USER_ID"))


def _url(path: str) -> str:
    return f"https://graph.facebook.com/{_env('META_GRAPH_VERSION') or DEFAULT_VERSION}/{path.lstrip('/')}"


def _post(path: str, data: dict, files: dict | None = None) -> dict:
    payload = {**data, "access_token": _env("META_PAGE_TOKEN")}
    resp = httpx.post(_url(path), data=payload, files=files, timeout=_TIMEOUT)
    body = resp.json() if resp.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
    if resp.status_code != 200 or "error" in body:
        # the error's type and code only: Meta's messages can echo the request
        err = body.get("error") or {}
        raise RuntimeError(f"Graph API {path.split('/')[-1]}: HTTP {resp.status_code} {err.get('type')} {err.get('code')}")
    return body


def _get(path: str, params: dict) -> dict:
    resp = httpx.get(_url(path), params={**params, "access_token": _env("META_PAGE_TOKEN")}, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Graph API GET: HTTP {resp.status_code}")
    return resp.json()


def _photo_url(photo_id: str) -> str | None:
    images = _get(photo_id, {"fields": "images"}).get("images") or []
    biggest = max(images, key=lambda i: i.get("width", 0), default=None)
    return biggest.get("source") if biggest else None


def publish_page_photos(pngs: list[bytes], caption: str) -> tuple[str, list[str]]:
    """One post on the Page with these images (one photo, or an album of several) and the caption. Returns the post id
    and the images' public addresses, which Instagram can then publish from."""
    page = _env("META_PAGE_ID")
    if len(pngs) == 1:
        body = _post(f"{page}/photos", {"caption": caption, "published": "true"},
                     files={"source": ("todira.png", pngs[0], "image/png")})
        return body.get("post_id") or body.get("id", ""), [u for u in [_photo_url(body["id"])] if u]
    ids = []
    for n, png in enumerate(pngs):
        body = _post(f"{page}/photos", {"published": "false"}, files={"source": (f"todira-{n + 1}.png", png, "image/png")})
        ids.append(body["id"])
    data = {"message": caption}
    for n, photo_id in enumerate(ids):
        data[f"attached_media[{n}]"] = f'{{"media_fbid":"{photo_id}"}}'
    post = _post(f"{page}/feed", data)
    return post.get("id", ""), [u for u in (_photo_url(i) for i in ids) if u]


def publish_instagram(image_urls: list[str], caption: str) -> str:
    """One Instagram post (an image, or a carousel of up to 10) from public image addresses. Returns the media id."""
    ig = _env("META_IG_USER_ID")
    if len(image_urls) == 1:
        container = _post(f"{ig}/media", {"image_url": image_urls[0], "caption": caption})["id"]
    else:
        children = [_post(f"{ig}/media", {"image_url": url, "is_carousel_item": "true"})["id"] for url in image_urls[:10]]
        container = _post(f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]
    for _ in range(10):  # Instagram fetches the images first; publishing too early is refused
        status = _get(container, {"fields": "status_code"}).get("status_code")
        if status in (None, "FINISHED"):
            break
        if status == "ERROR":
            raise RuntimeError("Instagram could not prepare the post")
        time.sleep(3)
    return _post(f"{ig}/media_publish", {"creation_id": container}).get("id", "")


def reply_to_page_comment(comment_id: str, text: str) -> None:
    _post(f"{comment_id}/comments", {"message": text})


def reply_to_instagram_comment(comment_id: str, text: str) -> None:
    _post(f"{comment_id}/replies", {"message": text})


def signature_ok(body: bytes, header: str | None) -> bool:
    """Whether a webhook call really comes from Meta: X-Hub-Signature-256 is the app secret's HMAC of the body."""
    secret = _env("META_APP_SECRET")
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def verify_token() -> str:
    return _env("META_VERIFY_TOKEN")
