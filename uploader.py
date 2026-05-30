"""
uploader.py — Multi-platform social media uploader.

Upload strategy per platform:
  ┌────────────┬──────────────────────────────────────────────────────┐
  │ Platform   │ Method                                               │
  ├────────────┼──────────────────────────────────────────────────────┤
  │ YouTube    │ Official YouTube Data API v3 (OAuth 2.0)            │
  │ TikTok     │ TikTok Content Posting API (Business/Creator)       │
  │ Instagram  │ Instagram Graph API (via Facebook)                  │
  │ Facebook   │ Facebook Graph API                                  │
  │ X (Twitter)│ X API v2 (media upload + tweet)                     │
  └────────────┴──────────────────────────────────────────────────────┘

For platforms that block API uploads or require browser login,
a Playwright-based fallback is included.
"""

import logging
import os
import time
from pathlib import Path

import requests
from config import Config
from seo    import SEOPackage

log = logging.getLogger("uploader")


# ═════════════════════════════════════════════════════════════════════════════
#  YOUTUBE
# ═════════════════════════════════════════════════════════════════════════════

def upload_youtube(video_path: Path, seo: SEOPackage, cfg: Config, is_private: bool = False) -> bool:
    """
    Upload a video to YouTube Shorts via YouTube Data API v3.

    Prerequisites:
      1. Create a project in Google Cloud Console.
      2. Enable "YouTube Data API v3".
      3. Create OAuth 2.0 credentials → download as youtube_client_secret.json.
      4. On first run this will open a browser for OAuth consent.
    """
    try:
        from googleapiclient.discovery     import build
        from googleapiclient.http          import MediaFileUpload
        from google_auth_oauthlib.flow     import InstalledAppFlow
        from google.oauth2.credentials     import Credentials
        import pickle, json

        SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
        token_file  = Path(cfg.YOUTUBE_TOKEN_FILE)
        secret_file = Path(cfg.YOUTUBE_CLIENT_SECRET_FILE)

        if not secret_file.exists():
            log.warning("YouTube client secret not found; skipping YouTube upload.")
            return False

        creds = None
        if token_file.exists():
            with open(token_file, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                flow  = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_file, "wb") as f:
                import pickle; pickle.dump(creds, f)

        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title":       seo.title[:100],
                "description": seo.description[:5000],
                "tags":        seo.tags[:500],                    # max 500 chars total
                "categoryId":  "20",                              # Gaming
            },
            "status": {
                "privacyStatus":         "private" if is_private else "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True,
                                mimetype="video/mp4")
        req   = youtube.videos().insert(part="snippet,status", body=body,
                                        media_body=media)

        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                log.info(f"  YouTube upload {int(status.progress() * 100)}%")

        log.info(f"  ✓ YouTube uploaded: https://youtu.be/{response['id']}")
        return True

    except Exception as exc:
        log.error(f"  ✗ YouTube upload failed: {exc}", exc_info=True)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  TIKTOK
# ═════════════════════════════════════════════════════════════════════════════

