/* ═══════════════════════════════════════════════════════════════
   app.js — AI Video Automation Studio Web Interface
   Mirrors the desktop app.py logic 1-to-1
═══════════════════════════════════════════════════════════════ */

/* ─── STATE ──────────────────────────────────────────────────────── */
let state = {
  maxVideos: 5,
  screenshotFile: null,
  screenshotDataUrl: null,
  recordingFile: null,
  processing: false,
  paused: false,
  progress: 0,
  searchResults: [],
  selectedResultIdx: -1,
  seoPackages: {},
  lastRenderedUrl: null,
  renderMode: 'local',     // 'local' | 'cloud'
  sourceMode: 'search',    // 'search' | 'url'
  safeZoneVisible: false,
};

/* ─── CANVAS STATE ───────────────────────────────────────────────── */
const canvas   = document.getElementById('previewCanvas');
const ctx      = canvas.getContext('2d');
const PV_W     = 300;
const PV_H     = 534;

let items         = [];       // array of canvas items
let selectedItem  = null;
let isDragging    = false;
let dragMode      = null;     // 'move' | 'scale' | 'rotate'
let dragStart     = { x: 0, y: 0 };
let dragStartItem = { x: 0, y: 0, scale: 1 };
let startDist     = 1;
let startAngle    = 0;
let startRotation = 0;
let animFrameId   = null;

const HANDLE_R    = 7;

/* ─── CANVAS ITEM CLASS ─────────────────────────────────────────── */
class CanvasItem {
  constructor(kind, x, y, text = '', imgSrc = '') {
    this.kind     = kind;
    this.x        = x;
    this.y        = y;
    this.scale    = 1.0;
    this.rotation = 0;
    this.text     = text;
    this.imgSrc   = imgSrc;
    this.img      = null;

    if ((kind === 'screenshot' || kind === 'custom_img') && imgSrc) {
      const i = new Image();
      i.onload = () => { this.img = i; requestRender(); };
      i.src = imgSrc;
    }
  }

  get baseSize() {
    const sizes = { circle: 80, arrow: 80, finger: 72, cartoon: 80, screenshot: null };
    return sizes[this.kind] || 64;
  }
}

/* ─── CANVAS RENDER ─────────────────────────────────────────────── */
function requestRender() {
  if (!animFrameId) animFrameId = requestAnimationFrame(renderCanvas);
}

function renderCanvas() {
  animFrameId = null;
  ctx.clearRect(0, 0, PV_W, PV_H);

  // Background gradient
  const grad = ctx.createLinearGradient(0, 0, 0, PV_H);
  grad.addColorStop(0, '#0a0a16');
  grad.addColorStop(1, '#0d0d1a');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, PV_W, PV_H);

  // Draw items
  for (const item of items) {
    if (item.kind === 'safe_zone') { drawSafeZone(); continue; }
    drawItem(item);
  }

  // Draw selection handles on selected item
  if (selectedItem && selectedItem.kind !== 'safe_zone') {
    drawHandles(selectedItem);
  }

  // Keep animating for sticker animations
  animFrameId = requestAnimationFrame(renderCanvas);
}

function drawItem(item) {
  ctx.save();
  ctx.translate(item.x, item.y);
  ctx.rotate((item.rotation * Math.PI) / 180);

  switch (item.kind) {
    case 'screenshot':
      drawScreenshot(item);
      break;
    case 'link':
      drawLink(item);
      break;
    case 'circle':
      drawCircle(item);
      break;
    case 'arrow':
      drawArrow(item);
      break;
    case 'finger':
      drawFinger(item);
      break;
    case 'cartoon':
      drawCartoon(item);
      break;
    case 'text':
      drawTextSticker(item);
      break;
  }
  ctx.restore();
}

function drawScreenshot(item) {
  if (!item.img) {
    ctx.strokeStyle = '#00d4ff40';
    ctx.lineWidth = 1;
    ctx.strokeRect(-item.scale * 60, -item.scale * 60, item.scale * 120, item.scale * 120);
    return;
  }
  const s  = item.scale;
  const w  = item.img.width * s;
  const h  = item.img.height * s;
  ctx.drawImage(item.img, -w / 2, -h / 2, w, h);
}

function drawLink(item) {
  const url    = item.text;
  const s      = Math.max(0.5, item.scale);
  const fs     = Math.max(9, 13 * s);
  const color  = document.getElementById('linkColorPicker').value || '#64dcff';
  ctx.font     = `bold ${fs}px Inter, Arial`;
  const tw     = ctx.measureText(url).width;
  const th     = fs + 8;
  const pad    = 8 * s;
  ctx.fillStyle = 'rgba(0,0,0,0.65)';
  roundRect(ctx, -tw / 2 - pad, -th / 2, tw + pad * 2, th + 4, 8 * s);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.textAlign   = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(url, 0, 2);
}

