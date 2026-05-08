import sys
import logging
from video_processor import VideoProcessor
from config import Config

logging.basicConfig(level=logging.INFO)

cfg = Config()
processor = VideoProcessor(elevenlabs_key="", elevenlabs_voice_id="")

try:
    processor.process(
        input_path="downloads/raw/I AM SEGA _In-Game Version__eFmRgJd4cqg.mp4",
        game_name="SEGA",
        channel_screenshot="uploads/screenshot.png",  # might not exist, but let's see
        landing_url="test.com",
        progress_callback=lambda p, m: print(f"{p}% - {m}"),
        overlay_data=[],
        layout={}
    )
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
