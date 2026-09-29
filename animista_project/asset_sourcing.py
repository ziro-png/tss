# -*- coding: utf-8 -*-
"""Small, best-effort image sourcing layer for Animista renders."""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _keywords(scene: dict, reference: Path | None = None) -> str:
    text = f"{scene.get('visual_description', '')} {scene.get('narration', '')}"
    if reference:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent / ".env")
            from llm_router import safe_completion

            encoded = base64.b64encode(reference.read_bytes()).decode("ascii")
            mime = mimetypes.guess_type(reference.name)[0] or "image/png"
            response = safe_completion(
                model="gemini/gemini-2.5-flash",
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "Return 5 short English search keywords for similar 2D vector artwork. JSON array only."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ]}],
            )
            text += " " + response.choices[0].message.content
        except Exception as error:
            print(f"[ASSETS] Vision analysis skipped: {error}")
    ignored = {"hand", "drawn", "sketch", "paper", "background", "simple", "appealing",
               "pastel", "line", "art", "style", "scene", "visual", "description",
               "with", "from", "into", "that", "this", "and", "the"}
    words = [word for word in re.findall(r"[^\W_]{3,}", text.lower()) if word not in ignored]
    return " ".join(words[:8]) + " illustration"


def _wikimedia_image_url(query: str) -> str | None:
    queries = [query, " ".join(query.split()[:4])]
    for candidate in queries:
        try:
            response = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params={"action": "query", "generator": "search", "gsrsearch": candidate,
                        "gsrnamespace": 6, "gsrlimit": 5, "prop": "imageinfo",
                        "iiprop": "url", "iiurlwidth": 1280, "format": "json"},
                headers={"User-Agent": "Animista/1.0 image sourcing"}, timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url and Path(url.split("?")[0]).suffix.lower() in IMAGE_EXTENSIONS:
                return url
    return None


def _duckduckgo_image_url(query: str) -> str | None:
    response = requests.get(
        f"https://html.duckduckgo.com/html/?q={quote(query)}",
        headers={"User-Agent": "Mozilla/5.0 Animista"}, timeout=15,
    )
    response.raise_for_status()
    links = re.findall(r'class="result__a"[^>]+href="([^"]+)"', response.text)
    for link in links[:5]:
        try:
            page = requests.get(link, headers={"User-Agent": "Mozilla/5.0 Animista"}, timeout=10)
            match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page.text, re.I)
            if match:
                return match.group(1)
        except requests.RequestException:
            continue
    return None


def _fallback_image_url(scene_number: int) -> str:
    tags = (
        "cartoon,cloud,satellite", "cartoon,earth,network", "ocean,underwater,cable",
        "fiber,optical,technology", "smartphone,data,cartoon", "network,route,technology",
        "server,underwater,technology", "computer,cartoon,conversation",
    )
    return f"https://loremflickr.com/1280/720/{tags[(scene_number - 1) % len(tags)]}?lock={scene_number}"


def source_scene_assets(scene: dict, scene_number: int, assets_dir: Path) -> Path | None:
    """Return a local scene image, fetching one once when it is missing."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(assets_dir.glob(f"scene_{scene_number:02d}_auto.*")):
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            return path
    reference = next((p for p in sorted(assets_dir.glob("reference.*")) if p.suffix.lower() in IMAGE_EXTENSIONS), None)
    query = _keywords(scene, reference)
    try:
        image_urls = [_wikimedia_image_url(query), _duckduckgo_image_url(query), _fallback_image_url(scene_number)]
        for image_url in image_urls:
            if not image_url:
                continue
            try:
                download = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0 Animista"}, timeout=20)
                download.raise_for_status()
                if not download.headers.get("content-type", "").startswith("image/"):
                    continue
                image = Image.open(__import__("io").BytesIO(download.content)).convert("RGB")
                destination = assets_dir / f"scene_{scene_number:02d}_auto.jpg"
                image.thumbnail((1920, 1080))
                image.save(destination, quality=88)
                print(f"[ASSETS] Downloaded scene {scene_number}: {destination.name}")
                return destination
            except Exception:
                continue
        raise RuntimeError("no valid image result")
    except Exception as error:
        print(f"[ASSETS] Scene {scene_number} fetch skipped: {error}")
        return None
