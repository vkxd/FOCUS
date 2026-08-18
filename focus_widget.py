import sys
import time
import math
import threading
import asyncio
import tkinter as tk
from tkinter import font as tkfont

try:
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False

# --- CONFIGURATION & CONSTANTS ---
TRANSPARENCY = 0.92
CHROMA_KEY = "#ff00fe"
RADIUS = 40

BG_CARD = "#0e0c0b"
BORDER = "#2a1c12"
TEXT_PRIMARY = "#f3eee8"
TEXT_SECONDARY = "#8b8580"
TEXT_MUTED = "#6e6862"
TRACK = "#211c19"

def rounded_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]

class Task:
    __slots__ = ("text", "done")
    def __init__(self, text, done=False):
        self.text = text
        self.done = done

class FocusWidget:
    def __init__(self, root):
        self.root = root
        self.is_windows = sys.platform.startswith("win")

        self.total_seconds = 25 * 60
        self.remaining = self.total_seconds
        self.running = False
        self.after_id = None
        self.editing_time = False

        # Accent Color Configuration
        self.highlight_color = "#ff7a1a"
        
        # Explicitly tie StringVar to root so Radiobuttons track it properly
        self.taskbar_position = tk.StringVar(self.root, value="Top")

        self.tasks = [Task("Deep work block"), Task("Clear inbox")]

        self._offset_x = 0
        self._offset_y = 0
        
        self._setup_media()
        self._setup_window()
        self._build_ui()
        
        self.settings_visible = False
        self._apply_layout_change()
        self._render_timer()
        self._render_tasks()

    def _setup_media(self):
        if not self.is_windows or not HAS_WINSDK:
            self.media_status = "Media player ready"
            return
            
        self.media_status = "Waiting for media..."
        t = threading.Thread(target=self._poll_media_loop, daemon=True)
        t.start()

    def _poll_media_loop(self):
        async def fetch_media():
            try:
                manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                session = manager.get_current_session()
                if session:
                    info = await session.try_get_media_properties_async()
                    pb_info = session.get_playback_info()
                    is_playing = (int(pb_info.playback_status) == 5)
                    return info.title, info.artist, is_playing
            except Exception:
                pass
            return None, None, False

        while True:
            try:
                title, artist, is_playing = asyncio.run(fetch_media())
                if title:
                    text = f"{title} - {artist}" if artist else title
                    if len(text) > 35: 
                        text = text[:32] + "..."
                    self.root.after(0, lambda t=text, p=is_playing: self._update_media_ui(t, p))
                else:
                    self.root.after(0, lambda: self._update_media_ui("No active playback", False))
            except Exception:
                pass
            time.sleep(2)

    def _update_media_ui(self, text, is_playing):
        self.track_var.set(text)
        self.play_var.set("⏸" if is_playing else "▶")

    def _media_action(self, action):
        if not HAS_WINSDK: return
        
        async def do_action():
            try:
                manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                session = manager.get_current_session()
                if session:
                    if action == 'playpause':
                        pb_info = session.get_playback_info()
                        if int(pb_info.playback_status) == 5:
                            await session.try_pause_async()
                        else:
                            await session.try_play_async()
                    elif action == 'next':
                        await session.try_skip_next_async()
                    elif action == 'prev':
                        await session.try_skip_previous_async()
            except Exception as e:
                print("Media control error:", e)
                
        threading.Thread(target=lambda: asyncio.run(do_action()), daemon=True).start()

    def _setup_window(self):
        root = self.root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("600x390+200+200")
        root.minsize(400, 300)
        root.attributes("-alpha", TRANSPARENCY)

        if self.is_windows:
            root.configure(bg=CHROMA_KEY)
            root.attributes("-transparentcolor", CHROMA_KEY)
        else:
            root.configure(bg=BG_CARD)

    def _build_ui(self):
        outer_bg = CHROMA_KEY if self.is_windows else BG_CARD

        self.canvas = tk.Canvas(
            self.root, bg=outer_bg, highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.bg_polygon = self.canvas.create_polygon(0, 0, 0, 0, fill=BG_CARD, outline=BORDER, width=1)

        # Drag bar / Window Controls
        self.drag_bar = tk.Frame(self.canvas, bg=BG_CARD, height=30)
        self.drag_bar_window = self.canvas.create_window(0, 0, window=self.drag_bar, anchor="nw")
        
        self.drag_bar.bind("<ButtonPress-1>", self._drag_start)
        self.drag_bar.bind("<B1-Motion>", self._drag_move)

        handle = tk.Frame(self.drag_bar, bg="#3a322c", width=36, height=4)
        handle.place(relx=0.5, y=6, anchor="n")
        handle.bind("<ButtonPress-1>", self._drag_start)
        handle.bind("<B1-Motion>", self._drag_move)

        self.close_btn = tk.Label(self.drag_bar, text="\u2715", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 10), cursor="hand2")
        self.close_btn.place(relx=1.0, x=-12, y=2, anchor="ne")
        self.close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        self.settings_btn = tk.Label(self.drag_bar, text="⚙", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 11), cursor="hand2")
        self.settings_btn.place(relx=1.0, x=-34, y=1, anchor="ne")
        self.settings_btn.bind("<Button-1>", lambda e: self._toggle_settings())

        # Main Content Container Frame
        self.content_frame = tk.Frame(self.canvas, bg=BG_CARD)
        self.content_window = self.canvas.create_window(0, 0, window=self.content_frame, anchor="nw")

        # Media Taskbar Frame
        self.media_frame = tk.Frame(self.content_frame, bg=BG_CARD)
        self.track_var = tk.StringVar(value=getattr(self, 'media_status', 'Loading...'))
        self.play_var = tk.StringVar(value="▶")

        track_lbl = tk.Label(self.media_frame, textvariable=self.track_var, bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 9))
        track_lbl.pack(side="top", pady=(0, 2))

        ctrl_frame = tk.Frame(self.media_frame, bg=BG_CARD)
        ctrl_frame.pack(side="top")

        btn_kwargs = dict(bg=BG_CARD, fg=self.highlight_color, bd=0, relief="flat", font=("Segoe UI", 11), cursor="hand2", activebackground=BG_CARD)
        self.btn_prev = tk.Button(ctrl_frame, text="⏮", command=lambda: self._media_action('prev'), **btn_kwargs)
        self.btn_prev.pack(side="left", padx=8)
        self.btn_play = tk.Button(ctrl_frame, textvariable=self.play_var, command=lambda: self._media_action('playpause'), **btn_kwargs)
        self.btn_play.pack(side="left", padx=8)
        self.btn_next = tk.Button(ctrl_frame, text="⏭", command=lambda: self._media_action('next'), **btn_kwargs)
        self.btn_next.pack(side="left", padx=8)

        # Workspace Container (Timer + Tasks)
        self.workspace = tk.Frame(self.content_frame, bg=BG_CARD)
        self.workspace.columnconfigure(0, weight=1)
        self.workspace.columnconfigure(1, weight=1)
        self.workspace.rowconfigure(0, weight=1)

        # Timer View Component
        self.timer_frame = tk.Frame(self.workspace, bg=BG_CARD)
        self.timer_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        self.lbl_focus = tk.Label(self.timer_frame, text="FOCUS", bg=BG_CARD, fg=self.highlight_color, font=("Segoe UI", 10, "bold"))
        self.lbl_focus.pack(side="top", pady=(0, 0))

        self.mode_label = tk.Label(self.timer_frame, text="click the time to set it", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 9))
        self.mode_label.pack(side="top", pady=(0, 2))

        ring_size = 150
        pad, ring_width = 10, 12
        self.ring_canvas = tk.Canvas(self.timer_frame, width=ring_size, height=ring_size, bg=BG_CARD, highlightthickness=0, bd=0)
        self.ring_canvas.pack(side="top", pady=5)

        self.ring_track = self.ring_canvas.create_oval(pad, pad, ring_size - pad, ring_size - pad, outline=TRACK, width=ring_width)
        self.ring_arc = self.ring_canvas.create_arc(pad, pad, ring_size - pad, ring_size - pad, start=90, extent=0, outline=self.highlight_color, width=ring_width, style="arc")

        self.time_var = tk.StringVar(value=self._fmt(self.remaining))
        self.time_label = tk.Label(self.ring_canvas, textvariable=self.time_var, bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 22, "bold"), cursor="xterm")
        self.ring_canvas.create_window(ring_size // 2, ring_size // 2, window=self.time_label)
        self.time_label.bind("<Button-1>", self._start_time_edit)

        controls = tk.Frame(self.timer_frame, bg=BG_CARD)
        controls.pack(side="top", pady=5)

        tk.Button(controls, text="Reset", command=self._reset, bg="#1c1815", fg="#d8d2cb", activebackground="#241f1b", activeforeground="#d8d2cb", bd=0, relief="flat", font=("Segoe UI", 9, "bold"), padx=10, pady=4, cursor="hand2").pack(side="left", padx=4)
        self.start_btn = tk.Button(controls, text="Start", command=self._toggle_timer, bg=self.highlight_color, fg="#1a1310", bd=0, relief="flat", font=("Segoe UI", 9, "bold"), padx=14, pady=4, cursor="hand2")
        self.start_btn.pack(side="left", padx=4)

        # Checklist View Component
        self.right_frame = tk.Frame(self.workspace, bg=BG_CARD)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)

        header = tk.Frame(self.right_frame, bg=BG_CARD)
        header.pack(side="top", fill="x", pady=(0, 5))
        tk.Label(header, text="CHECKLIST", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.count_label = tk.Label(header, text="0/0", bg=BG_CARD, fg=self.highlight_color, font=("Segoe UI", 9, "bold"))
        self.count_label.pack(side="right")

        list_wrap = tk.Frame(self.right_frame, bg=BG_CARD)
        list_wrap.pack(side="top", fill="both", expand=True, pady=(0, 5))

        self.list_canvas = tk.Canvas(list_wrap, bg=BG_CARD, highlightthickness=0, bd=0)
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.tasks_frame = tk.Frame(self.list_canvas, bg=BG_CARD)
        self.list_window = self.list_canvas.create_window((0, 0), window=self.tasks_frame, anchor="nw")
        
        self.tasks_frame.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfig(self.list_window, width=e.width))
        self.list_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        add_row = tk.Frame(self.right_frame, bg=BG_CARD)
        add_row.pack(side="bottom", fill="x")

        self.add_entry = tk.Entry(add_row, bg="#171310", fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=("Segoe UI", 9), highlightthickness=1, highlightbackground="#2a1c12", highlightcolor=self.highlight_color)
        self.add_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        self.add_entry.bind("<Return>", lambda e: self._add_task())
        self._placeholder_on()
        self.add_entry.bind("<FocusIn>", self._placeholder_off)
        self.add_entry.bind("<FocusOut>", lambda e: self._placeholder_on() if not self.add_entry.get().strip() else None)

        self.add_btn = tk.Button(add_row, text="+", command=self._add_task, bg="#2a1c12", fg=self.highlight_color, activebackground="#3a2717", activeforeground=self.highlight_color, bd=0, relief="flat", font=("Segoe UI", 10, "bold"), width=3, cursor="hand2")
        self.add_btn.pack(side="left")

        # Settings Container Component
        self.settings_frame = tk.Frame(self.canvas, bg=BG_CARD)
        self._build_settings_view()

        self.root.bind("<Configure>", self._on_resize)

    def _build_settings_view(self):
        lbl_title = tk.Label(self.settings_frame, text="SETTINGS", bg=BG_CARD, fg=self.highlight_color, font=("Segoe UI", 11, "bold"))
        lbl_title.pack(side="top", pady=(5, 10))

        # 1. Color Customization Section
        color_section = tk.LabelFrame(self.settings_frame, text=" Accent Highlight Color ", bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 9), bd=1, relief="solid")
        color_section.pack(fill="x", padx=15, pady=5)

        color_row = tk.Frame(color_section, bg=BG_CARD)
        color_row.pack(fill="x", padx=10, pady=8)

        tk.Label(color_row, text="Hex Code:", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 9)).pack(side="left", padx=(0, 5))
        
        self.color_entry = tk.Entry(color_row, bg="#171310", fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", width=10, font=("Segoe UI", 9))
        self.color_entry.insert(0, self.highlight_color)
        self.color_entry.pack(side="left", padx=5)

        btn_apply_color = tk.Button(color_row, text="Apply", command=self._apply_custom_color, bg="#2a1c12", fg=TEXT_PRIMARY, bd=0, font=("Segoe UI", 8, "bold"), cursor="hand2")
        btn_apply_color.pack(side="left", padx=5)

        # 2. Layout Position Section
        layout_section = tk.LabelFrame(self.settings_frame, text=" Media Taskbar Position ", bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 9), bd=1, relief="solid")
        layout_section.pack(fill="x", padx=15, pady=10)

        options = [("Top", "Top"), ("Bottom", "Bottom"), ("Left", "Left"), ("Right", "Right"), ("Hide", "Hidden")]
        opts_frame = tk.Frame(layout_section, bg=BG_CARD)
        opts_frame.pack(fill="x", padx=10, pady=5)

        for text, val in options:
            rb = tk.Radiobutton(opts_frame, text=text, value=val, variable=self.taskbar_position, command=self._apply_layout_change, bg=BG_CARD, fg=TEXT_PRIMARY, selectcolor=BG_CARD, activebackground=BG_CARD, activeforeground=TEXT_PRIMARY, font=("Segoe UI", 9))
            rb.pack(side="left", expand=True)

        back_btn = tk.Button(self.settings_frame, text="Done", command=self._toggle_settings, bg="#2a1c12", fg=self.highlight_color, bd=0, font=("Segoe UI", 9, "bold"), padx=16, pady=4, cursor="hand2")
        back_btn.pack(side="bottom", pady=10)

    def _apply_custom_color(self):
        new_color = self.color_entry.get().strip()
        if new_color and (new_color.startswith("#") and len(new_color) in (4, 7)):
            self.highlight_color = new_color
            
            self.lbl_focus.configure(fg=self.highlight_color)
            self.count_label.configure(fg=self.highlight_color)
            self.start_btn.configure(bg=self.highlight_color)
            self.add_entry.configure(highlightcolor=self.highlight_color)
            self.add_btn.configure(fg=self.highlight_color, activeforeground=self.highlight_color)
            self.btn_prev.configure(fg=self.highlight_color)
            self.btn_play.configure(fg=self.highlight_color)
            self.btn_next.configure(fg=self.highlight_color)
            self.ring_canvas.itemconfig(self.ring_arc, outline=self.highlight_color)
            self._render_tasks()

    def _apply_layout_change(self):
        pos = self.taskbar_position.get()
        self.media_frame.pack_forget()
        self.workspace.pack_forget()

        if pos == "Top":
            self.media_frame.pack(side="top", fill="x", pady=(0, 5))
            self.workspace.pack(side="top", fill="both", expand=True)
        elif pos == "Bottom":
            self.media_frame.pack(side="bottom", fill="x", pady=(5, 0))
            self.workspace.pack(side="top", fill="both", expand=True)
        elif pos == "Left":
            self.media_frame.pack(side="left", fill="y", padx=(0, 10))
            self.workspace.pack(side="left", fill="both", expand=True)
        elif pos == "Right":
            self.media_frame.pack(side="right", fill="y", padx=(10, 0))
            self.workspace.pack(side="left", fill="both", expand=True)
        elif pos == "Hidden":
            self.workspace.pack(side="top", fill="both", expand=True)

    def _on_resize(self, event):
        if event.widget != self.root:
            return

        w, h = event.width, event.height
        pts = rounded_rect_points(1, 1, w - 1, h - 1, RADIUS)
        self.canvas.coords(self.bg_polygon, *pts)

        self.canvas.coords(self.drag_bar_window, 10, 10)
        self.canvas.itemconfig(self.drag_bar_window, width=w - 20, height=30)

        if self.settings_visible:
            self.canvas.coords(self.content_window, 10, 45)
            self.canvas.itemconfig(self.content_window, width=w - 20, height=h - 55)
            self.settings_frame.place(x=10, y=45, width=w - 20, height=h - 55)
        else:
            self.settings_frame.place_forget()
            self.canvas.coords(self.content_window, 10, 45)
            self.canvas.itemconfig(self.content_window, width=w - 20, height=h - 55)

    def _toggle_settings(self):
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.canvas.itemconfig(self.content_window, state="hidden")
            self.settings_frame.place(x=10, y=45, width=self.root.winfo_width() - 20, height=self.root.winfo_height() - 55)
            self.settings_btn.configure(text="✕")
        else:
            self.settings_frame.place_forget()
            self.canvas.itemconfig(self.content_window, state="normal")
            self.settings_btn.configure(text="⚙")

    def _placeholder_on(self):
        self.add_entry.delete(0, "end")
        self.add_entry.insert(0, "Add a task")
        self.add_entry.configure(fg=TEXT_MUTED)
        self._placeholder_active = True

    def _placeholder_off(self, event=None):
        if getattr(self, "_placeholder_active", False):
            self.add_entry.delete(0, "end")
            self.add_entry.configure(fg=TEXT_PRIMARY)
            self._placeholder_active = False

    def _on_mousewheel(self, event):
        self.list_canvas.yview_scroll(int(-event.delta / 40), "units")

    def _drag_start(self, event):
        self._offset_x = event.x_root - self.root.winfo_x()
        self._offset_y = event.y_root - self.root.winfo_y()

    def _drag_move(self, event):
        self.root.geometry(f"+{event.x_root - self._offset_x}+{event.y_root - self._offset_y}")

    def _fmt(self, seconds):
        m, s = divmod(max(0, int(seconds)), 60)
        return f"{m:02d}:{s:02d}"

    def _render_timer(self):
        self.time_var.set(self._fmt(self.remaining))
        self.ring_canvas.itemconfig(self.ring_arc, extent=-360 * (self.remaining / self.total_seconds) if self.total_seconds else 0)

    def _tick(self):
        if self.remaining <= 0:
            self.running = False
            self.start_btn.configure(text="Start")
            self.mode_label.configure(text="time's up")
            self.after_id = None
            return
        self.remaining -= 1
        self._render_timer()
        self.after_id = self.root.after(1000, self._tick)

    def _toggle_timer(self):
        if self.running:
            self.running = False
            self.start_btn.configure(text="Start")
            self.mode_label.configure(text="paused")
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
        else:
            if self.remaining <= 0: self.remaining = self.total_seconds
            self.running = True
            self.start_btn.configure(text="Pause")
            self.mode_label.configure(text="in progress")
            self.after_id = self.root.after(1000, self._tick)

    def _reset(self):
        self.running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.remaining = self.total_seconds
        self.start_btn.configure(text="Start")
        self.mode_label.configure(text="click the time to set it")
        self._render_timer()

    def _start_time_edit(self, event):
        if self.running or self.editing_time: return
        self.editing_time = True
        entry = tk.Entry(self.ring_canvas, bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=("Segoe UI", 18, "bold"), justify="center", width=6)
        entry.insert(0, self._fmt(self.remaining))
        window_id = self.ring_canvas.create_window(75, 75, window=entry)
        entry.focus_set()
        entry.select_range(0, "end")

        def commit(evt=None):
            raw = entry.get().strip()
            secs = self.total_seconds
            if ":" in raw:
                parts = raw.split(":")
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    secs = max(0, min(359999, int(parts[0]) * 60 + int(parts[1])))
            elif raw.isdigit():
                secs = max(0, min(359999, int(raw) * 60))
            self.total_seconds = self.remaining = secs
            self.ring_canvas.delete(window_id)
            self.editing_time = False
            self._render_timer()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)

    def _add_task(self):
        text = self.add_entry.get().strip()
        if not text or getattr(self, "_placeholder_active", False): return
        self.tasks.append(Task(text))
        self._placeholder_on()
        self._render_tasks()

    def _toggle_task(self, index):
        self.tasks[index].done = not self.tasks[index].done
        self._render_tasks()

    def _delete_task(self, index):
        del self.tasks[index]
        self._render_tasks()

    def _render_tasks(self):
        for child in self.tasks_frame.winfo_children():
            child.destroy()

        if not self.tasks:
            tk.Label(self.tasks_frame, text="no tasks yet", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(pady=10)
        else:
            for i, task in enumerate(self.tasks):
                row = tk.Frame(self.tasks_frame, bg=BG_CARD)
                row.pack(fill="x", pady=3)

                dot = tk.Canvas(row, width=17, height=17, bg=BG_CARD, highlightthickness=0, bd=0, cursor="hand2")
                dot.pack(side="left", padx=(2, 8))
                dot.create_oval(1, 1, 16, 16, outline=self.highlight_color if task.done else "#8a4b1f", width=2, fill=self.highlight_color if task.done else BG_CARD)
                if task.done:
                    dot.create_line(4, 9, 7, 12, fill="#1a1310", width=2)
                    dot.create_line(7, 12, 13, 5, fill="#1a1310", width=2)
                dot.bind("<Button-1>", lambda e, i=i: self._toggle_task(i))

                text_lbl = tk.Label(row, text=task.text, bg=BG_CARD, fg=TEXT_MUTED if task.done else TEXT_PRIMARY, font=("Segoe UI", 9, "overstrike" if task.done else "normal"), anchor="w", cursor="hand2", justify="left")
                text_lbl.pack(side="left", fill="x", expand=True)
                text_lbl.bind("<Button-1>", lambda e, i=i: self._toggle_task(i))

                del_btn = tk.Label(row, text="\u2715", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9), cursor="hand2")
                del_btn.pack(side="right", padx=(6, 2))
                del_btn.bind("<Button-1>", lambda e, i=i: self._delete_task(i))

        self.count_label.configure(text=f"{sum(1 for t in self.tasks if t.done)}/{len(self.tasks)}")

def main():
    root = tk.Tk()
    FocusWidget(root)
    root.mainloop()

if __name__ == "__main__":
    main()