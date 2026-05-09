"""
editor.py — Video editing pipeline.

Steps (in order):
  1. Trim to ≤30 seconds
  2. Force 9:16 (1080×1920) aspect ratio via crop + pad
  3. Generate AI voiceover with ElevenLabs (fallback: gTTS)
  4. Transcribe audio → burned-in subtitles with Whisper
  5. Overlay branding image at the end (last 3 seconds)
  6. Render QR / text end-card with landing page URL
  7. Export as H.264/AAC MP4

Dependencies: moviepy, pillow, openai-whisper, elevenlabs, gtts, requests
"""

import logging
import os
import textwrap
import requests
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageColor
# Monkey-patch for MoviePy 1.0.3 compatibility with Pillow 10+
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    ImageClip, TextClip, concatenate_videoclips,
)
from moviepy.video.fx.all import crop

try:
    import whisper                      # openai-whisper
    _HAS_WHISPER = True
except Exception:
    whisper = None
    _HAS_WHISPER = False
from gtts import gTTS               # fallback TTS

from config import Config

log = logging.getLogger("editor")

# ── Constants ─────────────────────────────────────────────────────────────────
FONT_PATH    = Path("assets/Montserrat-Bold.ttf")   # bundled font
BRANDING_DUR = 3                                     # seconds of branding at end


