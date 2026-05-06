"""
scraper.py — Video discovery, filtering, and downloading.

Backends used:
  • yt-dlp  — YouTube (primary), plus many other sites
  • TikTok  — via yt-dlp (no API key needed for public content)

Filtering criteria:
  • Duration  ≤ 30 seconds
  • Aspect ratio 9:16 (portrait / vertical)
"""

import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from config import Config

log = logging.getLogger("scraper")


class VideoScraper:
    """Search for, filter, and download short vertical videos."""

    def __init__(self, config: Config):
        self.cfg = config
        self._check_ytdlp()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _check_ytdlp():
        if not shutil.which("yt-dlp"):
            raise EnvironmentError(
                "yt-dlp not found. Install it: pip install yt-dlp"
            )

    def _ytdlp_search(self, query: str, source: str, max_results: int) -> list[dict]:
        """Run yt-dlp to collect metadata only (no download)."""
        if source == "youtube":
            url = f"ytsearch{max_results}:{query}"
        elif source == "tiktok":
            # TikTok search via yt-dlp; requires cookies for some regions
            url = f"https://www.tiktok.com/search?q={query.replace(' ', '+')}"
        else:
            url = f"ytsearch{max_results}:{query}"

        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--flat-playlist",
            "--max-downloads", str(max_results),
        ]

        if self.cfg.YT_DLP_COOKIES:
            cmd += ["--cookies", self.cfg.YT_DLP_COOKIES]

        cmd.append(url)

        log.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            items = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return items
        except subprocess.TimeoutExpired:
            log.warning(f"yt-dlp timed out for source={source}")
            return []
        except Exception as exc:
            log.error(f"yt-dlp error: {exc}")
            return []

    def _get_full_metadata(self, video_url: str) -> Optional[dict]:
        """Fetch complete metadata (including duration + resolution) for one URL."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
        ]
        if self.cfg.YT_DLP_COOKIES:
            cmd += ["--cookies", self.cfg.YT_DLP_COOKIES]
        cmd.append(video_url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return None
            return json.loads(result.stdout.strip())
        except Exception as exc:
            log.warning(f"Metadata fetch failed for {video_url}: {exc}")
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 15) -> list[dict]:
        """
        Search YouTube and TikTok for 'query'.
        Returns a list of video metadata dicts.
        """
        log.info(f"Searching YouTube for: '{query}'")
        yt_results  = self._ytdlp_search(query, "youtube", max_results)
        log.info(f"  → {len(yt_results)} YouTube results")

        # Combine and de-duplicate by id
        all_results = {v.get("id", v.get("url", str(i))): v
                       for i, v in enumerate(yt_results)}

        return list(all_results.values())[:max_results]

    def filter_eligible(self, candidates: list[dict]) -> list[dict]:
        """
        Keep only videos that are:
          • ≤ MAX_DURATION seconds
          • 9:16 aspect ratio (width < height, ~0.5625 ratio)
        """
        eligible = []

        for item in candidates:
            video_url = item.get("webpage_url") or item.get("url", "")
            if not video_url:
                continue

            # Try to use pre-loaded metadata first; fall back to full fetch
            duration = item.get("duration")
            width    = item.get("width")
            height   = item.get("height")

            # If resolution is missing, fetch full metadata
            if duration is None or width is None or height is None:
                meta = self._get_full_metadata(video_url)
                if not meta:
                    continue
                duration = meta.get("duration", 0)
                width    = meta.get("width", 0)
                height   = meta.get("height", 0)
                item.update(meta)   # enrich in-place

            # ── Duration check ────────────────────────────────────────────────
            if not duration or duration > self.cfg.MAX_DURATION:
                log.debug(f"  SKIP (duration={duration}s): {item.get('title','?')[:60]}")
                continue

            # ── Aspect ratio check ────────────────────────────────────────────
            if not width or not height or width >= height:
                log.debug(f"  SKIP (ratio={width}x{height}): {item.get('title','?')[:60]}")
                continue

            ratio = width / height                 # should be ~0.5625 for 9:16
            if not (0.52 <= ratio <= 0.60):        # small tolerance
                log.debug(f"  SKIP (ratio={ratio:.3f}): {item.get('title','?')[:60]}")
                continue

            log.info(f"  ✓ ELIGIBLE ({duration}s, {width}x{height}): {item.get('title','?')[:60]}")
            eligible.append(item)

        return eligible

    def download(self, video_meta: dict) -> Optional[Path]:
        """
        Download the best available format for a video.
        Returns the local path on success, None on failure.
        """
        video_url = video_meta.get("webpage_url") or video_meta.get("url", "")
        if not video_url:
            log.error("No URL in video metadata; cannot download.")
            return None

        safe_title = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in video_meta.get("title", "video")
        )[:60]
        output_tmpl = str(self.cfg.RAW_DIR / f"{safe_title}_%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", output_tmpl,
            "--merge-output-format", "mp4",
            "--no-playlist",
        ]
        if self.cfg.YT_DLP_COOKIES:
            cmd += ["--cookies", self.cfg.YT_DLP_COOKIES]
        cmd.append(video_url)

        log.info(f"  Downloading: {video_url}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            log.error(f"  Download failed: {exc.stderr.decode()[:300]}")
            return None
        except subprocess.TimeoutExpired:
            log.error("  Download timed out.")
            return None

        # Find the actual downloaded file
        video_id  = video_meta.get("id", "")
        candidates = list(self.cfg.RAW_DIR.glob(f"*{video_id}*.mp4"))
        if candidates:
            return candidates[0]

        # Fallback: newest .mp4
        mp4s = sorted(self.cfg.RAW_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        return mp4s[-1] if mp4s else None
