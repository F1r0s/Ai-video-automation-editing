#!/usr/bin/env python3
"""
=============================================================================
  AI VIDEO AUTOMATION PIPELINE
  Full-stack scrape → edit → upload workflow for short-form vertical video
=============================================================================
  Author  : Auto-generated for One State RP MOD channel
  Version : 1.0.0
  License : MIT
=============================================================================
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# ── Internal modules ──────────────────────────────────────────────────────────
from scraper     import VideoScraper
from editor      import VideoEditor
from uploader    import SocialMediaUploader
from seo         import SEOGenerator
from config      import Config

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("main")


def run_pipeline(game_name: str, branding_image: str, landing_url: str,
                 max_videos: int = 5, dry_run: bool = False) -> None:
    """
    Full end-to-end pipeline:
      1. Scrape → 2. Edit → 3. Upload
    """
    cfg = Config()
    log.info("=" * 60)
    log.info(f"  PIPELINE START  |  game='{game_name}'  |  dry_run={dry_run}")
    log.info("=" * 60)

    # ── STEP 1: Scrape ────────────────────────────────────────────────────────
    scraper = VideoScraper(config=cfg)
    query   = f"{game_name} MOD"
    log.info(f"[1/3] Scraping for: '{query}'")

    candidates = scraper.search(query, max_results=max_videos * 3)
    if not candidates:
        log.error("No videos found. Exiting.")
        return

    log.info(f"  Found {len(candidates)} candidate(s) before filtering.")
    videos = scraper.filter_eligible(candidates)          # ≤30 s + 9:16
    log.info(f"  {len(videos)} video(s) passed filters.")

    if not videos:
        log.warning("No eligible videos after filtering. Try a broader search.")
        return

    videos = videos[:max_videos]

    # ── STEP 2: Download + Edit ───────────────────────────────────────────────
    editor     = VideoEditor(config=cfg)
    seo_gen    = SEOGenerator()
    processed  = []

    for idx, video_meta in enumerate(videos, 1):
        log.info(f"[2/3] Editing video {idx}/{len(videos)}: {video_meta['title']}")
        try:
            raw_path = scraper.download(video_meta)
            if not raw_path:
                log.warning(f"  Download failed for: {video_meta['title']}, skipping.")
                continue

            edited_path = editor.process(
                input_path      = raw_path,
                branding_image  = branding_image,
                landing_url     = landing_url,
                game_name       = game_name,
            )

            seo = seo_gen.generate(
                game_name   = game_name,
                video_title = video_meta.get("title", ""),
            )

            processed.append({"path": edited_path, "seo": seo, "meta": video_meta})
            log.info(f"  ✓ Edited → {edited_path}")

        except Exception as exc:
            log.error(f"  ✗ Error editing video '{video_meta['title']}': {exc}", exc_info=True)

    if not processed:
        log.error("No videos were edited successfully. Aborting upload step.")
        return

    # ── STEP 3: Upload ────────────────────────────────────────────────────────
    if dry_run:
        log.info("[3/3] DRY RUN — skipping uploads. Edited files:")
        for item in processed:
            log.info(f"  → {item['path']}")
        return

    uploader = SocialMediaUploader(config=cfg)
    log.info(f"[3/3] Uploading {len(processed)} video(s) to all platforms…")

    for item in processed:
        uploader.upload_all(
            video_path = item["path"],
            seo        = item["seo"],
        )

    # ── STEP 4: Telegram Notification ─────────────────────────────────────────
    if cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_CHAT_ID:
        log.info("[4/4] Sending final video to Telegram...")
        import requests
        for item in processed:
            video_path = item["path"]
            url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendVideo"
            try:
                with open(video_path, "rb") as f:
                    resp = requests.post(
                        url,
                        data={"chat_id": cfg.TELEGRAM_CHAT_ID, "caption": "🎥 New video ready: " + item['meta'].get('title', '')[:50]},
                        files={"video": f},
                        timeout=300
                    )
                resp.raise_for_status()
                log.info("  ✓ Video sent to Telegram!")
            except Exception as e:
                log.error(f"  ✗ Failed to send to Telegram: {e}")

    log.info("=" * 60)
    log.info("  PIPELINE COMPLETE")
    log.info("=" * 60)


# ── CLI entry-point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Video Automation Pipeline — scrape, edit, upload."
    )
    parser.add_argument("game",            help="Game name, e.g. 'One State RP'")
    parser.add_argument("--branding",      default="branding.png",   help="Path to branding image overlay")
    parser.add_argument("--landing-url",   default="https://example.com", help="Landing page URL for end-card")
    parser.add_argument("--max-videos",    type=int, default=5,       help="Max videos to process per run")
    parser.add_argument("--dry-run",       action="store_true",       help="Skip uploads; edit only")

    args = parser.parse_args()

    run_pipeline(
        game_name      = args.game,
        branding_image = args.branding,
        landing_url    = args.landing_url,
        max_videos     = args.max_videos,
        dry_run        = args.dry_run,
    )
