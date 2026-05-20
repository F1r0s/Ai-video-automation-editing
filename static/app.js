/* ═══════════════════════════════════════════════════════════════
   app.js — AI Video Automation Studio  (Local App Version)
═══════════════════════════════════════════════════════════════ */

/* ─── STATE ───────────────────────────────────────────────── */
var state = {
  maxVideos: 5,
  screenshotFile: null,
  recordingFile: null,
  processing: false,
  paused: false,
  searchResults: [],
  selectedResultIdx: -1,
  seoPackages: {},
  lastRenderedUrl: null,
  renderMode: 'local',
  sourceMode: 'search',
  demoInterval: null
};

/* ─── CANVAS SETUP ───────────────────────────────────────── */
var canvas = document.getElementById('previewCanvas');
var ctx    = canvas.getContext('2d');
var PV_W   = 300;
var PV_H   = 534;
var HANDLE_R = 7;

var items        = [];
var selectedItem = null;
var isDragging   = false;
var dragMode     = null;
var dragStart    = { x: 0, y: 0 };
var dragStartItem = { x: 0, y: 0, scale: 1 };
var startDist    = 1;
var startAngle   = 0;
var startRotation = 0;

/* ─── CANVAS ITEM ────────────────────────────────────────── */
function CanvasItem(kind, x, y, text, imgSrc) {
  this.kind     = kind;
  this.x        = x || PV_W / 2;
  this.y        = y || PV_H / 2;
  this.scale    = 1.0;
  this.rotation = 0;
  this.text     = text || '';
  this.img      = null;

  if (kind === 'screenshot' && imgSrc) {
    var self = this;
    var img = new Image();
    img.onload = function () {
      self.img = img;
      var s = PV_W / img.width;
      if (img.height * s > PV_H + 200) s = (PV_H + 200) / img.height;
      self.scale = s;
    };
    img.src = imgSrc;
  }
}

/* ─── RENDER LOOP ────────────────────────────────────────── */
function renderLoop() {
  ctx.clearRect(0, 0, PV_W, PV_H);

  /* background */
  var grad = ctx.createLinearGradient(0, 0, 0, PV_H);
  grad.addColorStop(0, '#0a0a16');
  grad.addColorStop(1, '#0d0d1a');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, PV_W, PV_H);

  /* items */
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    if (item.kind === 'safe_zone') { drawSafeZone(); continue; }
    drawItem(item);
  }

  /* caption preview */
  drawCaptionPreview();

  /* selection handles */
  if (selectedItem && selectedItem.kind !== 'safe_zone') drawHandles(selectedItem);

  requestAnimationFrame(renderLoop);
}

/* ─── DRAW ITEM ──────────────────────────────────────────── */
function drawItem(item) {
  ctx.save();
  ctx.translate(item.x, item.y);
  ctx.rotate(item.rotation * Math.PI / 180);
  switch (item.kind) {
    case 'screenshot':   drawScreenshot(item); break;
    case 'link':         drawLink(item);       break;
    case 'circle':       drawCircle(item);     break;
    case 'arrow':        drawArrow(item);      break;
    case 'finger':       drawFinger(item);     break;
    case 'cartoon':      drawCartoon(item);    break;
    case 'text':         drawTextSticker(item);break;
  }
  ctx.restore();
}

function drawScreenshot(item) {
  if (!item.img) return;
  var w = item.img.width  * item.scale;
  var h = item.img.height * item.scale;
  ctx.drawImage(item.img, -w / 2, -h / 2, w, h);
}

function drawLink(item) {
  var url   = item.text;
  var s     = Math.max(0.5, item.scale);
  var fs    = Math.max(9, Math.round(13 * s));
  var color = document.getElementById('linkColorPicker').value || '#64dcff';
  ctx.font  = 'bold ' + fs + 'px Inter, Arial';
  var tw    = ctx.measureText(url).width;
  var pad   = 8;
  ctx.fillStyle = 'rgba(0,0,0,0.7)';
  fillRoundRect(-tw / 2 - pad, -fs / 2 - 4, tw + pad * 2, fs + 10, 8);
  ctx.fillStyle    = color;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(url, 0, 0);
}