function drawCircle(item) {
  const r  = 36 * item.scale;
  const t  = Date.now() / 1000;
  const pulse = 1 + 0.12 * Math.sin(t * 10);
  const rp = r * pulse;
  ctx.strokeStyle = '#ff1744';
  ctx.lineWidth   = Math.max(2, 4 * item.scale);
  ctx.shadowColor = '#ff1744';
  ctx.shadowBlur  = 12;
  ctx.beginPath();
  ctx.ellipse(0, 0, rp, rp * 0.75, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function drawArrow(item) {
  const s  = item.scale;
  const t  = Date.now() / 1000;
  const bounce = 8 * Math.sin(t * 8);
  const size = 28 * s;
  ctx.fillStyle = '#ff1744';
  ctx.shadowColor = '#ff1744';
  ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.moveTo(0, bounce - size);
  ctx.lineTo(-size * 0.7, bounce);
  ctx.lineTo(0, bounce - size * 0.3);
  ctx.lineTo(size * 0.7, bounce);
  ctx.closePath();
  ctx.fill();
  ctx.shadowBlur = 0;
}

function drawFinger(item) {
  const s  = item.scale;
  const t  = Date.now() / 1000;
  const bounce = 8 * Math.sin(t * 8);
  ctx.font = `${Math.round(36 * s)}px Segoe UI Emoji, sans-serif`;
  ctx.textAlign   = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowColor = '#ff1744';
  ctx.shadowBlur = 8;
  ctx.fillText('☝️', 0, bounce);
  ctx.shadowBlur = 0;
}

function drawCartoon(item) {
  const s  = item.scale;
  const t  = Date.now() / 1000;
  const pulse = 1 + 0.12 * Math.sin(t * 10);
  const r = 28 * s * pulse;
  const grd = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
  grd.addColorStop(0, '#7c3aed');
  grd.addColorStop(1, '#4a00e0');
  ctx.fillStyle = grd;
  ctx.shadowColor = '#7c3aed';
  ctx.shadowBlur = 20;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2 * s;
  ctx.stroke();
  ctx.font = `${Math.round(18 * s)}px Segoe UI Emoji`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowBlur = 0;
  ctx.fillStyle = '#fff';
  ctx.fillText('★', 0, 1);
}

function drawTextSticker(item) {
  const s  = Math.max(0.5, item.scale);
  const t  = Date.now() / 1000;
  const pulse = 1 + 0.1 * Math.sin(t * 10);
  const fs = Math.round(13 * s * pulse);
  ctx.font = `bold ${fs}px Inter, Arial`;
  const tw = ctx.measureText(item.text).width;
  const th = fs + 10;
  const pad = 10;
  ctx.fillStyle = 'rgba(0,0,0,0.85)';
  roundRect(ctx, -tw / 2 - pad, -th / 2 - 2, tw + pad * 2, th + 4, 8);
  ctx.fill();
  ctx.fillStyle = '#ffeb3b';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowColor = '#ff9800';
  ctx.shadowBlur = 6;
  ctx.fillText(item.text, 0, 2);
  ctx.shadowBlur = 0;
}

/* ─── SAFE ZONE ──────────────────────────────────────────────────── */
function drawSafeZone() {
  ctx.save();

  // Top dead zone
  ctx.fillStyle = 'rgba(255,51,0,0.18)';
  ctx.fillRect(0, 0, PV_W, PV_H * 0.12);
  ctx.fillStyle = '#ff9980';
  ctx.font = 'bold 8px Inter';
  ctx.textAlign = 'center';
  ctx.fillText('⛔ DEAD ZONE — Platform UI', PV_W / 2, PV_H * 0.06);

  // Bottom dead zone
  ctx.fillStyle = 'rgba(255,51,0,0.18)';
  ctx.fillRect(0, PV_H * 0.80, PV_W, PV_H * 0.20);
  ctx.fillStyle = '#ff9980';
  ctx.font = 'bold 8px Inter';
  ctx.textAlign = 'center';
  ctx.fillText('⛔ DEAD ZONE — Buttons + Caption', PV_W / 2, PV_H * 0.90);

  // Right dead zone
  ctx.fillStyle = 'rgba(255,102,0,0.18)';
  ctx.fillRect(PV_W * 0.82, PV_H * 0.12, PV_W * 0.18, PV_H * 0.68);
  ctx.fillStyle = '#ffcc99';
  ctx.font = 'bold 7px Inter';
  ctx.textAlign = 'center';
  ctx.fillText('⛔', PV_W * 0.91, PV_H * 0.42);
  ctx.fillText('BTNS', PV_W * 0.91, PV_H * 0.50);

  // Content zone guide
  ctx.strokeStyle = '#00aaff';
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 3]);
  ctx.strokeRect(0, PV_H * 0.12, PV_W * 0.82, PV_H * 0.43);
  ctx.fillStyle = '#00aaff';
  ctx.font = 'bold 7px Inter';
  ctx.textAlign = 'center';
  ctx.fillText('📸 SCREENSHOT / MAIN CONTENT', PV_W * 0.41, PV_H * 0.34);

  // Caption zone
  ctx.strokeStyle = '#00ff88';
  ctx.strokeRect(0, PV_H * 0.55, PV_W * 0.82, PV_H * 0.20);
  ctx.fillStyle = '#00ff88';
  ctx.fillText('✅ CAPTION ZONE', PV_W * 0.41, PV_H * 0.65);

  // CPA link zone
  ctx.strokeStyle = '#ffdd00';
  ctx.strokeRect(0, PV_H * 0.75, PV_W * 0.82, PV_H * 0.05);
  ctx.fillStyle = '#ffdd00';
  ctx.fillText('🔗 CPA LINK / CTA BAR', PV_W * 0.41, PV_H * 0.775);

  ctx.setLineDash([]);
  ctx.restore();
}

