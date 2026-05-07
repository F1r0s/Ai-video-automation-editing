"""
web_app.py — Flask Backend for AI Video Automation
Hosts the HTML visual editor and processes videos.
"""
import os, json, logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from video_processor import VideoProcessor
from scraper import VideoScraper
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("web_app")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = str(Path(__file__).parent / 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max for screenshot

# Make sure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Set a simple password in your .env or hardcode here
APP_SECRET_PWD = os.getenv("APP_PASSWORD", "promo123")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/generate', methods=['POST'])
def generate():
    # 1. Check Password
    pwd = request.form.get('pwd', '')
    if pwd != APP_SECRET_PWD:
        return jsonify({"error": "Incorrect password!"}), 403

    game = request.form.get('game', '').strip()
    url = request.form.get('url', '').strip()
    max_v = int(request.form.get('max', 3))
    overlays_json = request.form.get('overlays', '[]')
    layout_json = request.form.get('layout', '{}')

    if not game or not url:
        return jsonify({"error": "Missing game or URL."}), 400

    if 'screenshot' not in request.files:
        return jsonify({"error": "Missing screenshot."}), 400
    
    file = request.files['screenshot']
    if file.filename == '':
        return jsonify({"error": "No selected file."}), 400

    filename = secure_filename(file.filename)
    screenshot_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(screenshot_path)

    overlays = json.loads(overlays_json)
    layout = json.loads(layout_json)

    # 2. Start Pipeline
    cfg = Config()
    scraper = VideoScraper(config=cfg)
    processor = VideoProcessor(
        elevenlabs_key=os.getenv("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "")
    )

    log.info(f"Starting web pipeline for: {game}")
    candidates = scraper.search(f"{game} MOD gameplay", max_results=max_v * 3)
    
    if not candidates:
        return jsonify({"error": "No videos found to scrape."}), 404

    videos = candidates[:max_v]
    processed_files = []

    for idx, meta in enumerate(videos, 1):
        log.info(f"Downloading video {idx}/{len(videos)}...")
        raw_path = scraper.download(meta)
        if not raw_path:
            continue

        try:
            out_path = processor.process(
                input_path=str(raw_path),
                game_name=game,
                channel_screenshot=screenshot_path,
                landing_url=url,
                progress_callback=lambda p, m: log.info(f"[{p}%] {m}"),
                overlay_data=overlays,
                layout=layout
            )
            processed_files.append(out_path)
            log.info(f"Processed successfully: {out_path}")
        except Exception as e:
            log.error(f"Error processing video: {e}")

    # 3. Send to Telegram
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    
    if tg_token and tg_chat and processed_files:
        import requests
        for fp in processed_files:
            try:
                with open(fp, "rb") as f:
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendVideo",
                        data={"chat_id": tg_chat, "caption": f"Promo ready: {Path(fp).name}"},
                        files={"video": f},
                        timeout=300
                    )
            except Exception as e:
                log.error(f"Telegram error: {e}")

    # Clean up screenshot
    try:
        os.remove(screenshot_path)
    except: pass

    return jsonify({
        "success": True,
        "processed_count": len(processed_files)
    })

if __name__ == '__main__':
    # Run locally for testing before Cloud Run
    app.run(host='0.0.0.0', port=5000, debug=True)