function drawCircle(item) {
  var r  = 36 * item.scale;
  var t  = Date.now() / 1000;
  var rp = r * (1 + 0.12 * Math.sin(t * 10));
  ctx.strokeStyle = '#ff1744';
  ctx.lineWidth   = Math.max(2, 4 * item.scale);
  ctx.shadowColor = '#ff1744';
  ctx.shadowBlur  = 14;
  ctx.beginPath();
  ctx.ellipse(0, 0, rp, rp * 0.75, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function drawArrow(item) {
  var s      = item.scale;
  var bounce = 8 * Math.sin(Date.now() / 125);
  var size   = 28 * s;
  ctx.fillStyle   = '#ff1744';
  ctx.shadowColor = '#ff1744';
  ctx.shadowBlur  = 10;
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
  var s      = item.scale;
  var bounce = 8 * Math.sin(Date.now() / 125);
  ctx.font          = Math.round(36 * s) + 'px Segoe UI Emoji, sans-serif';
  ctx.textAlign     = 'center';
  ctx.textBaseline  = 'middle';
  ctx.shadowColor   = '#ff1744';
  ctx.shadowBlur    = 8;
  ctx.fillText('\u261d\ufe0f', 0, bounce);
  ctx.shadowBlur = 0;
}

function drawCartoon(item) {
  var s  = item.scale;
  var r  = 28 * s * (1 + 0.12 * Math.sin(Date.now() / 100));
  var gd = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
  gd.addColorStop(0, '#a855f7');
  gd.addColorStop(1, '#4a00e0');
  ctx.fillStyle   = gd;
  ctx.shadowColor = '#7c3aed';
  ctx.shadowBlur  = 18;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth   = 2 * s;
  ctx.stroke();
  ctx.shadowBlur   = 0;
  ctx.fillStyle    = '#fff';
  ctx.font         = Math.round(18 * s) + 'px Segoe UI Emoji, Arial';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('\u2605', 0, 1);
}

function drawTextSticker(item) {
  var s    = Math.max(0.5, item.scale);
  var pulse = 1 + 0.1 * Math.sin(Date.now() / 100);
  var fs   = Math.round(13 * s * pulse);
  ctx.font = 'bold ' + fs + 'px Inter, Arial';
  var tw   = ctx.measureText(item.text).width;
  var pad  = 10;
  ctx.fillStyle = 'rgba(0,0,0,0.85)';
  fillRoundRect(-tw / 2 - pad, -fs / 2 - 4, tw + pad * 2, fs + 10, 8);
  ctx.fillStyle    = '#ffeb3b';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowColor  = '#ff9800';
  ctx.shadowBlur   = 6;
  ctx.fillText(item.text, 0, 0);
  ctx.shadowBlur = 0;
}

/* ─── SAFE ZONE ──────────────────────────────────────────── */
function drawSafeZone() {
  ctx.save();
  ctx.fillStyle = 'rgba(255,51,0,0.18)';
  ctx.fillRect(0, 0, PV_W, PV_H * 0.12);
  ctx.fillStyle    = '#ff9980';
  ctx.font         = 'bold 8px Arial';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('DEAD ZONE - Platform UI', PV_W / 2, PV_H * 0.06);

  ctx.fillStyle = 'rgba(255,51,0,0.18)';
  ctx.fillRect(0, PV_H * 0.80, PV_W, PV_H * 0.20);
  ctx.fillStyle = '#ff9980';
  ctx.fillText('DEAD ZONE - Buttons', PV_W / 2, PV_H * 0.90);

  ctx.fillStyle = 'rgba(255,102,0,0.18)';
  ctx.fillRect(PV_W * 0.82, PV_H * 0.12, PV_W * 0.18, PV_H * 0.68);

  ctx.strokeStyle = '#00aaff';
  ctx.lineWidth   = 1;
  ctx.setLineDash([5, 3]);
  ctx.strokeRect(0, PV_H * 0.12, PV_W * 0.82, PV_H * 0.43);
  ctx.fillStyle = '#00aaff';
  ctx.font      = 'bold 7px Arial';
  ctx.fillText('SCREENSHOT ZONE', PV_W * 0.41, PV_H * 0.34);

  ctx.strokeStyle = '#00ff88';
  ctx.strokeRect(0, PV_H * 0.55, PV_W * 0.82, PV_H * 0.20);
  ctx.fillStyle = '#00ff88';
  ctx.fillText('CAPTION ZONE', PV_W * 0.41, PV_H * 0.65);

  ctx.strokeStyle = '#ffdd00';
  ctx.strokeRect(0, PV_H * 0.75, PV_W * 0.82, PV_H * 0.05);
  ctx.fillStyle = '#ffdd00';
  ctx.fillText('CPA LINK ZONE', PV_W * 0.41, PV_H * 0.775);

  ctx.setLineDash([]);
  ctx.restore();
}

/* ─── CAPTION PREVIEW ────────────────────────────────────── */
function drawCaptionPreview() {
  var posEl   = document.getElementById('captionPos');
  var colorEl = document.getElementById('captionColor');
  if (!posEl || !colorEl) return;

  var pos   = parseFloat(posEl.value) || 0.58;
  var color = colorEl.value || 'yellow';
  var y     = PV_H * pos;
  var map   = { yellow: '#ffd600', white: '#ffffff', green: '#00e676', cyan: '#00d4ff' };
  var fill  = map[color] || '#ffd600';

  var text = 'AI Generated Subtitle';
  var fs   = 15;
  ctx.save();
  ctx.font          = 'bold ' + fs + 'px Inter, Arial';
  var tw            = ctx.measureText(text).width;
  ctx.fillStyle     = 'rgba(17,17,17,0.88)';
  fillRoundRect((PV_W - tw) / 2 - 10, y - fs / 2 - 6, tw + 20, fs + 14, 8);
  ctx.fillStyle     = fill;
  ctx.textAlign     = 'center';
  ctx.textBaseline  = 'middle';
  ctx.shadowColor   = 'rgba(0,0,0,0.9)';
  ctx.shadowBlur    = 5;
  ctx.fillText(text, PV_W / 2, y + 1);
  ctx.shadowBlur    = 0;
  ctx.restore();
}

/* ─── SELECTION HANDLES ──────────────────────────────────── */
function getItemBbox(item) {
  var hw = 40, hh = 40;
  if (item.kind === 'screenshot' && item.img) {
    hw = item.img.width  * item.scale / 2;
    hh = item.img.height * item.scale / 2;
  } else if (item.kind === 'link' || item.kind === 'text') {
    var fs = Math.round(13 * item.scale);
    ctx.font = 'bold ' + fs + 'px Inter, Arial';
    hw = ctx.measureText(item.text).width / 2 + 16;
    hh = fs / 2 + 8;
  } else {
    var base = { circle: 40, arrow: 32, finger: 38, cartoon: 32 };
    var b2   = (base[item.kind] || 40) * item.scale;
    hw = hh = b2 + 4;
  }
  return { x1: item.x - hw, y1: item.y - hh, x2: item.x + hw, y2: item.y + hh };
}

function drawHandles(item) {
  var b   = getItemBbox(item);
  var pad = 4;
  var x1  = b.x1 - pad, y1 = b.y1 - pad;
  var x2  = b.x2 + pad, y2 = b.y2 + pad;
  ctx.save();
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth   = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  ctx.setLineDash([]);
  [[x1,y1],[x2,y1],[x2,y2],[x1,y2]].forEach(function(pt) {
    ctx.beginPath();
    ctx.arc(pt[0], pt[1], HANDLE_R, 0, Math.PI * 2);
    ctx.fillStyle   = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#00d4ff';
    ctx.lineWidth   = 2;
    ctx.stroke();
  });
  var hx = (x1 + x2) / 2, hy = y1 - 22;
  ctx.setLineDash([2, 2]);
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth   = 1;
  ctx.beginPath(); ctx.moveTo((x1 + x2) / 2, y1); ctx.lineTo(hx, hy); ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(hx, hy, HANDLE_R, 0, Math.PI * 2);
  ctx.fillStyle   = '#00d4ff';
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth   = 1.5;
  ctx.stroke();
  ctx.restore();
}

function getCorners(item) {
  var b = getItemBbox(item), pad = 4;
  var x1 = b.x1-pad, y1 = b.y1-pad, x2 = b.x2+pad, y2 = b.y2+pad;
  return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]];
}
function getRotHandle(item) {
  var b = getItemBbox(item), pad = 4;
  var x1 = b.x1-pad, y1 = b.y1-pad, x2 = b.x2+pad;
  return [(x1+x2)/2, y1-22];
}
function hitPt(ax, ay, bx, by) {
  return Math.hypot(ax-bx, ay-by) <= HANDLE_R + 5;
}