class VideoEditor:
    """Full editing pipeline for a single short-form vertical video."""

    def __init__(self, config: Config):
        self.cfg = config
        self._whisper_model: Optional[object] = None   # lazy-loaded

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_whisper(self):
        if not _HAS_WHISPER:
            log.info("  Whisper not installed; skipping transcription.")
            return None

        if self._whisper_model is None:
            log.info("  Loading Whisper model (small)…")
            self._whisper_model = whisper.load_model("small")
        return self._whisper_model

    # ── TTS ───────────────────────────────────────────────────────────────────

    def _elevenlabs_tts(self, text: str, out_path: Path) -> bool:
        """Generate speech using ElevenLabs API. Returns True on success."""
        api_key  = self.cfg.ELEVENLABS_API_KEY
        voice_id = self.cfg.ELEVENLABS_VOICE_ID
        if not api_key:
            return False

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key":    api_key,
            "Content-Type":  "application/json",
        }
        payload = {
            "text":           text,
            "model_id":       "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
            log.info(f"  ElevenLabs TTS → {out_path}")
            return True
        except Exception as exc:
            log.warning(f"  ElevenLabs failed ({exc}); falling back to gTTS.")
            return False

    def _gtts_fallback(self, text: str, out_path: Path):
        """Generate speech using Google TTS (free, no API key)."""
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(str(out_path))
        log.info(f"  gTTS → {out_path}")

    def _generate_voiceover(self, game_name: str) -> Path:
        """Create a hook-style voiceover MP3 for the given game."""
        hook = (
            f"Wait — are you playing {game_name} without this mod? "
            f"This changes EVERYTHING. Watch till the end and grab the link below!"
        )
        out = Path(tempfile.mktemp(suffix=".mp3"))
        if not self._elevenlabs_tts(hook, out):
            self._gtts_fallback(hook, out)
        return out

    # ── Whisper captions ──────────────────────────────────────────────────────

    def _transcribe(self, video_path: Path) -> list[dict]:
        """
        Transcribe audio using Whisper.
        Returns list of {start, end, text} dicts.
        """
        model = self._load_whisper()
        if model is None:
            return []

        result = model.transcribe(str(video_path), language="en", fp16=False)
        return result.get("segments", [])

    def _make_subtitle_clips(self, segments: list[dict], video_w: int, video_h: int, caption_color: str = "white", caption_pos: float = 0.58) -> list:
        """Render each subtitle segment as a TextClip."""
        clips = []
        def resolve_color(value: str) -> tuple[int, int, int]:
            try:
                return ImageColor.getrgb(value)
            except Exception:
                palette = {
                    "yellow": (255, 215, 0),
                    "white": (255, 255, 255),
                    "green": (0, 230, 118),
                    "cyan": (0, 212, 255),
                }
                return palette.get(str(value).lower(), (255, 255, 255))

        subtitle_rgb = resolve_color(caption_color)
        for seg in segments:
            txt   = seg["text"].strip()
            start = seg["start"]
            end   = seg["end"]
            dur   = end - start
            if not txt or dur <= 0:
                continue

            # Wrap long lines
            wrapped = "\n".join(textwrap.wrap(txt, width=18))

            try:
                import numpy as np

                font_size = max(64, int(video_h * 0.050))
                font = ImageFont.truetype(str(FONT_PATH), font_size) if FONT_PATH.exists() else ImageFont.load_default()
                stroke_width = max(4, font_size // 18)
                box_w = min(video_w - 80, 1040)
                box_h = 260
                img = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)
                bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=10, stroke_width=stroke_width)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                pad_x = 38
                pad_y = 24
                bg_left = max(0, (box_w - tw) // 2 - pad_x)
                bg_top = max(0, (box_h - th) // 2 - pad_y)
                bg_right = min(box_w, (box_w + tw) // 2 + pad_x)
                bg_bottom = min(box_h, (box_h + th) // 2 + pad_y)
                draw.rounded_rectangle([bg_left, bg_top, bg_right, bg_bottom], radius=28, fill=(0, 0, 0, 185))
                draw.multiline_text(
                    ((box_w - tw) / 2, (box_h - th) / 2 - 2),
                    wrapped,
                    font=font,
                    fill=subtitle_rgb + (255,),
                    align="center",
                    spacing=10,
                    stroke_width=stroke_width,
                    stroke_fill=(0, 0, 0, 255),
                )
                clip = ImageClip(np.array(img)).set_start(start).set_duration(dur).set_position(("center", int(video_h * max(0.50, min(caption_pos, 0.66)))))
                clips.append(clip)
            except Exception as exc:
                log.warning(f"  Subtitle clip error: {exc}")

        return clips

    # ── Branding overlay ──────────────────────────────────────────────────────

    def _make_branding_clip(self, branding_image: str, landing_url: str,
                            video_w: int, video_h: int, duration: float) -> ImageClip:
        """
        Create a semi-transparent branding frame:
          - branding image centred
          - landing URL text below it
        """
        # Base: black semi-transparent background
        bg = Image.new("RGBA", (video_w, video_h), (0, 0, 0, 180))
        draw = ImageDraw.Draw(bg)

        # Load branding image
        brand_path = Path(branding_image)
        if brand_path.exists():
            brand_img = Image.open(brand_path).convert("RGBA")
            # Scale to 60% of video width
            scale    = (video_w * 0.6) / brand_img.width
            new_size = (int(brand_img.width * scale), int(brand_img.height * scale))
            brand_img = brand_img.resize(new_size, Image.LANCZOS)
            bx = (video_w - new_size[0]) // 2
            by = (video_h - new_size[1]) // 2 - 80
            bg.paste(brand_img, (bx, by), brand_img)

        # URL text
        try:
            font = ImageFont.truetype(str(FONT_PATH), 36) if FONT_PATH.exists() \
                   else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        url_text = landing_url
        bbox = draw.textbbox((0, 0), url_text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((video_w - tw) // 2, video_h - 200), url_text,
                  fill=(0, 200, 255, 255), font=font)
        draw.text(((video_w - 400) // 2, video_h - 260),
                  "👇 Get the MOD link below 👇",
                  fill=(255, 255, 255, 220), font=font)

        # Save temp PNG
        tmp = Path(tempfile.mktemp(suffix=".png"))
        bg.save(str(tmp))

        return (
            ImageClip(str(tmp))
            .set_duration(duration)
            .set_opacity(0.92)
        )

    # ── Core pipeline ─────────────────────────────────────────────────────────

    def _force_9_16(self, clip: VideoFileClip) -> VideoFileClip:
        """Crop/pad clip to exactly 9:16 (1080×1920)."""
        tw, th = self.cfg.TARGET_WIDTH, self.cfg.TARGET_HEIGHT
        w, h   = clip.size

        # Calculate target crop dimensions maintaining 9:16
        if w / h > 9 / 16:
            # Too wide — crop sides
            new_w = int(h * 9 / 16)
            clip  = crop(clip, x_center=w / 2, width=new_w)
        elif w / h < 9 / 16:
            # Too tall — crop top/bottom
            new_h = int(w * 16 / 9)
            clip  = crop(clip, y_center=h / 2, height=new_h)

        # Resize to target
        clip = clip.resize((tw, th))
        return clip

    def process(self, input_path: Path, branding_image: str,
                landing_url: str, game_name: str, caption_color: str = "white", caption_pos: float = 0.58) -> Path:
        """
        Full editing pipeline for one video.
        Returns path to the final MP4.
        """
        log.info(f"  Loading: {input_path}")
        clip = VideoFileClip(str(input_path))

        # 1. Trim ─────────────────────────────────────────────────────────────
        if clip.duration > self.cfg.MAX_DURATION:
            log.info(f"  Trimming {clip.duration:.1f}s → {self.cfg.MAX_DURATION}s")
            clip = clip.subclip(0, self.cfg.MAX_DURATION)

        # 2. Force 9:16 ───────────────────────────────────────────────────────
        clip = self._force_9_16(clip)
        tw, th = clip.size

        # 3. Voiceover ────────────────────────────────────────────────────────
        vo_path = self._generate_voiceover(game_name)
        vo_clip = AudioFileClip(str(vo_path))

        # Mix original audio (lower) + voiceover
        try:
            from moviepy.audio.fx.all import volumex, audio_fadein, audio_fadeout
            orig_audio = clip.audio.fx(volumex, 0.3) if clip.audio else None
            vo_audio   = vo_clip.fx(volumex, 1.0)

            if orig_audio:
                from moviepy.editor import CompositeAudioClip
                mixed = CompositeAudioClip([orig_audio, vo_audio])
            else:
                mixed = vo_audio

            clip = clip.set_audio(mixed)
        except Exception as exc:
            log.warning(f"  Audio mix error: {exc} — using voiceover only")
            clip = clip.set_audio(vo_clip)

        # 4. Subtitles (Whisper transcription) ────────────────────────────────
        try:
            segments = self._transcribe(input_path)
            sub_clips = self._make_subtitle_clips(segments, tw, th, caption_color=caption_color, caption_pos=caption_pos)
            if sub_clips:
                clip = CompositeVideoClip([clip] + sub_clips)
        except Exception as exc:
            log.warning(f"  Subtitle generation failed: {exc}")

        # 5. Branding overlay (last BRANDING_DUR seconds) ─────────────────────
        try:
            brand_start = max(0, clip.duration - BRANDING_DUR)
            brand_dur   = clip.duration - brand_start
            brand_clip  = (
                self._make_branding_clip(branding_image, landing_url, tw, th, brand_dur)
                .set_start(brand_start)
            )
            clip = CompositeVideoClip([clip, brand_clip])
        except Exception as exc:
            log.warning(f"  Branding overlay failed: {exc}")

        # 6. Export ───────────────────────────────────────────────────────────
        stem      = Path(input_path).stem
        out_path  = self.cfg.EDITED_DIR / f"{stem}_edited.mp4"

        log.info(f"  Rendering → {out_path}")
        clip.write_videofile(
            str(out_path),
            codec          = "libx264",
            audio_codec    = "aac",
            fps            = 30,
            preset         = "fast",
            threads        = 4,
            logger         = None,           # suppress verbose ffmpeg
        )

        # Cleanup temp files
        try:
            vo_path.unlink(missing_ok=True)
        except Exception:
            pass

        clip.close()
        return out_path
