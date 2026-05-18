import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

nb_path = Path(r'c:\Users\sayan\OneDrive\Desktop\Projects\03_Market_Research\market-research\DTE0_options\backtest_notebooks\grid_search.ipynb')
cache   = Path(r'c:\Users\sayan\OneDrive\Desktop\Projects\03_Market_Research\market-research\DTE0_options\backtest_notebooks\gs_cache')

with open(nb_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)
cells  = nb['cells']
changed = []

def set_source(cell, new_src):
    new_src = new_src.rstrip('\n')
    lines   = new_src.split('\n')
    cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]]

# ── Cell 0: markdown ──────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'markdown':
        src = ''.join(cell['source'])
        if 'Strip, Long Straddle' in src:
            new_src = src.replace(
                'Bear Call Spread, Bull Put Spread, Batman, Strip, Long Straddle',
                'Bear Call Spread, Bull Put Spread, Batman, Iron Condor'
            ).replace(
                'handles NSE Thu->Tue expiry change from 2025-09-02)',
                'handles NSE Thu->Tue expiry change from 2025-09-02) '
                '· Strip/Straddle removed '
                '· Batman wings widened (mid=3,outer=6,far=10) '
                '· Iron Condor added (sell=0,buy=6 steps)'
            )
            set_source(cell, new_src)
            changed.append('Cell 0 markdown: strategies updated')
            break

# ── Cell 1: Config ────────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'BAT_MID_W' in src and "'Strip'" in src:
            new_src = src
            new_src = new_src.replace('BAT_MID_W   = 1', 'BAT_MID_W   = 3')
            new_src = new_src.replace('BAT_OUTER_W = 3', 'BAT_OUTER_W = 6')
            new_src = new_src.replace('BAT_FAR_W   = 6', 'BAT_FAR_W   = 10')
            new_src = new_src.replace(
                'BAT_FAR_W   = 10\n',
                'BAT_FAR_W   = 10\n'
                'IC_SELL_WIDTH = 0   # IC steps from ATM to short legs (0 = sell at ATM for max credit)\n'
                'IC_BUY_WIDTH  = 6   # IC steps from ATM to wing legs (= 300 pts)\n'
            )
            # SPAN
            new_src = new_src.replace(
                "    'Batman':           90_000, 'Strip':           25_000, 'Long Straddle': 20_000,",
                "    'Batman':           90_000, 'Iron Condor':     25_000,"
            )
            # MAX_LOTS
            new_src = new_src.replace(
                "    'Batman':           1, 'Strip':           5, 'Long Straddle': 5,",
                "    'Batman':           1, 'Iron Condor':     5,"
            )
            set_source(cell, new_src)
            changed.append('Cell 1 Config: Batman widths 1/3/6->3/6/10, IC params, SPAN/MAX_LOTS')
            break

# ── Cell 2: Unit tests — add T9 ───────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'ALL 8 TESTS PASSED' in src and '_ic' not in src:
            t9_block = (
                "\n"
                "# T9 -- Iron Condor net credit is positive\n"
                "from strategies.iron_condor import get_legs as _ic\n"
                "legs = _ic(25000, 50, lots=1, sell_width=0, buy_width=6)\n"
                "nc9 = _nc(legs, {(25000,'CE'): 200.0, (25300,'CE'): 50.0,\n"
                "                  (25000,'PE'): 180.0, (24700,'PE'): 45.0})\n"
                "assert nc9 > 0, 'T9 FAIL: IC nc must be positive, got ' + str(nc9)\n"
                "print(f'T9 PASS  IC nc = +{nc9:.0f}  (credit -> positive)')\n"
            )
            new_src = src.replace(
                "\nprint()\nprint('ALL 8 TESTS PASSED -- safe to run grid search')",
                t9_block + "\nprint()\nprint('ALL 9 TESTS PASSED -- safe to run grid search')"
            )
            set_source(cell, new_src)
            changed.append('Cell 2 Unit tests: T9 added (IC nc > 0), count -> 9')
            break

# ── Cell 3: Imports + STRATS ──────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'strip_mod' in src and 'STRATS' in src:
            new_src = src.replace(
                "import strategies.strip            as strip_mod\n"
                "import strategies.long_straddle    as straddle_mod",
                "import strategies.iron_condor      as ic_mod"
            ).replace(
                "STRATS = {\n"
                "    'Bear Call Spread': bcs_mod,\n"
                "    'Bull Put Spread':  bps_mod,\n"
                "    'Batman':           batman_mod,\n"
                "    'Strip':            strip_mod,\n"
                "    'Long Straddle':    straddle_mod,\n"
                "}",
                "STRATS = {\n"
                "    'Bear Call Spread': bcs_mod,\n"
                "    'Bull Put Spread':  bps_mod,\n"
                "    'Batman':           batman_mod,\n"
                "    'Iron Condor':      ic_mod,\n"
                "}"
            )
            set_source(cell, new_src)
            changed.append('Cell 3 Imports: strip/straddle removed, ic_mod added, STRATS updated')
            break

# ── Cell 6: make_legs — add IC case ──────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'def make_legs' in src and 'IC_SELL_WIDTH' not in src:
            new_src = src.replace(
                "    return mod.get_legs(atm, STRIKE_STEP, lots=1)",
                "    if sname == 'Iron Condor':\n"
                "        return mod.get_legs(atm, STRIKE_STEP, lots=1,\n"
                "                            sell_width=IC_SELL_WIDTH, buy_width=IC_BUY_WIDTH)\n"
                "    return mod.get_legs(atm, STRIKE_STEP, lots=1)"
            )
            set_source(cell, new_src)
            changed.append('Cell 6 make_legs: Iron Condor case added')
            break

# ── Clear outputs ─────────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        cell['outputs'] = []
        cell['execution_count'] = None
changed.append('All outputs cleared')

with open(nb_path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print('Notebook patched.')
for c in changed:
    print(f'  + {c}')

# ── Delete stale Batman pkl files ─────────────────────────────────────────────
deleted = []
for dte in range(5):
    fp = cache / f'gs_Batman_DTE{dte}.pkl'
    if fp.exists():
        fp.unlink()
        deleted.append(fp.name)
print(f'\nDeleted stale Batman caches: {deleted if deleted else "none found"}')
