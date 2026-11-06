"""
Cross-process progress reporting for Simulation.run_collection.

Worker processes never print directly to the console -- with several worker
processes doing that at once, output from different scenarios interleaves
and appears out of order (this is just how unsynchronized print() from
multiple OS processes looks, not a bug in any one of them). Instead, workers
report short events (task started, scenario done, scenario error) through a
multiprocessing.Queue to the main process, where a single listener thread is
the only thing that ever writes to the console -- which makes interleaving
impossible by construction -- and optionally drives a Tk progress window.

Detailed per-scenario output (the timing/ETA line, full tracebacks) is
written to a per-task log file instead of the console, so nothing is lost;
only short summaries travel through the queue.
"""
import datetime
import os
import queue
import threading
import time


def _fmt_duration(seconds: float) -> str:
    return str(datetime.timedelta(seconds=max(0, int(seconds))))

# --- worker-process state ---
# Each worker process only ever runs one task (one input file, or one chunk
# of one) at a time, so plain module globals are safe here -- there is no
# concurrent use within a single process.
_queue = None
_log_file = None
_file_key = None


def init_worker(q):
    """ProcessPoolExecutor initializer: stash the shared queue in this worker process."""
    global _queue
    _queue = q


def _put(event):
    if _queue is None:
        return
    try:
        _queue.put_nowait(event)
    except Exception:
        pass  # progress reporting must never be able to stall or fail a scenario


def start_task(file_key: str, log_path: str):
    """Call once before running a file/chunk's scenarios."""
    global _log_file, _file_key
    _file_key = file_key
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        _log_file = open(log_path, 'a', buffering=1)
    except Exception:
        _log_file = None
    _put(('task_start', os.getpid(), file_key, None, None))


def end_task():
    """Call in a finally so it fires whether or not the task raised."""
    global _log_file, _file_key
    _put(('task_end', os.getpid(), _file_key, None, None))
    if _log_file is not None:
        try:
            _log_file.close()
        except Exception:
            pass
    _log_file = None
    _file_key = None


def report_scenario_done(scen_id, elapsed: float, remaining_str: str):
    line = f'Scenario {scen_id} done in {round(elapsed, 3)} seconds. Remaining time: {remaining_str}'
    if _log_file is not None:
        try:
            _log_file.write(line + '\n')
        except Exception:
            pass
    else:
        # start_task was never called (e.g. run_model() used standalone) -- fall back to
        # today's behavior so nothing changes for callers outside run_collection.
        print(line)
    _put(('scenario_done', os.getpid(), _file_key, scen_id, elapsed))


def report_scenario_error(scen_id, ex: Exception, tb_text: str):
    line = f'Exception thrown for Scenario{scen_id}\n{ex}\n{tb_text}'
    if _log_file is not None:
        try:
            _log_file.write(line + '\n')
        except Exception:
            pass
    else:
        print(line)
    _put(('scenario_error', os.getpid(), _file_key, scen_id, str(ex)))


# --- main-process state ---

class ProgressListener:
    """
    Owns the progress queue in the main process and is the sole console
    writer -- draining the queue on a background thread and printing from
    there keeps output clean no matter how many worker processes are
    reporting concurrently.
    """

    def __init__(self, q, console_verbose: bool = False, gui=None):
        self._queue = q
        self._console_verbose = console_verbose
        self._gui = gui
        self._slots = {}
        self._next_slot = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def attach_gui(self, gui):
        """Wire a ProgressGui in after construction, once show_gui builds one."""
        self._gui = gui

    def _slot_for(self, pid):
        if pid not in self._slots:
            self._slots[pid] = self._next_slot
            self._next_slot += 1
        return self._slots[pid]

    def _run(self):
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            except (EOFError, OSError):
                break
            self._handle(event)

    def _handle(self, event):
        kind, pid, file_key, scen_id, payload = event
        slot = self._slot_for(pid)
        if kind == 'scenario_done' and self._console_verbose:
            print(f'  [worker {slot}] {file_key}: scenario {scen_id} done in {round(payload, 3)}s')
        elif kind == 'scenario_error':
            print(f'  [worker {slot}] {file_key}: scenario {scen_id} FAILED: {payload}')
        if self._gui is not None:
            self._gui.handle_event(kind, slot, file_key, scen_id, payload)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)


