"""
HouseholdSim Hub
----------------
One window that ties the model's tools together:

-   Tools tab: launches the Data Import Wizard, the Input Builder Wizard, and the Results Viewer, each
    unchanged and in its own process (ResultsGUI.py builds its window at import time, and each tool
    expects to own its Tk root, so separate processes are what lets them all stay exactly as they are).
-   Run Simulation tab: runs Simulation.run_model (one input file) or Simulation.run_collection (a folder
    of input files) with the same options main.py would pass, streaming the console output into the
    window -- so a run no longer means editing main.py. Each run also logs the equivalent main.py call.

Run this file directly from anywhere (it chdirs to the repository root):

    python HouseholdSimHub.py

The simulation itself runs in a child process started as `python HouseholdSimHub.py --run <json>`, so a
crash or a Stop can't take the hub down. Module-level imports are stdlib-only on purpose: run_collection's
worker processes re-import this file as __mp_main__, and they shouldn't pay for tkinter/matplotlib.
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = 'InputFiles'
OUTPUT_DIR = 'Outputs'
NON_SCENARIO_INPUTS = {'Empty.xlsx'}  # template the Input Builder writes onto, not a runnable scenario file
NON_COLLECTION_DIRS = {'EV Files'}
TOOL_LOG_DIR = os.path.join(tempfile.gettempdir(), 'HouseholdSimHub')

TOOLS = [
    ('DataImportWizard.py', 'Data Import Wizard',
     'Download and process solar (NSRDB), house loads (ResStock), utilities/tariffs, and grid CO2 '
     '(Cambium/WattTime).'),
    ('InputBuilderWizard.py', 'Input Builder Wizard',
     'Build scenario-sweep input workbooks (single files or whole collections) into InputFiles/.'),
    ('ResultsGUI.py', 'Results Viewer',
     'Load finished runs and plot component time series and energy flows.'),
]

# run_model / run_collection defaults, so the equivalent main.py line only lists what was changed
MODEL_DEFAULTS = {'overwrite_runs': False, 'only_run': None, 'starting_scen': None, 'end_scen': None,
                  'full_results': None, 'save_pickles': False, 'write_parquet': True, 'compress_pickles': True,
                  'consolidate_results': False}
COLLECTION_DEFAULTS = {'overwrite_runs': True, 'parallel': True, 'max_workers': None, 'schedule': 'auto',
                       'save_pickles': False, 'compress_pickles': True, 'console_verbose': False,
                       'show_gui': False, 'consolidate_results': False}


# ----------------------------- Headless runner (child process) -----------------------------

def main_py_equivalent(job: dict) -> str:
    defaults = MODEL_DEFAULTS if job['mode'] == 'model' else COLLECTION_DEFAULTS
    func = 'run_model' if job['mode'] == 'model' else 'run_collection'
    args = [f'{k}={v!r}' for k, v in job['kwargs'].items() if k not in defaults or defaults[k] != v]
    return f'sm.{func}({", ".join(args)})'


def run_job(job: dict) -> int:
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)
    print(f'Equivalent main.py call:\n    {main_py_equivalent(job)}\n', flush=True)
    import Simulation as sm
    t0 = time.time()
    try:
        if job['mode'] == 'model':
            sm.run_model(**job['kwargs'])
        else:
            sm.run_collection(**job['kwargs'])
    except Exception:
        traceback.print_exc()
        print(f'\nRun FAILED after {time.time() - t0:.1f} s.', flush=True)
        return 1
    print(f'\nRun finished in {time.time() - t0:.1f} s.', flush=True)
    return 0


# ----------------------------- Helpers -----------------------------

def list_input_files() -> list:
    """Scenario workbooks as run_model expects them: path under InputFiles/, '/'-separated, no .xlsx."""
    found = []
    for dirpath, dirnames, filenames in os.walk(INPUT_DIR):
        dirnames[:] = sorted(d for d in dirnames if d not in NON_COLLECTION_DIRS)
        rel_dir = os.path.relpath(dirpath, INPUT_DIR)
        for f in sorted(filenames):
            if f.endswith('.xlsx') and not f.startswith('~$') and f not in NON_SCENARIO_INPUTS:
                rel = f[:-5] if rel_dir == '.' else os.path.join(rel_dir, f[:-5])
                found.append(rel.replace(os.sep, '/'))
    # top-level files first, then collection members
    return sorted(found, key=lambda p: ('/' in p, p.lower()))


def list_collections() -> list:
    if not os.path.isdir(INPUT_DIR):
        return []
    return sorted(d for d in os.listdir(INPUT_DIR)
                  if d not in NON_COLLECTION_DIRS and os.path.isdir(os.path.join(INPUT_DIR, d))
                  and any(f.endswith('.xlsx') for f in os.listdir(os.path.join(INPUT_DIR, d))))


def _cast(text: str):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def parse_only_run(text: str):
    """'Load Amount = 6000, 15000; Net Meter Type = nem3' -> {'Load Amount': [6000, 15000], ...}"""
    text = text.strip()
    if not text:
        return None
    result = {}
    for clause in text.split(';'):
        if not clause.strip():
            continue
        if '=' not in clause:
            raise ValueError(f'"{clause.strip()}" is missing "=" (expected Column = value1, value2)')
        col, values = clause.split('=', 1)
        vals = [_cast(v.strip()) for v in values.split(',') if v.strip()]
        result[col.strip()] = vals[0] if len(vals) == 1 else vals
    return result


def _optional_int(text: str, name: str):
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise ValueError(f'{name} must be a whole number (or blank)')


def kill_tree(proc: subprocess.Popen):
    """Stops a process and everything it spawned (run_collection's worker pool included)."""
    if proc.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def _popen_kwargs() -> dict:
    kw = {'cwd': REPO_ROOT, 'stdin': subprocess.DEVNULL}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW
    else:
        kw['start_new_session'] = True
    return kw


def open_path(path: str):
    if os.name == 'nt':
        os.startfile(path)
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])