/* ─── CANVAS MOUSE EVENTS ───────────────────────────────── */
function canvasPos(e) {
  var r = canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
canvas.addEventListener('mousedown', function(e) {
  var pos = canvasPos(e);
  if (selectedItem) {
    var rh = getRotHandle(selectedItem);
    if (hitPt(pos.x, pos.y, rh[0], rh[1])) {
      dragMode      = 'rotate';
      startAngle    = Math.atan2(pos.y - selectedItem.y, pos.x - selectedItem.x) * 180 / Math.PI;
      startRotation = selectedItem.rotation;
      isDragging    = true;
      return;
    }
    var corners = getCorners(selectedItem);
    for (var ci = 0; ci < corners.length; ci++) {
      if (hitPt(pos.x, pos.y, corners[ci][0], corners[ci][1])) {
        dragMode      = 'scale';
        startDist     = Math.hypot(pos.x - selectedItem.x, pos.y - selectedItem.y) || 1;
        dragStartItem = { scale: selectedItem.scale };
        isDragging    = true;
        return;
      }
    }
  }
  var clicked = null;
  for (var i = items.length - 1; i >= 0; i--) {
    if (items[i].kind === 'safe_zone') continue;
    var b = getItemBbox(items[i]);
    if (pos.x >= b.x1 && pos.x <= b.x2 && pos.y >= b.y1 && pos.y <= b.y2) {
      clicked = items[i]; break;
    }
  }
  selectedItem = clicked;
  if (clicked) {
    dragMode      = 'move';
    isDragging    = true;
    dragStart     = pos;
    dragStartItem = { x: clicked.x, y: clicked.y };
  }
});
canvas.addEventListener('mousemove', function(e) {
  if (!isDragging || !selectedItem) return;
  var pos = canvasPos(e);
  if (dragMode === 'move') {
    selectedItem.x = dragStartItem.x + (pos.x - dragStart.x);
    selectedItem.y = dragStartItem.y + (pos.y - dragStart.y);
  } else if (dragMode === 'scale') {
    var d = Math.hypot(pos.x - selectedItem.x, pos.y - selectedItem.y) || 1;
    selectedItem.scale = Math.max(0.1, Math.min(10, dragStartItem.scale * d / startDist));
  } else if (dragMode === 'rotate') {
    var a = Math.atan2(pos.y - selectedItem.y, pos.x - selectedItem.x) * 180 / Math.PI;
    selectedItem.rotation = (startRotation + a - startAngle) % 360;
  }
});
canvas.addEventListener('mouseup',    function() { isDragging = false; dragMode = null; });
canvas.addEventListener('dblclick',   function() { selectedItem = null; });
document.addEventListener('keydown',  function(e) { if (e.key === 'Delete') deleteSelected(); });

/* ─── STICKER FUNCTIONS ─────────────────────────────────── */
function addSticker(kind) {
  var item = new CanvasItem(kind, PV_W / 2, Math.round(PV_H * 0.25));
  items.push(item);
  selectedItem = item;
}
function addTextSticker(text) {
  var item = new CanvasItem('text', PV_W / 2, Math.round(PV_H * 0.25), text);
  items.push(item);
  selectedItem = item;
}
function deleteSelected() {
  if (!selectedItem) return;
  var idx = items.indexOf(selectedItem);
  if (idx !== -1) items.splice(idx, 1);
  selectedItem = null;
}
function clearStickers() {
  items = items.filter(function(i) {
    return i.kind === 'screenshot' || i.kind === 'link' || i.kind === 'safe_zone';
  });
  selectedItem = null;
}
function toggleSafeZone() {
  var idx = items.findIndex(function(i) { return i.kind === 'safe_zone'; });
  if (idx !== -1) items.splice(idx, 1);
  else items.push(new CanvasItem('safe_zone', PV_W / 2, PV_H / 2));
}

/* ─── FILE INPUTS ───────────────────────────────────────── */
function onScreenshot(input) {
  var file = input.files[0];
  if (!file) return;
  state.screenshotFile = file;
  document.getElementById('ssName').textContent = file.name;
  var reader = new FileReader();
  reader.onload = function(e) {
    var idx = items.findIndex(function(i) { return i.kind === 'screenshot'; });
    if (idx !== -1) items.splice(idx, 1);
    var ss = new CanvasItem('screenshot', PV_W / 2, PV_H / 2, '', e.target.result);
    items.unshift(ss);
    selectedItem = ss;
    document.getElementById('canvasPlaceholder').style.display = 'none';
    updateLinkOverlay();
  };
  reader.readAsDataURL(file);
}
function onRecording(input) {
  var file = input.files[0];
  if (!file) return;
  state.recordingFile = file;
  document.getElementById('recName').textContent = file.name;
  addLog('Screen recording selected: ' + file.name, 'info');
}

/* ─── LINK OVERLAY ──────────────────────────────────────── */
function onLinkChange() { updateLinkOverlay(); }
function updateLinkOverlay() {
  var url = document.getElementById('landingUrl').value.trim();
  var idx = items.findIndex(function(i) { return i.kind === 'link'; });
  if (url) {
    if (idx === -1) items.push(new CanvasItem('link', PV_W / 2, PV_H - 30, url));
    else items[idx].text = url;
  } else {
    if (idx !== -1) items.splice(idx, 1);
  }
}

/* ─── COLOR SYNC ────────────────────────────────────────── */
function onLinkColorChange() {
  document.getElementById('linkColorHex').value = document.getElementById('linkColorPicker').value;
}
function onLinkHexChange() {
  var v = document.getElementById('linkColorHex').value;
  if (/^#[0-9a-fA-F]{6}$/.test(v)) document.getElementById('linkColorPicker').value = v;
}

/* ─── SPINNER ───────────────────────────────────────────── */
function changeMax(delta) {
  state.maxVideos = Math.max(1, Math.min(30, state.maxVideos + delta));
  document.getElementById('maxVal').textContent = state.maxVideos;
}

/* ─── SETTINGS TOGGLE ───────────────────────────────────── */
function toggleSettings() {
  var p = document.getElementById('settingsPanel');
  p.style.display = (p.style.display === 'none' || p.style.display === '') ? 'block' : 'none';
}

/* ─── SOURCE MODE ───────────────────────────────────────── */
function onSourceModeChange() {
  var checked = document.querySelector('input[name="sourceMode"]:checked');
  state.sourceMode = checked ? checked.value : 'search';
  document.getElementById('directUrlPanel').style.display = state.sourceMode === 'url'  ? 'block' : 'none';
  document.getElementById('searchCard').style.display     = state.sourceMode === 'search'? 'block' : 'none';
}

/* ─── PASTE ─────────────────────────────────────────────── */
function pasteUrl() {
  if (navigator.clipboard && navigator.clipboard.readText) {
    navigator.clipboard.readText().then(function(t) {
      document.getElementById('directUrl').value = t;
    }).catch(function() { showToast('Clipboard access denied — paste manually'); });
  } else {
    showToast('Clipboard API not available — paste manually');
  }
}

/* ─── SEARCH ────────────────────────────────────────────── */
function onSearch() {
  var game = document.getElementById('gameName').value.trim();
  if (!game) { showToast('Enter a game name first!'); return; }

  var btn  = document.getElementById('searchBtn');
  var list = document.getElementById('resultsList');
  btn.disabled    = true;
  btn.textContent = 'Searching...';
  list.innerHTML  = '<div class="results-placeholder">Searching for ' + game + '...</div>';
  state.searchResults     = [];
  state.selectedResultIdx = -1;

  var api = getApiBase();
  var form = new FormData();
  form.append('game', game);
  form.append('max', state.maxVideos);
  fetch(api + '/api/search', { method: 'POST', body: form })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      btn.disabled    = false;
      btn.textContent = '🔍 SEARCH';
      if (data.results) {
        state.searchResults = data.results;
        renderResultsList(data.results);
        setStatus('Found ' + data.results.length + ' results.', 'ok');
      } else {
        list.innerHTML = '<div class="results-placeholder" style="color:#ff4f4f">Error: ' + (data.error || 'No results') + '</div>';
        setStatus('Search failed.', 'err');
      }
    })
    .catch(function(err) {
      btn.disabled    = false;
      btn.textContent = '🔍 SEARCH';
      list.innerHTML  = '<div class="results-placeholder" style="color:#ff4f4f">Cannot reach API. Check connection.</div>';
      addLog('Search error: ' + err.message, 'err');
    });
}

