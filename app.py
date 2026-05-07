"""
app.py — GUI with Visual Preview Editor + Capcut-style 4-corner Resizing

Left panel: form fields
Right panel: Live preview canvas with 4-corner scale/move for all elements
"""

import os, logging, threading, time, math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from video_processor import VideoProcessor
from scraper import VideoScraper
from config import Config

log = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BG, BG_CARD, BG_INPUT = "#1a1a2e", "#16213e", "#0f3460"
FG, FG_DIM, ACCENT = "#e6e6e6", "#8888aa", "#00d4ff"
GREEN, RED, ORANGE = "#00e676", "#ff5252", "#ffa726"

PV_W, PV_H = 270, 480
VID_W, VID_H = 1080, 1920


class CanvasItem:
    """Represents any element on the canvas (screenshot, link, sticker)."""
    def __init__(self, editor, kind, x, y, text="", path=""):
        self.editor = editor
        self.canvas = editor.canvas
        self.kind = kind
        self.x = x
        self.y = y
        self.scale = 1.0
        self.text = text
        self.path = path
        
        self.ids = []
        self.tk_img = None
        self.pil_img = None
        
        if kind == "screenshot" and path:
            self.pil_img = Image.open(path).convert("RGBA")
            
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
            self.tk_img = ImageTk.PhotoImage(resized)
            self.ids.append(self.canvas.create_image(x, y, image=self.tk_img, anchor="center"))
            
        elif self.kind == "link":
            if not self.text: return
            fnt = ("Arial", max(8, int(13 * s)))
            # Dummy text to get bbox
            t_id = self.canvas.create_text(x, y, text=self.text, font=fnt)
            bbox = self.canvas.bbox(t_id)
            self.canvas.delete(t_id)
            if bbox:
                pad = int(4 * s)
                bg_id = self.canvas.create_rectangle(bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad,
                                                     fill="black", stipple="gray50", outline="")
                self.ids.append(bg_id)
            self.ids.append(self.canvas.create_text(x, y, text=self.text, fill="#64dcff", font=fnt))
            
        elif self.kind == "circle":
            r = int(40 * s)
            self.ids.append(self.canvas.create_oval(x-r, y-r, x+r, y+r, outline="red", width=max(1, int(3*s))))
            
        elif self.kind == "arrow":
            r = int(20 * s)
            self.ids.append(self.canvas.create_polygon(x, y-int(25*s), x-r, y+int(12*s), x+r, y+int(12*s),
                                                       outline="red", fill="red", width=max(1, int(2*s))))
            
        elif self.kind == "finger":
            fs = max(8, int(36 * s))
            self.ids.append(self.canvas.create_text(x, y, text="\u261d", fill="red", font=("Segoe UI Emoji", fs)))
            
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


