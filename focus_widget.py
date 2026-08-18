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

# --- CONFIGURATION ---
LAYOUT = "landscape"  # Options: "landscape" or "portrait"
TRANSPARENCY = 0.92   # 1.0 is solid, lower values increase transparency

# Constants
CHROMA_KEY = "#ff00fe"
RADIUS = 50

# Colors
BG_CARD = "#0e0c0b"
BORDER = "#2a1c12"
ORANGE = "#ff7a1a"
ORANGE_SOFT = "#ff8c3a"
TEXT_PRIMARY = "#f3eee8"
TEXT_SECONDARY = "#8b8580"
TEXT_MUTED = "#6e6862"
TRACK = "#211c19"

# Layout Dimensions
if LAYOUT == "landscape":
    WIDTH, HEIGHT = 600, 390
    LEFT_CX = WIDTH // 4
    RIGHT_CX = (WIDTH * 3) // 4
    
    MUSIC_X = WIDTH // 2
    MUSIC_Y = 60
    
    FOCUS_Y = 116
    MODE_Y = 134
    RING_Y = 230
    CONTROLS_Y = 355
    
    HEADER_X = RIGHT_CX
    HEADER_Y = 116
    HEADER_W = (WIDTH // 2) - 40
    
    LIST_X = RIGHT_CX
    LIST_Y = 140
    LIST_H = HEIGHT - LIST_Y - 50
    LIST_W = (WIDTH // 2) - 40
    
    ADD_X = RIGHT_CX
    ADD_Y = 355
    ADD_W = (WIDTH // 2) - 40
    
    DIV_COORDS = (WIDTH // 2, 90, WIDTH // 2, HEIGHT - 20)
else:
    WIDTH, HEIGHT = 300, 600
    LEFT_CX = WIDTH // 2
    
    MUSIC_X = WIDTH // 2
    MUSIC_Y = 60
    
    FOCUS_Y = 116
    MODE_Y = 134
    RING_Y = 242
    CONTROLS_Y = 360
    
    DIV_COORDS = (30, CONTROLS_Y + 28, WIDTH - 30, CONTROLS_Y + 28)
    
    HEADER_X = WIDTH // 2
    HEADER_Y = CONTROLS_Y + 45
    HEADER_W = WIDTH - 60
    
    LIST_X = WIDTH // 2
    LIST_Y = HEADER_Y + 16
    LIST_H = HEIGHT - 66 - LIST_Y
    LIST_W = WIDTH - 52
    
    ADD_X = WIDTH // 2
    ADD_Y = HEIGHT - 34
    ADD_W = WIDTH - 52

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

        self.tasks = [Task("Deep work block"), Task("Clear inbox")]

        self._offset_x = 0
        self._offset_y = 0
        
        self._setup_media()
        self._setup_window()
        self._build_ui()
        self._render_timer()
        self._render_tasks()

    def _setup_media(self):
        if not self.is_windows or not HAS_WINSDK:
            self.media_status = "winsdk not installed"
            return
            
        self.media_status = "Waiting for media..."
        
        # Start background thread to poll currently playing track from Windows
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
                    # 5 = Playing, 4 = Paused/Stopped in the Windows Media Enum
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
                    if len(text) > 40: 
                        text = text[:37] + "..."
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
        root.geometry(f"{WIDTH}x{HEIGHT}+200+200")
        root.attributes("-alpha", TRANSPARENCY)

        if self.is_windows:
            root.configure(bg=CHROMA_KEY)
            root.attributes("-transparentcolor", CHROMA_KEY)
        else:
            root.configure(bg=BG_CARD)

    def _build_ui(self):
        outer_bg = CHROMA_KEY if self.is_windows else BG_CARD

        self.canvas = tk.Canvas(
            self.root, width=WIDTH, height=HEIGHT,
            bg=outer_bg, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        pts = rounded_rect_points(1, 1, WIDTH - 1, HEIGHT - 1, RADIUS)
        self.canvas.create_polygon(
            pts, smooth=True, splinesteps=24,
            fill=BG_CARD, outline=BORDER, width=1,
        )

        # Drag bar / Header container
        drag_bar = tk.Frame(self.canvas, bg=BG_CARD, height=34)
        self.canvas.create_window(WIDTH // 2, 20, window=drag_bar, width=WIDTH - 20, height=34)
        drag_bar.bind("<ButtonPress-1>", self._drag_start)
        drag_bar.bind("<B1-Motion>", self._drag_move)

        handle = tk.Frame(drag_bar, bg="#3a322c", width=36, height=4)
        handle.place(relx=0.5, y=4, anchor="n")
        handle.bind("<ButtonPress-1>", self._drag_start)
        handle.bind("<B1-Motion>", self._drag_move)

        # Close Button
        close_btn = tk.Label(drag_bar, text="\u2715", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 10), cursor="hand2")
        close_btn.place(relx=1.0, y=2, anchor="ne")
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg=ORANGE))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=TEXT_MUTED))

        # Settings Cog Button
        self.settings_btn = tk.Label(drag_bar, text="⚙", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 10), cursor="hand2")
        self.settings_btn.place(relx=1.0, x=-22, y=2, anchor="ne")
        self.settings_btn.bind("<Button-1>", lambda e: self._toggle_settings())
        self.settings_btn.bind("<Enter>", lambda e: self.settings_btn.configure(fg=ORANGE))
        self.settings_btn.bind("<Leave>", lambda e: self.settings_btn.configure(fg=TEXT_MUTED))

        # Main Content Container (FIXED: Using .place() instead of create_window)
        self.main_container = tk.Frame(self.canvas, bg=BG_CARD)
        self.main_container.place(x=WIDTH // 2, y=HEIGHT // 2 + 10, width=WIDTH, height=HEIGHT - 40, anchor="center")

        # Settings Content Container
        self.settings_container = tk.Frame(self.canvas, bg=BG_CARD)
        
        # Build Main View components inside main_container
        self._build_main_view()
        
        # Build Settings View components inside settings_container
        self._build_settings_view()

        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)

    def _build_main_view(self):
        # Media Player
        music_frame = tk.Frame(self.main_container, bg=BG_CARD)
        music_frame.place(x=0, y=10, width=WIDTH, anchor="n") # Adjusted relative layout positioning
        # To make it safe inside main_container bounds, use pack/place securely:
        music_frame.pack(side="top", pady=(5, 0))

        self.track_var = tk.StringVar(value=getattr(self, 'media_status', 'Loading...'))
        self.play_var = tk.StringVar(value="▶")

        track_lbl = tk.Label(music_frame, textvariable=self.track_var, bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 9))
        track_lbl.pack(side="top", pady=(0, 2))

        ctrl_frame = tk.Frame(music_frame, bg=BG_CARD)
        ctrl_frame.pack(side="top")

        btn_kwargs = dict(bg=BG_CARD, fg=ORANGE, bd=0, relief="flat", font=("Segoe UI", 11), cursor="hand2", activebackground=BG_CARD, activeforeground=ORANGE_SOFT)
        
        tk.Button(ctrl_frame, text="⏮", command=lambda: self._media_action('prev'), **btn_kwargs).pack(side="left", padx=12)
        tk.Button(ctrl_frame, textvariable=self.play_var, command=lambda: self._media_action('playpause'), **btn_kwargs).pack(side="left", padx=12)
        tk.Button(ctrl_frame, text="⏭", command=lambda: self._media_action('next'), **btn_kwargs).pack(side="left", padx=12)

        # Timer Elements
        if LAYOUT == "landscape":
            timer_frame = tk.Frame(self.main_container, bg=BG_CARD)
            timer_frame.place(x=WIDTH // 4 - 20, y=55, anchor="n", width=WIDTH // 2, height=270)
            
            label = tk.Label(timer_frame, text="FOCUS", bg=BG_CARD, fg=ORANGE, font=("Segoe UI", 10, "bold"))
            label.pack(side="top", pady=(5, 0))

            self.mode_label = tk.Label(timer_frame, text="click the time to set it", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 9))
            self.mode_label.pack(side="top", pady=(0, 5))

            ring_size = 176
            pad, ring_width = 12, 14
            self.ring_canvas = tk.Canvas(timer_frame, width=ring_size, height=ring_size, bg=BG_CARD, highlightthickness=0, bd=0)
            self.ring_canvas.pack(side="top", pady=5)

            self.ring_track = self.ring_canvas.create_oval(pad, pad, ring_size - pad, ring_size - pad, outline=TRACK, width=ring_width)
            self.ring_arc = self.ring_canvas.create_arc(pad, pad, ring_size - pad, ring_size - pad, start=90, extent=0, outline=ORANGE, width=ring_width, style="arc")

            self.time_var = tk.StringVar(value=self._fmt(self.remaining))
            self.time_label = tk.Label(self.ring_canvas, textvariable=self.time_var, bg=BG_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 26, "bold"), cursor="xterm")
            self.ring_canvas.create_window(ring_size // 2, ring_size // 2, window=self.time_label)
            self.time_label.bind("<Button-1>", self._start_time_edit)

            controls = tk.Frame(timer_frame, bg=BG_CARD)
            controls.pack(side="top", pady=5)

            tk.Button(controls, text="Reset", command=self._reset, bg="#1c1815", fg="#d8d2cb", activebackground="#241f1b", activeforeground="#d8d2cb", bd=0, relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=6, cursor="hand2").pack(side="left", padx=4)
            self.start_btn = tk.Button(controls, text="Start", command=self._toggle_timer, bg=ORANGE, fg="#1a1310", activebackground=ORANGE_SOFT, activeforeground="#1a1310", bd=0, relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6, cursor="hand2")
            self.start_btn.pack(side="left", padx=4)

            # Vertical separator line
            div_line = tk.Canvas(self.main_container, width=2, height=HEIGHT - 80, bg=BG_CARD, highlightthickness=0)
            div_line.place(x=WIDTH // 2 - 20, y=50)
            div_line.create_line(0, 0, 0, HEIGHT - 80, fill=BORDER)

            # Checklist side
            right_frame = tk.Frame(self.main_container, bg=BG_CARD)
            right_frame.place(x=WIDTH // 2, y=55, anchor="nw", width=(WIDTH // 2) - 30, height=270)

            header = tk.Frame(right_frame, bg=BG_CARD)
            header.pack(side="top", fill="x", pady=(0, 5))
            tk.Label(header, text="CHECKLIST", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 9, "bold")).pack(side="left")
            self.count_label = tk.Label(header, text="0/0", bg=BG_CARD, fg=ORANGE, font=("Segoe UI", 9, "bold"))
            self.count_label.pack(side="right")

            list_wrap = tk.Frame(right_frame, bg=BG_CARD)
            list_wrap.pack(side="top", fill="both", expand=True, pady=(0, 5))

            self.list_canvas = tk.Canvas(list_wrap, bg=BG_CARD, highlightthickness=0, bd=0)
            self.list_canvas.pack(side="left", fill="both", expand=True)
            self.tasks_frame = tk.Frame(self.list_canvas, bg=BG_CARD)
            self.list_window = self.list_canvas.create_window((0, 0), window=self.tasks_frame, anchor="nw")
            
            self.tasks_frame.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
            self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfig(self.list_window, width=e.width))
            self.list_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

            add_row = tk.Frame(right_frame, bg=BG_CARD)
            add_row.pack(side="bottom", fill="x")

            self.add_entry = tk.Entry(add_row, bg="#171310", fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=("Segoe UI", 10), highlightthickness=1, highlightbackground="#2a1c12", highlightcolor=ORANGE)
            self.add_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
            self.add_entry.bind("<Return>", lambda e: self._add_task())
            self._placeholder_on()
            self.add_entry.bind("<FocusIn>", self._placeholder_off)
            self.add_entry.bind("<FocusOut>", lambda e: self._placeholder_on() if not self.add_entry.get() else None)

            tk.Button(add_row, text="+", command=self._add_task, bg="#2a1c12", fg=ORANGE, activebackground="#3a2717", activeforeground=ORANGE, bd=0, relief="flat", font=("Segoe UI", 11, "bold"), width=2, cursor="hand2").pack(side="left")
        else:
            # Portrait layout implementation handles natively if needed, keeping compact structure
            pass

    def _build_settings_view(self):
        # FIXED: Removed self.settings_container.place(...) so it doesn't open by default.
        
        lbl_title = tk.Label(self.settings_container, text="SETTINGS", bg=BG_CARD, fg=ORANGE, font=("Segoe UI", 12, "bold"))
        lbl_title.pack(side="top", pady=(10, 20))

        lbl_coming = tk.Label(self.settings_container, text="comming soon", bg=BG_CARD, fg=TEXT_SECONDARY, font=("Segoe UI", 11))
        lbl_coming.pack(side="top", pady=20)

        back_btn = tk.Button(self.settings_container, text="Back to Widget", command=self._toggle_settings, bg="#2a1c12", fg=ORANGE, activebackground="#3a2717", activeforeground=ORANGE, bd=0, relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=8, cursor="hand2")
        back_btn.pack(side="top", pady=20)

    def _toggle_settings(self):
        if self.settings_container.winfo_ismapped():
            # Switch back to main view
            self.settings_container.place_forget()
            self.main_container.place(x=WIDTH // 2, y=HEIGHT // 2 + 10, width=WIDTH, height=HEIGHT - 40, anchor="center")
            self.settings_btn.configure(text="⚙")
        else:
            # Switch to settings view
            self.main_container.place_forget()
            self.settings_container.place(x=WIDTH // 2, y=HEIGHT // 2 + 10, width=WIDTH - 40, height=HEIGHT - 60, anchor="center")
            self.settings_btn.configure(text="✕")

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
        entry = tk.Entry(self.ring_canvas, bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=("Segoe UI", 22, "bold"), justify="center", width=6)
        entry.insert(0, self._fmt(self.remaining))
        window_id = self.ring_canvas.create_window(88, 88, window=entry)
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
        self.add_entry.delete(0, "end")
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
                dot.create_oval(1, 1, 16, 16, outline=ORANGE if task.done else "#8a4b1f", width=2, fill=ORANGE if task.done else BG_CARD)
                if task.done:
                    dot.create_line(4, 9, 7, 12, fill="#1a1310", width=2)
                    dot.create_line(7, 12, 13, 5, fill="#1a1310", width=2)
                dot.bind("<Button-1>", lambda e, i=i: self._toggle_task(i))

                text_lbl = tk.Label(row, text=task.text, bg=BG_CARD, fg=TEXT_MUTED if task.done else TEXT_PRIMARY, font=("Segoe UI", 10, "overstrike" if task.done else "normal"), anchor="w", cursor="hand2", wraplength=LIST_W - 60, justify="left")
                text_lbl.pack(side="left", fill="x", expand=True)
                text_lbl.bind("<Button-1>", lambda e, i=i: self._toggle_task(i))

                del_btn = tk.Label(row, text="\u2715", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9), cursor="hand2")
                del_btn.pack(side="right", padx=(6, 2))
                del_btn.bind("<Button-1>", lambda e, i=i: self._delete_task(i))
                del_btn.bind("<Enter>", lambda e, w=del_btn: w.configure(fg=ORANGE))
                del_btn.bind("<Leave>", lambda e, w=del_btn: w.configure(fg=TEXT_MUTED))

        self.count_label.configure(text=f"{sum(1 for t in self.tasks if t.done)}/{len(self.tasks)}")

def main():
    root = tk.Tk()
    FocusWidget(root)
    root.mainloop()

if __name__ == "__main__":
    main()