class ProgressGui:
    """
    Tkinter window with a fixed header (overall progress bar + elapsed/
    remaining/ETA), a scrollable list with one row per input file (bar,
    x/total count, worker slot(s), per-file ETA), and a fixed footer with a
    Close button. Must be created and driven (mainloop/after) from the
    thread that will own it -- see drive_with_gui.
    """

    def __init__(self, file_totals: dict):
        import tkinter as tk
        from tkinter import ttk

        self.root = tk.Tk()
        self.root.title('Scenario Progress')
        self.root.geometry('760x420')

        self._totals = dict(file_totals)
        self._overall_total = sum(self._totals.values()) or 1
        self._counts = {file_key: 0 for file_key in file_totals}
        self._workers = {file_key: set() for file_key in file_totals}
        self._file_start = {file_key: None for file_key in file_totals}
        self._start_time = time.time()
        self._events = queue.Queue()

        # --- fixed header: overall progress + time stats ---
        header = ttk.Frame(self.root, padding=(10, 8, 10, 6))
        header.pack(side='top', fill='x')
        ttk.Label(header, text='Overall Progress').pack(side='top', anchor='w')
        self._overall_bar = ttk.Progressbar(header, maximum=self._overall_total)
        self._overall_bar.pack(side='top', fill='x', pady=(2, 4))
        self._stats_label = ttk.Label(header, text='Elapsed: 0:00:00   Remaining: estimating...   '
                                                     'ETA: estimating...')
        self._stats_label.pack(side='top', anchor='w')
        ttk.Separator(self.root, orient='horizontal').pack(side='top', fill='x')

        # --- scrollable per-file list (future-proofed for large collections) ---
        list_container = ttk.Frame(self.root)
        list_container.pack(side='top', fill='both', expand=True)
        canvas = tk.Canvas(list_container, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(list_container, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        vscroll.pack(side='right', fill='y')

        inner = ttk.Frame(canvas, padding=(10, 4, 10, 4))
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(inner_id, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all(
            '<MouseWheel>', lambda ev: canvas.yview_scroll(int(-1 * (ev.delta / 120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        self._bars = {}
        self._count_labels = {}
        self._worker_labels = {}
        self._eta_labels = {}
        for row, (file_key, total) in enumerate(file_totals.items()):
            ttk.Label(inner, text=file_key, width=26, anchor='w').grid(
                row=row, column=0, sticky='w', padx=(0, 6), pady=2)
            bar = ttk.Progressbar(inner, maximum=max(total, 1), length=200)
            bar.grid(row=row, column=1, padx=6, pady=2, sticky='w')
            self._bars[file_key] = bar
            count_label = ttk.Label(inner, text=f'0/{total}', width=9, anchor='w')
            count_label.grid(row=row, column=2, sticky='w', padx=6)
            self._count_labels[file_key] = count_label
            worker_label = ttk.Label(inner, text='', width=12, anchor='w')
            worker_label.grid(row=row, column=3, sticky='w', padx=6)
            self._worker_labels[file_key] = worker_label
            eta_label = ttk.Label(inner, text='estimating...', width=24, anchor='w')
            eta_label.grid(row=row, column=4, sticky='w', padx=6)
            self._eta_labels[file_key] = eta_label

        # --- fixed footer ---
        footer = ttk.Frame(self.root, padding=(10, 6, 10, 8))
        footer.pack(side='bottom', fill='x')
        self._close_btn = ttk.Button(footer, text='Close', command=self.root.destroy, state='disabled')
        self._close_btn.pack(side='right')

        self.root.after(100, self._poll)
        self.root.after(1000, self._tick)

    def handle_event(self, kind, slot, file_key, scen_id, payload):
        # Called from the listener thread -- only ever queues; widgets are touched
        # exclusively from _poll/_tick, which run on the Tk main thread.
        self._events.put((kind, slot, file_key))

    def notify_finished(self):
        self._events.put(('__finished__', None, None))

    def _alive(self) -> bool:
        try:
            return bool(self.root.winfo_exists())
        except Exception:
            return False

    def _poll(self):
        try:
            while True:
                kind, slot, file_key = self._events.get_nowait()
                self._apply(kind, slot, file_key)
        except queue.Empty:
            pass
        if self._alive():
            self.root.after(100, self._poll)

    def _tick(self):
        # Elapsed/remaining/ETA are wall-clock, not event-driven, so they need their own
        # ticker to keep counting even between scenario completions.
        if not self._alive():
            return
        self._refresh_time_labels()
        self.root.after(1000, self._tick)

    def _apply(self, kind, slot, file_key):
        if kind == '__finished__':
            self._close_btn.config(state='normal')
            self._refresh_time_labels()
            return
        if file_key not in self._bars:
            return
        if kind == 'task_start':
            self._workers[file_key].add(slot)
            if self._file_start[file_key] is None:
                self._file_start[file_key] = time.time()
        elif kind == 'task_end':
            self._workers[file_key].discard(slot)
        elif kind == 'scenario_done':
            self._counts[file_key] += 1
            self._bars[file_key]['value'] = self._counts[file_key]
            self._count_labels[file_key].config(text=f'{self._counts[file_key]}/{self._totals[file_key]}')
            self._overall_bar['value'] = sum(self._counts.values())
        workers = sorted(self._workers[file_key])
        self._worker_labels[file_key].config(
            text=f"workers: {', '.join(str(w) for w in workers)}" if workers else '')

    def _file_eta_text(self, file_key: str, now: float) -> str:
        total = self._totals[file_key]
        completed = self._counts[file_key]
        if total <= 0:
            return 'n/a'
        if completed >= total:
            return 'done'
        start = self._file_start[file_key]
        if start is None or completed == 0:
            return 'estimating...'
        rate = completed / (now - start) if now > start else 0
        if rate <= 0:
            return 'estimating...'
        remaining = (total - completed) / rate
        eta_clock = (datetime.datetime.now() + datetime.timedelta(seconds=remaining)).strftime('%H:%M:%S')
        return f'{eta_clock} (~{_fmt_duration(remaining)} left)'

    def _refresh_time_labels(self):
        now = time.time()
        for file_key in self._totals:
            self._eta_labels[file_key].config(text=self._file_eta_text(file_key, now))

        elapsed = now - self._start_time
        completed = sum(self._counts.values())
        remaining_text = 'estimating...'
        eta_text = 'estimating...'
        if completed > 0 and elapsed > 0:
            rate = completed / elapsed
            if rate > 0:
                remaining = (self._overall_total - completed) / rate
                remaining_text = _fmt_duration(remaining)
                eta_text = (datetime.datetime.now() + datetime.timedelta(seconds=remaining)).strftime('%H:%M:%S')
        self._stats_label.config(
            text=f'Elapsed: {_fmt_duration(elapsed)}   Remaining: ~{remaining_text}   ETA: {eta_text}   '
                 f'({completed}/{self._overall_total} scenarios)')

    def run(self):
        self.root.mainloop()


def drive_with_gui(driver_fn, gui: 'ProgressGui'):
    """
    Runs driver_fn() (the actual submit/as_completed work) on a background
    thread while the calling thread owns the Tk mainloop -- Tk is only safe
    to drive from the thread that created it, so the caller must build the
    ProgressGui (and attach it to the ProgressListener via attach_gui so
    events actually reach it) before calling this.
    """
    def _drive():
        try:
            driver_fn()
        finally:
            gui.notify_finished()

    thread = threading.Thread(target=_drive, daemon=True)
    thread.start()
    gui.run()
    thread.join()