/* ─── CAPTION PREVIEW ────────────────────────────────────────────── */
function drawCaptionPreview() {
  const pos   = parseFloat(document.getElementById('captionPos').value) || 0.58;
  const color = document.getElementById('captionColor').value || 'yellow';
  const y     = PV_H * pos;

  const colorMap = { yellow: '#ffd600', white: '#ffffff', green: '#00e676', cyan: '#00d4ff' };
  const fillColor = colorMap[color] || '#ffd600';

  const text = 'Llama 3 Generated Subtitle';
  const fs   = 15;
  ctx.save();
  ctx.font   = `bold ${fs}px Inter, Arial`;
  const tw   = ctx.measureText(text).width;
  const th   = fs + 10;
  ctx.fillStyle = 'rgba(17,17,17,0.85)';
  roundRect(ctx, (PV_W - tw) / 2 - 8, y - th / 2 - 2, tw + 16, th + 4, 8);
  ctx.fill();
  ctx.fillStyle     = fillColor;
  ctx.textAlign     = 'center';
  ctx.textBaseline  = 'middle';
  ctx.shadowColor   = 'rgba(0,0,0,0.8)';
  ctx.shadowBlur    = 4;
  ctx.fillText(text, PV_W / 2, y + 2);
  ctx.shadowBlur = 0;
  ctx.restore();
}

/* ─── SELECTION HANDLES ──────────────────────────────────────────── */
function getItemBbox(item) {
  // Approximate bounding box (axis-aligned, ignoring rotation for simplicity)
  let hw = 40, hh = 40;
  if (item.kind === 'screenshot' && item.img) {
    hw = (item.img.width  * item.scale) / 2;
    hh = (item.img.height * item.scale) / 2;
  } else if (item.kind === 'link') {
    const fs = Math.max(9, 13 * item.scale);
    ctx.font = `bold ${fs}px Inter`;
    hw = ctx.measureText(item.text).width / 2 + 16;
    hh = fs / 2 + 8;
  } else if (item.kind === 'text') {
    const fs = Math.round(13 * item.scale);
    ctx.font = `bold ${fs}px Inter`;
    hw = ctx.measureText(item.text).width / 2 + 14;
    hh = fs / 2 + 8;
  } else {
    hw = hh = (item.baseSize || 40) * item.scale / 2 + 4;
  }
  return { x1: item.x - hw, y1: item.y - hh, x2: item.x + hw, y2: item.y + hh };
}

function drawHandles(item) {
  const b = getItemBbox(item);
  const pad = 4;
  const x1 = b.x1 - pad, y1 = b.y1 - pad;
  const x2 = b.x2 + pad, y2 = b.y2 + pad;

  // Selection rect
  ctx.save();
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth   = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  ctx.setLineDash([]);

  // 4 corners
  for (const [cx, cy] of [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]) {
    ctx.beginPath();
    ctx.arc(cx, cy, HANDLE_R, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#00d4ff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // Rotation handle
  const hx = (x1 + x2) / 2, hy = y1 - 22;
  ctx.setLineDash([2, 2]);
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo((x1+x2)/2, y1); ctx.lineTo(hx, hy); ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(hx, hy, HANDLE_R, 0, Math.PI * 2);
  ctx.fillStyle = '#00d4ff';
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.restore();
}

function getCorners(item) {
  const b = getItemBbox(item);
  const pad = 4;
  const x1 = b.x1 - pad, y1 = b.y1 - pad;
  const x2 = b.x2 + pad, y2 = b.y2 + pad;
  return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]];
}
function getRotHandle(item) {
  const b = getItemBbox(item);
  const pad = 4;
  const x1 = b.x1 - pad, y1 = b.y1 - pad;
  const x2 = b.x2 + pad;
  return [(x1+x2)/2, y1 - 22];
}

function hitPoint(ax, ay, bx, by, r) {
  return Math.hypot(ax - bx, ay - by) <= r + 4;
}

/* ─── CANVAS EVENTS ──────────────────────────────────────────────── */
canvas.addEventListener('mousedown', onCanvasMousedown);
canvas.addEventListener('mousemove', onCanvasMousemove);
canvas.addEventListener('mouseup',   onCanvasMouseup);
canvas.addEventListener('dblclick',  onCanvasDblClick);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Delete' && selectedItem) deleteSelected();
});

function getCanvasPos(e) {
  const r = canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

function onCanvasMousedown(e) {
  const pos = getCanvasPos(e);

  // Check rotation handle
  if (selectedItem) {
    const [rhx, rhy] = getRotHandle(selectedItem);
    if (hitPoint(pos.x, pos.y, rhx, rhy, HANDLE_R)) {
      dragMode     = 'rotate';
      startAngle   = Math.atan2(pos.y - selectedItem.y, pos.x - selectedItem.x) * 180 / Math.PI;
      startRotation = selectedItem.rotation;
      isDragging    = true;
      return;
    }
    // Check scale handles (corners)
    for (const [cx, cy] of getCorners(selectedItem)) {
      if (hitPoint(pos.x, pos.y, cx, cy, HANDLE_R)) {
        dragMode   = 'scale';
        startDist  = Math.hypot(pos.x - selectedItem.x, pos.y - selectedItem.y) || 1;
        dragStartItem = { scale: selectedItem.scale };
        isDragging = true;
        return;
      }
    }
  }

  // Hit test items (top-most first)
  let clicked = null;
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === 'safe_zone') continue;
    const b = getItemBbox(item);
    if (pos.x >= b.x1 && pos.x <= b.x2 && pos.y >= b.y1 && pos.y <= b.y2) {
      clicked = item; break;
    }
  }

  selectedItem = clicked;
  if (clicked) {
    dragMode      = 'move';
    isDragging    = true;
    dragStart     = pos;
    dragStartItem = { x: clicked.x, y: clicked.y };
  }
}

