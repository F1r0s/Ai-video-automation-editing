"""
video_processor.py — CPA Promo Video Processing Engine

Pipeline per video:
  1. Load original video
  2. Strip existing audio voiceover
  3. Trim to 30s max, force 9:16 (1080x1920)
  4. Generate new ElevenLabs voiceover (FULL 30 seconds)
  5. Transcribe new voiceover -> burn-in subtitles
  6. Overlay CPA link bar at the bottom (first 25 seconds)
  7. Channel screenshot FULL SCREEN (last 5 seconds)
     - Red circle on "Subscribe" button
     - Red circle on the link with arrow text
     - Disappears when video ends
  8. Export as _promo.mp4
"""

import logging
import os
import textwrap
import tempfile
import math
from pathlib import Path
from typing import Optional, Callable

import requests
from PIL import Image, ImageDraw, ImageFont
# Monkey-patch for MoviePy 1.0.3 + Pillow 10+
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    ImageClip, TextClip, ColorClip, concatenate_audioclips,
)
from moviepy.video.fx.all import crop

from gtts import gTTS

log = logging.getLogger("processor")

# Constants
TARGET_W = 1080
TARGET_H = 1920
MAX_DUR  = 30
FONT_PATH = Path("assets/Montserrat-Bold.ttf")


class VideoProcessor:
    """Processes a single video into a CPA promo clip."""

    def __init__(self, elevenlabs_key: str = "", elevenlabs_voice_id: str = ""):
        self.el_key      = elevenlabs_key
        self.el_voice_id = elevenlabs_voice_id or "EXAVITQu4vr4xnSDxMaL"
        self._whisper     = None

    # ── TTS ────────────────────────────────────────────────────────────────────

    def _elevenlabs_tts(self, text: str, out: Path) -> bool:
        if not self.el_key:
            return False
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.el_voice_id}"
        headers = {"xi-api-key": self.el_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            out.write_bytes(r.content)
            return True
        except Exception as e:
            log.warning(f"ElevenLabs failed: {e}")
            return False

    def _gtts_fallback(self, text: str, out: Path) -> bool:
        try:
            log.info("Using gTTS fallback for voiceover...")
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(str(out))
            return True
        except Exception as e:
            log.error(f"gTTS fallback failed: {e}")
            return False

    def _make_voiceover(self, game_name: str) -> Path:
        """
        Generate a LONG voiceover script that fills ~30 seconds.
        """
        hook = (
            f"Wait. Are you still playing {game_name} the normal way? "
            f"You are missing out on the best mod of twenty twenty five. "
            f"This mod gives you unlimited money, unlimited gems, "
            f"and every single resource completely for free. "
            f"No root needed. No jailbreak. Works on Android and iPhone. "
            f"And the best part? There is absolutely no ban. "
            f"I tested this myself and it works perfectly. "
            f"The link is right here on screen. "
            f"Tap it right now before they patch it. "
            f"Also make sure to subscribe to my channel "
            f"so you never miss the next working mod. "
            f"Go ahead. Download it now. You will not regret it."
        )
        out = Path(tempfile.mktemp(suffix=".mp3"))
        
        # Try ElevenLabs first
        success = self._elevenlabs_tts(hook, out)
        
        # Try gTTS fallback
        if not success:
            success = self._gtts_fallback(hook, out)
            
        # If BOTH fail (network error, rate limit, etc), create a silent audio file so it doesn't crash!
        if not success or not out.exists():
            log.warning("ALL TTS FAILED! Using 1-second silent audio to prevent crash.")
            from moviepy.editor import AudioClip
            silent = AudioClip(lambda t: [0,0], duration=5, fps=44100)
            silent.write_audiofile(str(out), fps=44100, logger=None)
            
        return out

    # ── Whisper subtitles ──────────────────────────────────────────────────────

    def _load_whisper(self):
        if self._whisper is None:
            import whisper
            self._whisper = whisper.load_model("small")
        return self._whisper

    def _transcribe(self, audio_path: Path) -> list[dict]:
        model = self._load_whisper()
        result = model.transcribe(str(audio_path), language="en", fp16=False)
        return result.get("segments", [])

    def _make_subtitle_clips(self, segments: list[dict], w: int, h: int, color: str, pos_y: float) -> list:
        clips = []
        try:
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            from moviepy.editor import ImageClip
            
            font_path = str(FONT_PATH) if FONT_PATH.exists() else "arial.ttf"
            try:
                font = ImageFont.truetype(font_path, 54)
            except IOError:
                font = ImageFont.load_default()

            for seg in segments:
                txt = seg["text"].strip()
                start, end = seg["start"], seg["end"]
                dur = end - start
                if not txt or dur <= 0:
                    continue
                
                wrapped = "\n".join(textwrap.wrap(txt, width=28))
                
                # Create transparent PIL image
                img = Image.new('RGBA', (w - 80, 200), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)
                
                # Calculate text size using textbbox for newer PIL versions
                bbox = draw.textbbox((0, 0), wrapped, font=font, align="center")
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                
                # Center text
                tx = ((w - 80) - tw) / 2
                ty = (200 - th) / 2
                
                # Draw text with stroke (black border)
                stroke_width = 3
                draw.text((tx, ty), wrapped, font=font, fill=color, align="center", 
                          stroke_width=stroke_width, stroke_fill="black")
                
                # Convert to numpy array
                img_np = np.array(img)
                
                # Create ImageClip
                clip = (
                    ImageClip(img_np)
                    .set_start(start)
                    .set_duration(dur)
                    .set_position(("center", int(h * pos_y)))
                )
                clips.append(clip)
        except Exception as e:
            log.warning(f"Failed to create PIL subtitle clip: {e}")
        return clips

    # ── CPA Link Bar (shown during gameplay, first 25 seconds) ─────────────────

    def _make_cpa_bar(self, landing_url: str, duration: float) -> ImageClip:
        """Semi-transparent bar at the bottom with the CPA link."""
        bar_h = 130
        img = Image.new("RGBA", (TARGET_W, bar_h), (0, 0, 0, 210))
        draw = ImageDraw.Draw(img)

        try:
            font_big   = ImageFont.truetype(str(FONT_PATH), 34) if FONT_PATH.exists() else ImageFont.load_default()
            font_small = ImageFont.truetype(str(FONT_PATH), 26) if FONT_PATH.exists() else ImageFont.load_default()
        except Exception:
            font_big = font_small = ImageFont.load_default()

        # CTA text
        cta = "Download FREE MOD Now!"
        bbox = draw.textbbox((0, 0), cta, font=font_big)
        tw = bbox[2] - bbox[0]
        draw.text(((TARGET_W - tw) // 2, 15), cta, fill=(0, 255, 100, 255), font=font_big)

        # URL text
        bbox2 = draw.textbbox((0, 0), landing_url, font=font_small)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((TARGET_W - tw2) // 2, 70), landing_url, fill=(100, 200, 255, 255), font=font_small)

        tmp = Path(tempfile.mktemp(suffix=".png"))
        img.save(str(tmp))

        return (
            ImageClip(str(tmp))
            .set_duration(duration)
            .set_position(("center", TARGET_H - bar_h))
            .set_opacity(0.95)
        )

    def _make_channel_overlay(self, screenshot_path: str, landing_url: str,
                               duration: float, overlay_data: list = None,
                               layout: dict = None) -> Optional[CompositeVideoClip]:
        """Animated channel overlay with user-positioned screenshot, link, and stickers."""
        if not screenshot_path or not Path(screenshot_path).exists():
            return None

        import numpy as np
        from moviepy.editor import VideoClip

        lay = layout or {}
        ss_ox = lay.get("ss_ox", 0)
        ss_oy = lay.get("ss_oy", 0)
        ss_zoom = lay.get("ss_zoom", 1.0)
        link_x = lay.get("link_x", 0.5)
        link_y = lay.get("link_y", 0.96)
        link_scale = lay.get("link_scale", 1.0)

        # Pre-render screenshot at correct position
        ss_img = Image.open(screenshot_path).convert("RGBA")
        ss_img = ss_img.resize((int(ss_img.width * ss_zoom), int(ss_img.height * ss_zoom)), Image.LANCZOS)
        scale = TARGET_W / ss_img.width
        nw, nh = TARGET_W, int(ss_img.height * scale)
        if nh > TARGET_H - 120:
            scale = (TARGET_H - 120) / ss_img.height
            nw, nh = int(ss_img.width * scale), int(ss_img.height * scale)
        ss_img = ss_img.resize((nw, nh), Image.LANCZOS)
        ss_px = (TARGET_W - nw) // 2 + int(ss_ox * TARGET_W)
        ss_py = (TARGET_H - nh) // 2 + int(ss_oy * TARGET_H)

        try:
            sticker_font = ImageFont.truetype(str(FONT_PATH), 48) if FONT_PATH.exists() else ImageFont.load_default()
            base_fs = max(15, int(30 * link_scale))
            link_font = ImageFont.truetype(str(FONT_PATH), base_fs) if FONT_PATH.exists() else ImageFont.load_default()
        except Exception:
            sticker_font = link_font = ImageFont.load_default()

        items = overlay_data or []

        def make_frame(t):
            """Generate animated frame at time t."""
            bg = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 255))
            bg.paste(ss_img, (ss_px, ss_py))
            draw = ImageDraw.Draw(bg)

            # Pulse factor: oscillates 0.85 to 1.15 over 0.6s
            pulse = 1.0 + 0.15 * math.sin(t * 10)
            # Bounce: oscillates +-15px over 0.8s
            bounce = int(15 * math.sin(t * 8))

            for item in items:
                cx = int(item["cx"] * TARGET_W)
                cy = int(item["cy"] * TARGET_H)
                sz = item.get("size", 1.0)

                if item["kind"] == "circle":
                    rx = int(item.get("rx", 0.07) * TARGET_W * pulse * sz)
                    ry = int(item.get("ry", 0.04) * TARGET_H * pulse * sz)
                    for th in range(6):
                        draw.ellipse([cx-rx-th, cy-ry-th, cx+rx+th, cy+ry+th],
                                     outline=(255, 0, 0, 255))

                elif item["kind"] == "arrow":
                    ay = cy + bounce
                    r = int(50 * sz)
                    h = int(80 * sz)
                    draw.polygon([(cx, ay-h), (cx-r, ay+int(h*0.5)),
                                  (cx+r, ay+int(h*0.5))], fill=(255, 0, 0))

                elif item["kind"] == "finger":
                    fy = cy + bounce
                    try:
                        ff = ImageFont.truetype("seguiemj.ttf", int(80 * sz))
                    except: ff = sticker_font
                    draw.text((cx-40, fy-40), "\u261d", fill=(255,0,0), font=ff)

                elif item["kind"] == "text":
                    txt = item.get("text", "Click Here!")
                    fs = max(20, int(48 * sz * pulse))
                    try: tf = ImageFont.truetype(str(FONT_PATH), fs) if FONT_PATH.exists() else ImageFont.load_default()
                    except: tf = ImageFont.load_default()
                    bb = draw.textbbox((0,0), txt, font=tf)
                    tw, th = bb[2]-bb[0], bb[3]-bb[1]
                    pad = 12
                    draw.rounded_rectangle(
                        [cx-tw//2-pad, cy-th//2-pad, cx+tw//2+pad, cy+th//2+pad],
                        radius=16, fill=(0,0,0,220))
                    draw.text((cx-tw//2, cy-th//2), txt, fill=(255,255,0), font=tf)

            # Link text
            lx = int(link_x * TARGET_W)
            ly = int(link_y * TARGET_H)
            bb = draw.textbbox((0,0), landing_url, font=link_font)
            ltw = bb[2] - bb[0]
            draw.rectangle([(lx-ltw//2-8, ly-14), (lx+ltw//2+8, ly+14)], fill=(0,0,0,200))
            draw.text((lx-ltw//2, ly-10), landing_url, fill=(100,220,255), font=link_font)

            return np.array(bg.convert("RGB"))

        return VideoClip(make_frame, duration=duration).set_fps(30)

    # ── Force 9:16 ─────────────────────────────────────────────────────────────

    def _force_vertical(self, clip: VideoFileClip) -> VideoFileClip:
        w, h = clip.size
        if w / h > 9 / 16:
            new_w = int(h * 9 / 16)
            clip = crop(clip, x_center=w / 2, width=new_w)
        elif w / h < 9 / 16:
            new_h = int(w * 16 / 9)
            clip = crop(clip, y_center=h / 2, height=new_h)
        return clip.resize((TARGET_W, TARGET_H))

    # ── Main pipeline ──────────────────────────────────────────────────────────

    def process(
        self,
        input_path: str,
        game_name: str,
        channel_screenshot: str,
        landing_url: str,
        progress_callback: Optional[Callable] = None,
        overlay_data: list = None,
        layout: dict = None,
        caption_color: str = "yellow",
        caption_pos: float = 0.70,
    ) -> str:
        """
        Full pipeline for one video file.
        Returns path to the final _promo.mp4 file.
        """

        def _progress(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
            log.info(f"  [{pct}%] {msg}")

        _progress(5, "Loading video...")
        clip = VideoFileClip(input_path)

        # 1. Trim to 30s
        _progress(10, f"Trimming to {MAX_DUR}s...")
        if clip.duration > MAX_DUR:
            clip = clip.subclip(0, MAX_DUR)

        # 2. Force 9:16
        _progress(20, "Cropping to 9:16 vertical...")
        clip = self._force_vertical(clip)

        # 3. Strip original audio
        _progress(30, "Removing original voiceover...")
        clip = clip.without_audio()

        # 4. Generate new voiceover (LONG script, fills ~30s)
        _progress(40, "Generating AI voiceover (full 30 seconds)...")
        vo_path = self._make_voiceover(game_name)
        vo_clip = AudioFileClip(str(vo_path))

        # If voiceover is shorter than video, loop it to fill
        if vo_clip.duration < clip.duration:
            # Repeat voiceover to fill
            repeats = math.ceil(clip.duration / vo_clip.duration)
            vo_clips = [vo_clip] * repeats
            vo_clip = concatenate_audioclips(vo_clips)

        # Trim voiceover to match video exactly
        if vo_clip.duration > clip.duration:
            vo_clip = vo_clip.subclip(0, clip.duration)

        clip = clip.set_audio(vo_clip)

        # 5. Subtitles from voiceover
        _progress(55, "Generating subtitles with AI...")
        try:
            segments = self._transcribe(vo_path)
            # Only show subtitles during the first 25 seconds (gameplay part)
            filtered_segs = [s for s in segments if s["start"] < (MAX_DUR - 5)]
            sub_clips = self._make_subtitle_clips(filtered_segs, TARGET_W, TARGET_H, caption_color, caption_pos)
            if sub_clips:
                clip = CompositeVideoClip([clip] + sub_clips)
        except Exception as e:
            log.warning(f"Subtitle generation failed: {e}")

        # 6. CPA link bar (first 25 seconds only, disappears for channel overlay)
        _progress(70, "Adding CPA link bar...")
        try:
            cpa_duration = max(1, clip.duration - 5)  # stop 5s before end
            cpa_bar = self._make_cpa_bar(landing_url, cpa_duration)
            clip = CompositeVideoClip([clip, cpa_bar])
        except Exception as e:
            log.warning(f"CPA bar failed: {e}")

        # 7. Channel screenshot overlay (last 5 seconds, FULL SCREEN)
        _progress(80, "Adding channel screenshot + your overlays...")
        try:
            overlay_dur = min(5, clip.duration)
            overlay = self._make_channel_overlay(
                channel_screenshot, landing_url, overlay_dur,
                overlay_data or [], layout or {}
            )
            if overlay:
                overlay = overlay.set_start(clip.duration - overlay_dur)
                clip = CompositeVideoClip([clip, overlay])
        except Exception as e:
            log.warning(f"Channel overlay failed: {e}")

        # 8. Export
        _progress(90, "Rendering final video...")
        stem = Path(input_path).stem
        
        # Save to EDITED_DIR instead of raw dir
        from config import Config
        cfg = Config()
        out_dir = Path(cfg.EDITED_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        out_path = str(out_dir / f"{stem}_promo.mp4")

        clip.write_videofile(
            out_path,
            codec="libx264", audio_codec="aac",
            fps=30, preset="fast", threads=4,
            logger='bar',
        )

        # Cleanup
        try:
            vo_path.unlink(missing_ok=True)
        except Exception:
            pass
        clip.close()

        _progress(100, "Done!")
        return out_path