function renderResultsList(results) {
  var list        = document.getElementById('resultsList');
  var ratioFilter = document.getElementById('ratioFilter').value;
  var visible     = results.filter(function(r) {
    if (ratioFilter === '9:16')  return r.ratio === '9:16';
    if (ratioFilter === '16:9')  return r.ratio === '16:9';
    return true;
  });
  if (!visible.length) {
    list.innerHTML = '<div class="results-placeholder">No results for filter "' + ratioFilter + '"</div>';
    return;
  }
  list.innerHTML = '';
  visible.forEach(function(r, i) {
    var div   = document.createElement('div');
    div.className = 'result-item ' + (r.ratio === '9:16' ? 'ratio-916' : 'ratio-169');
    var dur   = r.dur ? '[' + r.dur + 's] ' : '';
    var short = (r.url || '').substring(0, 45) + ((r.url || '').length > 45 ? '…' : '');
    div.textContent = '[' + (r.ratio || '?') + '] ' + dur + r.title + '  |  ' + short;
    div.title       = r.url || r.title;
    (function(idx, el) {
      el.addEventListener('click',   function() { selectResult(idx, el); });
      el.addEventListener('dblclick',function() { selectResult(idx, el); openSelectedInBrowser(); });
    })(i, div);
    list.appendChild(div);
  });
  selectResult(0, list.firstChild);
}

