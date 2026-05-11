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
from PIL import Image, ImageDraw, ImageFont, ImageSequence, ImageColor
from groq import Groq
# Monkey-patch for MoviePy 1.0.3 + Pillow 10+
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    ImageClip, TextClip, ColorClip, concatenate_audioclips,
    concatenate_videoclips,
)
from moviepy.video.fx.all import crop

from gtts import gTTS

log = logging.getLogger("processor")

# Constants
TARGET_W = 1080
TARGET_H = 1920
MAX_DUR  = 30
ASSETS_DIR = Path(__file__).parent / "assets"
FONT_PATH = ASSETS_DIR / "Montserrat-Bold.ttf"

if not FONT_PATH.exists():
    log.warning(
        f"Font '{FONT_PATH}' not found. "
        "Subtitles and overlays will use the PIL default font. "
        "Download Montserrat-Bold.ttf from Google Fonts and place it in the assets/ folder."
    )

# Sticker asset paths
STICKER_ASSETS = {
    "circle": ASSETS_DIR / "Circle Mark Sticker by bartek ujma.gif",
    "arrow": ASSETS_DIR / "arrow animated.gif",
    "finger": ASSETS_DIR / "hand pointing finger.gif",
    "cartoon": ASSETS_DIR / "Cartoon Look Sticker by Javi Brations.gif",
}


