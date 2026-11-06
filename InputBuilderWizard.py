"""
Input Builder Wizard
---------------------
A Tkinter front end for Setup.generate_input_file / Setup.generate_input_collection -- the
programmatic machinery that already builds full-factorial scenario-sweep workbooks onto
InputFiles/Empty.xlsx. This module writes no xlsx files itself; it only collects and validates the
sweep parameters those two functions already accept, previews the resulting scenario count before
anything is written, and shows reference-data pickers (EV models, PV models, driving patterns, zip
codes) for the columns that are easy to get wrong by hand (a bad Utility File/Tariff ID/EV File/EV
Year+Make+Model+Trim combination fails with a raw exception or silently falls back deep inside
run_model, not at input-authoring time).

Run this file directly (it must be run from the repository root, same as DataImportWizard.py/
ResultsGUI.py).
"""
import os
from tkinter import *
from tkinter import ttk, messagebox

import pandas as pd

import Setup as sp
import gui_common
from gui_common import PALETTE

EV_REFERENCE_PATH = 'Model Data/EVs.csv'
PV_REFERENCE_PATH = 'Model Data/PVs.xlsx'
DRIVING_PATTERNS_DIR = 'DrivingPatterns'
EV_FILES_DIR = 'InputFiles/EV Files'
UTILITIES_DIR = 'Utilities'
DEFAULT_POOL_DIR = 'Scripts/Pool Generation'  # where the real pool CSVs (e.g. refined_pools.csv) live

HES_OPT_STYLES = ['simple', 'flat', 'full charge']  # 'perfect' also parses but is a functional no-op today
CHARGE_SCHEMES = ['Front End', 'trickle charge', 'frontend']


def _parse_list(text: str, cast=str):
    """
    Splits a comma-separated entry into a list, casting each item. Blank input returns None, which
    tells generate_input_file/generate_input_collection to fall back to their own built-in defaults
    (that's what a None argument means to both functions) rather than an empty sweep axis.
    """
    text = (text or '').strip()
    if not text:
        return None
    return [cast(v.strip()) for v in text.split(',') if v.strip()]


def _axis_len(values, default_len: int) -> int:
    return len(values) if values is not None else default_len


