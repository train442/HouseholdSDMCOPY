"""
Shared Tkinter look-and-feel and reusable widget helpers for HouseholdSim's GUIs
(DataImportWizard.py, ResultsGUI.py, InputBuilderWizard.py).

Originally written inline in DataImportWizard.py; pulled out here once a second and third GUI
wanted the same styled ttk theme and card/scrollable-frame/file-picker/log-box patterns, so all
three share one canonical look instead of drifting apart.
"""
import os
import queue
import threading
import traceback
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, scrolledtext

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import pandastable as pdt

# ----------------------------- Look & Feel -----------------------------

FONT_FAMILY = 'Segoe UI'
PALETTE = {
    'bg': '#f2f4f7',
    'surface': '#ffffff',
    'primary': '#1f4e79',
    'primary_active': '#2c6aa3',
    'text': '#1a1f26',
    'muted': '#5b6672',
    'border': '#d7dce2',
    'log_bg': '#0f172a',
    'log_fg': '#d7dee7',
    'warn': '#9a4b12',
}


def configure_style(root: Tk):
    root.configure(bg=PALETTE['bg'])
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass

    style.configure('.', font=(FONT_FAMILY, 10), background=PALETTE['bg'], foreground=PALETTE['text'])
    style.configure('TFrame', background=PALETTE['bg'])
    style.configure('TLabel', background=PALETTE['bg'], foreground=PALETTE['text'])
    style.configure('App.TFrame', background=PALETTE['primary'])
    style.configure('AppTitle.TLabel', background=PALETTE['primary'], foreground='white',
                    font=(FONT_FAMILY, 15, 'bold'))
    style.configure('Header.TLabel', font=(FONT_FAMILY, 12, 'bold'), foreground=PALETTE['primary'])
    style.configure('Sub.TLabel', font=(FONT_FAMILY, 9), foreground=PALETTE['muted'])
    style.configure('Warn.TLabel', font=(FONT_FAMILY, 9, 'italic'), foreground=PALETTE['warn'])
    style.configure('Card.TLabelframe', background=PALETTE['surface'], bordercolor=PALETTE['border'],
                    relief='solid', borderwidth=1)
    style.configure('Card.TLabelframe.Label', background=PALETTE['surface'], foreground=PALETTE['primary'],
                    font=(FONT_FAMILY, 10, 'bold'))
    style.configure('Card.TFrame', background=PALETTE['surface'])
    style.configure('Card.TLabel', background=PALETTE['surface'], foreground=PALETTE['text'])
    style.configure('TButton', font=(FONT_FAMILY, 10), padding=6)
    style.configure('Accent.TButton', font=(FONT_FAMILY, 10, 'bold'))
    style.map('Accent.TButton', foreground=[('!disabled', 'white')],
             background=[('!disabled', PALETTE['primary']), ('active', PALETTE['primary_active'])])
    style.configure('TNotebook', background=PALETTE['bg'], borderwidth=0)
    style.configure('TNotebook.Tab', font=(FONT_FAMILY, 10), padding=(14, 8))
    style.configure('TEntry', padding=4)
    style.configure('TCombobox', padding=4)
    style.configure('TCheckbutton', background=PALETTE['surface'])


# ----------------------------- File listing -----------------------------

def list_files(directory: str, pattern: str = '*.csv') -> list:
    if not os.path.isdir(directory):
        return []
    return sorted(str(p.relative_to(directory)).replace(os.sep, '/') for p in Path(directory).rglob(pattern))


def list_subdirs(directory: str) -> list:
    if not os.path.isdir(directory):
        return []
    return sorted(d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d)))


# ----------------------------- Background work plumbing -----------------------------

class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class ThreadedLog:
    """
    Runs a worker function on a background thread and streams its log(...) calls into a ScrolledText
    widget on the main thread via a queue, so long-running work doesn't freeze the GUI.
    """

    def __init__(self, text_widget: scrolledtext.ScrolledText):
        self.text_widget = text_widget
        self.q = queue.Queue()
        self._poll()

    def log(self, message):
        self.q.put(str(message))

    def _poll(self):
        try:
            while True:
                message = self.q.get_nowait()
                self.text_widget.configure(state=NORMAL)
                self.text_widget.insert(END, message + '\n')
                self.text_widget.see(END)
                self.text_widget.configure(state=DISABLED)
        except queue.Empty:
            pass
        self.text_widget.after(150, self._poll)

    def run(self, func, *args, on_done=None, on_error=None, on_finally=None, **kwargs):
        # Callers pass log=self.log explicitly in kwargs when the target function accepts a log parameter.
        def target():
            try:
                result = func(*args, **kwargs)
                self.log('Done.')
                if on_done is not None:
                    self.text_widget.after(0, lambda: on_done(result))
            except Exception as ex:
                self.log(f'ERROR: {ex}')
                self.log(traceback.format_exc())
                if on_error is not None:
                    self.text_widget.after(0, lambda: on_error(ex))
            finally:
                if on_finally is not None:
                    self.text_widget.after(0, on_finally)

        threading.Thread(target=target, daemon=True).start()


# ----------------------------- Widget helpers -----------------------------

