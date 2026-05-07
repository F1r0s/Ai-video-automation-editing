"""
scraper.py — Multi-platform vertical video scraper.

Searches for 9:16 short-form content across:
  - YouTube Shorts
  - TikTok
  - Instagram Reels
  - Facebook Reels
  - X (Twitter) videos

Uses yt-dlp as the unified backend for all platforms.
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
    """Search, filter, and download short vertical videos from multiple platforms."""

    def __init__(self, config: Config):
        self.cfg = config
        self._check_ytdlp()

    @staticmethod
    def _check_ytdlp():
        if not shutil.which("yt-dlp"):
            raise EnvironmentError("yt-dlp not found. Install: pip install yt-dlp")

    def _run_ytdlp_search(self, url: str, max_results: int) -> list[dict]:
        """Run yt-dlp to collect metadata (no download)."""
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

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
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
            log.warning(f"yt-dlp timed out for: {url[:80]}")
            return []
        except Exception as exc:
            log.error(f"yt-dlp error: {exc}")
            return []

    # ── Platform-specific searches ─────────────────────────────────────────────

    def _search_youtube_shorts(self, query: str, max_results: int) -> list[dict]:
        """Search YouTube specifically for Shorts (vertical, <60s)."""
        # Adding "#shorts" and "shorts" to target short-form vertical content
        searches = [
            f"ytsearch{max_results}:{query} shorts",
            f"ytsearch{max_results}:{query} #shorts gameplay",
        ]
        all_items = []
        for search_url in searches:
            items = self._run_ytdlp_search(search_url, max_results)
            all_items.extend(items)
            if len(all_items) >= max_results:
                break
        log.info(f"  YouTube Shorts: found {len(all_items)} result(s)")
        return all_items

    def _search_duckduckgo(self, d_query: str, max_results: int) -> list[dict]:
        """Search DuckDuckGo for URLs, then use yt-dlp to extract metadata."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            log.warning("duckduckgo_search not installed.")
            return []
            
        items = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(d_query, max_results=max_results))
                for r in results:
                    url = r.get("href")
                    if url:
                        meta_list = self._run_ytdlp_search(url, 1)
                        if meta_list:
                            items.extend(meta_list)
        except Exception as e:
            log.error(f"DDGS error: {e}")
        return items

    def _search_tiktok(self, query: str, max_results: int) -> list[dict]:
        """Search TikTok for vertical gameplay videos via DuckDuckGo."""
        items = self._search_duckduckgo(f"site:tiktok.com {query} gameplay", max_results)
        log.info(f"  TikTok: found {len(items)} result(s)")
        return items

    def _search_instagram_reels(self, query: str, max_results: int) -> list[dict]:
        """Search Instagram Reels via DuckDuckGo."""
        items = self._search_duckduckgo(f"site:instagram.com/reel/ {query} gameplay", max_results)
        log.info(f"  Instagram Reels: found {len(items)} result(s)")
        return items

    def _search_facebook_reels(self, query: str, max_results: int) -> list[dict]:
        """Search Facebook Reels via DuckDuckGo."""
        items = self._search_duckduckgo(f"site:facebook.com/reel/ {query} gameplay", max_results)
        log.info(f"  Facebook Reels: found {len(items)} result(s)")
        return items

    def _search_x(self, query: str, max_results: int) -> list[dict]:
        """Search X (Twitter) for video posts via DuckDuckGo."""
        items = self._search_duckduckgo(f"site:twitter.com {query} video", max_results)
        log.info(f"  X/Additional: found {len(items)} result(s)")
        return items

    # ── Public API ────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 15) -> list[dict]:
        """
        Search ALL platforms for vertical gameplay videos.
        Returns combined, de-duplicated list of video metadata.
        """
        log.info(f"Searching all platforms for: '{query}'")

        all_results = {}

        # 1. YouTube Shorts (best source, always works)
        yt_items = self._search_youtube_shorts(query, max_results)
        for item in yt_items:
            vid = item.get("id", item.get("url", ""))
            if vid:
                all_results[vid] = item

        # 2. TikTok (may need cookies in some regions)
        try:
            tt_items = self._search_tiktok(query, max_results)
            for item in tt_items:
                vid = item.get("id", item.get("url", ""))
                if vid and vid not in all_results:
                    all_results[vid] = item
        except Exception as e:
            log.warning(f"TikTok search failed: {e}")

        # 3. Instagram Reels (may need login cookies)
        try:
            ig_items = self._search_instagram_reels(query, max_results)
            for item in ig_items:
                vid = item.get("id", item.get("url", ""))
                if vid and vid not in all_results:
                    all_results[vid] = item
        except Exception as e:
            log.warning(f"Instagram search failed: {e}")

        # 4. Facebook Reels
        try:
            fb_items = self._search_facebook_reels(query, max_results)
            for item in fb_items:
                vid = item.get("id", item.get("url", ""))
                if vid and vid not in all_results:
                    all_results[vid] = item
        except Exception as e:
            log.warning(f"Facebook search failed: {e}")

        # 5. X / Extra YouTube results
        try:
            x_items = self._search_x(query, max(3, max_results // 3))
            for item in x_items:
                vid = item.get("id", item.get("url", ""))
                if vid and vid not in all_results:
                    all_results[vid] = item
        except Exception as e:
            log.warning(f"X search failed: {e}")

        results = list(all_results.values())[:max_results]
        log.info(f"Total unique results across all platforms: {len(results)}")
        return results

    def filter_eligible(self, candidates: list[dict]) -> list[dict]:
        """
        All videos are eligible — the editor handles trimming and cropping.
        We just pass everything through.
        """
        return candidates

    def download(self, video_meta: dict) -> Optional[Path]:
        """
        Download the best available format for a video.
        Returns the local path on success, None on failure.
        """
        video_url = video_meta.get("webpage_url") or video_meta.get("url", "")
        if not video_url:
            log.error("No URL in metadata; cannot download.")
            return None

        # Clean filename
        safe_title = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in video_meta.get("title", "video")
        )[:60]
        output_tmpl = str(self.cfg.RAW_DIR / f"{safe_title}_%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", output_tmpl,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--match-filter", "duration < 1800"
        ]
        if self.cfg.YT_DLP_COOKIES:
            cmd += ["--cookies", self.cfg.YT_DLP_COOKIES]
        cmd.append(video_url)

        log.info(f"  Downloading: {video_url[:80]}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        except subprocess.CalledProcessError as exc:
            log.error(f"  Download failed: {exc.stderr.decode('utf-8', errors='replace')[:300]}")
            return None
        except subprocess.TimeoutExpired:
            log.error("  Download timed out.")
            return None

        # Find the downloaded file
        video_id = video_meta.get("id", "")
        candidates = list(self.cfg.RAW_DIR.glob(f"*{video_id}*.mp4"))
        if candidates:
            return candidates[0]

        # Fallback: newest .mp4
        mp4s = sorted(self.cfg.RAW_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        return mp4s[-1] if mp4s else None
