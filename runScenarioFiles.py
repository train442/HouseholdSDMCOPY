"""
Summary
-------
DEPRECATED. This module is retained only as a thin shim over Simulation.py.

It previously carried its own copies of twelve constructor functions -- make_ev, make_timekeep,
rows_match, get_reset_dict, make_city, make_tariff, make_house, make_grid, make_pv, make_fleet,
get_baseline and check_resolution -- duplicated from Simulation.py. Nothing imported it, the copies had
drifted from the originals, and they carried a bug in rows_match (it compared a row against itself
rather than against the previous row) that was fixed in Simulation.py but would have survived here.

The live entry point is main.py -> Simulation.run_model. The names below are re-exported so any old
script that imported from this module keeps working, but they now resolve to the single maintained
implementation in Simulation.py.

An annotated copy of the original 629-line file is preserved for reference at
Obsolete/Optimization_Review_2026-08-09/runScenarioFiles_PRE_OPTIMIZATION.py.
"""
import warnings

import Simulation as sm
# Re-exported for backwards compatibility. These are Simulation.py's implementations, not copies.
from Simulation import (check_resolution, get_baseline, get_reset_dict, make_city, make_ev, make_fleet,
                        make_grid, make_house, make_pv, make_tariff, make_timekeep, rows_match,
                        run_collection, run_model, run_simulation)

# Declares the re-exports as this module's public surface, so linters stop reporting them as unused
# imports and "from runScenarioFiles import *" keeps behaving as it always did.
__all__ = ['check_resolution', 'get_baseline', 'get_reset_dict', 'make_city', 'make_ev', 'make_fleet',
           'make_grid', 'make_house', 'make_pv', 'make_tariff', 'make_timekeep', 'rows_match',
           'run_collection', 'run_model', 'run_simulation', 'save_loads', 'overwrite_scenarios']

warnings.simplefilter(action='ignore', category=FutureWarning)

save_loads = False
overwrite_scenarios = False  # Set to True if you wish to overwrite runs.


if __name__ == '__main__':
    # Preserved behaviour: prompt for an input file and a run name, then run it.
    sm.run_model()