def make_scrollable(parent) -> ttk.Frame:
    """
    Wraps a notebook tab (or subtab) in a vertically scrollable canvas and returns the frame to build
    that tab's content into, exactly as if it were the tab itself.
    """
    canvas = Canvas(parent, background=PALETTE['bg'], highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient=VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill=Y)

    content = ttk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=content, anchor='nw')

    def on_content_configure(event=None):
        canvas.configure(scrollregion=canvas.bbox('all'))

    def on_canvas_configure(event):
        canvas.itemconfigure(window_id, width=event.width)  # inner frame tracks the canvas's width

    content.bind('<Configure>', on_content_configure)
    canvas.bind('<Configure>', on_canvas_configure)

    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

    # only steal the mouse wheel while the pointer is actually over this canvas, so tabs/subtabs don't
    # fight each other over global wheel events
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', on_mousewheel))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

    return content


def card(parent, title) -> ttk.LabelFrame:
    frame = ttk.LabelFrame(parent, text=title, style='Card.TLabelframe', padding=10)
    frame.pack(fill=X, padx=10, pady=(10, 0))
    return frame


def make_log_box(parent) -> ThreadedLog:
    frame = ttk.LabelFrame(parent, text='Activity Log', style='Card.TLabelframe', padding=6)
    frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
    box = scrolledtext.ScrolledText(frame, height=9, state=DISABLED, bg=PALETTE['log_bg'],
                                    fg=PALETTE['log_fg'], insertbackground=PALETTE['log_fg'],
                                    font=('Consolas', 9), relief='flat')
    box.pack(fill=BOTH, expand=True)
    return ThreadedLog(box)


def bind_combobox_filter(combo: ttk.Combobox, get_full_list):
    # Narrows the dropdown to substring matches as the user types, without touching what they've typed.
    def on_keyrelease(event):
        if event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        typed = combo.get()
        full = get_full_list()
        combo['values'] = full if not typed else [v for v in full if typed.lower() in v.lower()]

    combo.bind('<KeyRelease>', on_keyrelease)


def make_file_picker(parent, directory: str, pattern: str = '*.csv'):
    """Builds a labeled, filterable, refreshable dropdown of files under `directory`. Returns (var, combo,
    refresh_fn) -- call refresh_fn() after an action changes what files exist."""
    var = StringVar()
    combo = ttk.Combobox(parent, textvariable=var, width=48)
    state = {'all': []}

    def refresh():
        state['all'] = list_files(directory, pattern)
        combo['values'] = state['all']

    bind_combobox_filter(combo, lambda: state['all'])
    refresh()
    return var, combo, refresh


def preview_dataframe(root, df: pd.DataFrame, title: str = 'Preview'):
    win = Toplevel(root)
    win.title(title)
    win.geometry('950x620')
    table = pdt.Table(win, dataframe=df, showtoolbar=True, showstatusbar=True)
    table.show()


def preview_series(root, values, title: str, ylabel: str, max_points: int = 864):
    # 864 steps = ~3 days at 5-min resolution -- enough to sanity-check a schedule/curve without a slow plot.
    win = Toplevel(root)
    win.title(title)
    fig = Figure(figsize=(7, 4))
    ax = fig.add_subplot(111)
    ax.plot(np.asarray(values).flatten()[:max_points])
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel('Timestep')
    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=BOTH, expand=True)


def browse_file(target_var: StringVar, initialdir='.', filetypes=(('All files', '*.*'),)):
    path = filedialog.askopenfilename(initialdir=initialdir, filetypes=filetypes)
    if path:
        target_var.set(path)


def make_stoppable_action(parent, active_tokens: dict, token_key: str, start_text: str, start_cmd,
                          style='Accent.TButton'):
    """
    Builds a Start/Stop button pair for a long-running, cancellable action, returning the container Frame
    so the caller can place it with whichever geometry manager (pack or grid) the rest of that card
    already uses -- pack and grid can't be mixed within the same container. start_cmd receives a
    cancel_check callable it should pass through to the worker function.

    active_tokens is a dict the caller owns (one per window, e.g. self._active_tokens), so multiple
    independent stoppable actions in the same window can each track their own CancelToken by key.
    """
    row = ttk.Frame(parent, style='Card.TFrame')
    stop_btn = ttk.Button(row, text='Stop', state=DISABLED)
    start_btn = ttk.Button(row, text=start_text, style=style)

    def on_start():
        token = CancelToken()
        active_tokens[token_key] = token
        start_btn.configure(state=DISABLED)
        stop_btn.configure(state=NORMAL)

        def on_finally():
            start_btn.configure(state=NORMAL)
            stop_btn.configure(state=DISABLED)
            active_tokens.pop(token_key, None)

        start_cmd(token.is_cancelled, on_finally)

    def on_stop():
        token = active_tokens.get(token_key)
        if token is not None:
            token.cancel()
        stop_btn.configure(state=DISABLED)

    start_btn.configure(command=on_start)
    stop_btn.configure(command=on_stop)
    start_btn.pack(side=LEFT)
    stop_btn.pack(side=LEFT, padx=(6, 0))
    return row