# ----------------------------- GUI -----------------------------

def launch_gui():
    from tkinter import Tk, StringVar, BooleanVar, END, NORMAL, DISABLED, LEFT, RIGHT, BOTH, X, W, EW
    from tkinter import ttk, messagebox, scrolledtext
    import gui_common
    from gui_common import PALETTE

    class Hub:
        def __init__(self, root: Tk):
            self.root = root
            root.title('HouseholdSim Hub')
            root.geometry('1000x820')
            gui_common.configure_style(root)

            self.tool_procs = {}  # script -> (Popen, log_path)
            self.tool_status = {}  # script -> StringVar
            self.sim_proc = None
            self.sim_queue = queue.Queue()

            title_bar = ttk.Frame(root, style='App.TFrame')
            title_bar.pack(fill=X)
            ttk.Label(title_bar, text='  HouseholdSim Hub', style='AppTitle.TLabel').pack(side=LEFT, pady=10)

            notebook = ttk.Notebook(root)
            notebook.pack(fill=BOTH, expand=True, padx=8, pady=8)
            tools_tab = ttk.Frame(notebook)
            run_tab = ttk.Frame(notebook)
            notebook.add(tools_tab, text='Tools')
            notebook.add(run_tab, text='Run Simulation')
            notebook.bind('<<NotebookTabChanged>>', lambda e: self.refresh_inputs())

            self._build_tools_tab(tools_tab)
            self._build_run_tab(run_tab)
            self._poll()
            root.protocol('WM_DELETE_WINDOW', self.on_close)

        # ---------- Tools ----------

        def _build_tools_tab(self, tab):
            for script, name, desc in TOOLS:
                card = gui_common.card(tab, name)
                card.columnconfigure(0, weight=1)
                ttk.Label(card, text=desc, style='Card.TLabel', wraplength=640).grid(row=0, column=0, sticky=W)
                status = StringVar(value='Not running')
                self.tool_status[script] = status
                ttk.Label(card, textvariable=status, style='Sub.TLabel').grid(row=1, column=0, sticky=W,
                                                                               pady=(4, 0))
                ttk.Button(card, text='Open', style='Accent.TButton',
                           command=lambda s=script: self.launch_tool(s)).grid(row=0, column=1, rowspan=2,
                                                                              padx=(10, 0))
            ttk.Label(tab, text='Each tool opens in its own window and keeps running if the hub is closed. '
                                f'Their console output is saved under {TOOL_LOG_DIR}.',
                      style='Sub.TLabel', wraplength=900).pack(anchor=W, padx=12, pady=10)

        def launch_tool(self, script):
            running = self.tool_procs.get(script)
            if running and running[0].poll() is None:
                if not messagebox.askyesno('Already open', f'{script} is already running. Open another copy?'):
                    return
            os.makedirs(TOOL_LOG_DIR, exist_ok=True)
            log_path = os.path.join(TOOL_LOG_DIR, f'{script[:-3]}_{time.strftime("%Y%m%d_%H%M%S")}.log')
            log_file = open(log_path, 'w', encoding='utf-8', errors='replace')
            env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
            proc = subprocess.Popen([sys.executable, script], stdout=log_file, stderr=subprocess.STDOUT,
                                    env=env, **_popen_kwargs())
            log_file.close()  # the child holds its own handle
            self.tool_procs[script] = (proc, log_path)
            self.tool_status[script].set(f'Running (pid {proc.pid})')
            self.log(f'Opened {script} (pid {proc.pid}); output -> {log_path}')

        def _check_tools(self):
            for script, (proc, log_path) in list(self.tool_procs.items()):
                code = proc.poll()
                if code is None:
                    continue
                del self.tool_procs[script]
                if code == 0:
                    self.tool_status[script].set('Not running')
                    continue
                self.tool_status[script].set(f'Exited with error (code {code}) -- see Run Simulation log')
                try:
                    with open(log_path, encoding='utf-8', errors='replace') as f:
                        tail = f.readlines()[-25:]
                except OSError:
                    tail = []
                self.log(f'{script} exited with code {code}. Last output ({log_path}):')
                for line in tail:
                    self.log('    ' + line.rstrip())

        # ---------- Run Simulation ----------

        def _build_run_tab(self, tab):
            what = gui_common.card(tab, 'What to run')
            self.mode = StringVar(value='model')
            ttk.Radiobutton(what, text='Single input file  (run_model)', variable=self.mode, value='model',
                            command=self._on_mode).grid(row=0, column=0, sticky=W)
            ttk.Radiobutton(what, text='Collection folder  (run_collection)', variable=self.mode,
                            value='collection', command=self._on_mode).grid(row=0, column=1, sticky=W, padx=12)
            ttk.Button(what, text='Refresh lists', command=self.refresh_inputs).grid(row=0, column=2, sticky=W)

            self.input_label = ttk.Label(what, text='Input file:', style='Card.TLabel')
            self.input_label.grid(row=1, column=0, sticky=W, pady=(8, 2))
            self.input_var = StringVar()
            self.input_combo = ttk.Combobox(what, textvariable=self.input_var, width=60)
            self.input_combo.grid(row=1, column=1, columnspan=2, sticky=W, pady=(8, 2))
            self.input_combo.bind('<<ComboboxSelected>>', lambda e: self._default_collection_name())
            self._input_choices = []
            gui_common.bind_combobox_filter(self.input_combo, lambda: self._input_choices)

            self.name_label = ttk.Label(what, text='Output name (Outputs/...):', style='Card.TLabel')
            self.name_label.grid(row=2, column=0, sticky=W, pady=2)
            self.name_var = StringVar()
            self.name_entry = ttk.Entry(what, textvariable=self.name_var, width=62)
            self.name_entry.grid(row=2, column=1, columnspan=2, sticky=W, pady=2)

            opts = gui_common.card(tab, 'Options')
            self.overwrite = BooleanVar(value=MODEL_DEFAULTS['overwrite_runs'])
            self.save_pickles = BooleanVar(value=False)
            self.consolidate = BooleanVar(value=False)
            ttk.Checkbutton(opts, text='Overwrite existing runs (off = resume)', variable=self.overwrite).grid(
                row=0, column=0, sticky=W)
            ttk.Checkbutton(opts, text='Save per-scenario pickles', variable=self.save_pickles).grid(
                row=0, column=1, sticky=W, padx=12)
            ttk.Checkbutton(opts, text='Consolidate pickles into one store', variable=self.consolidate).grid(
                row=0, column=2, sticky=W)

            # run_model-only
            self.model_opts = ttk.Frame(opts, style='Card.TFrame')
            self.model_opts.grid(row=1, column=0, columnspan=3, sticky=EW, pady=(8, 0))
            self.full_results = BooleanVar(value=False)
            self.write_parquet = BooleanVar(value=True)
            ttk.Checkbutton(self.model_opts, text='Full results (keeps component objects; implies pickles)',
                            variable=self.full_results).grid(row=0, column=0, columnspan=2, sticky=W)
            ttk.Checkbutton(self.model_opts, text='Write Parquet results', variable=self.write_parquet).grid(
                row=0, column=2, sticky=W, padx=12)
            ttk.Label(self.model_opts, text='Scenario IDs from / to:', style='Card.TLabel').grid(
                row=1, column=0, sticky=W, pady=4)
            self.start_scen = StringVar()
            self.end_scen = StringVar()
            bounds = ttk.Frame(self.model_opts, style='Card.TFrame')
            bounds.grid(row=1, column=1, columnspan=2, sticky=W)
            ttk.Entry(bounds, textvariable=self.start_scen, width=8).pack(side=LEFT)
            ttk.Label(bounds, text=' to ', style='Card.TLabel').pack(side=LEFT)
            ttk.Entry(bounds, textvariable=self.end_scen, width=8).pack(side=LEFT)
            ttk.Label(bounds, text='  (blank = all)', style='Sub.TLabel').pack(side=LEFT)
            ttk.Label(self.model_opts, text='Only run where:', style='Card.TLabel').grid(row=2, column=0, sticky=W)
            self.only_run = StringVar()
            ttk.Entry(self.model_opts, textvariable=self.only_run, width=62).grid(row=2, column=1, columnspan=2,
                                                                                 sticky=W)
            ttk.Label(self.model_opts, text='e.g.  Load Amount = 6000, 15000; Net Meter Type = nem3   '
                                            '(blank = no filter)', style='Sub.TLabel').grid(
                row=3, column=1, columnspan=2, sticky=W)

            # run_collection-only
            self.coll_opts = ttk.Frame(opts, style='Card.TFrame')
            self.coll_opts.grid(row=1, column=0, columnspan=3, sticky=EW, pady=(8, 0))
            self.parallel = BooleanVar(value=True)
            self.show_gui = BooleanVar(value=True)
            self.verbose = BooleanVar(value=False)
            ttk.Checkbutton(self.coll_opts, text='Run in parallel', variable=self.parallel).grid(
                row=0, column=0, sticky=W)
            ttk.Checkbutton(self.coll_opts, text='Show progress window', variable=self.show_gui).grid(
                row=0, column=1, sticky=W, padx=12)
            ttk.Checkbutton(self.coll_opts, text='Print every scenario', variable=self.verbose).grid(
                row=0, column=2, sticky=W)
            ttk.Label(self.coll_opts, text='Max workers:', style='Card.TLabel').grid(row=1, column=0, sticky=W,
                                                                                     pady=4)
            self.max_workers = StringVar()
            workers_row = ttk.Frame(self.coll_opts, style='Card.TFrame')
            workers_row.grid(row=1, column=1, columnspan=2, sticky=W)
            ttk.Entry(workers_row, textvariable=self.max_workers, width=8).pack(side=LEFT)
            ttk.Label(workers_row, text=f'  (blank = all {os.cpu_count()} cores)   Schedule:',
                      style='Card.TLabel').pack(side=LEFT)
            self.schedule = StringVar(value='auto')
            ttk.Combobox(workers_row, textvariable=self.schedule, values=['auto', 'file', 'chunk'],
                         state='readonly', width=8).pack(side=LEFT, padx=4)

            actions = ttk.Frame(tab)
            actions.pack(fill=X, padx=10, pady=(10, 0))
            self.run_btn = ttk.Button(actions, text='Run', style='Accent.TButton', command=self.start_run)
            self.run_btn.pack(side=LEFT)
            self.stop_btn = ttk.Button(actions, text='Stop', state=DISABLED, command=self.stop_run)
            self.stop_btn.pack(side=LEFT, padx=6)
            ttk.Button(actions, text='Open output folder', command=self.open_output).pack(side=LEFT, padx=6)
            ttk.Button(actions, text='Open Results Viewer',
                       command=lambda: self.launch_tool('ResultsGUI.py')).pack(side=LEFT)
            ttk.Button(actions, text='Clear log', command=self.clear_log).pack(side=RIGHT)
            self.run_status = StringVar(value='Idle')
            ttk.Label(actions, textvariable=self.run_status, style='Sub.TLabel').pack(side=LEFT, padx=12)

            log_frame = ttk.LabelFrame(tab, text='Console Output', style='Card.TLabelframe', padding=6)
            log_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
            self.log_box = scrolledtext.ScrolledText(log_frame, height=12, state=DISABLED, bg=PALETTE['log_bg'],
                                                     fg=PALETTE['log_fg'], insertbackground=PALETTE['log_fg'],
                                                     font=('Consolas', 9), relief='flat')
            self.log_box.pack(fill=BOTH, expand=True)

            self._on_mode()

        def _on_mode(self):
            if self.mode.get() == 'model':
                self.coll_opts.grid_remove()
                self.model_opts.grid()
                self.input_label.configure(text='Input file:')
                self.name_label.grid()
                self.name_entry.grid()
                self.overwrite.set(MODEL_DEFAULTS['overwrite_runs'])
            else:
                self.model_opts.grid_remove()
                self.coll_opts.grid()
                self.input_label.configure(text='Collection folder:')
                self.name_label.grid_remove()  # run_collection writes to Outputs/<folder>/<file>
                self.name_entry.grid_remove()
                self.overwrite.set(COLLECTION_DEFAULTS['overwrite_runs'])
            self.input_var.set('')
            self.refresh_inputs()

        def refresh_inputs(self):
            self._input_choices = list_input_files() if self.mode.get() == 'model' else list_collections()
            self.input_combo['values'] = self._input_choices

        def _default_collection_name(self):
            self.name_var.set(self.input_var.get())

        def _build_job(self) -> dict:
            target = self.input_var.get().strip()
            if self.mode.get() == 'model':
                if target not in list_input_files():
                    raise ValueError(f'"{target}" is not a scenario file under {INPUT_DIR}/.')
                kwargs = {
                    'input_file': target,
                    'collection_name': self.name_var.get().strip() or target,
                    'overwrite_runs': self.overwrite.get(),
                    'only_run': parse_only_run(self.only_run.get()),
                    'starting_scen': _optional_int(self.start_scen.get(), 'Starting scenario'),
                    'end_scen': _optional_int(self.end_scen.get(), 'Ending scenario'),
                    'full_results': True if self.full_results.get() else None,
                    'save_pickles': self.save_pickles.get(),
                    'write_parquet': self.write_parquet.get(),
                    'consolidate_results': self.consolidate.get(),
                }
                return {'mode': 'model', 'kwargs': kwargs}
            if target not in list_collections():
                raise ValueError(f'"{target}" is not a folder of scenario files under {INPUT_DIR}/.')
            kwargs = {
                'collection_path': target,
                'overwrite_runs': self.overwrite.get(),
                'parallel': self.parallel.get(),
                'max_workers': _optional_int(self.max_workers.get(), 'Max workers'),
                'schedule': self.schedule.get(),
                'save_pickles': self.save_pickles.get(),
                'console_verbose': self.verbose.get(),
                'show_gui': self.show_gui.get(),
                'consolidate_results': self.consolidate.get(),
            }
            return {'mode': 'collection', 'kwargs': kwargs}

        def start_run(self):
            if self.sim_proc is not None and self.sim_proc.poll() is None:
                return
            try:
                job = self._build_job()
            except ValueError as ex:
                messagebox.showerror('Check inputs', str(ex))
                return
            if job['kwargs']['overwrite_runs']:
                out = job['kwargs'].get('collection_name') or job['kwargs'].get('collection_path')
                if os.path.isdir(os.path.join(OUTPUT_DIR, out)) and not messagebox.askyesno(
                        'Overwrite?', f'{OUTPUT_DIR}/{out} already has results. Overwrite existing runs?'):
                    return
            self._last_output = job['kwargs'].get('collection_name') or job['kwargs'].get('collection_path')

            env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
            self.log(f'\n===== {time.strftime("%H:%M:%S")} starting =====')
            self.sim_proc = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--run',
                                              json.dumps(job)],
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                             encoding='utf-8', errors='replace', bufsize=1, env=env,
                                             **_popen_kwargs())
            threading.Thread(target=self._pump, args=(self.sim_proc,), daemon=True).start()
            self._run_started = time.time()
            self.run_btn.configure(state=DISABLED)
            self.stop_btn.configure(state=NORMAL)
            self.run_status.set('Running...')

        def _pump(self, proc):
            for line in proc.stdout:
                self.sim_queue.put(line.rstrip('\n'))
            proc.wait()
            self.sim_queue.put(None)

        def stop_run(self):
            if self.sim_proc is not None and self.sim_proc.poll() is None:
                kill_tree(self.sim_proc)
                self.log('Stopped by user. Completed scenarios are kept; re-run without "Overwrite" to resume.')

        def _on_run_finished(self):
            code = self.sim_proc.returncode
            elapsed = time.time() - self._run_started
            self.run_status.set(f'{"Finished" if code == 0 else "Failed / stopped"} '
                                f'(exit code {code}, {elapsed:.0f} s)')
            self.run_btn.configure(state=NORMAL)
            self.stop_btn.configure(state=DISABLED)

        def open_output(self):
            name = getattr(self, '_last_output', None) or (
                self.name_var.get().strip() if self.mode.get() == 'model' else self.input_var.get().strip())
            path = os.path.join(REPO_ROOT, OUTPUT_DIR, name) if name else os.path.join(REPO_ROOT, OUTPUT_DIR)
            if not os.path.isdir(path):
                path = os.path.join(REPO_ROOT, OUTPUT_DIR)
            open_path(path)

        # ---------- shared ----------

        def log(self, message):
            self.sim_queue.put(message)

        def clear_log(self):
            self.log_box.configure(state=NORMAL)
            self.log_box.delete('1.0', END)
            self.log_box.configure(state=DISABLED)

        def _poll(self):
            lines = []
            try:
                while len(lines) < 2000:
                    item = self.sim_queue.get_nowait()
                    if item is None:
                        self._on_run_finished()
                    else:
                        lines.append(item)
            except queue.Empty:
                pass
            if lines:
                self.log_box.configure(state=NORMAL)
                self.log_box.insert(END, '\n'.join(lines) + '\n')
                self.log_box.see(END)
                self.log_box.configure(state=DISABLED)
            self._check_tools()
            self.root.after(150, self._poll)

        def on_close(self):
            if self.sim_proc is not None and self.sim_proc.poll() is None:
                if not messagebox.askyesno('Simulation running', 'A simulation is still running. Stop it and '
                                                                 'close the hub?'):
                    return
                kill_tree(self.sim_proc)
            self.root.destroy()

    root = Tk()
    Hub(root)
    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--run':
        sys.exit(run_job(json.loads(sys.argv[2])))
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)
    launch_gui()