function onCanvasMousemove(e) {
  if (!isDragging || !selectedItem) return;
  const pos = getCanvasPos(e);

  if (dragMode === 'move') {
    selectedItem.x = dragStartItem.x + (pos.x - dragStart.x);
    selectedItem.y = dragStartItem.y + (pos.y - dragStart.y);
  } else if (dragMode === 'scale') {
    const dist  = Math.hypot(pos.x - selectedItem.x, pos.y - selectedItem.y) || 1;
    const ratio = dist / startDist;
    selectedItem.scale = Math.max(0.1, Math.min(10, dragStartItem.scale * ratio));
  } else if (dragMode === 'rotate') {
    const angle  = Math.atan2(pos.y - selectedItem.y, pos.x - selectedItem.x) * 180 / Math.PI;
    selectedItem.rotation = (startRotation + angle - startAngle) % 360;
  }
}

function onCanvasMouseup() {
  isDragging = false;
  dragMode   = null;
}

function onCanvasDblClick(e) {
  // Double-click on result list item handled elsewhere;
  // here it deselects
  selectedItem = null;
}

/* ─── CANVAS ITEM MANAGEMENT ─────────────────────────────────────── */
function addSticker(kind) {
  const item = new CanvasItem(kind, PV_W / 2, Math.round(PV_H * 0.12));
  items.push(item);
  selectedItem = item;
}

function addTextSticker(text) {
  const item = new CanvasItem('text', PV_W / 2, Math.round(PV_H * 0.12), text);
  items.push(item);
  selectedItem = item;
}

function deleteSelected() {
  if (!selectedItem) return;
  const idx = items.indexOf(selectedItem);
  if (idx !== -1) items.splice(idx, 1);
  selectedItem = null;
}

function clearStickers() {
  items = items.filter(i => i.kind === 'screenshot' || i.kind === 'link' || i.kind === 'safe_zone');
  selectedItem = null;
}

function toggleSafeZone() {
  const idx = items.findIndex(i => i.kind === 'safe_zone');
  if (idx !== -1) {
    items.splice(idx, 1);
    state.safeZoneVisible = false;
  } else {
    items.push(new CanvasItem('safe_zone', PV_W / 2, PV_H / 2));
    state.safeZoneVisible = true;
  }
}

/* ─── SCREENSHOT HANDLING ────────────────────────────────────────── */
function onScreenshot(input) {
  const file = input.files[0];
  if (!file) return;
  state.screenshotFile = file;
  document.getElementById('ssName').textContent = file.name;

  const reader = new FileReader();
  reader.onload = (e) => {
    state.screenshotDataUrl = e.target.result;
    // Remove old screenshot
    const idx = items.findIndex(i => i.kind === 'screenshot');
    if (idx !== -1) items.splice(idx, 1);

    const ssItem = new CanvasItem('screenshot', PV_W / 2, PV_H / 2, '', e.target.result);
    ssItem.scale = 1.0; // will auto-fit once image loads
    ssItem.img = new Image();
    ssItem.img.onload = () => {
      // Auto-fit scale
      let scale = PV_W / ssItem.img.width;
      if (ssItem.img.height * scale > PV_H + 200) scale = (PV_H + 200) / ssItem.img.height;
      ssItem.scale = scale;
    };
    ssItem.img.src = e.target.result;
    items.unshift(ssItem); // insert at bottom
    selectedItem = ssItem;
    // Hide placeholder
    document.getElementById('canvasPlaceholder').classList.add('hidden');
    updateLinkOverlay();
  };
  reader.readAsDataURL(file);
}

function onRecording(input) {
  const file = input.files[0];
  if (!file) return;
  state.recordingFile = file;
  document.getElementById('recName').textContent = file.name;
  log(`Screen recording selected: ${file.name}`, 'info');
}

/* ─── LINK OVERLAY ───────────────────────────────────────────────── */
function onLinkChange() {
  updateLinkOverlay();
}

function updateLinkOverlay() {
  const url = document.getElementById('landingUrl').value.trim();
  const idx = items.findIndex(i => i.kind === 'link');
  if (url) {
    if (idx === -1) {
      items.push(new CanvasItem('link', PV_W / 2, PV_H - 20, url));
    } else {
      items[idx].text = url;
    }
  } else {
    if (idx !== -1) items.splice(idx, 1);
  }
}

/* ─── LINK COLOR ─────────────────────────────────────────────────── */
function onLinkColorChange() {
  const val = document.getElementById('linkColorPicker').value;
  document.getElementById('linkColorHex').value = val;
}
function onLinkHexChange() {
  const val = document.getElementById('linkColorHex').value;
  if (/^#[0-9a-fA-F]{6}$/.test(val)) {
    document.getElementById('linkColorPicker').value = val;
  }
}

/* ─── CAPTION PREVIEW UPDATE ─────────────────────────────────────── */
function updateCaptionPreview() {
  // Render loop handles this automatically
}

/* ─── SPINNER ────────────────────────────────────────────────────── */
function changeMax(delta) {
  state.maxVideos = Math.max(1, Math.min(30, state.maxVideos + delta));
  document.getElementById('maxVal').textContent = state.maxVideos;
}

/* ─── SETTINGS TOGGLE ────────────────────────────────────────────── */
function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  panel.classList.toggle('hidden');
}