/* ...rest stays same... */
function selectResult(idx, el) {
  state.selectedResultIdx = idx;
  document.querySelectorAll('.result-item').forEach(function(d) { d.classList.remove('selected'); });
  if (el) el.classList.add('selected');
}

function openSelectedInBrowser() {
  var idx = state.selectedResultIdx;
  if (idx < 0 || idx >= state.searchResults.length) { showToast('Select a video first.'); return; }
  var url = state.searchResults[idx].url || state.searchResults[idx].webpage_url || '';
  if (url) window.open(url, '_blank');
  else showToast('No URL for this result.');
}

/* ─── GENERATE ──────────────────────────────────────────── */
function onGenerate() {
  var game = document.getElementById('gameName').value.trim();
  var url  = document.getElementById('landingUrl').value.trim();
  if (!game) { showToast('Enter a game name!'); return; }
  if (!url)  { showToast('Enter a CPA landing page link!'); return; }

  var api = getApiBase();
  if (!state.screenshotFile) { showToast('Choose a channel screenshot first!'); return; }

  startGen();
  var form = new FormData();
  form.append('game',               game);
  form.append('url',                url);
  form.append('max',                state.maxVideos);
  form.append('caption_color',      document.getElementById('captionColor').value);
  form.append('caption_pos',        document.getElementById('captionPos').value);
  form.append('landing_link_color', document.getElementById('linkColorPicker').value);
  form.append('link_font',          document.getElementById('linkFont').value);
  form.append('sfx_enabled',        document.getElementById('sfxEnabled').checked);
  form.append('custom_script',      document.getElementById('customScript').value.trim());
  form.append('screenshot',         state.screenshotFile);
  if (state.recordingFile) form.append('manual_recording', state.recordingFile);
  form.append('overlays', JSON.stringify(getOverlays()));
  form.append('layout',   JSON.stringify(getLayout()));
  form.append('mode',     state.recordingFile ? 'reward_first' : 'legacy');
  form.append('hook_start', parseMSS(document.getElementById('hookStartSearch').value, 0));
  form.append('hook_end',   parseMSS(document.getElementById('hookEndSearch').value, 10));

  addLog('Starting pipeline for: ' + game);
  setProgress(5);

  var pollId = setInterval(function() {
    fetch(api + '/api/status').then(function(r) { return r.json(); }).then(function(d) {
      if (!d.message) return;
      var pct = (d.message.match(/\[(\d+)%\]/) || [])[1];
      if (pct) setProgress(parseInt(pct));
      setStatus(d.message, 'info');
      addLog(d.message);
    }).catch(function(){});
  }, 1500);

  var endpoint = state.recordingFile ? '/api/cloud_process' : '/api/generate';
  fetch(api + endpoint, { method: 'POST', body: form })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      clearInterval(pollId);
      stopGen();
      if (data.success) {
        setProgress(100);
        setStatus('Render complete!', 'ok');
        addLog('Done! ' + data.processed_count + ' video(s) processed.', 'ok');
        showOutput(api + (data.video_url_1080 || data.video_url));
        if (data.seo) populateSeo(data.seo);
      } else {
        setStatus('Render failed.', 'err');
        addLog('Error: ' + data.error, 'err');
      }
    })
    .catch(function(err) {
      clearInterval(pollId);
      stopGen();
      setStatus('Network error', 'err');
      addLog('Network error: ' + err.message, 'err');
    });
}