def upload_tiktok(video_path: Path, seo: SEOPackage, cfg: Config, is_private: bool = False) -> bool:
    """
    Upload via TikTok Content Posting API.
    Docs: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
    Requires: TikTok Developer App → Content Posting API access granted.
    """
    token = cfg.TIKTOK_ACCESS_TOKEN
    if not token:
        log.warning("  TikTok access token not set; skipping.")
        return False

    try:
        # Step 1: Initialise upload
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        headers  = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }
        file_size = video_path.stat().st_size
        caption   = (
            f"{seo.title}\n\n{seo.hashtag_string()}"
        )[:2200]

        init_payload = {
            "post_info": {
                "title":            caption,
                "privacy_level":    "SELF_ONLY" if is_private else "PUBLIC_TO_EVERYONE",
                "disable_duet":     False,
                "disable_comment":  False,
                "disable_stitch":   False,
            },
            "source_info": {
                "source":     "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        }

        resp = requests.post(init_url, json=init_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data       = resp.json()["data"]
        publish_id = data["publish_id"]
        upload_url = data["upload_url"]

        # Step 2: Upload file
        with open(video_path, "rb") as f:
            video_bytes = f.read()

        upload_headers = {
            "Content-Range":  f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type":   "video/mp4",
            "Content-Length": str(file_size),
        }
        up_resp = requests.put(upload_url, data=video_bytes,
                               headers=upload_headers, timeout=120)
        up_resp.raise_for_status()

        log.info(f"  ✓ TikTok uploaded — publish_id: {publish_id}")
        return True

    except Exception as exc:
        log.error(f"  ✗ TikTok upload failed: {exc}", exc_info=True)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  INSTAGRAM (Graph API — Reels)
# ═════════════════════════════════════════════════════════════════════════════

def upload_instagram(video_path: Path, seo: SEOPackage, cfg: Config,
                     public_video_url: str = "") -> bool:
    """
    Upload a Reel via Instagram Graph API.

    ⚠️  Instagram Graph API requires the video to be hosted at a publicly
        accessible URL (not a local file). You must upload the edited video to
        cloud storage (e.g., Google Cloud Storage / S3) first and pass the
        public URL here, OR use the resumable upload endpoint.

    For simplicity, this implementation uploads via Playwright as a fallback
    if no public URL is given.
    """
    token   = cfg.INSTAGRAM_ACCESS_TOKEN
    user_id = cfg.INSTAGRAM_USER_ID

    if not token or not user_id:
        log.warning("  Instagram credentials not set; skipping.")
        return False

    if not public_video_url:
        log.warning("  No public video URL for Instagram Graph API; using Playwright fallback.")
        return _instagram_playwright_fallback(video_path, seo, cfg)

    try:
        base  = f"https://graph.facebook.com/v19.0/{user_id}"
        cap   = f"{seo.description}\n{seo.hashtag_string()}"[:2200]

        # Step 1: Create container
        r = requests.post(f"{base}/media", params={
            "media_type":  "REELS",
            "video_url":   public_video_url,
            "caption":     cap,
            "access_token": token,
        }, timeout=30)
        r.raise_for_status()
        container_id = r.json()["id"]

        # Step 2: Poll until ready
        for _ in range(30):
            time.sleep(5)
            status_r = requests.get(
                f"https://graph.facebook.com/v19.0/{container_id}",
                params={"fields": "status_code", "access_token": token},
            )
            if status_r.json().get("status_code") == "FINISHED":
                break
        else:
            log.warning("  Instagram container not ready after 150 s.")
            return False

        # Step 3: Publish
        pub_r = requests.post(f"{base}/media_publish", params={
            "creation_id": container_id,
            "access_token": token,
        }, timeout=30)
        pub_r.raise_for_status()
        log.info(f"  ✓ Instagram Reel published: {pub_r.json().get('id')}")
        return True

    except Exception as exc:
        log.error(f"  ✗ Instagram upload failed: {exc}", exc_info=True)
        return False


def _instagram_playwright_fallback(video_path: Path, seo: SEOPackage, cfg: Config) -> bool:
    """Browser automation fallback for Instagram when no public URL exists."""
    try:
        from playwright.sync_api import sync_playwright

        ig_user = os.getenv("INSTAGRAM_USERNAME", "")
        ig_pass = os.getenv("INSTAGRAM_PASSWORD", "")
        if not ig_user or not ig_pass:
            log.warning("  Instagram Playwright: INSTAGRAM_USERNAME/PASSWORD not set.")
            return False

        log.info("  Starting Playwright for Instagram…")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page()

            # Login
            page.goto("https://www.instagram.com/accounts/login/")
            page.fill('input[name="username"]', ig_user)
            page.fill('input[name="password"]', ig_pass)
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)

            # Navigate to new post
            page.goto("https://www.instagram.com/create/reels/")
            page.wait_for_timeout(3000)

            # Upload file
            file_input = page.query_selector('input[type="file"]')
            if file_input:
                file_input.set_input_files(str(video_path))
                page.wait_for_timeout(5000)

            # Add caption
            caption_box = page.query_selector('[aria-label="Write a caption..."]')
            if caption_box:
                caption_box.click()
                cap = f"{seo.description}\n{seo.hashtag_string()}"[:2200]
                caption_box.type(cap)
                page.wait_for_timeout(1000)

            # Share
            share_btn = page.query_selector('button:has-text("Share")')
            if share_btn:
                share_btn.click()
                page.wait_for_timeout(8000)
                log.info("  ✓ Instagram Reel shared via Playwright.")
            else:
                log.warning("  Share button not found.")

            browser.close()
        return True

    except Exception as exc:
        log.error(f"  ✗ Instagram Playwright fallback failed: {exc}", exc_info=True)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  FACEBOOK
# ═════════════════════════════════════════════════════════════════════════════

def upload_facebook(video_path: Path, seo: SEOPackage, cfg: Config) -> bool:
    """
    Upload a video to a Facebook Page via Graph API.
    Requires: pages_manage_posts, publish_video permissions.
    """
    token   = cfg.FACEBOOK_ACCESS_TOKEN
    page_id = cfg.FACEBOOK_PAGE_ID

    if not token or not page_id:
        log.warning("  Facebook credentials not set; skipping.")
        return False

    try:
        url      = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
        desc     = f"{seo.description}\n{seo.hashtag_string()}"[:64000]

        with open(video_path, "rb") as f:
            resp = requests.post(
                url,
                data={
                    "description":    desc,
                    "title":          seo.title[:254],
                    "access_token":   token,
                    "published":      "true",
                },
                files={"source": ("video.mp4", f, "video/mp4")},
                timeout=300,
            )
        resp.raise_for_status()
        log.info(f"  ✓ Facebook uploaded: {resp.json().get('id')}")
        return True

    except Exception as exc:
        log.error(f"  ✗ Facebook upload failed: {exc}", exc_info=True)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  X (TWITTER)
# ═════════════════════════════════════════════════════════════════════════════

def upload_x(video_path: Path, seo: SEOPackage, cfg: Config) -> bool:
    """
    Upload a video + tweet to X using Tweepy (X API v2 / v1.1 media upload).

    v1.1 is still required for media uploads even in X API v2.
    """
    if not all([cfg.X_API_KEY, cfg.X_API_SECRET,
                cfg.X_ACCESS_TOKEN, cfg.X_ACCESS_TOKEN_SECRET]):
        log.warning("  X credentials not fully set; skipping.")
        return False

    try:
        import tweepy

        # Authenticate
        auth = tweepy.OAuth1UserHandler(
            cfg.X_API_KEY, cfg.X_API_SECRET,
            cfg.X_ACCESS_TOKEN, cfg.X_ACCESS_TOKEN_SECRET,
        )
        api_v1 = tweepy.API(auth)

        # Upload media (chunked upload via v1.1)
        log.info("  Uploading video to X media…")
        media = api_v1.media_upload(
            filename   = str(video_path),
            media_type = "video/mp4",
            chunked    = True,
            wait_for_async_finalize=True,
        )
        media_id = media.media_id_string

        # Post tweet via v2
        client = tweepy.Client(
            consumer_key        = cfg.X_API_KEY,
            consumer_secret     = cfg.X_API_SECRET,
            access_token        = cfg.X_ACCESS_TOKEN,
            access_token_secret = cfg.X_ACCESS_TOKEN_SECRET,
        )
        tweet_text = seo.title  # already ≤280 chars from SEO generator
        client.create_tweet(text=tweet_text, media_ids=[media_id])

        log.info(f"  ✓ X (Twitter) tweet posted with video.")
        return True

    except Exception as exc:
        log.error(f"  ✗ X upload failed: {exc}", exc_info=True)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═════════════════════════════════════════════════════════════════════════════

class SocialMediaUploader:
    """Uploads one video to all configured platforms."""

    def __init__(self, config: Config):
        self.cfg = config

    def upload_all(self, video_path: Path, seo: dict[str, SEOPackage], is_private: bool = False) -> dict[str, bool]:
        """
        Upload video to every platform.
        Returns a dict of {platform: success_bool}.
        """
        results = {}

        log.info(f"  Uploading: {video_path.name}")

        results["youtube"]   = upload_youtube(  video_path, seo["youtube"],   self.cfg, is_private)
        results["tiktok"]    = upload_tiktok(   video_path, seo["tiktok"],    self.cfg, is_private)
        results["instagram"] = upload_instagram(video_path, seo["instagram"], self.cfg)
        results["facebook"]  = upload_facebook( video_path, seo["facebook"],  self.cfg)
        results["x"]         = upload_x(        video_path, seo["x"],         self.cfg)

        successes = [p for p, ok in results.items() if ok]
        failures  = [p for p, ok in results.items() if not ok]

        log.info(f"  Upload results → ✓ {successes} | ✗ {failures}")
        return results
