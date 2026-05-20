#!/usr/bin/env python3
"""
Local device scraper → Hugging Face Space renderer bridge.

This script runs the scrape/download step on the user's own machine so the
requests originate from that device's IP, then uploads the downloaded video to
the Hugging Face Space Flask API for rendering.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from config import Config
from scraper import VideoScraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape locally on this device, then send the video to Hugging Face Space for rendering."
    )
    parser.add_argument("game", help="Game name, e.g. 'One State RP'")
    parser.add_argument("--backend-url", default=os.getenv("CLOUD_API_URL", ""), help="Hugging Face Space backend base URL, e.g. https://username-space-name.hf.space")
    parser.add_argument("--landing-url", required=True, help="Landing page URL passed to the render pipeline")
    parser.add_argument("--max-videos", type=int, default=1, help="Number of candidates to scrape locally before sending one to the cloud")
    parser.add_argument("--pick-index", type=int, default=1, help="1-based candidate index to download and send")
    parser.add_argument("--screenshot", default="", help="Optional screenshot file to include in the render request")
    parser.add_argument("--caption-color", default="yellow")
    parser.add_argument("--caption-pos", type=float, default=0.58)
    parser.add_argument("--landing-link-color", default="#64dcff")
    parser.add_argument("--link-font", default="Montserrat-Bold")
    parser.add_argument("--elevenlabs-key", default=os.getenv("ELEVENLABS_API_KEY", ""))
    parser.add_argument("--elevenlabs-voice-id", default=os.getenv("ELEVENLABS_VOICE_ID", ""))
    parser.add_argument("--groq-key", default=os.getenv("GROQ_API_KEY", ""))
    parser.add_argument("--sfx-enabled", action="store_true", default=True)
    parser.add_argument("--no-sfx", dest="sfx_enabled", action="store_false")
    parser.add_argument("--api-secret", default=os.getenv("CLOUD_API_SECRET_KEY") or os.getenv("API_SECRET_KEY", ""), help="API Secret Key for Hugging Face authentication")
    return parser


def resolve_backend_url(raw_url: str) -> str:
    backend_url = raw_url.strip().rstrip("/")
    if not backend_url:
        raise SystemExit("Missing --backend-url or CLOUD_API_URL.")
    return backend_url


def main() -> int:
    args = build_parser().parse_args()
    backend_url = resolve_backend_url(args.backend_url)

    cfg = Config()
    scraper = VideoScraper(config=cfg)

    search_term = args.game if "mod" in args.game.lower() else f"{args.game} MOD"
    print(f"[local] Searching from this device for: {search_term} gameplay")
    candidates = scraper.search(f"{search_term} gameplay", max_results=max(args.max_videos * 3, 3))
    if not candidates:
        print("[local] No candidate videos found.")
        return 1

    pick_index = max(1, min(args.pick_index, len(candidates))) - 1
    chosen = candidates[pick_index]
    print(f"[local] Selected candidate {pick_index + 1}/{len(candidates)}: {chosen.get('title', 'untitled')}")

    downloaded = scraper.download(chosen)
    if not downloaded:
        print("[local] Download failed.")
        return 1

    payload = {
        "game": args.game,
        "url": args.landing_url,
        "overlays": json.dumps([]),
        "layout": json.dumps({}),
        "caption_color": args.caption_color,
        "caption_pos": str(args.caption_pos),
        "landing_link_color": args.landing_link_color,
        "link_font": args.link_font,
        "elevenlabs_key": args.elevenlabs_key,
        "elevenlabs_voice_id": args.elevenlabs_voice_id,
        "groq_key": args.groq_key,
        "sfx_enabled": "true" if args.sfx_enabled else "false",
    }

    files = {"video": open(downloaded, "rb")}
    try:
        screenshot_path = Path(args.screenshot).expanduser() if args.screenshot else None
        if screenshot_path and screenshot_path.exists():
            files["screenshot"] = open(screenshot_path, "rb")

        headers = {}
        if args.api_secret:
            headers["X-API-Key"] = args.api_secret

        print(f"[cloud] Sending scraped file to: {backend_url}/api/cloud_process")
        response = requests.post(
            f"{backend_url}/api/cloud_process",
            data=payload,
            files=files,
            headers=headers,
            timeout=600,
        )
        print(f"[cloud] HTTP {response.status_code}")

        try:
            body = response.json()
        except Exception:
            print(response.text)
            return 1 if not response.ok else 0

        print(json.dumps(body, indent=2))
        return 0 if response.ok else 1
    finally:
        for handle in files.values():
            try:
                handle.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())