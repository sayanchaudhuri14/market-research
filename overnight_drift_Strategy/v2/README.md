# Overnight Drift — v2 (CLOSED)

**Status: Research artifact only. Strategy was closed April 2026.**
**See `../RESEARCH_SUMMARY.md` for the full post-mortem.**

---

## Files

| File | Purpose |
|------|---------|
| `backtest.ipynb` | Full historical backtest (2019–2026). No filter. Correct costs. Run to reproduce final numbers. |
| `daily_signal.ipynb` | Signal generator — kept for reference only. Not for live use. |

## Final numbers (2019–2026, no filter)

- Gross mean return per session: **+0.2029%**
- PCT cost alone (STT both sides): **0.2225%**
- Net: **negative at any capital level**

## Why it was closed

STT on equity delivery is 0.10% on both buy and sell sides — 0.20% round-trip.
The entire overnight drift edge is consumed by STT alone. Not fixable within equity delivery.
