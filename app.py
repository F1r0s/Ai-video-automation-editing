"""
app.py — GUI with Visual Preview Editor + Capcut-style 4-corner Resizing

Left panel: form fields
Right panel: Live preview canvas with 4-corner scale/move for all elements
"""

import os, logging, threading, time, math, json, requests
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from scraper import VideoScraper
from config import Config
from video_processor import VideoProcessor

log = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BG, BG_CARD, BG_INPUT = "#1a1a2e", "#16213e", "#0f3460"
FG, FG_DIM, ACCENT = "#e6e6e6", "#8888aa", "#00d4ff"
GREEN, RED, ORANGE = "#00e676", "#ff5252", "#ffa726"

PV_W, PV_H = 300, 534        # preview canvas (9:16 ratio, +~11% for larger window)
VID_W, VID_H = 1080, 1920


class CanvasItem:
    """Represents any element on the canvas (screenshot, link, sticker)."""
    _GIF_CACHE = {}

    def __init__(self, editor, kind, x, y, text="", path=""):
        self.editor = editor
        self.canvas = editor.canvas
        self.kind = kind
        self.x = x
        self.y = y
        self.scale = 1.0
        self.rotation = 0.0
        self.text = text
        self.path = path
        
        self.ids = []
        self.tk_img = None
        self.pil_img = None
        self._gif_frames = None
        self._gif_durations = None
        self._gif_index = 0
        self._anim_after_id = None

        if kind == "screenshot" and path:
            self.pil_img = Image.open(path).convert("RGBA")

        # Preload sticker GIF frames when available
        if kind in ("circle", "arrow", "finger", "cartoon"):
            try:
                self._load_gif_frames()
            except Exception:
                self._gif_frames = None
                self._gif_durations = None
                self._gif_index = 0

        self.draw()

    def draw(self):
        for i in self.ids:
            self.canvas.delete(i)
        self.ids.clear()
        
        x, y, s = self.x, self.y, self.scale
        
        if self.kind == "screenshot":
            if not self.pil_img: return
            # Resize image
            img = self.pil_img
            w, h = int(img.width * s), int(img.height * s)
            # Cap size to avoid memory explosion during drag
            w, h = max(10, w), max(10, h)
            resized = img.resize((w, h), Image.NEAREST if self.editor.is_dragging else Image.LANCZOS)
            if self.rotation != 0:
                resized = resized.rotate(-self.rotation, expand=True, resample=Image.BICUBIC)
            self.tk_img = ImageTk.PhotoImage(resized)
            self.ids.append(self.canvas.create_image(x, y, image=self.tk_img, anchor="center"))
            
        elif self.kind == "link":
            if not self.text: return
            tk_fnt = getattr(self.editor, "link_font", "Arial").split("-")[0]
            if tk_fnt == "Comic": tk_fnt = "Comic Sans MS"
            if tk_fnt == "Montserrat": tk_fnt = "Arial"
            fnt = (tk_fnt, max(8, int(13 * s)), "bold")
            link_color = getattr(self.editor, "link_color", "#64dcff")
            # Dummy text to get bbox
            t_id = self.canvas.create_text(x, y, text=self.text, font=fnt)
            bbox = self.canvas.bbox(t_id)
            self.canvas.delete(t_id)
            if bbox:
                pad = int(4 * s)
                bg_id = self.canvas.create_rectangle(bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad,
                                                     fill="black", stipple="gray50", outline="")
                self.ids.append(bg_id)
            self.ids.append(self.canvas.create_text(x, y, text=self.text, fill=link_color, font=fnt))
            
        elif self.kind in ("circle", "arrow", "finger", "cartoon"):
            # If GIF frames loaded, draw the current frame as image
            if self._gif_frames:
                # Resize current PIL frame according to scale
                frame = self._gif_frames[self._gif_index]
                # Determine target size based on a base size per kind
                base_sizes = {"circle": (80, 80), "arrow": (80, 80), "finger": (72, 72), "cartoon": (80, 80)}
                bw, bh = base_sizes.get(self.kind, (64, 64))
                tw, th = max(1, int(bw * s)), max(1, int(bh * s))
                resized = frame.resize((tw, th), Image.LANCZOS)
                if self.rotation != 0:
                    resized = resized.rotate(-self.rotation, expand=True, resample=Image.BICUBIC)
                self.tk_img = ImageTk.PhotoImage(resized)
                self.ids.append(self.canvas.create_image(x, y, image=self.tk_img, anchor="center"))
                # Start animation loop
                self._start_animation()
            else:
                # Fallback to vector shapes when GIF not available
                if self.kind == "circle":
                    r = int(40 * s)
                    self.ids.append(self.canvas.create_oval(x-r, y-r, x+r, y+r, outline="red", width=max(1, int(3*s))))
                elif self.kind == "arrow":
                    r = int(20 * s)
                    self.ids.append(self.canvas.create_polygon(x, y-int(25*s), x-r, y+int(12*s), x+r, y+int(12*s),
                                                               outline="red", fill="red", width=max(1, int(2*s))))
                elif self.kind == "finger":
                    fs = max(8, int(36 * s))
                    self.ids.append(self.canvas.create_text(x, y, text="\u261d", fill="red", font=("Segoe UI Emoji", fs)))
                elif self.kind == "cartoon":
                    r = int(30 * s)
                    self.ids.append(self.canvas.create_rectangle(x-r, y-r, x+r, y+r, outline="blue", width=max(1, int(3*s))))
            
        elif self.kind == "text":
            fs = max(8, int(13 * s))
            fnt = ("Segoe UI", fs, "bold")
            t_id = self.canvas.create_text(x, y, text=self.text, font=fnt)
            bbox = self.canvas.bbox(t_id)
            self.canvas.delete(t_id)
            if bbox:
                pad = int(6 * s)
                bg_id = self.canvas.create_rectangle(bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad,
                                                     fill="#111", outline="")
                self.ids.append(bg_id)
            self.ids.append(self.canvas.create_text(x, y, text=self.text, fill="yellow", font=fnt))

        elif self.kind == "safe_zone":
            # ── 9:16 Platform Safe Zone Guide ──────────────────────────────────
            # Dead zones: areas covered by platform UI on TikTok/Shorts/Reels/Facebook
            #
            # TOP dead zone  (0% – 12%)  : Status bar, platform header
            # BOTTOM dead zone (80% – 100%): Like/comment/share buttons + caption
            # RIGHT dead zone  (82% – 100%): Action buttons (like, comment, share, follow)

            # ── Dead zones (red/orange hatch) ──────────────────────────────────
            # Top dead zone
            self.ids.append(self.canvas.create_rectangle(
                0, 0, PV_W, int(PV_H * 0.12),
                fill="#ff3300", stipple="gray25", outline=""))
            self.ids.append(self.canvas.create_text(
                PV_W // 2, int(PV_H * 0.06),
                text="⛔ DEAD ZONE — Platform UI", fill="#ff9980",
                font=("Arial", 7, "bold"), justify="center"))

            # Bottom dead zone
            self.ids.append(self.canvas.create_rectangle(
                0, int(PV_H * 0.80), PV_W, PV_H,
                fill="#ff3300", stipple="gray25", outline=""))
            self.ids.append(self.canvas.create_text(
                PV_W // 2, int(PV_H * 0.90),
                text="⛔ DEAD ZONE — Buttons + Caption Bar", fill="#ff9980",
                font=("Arial", 7, "bold"), justify="center"))

            # Right side dead zone (action buttons)
            self.ids.append(self.canvas.create_rectangle(
                int(PV_W * 0.82), int(PV_H * 0.12), PV_W, int(PV_H * 0.80),
                fill="#ff6600", stipple="gray25", outline=""))
            self.ids.append(self.canvas.create_text(
                int(PV_W * 0.91), int(PV_H * 0.46),
                text="⛔\nBTNS", fill="#ffcc99",
                font=("Arial", 6, "bold"), justify="center"))

            # ── Content zones (labeled guides) ─────────────────────────────────
            # Caption zone (55% – 75%)
            self.ids.append(self.canvas.create_rectangle(
                0, int(PV_H * 0.55), int(PV_W * 0.82), int(PV_H * 0.75),
                outline="#00ff88", dash=(5, 3), width=1))
            self.ids.append(self.canvas.create_text(
                int(PV_W * 0.41), int(PV_H * 0.65),
                text="✅ CAPTION ZONE", fill="#00ff88",
                font=("Arial", 7, "bold"), justify="center"))

            # Screenshot / Main content zone (12% – 55%)
            self.ids.append(self.canvas.create_rectangle(
                0, int(PV_H * 0.12), int(PV_W * 0.82), int(PV_H * 0.55),
                outline="#00aaff", dash=(5, 3), width=1))
            self.ids.append(self.canvas.create_text(
                int(PV_W * 0.41), int(PV_H * 0.335),
                text="📸 SCREENSHOT / MAIN CONTENT", fill="#00aaff",
                font=("Arial", 7, "bold"), justify="center"))

            # CPA link zone (75% – 80%)
            self.ids.append(self.canvas.create_rectangle(
                0, int(PV_H * 0.75), int(PV_W * 0.82), int(PV_H * 0.80),
                outline="#ffdd00", dash=(5, 3), width=1))
            self.ids.append(self.canvas.create_text(
                int(PV_W * 0.41), int(PV_H * 0.775),
                text="🔗 CPA LINK / CTA BAR", fill="#ffdd00",
                font=("Arial", 7, "bold"), justify="center"))


        # Re-apply z-order: screenshot at back, then others, then handles
        self.canvas.tag_lower(self.ids[0] if self.ids else "none")
        if self.kind == "screenshot":
            for i in self.ids: self.canvas.tag_lower(i)

    def get_bbox(self):
        if not self.ids: return None
        bboxes = [self.canvas.bbox(i) for i in self.ids]
        bboxes = [b for b in bboxes if b]
        if not bboxes: return None
        return (min(b[0] for b in bboxes), min(b[1] for b in bboxes),
                max(b[2] for b in bboxes), max(b[3] for b in bboxes))

    def _load_gif_frames(self):
        from PIL import Image, ImageSequence
        mapping = {
            "circle": "Circle Mark Sticker by bartek ujma.gif",
            "arrow": "arrow animated.gif",
            "finger": "hand pointing finger.gif",
            "cartoon": "Cartoon Look Sticker by Javi Brations.gif",
        }
        asset = mapping.get(self.kind)
        if not asset:
            return
        p = Path("assets") / asset
        if not p.exists():
            return

        cached = CanvasItem._GIF_CACHE.get(self.kind)
        if cached:
            self._gif_frames, self._gif_durations = cached
            self._gif_index = 0
            return

        try:
            img = Image.open(p)
            frames = []
            durations = []
            for frame in ImageSequence.Iterator(img):
                rgba = frame.convert("RGBA")
                frames.append(rgba.copy())
                durations.append(max(40, int(frame.info.get("duration", img.info.get("duration", 100) or 100))))
            if frames:
                self._gif_frames = frames
                self._gif_durations = durations
                self._gif_index = 0
                CanvasItem._GIF_CACHE[self.kind] = (frames, durations)
        except Exception as e:
            print(f"FAILED TO LOAD GIF {self.kind}: {e}")
            import traceback
            traceback.print_exc()
            self._gif_frames = None
            self._gif_durations = None

    def _start_animation(self):
        # Cancel existing
        try:
            if self._anim_after_id:
                self.canvas.after_cancel(self._anim_after_id)
        except Exception:
            pass

        if not self._gif_frames or not self.ids:
            return

        def _step():
            if not self._gif_frames or not self.ids:
                return
            self._gif_index = (self._gif_index + 1) % len(self._gif_frames)
            frame = self._gif_frames[self._gif_index]
            s = self.scale
            base_sizes = {"circle": (80, 80), "arrow": (80, 80), "finger": (72, 72), "cartoon": (80, 80)}
            bw, bh = base_sizes.get(self.kind, (64, 64))
            tw, th = max(1, int(bw * s)), max(1, int(bh * s))
            resized = frame.resize((tw, th), Image.LANCZOS)
            if getattr(self, "rotation", 0) != 0:
                resized = resized.rotate(-self.rotation, expand=True, resample=Image.BICUBIC)
            self.tk_img = ImageTk.PhotoImage(resized)
            # update canvas image
            try:
                self.canvas.itemconfigure(self.ids[0], image=self.tk_img)
            except Exception:
                pass
            # schedule next frame
            dur = self._gif_durations[self._gif_index] if self._gif_durations else 100
            self._anim_after_id = self.canvas.after(max(20, dur), _step)

        # start
        first_dur = self._gif_durations[0] if self._gif_durations else 100
        self._anim_after_id = self.canvas.after(max(20, first_dur), _step)

    def _stop_animation(self):
        try:
            if self._anim_after_id:
                self.canvas.after_cancel(self._anim_after_id)
                self._anim_after_id = None
        except Exception:
            pass


