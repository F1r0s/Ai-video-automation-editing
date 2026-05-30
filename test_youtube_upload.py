import logging
from pathlib import Path

from config import Config
from uploader import upload_youtube
from seo import SEOGenerator

logging.basicConfig(level=logging.INFO)

def test_youtube():
    cfg = Config()
    
    # We will use one of the existing videos in your folder for the test
    video_path = Path("tmp8pufhxvz.mp4")
    
    if not video_path.exists():
        print(f"Error: Could not find {video_path}")
        return

    print("Generating SEO metadata for the test...")
    seo_gen = SEOGenerator()
    seo_packages = seo_gen.generate(game_name="Test Game")
    youtube_seo = seo_packages["youtube"]
    
    # Add [TEST] to the title so you know it's a test upload
    youtube_seo.title = "[TEST] " + youtube_seo.title
    youtube_seo.status = {"privacyStatus": "private"} # Keep it private for the test
    
    print(f"Starting YouTube upload test for: {video_path.name}")
    print("If this is your first time, a browser window will open asking you to log in to Google and authorize the app.")
    
    success = upload_youtube(video_path, youtube_seo, cfg)
    
    if success:
        print("\n✅ YouTube upload test succeeded!")
    else:
        print("\n❌ YouTube upload test failed. Check the logs above for errors.")

if __name__ == "__main__":
    test_youtube()
