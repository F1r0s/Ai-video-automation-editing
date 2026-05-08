"""
mobile_client.py - Run this on your Phone (Termux)
This hosts the web UI locally on your phone.
When you click generate, it downloads the video using your Phone's safe IP,
and then automatically uploads it to your Hugging Face space for heavy AI rendering!
"""
import os, json, logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import requests

from scraper import VideoScraper
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mobile_client")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = str(Path(__file__).parent / 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# YOUR HUGGING FACE URL GOES HERE!
# Example: "https://your-username-ai-video-studio.hf.space"
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "https://replace-me-with-your-huggingface-url.hf.space")


# Simple global status just like the main app
current_status = "Waiting to start..."
def update_status(msg: str):
    global current_status
    current_status = msg
    log.info(f"STATUS: {msg}")

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({"message": current_status})


@app.route('/')
def index():
    # Serve the exact same beautiful UI!
    return render_template('index.html')


@app.route('/api/generate', methods=['POST'])
def generate():
    global current_status
    update_status("Starting Mobile Scraper pipeline...")

    game = request.form.get('game', '').strip()
    url = request.form.get('url', '').strip()
    overlays_json = request.form.get('overlays', '[]')
    layout_json = request.form.get('layout', '{}')
    cap_color = request.form.get('caption_color', 'yellow')
    cap_pos = request.form.get('caption_pos', '0.70')
    
    screenshot_file = request.files.get('screenshot')
    screenshot_path = ""
    if screenshot_file:
        screenshot_path = str(Path(app.config['UPLOAD_FOLDER']) / secure_filename(screenshot_file.filename))
        screenshot_file.save(screenshot_path)

    # 1. Scrape using Phone IP!
    cfg = Config()
    scraper = VideoScraper(config=cfg)
    
    update_status(f"Searching web for: {game}...")
    search_term = game if "mod" in game.lower() else f"{game} MOD"
    candidates = scraper.search(f"{search_term} gameplay", max_results=3)
    
    if not candidates:
        update_status("Error: No videos found.")
        return jsonify({"error": "No videos found."}), 404

    # Download the best raw video using mobile data!
    update_status("Downloading raw video safely via Mobile IP...")
    raw_path = scraper.download(candidates[0])
    
    if not raw_path:
        update_status("Error: Download failed.")
        return jsonify({"error": "Download failed."}), 500

    # 2. Upload to Hugging Face Cloud!
    update_status("Uploading raw video to Hugging Face Cloud for heavy AI rendering...")
    
    if "replace-me" in CLOUD_API_URL:
        update_status("Error: Please set your CLOUD_API_URL in mobile_client.py!")
        return jsonify({"error": "CLOUD_API_URL not set."}), 500

    try:
        files = {
            'video': open(raw_path, 'rb')
        }
        if screenshot_path and os.path.exists(screenshot_path):
            files['screenshot'] = open(screenshot_path, 'rb')
            
        data = {
            'game': game,
            'url': url,
            'overlays': overlays_json,
            'layout': layout_json,
            'caption_color': cap_color,
            'caption_pos': cap_pos
        }
        
        # This sends it to Hugging Face! HF will process and send to Telegram.
        response = requests.post(f"{CLOUD_API_URL}/api/cloud_process", data=data, files=files)
        
        if response.ok:
            update_status("✅ Success! Cloud Rendered and Sent to Telegram!")
            return jsonify(response.json())
        else:
            err = response.json().get('error', response.text)
            update_status(f"❌ Cloud Render Error: {err}")
            return jsonify({"error": err}), 500

    except Exception as e:
        update_status(f"Error communicating with Cloud: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Run on mobile localhost
    print("==================================================")
    print("📱 MOBILE CLIENT STARTED")
    print("Open your phone's browser to: http://127.0.0.1:5000")
    print("==================================================")
    app.run(host='0.0.0.0', port=5000, debug=False)