/* ─── RENDER MODE ────────────────────────────────────────────────── */
function onRenderModeChange() {
  state.renderMode = document.querySelector('input[name="renderMode"]:checked').value;
  const cloudUrlRow = document.getElementById('cloudUrlRow');
  if (state.renderMode === 'cloud') {
    cloudUrlRow.classList.remove('hidden');
  } else {
    cloudUrlRow.classList.add('hidden');
  }
}

/* ─── SOURCE MODE ────────────────────────────────────────────────── */
function onSourceModeChange() {
  state.sourceMode = document.querySelector('input[name="sourceMode"]:checked').value;
  const directPanel = document.getElementById('directUrlPanel');
  const searchCard  = document.getElementById('searchCard');
  if (state.sourceMode === 'url') {
    directPanel.classList.remove('hidden');
    searchCard.classList.add('hidden');
  } else {
    directPanel.classList.add('hidden');
    searchCard.classList.remove('hidden');
  }
}

/* ─── PASTE URL ──────────────────────────────────────────────────── */
async function pasteUrl() {
  try {
    const text = await navigator.clipboard.readText();
    document.getElementById('directUrl').value = text;
  } catch {
    toast('⚠ Clipboard access denied. Paste manually.');
  }
}

/* ─── SEARCH ─────────────────────────────────────────────────────── */
function onSearch() {
  const game = document.getElementById('gameName').value.trim();
  if (!game) { toast('⚠ Enter a game name first!'); return; }

  const btn = document.getElementById('searchBtn');
  btn.disabled  = true;
  btn.textContent = '🔍 Searching...';

  const list = document.getElementById('resultsList');
  list.innerHTML = '<div class="results-placeholder">Searching...</div>';
  state.searchResults = [];
  state.selectedResultIdx = -1;

  // Determine which API endpoint to use
  const apiBase = getApiBase();
  if (!apiBase) {
    // Demo mode — generate fake results
    setTimeout(() => {
      const fakeTitles = [
        { title: `${game} MOD Unlimited Money 2025`, url: 'https://youtube.com/shorts/demo1', ratio: '9:16', dur: 28 },
        { title: `${game} HACK Gameplay Tutorial`, url: 'https://youtube.com/shorts/demo2', ratio: '9:16', dur: 22 },
        { title: `${game} Best Settings Guide`, url: 'https://youtube.com/watch?v=demo3', ratio: '16:9', dur: 180 },
        { title: `${game} Season 10 New Update`, url: 'https://youtube.com/shorts/demo4', ratio: '9:16', dur: 30 },
        { title: `${game} Pro Tips 2025`, url: 'https://youtube.com/watch?v=demo5', ratio: '16:9', dur: 240 },
      ];
      state.searchResults = fakeTitles;
      renderResultsList(fakeTitles);
      btn.disabled = false;
      btn.textContent = '🔍 SEARCH';
      setStatus(`Found ${fakeTitles.length} results.`, 'ok');
    }, 1200);
    return;
  }

  // Real API call
  const form = new FormData();
  form.append('game', game);
  form.append('max', state.maxVideos);

  fetch(`${apiBase}/api/search`, { method: 'POST', body: form })
    .then(r => r.json())
    .then(data => {
      btn.disabled = false;
      btn.textContent = '🔍 SEARCH';
      if (data.results) {
        state.searchResults = data.results;
        renderResultsList(data.results);
        setStatus(`Found ${data.results.length} results.`, 'ok');
      } else {
        list.innerHTML = `<div class="results-placeholder" style="color:var(--red)">Error: ${data.error || 'No results'}</div>`;
        setStatus('Search failed.', 'err');
      }
    })
    .catch(err => {
      btn.disabled = false;
      btn.textContent = '🔍 SEARCH';
      list.innerHTML = `<div class="results-placeholder" style="color:var(--red)">Network error. Running in demo mode.</div>`;
      log(`Search error: ${err.message}`, 'err');
    });
}

function renderResultsList(results) {
  const list       = document.getElementById('resultsList');
  const ratioFilter = document.getElementById('ratioFilter').value;
  list.innerHTML   = '';

  let visible = results;
  if (ratioFilter === '9:16') visible = results.filter(r => r.ratio === '9:16');
  else if (ratioFilter === '16:9') visible = results.filter(r => r.ratio === '16:9');

  if (!visible.length) {
    list.innerHTML = `<div class="results-placeholder">No results for filter "${ratioFilter}"</div>`;
    return;
  }

  visible.forEach((r, i) => {
    const div = document.createElement('div');
    div.className = 'result-item ' + (r.ratio === '9:16' ? 'ratio-916' : 'ratio-169');
    const dur = r.dur ? `[${r.dur}s] ` : '';
    const shortUrl = (r.url || '').substring(0, 50) + ((r.url || '').length > 50 ? '...' : '');
    div.textContent = `[${r.ratio || '?'}] ${dur}${r.title}  |  ${shortUrl}`;
    div.title = r.url || r.title;
    div.dataset.idx = i;
    div.addEventListener('click', () => selectResult(i, div));
    div.addEventListener('dblclick', () => { selectResult(i, div); openSelectedInBrowser(); });
    list.appendChild(div);
  });

  // Auto-select first
  if (visible.length > 0) {
    selectResult(0, list.firstChild);
  }
}

function selectResult(idx, el) {
  state.selectedResultIdx = idx;
  document.querySelectorAll('.result-item').forEach(d => d.classList.remove('selected'));
  if (el) el.classList.add('selected');
}

