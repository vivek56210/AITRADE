import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); from participant_load import load, daily
S = sys.argv[1]
oi = load("oi")
idx = pd.to_datetime(oi.index)
cchg = pd.Series(((oi[("fut_idx_long", "Client")] - oi[("fut_idx_short", "Client")]).diff()).values, index=idx)
COST = 0.042
sigs = {}
for sym in ("NIFTY", "BANKNIFTY"):
    px = daily(sym, S); px.index = pd.to_datetime(px.index); px = px.reindex(idx)
    ret0 = px.close.pct_change() * 100
    fwd = (px.close.shift(-1) / px.open.shift(-1) - 1) * 100
    # residual of retail flow after today's return, fitted on a trailing 250-day window only (no look-ahead)
    res = pd.Series(np.nan, index=idx)
    r_c, r_r = cchg.rank(pct=True), ret0
    for i in range(250, len(idx)):
        w = slice(i - 250, i + 1)
        a, b = ret0.iloc[w].values, cchg.iloc[w].values
        m = ~(np.isnan(a) | np.isnan(b))
        if m.sum() < 120: continue
        beta = np.polyfit(a[m], b[m], 1)
        z = b[m] - np.polyval(beta, a[m])
        res.iloc[i] = (cchg.iloc[i] - np.polyval(beta, ret0.iloc[i])) / z.std()
    sig = -np.sign(res)  # fade retail flow beyond what the day's move explains
    sigs[sym] = res
    for thr in (0.0, 1.0):
        s = sig.where(res.abs() > thr, 0)
        for a, b, w in [("2018-04-01", "2022-12-31", "IS "), ("2023-01-01", "2026-10-31", "OOS")]:
            d = pd.DataFrame({"s": s, "f": fwd}).loc[a:b].dropna(); d = d[d.s != 0]
            p = d.s * d.f - COST
            yrs = d.index.year
            by = p.groupby(yrs).sum().round(1).to_dict()
            print(f"{sym:<9} |z|>{thr:.0f} {w} n={len(p):4d} net/trade={p.mean():+.3f}% total={p.sum():+6.1f}% t={p.mean()/p.std()*np.sqrt(len(p)):+.2f} win={(p>0).mean():.2f} by-year={by}")
pd.DataFrame(sigs).to_csv(f"{S}/retail_resid.csv")
