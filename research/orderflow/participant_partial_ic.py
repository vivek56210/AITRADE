import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); from participant_load import load, daily
S = sys.argv[1]
oi, vol = load("oi"), load("vol")
x = pd.DataFrame(index=pd.to_datetime(oi.index))
x["fii_fut_chg"] = ((oi[("fut_idx_long", "FII")] - oi[("fut_idx_short", "FII")]).diff()).values
x["fii_fut_vol"] = (vol[("fut_idx_long", "FII")] - vol[("fut_idx_short", "FII")]).values
x["client_fut_chg"] = ((oi[("fut_idx_long", "Client")] - oi[("fut_idx_short", "Client")]).diff()).values
x["pro_fut_chg"] = ((oi[("fut_idx_long", "Pro")] - oi[("fut_idx_short", "Pro")]).diff()).values
rk = lambda s: s.rank()
for sym in ("NIFTY", "BANKNIFTY"):
    px = daily(sym, S); px.index = pd.to_datetime(px.index); px = px.reindex(x.index)
    d = x.copy()
    d["ret0"] = px.close.pct_change() * 100          # same-day return (known at signal time)
    d["fwd1"] = (px.close.shift(-1) / px.open.shift(-1) - 1) * 100  # next-day open->close
    d["gap1"] = (px.open.shift(-1) / px.close - 1) * 100  # overnight gap (not tradable on the signal)
    print(f"== {sym}")
    for a, b, w in [("2017-04-01", "2022-12-31", "IS "), ("2023-01-01", "2026-10-31", "OOS")]:
        e = d.loc[a:b].dropna()
        line = [f"{w} same-day corr(flow, ret0):"]
        for c in ("fii_fut_chg", "fii_fut_vol", "client_fut_chg", "pro_fut_chg"):
            line.append(f"{c}={rk(e[c]).corr(rk(e.ret0)):+.2f}")
        print(" ".join(line))
        line = [f"{w} next-day IC  raw / partial(after ret0):  ret0->fwd1={rk(e.ret0).corr(rk(e.fwd1)):+.3f}"]
        for c in ("fii_fut_chg", "fii_fut_vol", "client_fut_chg", "pro_fut_chg"):
            beta = np.polyfit(rk(e.ret0), rk(e[c]), 1); res = rk(e[c]) - np.polyval(beta, rk(e.ret0))
            line.append(f"{c}={rk(e[c]).corr(rk(e.fwd1)):+.3f}/{res.corr(rk(e.fwd1)):+.3f}")
        print(" ".join(line))
        print(f"{w} gap IC (overnight, untradeable): fii_fut_vol={rk(e.fii_fut_vol).corr(rk(e.gap1)):+.3f}")
