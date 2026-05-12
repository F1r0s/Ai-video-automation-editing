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
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max for video uploads

# Make sure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return jsonify({"status": "AI Video Automation Cloud API is running. Ready for requests from Desktop App."})

def update_status(msg):
    try:
        with open("status.json", "w") as f:
            json.dump({"message": msg}, f)
    except:
        pass


def _send_videos_to_telegram(processed_files, caption_prefix="Promo ready"):
    from datetime import datetime
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")

    if not tg_token or not tg_chat:
        err_msg = "Telegram not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        update_status(f"⚠ {err_msg}")
        log.warning(err_msg)
        return

    if not processed_files:
        update_status("⚠ No files to send to Telegram.")
        return

    import requests

    tg_batch_start = datetime.now()
    update_status(f"📱 Sending {len(processed_files)} video(s) to Telegram...")
    log.info(f"Telegram: Starting send of {len(processed_files)} file(s)")

    for idx, fp in enumerate(processed_files, 1):
        try:
            tg_send_start = datetime.now()
            file_size_mb = os.path.getsize(fp) / (1024 * 1024)
            
            log.info(f"Telegram: [{idx}/{len(processed_files)}] Sending {Path(fp).name} ({file_size_mb:.1f}MB)...")
            update_status(f"📱 [{idx}/{len(processed_files)}] Uploading to Telegram... ({file_size_mb:.1f}MB)")
            
            with open(fp, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendVideo",
                    data={"chat_id": tg_chat, "caption": f"{caption_prefix}: {Path(fp).name}"},
                    files={"video": f},
                    timeout=300,
                )
            tg_send_end = datetime.now()
            send_duration = (tg_send_end - tg_send_start).total_seconds()
            
            if r.ok:
                log.info(f"✓ Telegram {idx}/{len(processed_files)} sent [{tg_send_end.isoformat()}] - {send_duration:.1f}s")
                update_status(f"✅ Telegram [{idx}/{len(processed_files)}] sent successfully! ({send_duration:.1f}s)")
            else:
                err_text = r.text[:200] if r.text else f"HTTP {r.status_code}"
                log.error(f"✗ Telegram Error: {err_text}")
                update_status(f"❌ Telegram failed ({r.status_code}): {err_text}")
        except requests.Timeout as e:
            log.error(f"Telegram timeout: {e}")
            update_status(f"❌ Telegram timeout: {e}")
        except Exception as e:
            log.error(f"Telegram error: {type(e).__name__}: {e}")
            update_status(f"❌ Telegram error: {type(e).__name__}: {e}")

    tg_batch_end = datetime.now()
    total_duration = (tg_batch_end - tg_batch_start).total_seconds()
    log.info(f"Telegram batch complete: {total_duration:.1f}s total for {len(processed_files)} file(s)")
    update_status(f"✅ All Telegram deliveries complete ({total_duration:.1f}s)")


def _make_720p_copy(source_path: str) -> str:
    """Create a lower-resolution 720p copy next to the finished 1080p render."""
    source = Path(source_path)
    target = source.with_name(f"{source.stem}_720p{source.suffix}")

    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(str(source))
        try:
            clip.resize(height=720).write_videofile(
                str(target),
                codec="libx264",
                audio_codec="aac",
                fps=30,
                preset="fast",
                threads=4,
                pix_fmt="yuv420p",
                logger=None,
            )
        finally:
            clip.close()

        return str(target)
    except Exception as exc:
        log.warning(f"720p conversion failed for {source.name}: {exc}")
        return str(source)


def _output_url(path_value: str) -> str:
    return f"/output/{Path(path_value).name}"

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
    return jsonify({"success": True})

