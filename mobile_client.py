"""
mobile_client.py - Run this on your Phone (Termux)
Downloads video using your Phone's mobile IP,
then processes it locally OR sends to Hugging Face cloud.
"""
import os, json, logging, threading
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
from dotenv import load_dotenv

# Load .env FIRST before reading any environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mobile_client")

app = Flask(__name__)
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
EDITED_FOLDER = Path(__file__).parent / 'downloads' / 'edited'
UPLOAD_FOLDER.mkdir(exist_ok=True)
EDITED_FOLDER.mkdir(parents=True, exist_ok=True)

# Set to your HF Space URL if you want cloud rendering
# Leave blank to use LOCAL rendering on the phone
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "")

current_status = "📱 Ready! Enter game name and tap Generate."
result_video_path = ""

def update_status(msg: str):
    global current_status
    current_status = msg
    log.info(f"STATUS: {msg}")

def send_telegram(video_path: str, game: str):
    """Send final video to Telegram."""
    from dotenv import load_dotenv
    load_dotenv()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        update_status("⚠️ Telegram not configured in .env - skipping delivery.")
        return
    try:
        update_status("📤 Sending to Telegram...")
        with open(video_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendVideo",
                data={"chat_id": tg_chat, "caption": f"🎮 {game} - AI Promo Ready!"},
                files={"video": f},
                timeout=300
            )
        if r.ok:
            update_status("✅ Video sent to Telegram!")
        else:
            update_status(f"❌ Telegram error: {r.json().get('description', r.text)}")
    except Exception as e:
        update_status(f"❌ Telegram failed: {e}")