class InputBuilderWizard:
    # Rough axis lengths for generate_input_file's own hardcoded defaults, used only so the
    # row-count preview means something when a field is left blank.
    _DEFAULT_LENS = {
        'years': 1, 'net_met_policies': 2, 'house_loads': 3, 'pv_sizes': 11, 'hes_sizes': 9,
        'hes_opt_styles': 2, 'v2h_limits': 3, 'commutes': 1, 'charge_schemes': 1,
    }

    def __init__(self, root: Tk):
        self.root = root
        root.title('HouseholdSim - Input Builder Wizard')
        root.geometry('1080x840')
        gui_common.configure_style(root)

        title_bar = ttk.Frame(root, style='App.TFrame')
        title_bar.pack(fill=X)
        ttk.Label(title_bar, text='  HouseholdSim Input Builder Wizard', style='AppTitle.TLabel').pack(
            side=LEFT, pady=10)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=BOTH, expand=True, padx=8, pady=8)

        self.single_tab = ttk.Frame(notebook)
        self.collection_tab = ttk.Frame(notebook)
        notebook.add(self.single_tab, text='Single File')
        notebook.add(self.collection_tab, text='Collection')

        self._active_tokens = {}

        self._build_single_tab()
        self._build_collection_tab()

    # ---------- shared sweep-axis form ----------

    def _build_axis_fields(self, card) -> dict:
        """
        Builds the common sweep-axis entry fields (years, net meter policies, house loads, PV sizes,
        HES sizes, HES optimization styles, V2H limits, commutes, charge schemes) shared by both the
        Single File and Collection tabs. Returns {axis_name: StringVar}.
        """
        rows = [
            ('years', 'Years', 'e.g. 2018'),
            ('net_met_policies', 'Net Meter Policies', 'e.g. wholesale, one-to-one, nem3'),
            ('house_loads', 'House Loads (kWh/yr)', 'e.g. 6000, 11000, 15000'),
            ('pv_sizes', 'PV Sizes (kW)', 'e.g. 0, 3, 5, 7, 10'),
            ('hes_sizes', 'HES Sizes (kWh)', 'e.g. 0, 5, 10, 20'),
            ('hes_opt_styles', 'HES Optimization Styles', ', '.join(HES_OPT_STYLES)),
            ('v2h_limits', 'V2H Discharge Limits', 'e.g. 1, 0.7, 0.5'),
            ('charge_schemes', 'EV Charge Schemes', ', '.join(CHARGE_SCHEMES)),
        ]
        vars_by_axis = {}
        for r, (axis, label, hint) in enumerate(rows):
            ttk.Label(card, text=label + ':', style='Card.TLabel').grid(
                row=r, column=0, sticky=W, padx=5, pady=4)
            var = StringVar()
            ttk.Entry(card, textvariable=var, width=44).grid(row=r, column=1, sticky=W, padx=5, pady=4)
            ttk.Label(card, text=hint, style='Sub.TLabel').grid(row=r, column=2, sticky=W, padx=5)
            vars_by_axis[axis] = var

        # Commutes get a reference-data picker over DrivingPatterns/ instead of free text, since a
        # typo'd pattern name fails with a raw FileNotFoundError deep in make_fleet.
        next_row = len(rows)
        ttk.Label(card, text='Commutes:', style='Card.TLabel').grid(
            row=next_row, column=0, sticky=W, padx=5, pady=4)
        commute_var, commute_combo, _ = gui_common.make_file_picker(card, DRIVING_PATTERNS_DIR, '*.csv')
        commute_combo.grid(row=next_row, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(card, text='pick one, or type several comma-separated stems',
                 style='Sub.TLabel').grid(row=next_row, column=2, sticky=W, padx=5)
        vars_by_axis['commutes'] = commute_var

        return vars_by_axis

    def _read_axes(self, axis_vars: dict) -> dict:
        commutes = _parse_list(axis_vars['commutes'].get())
        if commutes is not None:
            # The file picker's values include the .csv extension (needed for other pickers, e.g.
            # Utility Files), but generate_input_file's Pattern column wants a bare stem -- it appends
            # .csv itself when it resolves the file.
            commutes = [c[:-4] if c.lower().endswith('.csv') else c for c in commutes]
        return {
            'years': _parse_list(axis_vars['years'].get(), int),
            'net_met_policies': _parse_list(axis_vars['net_met_policies'].get()),
            'house_loads': _parse_list(axis_vars['house_loads'].get(), float),
            'pv_sizes': _parse_list(axis_vars['pv_sizes'].get(), float),
            'hes_sizes': _parse_list(axis_vars['hes_sizes'].get(), float),
            'hes_opt_styles': _parse_list(axis_vars['hes_opt_styles'].get()),
            'v2h_limits': _parse_list(axis_vars['v2h_limits'].get(), float),
            'commutes': commutes,
            'charge_schemes': _parse_list(axis_vars['charge_schemes'].get()),
        }

    def _estimate_rows(self, axes: dict, extra_axes: dict) -> int:
        total = 1
        for name, values in {**axes, **extra_axes}.items():
            total *= _axis_len(values, self._DEFAULT_LENS.get(name, 1))
        return total

    # ---------- Single File tab ----------

    def _build_single_tab(self):
        tab = gui_common.make_scrollable(self.single_tab)
        ttk.Label(tab, text='Single Scenario File', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))
        ttk.Label(tab, text='Wraps Setup.generate_input_file -- builds one InputFiles/<title>.xlsx workbook '
                            'covering the full factorial sweep of every axis below (leave an axis blank to '
                            "use generate_input_file's own default for it).", style='Sub.TLabel',
                 wraplength=1000).pack(anchor=W, padx=10)

        basics = gui_common.card(tab, '1. File')
        ttk.Label(basics, text='Title:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        title_var = StringVar()
        ttk.Entry(basics, textvariable=title_var, width=44).grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(basics, text='written to InputFiles/<title>.xlsx', style='Sub.TLabel').grid(
            row=0, column=2, sticky=W, padx=5)

        ttk.Label(basics, text='Zip Codes:', style='Card.TLabel').grid(row=1, column=0, sticky=W, padx=5, pady=4)
        zips_var = StringVar()
        ttk.Entry(basics, textvariable=zips_var, width=44).grid(row=1, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(basics, text='e.g. 30332, 90011 -- comma-separated', style='Sub.TLabel').grid(
            row=1, column=2, sticky=W, padx=5)

        axes_card = gui_common.card(tab, '2. Sweep Axes')
        axis_vars = self._build_axis_fields(axes_card)

        adv_card = gui_common.card(tab, '3. Advanced: Utility/Tariff (optional)')
        ttk.Label(adv_card, text="Leave blank to auto-pick the best utility & tariff for each zip "
                                 '(generate_input_file\'s default and the recommended choice).',
                 style='Sub.TLabel', wraplength=1000).grid(row=0, column=0, columnspan=3, sticky=W)
        ttk.Label(adv_card, text='Utility Files:', style='Card.TLabel').grid(
            row=1, column=0, sticky=W, padx=5, pady=4)
        util_file_var, util_combo, _ = gui_common.make_file_picker(adv_card, UTILITIES_DIR, '*.csv')
        util_combo.grid(row=1, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(adv_card, text='pick one, or type several comma-separated filenames', style='Sub.TLabel').grid(
            row=1, column=2, sticky=W, padx=5)
        ttk.Label(adv_card, text='Tariffs:', style='Card.TLabel').grid(row=2, column=0, sticky=W, padx=5, pady=4)
        tariffs_var = StringVar()
        ttk.Entry(adv_card, textvariable=tariffs_var, width=44).grid(row=2, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(adv_card, text='must match a Name in the chosen utility file(s)', style='Sub.TLabel').grid(
            row=2, column=2, sticky=W, padx=5)

        preview_card = gui_common.card(tab, '4. Preview & Generate')
        preview_label = ttk.Label(preview_card, text='', style='Card.TLabel')
        preview_label.grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 6))

        def do_preview():
            axes = self._read_axes(axis_vars)
            zips = _parse_list(zips_var.get()) or ['(default)']
            n = self._estimate_rows(axes, {'zip_codes': zips})
            preview_label.configure(
                text=f'~{n} scenario rows from the axes above (zip codes x utility/tariff/net-meter '
                     'combinations may multiply this further -- exact utility/tariff resolution '
                     'happens during generation, not here).')

        ttk.Button(preview_card, text='Preview Row Count', command=do_preview).grid(
            row=1, column=0, sticky=W, pady=(0, 8))

        log = gui_common.make_log_box(tab)

        def start_generate(cancel_check, on_finally):
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning('Missing input', 'Enter a title for the file.')
                on_finally()
                return
            zips = _parse_list(zips_var.get())
            if not zips:
                messagebox.showwarning('Missing input', 'Enter at least one zip code.')
                on_finally()
                return
            dest = f'InputFiles/{title}.xlsx'
            if os.path.exists(dest) and not messagebox.askyesno(
                    'File exists', f'{dest} already exists. Overwrite it?'):
                on_finally()
                return

            axes = self._read_axes(axis_vars)
            util_files = _parse_list(util_file_var.get())
            tariffs = _parse_list(tariffs_var.get())

            def work():
                log.log(f'Generating {dest} ...')
                sp.generate_input_file(title=title, zip_codes=zips, util_files=util_files, tariffs=tariffs,
                                       **axes)
                return dest

            log.run(work, on_done=lambda path: log.log(f'Wrote {path}'), on_finally=on_finally)

        gui_common.make_stoppable_action(preview_card, self._active_tokens, 'single_file', 'Generate File',
                                         start_generate).grid(row=1, column=1, sticky=W, padx=(12, 0))

    # ---------- Collection tab ----------

    def _build_collection_tab(self):
        tab = gui_common.make_scrollable(self.collection_tab)
        ttk.Label(tab, text='Scenario Collection', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))
        ttk.Label(tab, text='Wraps Setup.generate_input_collection -- builds one InputFiles/<title>/ folder '
                            'with one F<N>_... workbook per city in the chosen pool CSV, ready for '
                            'Simulation.run_collection.', style='Sub.TLabel', wraplength=1000).pack(
            anchor=W, padx=10)

        basics = gui_common.card(tab, '1. Collection')
        ttk.Label(basics, text='Title:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        title_var = StringVar()
        ttk.Entry(basics, textvariable=title_var, width=44).grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(basics, text='written to InputFiles/<title>/', style='Sub.TLabel').grid(
            row=0, column=2, sticky=W, padx=5)

        pool_card = gui_common.card(tab, '2. City Pool')
        ttk.Label(pool_card, text='Pool CSV:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        pool_var = StringVar()
        ttk.Entry(pool_card, textvariable=pool_var, width=50).grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Button(pool_card, text='Browse...', command=lambda: gui_common.browse_file(
            pool_var, DEFAULT_POOL_DIR if os.path.isdir(DEFAULT_POOL_DIR) else '.',
            (('CSV files', '*.csv'), ('All files', '*.*')))).grid(row=0, column=2, padx=5)

        def do_preview_pool():
            path = pool_var.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showwarning('Missing input', 'Pick a pool CSV first.')
                return
            gui_common.preview_dataframe(self.root, pd.read_csv(path), title=os.path.basename(path))

        ttk.Button(pool_card, text='Preview Pool', command=do_preview_pool).grid(
            row=1, column=1, sticky=W, padx=5, pady=(0, 4))

        sort_var = BooleanVar(value=True)
        ttk.Checkbutton(pool_card, text='Largest population first', variable=sort_var).grid(
            row=2, column=0, columnspan=2, sticky=W, padx=5, pady=(4, 0))
        ttk.Label(pool_card, text='Number of cities:', style='Card.TLabel').grid(
            row=3, column=0, sticky=W, padx=5, pady=4)
        number_var = StringVar()
        ttk.Entry(pool_card, textvariable=number_var, width=10).grid(row=3, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(pool_card, text='blank = every city in the pool', style='Sub.TLabel').grid(
            row=3, column=2, sticky=W, padx=5)

        axes_card = gui_common.card(tab, '3. Sweep Axes (same as Single File, applied to every city)')
        axis_vars = self._build_axis_fields(axes_card)
        ttk.Label(axes_card, text="Commutes: type 'all' to use every driving pattern combination "
                                  "(matches generate_input_collection's 'all' shorthand).",
                 style='Sub.TLabel', wraplength=1000).grid(
            row=len(axis_vars), column=0, columnspan=3, sticky=W, pady=(4, 0))

        preview_card = gui_common.card(tab, '4. Preview & Generate')
        preview_label = ttk.Label(preview_card, text='', style='Card.TLabel')
        preview_label.grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 6))

        def do_preview():
            path = pool_var.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showwarning('Missing input', 'Pick a pool CSV first.')
                return
            n_cities = len(pd.read_csv(path))
            number_text = number_var.get().strip()
            if number_text:
                n_cities = min(n_cities, int(number_text))
            axes = self._read_axes(axis_vars)
            if axis_vars['commutes'].get().strip().lower() == 'all':
                axes['commutes'] = list(range(17))  # generate_input_collection's 'all' shorthand
            per_city = self._estimate_rows(axes, {})
            preview_label.configure(
                text=f'{n_cities} cities x ~{per_city} scenario rows/city = ~{n_cities * per_city} total rows '
                     '(utility/tariff/net-meter combinations may multiply this further).')

        ttk.Button(preview_card, text='Preview Size', command=do_preview).grid(
            row=1, column=0, sticky=W, pady=(0, 8))

        log = gui_common.make_log_box(tab)

        def start_generate(cancel_check, on_finally):
            title = title_var.get().strip()
            pool_path = pool_var.get().strip()
            if not title or not pool_path or not os.path.exists(pool_path):
                messagebox.showwarning('Missing input', 'Enter a title and pick a valid pool CSV.')
                on_finally()
                return
            dest = f'InputFiles/{title}'
            if os.path.isdir(dest) and os.listdir(dest) and not messagebox.askyesno(
                    'Folder exists', f'{dest} already has files in it. Continue and overwrite matching ones?'):
                on_finally()
                return

            axes = self._read_axes(axis_vars)
            if axis_vars['commutes'].get().strip().lower() == 'all':
                # generate_input_collection special-cases the literal string 'all'/'All' (not a
                # parsed list) to mean every driving pattern combination.
                axes['commutes'] = 'all'
            number_text = number_var.get().strip()
            number = int(number_text) if number_text else None
            sort_by_pop = sort_var.get()  # read on the main thread -- Tk variables aren't safe to
                                          # touch from the background thread work() runs on below

            def work():
                log.log(f'Generating collection {dest} ...')
                sp.generate_input_collection(collection_title=title, pool_file=pool_path,
                                             sort_by_pop=sort_by_pop, number=number, **axes)
                return dest

            log.run(work, on_done=lambda path: log.log(f'Collection written to {path}'), on_finally=on_finally)

        gui_common.make_stoppable_action(preview_card, self._active_tokens, 'collection', 'Generate Collection',
                                         start_generate).grid(row=1, column=1, sticky=W, padx=(12, 0))


if __name__ == '__main__':
    root = Tk()
    InputBuilderWizard(root)
    root.mainloop()