function populateSeo(seoData) {
  state.seoPackages = seoData;
  onSeoPlatformChange();
}

/* ─── GENERATE HELPERS ──────────────────────────────────── */
function startGen() {
  state.processing = true;
  state.paused     = false;
  document.getElementById('generateBtn').disabled = true;
  document.getElementById('pauseBtn').disabled    = false;
  document.getElementById('cancelBtn').disabled   = false;
  document.getElementById('logBox').innerHTML     = '';
  setProgress(0);
}
var _demoInterval = null; // added for safety
function stopGen() {
  state.processing = false;
  state.paused     = false;
  document.getElementById('generateBtn').disabled = false;
  document.getElementById('pauseBtn').disabled    = true;
  document.getElementById('cancelBtn').disabled   = true;
  document.getElementById('pauseBtn').textContent = '⏸ PAUSE';
}
function onPause() {
  state.paused = !state.paused;
  var btn = document.getElementById('pauseBtn');
  if (state.paused) {
    btn.textContent = '▶ RESUME';
    setStatus('PAUSED', 'err');
    addLog('--- PAUSED ---');
  } else {
    btn.textContent = '⏸ PAUSE';
    setStatus('Resuming...', 'info');
    addLog('--- RESUMED ---');
  }
}
function onCancel() {
  stopGen();
  setStatus('Cancelled', 'err');
  addLog('--- CANCELLED ---', 'err');
  setProgress(0);
}