def _resolve_rgb(color_value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb(color_value)
    except Exception:
        named = {
            "yellow": (255, 215, 0),
            "white": (255, 255, 255),
            "green": (0, 230, 118),
            "cyan": (0, 212, 255),
        }
        return named.get(str(color_value).lower(), fallback)


class VideoProcessor:
    """Processes a single video into a CPA promo clip."""

    def __init__(self, elevenlabs_key: str = "", elevenlabs_voice_id: str = "", groq_key: str = ""):
        self.el_key      = elevenlabs_key
        self.el_voice_id = elevenlabs_voice_id or "EXAVITQu4vr4xnSDxMaL"
        self.groq_key    = groq_key
        self.groq_client = Groq(api_key=groq_key) if groq_key else None
        self._whisper     = None
        self.sticker_cache = {}  # Cache loaded sticker assets
        self._load_sticker_assets()

    def _load_sticker_assets(self):
        """Pre-load sticker assets from disk with transparency preserved."""
        for kind, asset_path in STICKER_ASSETS.items():
            if asset_path.exists():
                try:
                    source = Image.open(str(asset_path))
                    frames = []
                    durations = []
                    for frame in ImageSequence.Iterator(source):
                        rgba = frame.convert("RGBA")
                        frames.append(rgba.copy())
                        durations.append(max(40, int(frame.info.get("duration", source.info.get("duration", 100) or 100))))
                    if not frames:
                        frames = [source.convert("RGBA")]
                        durations = [100]
                    self.sticker_cache[kind] = {"frames": frames, "durations": durations}
                    log.info(f"Loaded sticker asset: {kind} ({asset_path})")
                except Exception as e:
                    log.warning(f"Failed to load sticker {kind}: {e}")
            else:
                log.warning(f"Sticker asset not found: {asset_path}")

    def _sticker_frame(self, sticker: dict, t: float) -> Image.Image:
        frames = sticker.get("frames") or []
        durations = sticker.get("durations") or []
        if not frames:
            raise ValueError("Empty sticker asset")
        if len(frames) == 1:
            return frames[0]

        total = sum(durations) if durations else len(frames) * 100
        if total <= 0:
            return frames[0]

        position_ms = int((t * 1000) % total)
        elapsed = 0
        for frame, duration in zip(frames, durations):
            elapsed += duration
            if position_ms < elapsed:
                return frame
        return frames[-1]

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

    def _generate_llama_script(self, game_name: str) -> str:
        """Use Groq Llama 3 to generate a high-retention vertical video script."""
        if not self.groq_client:
            # Fallback to hardcoded script if no key
            return (
                f"Wait. Are you still playing {game_name} the normal way? "
                f"This changes EVERYTHING. Watch till the end and grab the link below!"
            )
            
        prompt = f"""
        Write a short, punchy 30-second script for a mobile game 'MOD' promo video for the game '{game_name}'.
        The script should sound like a viral TikTok/Reels hook.
        Structure:
        1. Strong hook (Wait, stop scrolling!)
        2. The problem (playing the normal way is too slow/hard)
        3. The solution (this new 2025 mod gives unlimited resources)
        4. Proof (I tested this and it's insane)
        5. Call to action (Link on screen, tap it now!)
        Keep it under 80 words. Direct speech only.
        """
        
        try:
            completion = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"Llama script generation failed: {e}")
            return f"Check out this secret {game_name} trick for twenty twenty five. It is completely free and works on all devices. Tap the link now!"

    def _make_voiceover(self, game_name: str) -> Path:
        """
        Generate a dynamic script via Llama and convert to audio via ElevenLabs.
        """
        script = self._generate_llama_script(game_name)
        log.info(f"Generated Script: {script[:100]}...")

        out = Path(tempfile.mktemp(suffix=".mp3"))
        
        # Try ElevenLabs first (Keep this integration as requested!)
        success = self._elevenlabs_tts(script, out)
        
        # Try gTTS fallback
        if not success:
            success = self._gtts_fallback(script, out)
            
        if not success or not out.exists():
            log.warning("ALL TTS FAILED! Using 1-second silent audio to prevent crash.")
            from moviepy.editor import AudioClip
            import numpy as np
            silent = AudioClip(lambda t: np.zeros((len(t) if isinstance(t, np.ndarray) else 1, 2)), duration=5, fps=44100)
            silent.write_audiofile(str(out), fps=44100, logger=None)
            
        return out

    # ── Whisper subtitles ──────────────────────────────────────────────────────

    def _load_whisper(self):
        if self._whisper is None:
            import whisper
            self._whisper = whisper.load_model("small")
        return self._whisper

    def _transcribe(self, audio_path: Path) -> list[dict]:
        """Transcribe audio using Groq Whisper (whisper-large-v3)."""
        if not self.groq_client:
            log.warning("No Groq client available for transcription.")
            return []

        try:
            with open(audio_path, "rb") as file:
                # Use Groq Whisper API for lightning-fast transcription
                transcription = self.groq_client.audio.transcriptions.create(
                    file=(audio_path.name, file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
                words = getattr(transcription, "words", [])
                if words:
                    segments = []
                    chunk = []
                    for w in words:
                        chunk.append(w)
                        word_str = w.get("word", "") if isinstance(w, dict) else getattr(w, "word", "")
                        if len(chunk) >= 2 or word_str.strip().endswith((".", "?", "!", ",")):
                            start = chunk[0].get("start", 0) if isinstance(chunk[0], dict) else getattr(chunk[0], "start", 0)
                            end = chunk[-1].get("end", 0) if isinstance(chunk[-1], dict) else getattr(chunk[-1], "end", 0)
                            text = " ".join((c.get("word", "") if isinstance(c, dict) else getattr(c, "word", "")).strip() for c in chunk)
                            segments.append({"start": start, "end": end, "text": text})
                            chunk = []
                    if chunk:
                        start = chunk[0].get("start", 0) if isinstance(chunk[0], dict) else getattr(chunk[0], "start", 0)
                        end = chunk[-1].get("end", 0) if isinstance(chunk[-1], dict) else getattr(chunk[-1], "end", 0)
                        text = " ".join((c.get("word", "") if isinstance(c, dict) else getattr(c, "word", "")).strip() for c in chunk)
                        segments.append({"start": start, "end": end, "text": text})
                    return segments
                
                # Fallback to segments if words not available
                segments = []
                for s in getattr(transcription, "segments", []):
                    segments.append({
                        "start": s.get("start") if isinstance(s, dict) else getattr(s, "start", 0),
                        "end": s.get("end") if isinstance(s, dict) else getattr(s, "end", 0),
                        "text": s.get("text") if isinstance(s, dict) else getattr(s, "text", ""),
                    })
                return segments
        except Exception as e:
            log.error(f"Groq Whisper transcription failed: {e}")
            return []

    def _make_subtitle_clips(self, segments: list[dict], w: int, h: int, color: str, pos_y: float) -> list:
        clips = []
        try:
            import numpy as np
            from moviepy.editor import ImageClip

            subtitle_rgb = _resolve_rgb(color, (255, 255, 255))
            font_path = str(FONT_PATH) if FONT_PATH.exists() else "Arial"
            try:
                font = ImageFont.truetype(font_path, max(64, int(h * 0.050)))
            except IOError:
                font = ImageFont.load_default()

            for seg in segments:
                txt = seg["text"].strip()
                start, end = seg["start"], seg["end"]
                dur = end - start
                if not txt or dur <= 0:
                    continue
                
                wrapped = "\n".join(textwrap.wrap(txt, width=25))
                
                stroke_width = max(4, font.size // 18 if hasattr(font, "size") else 4)
                
                # Calculate dimensions first to prevent text from being cut off
                dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
                bbox = dummy_draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=10, stroke_width=stroke_width)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

                box_w = min(w - 80, 1040)
                box_h = max(260, int(th + 120))  # Dynamically size height
                
                img = Image.new('RGBA', (box_w, box_h), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)

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

    def _make_cpa_bar(self, landing_url: str, duration: float, link_color: str = "#64dcff", game_name: str = "") -> ImageClip:
        """Semi-transparent bar at the bottom with the CPA link."""
        bar_h = 240
        img = Image.new("RGBA", (TARGET_W, bar_h), (0, 0, 0, 210))
        draw = ImageDraw.Draw(img)

        try:
            font_big   = ImageFont.truetype(str(FONT_PATH), 64) if FONT_PATH.exists() else ImageFont.load_default()
            font_small = ImageFont.truetype(str(FONT_PATH), 52) if FONT_PATH.exists() else ImageFont.load_default()
        except Exception:
            font_big = font_small = ImageFont.load_default()

        # CTA text
        gn_lower = game_name.lower()
        if "mod" in gn_lower or "hack" in gn_lower or "unlimited" in gn_lower:
            cta = "Download FREE MOD Now!"
        else:
            cta = "Check out the Secret Here!"
            
        bbox = draw.textbbox((0, 0), cta, font=font_big)
        tw = bbox[2] - bbox[0]
        draw.text(((TARGET_W - tw) // 2, 24), cta, fill=(0, 255, 100, 255), font=font_big)

        # URL text - convert hex color to RGB tuple
        try:
            from PIL import ImageColor
            link_rgb = ImageColor.getrgb(link_color)
            link_fill = link_rgb + (255,)  # add alpha
        except:
            link_fill = (100, 200, 255, 255)  # fallback cyan
        
        bbox2 = draw.textbbox((0, 0), landing_url, font=font_small)
        tw2 = bbox2[2] - bbox2[0]
        draw.rounded_rectangle([(TARGET_W - tw2) // 2 - 24, 120, (TARGET_W + tw2) // 2 + 24, 120 + 70], radius=20, fill=(0, 0, 0, 160))
        draw.text(((TARGET_W - tw2) // 2, 126), landing_url, fill=link_fill, font=font_small)

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
                               layout: dict = None, link_color: str = "#64dcff") -> Optional[CompositeVideoClip]:
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
            sticker_font = ImageFont.truetype(str(FONT_PATH), 144) if FONT_PATH.exists() else ImageFont.load_default()
            base_fs = max(45, int(90 * link_scale))
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
            # Bounce: oscillates +-30px over 0.8s
            bounce = int(30 * math.sin(t * 8))

            for item in items:
                cx = int(item["cx"] * TARGET_W)
                cy = int(item["cy"] * TARGET_H)
                sz = item.get("size", 1.0)

                if item["kind"] == "circle" and "circle" in self.sticker_cache:
                    # Render circle asset with animation
                    circle_img = self._sticker_frame(self.sticker_cache["circle"], t)
                    scaled_sz = int(240 * sz * pulse)
                    scaled_circle = circle_img.resize((scaled_sz, scaled_sz), Image.LANCZOS)
                    rot = item.get("rotation", 0)
                    if rot != 0:
                        scaled_circle = scaled_circle.rotate(-rot, expand=True, resample=Image.BICUBIC)
                    paste_x = cx - scaled_circle.width // 2
                    paste_y = cy - scaled_circle.height // 2
                    bg.paste(scaled_circle, (paste_x, paste_y), scaled_circle)

                elif item["kind"] == "arrow" and "arrow" in self.sticker_cache:
                    # Render arrow asset with bounce animation
                    arrow_img = self._sticker_frame(self.sticker_cache["arrow"], t)
                    ay = cy + bounce
                    scaled_sz = int(240 * sz)
                    scaled_arrow = arrow_img.resize((scaled_sz, int(scaled_sz * 1.3)), Image.LANCZOS)
                    rot = item.get("rotation", 0)
                    if rot != 0:
                        scaled_arrow = scaled_arrow.rotate(-rot, expand=True, resample=Image.BICUBIC)
                    paste_x = cx - scaled_arrow.width // 2
                    paste_y = ay - scaled_arrow.height // 2
                    bg.paste(scaled_arrow, (paste_x, paste_y), scaled_arrow)

                elif item["kind"] == "finger" and "finger" in self.sticker_cache:
                    # Render finger asset with bounce animation
                    finger_img = self._sticker_frame(self.sticker_cache["finger"], t)
                    fy = cy + bounce
                    scaled_sz = int(300 * sz)
                    scaled_finger = finger_img.resize((scaled_sz, scaled_sz), Image.LANCZOS)
                    rot = item.get("rotation", 0)
                    if rot != 0:
                        scaled_finger = scaled_finger.rotate(-rot, expand=True, resample=Image.BICUBIC)
                    paste_x = cx - scaled_finger.width // 2
                    paste_y = fy - scaled_finger.height // 2
                    bg.paste(scaled_finger, (paste_x, paste_y), scaled_finger)

                elif item["kind"] == "cartoon" and "cartoon" in self.sticker_cache:
                    # Render cartoon asset with pulse animation
                    cartoon_img = self._sticker_frame(self.sticker_cache["cartoon"], t)
                    scaled_sz = int(240 * sz * pulse)
                    scaled_cartoon = cartoon_img.resize((scaled_sz, scaled_sz), Image.LANCZOS)
                    rot = item.get("rotation", 0)
                    if rot != 0:
                        scaled_cartoon = scaled_cartoon.rotate(-rot, expand=True, resample=Image.BICUBIC)
                    paste_x = cx - scaled_cartoon.width // 2
                    paste_y = cy - scaled_cartoon.height // 2
                    bg.paste(scaled_cartoon, (paste_x, paste_y), scaled_cartoon)

                elif item["kind"] == "text":
                    txt = item.get("text", "Click Here!")
                    fs = max(40, int(144 * sz * pulse))
                    try: tf = ImageFont.truetype(str(FONT_PATH), fs) if FONT_PATH.exists() else ImageFont.load_default()
                    except: tf = ImageFont.load_default()
                    bb = draw.textbbox((0,0), txt, font=tf)
                    tw, th = bb[2]-bb[0], bb[3]-bb[1]
                    pad = 24
                    
                    txt_img = Image.new("RGBA", (tw + pad*2, th + pad*2), (0,0,0,0))
                    txt_draw = ImageDraw.Draw(txt_img)
                    txt_draw.rounded_rectangle([0, 0, tw + pad*2, th + pad*2], radius=24, fill=(0,0,0,220))
                    txt_draw.text((pad, pad), txt, fill=(255,255,0,255), font=tf)
                    
                    rot = item.get("rotation", 0)
                    if rot != 0:
                        txt_img = txt_img.rotate(-rot, expand=True, resample=Image.BICUBIC)
                        
                    paste_x = cx - txt_img.width // 2
                    paste_y = cy - txt_img.height // 2
                    bg.paste(txt_img, (paste_x, paste_y), txt_img)

            # Link text
            lx = int(link_x * TARGET_W)
            ly = int(link_y * TARGET_H)
            
            # Convert hex color to RGB
            try:
                from PIL import ImageColor
                link_rgb = ImageColor.getrgb(link_color)
                link_fill = link_rgb + (255,)  # add alpha
            except:
                link_fill = (100, 220, 255, 255)  # fallback cyan
            
            bb = draw.textbbox((0,0), landing_url, font=link_font)
            ltw = bb[2] - bb[0]
            draw.rounded_rectangle([(lx-ltw//2-30, ly-36), (lx+ltw//2+30, ly+40)], radius=24, fill=(0,0,0,200))
            draw.text((lx-ltw//2, ly-26), landing_url, fill=link_fill, font=link_font)

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

    # ── Reward-First helpers ───────────────────────────────────────────────────

    def _prepare_hook(self, video_path: str, hook_duration: float = 5.0):
        """Load scraped gameplay, force 9:16, trim to hook_duration, strip audio."""
        clip = VideoFileClip(video_path)
        if clip.duration > hook_duration:
            clip = clip.subclip(0, hook_duration)
        clip = self._force_vertical(clip)
        clip = clip.without_audio()
        return clip

    def _validate_recording(self, recording_path: str):
        """Load user's manual screen recording, force 9:16, strip audio."""
        clip = VideoFileClip(recording_path)
        clip = self._force_vertical(clip)
        clip = clip.without_audio()
        return clip

    def _generate_reward_script(self, game_name: str, landing_url: str = "") -> str:
        """Generate a bridging script for the reward-first workflow using Llama 3."""
        if not self.groq_client:
            return (
                f"Wait. Look at this {game_name} gameplay. "
                f"Want this on your device? I will show you exactly how. "
                f"Go to the link on screen. Tap download. It is completely free. Go now!"
            )

        prompt = f"""Write a short, punchy 30-second voiceover script for a viral TikTok video about '{game_name}'.

The video has TWO parts:
Part 1 (first 5 seconds): Shows insane, jaw-dropping gameplay footage as a hook.
Part 2 (remaining 25 seconds): Shows a step-by-step screen recording of how to download the mod.

Structure the script EXACTLY like this:
1. HOOK (0-5s): "Wait... you need to see THIS gameplay..." — grab attention instantly
2. BRIDGE (5-8s): "Want this on YOUR device? Let me show you exactly how..."
3. WALKTHROUGH (8-22s): "Step one, go to the link on screen... step two, tap download..."
4. CTA (22-30s): "It works on all devices. Link is on screen right now. Download the mod and thank me later!"

Rules:
- Keep it under 80 words. Direct speech only. No stage directions.
- Use the phrase "link on screen" or "tap download" at least once.
- Sound excited and urgent like a real TikToker.
- The link is: {landing_url}"""

        try:
            completion = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"Llama reward script generation failed: {e}")
            return (
                f"Wait. Look at this {game_name} gameplay. "
                f"Want this on your device? I will show you exactly how. "
                f"Go to the link on screen. Tap download. It is completely free. Go now!"
            )

    def _find_trigger_time(self, segments: list[dict], hook_duration: float = 5.0) -> float:
        """
        Scan word-level transcription to find when trigger words are spoken.
        Returns the timestamp when stickers should start appearing.
        Trigger words: link, download, tap, click, bio, screen, button, free, mod, get
        """
        triggers = {"link", "download", "tap", "click", "bio", "screen", "button", "free", "mod", "get"}
        for seg in segments:
            text = seg.get("text", "").lower()
            start = seg.get("start", 0)
            # Only consider segments during the recording portion
            if start < hook_duration:
                continue
            for word in text.split():
                cleaned = word.strip(".,!?'\"")
                if cleaned in triggers:
                    return start
        # Fallback: stickers appear 3 seconds into the recording
        return hook_duration + 3.0

    # ── Reward-First Pipeline ──────────────────────────────────────────────────

    def process_reward_first(
        self,
        scraped_video_path: str,
        manual_recording_path: str,
        game_name: str,
        channel_screenshot: str,
        landing_url: str,
        overlay_data: list = None,
        layout: dict = None,
        caption_color: str = "yellow",
        caption_pos: float = 0.58,
        landing_link_color: str = "#64dcff",
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """
        Reward-First pipeline:
        [5s scraped hook] + [user's manual recording] with AI voiceover bridging both.
        Stickers/overlays appear only during the recording segment, triggered by keywords.
        """

        def _progress(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
            log.info(f"  [{pct}%] {msg}")

        hook_duration = 5.0

        # 1. Prepare the hook clip
        _progress(5, "Preparing 5s gameplay hook...")
        hook_clip = self._prepare_hook(scraped_video_path, hook_duration)

        # 2. Validate and prepare the manual recording
        _progress(15, "Validating manual screen recording (9:16)...")
        recording_clip = self._validate_recording(manual_recording_path)

        # 3. Concatenate hook + recording
        _progress(25, "Stitching hook + recording...")
        combined = concatenate_videoclips([hook_clip, recording_clip], method="compose")
        total_duration = combined.duration

        # 4. Generate bridging voiceover script
        _progress(35, "Generating AI bridging script...")
        script = self._generate_reward_script(game_name, landing_url)
        log.info(f"Reward Script: {script[:120]}...")

        # 5. TTS voiceover
        _progress(45, "Synthesizing AI voiceover...")
        vo_path = self._make_voiceover(game_name)
        # Override with reward script (re-generate with the reward-specific script)
        vo_path_reward = Path(tempfile.mktemp(suffix=".mp3"))
        success = self._elevenlabs_tts(script, vo_path_reward)
        if not success:
            success = self._gtts_fallback(script, vo_path_reward)
        if success and vo_path_reward.exists():
            vo_path = vo_path_reward

        vo_clip = AudioFileClip(str(vo_path))

        # Loop/trim voiceover to match combined video
        if vo_clip.duration < total_duration:
            repeats = math.ceil(total_duration / vo_clip.duration)
            vo_clip = concatenate_audioclips([vo_clip] * repeats)
        if vo_clip.duration > total_duration:
            vo_clip = vo_clip.subclip(0, total_duration)

        combined = combined.set_audio(vo_clip)

        # 6. Transcribe voiceover for subtitles
        _progress(55, "Transcribing voiceover for subtitles...")
        try:
            segments = self._transcribe(vo_path)
            # Filter subtitles: only show during the recording segment (after hook)
            recording_segs = [s for s in segments if s["start"] >= hook_duration]
            sub_clips = self._make_subtitle_clips(recording_segs, TARGET_W, TARGET_H, caption_color, caption_pos)
            if sub_clips:
                combined = CompositeVideoClip([combined] + sub_clips)
        except Exception as e:
            log.warning(f"Subtitle generation failed: {e}")
            segments = []

        # 7. Find trigger time for stickers (when AI says "link", "download", etc.)
        _progress(65, "Calculating sticker trigger timing...")
        sticker_start = self._find_trigger_time(segments, hook_duration)
        log.info(f"Stickers will appear at t={sticker_start:.1f}s")

        # 8. CPA link bar — shown during recording segment only
        _progress(70, "Adding CPA link bar...")
        try:
            cpa_duration = total_duration - hook_duration
            if cpa_duration > 0:
                cpa_bar = self._make_cpa_bar(landing_url, cpa_duration, link_color=landing_link_color, game_name=game_name)
                cpa_bar = cpa_bar.set_start(hook_duration)
                combined = CompositeVideoClip([combined, cpa_bar])
        except Exception as e:
            log.warning(f"CPA bar failed: {e}")

        # 9. Stickers & channel overlay — triggered at keyword time
        _progress(80, "Adding stickers & channel overlay...")
        try:
            overlay_dur = total_duration - sticker_start
            if overlay_dur > 0 and (overlay_data or channel_screenshot):
                overlay = self._make_channel_overlay(
                    channel_screenshot, landing_url, overlay_dur,
                    overlay_data or [], layout or {}, link_color=landing_link_color
                )
                if overlay:
                    overlay = overlay.set_start(sticker_start)
                    combined = CompositeVideoClip([combined, overlay])
        except Exception as e:
            log.warning(f"Overlay failed: {e}")

        # 10. Export
        _progress(90, "Rendering final Reward-First video...")
        stem = Path(scraped_video_path).stem.replace("hook_", "")

        from config import Config
        cfg = Config()
        out_dir = Path(cfg.EDITED_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = str(out_dir / f"{stem}_reward_promo.mp4")

        combined.write_videofile(
            out_path,
            codec="libx264", audio_codec="aac",
            fps=30, preset="fast", threads=4,
            ffmpeg_params=['-pix_fmt', 'yuv420p'],
            logger=None,
        )

        # Cleanup
        try:
            vo_path.unlink(missing_ok=True)
            if vo_path_reward.exists():
                vo_path_reward.unlink(missing_ok=True)
        except Exception:
            pass
        combined.close()

        _progress(100, "Reward-First video done!")
        return out_path

    # ── Legacy Main pipeline ──────────────────────────────────────────────────

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
        caption_pos: float = 0.58,
        landing_link_color: str = "#64dcff",
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

        # 6. CPA link bar (Shown only at the end with the channel screenshot)
        _progress(70, "Adding CPA link bar to end screen...")
        try:
            cpa_start = max(0, clip.duration - 5)
            cpa_duration = clip.duration - cpa_start
            if cpa_duration > 0:
                cpa_bar = self._make_cpa_bar(landing_url, cpa_duration, link_color=landing_link_color, game_name=game_name)
                cpa_bar = cpa_bar.set_start(cpa_start)
                clip = CompositeVideoClip([clip, cpa_bar])
        except Exception as e:
            log.warning(f"CPA bar failed: {e}")

        # 7. Channel screenshot overlay (last 5 seconds, FULL SCREEN)
        _progress(80, "Adding channel screenshot + your overlays...")
        try:
            overlay_dur = min(5, clip.duration)
            overlay = self._make_channel_overlay(
                channel_screenshot, landing_url, overlay_dur,
                overlay_data or [], layout or {}, link_color=landing_link_color
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
            ffmpeg_params=['-pix_fmt', 'yuv420p'],
            logger=None,   # suppress verbose ffmpeg bar in desktop GUI
        )

        # Cleanup
        try:
            vo_path.unlink(missing_ok=True)
        except Exception:
            pass
        clip.close()

        _progress(100, "Done!")
        return out_path