function openSelectedInBrowser() {
  const idx = state.selectedResultIdx;
  if (idx < 0 || idx >= state.searchResults.length) {
    toast('⚠ Select a video from the list first.');
    return;
  }
  const url = state.searchResults[idx].url || state.searchResults[idx].webpage_url;
  if (url) window.open(url, '_blank');
  else toast('⚠ No URL found for this result.');
}

/* ─── GENERATE ───────────────────────────────────────────────────── */
function onGenerate() {
  const game = document.getElementById('gameName').value.trim();
  const url  = document.getElementById('landingUrl').value.trim();

  if (!game) { toast('⚠ Enter game name!'); return; }
  if (!url)  { toast('⚠ Enter a CPA landing page link!'); return; }

  const apiBase = getApiBase();
  if (!apiBase) {
    // DEMO mode — simulate pipeline
    runDemoGeneration(game, url);
    return;
  }

  // Real API call
  if (!state.screenshotFile) { toast('⚠ Choose a channel screenshot first!'); return; }

  startGeneration();

  const form = new FormData();
  form.append('game', game);
  form.append('url', url);
  form.append('max', state.maxVideos);
  form.append('caption_color', document.getElementById('captionColor').value);
  form.append('caption_pos',   document.getElementById('captionPos').value);
  form.append('landing_link_color', document.getElementById('linkColorPicker').value);
  form.append('link_font', document.getElementById('linkFont').value);
  form.append('sfx_enabled', document.getElementById('sfxEnabled').checked);
  form.append('custom_script', document.getElementById('customScript').value.trim());
  form.append('screenshot', state.screenshotFile);
  if (state.recordingFile) form.append('manual_recording', state.recordingFile);

  // Overlays & layout
  form.append('overlays', JSON.stringify(getOverlays()));
  form.append('layout', JSON.stringify(getLayout()));

  // Mode
  const mode = (state.recordingFile) ? 'reward_first' : 'legacy';
  form.append('mode', mode);

  // Hook timing
  const hookStart = parseMSS(document.getElementById('hookStartSearch').value, 0);
  const hookEnd   = parseMSS(document.getElementById('hookEndSearch').value, 10);
  form.append('hook_start', hookStart);
  form.append('hook_end', hookEnd);

  log(`▶ Starting ${mode} pipeline for: ${game}`);
  setProgress(5);

  // Poll status
  const pollInterval = startStatusPoll(apiBase);

  const endpoint = mode === 'reward_first' ? '/api/cloud_process' : '/api/generate';

  fetch(`${apiBase}${endpoint}`, { method: 'POST', body: form })
    .then(r => r.json())
    .then(data => {
      clearInterval(pollInterval);
      stopGeneration();
      if (data.success) {
        setProgress(100);
        setStatus('✅ Render complete!', 'ok');
        log(`✅ ${data.processed_count} video(s) processed. Sent to Telegram.`, 'ok');
        showOutput(`${apiBase}${data.video_url_1080 || data.video_url}`);
        if (data.seo) populateSeo(data.seo);
      } else {
        setStatus('❌ Render failed.', 'err');
        log(`Error: ${data.error}`, 'err');
      }
    })
    .catch(err => {
      clearInterval(pollInterval);
      stopGeneration();
      setStatus('❌ Network error', 'err');
      log(`Network error: ${err.message}`, 'err');
    });
}

/* Demo mode simulation */
function runDemoGeneration(game, url) {
  startGeneration();
  const steps = [
    [5,   `▶ Starting pipeline for: ${game}`],
    [12,  '🔍 Searching for gameplay videos...'],
    [22,  '✅ Found 5 candidate video(s).'],
    [30,  '⬇ Downloading candidate 1/1...'],
    [40,  '✓ Download succeeded. Processing...'],
    [50,  '🤖 Generating AI script via Llama 3...'],
    [58,  '🎙 Generating ElevenLabs voiceover...'],
    [65,  '📝 Transcribing audio for subtitles...'],
    [72,  '🎬 Compositing overlays & stickers...'],
    [80,  '🔧 Encoding final 1080p video...'],
    [90,  '📱 Sending to Telegram...'],
    [100, '✅ Render complete! Video sent to Telegram.'],
  ];

  let i = 0;
  const interval = setInterval(() => {
    if (!state.processing || state.paused) return;
    if (i >= steps.length) {
      clearInterval(interval);
      stopGeneration();
      setStatus('✅ Demo complete!', 'ok');
      showDemoOutput(game, url);
      generateDemoSeo(game);
      return;
    }
    const [prog, msg] = steps[i++];
    setProgress(prog);
    setStatus(msg, prog < 100 ? 'info' : 'ok');
    log(msg, prog < 100 ? '' : 'ok');
  }, 800);

  state._demoInterval = interval;
}

function showDemoOutput(game, url) {
  const thumb = document.getElementById('outputThumb');
  thumb.innerHTML = `
    <div style="text-align:center;padding:12px">
      <div style="font-size:40px;margin-bottom:8px">🎬</div>
      <div style="font-size:13px;font-weight:700;color:var(--green);margin-bottom:4px">${game}_promo.mp4</div>
      <div style="font-size:11px;color:var(--fg-dim)">1080p · 30s · 9:16 vertical</div>
      <div style="font-size:11px;color:var(--fg-dim);margin-top:4px">🔗 ${url}</div>
      <div style="font-size:11px;color:var(--orange);margin-top:6px">⚠ Demo mode — connect cloud API to render real videos</div>
    </div>
  `;
  state.lastRenderedUrl = 'demo';
  document.getElementById('exportBtns').classList.remove('hidden');
}