class CanvasEditor:
    """Manages the items on the canvas, selection, moving, and 4-corner scaling."""
    def __init__(self, canvas):
        self.canvas = canvas
        self.items = []
        self.selected = None
        self.locked = False
        
        self.handles = []
        self.rot_handle = None
        self.rot_line = None
        self.sel_rect = None
        
        self.is_dragging = False
        self.drag_mode = None # "move", "scale", "rotate"
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.start_scale = 1.0
        self.start_dist = 1.0
        
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Delete>", self.on_delete_key)

    def set_locked(self, locked):
        self.locked = locked
        if locked:
            self.select(None)

    def add_item(self, kind, x, y, text="", path=""):
        item = CanvasItem(self, kind, x, y, text=text, path=path)
        # If screenshot, insert at beginning (bottom)
        if kind == "screenshot":
            self.items.insert(0, item)
        else:
            self.items.append(item)
        self.select(item)
        return item

    def remove_item(self, item):
        if hasattr(item, "_stop_animation"):
            item._stop_animation()
        for i in item.ids: self.canvas.delete(i)
        if item in self.items: self.items.remove(item)
        if self.selected == item: self.select(None)

    def toggle_safe_zone(self):
        sz = next((i for i in self.items if i.kind == "safe_zone"), None)
        if sz:
            self.remove_item(sz)
        else:
            sz = self.add_item("safe_zone", PV_W//2, PV_H//2)
            # Ensure it's not selectable to avoid accidental drags
            self.select(None)
            for i in sz.ids: self.canvas.tag_raise(i)

    def delete_selected(self):
        if self.selected:
            self.remove_item(self.selected)

    def clear_stickers(self):
        stickers = [i for i in self.items if i.kind not in ("screenshot", "link")]
        for s in stickers: self.remove_item(s)

    def select(self, item):
        self.selected = item
        try:
            self.canvas.focus_set()
        except Exception:
            pass
        self.draw_selection()

    def draw_selection(self):
        if self.sel_rect: self.canvas.delete(self.sel_rect)
        if self.rot_line: self.canvas.delete(self.rot_line)
        if self.rot_handle: self.canvas.delete(self.rot_handle)
        for h in self.handles: self.canvas.delete(h)
        self.handles.clear()
        
        if not self.selected: return
        bbox = self.selected.get_bbox()
        if not bbox: return
        
        pad = 4
        x1, y1, x2, y2 = bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad
        self.sel_rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00d4ff", dash=(4,4), width=2)
        
        # 4 corners
        r = 6
        corners = [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
        for cx, cy in corners:
            h = self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#fff", outline="#00d4ff", width=2)
            self.handles.append(h)
            
        # Rotation handle
        hx, hy = (x1+x2)//2, y1 - 25
        self.rot_line = self.canvas.create_line((x1+x2)//2, y1, hx, hy, fill="#00d4ff", dash=(2,2))
        self.rot_handle = self.canvas.create_oval(hx-r, hy-r, hx+r, hy+r, fill="#00d4ff", outline="#fff", width=2)
            
        # Ensure handles are on top
        self.canvas.tag_raise(self.sel_rect)
        self.canvas.tag_raise(self.rot_line)
        self.canvas.tag_raise(self.rot_handle)
        for h in self.handles: self.canvas.tag_raise(h)

    def on_press(self, e):
        if self.locked:
            return

        # 0. Check rotation handle
        if self.rot_handle:
            c = self.canvas.coords(self.rot_handle)
            if c and c[0]-5 <= e.x <= c[2]+5 and c[1]-5 <= e.y <= c[3]+5:
                self.drag_mode = "rotate"
                self.drag_start_angle = math.degrees(math.atan2(e.y - self.selected.y, e.x - self.selected.x))
                self.start_rotation = getattr(self.selected, 'rotation', 0.0)
                return

        # 1. Check if clicked on a handle
        for h in self.handles:
            c = self.canvas.coords(h)
            if c and c[0]-5 <= e.x <= c[2]+5 and c[1]-5 <= e.y <= c[3]+5:
                self.drag_mode = "scale"
                self.drag_start_x = e.x
                self.drag_start_y = e.y
                self.start_scale = self.selected.scale
                # Calculate initial distance from center to mouse
                self.start_dist = math.hypot(e.x - self.selected.x, e.y - self.selected.y)
                if self.start_dist < 1: self.start_dist = 1
                return

        # 2. Check if clicked inside any item (top-most first)
        clicked_item = None
        for item in reversed(self.items):
            if item.kind == "safe_zone": continue
            bbox = item.get_bbox()
            if bbox and bbox[0] <= e.x <= bbox[2] and bbox[1] <= e.y <= bbox[3]:
                clicked_item = item
                break
                
        self.select(clicked_item)
        
        if clicked_item:
            self.drag_mode = "move"
            self.drag_start_x = e.x
            self.drag_start_y = e.y
            self.start_item_x = clicked_item.x
            self.start_item_y = clicked_item.y

    def on_drag(self, e):
        if self.locked or not self.selected:
            return
        self.is_dragging = True
        
        if self.drag_mode == "move":
            dx = e.x - self.drag_start_x
            dy = e.y - self.drag_start_y
            self.selected.x = self.start_item_x + dx
            self.selected.y = self.start_item_y + dy
            self.selected.draw()
            
        elif self.drag_mode == "scale":
            dist = math.hypot(e.x - self.selected.x, e.y - self.selected.y)
            ratio = dist / self.start_dist
            new_scale = self.start_scale * ratio
            self.selected.scale = max(0.1, min(10.0, new_scale))
            self.selected.draw()
            
        elif self.drag_mode == "rotate":
            current_angle = math.degrees(math.atan2(e.y - self.selected.y, e.x - self.selected.x))
            angle_diff = current_angle - self.drag_start_angle
            self.selected.rotation = (self.start_rotation + angle_diff) % 360
            self.selected.draw()
            
        self._redraw_all()

    def on_release(self, e):
        if self.is_dragging and self.selected and self.selected.kind == "screenshot":
            # Force high-quality redraw for image after drag
            self.is_dragging = False
            self.selected.draw()
        self.is_dragging = False
        self.drag_mode = None
        self._redraw_all()

    def on_delete_key(self, _event=None):
        if self.locked:
            return
        self.delete_selected()

    def on_right_click(self, e):
        if self.locked: return
        
        clicked_item = None
        for item in reversed(self.items):
            if item.kind == "safe_zone": continue
            bbox = item.get_bbox()
            if bbox and bbox[0] <= e.x <= bbox[2] and bbox[1] <= e.y <= bbox[3]:
                clicked_item = item
                break
                
        if not clicked_item: return
        self.select(clicked_item)
        
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="Bring to Front", command=lambda: self.bring_to_front(clicked_item))
        menu.add_command(label="Send to Back", command=lambda: self.send_to_back(clicked_item))
        menu.tk_popup(e.x_root, e.y_root)

    def bring_to_front(self, item):
        if item in self.items:
            self.items.remove(item)
            self.items.append(item)
            self._redraw_all()
            
    def send_to_back(self, item):
        if item in self.items:
            self.items.remove(item)
            self.items.insert(0, item)
            self._redraw_all()

    def _redraw_all(self):
        for item in self.items:
            if item.kind == "safe_zone": continue
            for i in item.ids:
                self.canvas.tag_raise(i)
        
        # Ensure safe_zone stays visually on top
        sz = next((i for i in self.items if i.kind == "safe_zone"), None)
        if sz:
            for i in sz.ids: self.canvas.tag_raise(i)
            
        self.draw_selection()

    def get_layout_data(self):
        # Extract screenshot layout
        ss = next((i for i in self.items if i.kind == "screenshot"), None)
        ss_ox, ss_oy, ss_zoom = 0.0, 0.0, 1.0
        if ss and ss.pil_img:
            # normalized offset from center
            ss_ox = (ss.x - PV_W/2) / PV_W
            ss_oy = (ss.y - PV_H/2) / PV_H
            # relative zoom compared to initial auto-fit scale
            auto_scale = PV_W / ss.pil_img.width
            if ss.pil_img.height * auto_scale > PV_H + 200:
                auto_scale = (PV_H+200) / ss.pil_img.height
            ss_zoom = ss.scale / auto_scale

        # Extract link layout
        link = next((i for i in self.items if i.kind == "link"), None)
        link_x, link_y = 0.5, 0.96
        if link:
            link_x = link.x / PV_W
            link_y = link.y / PV_H

        return {"ss_ox": ss_ox, "ss_oy": ss_oy, "ss_zoom": ss_zoom,
                "link_x": link_x, "link_y": link_y}

    def get_overlays(self):
        ov = []
        stickers = [i for i in self.items if i.kind not in ("screenshot", "link", "safe_zone")]
        for s in stickers:
            d = {"kind": s.kind, "cx": s.x/PV_W, "cy": s.y/PV_H, "size": s.scale, "rotation": getattr(s, "rotation", 0)}
            if s.text: d["text"] = s.text
            if s.kind == "circle":
                d["rx"] = (40 * s.scale) / PV_W
                d["ry"] = (40 * s.scale) / PV_H
            ov.append(d)
        return ov


class VideoAutomationApp:
    def __init__(self, root):
        self.root = root
        root.title("AI Video Automation Studio")
        root.geometry("1416x1128")   # +20% from original 1180x940
        root.resizable(True, True)
        root.configure(bg=BG)

        self.game_name = tk.StringVar()
        self.screenshot_path = tk.StringVar()
        self.landing_url = tk.StringVar()
        self.landing_link_color = tk.StringVar(value="#64dcff")
        self.manual_recording_path = tk.StringVar()
        self.max_videos = tk.IntVar(value=5)
        self.ratio_filter = tk.StringVar(value="Both")
        self.render_local = tk.BooleanVar(value=True)
        self.render_cloud = tk.BooleanVar(value=False)
        self.export_quality = tk.StringVar(value="1080")
        self.caption_color = tk.StringVar(value="yellow")
        self.caption_pos = tk.DoubleVar(value=0.58)
        self.link_font = tk.StringVar(value="Montserrat-Bold")
        self.custom_script = tk.StringVar()
        self.hook_start = tk.StringVar(value="0:00")  # M:SS format
        self.hook_end = tk.StringVar(value="0:10")    # M:SS format
        
        self.processing = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self._last_errors = []   # collect render error traces
        self.source_mode = tk.StringVar(value="search")  # "search" or "url"

        self.editor = None

        self.landing_url.trace_add("write", lambda *_: self._update_link())
        self.landing_link_color.trace_add("write", lambda *_: self._sync_link_color())
        self.caption_pos.trace_add("write", lambda *_: self._update_caption_preview())
        self.caption_color.trace_add("write", lambda *_: self._update_caption_preview())
        self.link_font.trace_add("write", lambda *_: self._sync_link_font())
        self._build_ui()

    def _build_ui(self):
        # ── LEFT PANEL — scrollable so all controls + log are always reachable ──
        left_outer = tk.Frame(self.root, bg=BG, width=640)
        left_outer.pack(side="left", fill="y", padx=(24, 12), pady=24)
        left_outer.pack_propagate(False)

        _lc = tk.Canvas(left_outer, bg=BG, highlightthickness=0)
        _sb = ttk.Scrollbar(left_outer, orient="vertical", command=_lc.yview)
        _lc.configure(yscrollcommand=_sb.set)
        _sb.pack(side="right", fill="y")
        _lc.pack(side="left", fill="both", expand=True)

        left = tk.Frame(_lc, bg=BG)
        _win = _lc.create_window((0, 0), window=left, anchor="nw")

        left.bind("<Configure>", lambda _: _lc.configure(scrollregion=_lc.bbox("all")))
        _lc.bind("<Configure>", lambda e: _lc.itemconfig(_win, width=e.width))
        # Mouse-wheel scrolling (Windows)
        _lc.bind_all("<MouseWheel>", lambda e: _lc.yview_scroll(int(-1 * e.delta / 120), "units"))

        tk.Label(left, text="AI VIDEO", font=("Segoe UI", 24, "bold"), fg=ACCENT, bg=BG).pack()
        tk.Label(left, text="Automation Studio", font=("Segoe UI", 12), fg=FG_DIM, bg=BG).pack()
        tk.Frame(left, bg=ACCENT, height=2).pack(fill="x", pady=(8,12))

        self._step(left,"1","Game Name",self.game_name,entry=True)
        self._step_spin(left,"2","Max Search Results",self.max_videos)
        self.screenshot_path_label = self._step(left,"3","Channel Screenshot",self.screenshot_path, btn="Choose...",cmd=self._pick_ss)
        self._step(left,"4","CPA Landing Page Link",self.landing_url,entry=True)
        self.recording_path_label = self._step(left,"5","Screen Recording (Walkthrough)",self.manual_recording_path, btn="Choose...",cmd=self._pick_recording)
        self._step(left,"6","Custom Walkthrough Script (Optional)",self.custom_script,entry=True)

        # Caption Settings
        cap_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        cap_frame.pack(fill="x", pady=3)
        ci = tk.Frame(cap_frame, bg=BG_CARD); ci.pack(fill="x", padx=10, pady=8)
        tk.Label(ci, text="Caption Color:", font=("Segoe UI", 9, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.OptionMenu(ci, self.caption_color, "yellow", "white", "green", "cyan").pack(side="left", padx=5)
        tk.Label(ci, text="Position:", font=("Segoe UI", 9, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(10,0))
        
        # Caption position with friendly labels
        cap_pos_menu = tk.OptionMenu(ci, self.caption_pos, 
                                      0.70, 0.50, 0.25, 0.85)
        cap_pos_menu.pack(side="left", padx=5)
        # Override menu to show labels
        menu = cap_pos_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="📍 Safe Zone Center (Default)", command=lambda: self.caption_pos.set(0.58))
        menu.add_command(label="📍 Slightly Lower", command=lambda: self.caption_pos.set(0.62))
        menu.add_command(label="📍 Higher", command=lambda: self.caption_pos.set(0.50))
        menu.add_command(label="📍 Very Bottom", command=lambda: self.caption_pos.set(0.78))

        # Landing Link Color and Font
        link_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        link_frame.pack(fill="x", pady=3)
        li = tk.Frame(link_frame, bg=BG_CARD); li.pack(fill="x", padx=10, pady=8)
        tk.Label(li, text="Link Color:", font=("Segoe UI", 9, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        self.link_color_btn = tk.Button(li, text="  🎨  ", font=("Segoe UI", 10), bg=self.landing_link_color.get(),
                                       relief="flat", padx=8, command=self._pick_link_color)
        self.link_color_btn.pack(side="left", padx=5)
        tk.Entry(li, textvariable=self.landing_link_color, font=("Segoe UI", 9), fg=ACCENT, bg=BG_INPUT, relief="flat", width=10).pack(side="left", padx=5)
        
        tk.Label(li, text="Font:", font=("Segoe UI", 9, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(10,0))
        fonts = ["Montserrat-Bold", "Arial-Bold", "Impact", "Verdana-Bold", "Courier-Bold", "Comic-Bold", "Roboto-Bold"]
        tk.OptionMenu(li, self.link_font, *fonts).pack(side="left", padx=5)

        # Cloud Rendering Toggle
        cloud_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        cloud_frame.pack(fill="x", pady=3)
        ci = tk.Frame(cloud_frame, bg=BG_CARD); ci.pack(fill="x", padx=10, pady=8)
        # Status indicator
        tk.Label(ci, text="☁️ CLOUD RENDERING ACTIVE", font=("Segoe UI", 10, "bold"),
             fg=GREEN, bg=BG_CARD).pack(anchor="w")
        mode_row = tk.Frame(ci, bg=BG_CARD)
        mode_row.pack(fill="x", pady=(6, 0))
        tk.Checkbutton(mode_row, text="Rendering on Local PC", variable=self.render_local,
                   command=lambda: self._sync_render_mode("local"),
                   fg=FG, bg=BG_CARD, selectcolor=BG_INPUT, activebackground=BG_CARD,
                   activeforeground=FG).pack(anchor="w")
        tk.Checkbutton(mode_row, text="Rendering in the Cloud", variable=self.render_cloud,
                   command=lambda: self._sync_render_mode("cloud"),
                   fg=FG, bg=BG_CARD, selectcolor=BG_INPUT, activebackground=BG_CARD,
                   activeforeground=FG).pack(anchor="w")

        settings_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        settings_frame.pack(fill="x", pady=3)
        si = tk.Frame(settings_frame, bg=BG_CARD); si.pack(fill="x", padx=10, pady=8)
        tk.Button(si, text="☰ Settings", font=("Segoe UI", 10, "bold"), fg=FG, bg=BG_INPUT,
              relief="flat", padx=10, pady=4, command=self._toggle_settings).pack(anchor="w")
        self.settings_panel = tk.Frame(settings_frame, bg=BG_CARD)
        tk.Label(self.settings_panel, text="Export Quality", font=("Segoe UI", 9, "bold"),
             fg=FG_DIM, bg=BG_CARD).pack(anchor="w", padx=10, pady=(6, 2))
        tk.Radiobutton(self.settings_panel, text="1080p", variable=self.export_quality, value="1080",
                   fg=FG, bg=BG_CARD, selectcolor=BG_INPUT, activebackground=BG_CARD,
                   activeforeground=FG).pack(anchor="w", padx=10)
        tk.Radiobutton(self.settings_panel, text="720p", variable=self.export_quality, value="720",
                   fg=FG, bg=BG_CARD, selectcolor=BG_INPUT, activebackground=BG_CARD,
                   activeforeground=FG).pack(anchor="w", padx=10)
        self.settings_panel.pack_forget()

        # ── SOURCE MODE TOGGLE ────────────────────────────────────────────────
        src_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        src_frame.pack(fill="x", pady=3)
        src_inner = tk.Frame(src_frame, bg=BG_CARD); src_inner.pack(fill="x", padx=10, pady=8)
        tk.Label(src_inner, text="📥  Video Source Mode", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=BG_CARD).pack(anchor="w")
        src_row = tk.Frame(src_inner, bg=BG_CARD); src_row.pack(fill="x", pady=(6,0))
        tk.Radiobutton(src_row, text="🔍  Search by Game Name (Auto-find videos)",
                       variable=self.source_mode, value="search",
                       command=self._on_source_mode_change,
                       fg=FG, bg=BG_CARD, selectcolor=BG_INPUT,
                       activebackground=BG_CARD, activeforeground=FG).pack(anchor="w")
        tk.Radiobutton(src_row, text="🔗  Paste Direct URL (YouTube / TikTok / Instagram)",
                       variable=self.source_mode, value="url",
                       command=self._on_source_mode_change,
                       fg=FG, bg=BG_CARD, selectcolor=BG_INPUT,
                       activebackground=BG_CARD, activeforeground=FG).pack(anchor="w")

        # ── DIRECT URL PANEL (hidden by default, shown when url mode active) ──
        self.direct_url_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        du_inner = tk.Frame(self.direct_url_frame, bg=BG_CARD)
        du_inner.pack(fill="x", padx=10, pady=8)
        tk.Label(du_inner, text="🔗  Paste Video URL", font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=BG_CARD).pack(anchor="w")
        tk.Label(du_inner, text="Paste a YouTube, TikTok, or Instagram video link below.",
                 font=("Segoe UI", 8), fg=FG_DIM, bg=BG_CARD).pack(anchor="w", pady=(2, 6))
        self.direct_url_var = tk.StringVar()
        du_entry_row = tk.Frame(du_inner, bg=BG_CARD); du_entry_row.pack(fill="x")
        self.direct_url_entry = tk.Entry(du_entry_row, textvariable=self.direct_url_var,
                                          font=("Segoe UI", 9), fg=FG, bg=BG_INPUT,
                                          relief="flat", insertbackground=FG)
        self.direct_url_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        tk.Button(du_entry_row, text="📋 Paste", font=("Segoe UI", 9, "bold"),
                  fg="#fff", bg=BG_INPUT, relief="flat", padx=8,
                  command=lambda: self.direct_url_var.set(self.root.clipboard_get())).pack(side="left")
        # Trim range for direct URL — M:SS format
        du_trim = tk.Frame(du_inner, bg=BG_CARD); du_trim.pack(fill="x", pady=(8, 0))
        tk.Label(du_trim, text="⏱ Hook from:", font=("Segoe UI", 8, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.Entry(du_trim, textvariable=self.hook_start, width=6,
                 font=("Segoe UI", 9), fg=FG, bg=BG_INPUT, relief="flat",
                 insertbackground=FG).pack(side="left", padx=(4, 8), ipady=3)
        tk.Label(du_trim, text="to:", font=("Segoe UI", 8, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.Entry(du_trim, textvariable=self.hook_end, width=6,
                 font=("Segoe UI", 9), fg=FG, bg=BG_INPUT, relief="flat",
                 insertbackground=FG).pack(side="left", padx=(4, 0), ipady=3)
        tk.Label(du_trim, text="(M:SS)", font=("Segoe UI", 7), fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(6, 0))
        # Pack once so Tkinter registers the widget, then immediately hide it
        self.direct_url_frame.pack(fill="x", pady=3)
        self.direct_url_frame.pack_forget()

        # Results Listbox
        self.results_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_INPUT)
        self.results_frame.pack(fill="x", pady=3)
        rf_hdr = tk.Frame(self.results_frame, bg=BG_CARD)
        rf_hdr.pack(fill="x", padx=10, pady=4)
        tk.Label(rf_hdr, text="Search Results (Select to process)", font=("Segoe UI", 9, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")

        self.search_btn = tk.Button(rf_hdr, text="🔍 SEARCH", font=("Segoe UI", 9, "bold"), fg="#fff", bg=ACCENT, relief="flat", padx=8, pady=2, command=self._on_search)
        self.search_btn.pack(side="right")

        # Ratio filter dropdown
        ratio_row = tk.Frame(self.results_frame, bg=BG_CARD)
        ratio_row.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(ratio_row, text="Format Filter:", font=("Segoe UI", 8, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.OptionMenu(ratio_row, self.ratio_filter, "Both", "9:16 only", "16:9 only").pack(side="left", padx=6)
        tk.Label(ratio_row, text="(applies on next search)", font=("Segoe UI", 7), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        
        trim_frame = tk.Frame(self.results_frame, bg=BG_CARD)
        trim_frame.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(trim_frame, text="⏱ Hook from:", font=("Segoe UI", 8, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.Entry(trim_frame, textvariable=self.hook_start, width=6,
                 font=("Segoe UI", 9), fg=FG, bg=BG_INPUT, relief="flat",
                 insertbackground=FG).pack(side="left", padx=(4, 8), ipady=3)
        tk.Label(trim_frame, text="to:", font=("Segoe UI", 8, "bold"), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.Entry(trim_frame, textvariable=self.hook_end, width=6,
                 font=("Segoe UI", 9), fg=FG, bg=BG_INPUT, relief="flat",
                 insertbackground=FG).pack(side="left", padx=(4, 8), ipady=3)
        tk.Label(trim_frame, text="(M:SS)", font=("Segoe UI", 7), fg=FG_DIM, bg=BG_CARD).pack(side="left")
        
        list_frame = tk.Frame(self.results_frame, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0,4))
        self.results_listbox = tk.Listbox(list_frame, bg=BG_INPUT, fg=FG, selectbackground=ACCENT,
                                          selectmode="extended",  # single click = one item, Ctrl+Click = multi
                                          height=6, font=("Consolas", 8))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.results_listbox.yview)
        self.results_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.results_listbox.pack(side="left", fill="both", expand=True)
        # Double-click opens the video URL in browser
        self.results_listbox.bind("<Double-Button-1>", lambda e: self._open_selected_video_url())

        # Open URL button row
        url_btn_row = tk.Frame(self.results_frame, bg=BG_CARD)
        url_btn_row.pack(fill="x", padx=10, pady=(0, 6))
        tk.Button(
            url_btn_row, text="🔗 Open Selected Video in Browser",
            font=("Segoe UI", 8, "bold"), fg="#fff", bg="#1565c0",
            relief="flat", padx=10, pady=3,
            command=self._open_selected_video_url
        ).pack(side="left")
        tk.Label(url_btn_row, text="(or double-click a result)",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=6)

        self.current_search_results = []

        bf = tk.Frame(left, bg=BG); bf.pack(pady=(12,6))
        self.gen_btn = tk.Button(bf, text="GENERATE", font=("Segoe UI",14,"bold"),
            fg="#fff", bg=GREEN, relief="flat", padx=25, pady=10, command=self._on_gen)
        self.gen_btn.pack(side="left", padx=(0,8))
        self.pause_btn = tk.Button(bf, text="PAUSE", font=("Segoe UI",12,"bold"),
            fg="#fff", bg=ORANGE, relief="flat", padx=15, pady=10, command=self._on_pause, state="disabled")
        self.pause_btn.pack(side="left")
        self.cancel_btn = tk.Button(bf, text="X", font=("Segoe UI",12,"bold"),
            fg="#fff", bg=RED, relief="flat", padx=15, pady=10, command=self._on_cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8,0))

        self.status_lbl = tk.Label(left, text="Ready", font=("Segoe UI",10), fg=FG_DIM, bg=BG, anchor="w")
        self.status_lbl.pack(fill="x")
        s=ttk.Style(); s.theme_use("clam")
        s.configure("C.Horizontal.TProgressbar", troughcolor=BG_CARD, background=ACCENT, bordercolor=BG, thickness=14)
        self.pbar = ttk.Progressbar(left, style="C.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.pbar.pack(fill="x", pady=(4,6))
        
        self.log_box = tk.Text(left, height=8, font=("Consolas",8), bg=BG_CARD, fg=FG_DIM, relief="flat", wrap="word", state="disabled", highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_INPUT)
        self.log_box.pack(fill="both", expand=True)

        output_frame = tk.Frame(left, bg=BG_CARD, highlightthickness=1, highlightbackground=ACCENT)
        output_frame.pack(fill="x", pady=(8, 0))
        out_hdr = tk.Frame(output_frame, bg=BG_CARD)
        out_hdr.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(out_hdr, text="Rendered Output", font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=BG_CARD).pack(side="left")

        # Thumbnail preview area
        self.thumb_label = tk.Label(output_frame, bg=BG_CARD, text="🎬 No output yet",
                                     font=("Segoe UI", 9), fg=FG_DIM, cursor="hand2",
                                     relief="flat", width=40, height=4)
        self.thumb_label.pack(fill="x", padx=10, pady=(0, 4))
        self.thumb_label.bind("<Button-1>", self._open_output_url)

        # Export buttons row (hidden until render completes)
        self.export_btns_frame = tk.Frame(output_frame, bg=BG_CARD)
        self.export_btns_frame.pack(fill="x", padx=10, pady=(0, 8))
        self.btn_export_1080 = tk.Button(
            self.export_btns_frame, text="⬇ Export 1080p",
            font=("Segoe UI", 9, "bold"), fg="#fff", bg="#6200ea",
            relief="flat", padx=10, pady=5,
            command=lambda: self._do_export("1080")
        )
        self.btn_export_720 = tk.Button(
            self.export_btns_frame, text="⬇ Export 720p",
            font=("Segoe UI", 9, "bold"), fg="#fff", bg="#37474f",
            relief="flat", padx=10, pady=5,
            command=lambda: self._do_export("720")
        )
        self.btn_open_folder = tk.Button(
            self.export_btns_frame, text="📂 Open Folder",
            font=("Segoe UI", 9), fg=FG, bg=BG_INPUT,
            relief="flat", padx=8, pady=5,
            command=self._open_output_folder
        )
        # Keep a reference to last rendered path
        self._last_rendered_path = ""
        self.output_url_var = tk.StringVar(value="")
        # Hide buttons initially
        for w in (self.btn_export_1080, self.btn_export_720, self.btn_open_folder):
            w.pack_forget()

        # RIGHT PANEL
        right = tk.Frame(self.root, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(10,24), pady=20)

        tk.Label(right, text="PREVIEW EDITOR", font=("Segoe UI",12,"bold"), fg=ACCENT, bg=BG).pack()
        tk.Label(right, text="Drag elements to move | Drag corners to resize", font=("Segoe UI",9), fg=FG_DIM, bg=BG).pack(pady=(0,6))

        cf = tk.Frame(right, bg="#000", highlightthickness=2, highlightbackground=ACCENT)
        cf.pack()
        self.canvas = tk.Canvas(cf, width=PV_W, height=PV_H, bg="#111", highlightthickness=0)
        self.canvas.pack()
        
        self.editor = CanvasEditor(self.canvas)
        self.editor.link_color = self.landing_link_color.get()
        self.editor.link_font = self.link_font.get()
        self.canvas.create_text(PV_W//2, PV_H//2, text="Choose a screenshot\nto see preview", fill=FG_DIM, font=("Segoe UI",11), justify="center", tags="ph")

        # Stickers toolbar
        tk.Label(right, text="Add Stickers:", font=("Segoe UI",9,"bold"), fg=FG, bg=BG).pack(pady=(10,2))
        tk.Label(right, text="(placed at top of frame — drag to reposition)",
                 font=("Segoe UI",8), fg=FG_DIM, bg=BG).pack(pady=(0,2))
        tb1 = tk.Frame(right, bg=BG); tb1.pack(pady=2)
        for txt, kind in [("O Circle", "circle"), ("\u25bc Arrow", "arrow"), ("\u261d Finger", "finger"), ("★ Cartoon", "cartoon")]:
            tk.Button(tb1, text=txt, font=("Segoe UI",9,"bold"), fg="#fff", bg="#e53935",
                      relief="flat", padx=8, pady=2,
                      command=lambda k=kind: self.editor.add_item(k, PV_W//2, int(PV_H * 0.12))
                      ).pack(side="left", padx=3)

        tb2 = tk.Frame(right, bg=BG); tb2.pack(pady=2)
        for label in ["Click Here!", "Download!", "Subscribe!", "Link Here \u2193", "FREE!"]:
            tk.Button(tb2, text=label, font=("Segoe UI",8,"bold"), fg="#000", bg="#ffeb3b",
                      relief="flat", padx=6, pady=2,
                      command=lambda t=label: self.editor.add_item("text", PV_W//2, int(PV_H * 0.12), text=t)
                      ).pack(side="left", padx=2)

        action_bar = tk.Frame(right, bg=BG)
        action_bar.pack(pady=4)
        tk.Button(action_bar, text="Delete Selected", font=("Segoe UI",9), fg="#fff", bg=RED,
                  relief="flat", padx=10, pady=2, command=self.editor.delete_selected).pack(side="left", padx=4)
        tk.Button(action_bar, text="Toggle Safe Zone", font=("Segoe UI",9,"bold"), fg="#fff", bg="#444",
                  relief="flat", padx=10, pady=2, command=self.editor.toggle_safe_zone).pack(side="left", padx=4)
        tk.Button(action_bar, text="Clear All Stickers", font=("Segoe UI",9), fg="#fff", bg=FG_DIM,
                  relief="flat", padx=10, pady=2, command=self.editor.clear_stickers).pack(side="left", padx=4)

    def _step(self, p, n, l, v, entry=False, btn=None, cmd=None):
        c=tk.Frame(p,bg=BG_CARD,highlightthickness=1,highlightbackground=BG_INPUT)
        c.pack(fill="x",pady=3)
        i=tk.Frame(c,bg=BG_CARD); i.pack(fill="x",padx=10,pady=6)
        h=tk.Frame(i,bg=BG_CARD); h.pack(fill="x")
        tk.Label(h,text=f" {n} ",font=("Segoe UI",9,"bold"),fg="#fff",bg=ACCENT).pack(side="left",padx=(0,6))
        tk.Label(h,text=l,font=("Segoe UI",10,"bold"),fg=FG,bg=BG_CARD).pack(side="left")
        r=tk.Frame(i,bg=BG_CARD); r.pack(fill="x",pady=(4,0))
        if entry:
            tk.Entry(r,textvariable=v,font=("Segoe UI",10),fg=FG,bg=BG_INPUT, insertbackground=FG,relief="flat",highlightthickness=1, highlightcolor=ACCENT,highlightbackground=BG_INPUT).pack(fill="x",ipady=4)
        else:
            lbl = tk.Label(r,textvariable=v,font=("Segoe UI",9),fg=ORANGE,bg=BG_INPUT, anchor="w",padx=6,pady=3)
            lbl.pack(side="left",fill="x",expand=True)
            if btn: tk.Button(r,text=btn,font=("Segoe UI",9),fg="#fff",bg=ACCENT, relief="flat",padx=8,command=cmd).pack(side="right",padx=(6,0))
            return lbl

    def _step_spin(self, p, n, l, v):
        c=tk.Frame(p,bg=BG_CARD,highlightthickness=1,highlightbackground=BG_INPUT)
        c.pack(fill="x",pady=3)
        i=tk.Frame(c,bg=BG_CARD); i.pack(fill="x",padx=10,pady=6)
        h=tk.Frame(i,bg=BG_CARD); h.pack(fill="x")
        tk.Label(h,text=f" {n} ",font=("Segoe UI",9,"bold"),fg="#fff",bg=ACCENT).pack(side="left",padx=(0,6))
        tk.Label(h,text=l,font=("Segoe UI",10,"bold"),fg=FG,bg=BG_CARD).pack(side="left")
        r=tk.Frame(i,bg=BG_CARD); r.pack(fill="x",pady=(4,0))
        tk.Spinbox(r,from_=1,to=30,textvariable=v,width=4,font=("Segoe UI",12,"bold"), fg=ACCENT,bg=BG_INPUT,relief="flat",justify="center").pack(side="left")

    def _pick_ss(self):
        p = filedialog.askopenfilename(title="Screenshot", filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.bmp")])
        if p:
            self.screenshot_path.set(p)
            self.canvas.delete("ph")
            # Remove old ss
            old_ss = next((i for i in self.editor.items if i.kind == "screenshot"), None)
            if old_ss: self.editor.remove_item(old_ss)
            
            # Calculate initial fit scale
            img = Image.open(p)
            scale = PV_W / img.width
            if img.height * scale > PV_H + 200:
                scale = (PV_H+200) / img.height
            
            ss = self.editor.add_item("screenshot", PV_W//2, PV_H//2, path=p)
            ss.scale = scale
            ss.draw()
            self._update_link()

    def _pick_recording(self):
        p = filedialog.askopenfilename(title="Screen Recording", filetypes=[("Videos","*.mp4 *.mov *.avi *.mkv *.webm")])
        if p:
            self.manual_recording_path.set(p)
            self._log(f"Screen recording selected: {Path(p).name}")

    def _pick_link_color(self):
        from tkinter.colorchooser import askcolor
        color = askcolor(color=self.landing_link_color.get(), title="Choose Landing Link Color")
        if color[1]:
            self.landing_link_color.set(color[1])
            self.link_color_btn.configure(bg=color[1])
            self._sync_link_color()

    def _sync_link_color(self):
        if not getattr(self, "editor", None):
            return
        self.editor.link_color = self.landing_link_color.get()
        link = next((i for i in self.editor.items if i.kind == "link"), None)
        if link:
            link.draw()

    def _sync_link_font(self):
        if getattr(self, "editor", None):
            self.editor.link_font = self.link_font.get()
            link = next((i for i in self.editor.items if i.kind == "link"), None)
            if link: link.draw()
            self._update_caption_preview()

    def _update_link(self):
        url = self.landing_url.get().strip()
        link = next((i for i in self.editor.items if i.kind == "link"), None)
        if url:
            if not link:
                self.editor.add_item("link", PV_W//2, PV_H-20, text=url)
            else:
                link.text = url
                link.draw()
        elif link:
            self.editor.remove_item(link)
        self.editor.draw_selection()

    def _update_caption_preview(self):
        if not getattr(self, "editor", None): return
        pos = self.caption_pos.get()
        color = self.caption_color.get()
        y_pos = int(PV_H * pos)
        
        tk_fnt = self.link_font.get().split("-")[0]
        if tk_fnt == "Comic": tk_fnt = "Comic Sans MS"
        if tk_fnt == "Montserrat": tk_fnt = "Arial"
        
        # Remove old dummy caption if exists
        self.editor.canvas.delete("dummy_caption")
        text = "Llama 3 Generated Subtitle"
        fnt = (tk_fnt, max(10, int(15 * (PV_W/300))), "bold")
        
        # Draw stroke/background
        t_id = self.editor.canvas.create_text(PV_W//2, y_pos, text=text, font=fnt, tags="dummy_caption")
        bbox = self.editor.canvas.bbox(t_id)
        if bbox:
            self.editor.canvas.create_rectangle(bbox[0]-6, bbox[1]-2, bbox[2]+6, bbox[3]+2, fill="#111", outline="", tags="dummy_caption")
            self.editor.canvas.tag_raise(t_id)
        self.editor.canvas.itemconfig(t_id, fill=color)

    # --- Log ---
    def _log(self, m):
        self.log_box.configure(state="normal"); self.log_box.insert("end",m+"\n")
        self.log_box.see("end"); self.log_box.configure(state="disabled")
    def _sts(self, m, c=FG_DIM): self.status_lbl.configure(text=m, fg=c)
    def _prg(self, v): self.pbar["value"] = v

    def _set_output_url(self, url):
        self.output_url = url
        self._last_rendered_path = url or ""
        self.output_url_var.set(url or "")
        # Update thumbnail label
        if url and url != "No output yet":
            name = Path(url).name if (os.path.exists(url) or "." in url.split("/")[-1]) else url
            self.thumb_label.configure(text=f"🎬 {name}", fg=GREEN)
            # Show export buttons
            self.btn_export_1080.pack(side="left", padx=(0, 6))
            self.btn_export_720.pack(side="left", padx=(0, 6))
            self.btn_open_folder.pack(side="left")
        else:
            self.thumb_label.configure(text="🎬 No output yet", fg=FG_DIM)
            for w in (self.btn_export_1080, self.btn_export_720, self.btn_open_folder):
                w.pack_forget()

    def _do_export(self, quality: str):
        """Export the rendered video at the given quality."""
        url = self._last_rendered_path
        if not url:
            messagebox.showinfo("No Output", "No rendered video found.\nRun GENERATE first.")
            return
        if quality == "720" and os.path.exists(url):
            self._log("Converting to 720p...")
            threading.Thread(target=self._export_720p_thread, args=(url,), daemon=True).start()
        else:
            self._export_to_preview()

    def _export_720p_thread(self, source_path: str):
        result = self._make_720p_copy(source_path)
        self.root.after(0, self._log, f"✓ 720p saved: {Path(result).name}")
        self.root.after(0, self._set_output_url, result)
        try:
            import sys
            if sys.platform == "win32":
                os.startfile(result)
        except Exception:
            pass

    def _open_output_folder(self):
        url = self._last_rendered_path
        if url and os.path.exists(url):
            folder = str(Path(url).parent)
            try:
                import subprocess
                subprocess.Popen(f'explorer "{folder}"')
            except Exception:
                pass

    def _open_output_url(self, _event=None):
        url = getattr(self, "output_url", "")
        if url:
            if os.path.exists(url):
                webbrowser.open(Path(url).resolve().as_uri())
            else:
                webbrowser.open(url)

    def _export_to_preview(self):
        """Export / open the last rendered video in the OS Preview Studio."""
        url = getattr(self, "output_url", "")
        if not url or url == "No output yet":
            messagebox.showinfo(
                "No Output",
                "No rendered video found.\nRun GENERATE first, then click Export."
            )
            return

        local_path = None
        if os.path.exists(url):
            local_path = Path(url).resolve()
        elif url.startswith("http"):
            # Cloud output — download to a temp file then open
            self._log("Downloading cloud video for preview...")
            try:
                import tempfile
                resp = requests.get(url, timeout=120, stream=True)
                resp.raise_for_status()
                
                content_type = resp.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    messagebox.showerror("Download Error", "The cloud server returned a web page instead of a video. It might be sleeping or erroring.")
                    return

                suffix = ".mp4"
                tmp_file = Path(tempfile.mktemp(suffix=suffix))
                with open(tmp_file, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                local_path = tmp_file
                self._log(f"Downloaded to {local_path}")
            except Exception as exc:
                messagebox.showerror("Download Error", f"Could not download video:\n{exc}")
                return

        if local_path and local_path.exists():
            try:
                import subprocess, sys
                if sys.platform == "win32":
                    os.startfile(str(local_path))   # Windows Media Player / Photos
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(local_path)])  # macOS QuickTime
                else:
                    subprocess.run(["xdg-open", str(local_path)])  # Linux
                self._log(f"✓ Opened in Preview Studio: {local_path.name}")
            except Exception as exc:
                messagebox.showerror("Preview Error", f"Could not open preview:\n{exc}")
        else:
            messagebox.showwarning("File Not Found", f"Video file not found at:\n{url}")

    def _on_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear(); self.pause_btn.configure(text="RESUME",bg=GREEN)
            self._sts("PAUSED",ORANGE); self._log("--- PAUSED ---")
        else:
            self.pause_event.set(); self.pause_btn.configure(text="PAUSE",bg=ORANGE)
            self._sts("Resuming...",ACCENT); self._log("--- RESUMED ---")

    def _on_cancel(self):
        if not self.processing: return
        self._log("--- CANCELLED BY USER ---")
        self._sts("Cancelled", RED)
        self.processing = False
        self.pause_event.set()
        self.pause_btn.configure(state="disabled", text="PAUSE", bg=ORANGE)
        self.cancel_btn.configure(state="disabled")
        self.gen_btn.configure(state="normal", bg=GREEN)
        self.editor.set_locked(False)

    def _wait(self):
        while not self.pause_event.is_set():
            if not self.processing: return
            time.sleep(0.3)
        if not self.processing: raise Exception("Cancelled by user")

    def _open_selected_video_url(self):
        """Open the URL of the selected search result in the default browser."""
        sel = self.results_listbox.curselection()
        if not sel:
            messagebox.showinfo("No Selection", "Select a video from the list first.")
            return
        idx = sel[0]
        if idx >= len(self.current_search_results):
            return
        meta = self.current_search_results[idx]
        url = meta.get("webpage_url") or meta.get("url", "")
        if url:
            webbrowser.open(url)
            self._log(f"  🔗 Opened in browser: {url}")
        else:
            messagebox.showwarning("No URL", "No URL found for this result.")

    def _on_search(self):
        g = self.game_name.get().strip()
        mx = self.max_videos.get()
        if not g:
            messagebox.showwarning("Missing", "Enter game name first.")
            return
            
        self.search_btn.configure(state="disabled", text="Searching...")
        self.results_listbox.delete(0, tk.END)
        self.current_search_results = []
        self._sts("Searching...", ACCENT)
        ratio_f = self.ratio_filter.get()
        self._log(f"Searching for '{g}' | Filter: {ratio_f} | Max: {mx}")

        threading.Thread(target=self._search_thread, args=(g, mx, ratio_f), daemon=True).start()

    def _search_thread(self, game, mx, ratio_f="Both"):
        from scraper import VideoScraper
        from config import Config
        cfg = Config()
        scraper = VideoScraper(config=cfg)
        cands = scraper.search(game, max_results=mx)
        
        def update_ui():
            self.search_btn.configure(state="normal", text="🔍 SEARCH")
            if not cands:
                self._sts("No results found.", RED)
                self._log("No videos found.")
                return

            self._sts(f"Found {len(cands)} results.", GREEN)

            # ── Apply ratio filter ──────────────────────────────────────────
            def _detect_ratio(c):
                w, h = c.get("width"), c.get("height")
                if w and h and w > 0 and h > 0:
                    return "9:16" if h > w else "16:9"
                url_lower = (c.get("webpage_url") or c.get("url", "")).lower()
                t_lower = c.get("title", "").lower()
                plat = c.get("platform", "")
                is_short = (
                    "/shorts/" in url_lower
                    or "tiktok.com" in url_lower
                    or "instagram.com/reel" in url_lower
                    or "facebook.com/reel" in url_lower
                    or plat in ("TikTok", "Instagram Reels", "Facebook Reels")
                    or "short" in t_lower
                    or "#shorts" in t_lower
                )
                return "9:16" if is_short else "16:9"

            # Use a NEW variable so Python doesn't treat `cands` as local
            if ratio_f == "9:16 only":
                visible = [c for c in cands if _detect_ratio(c) == "9:16"]
            elif ratio_f == "16:9 only":
                visible = [c for c in cands if _detect_ratio(c) == "16:9"]
            else:
                visible = list(cands)  # "Both" — show everything

            if not visible:
                self._sts(f"No results matched '{ratio_f}' filter.", ORANGE)
                self._log(f"No videos matched '{ratio_f}'. Try 'Both' or search again.")
                return

            self._log(f"Showing {len(visible)} result(s) [{ratio_f}].")
            self.current_search_results = visible
            for i, c in enumerate(visible):
                title = c.get("title", "Unknown")[:45]
                platform = c.get("platform", "Unknown")
                dur = c.get("duration", 0)
                dur_str = f"[{dur}s]" if dur else ""
                video_url = c.get("webpage_url") or c.get("url", "")
                short_url = video_url[:55] + "..." if len(video_url) > 55 else video_url

                ratio = _detect_ratio(c)  # reuse the same helper — no duplication

                display_text = f"[{ratio}] {dur_str} {title}  |  {short_url}"
                self.results_listbox.insert("end", display_text)
                if ratio == "9:16":
                    self.results_listbox.itemconfig(i, fg=GREEN)
                else:
                    self.results_listbox.itemconfig(i, fg=ORANGE)


            if cands:
                self.results_listbox.selection_set(0)
                
        self.root.after(0, update_ui)

    def _parse_mss(self, value: str, default: int = 0) -> int:
        """Convert M:SS or plain seconds string to integer seconds.
        Examples: '0:10' -> 10,  '1:30' -> 90,  '45' -> 45"""
        try:
            s = str(value).strip()
            if ":" in s:
                parts = s.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            return int(float(s))
        except Exception:
            return default

    def _on_source_mode_change(self):
        """Show/hide the search panel or direct URL panel based on current mode."""
        if self.source_mode.get() == "url":
            self.results_frame.pack_forget()
            self.direct_url_frame.pack(fill="x", pady=3)
        else:
            self.direct_url_frame.pack_forget()
            self.results_frame.pack(fill="x", pady=3)

    def _on_gen(self):
        g=self.game_name.get().strip(); ss=self.screenshot_path.get().strip()
        u=self.landing_url.get().strip(); c=self.max_videos.get()
        if not g and self.source_mode.get() != "url":
            messagebox.showwarning("Missing","Enter game name."); return
        if not u: messagebox.showwarning("Missing","Enter CPA link."); return
        if self.processing: return

        # ── DIRECT URL MODE ──
        if self.source_mode.get() == "url":
            direct_url = self.direct_url_var.get().strip()
            if not direct_url:
                messagebox.showwarning("Missing URL", "Please paste a video URL first.")
                return
            # Game name is optional in URL mode — fall back to domain name
            if not g:
                try:
                    from urllib.parse import urlparse
                    g = urlparse(direct_url).netloc.replace("www.", "").split(".")[0].title()
                except Exception:
                    g = "Video"
            self.processing = True; self.pause_event.set()
            self.gen_btn.configure(state="disabled", bg=FG_DIM)
            self.pause_btn.configure(state="normal")
            self.cancel_btn.configure(state="normal"); self._prg(0)
            self.editor.set_locked(True)
            self._set_output_url("No output yet")
            self.editor.select(None)
            ov = self.editor.get_overlays()
            layout = self.editor.get_layout_data()
            cloud_mode = self.render_cloud.get()
            rec = self.manual_recording_path.get().strip()
            custom_txt = self.custom_script.get().strip()
            hs = self._parse_mss(self.hook_start.get(), 0)
            he = self._parse_mss(self.hook_end.get(), 10)
            self._log(f"Starting URL mode: {direct_url} | Hook {hs}s → {he}s")
            threading.Thread(
                target=self._run_direct_url,
                args=(g, direct_url, ss, u, ov, layout, cloud_mode, rec, custom_txt, hs, he),
                daemon=True
            ).start()
            return

        # ── SEARCH MODE ──
        
        selected_indices = self.results_listbox.curselection()
        if not self.current_search_results:
            messagebox.showinfo("Search First", "Please click '🔍 SEARCH' to find videos, then select which ones you want to process.")
            return
            
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select at least one video from the search results to process.")
            return
            
        vids_to_process = [self.current_search_results[i] for i in selected_indices]
        
        self.processing=True; self.pause_event.set()
        self.gen_btn.configure(state="disabled",bg=FG_DIM)
        self.pause_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal"); self._prg(0)

        # Lock the editor so stickers cannot be moved while render/upload is running.
        self.editor.set_locked(True)
        self._set_output_url("No output yet")
        
        # Deselect to hide handles in preview (though it doesn't affect render)
        self.editor.select(None)
        
        ov=self.editor.get_overlays()
        layout=self.editor.get_layout_data()
        cloud_mode = self.render_cloud.get()
        
        rec = self.manual_recording_path.get().strip()
        custom_txt = self.custom_script.get().strip()
        hs = self._parse_mss(self.hook_start.get(), 0)
        he = self._parse_mss(self.hook_end.get(), 10)
        reward_mode = bool(rec and os.path.exists(rec))
        
        self._log(f"Starting: {g} {'(Reward-First)' if reward_mode else '(Legacy)'} {'(Cloud)' if cloud_mode else '(Local)'} | Hook {hs}s → {he}s")
        threading.Thread(target=self._run, args=(g,vids_to_process,ss,u,ov,layout,cloud_mode,rec,custom_txt,hs,he), daemon=True).start()

    def _run_direct_url(self, game, direct_url, ss, url, overlays, layout, cloud_mode, recording_path="", custom_script="", hook_start=0, hook_end=10):
        """Download a single user-provided URL, trim the hook, then process it just like a scraped video."""
        cfg = Config()
        scraper = VideoScraper(config=cfg)
        reward_mode = bool(recording_path and os.path.exists(recording_path))
        export_quality = self.export_quality.get()
        cloud_url = os.getenv("CLOUD_API_URL", "")

        self.root.after(0, self._log, f"  ⬇ Downloading from URL: {direct_url[:60]}...")
        self.root.after(0, self._prg, 10)

        try:
            import hashlib
            url_id = hashlib.md5(direct_url.encode()).hexdigest()[:8]  # short unique ID for file finding
            # meta dict that scraper.download / download_hook expect
            meta = {"url": direct_url, "webpage_url": direct_url, "title": game, "id": url_id}
            if reward_mode:
                # Use correct kwarg names: hook_start and hook_end (not start/duration)
                raw = scraper.download_hook(meta, hook_start=hook_start, hook_end=hook_end)
            else:
                # For legacy mode, still trim to hook_end seconds max using download_hook
                raw = scraper.download_hook(meta, hook_start=hook_start, hook_end=hook_end)

            if not raw or not Path(str(raw)).exists():
                self.root.after(0, self._log, "  ❌ Download failed — check the URL and your internet.")
                self._fin(0); return

            self.root.after(0, self._log, f"  ✓ Download complete: {Path(str(raw)).name}")
            self.root.after(0, self._prg, 30)

            # Wrap into a fake one-item list so we can reuse _run's per-video loop
            # by just calling the processing steps directly
            processor = VideoProcessor(
                elevenlabs_key=os.getenv("ELEVENLABS_API_KEY", ""),
                elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
                groq_key=os.getenv("GROQ_API_KEY", "")
            ) if not cloud_mode else None

            self.root.after(0, self._log, "  🎬 Processing video...")
            self.root.after(0, self._prg, 40)

            if cloud_mode:
                # Upload to cloud — reuse the same cloud upload path from _run
                self._run(game, [{"url": direct_url, "title": game}], ss, url, overlays, layout,
                          cloud_mode, recording_path, custom_script, hook_start, hook_end,
                          _override_raw=str(raw))
                return

            if reward_mode:
                out_path = processor.process_reward_first(
                    scraped_video_path=str(raw),
                    manual_recording_path=recording_path,
                    game_name=game,
                    channel_screenshot=ss,
                    landing_url=url,
                    overlay_data=overlays,
                    layout=layout,
                    caption_color=self.caption_color.get(),
                    caption_pos=self.caption_pos.get(),
                    landing_link_color=self.landing_link_color.get(),
                    link_font_name=self.link_font.get(),
                    progress_callback=lambda p, msg: self.root.after(0, self._log, f"  [{p}%] {msg}"),
                    custom_script=custom_script,
                    hook_duration=h_dur
                )
            else:
                out_path = processor.process(
                    input_path=str(raw),
                    game_name=game,
                    channel_screenshot=ss,
                    landing_url=url,
                    progress_callback=lambda p, m: self.root.after(0, self._log, f"  [{p}%] {m}"),
                    overlay_data=overlays,
                    layout=layout,
                    caption_color=self.caption_color.get(),
                    caption_pos=self.caption_pos.get(),
                    landing_link_color=self.landing_link_color.get(),
                    link_font_name=self.link_font.get()
                )

            final_path = str(out_path)
            if export_quality == "720":
                final_path = self._make_720p_copy(final_path)

            self.root.after(0, self._set_output_url, final_path)
            self.root.after(0, self._log, f"  ✓ Render complete: {final_path}")
            self.root.after(0, self._prg, 90)

            # Send to Telegram
            self.root.after(0, self._log, "  📱 Sending to Telegram...")
            try:
                import requests as req
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
                tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
                if tg_token and tg_chat:
                    with open(final_path, "rb") as f:
                        r = req.post(
                            f"https://api.telegram.org/bot{tg_token}/sendVideo",
                            data={"chat_id": tg_chat, "caption": f"✅ Direct URL Render: {game}"},
                            files={"video": f}, timeout=600
                        )
                    if r.ok:
                        self.root.after(0, self._log, "  ✅ Sent to Telegram!")
                    else:
                        self.root.after(0, self._log, f"  ❌ Telegram: {r.text[:200]}")
                else:
                    self.root.after(0, self._log, "  ⚠ Telegram not configured in .env")
            except Exception as te:
                self.root.after(0, self._log, f"  ❌ Telegram Upload Failed: {te}")

            self._fin(1)

        except Exception as e:
            import traceback as _tb
            self.root.after(0, self._log, f"  ❌ ERROR: {e}")
            log.error(f"Direct URL render error:\n{_tb.format_exc()}")
            self._fin(0)

    def _run(self, game, vids, ss, url, overlays, layout, cloud_mode, recording_path="", custom_script="", hook_start=0, hook_end=10, _override_raw=None):
        cfg=Config()
        reward_mode = bool(recording_path and os.path.exists(recording_path))
        
        scraper=VideoScraper(config=cfg)
        self.root.after(0,self._prg,10)
        
        cloud_url = os.getenv("CLOUD_API_URL", "")
        export_quality = self.export_quality.get()

        if cloud_mode and not cloud_url:
            self.root.after(0, self._log, "❌ FATAL ERROR: CLOUD_API_URL not set in .env")
            self.root.after(0, lambda: messagebox.showerror("Error", "Cloud Rendering is required. Please set CLOUD_API_URL in your .env file."))
            self._fin(0); return

        processor = None
        if not cloud_mode:
            processor = VideoProcessor(
                elevenlabs_key=os.getenv("ELEVENLABS_API_KEY", ""),
                elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
                groq_key=os.getenv("GROQ_API_KEY", "")
            )

        downloaded = 0
        rendered = 0
        for i,m in enumerate(vids,1):
            self._wait()
            t=m.get("title","?")[:50]
            self.root.after(0,self._sts,f"{i}/{len(vids)}: {t}",ACCENT)
            self.root.after(0,self._log,f"\n[2/3] Video {i}/{len(vids)}: {t}")
            
            # Download: hook for reward mode, full for legacy
            # If _override_raw is set (direct URL mode), skip the download entirely
            if _override_raw and Path(_override_raw).exists():
                raw = Path(_override_raw)
                self.root.after(0, self._log, f"  Using pre-downloaded file: {raw.name}")
                downloaded += 1
            elif reward_mode:
                h_dur = hook_end - hook_start
                if h_dur <= 0: h_dur = 10
                self.root.after(0,self._log,f"  Downloading hook (from {hook_start}s to {hook_end}s)...")
                raw=scraper.download_hook(m, hook_start=hook_start, hook_end=hook_end)
            else:
                self.root.after(0,self._log,"  Downloading...")
                raw=scraper.download(m)
            if not raw: self.root.after(0,self._log,"  Failed."); continue
            downloaded += 1
            self.root.after(0,self._log,f"  Got: {raw.name}"); self._wait()
            try:
                if cloud_mode:
                    self.root.after(0, self._log, "  Uploading to Cloud Rendering...")
                    import requests as req

                    data = {
                        'game': game, 'url': url,
                        'caption_color': self.caption_color.get(),
                        'caption_pos': str(self.caption_pos.get()),
                        'landing_link_color': self.landing_link_color.get(),
                        'link_font': self.link_font.get(),
                        'overlays': json.dumps(overlays),
                        'layout': json.dumps(layout),
                        'export_quality': export_quality,
                        'elevenlabs_voice_id': os.getenv("ELEVENLABS_VOICE_ID", ""),
                        'elevenlabs_key': os.getenv("ELEVENLABS_API_KEY", ""),
                        'groq_key': os.getenv("GROQ_API_KEY", ""),
                        'mode': 'reward_first' if reward_mode else 'legacy',
                        'custom_script': custom_script,
                        'hook_start': str(hook_start),
                        'hook_end': str(hook_end)
                    }

                    # ── Robust retry loop: 5 attempts with exponential backoff ──
                    from urllib3.util.retry import Retry
                    from requests.adapters import HTTPAdapter

                    max_retries = 5
                    retry_delays = [10, 20, 40, 60]  # seconds between retries
                    resp = None
                    last_error = None

                    # Build a Session with low-level urllib3 retries as safety net
                    session = req.Session()
                    adapter = HTTPAdapter(
                        max_retries=Retry(
                            total=2,
                            backoff_factor=1,
                            status_forcelist=[502, 503, 504],
                            allowed_methods=["POST"],
                        )
                    )
                    session.mount("http://", adapter)
                    session.mount("https://", adapter)

                    for attempt in range(1, max_retries + 1):
                        # Open fresh file handles for each attempt
                        fh_video = open(str(raw), 'rb')
                        fh_ss = open(ss, 'rb') if ss and os.path.exists(ss) else None
                        fh_rec = open(recording_path, 'rb') if reward_mode and os.path.exists(recording_path) else None

                        try:
                            files = {'video': (raw.name, fh_video, 'video/mp4')}
                            if fh_ss:
                                files['screenshot'] = (Path(ss).name, fh_ss, 'image/png')
                            if fh_rec:
                                files['manual_recording'] = (Path(recording_path).name, fh_rec, 'video/mp4')

                            self.root.after(0, self._log, f"  ⬆ Upload attempt {attempt}/{max_retries}...")
                            resp = session.post(
                                f"{cloud_url}/api/cloud_process",
                                data=data,
                                files=files,
                                timeout=(30, 3600),  # 30s connect, 1hr read
                            )
                            last_error = None
                            break  # Success — exit retry loop

                        except (req.exceptions.ConnectionError,
                                req.exceptions.Timeout,
                                req.exceptions.ChunkedEncodingError,
                                ConnectionResetError) as ce:
                            last_error = ce
                            if attempt < max_retries:
                                wait = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                                self.root.after(0, self._log,
                                    f"  ⚠ Attempt {attempt} failed ({type(ce).__name__}). "
                                    f"Retrying in {wait}s... (server may be rebuilding)")
                                time.sleep(wait)
                            else:
                                self.root.after(0, self._log,
                                    f"  ❌ All {max_retries} upload attempts failed. "
                                    f"Check your internet or wait for the HuggingFace Space to finish rebuilding.")
                        finally:
                            fh_video.close()
                            if fh_ss: fh_ss.close()
                            if fh_rec: fh_rec.close()

                    session.close()

                    if last_error:
                        raise last_error

                    if resp and resp.ok:
                        try:
                            payload = resp.json()
                        except Exception:
                            payload = {}

                        video_url = payload.get("video_url_720") if export_quality == "720" else payload.get("video_url_1080")
                        video_url = video_url or payload.get("video_url") or payload.get("video_path")
                        if video_url:
                            if video_url.startswith("/"):
                                video_url = f"{cloud_url}{video_url}"
                            self.root.after(0, self._set_output_url, video_url)
                            self.root.after(0, self._log, f"  ✓ Cloud render complete. Video: {video_url}")
                        else:
                            self.root.after(0, self._log, "  ✓ Cloud Render Started! Check Telegram.")
                        rendered += 1
                    elif resp:
                        self.root.after(0, self._log, f"  ✗ Cloud Error ({resp.status_code}): {resp.text[:300]}")



                else:
                    if reward_mode:
                        self.root.after(0, self._log, "  Rendering Reward-First locally...")
                        out_path = processor.process_reward_first(
                            scraped_video_path=str(raw),
                            manual_recording_path=recording_path,
                            game_name=game,
                            channel_screenshot=ss,
                            landing_url=url,
                            overlay_data=overlays,
                            layout=layout,
                            caption_color=self.caption_color.get(),
                            caption_pos=self.caption_pos.get(),
                            landing_link_color=self.landing_link_color.get(),
                            link_font_name=self.link_font.get(),
                            progress_callback=lambda p, msg: self.root.after(0, self._log, f"  [{p}%] {msg}"),
                            custom_script=custom_script,
                            hook_duration=hook_end - hook_start
                        )
                    else:
                        self.root.after(0, self._log, "  Rendering locally...")
                        out_path = processor.process(
                            input_path=str(raw),
                            game_name=game,
                            channel_screenshot=ss,
                            landing_url=url,
                            progress_callback=lambda p, m: self.root.after(0, self._log, f"  [{p}%] {m}"),
                            overlay_data=overlays,
                            layout=layout,
                            caption_color=self.caption_color.get(),
                            caption_pos=self.caption_pos.get(),
                            landing_link_color=self.landing_link_color.get(),
                            link_font_name=self.link_font.get()
                        )
                    final_path = str(out_path)
                    if export_quality == "720":
                        final_path = self._make_720p_copy(final_path)
                    self.root.after(0, self._set_output_url, final_path)
                    self.root.after(0, self._log, f"  ✓ Local render complete. Video: {final_path}")
                    
                    # 🚀 SEND TO TELEGRAM AFTER LOCAL RENDER
                    self.root.after(0, self._log, f"  📱 Uploading to Telegram...")
                    try:
                        import requests as req
                        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
                        tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
                        
                        if tg_token and tg_chat:
                            with open(final_path, "rb") as f:
                                r = req.post(
                                    f"https://api.telegram.org/bot{tg_token}/sendVideo",
                                    data={"chat_id": tg_chat, "caption": f"✅ Local Render Complete: {game}"},
                                    files={"video": f},
                                    timeout=600,
                                )
                            if r.ok:
                                self.root.after(0, self._log, "  ✅ Sent to Telegram successfully!")
                            else:
                                self.root.after(0, self._log, f"  ❌ Telegram Error: {r.text[:200]}")
                        else:
                            self.root.after(0, self._log, "  ⚠ Telegram not configured in .env (TELEGRAM_BOT_TOKEN or CHAT_ID missing)")
                    except Exception as e:
                        self.root.after(0, self._log, f"  ❌ Telegram Upload Failed: {e}")

                    rendered += 1
            except Exception as e:
                import traceback as _tb
                full = _tb.format_exc()
                self._last_errors.append(str(e))
                self.root.after(0, self._log, f"  ❌ ERROR: {e}")
                self.root.after(0, self._log, f"  (see error popup when finished)")
                log.error(f"Render error:\n{full}")
        # Local rendering now handles Telegram upload directly.
        self._fin(rendered, downloaded)

    def _fin(self, rendered, downloaded=0):
        self.root.after(0, self._prg, 100)
        if rendered:
            status = f"Done! {rendered} video(s) rendered"
            if downloaded and downloaded != rendered:
                status += f" from {downloaded} download(s)"
            status += "."
            self.root.after(0, self._sts, status, GREEN)
        elif downloaded:
            self.root.after(0, self._sts, f"Downloaded {downloaded} video(s), but render failed.", RED)
        else:
            self.root.after(0, self._sts, "No videos downloaded.", RED)

        self.root.after(0, lambda: self.gen_btn.configure(state="normal", bg=GREEN))
        self.root.after(0, lambda: self.pause_btn.configure(state="disabled", text="PAUSE", bg=ORANGE))
        self.root.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        self.root.after(0, lambda: self.editor.set_locked(False))
        self.processing = False

        errors = list(self._last_errors)
        self._last_errors.clear()

        if rendered:
            self.root.after(0, lambda: messagebox.showinfo(
                "✅ Done", f"{rendered} promo(s) rendered!\nClick 'Export to Preview Studio' to watch it."))
        elif errors:
            # Show the actual crash reason so the user knows exactly what to fix
            detail = "\n\n".join(errors[:3])   # show up to 3 errors
            self.root.after(0, lambda: messagebox.showerror(
                "❌ Render Failed — Error Details",
                f"The render failed with this error:\n\n{detail}\n\n"
                "Common fixes:\n"
                "• Local mode: make sure ffmpeg is installed (winget install ffmpeg)\n"
                "• Cloud mode: check that your HuggingFace Space is running\n"
                "• Scroll the log panel to see the full trace"
            ))

    def _sync_render_mode(self, changed):
        if changed == "local" and self.render_local.get():
            self.render_cloud.set(False)
        elif changed == "cloud" and self.render_cloud.get():
            self.render_local.set(False)
        if not self.render_local.get() and not self.render_cloud.get():
            self.render_local.set(True)

    def _toggle_settings(self):
        if self.settings_panel.winfo_ismapped():
            self.settings_panel.pack_forget()
        else:
            self.settings_panel.pack(fill="x", padx=10, pady=(2, 6))

    def _make_720p_copy(self, source_path: str) -> str:
        source = Path(source_path)
        target = source.with_name(f"{source.stem}_720p{source.suffix}")
        try:
            from moviepy.editor import VideoFileClip as VFC
            clip = VFC(str(source))
            try:
                clip.resize(height=720).write_videofile(
                    str(target),
                    codec="libx264",
                    audio_codec="aac",
                    fps=30,
                    preset="fast",
                    threads=4,
                    ffmpeg_params=["-pix_fmt", "yuv420p"],
                    logger=None,
                )
            finally:
                clip.close()
            return str(target)
        except Exception as exc:
            self.root.after(0, self._log, f"  ⚠ 720p conversion failed: {exc}")
            return str(source)

if __name__=="__main__":
    root=tk.Tk(); VideoAutomationApp(root); root.mainloop()