@app.route('/api/generate', methods=['POST'])
def generate():
    # Reset status
    update_status("Starting pipeline...")

    game = request.form.get('game', '').strip()
    url = request.form.get('url', '').strip()
    max_v = int(request.form.get('max', 3))
    cap_color = request.form.get('caption_color', 'yellow')
    cap_pos = float(request.form.get('caption_pos', 0.58))
    link_color = request.form.get('landing_link_color', '#64dcff')  # cyan default
    link_font = request.form.get('link_font', 'Montserrat-Bold')
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
    req_el_key = request.form.get('elevenlabs_key', '').strip()
    req_el_voice = request.form.get('elevenlabs_voice_id', '').strip()
    
    processor = VideoProcessor(
        elevenlabs_key=req_el_key or os.getenv("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=req_el_voice or os.getenv("ELEVENLABS_VOICE_ID", ""),
        groq_key=os.getenv("GROQ_API_KEY", "")
    )

    log.info(f"Starting web pipeline for: {game}")
    update_status(f"Searching web for: {game}...")
    search_term = game if "mod" in game.lower() else f"{game} MOD"
    candidates = scraper.search(f"{search_term} gameplay", max_results=max_v * 3)
    
    if not candidates:
        update_status("Error: No videos found to scrape.")
        return jsonify({"error": "No videos found to scrape."}), 404

    update_status(f"✓ Found {len(candidates)} candidate video(s). Now downloading...")
    videos = candidates[:max_v]
    processed_files = []
    downloaded_count = 0

    for idx, meta in enumerate(videos, 1):
        log.info(f"Downloading video {idx}/{len(videos)}...")
        update_status(f"Downloading candidate {idx}/{len(videos)}...")
        raw_path = scraper.download(meta)
        if not raw_path:
            update_status(f"  ⚠ Download {idx} failed, skipping...")
            continue
        
        downloaded_count += 1
        update_status(f"  ✓ Download {idx}/{len(videos)} succeeded. Processing...")

        try:
            update_status(f"Rendering video {idx}/{len(videos)}... (this takes a few minutes)")
            out_path = processor.process(
                input_path=str(raw_path),
                game_name=game,
                channel_screenshot=screenshot_path,
                landing_url=url,
                progress_callback=lambda p, m: update_status(f"[{p}%] {m}"),
                overlay_data=overlays,
                layout=layout,
                caption_color=cap_color,
                caption_pos=cap_pos,
                landing_link_color=link_color,
                link_font_name=link_font
            )
            processed_files.append(out_path)
            log.info(f"Processed successfully: {out_path}")
        except Exception as e:
            update_status(f"Error processing video: {e}")
            log.error(f"Error processing video: {e}")

    if not processed_files:
        if downloaded_count:
            return jsonify({
                "success": False,
                "downloaded_count": downloaded_count,
                "processed_count": 0,
                "error": "Videos were downloaded, but processing failed before any final video was produced. Check terminal logs."
            }), 500
        return jsonify({
            "success": False,
            "downloaded_count": 0,
            "processed_count": 0,
            "error": "Pipeline failed. No videos were successfully processed. Check terminal logs."
        }), 500

    log.info("Sending to Telegram synchronously...")
    _send_videos_to_telegram(processed_files.copy(), "Promo ready")

    video_1080p = str(processed_files[0])
    video_720p = _make_720p_copy(video_1080p)

    update_status("Rendering complete. Preview updated. Telegram sending in background...")

    return jsonify({
        "success": True,
        "downloaded_count": downloaded_count,
        "processed_count": len(processed_files),
        "video_path": video_1080p,
        "video_url": _output_url(video_1080p),
        "video_url_1080": _output_url(video_1080p),
        "video_url_720": _output_url(video_720p),
        "seo": {},
        "thumb_url": None
    })

@app.route('/api/cloud_process', methods=['POST'])
def cloud_process():
    """
    Endpoint for the Mobile/Termux client. 
    Receives raw video, processes it with AI, and sends to Telegram.
    Supports both legacy and reward-first modes.
    """
    game = request.form.get('game', '').strip()
    url = request.form.get('url', '').strip()
    overlays_json = request.form.get('overlays', '[]')
    layout_json = request.form.get('layout', '{}')
    cap_color = request.form.get('caption_color', 'yellow')
    cap_pos = float(request.form.get('caption_pos', 0.58))
    link_color = request.form.get('landing_link_color', '#64dcff')
    link_font = request.form.get('link_font', 'Montserrat-Bold')
    mode = request.form.get('mode', 'legacy')
    
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
        
    video_file = request.files['video']
    screenshot_file = request.files.get('screenshot')
    recording_file = request.files.get('manual_recording')
    
    # Save uploaded raw video
    raw_path = Path(app.config['UPLOAD_FOLDER']) / secure_filename(video_file.filename or 'mobile_upload.mp4')
    video_file.save(str(raw_path))
    
    # Save screenshot if provided
    screenshot_path = str(Path(app.config['UPLOAD_FOLDER']) / "mobile_ss.png")
    if screenshot_file:
        screenshot_file.save(screenshot_path)
    
    # Save manual recording if provided (reward-first mode)
    recording_path = ""
    if recording_file:
        recording_path = str(Path(app.config['UPLOAD_FOLDER']) / secure_filename(recording_file.filename or 'manual_recording.mp4'))
        recording_file.save(recording_path)
    
    # Process Video
    req_el_key = request.form.get('elevenlabs_key', '').strip()
    req_el_voice = request.form.get('elevenlabs_voice_id', '').strip()
    req_groq_key = request.form.get('groq_key', '').strip()
    
    processor = VideoProcessor(
        elevenlabs_key=req_el_key or os.getenv("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=req_el_voice or os.getenv("ELEVENLABS_VOICE_ID", ""),
        groq_key=req_groq_key or os.getenv("GROQ_API_KEY", "")
    )
    
    try:
        if mode == 'reward_first' and recording_path:
            log.info(f"Cloud: Reward-First mode for {game}")
            out_path = processor.process_reward_first(
                scraped_video_path=str(raw_path),
                manual_recording_path=recording_path,
                game_name=game,
                channel_screenshot=screenshot_path if screenshot_file else "",
                landing_url=url,
                overlay_data=json.loads(overlays_json),
                layout=json.loads(layout_json),
                caption_color=cap_color,
                caption_pos=cap_pos,
                landing_link_color=link_color,
                link_font_name=link_font,
                progress_callback=lambda p, m: log.info(f"Cloud Reward [{p}%]: {m}"),
            )
        else:
            log.info(f"Cloud: Legacy mode for {game}")
            out_path = processor.process(
                input_path=str(raw_path),
                game_name=game,
                channel_screenshot=screenshot_path if screenshot_file else "",
                landing_url=url,
                progress_callback=lambda p, m: log.info(f"Cloud Process [{p}%]: {m}"),
                overlay_data=json.loads(overlays_json),
                layout=json.loads(layout_json),
                caption_color=cap_color,
                caption_pos=cap_pos,
                landing_link_color=link_color,
                link_font_name=link_font
            )
    except Exception as e:
        log.error(f"Cloud processing crashed: {e}")
        return jsonify({"error": str(e)}), 500
        
    if out_path:
        log.info("Sending to Telegram synchronously...")
        _send_videos_to_telegram([out_path], "Cloud Render Complete")

    video_1080p = str(out_path)
    video_720p = _make_720p_copy(video_1080p)

    update_status("Rendering complete. Preview updated. Telegram sending in background...")

    return jsonify({
        "success": True,
        "video_path": str(out_path),
        "video_url": _output_url(video_1080p),
        "video_url_1080": _output_url(video_1080p),
        "video_url_720": _output_url(video_720p),
        "seo": {}
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