function generateDemoSeo(game) {
  const platforms = {
    youtube: {
      title: `🔥 ${game} MOD 2025 – Unlimited Resources EXPOSED!`,
      description: `Are you still playing ${game} the boring way? This INSANE trick gives you unlimited resources without spending a dime. Watch now before it gets removed!\n\n✅ 100% Free\n✅ Works on iOS & Android\n✅ No root required\n\n🔗 Download Link in Description!`,
      tags: `${game}, ${game} mod, ${game} hack, ${game} free, ${game} unlimited`,
      hashtags: `#${game.replace(/\s/g,'')} #gaming #mod #hack #free #viral #shorts`,
    },
    tiktok: {
      title: `${game} secret trick 🤫 #gaming #${game.replace(/\s/g,'')} #shorts`,
      description: `This ${game} trick changes EVERYTHING! Try it now 👇`,
      tags: `${game}, gaming, mod, trick, viral`,
      hashtags: `#${game.replace(/\s/g,'')} #gaming #mod #viral #fyp #foryoupage`,
    },
    instagram: {
      title: `🎮 ${game} MOD – Get Unlimited Coins! (2025)`,
      description: `Tap the link in bio to get unlimited ${game} resources for FREE! This working method was just discovered and it's going viral.`,
      tags: `${game}, gaming, mod, reels, hack`,
      hashtags: `#gaming #${game.replace(/\s/g,'')} #reels #mod #viral #explore`,
    },
    facebook: {
      title: `${game} HACK 2025 – Free Unlimited Resources (Still Working!)`,
      description: `🎮 Gaming trick that ACTUALLY works for ${game}. Join 50,000+ players using this method right now!`,
      tags: `${game}, gaming, hack, free`,
      hashtags: `#${game.replace(/\s/g,'')} #gaming #mod #free`,
    },
    x: {
      title: `This ${game} trick is insane 👀 #gaming #mod`,
      description: `Just found this ${game} method that gives you unlimited resources for FREE. Dropping the link 🧵`,
      tags: `gaming, mod, ${game}`,
      hashtags: `#gaming #${game.replace(/\s/g,'')} #mod`,
    },
  };
  state.seoPackages = platforms;
  onSeoPlatformChange();
}

/* ─── STATUS POLLING ─────────────────────────────────────────────── */
function startStatusPoll(apiBase) {
  return setInterval(() => {
    fetch(`${apiBase}/api/status`)
      .then(r => r.json())
      .then(d => {
        if (d.message) {
          const msg  = d.message;
          const pctM = msg.match(/\[(\d+)%\]/);
          if (pctM) setProgress(parseInt(pctM[1]));
          setStatus(msg, 'info');
          log(msg);
        }
      })
      .catch(() => {});
  }, 1500);
}

/* ─── GENERATE STATE HELPERS ─────────────────────────────────────── */
function startGeneration() {
  state.processing = true;
  state.paused     = false;
  document.getElementById('generateBtn').disabled = true;
  document.getElementById('pauseBtn').disabled    = false;
  document.getElementById('cancelBtn').disabled   = false;
  setProgress(0);
  document.getElementById('logBox').innerHTML = '';
}

function stopGeneration() {
  state.processing = false;
  state.paused     = false;
  document.getElementById('generateBtn').disabled = false;
  document.getElementById('pauseBtn').disabled    = true;
  document.getElementById('cancelBtn').disabled   = true;
  document.getElementById('pauseBtn').textContent = '⏸ PAUSE';
}

function onPause() {
  state.paused = !state.paused;
  const btn = document.getElementById('pauseBtn');
  if (state.paused) {
    btn.textContent = '▶ RESUME';
    setStatus('PAUSED', 'err');
    log('--- PAUSED ---');
  } else {
    btn.textContent = '⏸ PAUSE';
    setStatus('Resuming...', 'info');
    log('--- RESUMED ---');
  }
}

function onCancel() {
  if (state._demoInterval) clearInterval(state._demoInterval);
  stopGeneration();
  setStatus('Cancelled', 'err');
  log('--- CANCELLED BY USER ---', 'err');
  setProgress(0);
}

/* ─── OUTPUT ─────────────────────────────────────────────────────── */
function showOutput(url) {
  const thumb = document.getElementById('outputThumb');
  state.lastRenderedUrl = url;
  if (url && url.startsWith('http')) {
    thumb.innerHTML = `<video src="${url}" controls style="max-width:100%;max-height:240px;border-radius:8px"></video>`;
  } else {
    thumb.innerHTML = `<span style="color:var(--green);font-weight:700">🎬 ${url}</span>`;
  }
  document.getElementById('exportBtns').classList.remove('hidden');
}

function doExport(quality) {
  const url = state.lastRenderedUrl;
  if (!url || url === 'demo') {
    toast('⚠ No rendered video found. Run GENERATE first.');
    return;
  }
  if (quality === '720') {
    toast('720p export is handled by the cloud API.');
  } else {
    if (url.startsWith('http')) window.open(url, '_blank');
    else toast('No local download available in web mode.');
  }
}

function openOutputFolder() {
  toast('📂 Folder access is only available in the desktop app.');
}

/* ─── SEO ─────────────────────────────────────────────────────────── */
function onSeoPlatformChange() {
  const platform = document.getElementById('seoPlatform').value;
  const pkg      = state.seoPackages[platform];
  if (!pkg) return;

  document.getElementById('seoTitleInput').value = pkg.title   || '';
  document.getElementById('seoDesc').value        = pkg.description || '';
  document.getElementById('seoTags').value        = pkg.tags   || '';
  document.getElementById('seoHashtags').value    = pkg.hashtags || '';
}