MOBILE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>AI Video Studio 📱</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    padding: 16px;
    min-height: 100vh;
  }
  h1 {
    text-align: center;
    font-size: 1.4rem;
    font-weight: 900;
    background: linear-gradient(90deg, #00e676, #00d4ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 20px;
    padding-top: 10px;
  }
  .card {
    background: #16161f;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
    border: 1px solid #2a2a3a;
  }
  .card h2 {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #00e676;
    margin-bottom: 12px;
  }
  label {
    display: block;
    font-size: 0.75rem;
    color: #888;
    margin-bottom: 4px;
    margin-top: 10px;
  }
  input, select, textarea {
    width: 100%;
    padding: 12px;
    background: #0f0f1a;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    color: white;
    font-size: 1rem;
    font-family: 'Inter', sans-serif;
    -webkit-appearance: none;
  }
  input:focus, select:focus { outline: none; border-color: #00e676; }
  select { appearance: none; }
  
  .btn-generate {
    width: 100%;
    padding: 18px;
    background: linear-gradient(135deg, #00e676, #00d4ff);
    color: #000;
    font-size: 1.1rem;
    font-weight: 900;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    margin-top: 10px;
    letter-spacing: 1px;
  }
  .btn-generate:disabled { opacity: 0.5; }

  .status-box {
    background: #000;
    border: 1px solid #00e676;
    border-radius: 10px;
    padding: 14px;
    font-family: monospace;
    font-size: 0.85rem;
    color: #00e676;
    min-height: 80px;
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .video-card {
    display: none;
    background: #16161f;
    border: 2px solid #00e676;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
  }
  .video-card h2 {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #00e676;
    margin-bottom: 12px;
  }
  video { width: 100%; border-radius: 8px; background: #000; }
  
  .dl-btn {
    display: block;
    width: 100%;
    padding: 14px;
    border-radius: 10px;
    text-align: center;
    font-weight: 700;
    font-size: 0.95rem;
    text-decoration: none;
    margin-top: 10px;
  }
  .dl-1080 { background: #00e676; color: #000; }
  .dl-720  { background: #00d4ff; color: #000; }
  
  .seo-box {
    display: none;
    background: #16161f;
    border: 1px solid #2a2a3a;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
  }
  .seo-box h2 {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #00e676;
    margin-bottom: 12px;
  }
  .seo-title { color: #00d4ff; font-weight: 700; font-size: 0.9rem; margin-bottom: 4px; }
  .seo-desc  { font-size: 0.8rem; color: #aaa; margin-bottom: 6px; line-height: 1.4; }
  .seo-tags  { font-size: 0.75rem; color: #666; }

  .loader {
    display: none;
    text-align: center;
    padding: 10px;
    font-size: 1.5rem;
    animation: spin 1s linear infinite;
  }
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
</head>
<body>
<h1>🎮 AI Video Studio</h1>

<!-- Inputs -->
<div class="card">
  <h2>🎯 Video Settings</h2>
  <label>Game Name</label>
  <input id="game" type="text" placeholder="e.g. Free Fire, PUBG Mobile..." />
  <label>Your CPA / Landing Page Link</label>
  <input id="url" type="url" placeholder="https://yourlink.com" />
  <label>Caption Color</label>
  <select id="caption_color">
    <option value="yellow">⭐ Attractive Yellow</option>
    <option value="white">⚪ Clean White</option>
    <option value="#00e676">🟩 Neon Green</option>
    <option value="#00d4ff">🟦 Neon Cyan</option>
  </select>
  <label>Caption Position</label>
  <select id="caption_pos">
    <option value="0.70">Center Low (TikTok Style)</option>
    <option value="0.50">Dead Center</option>
    <option value="0.25">Top High</option>
    <option value="0.85">Very Bottom</option>
  </select>
</div>

<!-- Channel & Promo Tools -->
<div class="card">
  <h2>📸 Channel & Promo Tools</h2>
  <label>Channel Screenshot (shows last 5s)</label>
  <input id="screenshot" type="file" accept="image/*" />

  <label style="margin-top:14px; color:#00e676; font-size:0.8rem;">🔗 CPA Link Bar</label>
  <p style="font-size:0.75rem; color:#888; margin:4px 0 8px;">Your CPA link above will automatically be shown as a clickable bar on the video for the first 25 seconds.</p>

  <label style="color:#00e676; font-size:0.8rem;">🏷️ Custom Text Overlay</label>
  <input id="overlay_text" type="text" placeholder='e.g. "Download Now! 🔥"' style="margin-bottom:8px;" />

  <label>Overlay Position</label>
  <select id="overlay_pos">
    <option value="top">Top of Video</option>
    <option value="center">Center</option>
    <option value="bottom">Bottom</option>
  </select>
</div>

<button class="btn-generate" id="genBtn" onclick="generate()" style="margin-bottom:14px;">⚡ GENERATE VIDEO</button>

<!-- Status -->
<div class="card">
  <h2>📡 Pipeline Status</h2>
  <div class="loader" id="loader">⏳</div>
  <div class="status-box" id="statusBox">📱 Ready! Enter game name and tap Generate.</div>
</div>

<!-- Video Output -->
<div class="video-card" id="videoCard">
  <h2>🎬 Final Video</h2>
  <video id="outputVideo" controls playsinline></video>
  <a class="dl-btn dl-1080" id="dl1080" href="#" download>⬇ Download 1080p</a>
  <a class="dl-btn dl-720"  id="dl720"  href="#" download>⬇ Download 720p</a>
</div>

<!-- SEO -->
<div class="seo-box" id="seoBox">
  <h2>📈 SEO Package</h2>
  <div id="seoContent"></div>
</div>

<script>
let polling;

async function generate() {
  const game = document.getElementById('game').value.trim();
  const url = document.getElementById('url').value.trim();
  if (!game) return alert('Enter a game name!');
  if (!url)  return alert('Enter your landing link!');

  const btn = document.getElementById('genBtn');
  btn.disabled = true;
  document.getElementById('loader').style.display = 'block';
  document.getElementById('videoCard').style.display = 'none';
  document.getElementById('seoBox').style.display = 'none';

  const fd = new FormData();
  fd.append('game', game);
  fd.append('url', url);
  fd.append('caption_color', document.getElementById('caption_color').value);
  fd.append('caption_pos', document.getElementById('caption_pos').value);
  fd.append('overlay_text', document.getElementById('overlay_text').value);
  fd.append('overlay_pos',  document.getElementById('overlay_pos').value);
  const ss = document.getElementById('screenshot').files[0];
  if (ss) fd.append('screenshot', ss);

  // Start polling status
  polling = setInterval(pollStatus, 1500);

  try {
    const res = await fetch('/api/generate', { method: 'POST', body: fd });
    const data = await res.json();
    clearInterval(polling);
    document.getElementById('loader').style.display = 'none';
    btn.disabled = false;

    if (data.error) {
      setStatus('❌ ' + data.error);
      return;
    }

    // Show video if available locally
    if (data.video_url) {
      document.getElementById('outputVideo').src = data.video_url;
      document.getElementById('dl1080').href = data.video_url;
      document.getElementById('dl720').href  = data.video_url;
      document.getElementById('videoCard').style.display = 'block';
    } else {
      setStatus('✅ Done! Check your Telegram for the final video.');
    }

    // Show SEO
    if (data.seo) {
      let html = '';
      for (const [platform, pkg] of Object.entries(data.seo)) {
        html += `<div style="margin-bottom:14px; border-bottom:1px solid #222; padding-bottom:10px;">
          <div class="seo-title">${platform.toUpperCase()}</div>
          <div class="seo-desc">${pkg.title}</div>
          <div class="seo-tags">${(pkg.tags || []).slice(0,8).join(' ')}</div>
        </div>`;
      }
      document.getElementById('seoContent').innerHTML = html;
      document.getElementById('seoBox').style.display = 'block';
    }
  } catch(e) {
    clearInterval(polling);
    document.getElementById('loader').style.display = 'none';
    btn.disabled = false;
    setStatus('❌ Network Error: ' + e.message);
  }
}

async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    if (d.message) setStatus(d.message);
  } catch {}
}

function setStatus(msg) {
  document.getElementById('statusBox').textContent = msg;
}
</script>
</body>
</html>
"""

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({"message": current_status})

@app.route('/output/<filename>')
def output_file(filename):
    return send_file(str(EDITED_FOLDER / filename))

@app.route('/')
def index():
    return render_template_string(MOBILE_HTML)

@app.route('/api/generate', methods=['POST'])
def generate():
    global current_status, result_video_path
    update_status("🔍 Starting pipeline...")

    game      = request.form.get('game', '').strip()
    url       = request.form.get('url', '').strip()
    cap_color = request.form.get('caption_color', 'yellow')
    cap_pos   = float(request.form.get('caption_pos', 0.70))

    screenshot_file = request.files.get('screenshot')
    screenshot_path = ""
    if screenshot_file:
        screenshot_path = str(UPLOAD_FOLDER / secure_filename(screenshot_file.filename))
        screenshot_file.save(screenshot_path)

    # 1. Scrape with mobile IP
    from scraper import VideoScraper
    from config import Config
    cfg     = Config()
    scraper = VideoScraper(config=cfg)
    update_status(f"🌐 Searching for: {game}...")
    candidates = scraper.search(f"{game} gameplay shorts", max_results=5)

    if not candidates:
        update_status("❌ No videos found.")
        return jsonify({"error": "No videos found."}), 404

    update_status("⬇️ Downloading raw video via Mobile IP...")
    raw_path = scraper.download(candidates[0])
    if not raw_path:
        update_status("❌ Download failed. Make sure ffmpeg is installed (pkg install ffmpeg).")
        return jsonify({"error": "Download failed."}), 500

    # 2. Cloud rendering if URL set, otherwise process locally
    if CLOUD_API_URL and "replace" not in CLOUD_API_URL:
        update_status("☁️ Uploading to Cloud for AI rendering...")
        try:
            files = {'video': open(raw_path, 'rb')}
            if screenshot_path and os.path.exists(screenshot_path):
                files['screenshot'] = open(screenshot_path, 'rb')
            data = {
                'game': game, 'url': url,
                'caption_color': cap_color, 'caption_pos': str(cap_pos),
                'overlays': '[]', 'layout': '{}'
            }
            resp = requests.post(f"{CLOUD_API_URL}/api/cloud_process", data=data, files=files, timeout=600)
            if resp.ok:
                result = resp.json()
                seo = result.get("seo", {})
                update_status("✅ Cloud rendered! Check Telegram.")
                return jsonify({"success": True, "seo": seo})
            else:
                err = resp.json().get('error', resp.text[:200])
                update_status(f"❌ Cloud error: {err}")
                return jsonify({"error": err}), 500
        except Exception as e:
            update_status(f"❌ Cloud connection failed: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        # LOCAL rendering on the phone
        update_status("🎬 Processing video locally...")
        try:
            from video_processor import VideoProcessor
            from dotenv import load_dotenv
            load_dotenv()
            processor = VideoProcessor(
                elevenlabs_key=os.getenv("ELEVENLABS_API_KEY", ""),
                elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "")
            )
            out_path = processor.process(
                input_path=str(raw_path),
                game_name=game,
                channel_screenshot=screenshot_path,
                landing_url=url,
                progress_callback=lambda p, m: update_status(f"[{p}%] {m}"),
                caption_color=cap_color,
                caption_pos=cap_pos
            )
            result_video_path = out_path
        except Exception as e:
            update_status(f"❌ Processing failed: {e}")
            return jsonify({"error": str(e)}), 500

        # Deliver to Telegram in background
        threading.Thread(target=send_telegram, args=(result_video_path, game), daemon=True).start()

        # Generate SEO
        seo_data = {}
        try:
            from seo import SEOGenerator
            pkgs = SEOGenerator().generate(game)
            seo_data = {k: {"title": v.title, "desc": v.description, "tags": v.hashtags} for k, v in pkgs.items()}
        except: pass

        video_name = Path(result_video_path).name
        update_status(f"✅ Done! Video ready to download.")
        return jsonify({
            "success": True,
            "video_url": f"/output/{video_name}",
            "seo": seo_data
        })


if __name__ == '__main__':
    print("=" * 50)
    print("📱 MOBILE CLIENT STARTED")
    print("Open your phone browser: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
