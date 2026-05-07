"""
web_app.py — Flask Backend for AI Video Automation
Hosts the HTML visual editor and processes videos.
"""
import os, json, logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- Cloud Environment Setup ---
# If running on a cloud service like Hugging Face, write the cookies to a file
# securely from the environment variables to bypass yt-dlp bot blocking.
cookies_content = os.getenv("COOKIES_TXT_CONTENT")
if cookies_content:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(cookies_content)
    os.environ["YT_DLP_COOKIES"] = "cookies.txt"

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

def update_status(msg):
    try:
        with open("status.json", "w") as f:
            json.dump({"message": msg}, f)
    except:
        pass

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        if os.path.exists("status.json"):
            with open("status.json", "r") as f:
                return jsonify(json.load(f))
    except:
        pass
    return jsonify({"message": "Processing..."})

@app.route('/output/<filename>')
def serve_output(filename):
    cfg = Config()
    # Check edited dir first, fallback to raw dir for thumbnails
    edited_path = Path(cfg.EDITED_DIR) / filename
    raw_path = Path(cfg.RAW_DIR) / filename
    if edited_path.exists():
        return send_from_directory(str(cfg.EDITED_DIR), filename)
    elif raw_path.exists():
        return send_from_directory(str(cfg.RAW_DIR), filename)
    return "Not Found", 404

@app.route('/api/verify', methods=['POST'])
def verify_pwd():
    data = request.get_json() or {}
    if data.get('pwd') == APP_SECRET_PWD:
        return jsonify({"success": True})
    return jsonify({"success": False}), 403

@app.route('/api/generate', methods=['POST'])
def generate():
    # Reset status
    update_status("Starting pipeline...")
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
    update_status(f"Searching web for: {game}...")
    search_term = game if "mod" in game.lower() else f"{game} MOD"
    candidates = scraper.search(f"{search_term} gameplay", max_results=max_v * 3)
    
    if not candidates:
        update_status("Error: No videos found to scrape.")
        return jsonify({"error": "No videos found to scrape."}), 404

    videos = candidates[:max_v]
    processed_files = []

    for idx, meta in enumerate(videos, 1):
        log.info(f"Downloading video {idx}/{len(videos)}...")
        update_status(f"Downloading raw video {idx}/{len(videos)}...")
        raw_path = scraper.download(meta)
        if not raw_path:
            continue

        try:
            update_status(f"Rendering video {idx}/{len(videos)}... (this takes a few minutes)")
            out_path = processor.process(
                input_path=str(raw_path),
                game_name=game,
                channel_screenshot=screenshot_path,
                landing_url=url,
                progress_callback=lambda p, m: update_status(f"[{p}%] {m}"),
                overlay_data=overlays,
                layout=layout
            )
            processed_files.append(out_path)
            log.info(f"Processed successfully: {out_path}")
        except Exception as e:
            update_status(f"Error processing video: {e}")
            log.error(f"Error processing video: {e}")

    # 3. Send to Telegram
    update_status("Sending to Telegram...")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    
    if tg_token and tg_chat and processed_files:
        import requests
        for fp in processed_files:
            try:
                with open(fp, "rb") as f:
                    r = requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendVideo",
                        data={"chat_id": tg_chat, "caption": f"Promo ready: {Path(fp).name}"},
                        files={"video": f},
                        timeout=300
                    )
                    if not r.ok:
                        log.error(f"Telegram Error: {r.text}")
                        update_status(f"Telegram failed: {r.text}")
            except Exception as e:
                log.error(f"Telegram error: {e}")
                update_status(f"Telegram failed: {e}")

    update_status("Generating SEO and Thumbnail...")
    seo_data_dict = {}
    thumb_url = None
    try:
        from seo import SEOGenerator
        seo_gen = SEOGenerator()
        seo_pkgs = seo_gen.generate(game)
        seo_data_dict = {k: {"title": v.title, "description": v.description, "hashtags": v.hashtags} for k, v in seo_pkgs.items()}
        
        if processed_files:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(processed_files[0])
            thumb_name = f"thumb_{Path(processed_files[0]).stem}.jpg"
            thumb_path = os.path.join(cfg.RAW_DIR, thumb_name)
            clip.save_frame(str(thumb_path), t=clip.duration/2)
            thumb_url = f"/output/{thumb_name}"
            clip.close()
    except Exception as e:
        log.error(f"SEO/Thumb error: {e}")

    update_status("Complete!")
    return jsonify({
        "success": True,
        "processed_count": len(processed_files),
        "video_url": f"/output/{Path(processed_files[0]).name}" if processed_files else None,
        "seo": seo_data_dict,
        "thumb_url": thumb_url
    })

if __name__ == '__main__':
    # Run as a Desktop App locally
    import threading
    import os
    import time

    def run_server():
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
        
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    
    # Wait a moment for server to start
    time.sleep(1)
    
    # Open as a desktop app using Edge or Chrome's app mode
    log.info("Opening Desktop App Window...")
    # Tries to open Edge in app mode (looks like a native windows app). Falls back to standard browser.
    result = os.system('start msedge --app="http://127.0.0.1:5000" || start chrome --app="http://127.0.0.1:5000" || start http://127.0.0.1:5000')
    
    # Keep main thread alive
    while True:
        time.sleep(100)