/* ─── OUTPUT ────────────────────────────────────────────── */
function showOutput(url) {
  state.lastRenderedUrl = url;
  var t = document.getElementById('outputThumb');
  if (url && url.startsWith('http')) {
    t.innerHTML = '<video src="' + url + '" controls style="max-width:100%;max-height:220px;border-radius:8px"></video>';
  } else {
    t.innerHTML = '<span style="color:#00e676;font-weight:700">🎬 ' + url + '</span>';
  }
  document.getElementById('exportBtns').style.display = 'flex';
}
function doExport(quality) {
  if (!state.lastRenderedUrl) {
    showToast('No video yet. Click GENERATE first.'); return;
  }
  window.open(state.lastRenderedUrl, '_blank');
}
function openOutputFolder() { showToast('Folder access is only available in the desktop app.'); }

/* ─── SEO ───────────────────────────────────────────────── */
function onSeoPlatformChange() {
  var p   = document.getElementById('seoPlatform').value;
  var pkg = state.seoPackages[p];
  if (!pkg) return;
  document.getElementById('seoTitleInput').value = pkg.title || '';
  document.getElementById('seoDesc').value       = pkg.description || '';
  document.getElementById('seoTags').value       = pkg.tags || '';
  document.getElementById('seoHashtags').value   = pkg.hashtags || '';
}
function copySeoTitle() {
  var v = document.getElementById('seoTitleInput').value;
  if (!v || v.indexOf('Generate') === 0) { showToast('No title yet.'); return; }
  navigator.clipboard && navigator.clipboard.writeText(v).then(function() { showToast('Title copied!'); });
}
function copyAllSeo() {
  var t = document.getElementById('seoTitleInput').value;
  if (!t || t.indexOf('Generate') === 0) { showToast('Generate a video first.'); return; }
  var full = t + '\n\n'
    + document.getElementById('seoDesc').value + '\n\nTags: '
    + document.getElementById('seoTags').value + '\n\n'
    + document.getElementById('seoHashtags').value;
  navigator.clipboard && navigator.clipboard.writeText(full).then(function() { showToast('SEO copied!'); });
}

