import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

nb_path = Path(r'c:\Users\sayan\OneDrive\Desktop\Projects\03_Market_Research\market-research\DTE0_options\backtest_notebooks\grid_search.ipynb')
cache   = Path(r'c:\Users\sayan\OneDrive\Desktop\Projects\03_Market_Research\market-research\DTE0_options\backtest_notebooks\gs_cache')

with open(nb_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)
cells = nb['cells']
changed = []

def set_source(cell, new_src):
    new_src = new_src.rstrip('\n')
    lines = new_src.split('\n')
    cell['source'] = [l + '\n' for l in lines[:-1]] + [lines[-1]]

# ── Config cell ───────────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'SLIP_PER_UNIT' in src and 'IC_SELL_WIDTH' in src:
            new = src
            new = new.replace(
                'SLIP_PER_UNIT     = 4.0',
                'SLIP_PER_UNIT     = 1.0'
            )
            new = new.replace(
                'IC_SELL_WIDTH = 0   # IC steps from ATM to short legs (0 = sell at ATM for max credit)',
                'IC_SELL_WIDTH = 2   # IC steps from ATM to short legs (2 = sell 100 pts OTM)'
            )
            assert new != src, 'Config: nothing changed'
            set_source(cell, new)
            cell['outputs'] = []
            cell['execution_count'] = None
            changed.append('Config: SLIP_PER_UNIT 4->1, IC_SELL_WIDTH 0->2')
            break

# ── Markdown cell ─────────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'markdown':
        src = ''.join(cell['source'])
        if 'Slip Rs8' in src or 'sell=0' in src:
            new = src
            new = new.replace('Slip Rs8/unit/leg', 'Slip Rs2/unit/leg (round-trip)')
            new = new.replace('sell=0,buy=6 steps', 'sell=2,buy=6 steps')
            set_source(cell, new)
            changed.append('Markdown: slip description + IC sell_width')
            break

# ── T9 unit test ──────────────────────────────────────────────────────────────
for cell in cells:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'T9' in src and 'sell_width=0' in src:
            new = src
            new = new.replace(
                'legs = _ic(25000, 50, lots=1, sell_width=0, buy_width=6)',
                'legs = _ic(25000, 50, lots=1, sell_width=2, buy_width=6)'
            )
            # update the price dict to use the new strikes (100 pts OTM, not ATM)
            old_px = (
                "nc9 = _nc(legs, {(25000,'CE'): 200.0, (25300,'CE'): 50.0,\n"
                "                  (25000,'PE'): 180.0, (24700,'PE'): 45.0})"
            )
            new_px = (
                "nc9 = _nc(legs, {(25100,'CE'): 120.0, (25300,'CE'): 50.0,\n"
                "                  (24900,'PE'): 110.0, (24700,'PE'): 45.0})"
            )
            new = new.replace(old_px, new_px)
            set_source(cell, new)
            cell['outputs'] = []
            cell['execution_count'] = None
            changed.append('T9: sell_width 0->2, price dict updated to OTM strikes')
            break

# ── Clear all code outputs ────────────────────────────────────────────────────
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

# ── Delete IC pkl files ───────────────────────────────────────────────────────
deleted = []
for dte in range(5):
    fp = cache / f'gs_Iron_Condor_DTE{dte}.pkl'
    if fp.exists():
        fp.unlink()
        deleted.append(fp.name)
print(f'Deleted IC caches: {deleted if deleted else "none found"}')