class CanvasEditor:
    """Manages the items on the canvas, selection, moving, and 4-corner scaling."""
    def __init__(self, canvas):
        self.canvas = canvas
        self.items = []
        self.selected = None
        
        self.handles = []
        self.sel_rect = None
        
        self.is_dragging = False
        self.drag_mode = None # "move" or "scale"
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.start_scale = 1.0
        self.start_dist = 1.0
        
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

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
        for i in item.ids: self.canvas.delete(i)
        if item in self.items: self.items.remove(item)
        if self.selected == item: self.select(None)

    def clear_stickers(self):
        stickers = [i for i in self.items if i.kind not in ("screenshot", "link")]
        for s in stickers: self.remove_item(s)

    def select(self, item):
        self.selected = item
        self.draw_selection()

    def draw_selection(self):
        if self.sel_rect: self.canvas.delete(self.sel_rect)
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
            
        # Ensure handles are on top
        self.canvas.tag_raise(self.sel_rect)
        for h in self.handles: self.canvas.tag_raise(h)

    def on_press(self, e):
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
        if not self.selected: return
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
            
        self.draw_selection()

    def on_release(self, e):
        if self.is_dragging and self.selected and self.selected.kind == "screenshot":
            # Force high-quality redraw for image after drag
            self.is_dragging = False
            self.selected.draw()
        self.is_dragging = False
        self.drag_mode = None
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
        stickers = [i for i in self.items if i.kind not in ("screenshot", "link")]
        for s in stickers:
            d = {"kind": s.kind, "cx": s.x/PV_W, "cy": s.y/PV_H, "size": s.scale}
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
        root.geometry("1080x860")
        root.resizable(False, False)
        root.configure(bg=BG)

        self.game_name = tk.StringVar()
        self.screenshot_path = tk.StringVar()
        self.landing_url = tk.StringVar()
        self.max_videos = tk.IntVar(value=3)
        self.processing = False
        self.pause_event = threading.Event()
        self.pause_event.set()

        self.landing_url.trace_add("write", lambda *_: self._update_link())
        self._build_ui()

    def _build_ui(self):
        left = tk.Frame(self.root, bg=BG, width=540)
        left.pack(side="left", fill="y", padx=(20,10), pady=20)
        left.pack_propagate(False)

        tk.Label(left, text="AI VIDEO", font=("Segoe UI", 24, "bold"), fg=ACCENT, bg=BG).pack()
        tk.Label(left, text="Automation Studio", font=("Segoe UI", 12), fg=FG_DIM, bg=BG).pack()
        tk.Frame(left, bg=ACCENT, height=2).pack(fill="x", pady=(8,12))

        self._step(left,"1","Game Name",self.game_name,entry=True)
        self._step_spin(left,"2","Number of Videos",self.max_videos)
        self._step(left,"3","Channel Screenshot",self.screenshot_path, btn="Choose...",cmd=self._pick_ss)
        self._step(left,"4","CPA Landing Page Link",self.landing_url,entry=True)

        bf = tk.Frame(left, bg=BG); bf.pack(pady=(12,6))
        self.gen_btn = tk.Button(bf, text="GENERATE", font=("Segoe UI",14,"bold"),
            fg="#fff", bg=GREEN, relief="flat", padx=25, pady=10, command=self._on_gen)
        self.gen_btn.pack(side="left", padx=(0,8))
        self.pause_btn = tk.Button(bf, text="PAUSE", font=("Segoe UI",12,"bold"),
            fg="#fff", bg=ORANGE, relief="flat", padx=15, pady=10, command=self._on_pause, state="disabled")
        self.pause_btn.pack(side="left")

        self.status_lbl = tk.Label(left, text="Ready", font=("Segoe UI",10), fg=FG_DIM, bg=BG, anchor="w")
        self.status_lbl.pack(fill="x")
        s=ttk.Style(); s.theme_use("clam")
        s.configure("C.Horizontal.TProgressbar", troughcolor=BG_CARD, background=ACCENT, bordercolor=BG, thickness=14)
        self.pbar = ttk.Progressbar(left, style="C.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.pbar.pack(fill="x", pady=(4,6))
        
        self.log_box = tk.Text(left, height=6, font=("Consolas",8), bg=BG_CARD, fg=FG_DIM, relief="flat", wrap="word", state="disabled", highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_INPUT)
        self.log_box.pack(fill="both", expand=True)

        # RIGHT PANEL
        right = tk.Frame(self.root, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(10,20), pady=20)

        tk.Label(right, text="PREVIEW EDITOR", font=("Segoe UI",12,"bold"), fg=ACCENT, bg=BG).pack()
        tk.Label(right, text="Drag elements to move | Drag corners to resize", font=("Segoe UI",9), fg=FG_DIM, bg=BG).pack(pady=(0,6))

        cf = tk.Frame(right, bg="#000", highlightthickness=2, highlightbackground=ACCENT)
        cf.pack()
        self.canvas = tk.Canvas(cf, width=PV_W, height=PV_H, bg="#111", highlightthickness=0)
        self.canvas.pack()
        
        self.editor = CanvasEditor(self.canvas)
        self.canvas.create_text(PV_W//2, PV_H//2, text="Choose a screenshot\nto see preview", fill=FG_DIM, font=("Segoe UI",11), justify="center", tags="ph")

        # Stickers toolbar
        tk.Label(right, text="Add Stickers:", font=("Segoe UI",9,"bold"), fg=FG, bg=BG).pack(pady=(10,2))
        tb1 = tk.Frame(right, bg=BG); tb1.pack(pady=2)
        for txt, kind in [("O Circle", "circle"), ("\u25bc Arrow", "arrow"), ("\u261d Finger", "finger")]:
            tk.Button(tb1, text=txt, font=("Segoe UI",9,"bold"), fg="#fff", bg="#e53935",
                      relief="flat", padx=8, pady=2, command=lambda k=kind: self.editor.add_item(k, PV_W//2, PV_H//2)).pack(side="left", padx=3)

        tb2 = tk.Frame(right, bg=BG); tb2.pack(pady=2)
        for label in ["Click Here!", "Download!", "Subscribe!", "Link Here \u2193", "FREE!"]:
            tk.Button(tb2, text=label, font=("Segoe UI",8,"bold"), fg="#000", bg="#ffeb3b",
                      relief="flat", padx=6, pady=2,
                      command=lambda t=label: self.editor.add_item("text", PV_W//2, PV_H//2, text=t)).pack(side="left", padx=2)

        tk.Button(right, text="Clear All Stickers", font=("Segoe UI",9), fg="#fff", bg=FG_DIM, relief="flat", padx=10, pady=2, command=self.editor.clear_stickers).pack(pady=4)

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
            tk.Label(r,textvariable=v,font=("Segoe UI",9),fg=ORANGE,bg=BG_INPUT, anchor="w",padx=6,pady=3).pack(side="left",fill="x",expand=True)
            if btn: tk.Button(r,text=btn,font=("Segoe UI",9),fg="#fff",bg=ACCENT, relief="flat",padx=8,command=cmd).pack(side="right",padx=(6,0))

    def _step_spin(self, p, n, l, v):
        c=tk.Frame(p,bg=BG_CARD,highlightthickness=1,highlightbackground=BG_INPUT)
        c.pack(fill="x",pady=3)
        i=tk.Frame(c,bg=BG_CARD); i.pack(fill="x",padx=10,pady=6)
        h=tk.Frame(i,bg=BG_CARD); h.pack(fill="x")
        tk.Label(h,text=f" {n} ",font=("Segoe UI",9,"bold"),fg="#fff",bg=ACCENT).pack(side="left",padx=(0,6))
        tk.Label(h,text=l,font=("Segoe UI",10,"bold"),fg=FG,bg=BG_CARD).pack(side="left")
        r=tk.Frame(i,bg=BG_CARD); r.pack(fill="x",pady=(4,0))
        tk.Spinbox(r,from_=1,to=10,textvariable=v,width=4,font=("Segoe UI",12,"bold"), fg=ACCENT,bg=BG_INPUT,relief="flat",justify="center").pack(side="left")

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

    # --- Log ---
    def _log(self, m):
        self.log_box.configure(state="normal"); self.log_box.insert("end",m+"\n")
        self.log_box.see("end"); self.log_box.configure(state="disabled")
    def _sts(self, m, c=FG_DIM): self.status_lbl.configure(text=m, fg=c)
    def _prg(self, v): self.pbar["value"] = v

    def _on_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear(); self.pause_btn.configure(text="RESUME",bg=GREEN)
            self._sts("PAUSED",ORANGE); self._log("--- PAUSED ---")
        else:
            self.pause_event.set(); self.pause_btn.configure(text="PAUSE",bg=ORANGE)
            self._sts("Resuming...",ACCENT); self._log("--- RESUMED ---")

    def _wait(self):
        while not self.pause_event.is_set(): time.sleep(0.3)

    def _on_gen(self):
        g=self.game_name.get().strip(); ss=self.screenshot_path.get().strip()
        u=self.landing_url.get().strip(); c=self.max_videos.get()
        if not g: messagebox.showwarning("Missing","Enter game name."); return
        if not u: messagebox.showwarning("Missing","Enter CPA link."); return
        if self.processing: return
        self.processing=True; self.pause_event.set()
        self.gen_btn.configure(state="disabled",bg=FG_DIM)
        self.pause_btn.configure(state="normal"); self._prg(0)
        
        # Deselect to hide handles in preview (though it doesn't affect render)
        self.editor.select(None)
        
        ov=self.editor.get_overlays()
        layout=self.editor.get_layout_data()
        
        self._log(f"Starting: {g} ({len(ov)} stickers)")
        threading.Thread(target=self._run, args=(g,c,ss,u,ov,layout), daemon=True).start()

    def _run(self, game, mx, ss, url, overlays, layout):
        cfg=Config()
        self.root.after(0,self._sts,"Searching...",ACCENT)
        self.root.after(0,self._log,f"\n[1/3] Searching: '{game} MOD gameplay'...")
        scraper=VideoScraper(config=cfg)
        cands=scraper.search(f"{game} MOD gameplay", max_results=mx*3)
        if not cands:
            self.root.after(0,self._log,"No videos found."); self._fin(0); return
        self.root.after(0,self._log,f"  Found {len(cands)}."); self.root.after(0,self._prg,10)
        vids=cands[:mx]
        proc=VideoProcessor(os.getenv("ELEVENLABS_API_KEY",""),os.getenv("ELEVENLABS_VOICE_ID",""))
        done=[]
        for i,m in enumerate(vids,1):
            self._wait()
            t=m.get("title","?")[:50]
            self.root.after(0,self._sts,f"{i}/{len(vids)}: {t}",ACCENT)
            self.root.after(0,self._log,f"\n[2/3] Video {i}/{len(vids)}: {t}")
            self.root.after(0,self._log,"  Downloading...")
            raw=scraper.download(m)
            if not raw: self.root.after(0,self._log,"  Failed."); continue
            self.root.after(0,self._log,f"  Got: {raw.name}"); self._wait()
            def pg(p,msg,ii=i,tt=len(vids)):
                self.root.after(0,self._prg,min(int(((ii-1)/tt+p/100/tt)*100),95))
                self.root.after(0,self._log,f"  [{p}%] {msg}")
            try:
                o=proc.process(str(raw),game,ss,url,progress_callback=pg, overlay_data=overlays, layout=layout)
                done.append(o); self.root.after(0,self._log,f"  Saved: {o}")
            except Exception as e:
                self.root.after(0,self._log,f"  ERROR: {e}")
        tgt,tgc=os.getenv("TELEGRAM_BOT_TOKEN",""),os.getenv("TELEGRAM_CHAT_ID","")
        if tgt and tgc and done:
            self.root.after(0,self._log,"\n[3/3] Telegram...")
            import requests
            for fp in done:
                try:
                    with open(fp,"rb") as f:
                        requests.post(f"https://api.telegram.org/bot{tgt}/sendVideo", data={"chat_id":tgc,"caption":Path(fp).name}, files={"video":f},timeout=300).raise_for_status()
                    self.root.after(0,self._log,f"  Sent: {Path(fp).name}")
                except Exception as e: self.root.after(0,self._log,f"  Error: {e}")
        self._fin(len(done))

    def _fin(self, c):
        self.root.after(0,self._prg,100)
        self.root.after(0,self._sts,f"Done! {c} video(s)." if c else "No videos.",GREEN if c else RED)
        self.root.after(0,lambda:self.gen_btn.configure(state="normal",bg=GREEN))
        self.root.after(0,lambda:self.pause_btn.configure(state="disabled",text="PAUSE",bg=ORANGE))
        self.processing=False
        if c: self.root.after(0,lambda:messagebox.showinfo("Done",f"{c} promo(s) saved!"))

if __name__=="__main__":
    root=tk.Tk(); VideoAutomationApp(root); root.mainloop()