/* ─── LAYOUT / OVERLAYS ─────────────────────────────────── */
function getLayout() {
  var ss   = items.find(function(i) { return i.kind === 'screenshot'; });
  var link = items.find(function(i) { return i.kind === 'link'; });
  var ss_ox = 0, ss_oy = 0, ss_zoom = 1.0, link_x = 0.5, link_y = 0.96;
  if (ss && ss.img) {
    ss_ox   = (ss.x - PV_W / 2) / PV_W;
    ss_oy   = (ss.y - PV_H / 2) / PV_H;
    ss_zoom = ss.scale / (PV_W / ss.img.width || 1);
  }
  if (link) { link_x = link.x / PV_W; link_y = link.y / PV_H; }
  return { ss_ox: ss_ox, ss_oy: ss_oy, ss_zoom: ss_zoom, link_x: link_x, link_y: link_y };
}
function getOverlays() {
  return items.filter(function(i) {
    return i.kind !== 'screenshot' && i.kind !== 'link' && i.kind !== 'safe_zone';
  }).map(function(i) {
    return { kind: i.kind, cx: i.x / PV_W, cy: i.y / PV_H, size: i.scale, rotation: i.rotation, text: i.text || undefined };
  });
}

/* ─── HELPERS ───────────────────────────────────────────── */
function getApiBase() {
  // Always query local app backend relative path
  return window.location.origin;
}
function parseMSS(v, def) {
  v = (v || '').trim();
  var p = v.split(':');
  if (p.length === 2) return parseInt(p[0]) * 60 + parseInt(p[1]);
  return parseInt(v) || def;
}
function addLog(msg, type) {
  var box  = document.getElementById('logBox');
  var line = document.createElement('div');
  line.className   = 'log-line' + (type ? ' ' + type : '');
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}
function setStatus(msg, type) {
  var el = document.getElementById('statusText');
  el.textContent = msg;
  el.style.color = type === 'ok' ? '#00e676' : type === 'err' ? '#ff4f4f' : type === 'info' ? '#00d4ff' : '#6a6a9a';
}
function setProgress(v) {
  document.getElementById('progressBar').style.width = v + '%';
}
function fillRoundRect(x, y, w, h, r) {
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
}

/* ─── TOAST ─────────────────────────────────────────────── */
var _toastTimer = null;
function showToast(msg) {
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function() { el.classList.remove('show'); }, 3000);
}

/* ─── CAPTION PREVIEW ───────────────────────────────────── */
function updateCaptionPreview() { /* handled automatically by renderLoop */ }

/* ─── FIX INITIAL DISPLAY STATE ────────────────────────── */
(function() {
  document.getElementById('directUrlPanel').style.display = 'none';
  document.getElementById('settingsPanel').style.display  = 'none';
  document.getElementById('exportBtns').style.display     = 'none';
})();

/* ─── START ANIMATION LOOP ──────────────────────────────── */
renderLoop();

/* ─── STARTUP LOG ───────────────────────────────────────── */
addLog('AI Video Automation Studio ready.', 'info');
addLog('Enter a game name and click SEARCH or GENERATE.', '');
