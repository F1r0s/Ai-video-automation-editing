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
import wave
import struct
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
    concatenate_videoclips, CompositeAudioClip,
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

# Sound effects directory
SFX_DIR = ASSETS_DIR / "sfx"


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

    def __init__(self, elevenlabs_key: str = "", elevenlabs_voice_id: str = "", groq_key: str = "", sfx_enabled: bool = True):
        self.el_key      = elevenlabs_key
        self.el_voice_id = elevenlabs_voice_id or "pqHfZKP75CvOlQylNhV4"  # Adam (male)
        self.groq_key    = groq_key
        self.groq_client = Groq(api_key=groq_key) if groq_key else None
        self._whisper     = None
        self.sfx_enabled  = sfx_enabled
        self.sticker_cache = {}  # Cache loaded sticker assets
        self._load_sticker_assets()
        if sfx_enabled:
            self._ensure_sfx_assets()

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

    # ── Sound Effects ──────────────────────────────────────────────────────────

    def _ensure_sfx_assets(self):
        """Generate simple SFX WAV files if they don't already exist."""
        import numpy as np
        SFX_DIR.mkdir(parents=True, exist_ok=True)

        sfx_specs = [
            ("swoosh.wav", self._gen_swoosh_wav),
            ("cash_register.wav", self._gen_cash_register_wav),
            ("notification.wav", self._gen_notification_wav),
        ]
        for name, gen_fn in sfx_specs:
            path = SFX_DIR / name
            if not path.exists():
                try:
                    gen_fn(path)
                    log.info(f"Generated SFX: {path}")
                except Exception as e:
                    log.warning(f"Failed to generate SFX {name}: {e}")

    @staticmethod
    def _write_wav(path, samples, sample_rate=44100):
        """Write a mono float32 numpy array to a 16-bit WAV file."""
        import numpy as np
        samples = np.clip(samples, -1.0, 1.0)
        int_samples = (samples * 32767).astype(np.int16)
        with wave.open(str(path), 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            f.writeframes(int_samples.tobytes())

    @staticmethod
    def _gen_swoosh_wav(path, sr=44100):
        """Frequency-sweep swoosh sound."""
        import numpy as np
        dur = 0.4
        t = np.linspace(0, dur, int(sr * dur))
        freq = 3000 * np.exp(-6 * t)
        envelope = np.exp(-5 * t)
        tone = 0.35 * np.sin(2 * np.pi * freq * t) * envelope
        noise = 0.12 * np.random.randn(len(t)) * envelope
        VideoProcessor._write_wav(path, tone + noise, sr)

    @staticmethod
    def _gen_cash_register_wav(path, sr=44100):
        """Quick ka-ching cash register sound."""
        import numpy as np
        dur = 0.6
        t = np.linspace(0, dur, int(sr * dur))
        bell1 = 0.3 * np.sin(2 * np.pi * 2200 * t) * np.exp(-8 * t)
        bell2 = 0.25 * np.sin(2 * np.pi * 3300 * t) * np.exp(-6 * np.maximum(t - 0.1, 0))
        click = 0.4 * np.random.randn(len(t)) * np.exp(-40 * t)
        VideoProcessor._write_wav(path, bell1 + bell2 + click, sr)

    @staticmethod
    def _gen_notification_wav(path, sr=44100):
        """Pleasant two-tone notification beep."""
        import numpy as np
        dur = 0.5
        t = np.linspace(0, dur, int(sr * dur))
        tone1 = 0.3 * np.sin(2 * np.pi * 880 * t) * np.exp(-4 * t)
        t2 = np.maximum(t - 0.15, 0)
        tone2 = 0.3 * np.sin(2 * np.pi * 1320 * t2) * np.exp(-4 * t2) * (t > 0.15).astype(float)
        VideoProcessor._write_wav(path, tone1 + tone2, sr)

    def _mix_sound_effects(self, segments: list, total_duration: float,
                           end_screen_start: float = None, hook_duration: float = 0) -> list:
        """Create SFX AudioFileClip list positioned at trigger timestamps."""
        if not self.sfx_enabled:
            return []

        sfx_clips = []

        # 1. Cash register when CPA keywords are mentioned in voiceover
        trigger_time = self._find_trigger_time(segments, hook_duration)
        cash_path = SFX_DIR / "cash_register.wav"
        if cash_path.exists() and 0 < trigger_time < total_duration - 0.5:
            try:
                cash = AudioFileClip(str(cash_path)).volumex(0.5).set_start(trigger_time)
                sfx_clips.append(cash)
                log.info(f"SFX: cash_register at t={trigger_time:.1f}s")
            except Exception as e:
                log.warning(f"SFX cash_register failed: {e}")

        # 2. Swoosh when end-screen / stickers appear
        if end_screen_start and 0 < end_screen_start < total_duration:
            swoosh_path = SFX_DIR / "swoosh.wav"
            if swoosh_path.exists():
                try:
                    swoosh = AudioFileClip(str(swoosh_path)).volumex(0.45).set_start(end_screen_start)
                    sfx_clips.append(swoosh)
                    log.info(f"SFX: swoosh at t={end_screen_start:.1f}s")
                except Exception as e:
                    log.warning(f"SFX swoosh failed: {e}")

            # 3. Notification pop right after the swoosh
            notif_path = SFX_DIR / "notification.wav"
            if notif_path.exists():
                try:
                    notif_t = end_screen_start + 0.3
                    notif = AudioFileClip(str(notif_path)).volumex(0.4).set_start(notif_t)
                    sfx_clips.append(notif)
                    log.info(f"SFX: notification at t={notif_t:.1f}s")
                except Exception as e:
                    log.warning(f"SFX notification failed: {e}")

        return sfx_clips

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
            log.warning("ElevenLabs skipped: no API key")
            return False
        log.info(f"ElevenLabs TTS: using voice_id={self.el_voice_id}")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.el_voice_id}"
        headers = {"xi-api-key": self.el_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if not r.ok:
                log.warning(f"ElevenLabs failed: HTTP {r.status_code} — {r.text[:200]}")
                return False
            out.write_bytes(r.content)
            log.info(f"ElevenLabs TTS success: {len(r.content)} bytes saved")
            return True
        except Exception as e:
            log.warning(f"ElevenLabs exception: {e}")
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
        IMPORTANT: Only talk about the game '{game_name}'. Do NOT mention any other games like 'MadOut 2' or 'MadOut2 BigCityOnline'. Focus exclusively on '{game_name}'.
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
            log.warning("Transcription skipped: no Groq client (GROQ_API_KEY missing or not passed to processor)")
            return []
        log.info(f"Transcribing audio: {audio_path.name} ({audio_path.stat().st_size if audio_path.exists() else 'missing'} bytes)")

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

    def _make_subtitle_clips(self, segments: list[dict], w: int, h: int, color: str, pos_y: float, font_name: str = "Montserrat-Bold") -> list:
        clips = []
        try:
            import numpy as np
            from moviepy.editor import ImageClip

            subtitle_rgb = _resolve_rgb(color, (255, 255, 255))
            font_path = str(ASSETS_DIR / f"{font_name}.ttf")
            if not Path(font_path).exists():
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

    def _make_cpa_bar(self, landing_url: str, duration: float, link_color: str = "#64dcff", game_name: str = "", link_font_name: str = "Montserrat-Bold") -> ImageClip:
        """Semi-transparent bar at the bottom with the CPA link."""
        bar_h = 240
        img = Image.new("RGBA", (TARGET_W, bar_h), (0, 0, 0, 210))
        draw = ImageDraw.Draw(img)

        font_path = str(ASSETS_DIR / f"{link_font_name}.ttf")
        if not Path(font_path).exists():
            font_path = str(FONT_PATH) if FONT_PATH.exists() else "Arial"

        try:
            font_big   = ImageFont.truetype(font_path, 64)
            font_small = ImageFont.truetype(font_path, 52)
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
                               layout: dict = None, link_color: str = "#64dcff", link_font_name: str = "Montserrat-Bold") -> Optional[CompositeVideoClip]:
        """Animated channel overlay with user-positioned screenshot, link, and stickers.
        Even without a screenshot, stickers will still be rendered on a transparent base.
        Screenshot is positioned flush at the top (no dead zone gap) and scaled to
        leave ~200px at the bottom for playback controls."""
        has_screenshot = screenshot_path and Path(screenshot_path).exists()
        # Only bail out if there's NOTHING to render
        if not has_screenshot and not overlay_data:
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

        # Bottom padding to keep content above playback controls
        BOTTOM_PADDING = 200
        USABLE_H = TARGET_H - BOTTOM_PADDING

        # Pre-render screenshot: exact WYSIWYG mapping from the GUI editor
        ss_img = None
        ss_px = ss_py = 0
        if has_screenshot:
            ss_img = Image.open(screenshot_path).convert("RGBA")
            # In GUI, auto_scale fits width to canvas. ss_zoom is relative to that.
            base_scale = TARGET_W / ss_img.width
            final_scale = base_scale * ss_zoom
            nw, nh = int(ss_img.width * final_scale), int(ss_img.height * final_scale)
            ss_img = ss_img.resize((nw, nh), Image.LANCZOS)
            
            # GUI sends center offset (ss_ox, ss_oy). Paste coordinates are top-left.
            ss_px = int((TARGET_W / 2) + (ss_ox * TARGET_W) - (nw / 2))
            ss_py = int((TARGET_H / 2) + (ss_oy * TARGET_H) - (nh / 2))

        font_path = str(ASSETS_DIR / f"{link_font_name}.ttf")
        if not Path(font_path).exists():
            font_path = str(FONT_PATH) if FONT_PATH.exists() else "Arial"

        try:
            sticker_font = ImageFont.truetype(str(FONT_PATH), 144) if FONT_PATH.exists() else ImageFont.load_default()
            base_fs = max(30, int(60 * link_scale))
            link_font = ImageFont.truetype(font_path, base_fs)
        except Exception:
            sticker_font = link_font = ImageFont.load_default()

        items = overlay_data or []

        def make_frame(t):
            """Generate animated frame at time t."""
            # Transparent background when no screenshot (stickers composited over video)
            bg = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0) if not has_screenshot else (0, 0, 0, 255))
            if ss_img:
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

            # Link text — draw the CPA link on the channel overlay itself
            # (no separate CPA bar needed — this is the single source of truth)
            if landing_url:
                lx = int(link_x * TARGET_W)
                # Clamp link Y to stay within usable area (above playback controls)
                ly = min(int(link_y * TARGET_H), USABLE_H - 60)
                try:
                    from PIL import ImageColor
                    link_rgb = ImageColor.getrgb(link_color)
                    link_fill = link_rgb + (255,)
                except Exception:
                    link_fill = (100, 220, 255, 255)
                    
                # Dynamic font scaling if URL is too long
                current_font = link_font
                bb = draw.textbbox((0, 0), landing_url, font=current_font)
                ltw = bb[2] - bb[0]
                temp_fs = base_fs
                while ltw > TARGET_W - 80 and temp_fs > 20:
                    temp_fs -= 2
                    try:
                        current_font = ImageFont.truetype(font_path, temp_fs)
                    except Exception:
                        break
                    bb = draw.textbbox((0, 0), landing_url, font=current_font)
                    ltw = bb[2] - bb[0]

                # Make sure the bounding box doesn't go off the left/right screen edges
                left_edge = lx - ltw // 2
                right_edge = lx + ltw // 2
                if left_edge < 30:
                    lx += (30 - left_edge)
                elif right_edge > TARGET_W - 30:
                    lx -= (right_edge - (TARGET_W - 30))

                draw.rounded_rectangle([(lx-ltw//2-30, ly-36), (lx+ltw//2+30, ly+40)], radius=24, fill=(0,0,0,200))
                draw.text((lx-ltw//2, ly-26), landing_url, fill=link_fill, font=current_font)

            # Return RGBA for transparent overlay (stickers), RGB for screenshot overlay
            if has_screenshot:
                return np.array(bg.convert("RGB"))
            else:
                return np.array(bg)  # RGBA — MoviePy will use alpha channel for compositing

        if has_screenshot:
            return VideoClip(make_frame, duration=duration).set_fps(30)
        else:
            # Transparent RGBA overlay — stickers float over the video
            clip_ov = VideoClip(make_frame, duration=duration).set_fps(30)
            clip_ov = clip_ov.set_ismask(False)  # treat as normal clip, not mask
            return clip_ov

    # ── Short vs Long-Form Detection ───────────────────────────────────────────

    def _detect_video_type(self, clip: VideoFileClip) -> str:
        """
        Returns 'short' if the video is a YouTube Short:
          - Vertical (height >= width, i.e. ratio <= 1.0) OR close to 9:16
          - Duration <= 60 seconds
        Returns 'longform' otherwise (horizontal, or over 60s).
        """
        w, h = clip.size
        aspect = w / h  # < 1.0 means portrait/vertical
        duration = clip.duration
        is_vertical = aspect <= 1.05  # Allow slight tolerance (e.g. 1080x1080 square)
        is_short = duration <= 60.0
        if is_vertical and is_short:
            log.info(f"Video type: SHORT ({w}x{h}, {duration:.1f}s) — resize only")
            return "short"
        log.info(f"Video type: LONG-FORM ({w}x{h}, {duration:.1f}s) — letterbox to 9:16")
        return "longform"

    def _letterbox_ffmpeg(self, input_path: str, output_path: str) -> bool:
        """
        Convert any video to 9:16 (1080x1920) using FFmpeg directly.
        Strategy:
          - Scales the video to fit within 1080x1920 (preserving aspect ratio)
          - Fills the remaining space with a blurred+zoomed version of the same
            video as the background (no black bars, no cropping of content).
        This is 10-20x faster than doing it through MoviePy frame-by-frame.
        """
        import subprocess
        filter_graph = (
            # Background: scale-up and blur the original to fill 1080x1920
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "gblur=sigma=30[bg];"
            # Foreground: scale to fit inside 1080x1920 without cropping
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            # Overlay foreground centred on blurred background
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", filter_graph,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-threads", "4",
            output_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode != 0:
                err = result.stderr.decode('utf-8', errors='replace')[:500]
                log.warning(f"FFmpeg letterbox failed (code {result.returncode}): {err}")
                return False
            log.info(f"FFmpeg letterbox done: {output_path}")
            return True
        except subprocess.TimeoutExpired:
            log.error("FFmpeg letterbox timed out after 600s")
            return False
        except Exception as e:
            log.error(f"FFmpeg letterbox exception: {e}")
            return False

    def _prepare_for_916(self, clip: VideoFileClip, input_path: str = "") -> VideoFileClip:
        """
        Smart 9:16 conversion:
        - YouTube Shorts (vertical, ≤60s): simple resize, no cropping.
        - Long-form (horizontal or >60s): letterbox via FFmpeg blurred background.
          The full content is preserved — NO cropping, NO trimming.
        Returns a MoviePy VideoFileClip ready at 1080x1920.
        """
        video_type = self._detect_video_type(clip)

        if video_type == "short":
            # Already vertical — just resize to exact target
            return clip.resize((TARGET_W, TARGET_H))

        # Long-form: use FFmpeg letterbox for speed and no-crop guarantee
        if input_path and Path(input_path).exists():
            tmp_lb = Path(tempfile.mktemp(suffix="_lb.mp4"))
            success = self._letterbox_ffmpeg(input_path, str(tmp_lb))
            if success and tmp_lb.exists():
                clip.close()  # release original
                return VideoFileClip(str(tmp_lb))
            log.warning("FFmpeg letterbox failed — falling back to MoviePy letterbox")

        # MoviePy fallback letterbox (slower but no FFmpeg dependency failure)
        w, h = clip.size
        # Scale to fit within 1080x1920
        scale = min(TARGET_W / w, TARGET_H / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        fg = clip.resize((new_w, new_h))
        # Solid dark background
        bg = ColorClip(size=(TARGET_W, TARGET_H), color=(15, 15, 15), duration=clip.duration)
        letterboxed = CompositeVideoClip(
            [bg, fg.set_position(("center", "center"))],
            size=(TARGET_W, TARGET_H)
        )
        return letterboxed

    # ── Force 9:16 (legacy alias, kept for compatibility) ───────────────────────

    def _force_vertical(self, clip: VideoFileClip) -> VideoFileClip:
        """Legacy alias — kept for backward compatibility. Calls _prepare_for_916."""
        return self._prepare_for_916(clip)

    # ── Reward-First helpers ───────────────────────────────────────────────────

    def _find_best_hook_start(self, video_path: str, hook_duration: float = 5.0) -> float:
        """
        Scan the video to find the most energetic/exciting 5-second window.
        Uses frame-to-frame pixel variance as a motion energy metric.
        Returns the best start timestamp in seconds.
        """
        import numpy as np
        try:
            clip = VideoFileClip(video_path)
            total = clip.duration
            if total <= hook_duration:
                clip.close()
                return 0.0

            # Sample at 2fps to keep it fast
            sample_fps = 2.0
            step = 1.0 / sample_fps
            times = [i * step for i in range(int(total * sample_fps))]

            # Compute per-frame energy (mean absolute difference from previous frame)
            energies = []
            prev_frame = None
            for t in times:
                try:
                    frame = clip.get_frame(t)
                    small = frame[::4, ::4]  # downsample 4x for speed
                    if prev_frame is not None:
                        diff = np.mean(np.abs(small.astype(float) - prev_frame.astype(float)))
                        energies.append((t, diff))
                    prev_frame = small
                except Exception:
                    continue

            clip.close()

            if not energies:
                return 0.0

            # Compute sliding window energy over hook_duration
            window_frames = max(1, int(hook_duration * sample_fps))
            best_start = 0.0
            best_energy = -1.0

            for i in range(len(energies) - window_frames + 1):
                window_energy = sum(e for _, e in energies[i:i + window_frames])
                if window_energy > best_energy:
                    best_energy = window_energy
                    best_start = energies[i][0]
                    # Don't go so far that we can't fit hook_duration
                    if best_start + hook_duration > total:
                        best_start = max(0.0, total - hook_duration)

            log.info(f"Best hook window found at t={best_start:.1f}s (energy={best_energy:.1f})")
            return best_start

        except Exception as e:
            log.warning(f"Hook energy scan failed, using t=0: {e}")
            return 0.0

    def _prepare_hook(self, video_path: str, hook_duration: float = 5.0):
        """
        Load scraped gameplay, find the most energetic window, convert to 9:16, strip audio.
        For Shorts: resize. For long-form: letterbox (no cropping).
        """
        best_start = self._find_best_hook_start(video_path, hook_duration)
        clip = VideoFileClip(video_path)
        end = min(clip.duration, best_start + hook_duration)
        sub = clip.subclip(best_start, end)
        
        # Optimization: Save subclip to temp file so FFmpeg can handle the 9:16 letterbox fast
        tmp_sub = Path(tempfile.mktemp(suffix="_sub.mp4"))
        sub.write_videofile(str(tmp_sub), codec="libx264", audio_codec="aac", logger=None, preset="ultrafast")
        sub.close()
        clip.close()

        # Now use fast FFmpeg letterbox
        final_hook = VideoFileClip(str(tmp_sub))
        final_hook = self._prepare_for_916(final_hook, input_path=str(tmp_sub))
        
        # Cleanup the temp subclip file after loading back into memory/MoviePy
        # (Note: MoviePy keeps file handles open, so we might need to be careful with cleanup)
        return final_hook.without_audio()

    def _validate_recording(self, recording_path: str):
        """Load user's manual screen recording, convert to 9:16 (letterbox if needed), strip audio."""
        clip = VideoFileClip(recording_path)
        clip = self._prepare_for_916(clip, input_path=recording_path)
        clip = clip.without_audio()
        return clip

    def _generate_reward_script(self, game_name: str, landing_url: str = "", custom_script: str = "", hook_duration: float = 10.0) -> str:
        """Generate a bridging script for the reward-first workflow using Llama 3."""
        if not self.groq_client:
            return (
                f"Look at this {game_name} gameplay. "
                f"Want this on your device? Here is how. "
                f"Go to the link on screen. Tap download. It is completely free. Go now!"
            )

        if custom_script:
            prompt = f"""Write a short voiceover script for a YouTube Shorts video about '{game_name}'.
The video structure is:
- First {hook_duration} seconds: gameplay footage plays (NO talking during this part, the gameplay speaks for itself).
- After {hook_duration}s: a screen recording shows how to download the mod.

The user provided these walkthrough steps:
"{custom_script}"

Your script must ONLY cover the walkthrough portion (after the gameplay hook). Structure it like:
1. TRANSITION (1 sentence max): "Want this? Here is exactly how to get it."
2. WALKTHROUGH: Follow the user's steps above. Be direct. "Go to the link on screen. Tap download. Install it."
3. CTA (1 sentence): "Link is on screen. Download now, it is free."

Rules:
- Do NOT write anything for the gameplay hook portion. The hook has no voiceover.
- Keep it under 60 words total. Direct speech only. No stage directions, no labels, no numbering.
- Sound natural and direct, not over-hyped.
- IMPORTANT: Only talk about '{game_name}'. Do NOT mention any other game.
- CRITICAL: The website link is EXACTLY "{landing_url}". You MUST spell it exactly as shown — letter by letter. Do NOT alter, rearrange, or misspell the URL. Say it exactly as "{landing_url}"."""
        else:
            prompt = f"""Write a short voiceover script for a YouTube Shorts video about '{game_name}'.
The video structure is:
- First {hook_duration} seconds: gameplay footage plays (NO talking, the gameplay is the hook).
- After {hook_duration}s: a screen recording shows how to download the mod.

Your script must ONLY cover the walkthrough portion (after the gameplay hook). Structure it like:
1. TRANSITION (1 sentence): "Want this on your device? Let me show you."
2. WALKTHROUGH: "Go to the link on screen. Tap download. Install and open it."
3. CTA (1 sentence): "It works on all devices. Link is right there on screen."

Rules:
- Do NOT write anything for the gameplay hook. The hook has no voiceover.
- Keep it under 50 words total. Direct speech only. No stage directions, no labels.
- Get straight to the point. No fluff.
- IMPORTANT: Only talk about '{game_name}'. Do NOT mention any other game.
- CRITICAL: The website link is EXACTLY "{landing_url}". You MUST spell it exactly as shown — letter by letter. Do NOT alter, rearrange, or misspell the URL. Say it exactly as "{landing_url}"."""

        try:
            completion = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"Llama reward script generation failed: {e}")
            return (
                f"Want this on your device? Here is how. "
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
        link_font_name: str = "Montserrat-Bold",
        progress_callback: Optional[Callable] = None,
        custom_script: str = "",
        hook_duration: float = 10.0,
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

        # 1. Prepare the hook clip
        _progress(5, f"Preparing {hook_duration}s gameplay hook...")
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
        script = self._generate_reward_script(game_name, landing_url, custom_script, hook_duration)
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

        # Voiceover starts AFTER the hook (no talking during gameplay hook)
        # Create silence for the hook portion, then the voiceover for the walkthrough
        from moviepy.editor import AudioClip
        import numpy as np

        silence_duration = hook_duration
        silence = AudioClip(lambda t: np.zeros((1, 2)), duration=silence_duration, fps=44100)

        # Combine: silence during hook + voiceover during walkthrough
        walkthrough_audio = concatenate_audioclips([silence, vo_clip])

        # Trim to match combined video length
        if walkthrough_audio.duration > total_duration:
            walkthrough_audio = walkthrough_audio.subclip(0, total_duration)

        combined = combined.set_audio(walkthrough_audio)

        # 6. Transcribe voiceover for subtitles
        _progress(55, "Transcribing voiceover for subtitles...")
        segments = []
        sub_clips = []   # always defined even if transcription fails
        try:
            # Transcribe the reward-specific audio
            transcribe_path = vo_path_reward if vo_path_reward.exists() else vo_path
            segments = self._transcribe(transcribe_path)
            log.info(f"Got {len(segments)} subtitle segments from transcription")

            # OFFSET all subtitle timestamps by hook_duration so they align
            # with the walkthrough portion (voiceover starts after the hook)
            for seg in segments:
                seg["start"] += hook_duration
                seg["end"] += hook_duration

            sub_clips = self._make_subtitle_clips(segments, TARGET_W, TARGET_H, caption_color, caption_pos, link_font_name)
            if sub_clips:
                log.info(f"Adding {len(sub_clips)} subtitle clips (offset by {hook_duration}s for walkthrough)")
            else:
                log.warning("No subtitle clips were generated — check font path and segment data")
        except Exception as e:
            import traceback
            log.warning(f"Subtitle generation failed: {e}\n{traceback.format_exc()}")
            segments = []

        # 7. Screenshot + stickers appear in the LAST 5 seconds
        # (after the walkthrough, as an end-screen call-to-action)
        # NOTE: CPA bar is NOT added separately — the channel overlay already
        # draws the link text, so adding a CPA bar would create duplicates.
        _progress(65, "Preparing end-screen overlay timing...")
        end_screen_dur = min(5.0, total_duration * 0.25)  # last 5s or 25% of video
        end_screen_start = total_duration - end_screen_dur
        log.info(f"End-screen (screenshot + stickers) at t={end_screen_start:.1f}s for {end_screen_dur:.1f}s")

        # 9. Assemble all layers into a SINGLE CompositeVideoClip (FLATTENED)
        _progress(85, "Assembling video layers...")
        all_layers = [combined]  # Base: hook + recording + audio

        # Subtitles — filter to STOP before the end-screen starts
        # (no captions should bleed into the channel screenshot section)
        if sub_clips:
            filtered_subs = []
            for sc in sub_clips:
                # Each subtitle clip has .start and .duration
                clip_end = sc.start + sc.duration
                if clip_end <= end_screen_start:
                    filtered_subs.append(sc)
                elif sc.start < end_screen_start:
                    # Trim subtitle to end exactly at end_screen_start
                    trimmed_dur = end_screen_start - sc.start
                    if trimmed_dur > 0.1:
                        filtered_subs.append(sc.set_duration(trimmed_dur))
                # else: subtitle starts during end-screen, skip entirely
            log.info(f"Subtitles: {len(sub_clips)} total -> {len(filtered_subs)} after filtering (cut before t={end_screen_start:.1f}s)")
            all_layers.extend(filtered_subs)

        # Screenshot + stickers overlay — LAST 5 seconds only
        # The channel overlay already includes the link text, so no separate CPA bar.
        has_channel_overlay = False
        if end_screen_dur > 0 and (overlay_data or channel_screenshot):
            try:
                overlay = self._make_channel_overlay(
                    channel_screenshot or "", landing_url, end_screen_dur,
                    overlay_data or [], layout or {}, link_color=landing_link_color, link_font_name=link_font_name
                )
                if overlay:
                    overlay = overlay.set_start(end_screen_start)
                    all_layers.append(overlay)
                    has_channel_overlay = True
            except Exception as e:
                log.warning(f"Overlay failed: {e}")

        # CPA bar — ONLY if no channel overlay was rendered (to avoid duplicates)
        if not has_channel_overlay:
            try:
                if end_screen_dur > 0:
                    cpa_bar = self._make_cpa_bar(landing_url, end_screen_dur, link_color=landing_link_color, game_name=game_name, link_font_name=link_font_name)
                    cpa_bar = cpa_bar.set_start(end_screen_start)
                    all_layers.append(cpa_bar)
            except Exception as e:
                log.warning(f"CPA bar failed: {e}")

        # Final Flattened Composition
        final_video = CompositeVideoClip(all_layers, size=(TARGET_W, TARGET_H))

        # Mix in sound effects
        if self.sfx_enabled:
            try:
                sfx_clips = self._mix_sound_effects(segments, total_duration, end_screen_start, hook_duration)
                if sfx_clips and final_video.audio:
                    final_video = final_video.set_audio(
                        CompositeAudioClip([final_video.audio] + sfx_clips)
                    )
                    log.info(f"Mixed {len(sfx_clips)} SFX into reward-first audio")
            except Exception as e:
                log.warning(f"SFX mixing failed (non-fatal): {e}")

        # 10. Export
        _progress(90, "Rendering final Reward-First video...")
        stem = Path(scraped_video_path).stem.replace("hook_", "")

        from config import Config
        cfg = Config()
        out_dir = Path(cfg.EDITED_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = str(out_dir / f"{stem}_reward_promo.mp4")

        final_video.write_videofile(
            out_path,
            codec="libx264", 
            audio_codec="aac",
            fps=30, 
            preset="faster", 
            threads=8,
            ffmpeg_params=['-pix_fmt', 'yuv420p', '-crf', '24'],
            logger=None,
        )

        # Cleanup
        try:
            vo_path.unlink(missing_ok=True)
            if vo_path_reward.exists():
                vo_path_reward.unlink(missing_ok=True)
        except Exception:
            pass
        final_video.close()

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
        link_font_name: str = "Montserrat-Bold"
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

        # 1. Detect video type — Short or Long-form
        video_type = self._detect_video_type(clip)

        # Only trim YouTube Shorts (≤60s). NEVER trim long-form videos.
        _progress(10, f"Analyzing video type: {video_type}...")
        if video_type == "short" and clip.duration > MAX_DUR:
            log.info(f"Short video trimmed to {MAX_DUR}s")
            clip = clip.subclip(0, MAX_DUR)
        # Long-form: keep FULL length — no trimming

        # 2. Convert to 9:16:
        #    - Short: resize to 1080x1920
        #    - Long-form: letterbox with blurred background (NO CROPPING)
        _progress(20, "Converting to 9:16 vertical (letterbox for long-form, no cropping)...")
        clip = self._prepare_for_916(clip, input_path=input_path)

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
            sub_clips = self._make_subtitle_clips(filtered_segs, TARGET_W, TARGET_H, caption_color, caption_pos, link_font_name)
            if sub_clips:
                clip = CompositeVideoClip([clip] + sub_clips)
        except Exception as e:
            log.warning(f"Subtitle generation failed: {e}")

        # 6 & 7. Channel screenshot overlay + link (last 5 seconds, FULL SCREEN)
        # The channel overlay already draws the CPA link — no separate CPA bar needed.
        _progress(70, "Adding channel screenshot + your overlays...")
        has_channel_overlay = False
        try:
            overlay_dur = min(5, clip.duration)
            overlay = self._make_channel_overlay(
                channel_screenshot, landing_url, overlay_dur,
                overlay_data or [], layout or {}, link_color=landing_link_color, link_font_name=link_font_name
            )
            if overlay:
                overlay = overlay.set_start(clip.duration - overlay_dur)
                clip = CompositeVideoClip([clip, overlay])
                has_channel_overlay = True
        except Exception as e:
            log.warning(f"Channel overlay failed: {e}")

        # CPA bar fallback — only if no channel overlay was rendered
        if not has_channel_overlay:
            _progress(75, "Adding CPA link bar fallback...")
            try:
                cpa_start = max(0, clip.duration - 5)
                cpa_duration = clip.duration - cpa_start
                if cpa_duration > 0:
                    cpa_bar = self._make_cpa_bar(landing_url, cpa_duration, link_color=landing_link_color, game_name=game_name, link_font_name=link_font_name)
                    cpa_bar = cpa_bar.set_start(cpa_start)
                    clip = CompositeVideoClip([clip, cpa_bar])
            except Exception as e:
                log.warning(f"CPA bar failed: {e}")

        # 8. Mix in sound effects
        _progress(80, "Adding sound effects...")
        end_screen_t = max(0, clip.duration - 5)
        try:
            segments_for_sfx = segments if 'segments' in dir() else []
        except Exception:
            segments_for_sfx = []
        if self.sfx_enabled:
            try:
                sfx_clips = self._mix_sound_effects(segments_for_sfx, clip.duration, end_screen_t)
                if sfx_clips and clip.audio:
                    clip = clip.set_audio(
                        CompositeAudioClip([clip.audio] + sfx_clips)
                    )
                    log.info(f"Mixed {len(sfx_clips)} SFX into legacy audio")
            except Exception as e:
                log.warning(f"SFX mixing failed (non-fatal): {e}")

        # 9. Export
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