function copySeoTitle() {
  const v = document.getElementById('seoTitleInput').value;
  if (!v || v === 'Generate a video to see AI-optimized title') { toast('⚠ No title yet.'); return; }
  navigator.clipboard.writeText(v).then(() => toast('📋 Title copied!'));
}

function copyAllSeo() {
  const title  = document.getElementById('seoTitleInput').value;
  const desc   = document.getElementById('seoDesc').value;
  const tags   = document.getElementById('seoTags').value;
  const hashes = document.getElementById('seoHashtags').value;
  if (!title || title === 'Generate a video to see AI-optimized title') { toast('⚠ Generate a video first.'); return; }
  const full = `${title}\n\n${desc}\n\nTags: ${tags}\n\n${hashes}`;
  navigator.clipboard.writeText(full).then(() => toast('📋 Full SEO copied!'));
}

function populateSeo(seoData) {
  state.seoPackages = seoData;
  onSeoPlatformChange();
}

/* ─── LAYOUT / OVERLAY DATA ──────────────────────────────────────── */
function getLayout() {
  const ss   = items.find(i => i.kind === 'screenshot');
  const link = items.find(i => i.kind === 'link');
  let ss_ox = 0, ss_oy = 0, ss_zoom = 1.0;
  let link_x = 0.5, link_y = 0.96;

  if (ss && ss.img) {
    ss_ox   = (ss.x - PV_W / 2) / PV_W;
    ss_oy   = (ss.y - PV_H / 2) / PV_H;
    const autoScale = PV_W / ss.img.width;
    ss_zoom = ss.scale / (autoScale || 1);
  }
  if (link) {
    link_x = link.x / PV_W;
    link_y = link.y / PV_H;
  }
  return { ss_ox, ss_oy, ss_zoom, link_x, link_y };
}

function getOverlays() {
  return items
    .filter(i => !['screenshot','link','safe_zone'].includes(i.kind))
    .map(i => ({
      kind: i.kind,
      cx: i.x / PV_W,
      cy: i.y / PV_H,
      size: i.scale,
      rotation: i.rotation,
      text: i.text || undefined,
    }));
}

/* ─── HELPER: API BASE ───────────────────────────────────────────── */
function getApiBase() {
  if (state.renderMode === 'cloud') {
    const u = document.getElementById('cloudApiUrl').value.trim().replace(/\/$/, '');
    return u || null;
  }
  // Local mode — when served from Flask locally this would work, but on GitHub Pages we're static
  return null; // Demo mode on GitHub Pages
}

/* ─── HELPER: Parse M:SS ─────────────────────────────────────────── */
function parseMSS(val, fallback = 0) {
  if (!val) return fallback;
  val = val.trim();
  const parts = val.split(':');
  if (parts.length === 2) return parseInt(parts[0]) * 60 + parseInt(parts[1]);
  return parseInt(val) || fallback;
}

/* ─── HELPER: LOG ────────────────────────────────────────────────── */
function log(msg, type = '') {
  const box = document.getElementById('logBox');
  const line = document.createElement('div');
  line.className = 'log-line' + (type ? ` ${type}` : '');
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

/* ─── HELPER: STATUS ─────────────────────────────────────────────── */
function setStatus(msg, type = '') {
  const el = document.getElementById('statusText');
  el.textContent = msg;
  el.className = 'dim';
  if (type === 'ok')   el.style.color = 'var(--green)';
  else if (type === 'err')  el.style.color = 'var(--red)';
  else if (type === 'info') el.style.color = 'var(--accent)';
  else el.style.color = 'var(--fg-dim)';
}

/* ─── HELPER: PROGRESS ───────────────────────────────────────────── */
function setProgress(val) {
  state.progress = val;
  document.getElementById('progressBar').style.width = `${val}%`;
}

/* ─── HELPER: TOAST ──────────────────────────────────────────────── */
let _toastTimeout = null;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  if (_toastTimeout) clearTimeout(_toastTimeout);
  _toastTimeout = setTimeout(() => el.classList.remove('show'), 3000);
}

/* ─── HELPER: roundRect ──────────────────────────────────────────── */
function roundRect(ctx, x, y, w, h, r) {
  if (!ctx.roundRect) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.closePath();
  } else {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
  }
}

/* ─── MAIN RENDER PATCH (add caption to canvas loop) ────────────── */
const _origRenderCanvas = renderCanvas;
function renderCanvas() {
  animFrameId = null;
  ctx.clearRect(0, 0, PV_W, PV_H);

  // Background
  const grad = ctx.createLinearGradient(0, 0, 0, PV_H);
  grad.addColorStop(0, '#0a0a16');
  grad.addColorStop(1, '#0d0d1a');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, PV_W, PV_H);

  // Items
  for (const item of items) {
    if (item.kind === 'safe_zone') { drawSafeZone(); continue; }
    drawItem(item);
  }

  // Caption preview on top
  drawCaptionPreview();

  // Selection handles
  if (selectedItem && selectedItem.kind !== 'safe_zone') {
    drawHandles(selectedItem);
  }

  animFrameId = requestAnimationFrame(renderCanvas);
}

/* ─── INIT ───────────────────────────────────────────────────────── */
renderCanvas();
log('AI Video Automation Studio ready.', 'info');
log('Enter a game name and click SEARCH or GENERATE.', '');
log('Connect your Cloud API URL in the settings for real rendering.', '');