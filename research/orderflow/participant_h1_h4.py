"""Pre-registered tests H1-H4 of NSE participant positioning vs next-day-open-to-close-of-day-h index returns."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
def sp(a, b):
    return a.rank().corr(b.rank())
sys.path.insert(0, str(Path(__file__).parent)); from participant_load import load, daily
S = sys.argv[1]
oi = load("oi"); vol = load("vol")
f = pd.DataFrame(index=oi.index)
fl, fs = oi[("fut_idx_long", "FII")], oi[("fut_idx_short", "FII")]
f["H1_fii_fut_net_chg"] = (fl - fs).diff()
cl, cs = oi[("fut_idx_long", "Client")], oi[("fut_idx_short", "Client")]
cnet = cl - cs
f["H2_client_net_z_contra"] = -(cnet - cnet.rolling(250, min_periods=120).mean()) / cnet.rolling(250, min_periods=120).std()
f["H3_fii_long_ratio"] = fl / (fl + fs)
opt = (oi[("opt_idx_call_long", "FII")] - oi[("opt_idx_call_short", "FII")]) - (oi[("opt_idx_put_long", "FII")] - oi[("opt_idx_put_short", "FII")])
f["H4_fii_opt_net_chg"] = opt.diff()
f["H1b_fii_fut_vol_net"] = vol[("fut_idx_long", "FII")] - vol[("fut_idx_short", "FII")]
f.index = pd.to_datetime(f.index)
WIN = [("IS 2017-04..2022-12", "2017-04-01", "2022-12-31"), ("OOS 2023-01..2026-10", "2023-01-01", "2026-10-31")]
COST = 0.042  # % round trip, ~10 index points on NIFTY futures
out = []
for sym in ("NIFTY", "BANKNIFTY"):
    px = daily(sym, S); px.index = pd.to_datetime(px.index)
    px = px.reindex(f.index.union(px.index)).loc[f.index.min():]
    for h in (1, 3, 5):
        # signal known after close of t -> enter open t+1, exit close t+h
        fwd = (px.close.shift(-h) / px.open.shift(-1) - 1) * 100
        for col in f.columns:
            x = f[col]
            if col.startswith("H3"):  # bucket rule: <0.25 long, >0.75 short, else flat
                sig = pd.Series(np.where(x < 0.25, 1, np.where(x > 0.75, -1, 0)), index=x.index)
            else:
                sig = np.sign(x)
            for wname, a, b in WIN:
                d = pd.DataFrame({"x": x, "sig": sig, "fwd": fwd}).loc[a:b].dropna()
                d = d.iloc[::h]  # non-overlapping
                ic = sp(d.x, d.fwd) * (1 if not col.startswith("H3") else -1)
                pnl = d.sig * d.fwd - COST * (d.sig != 0)
                act = pnl[d.sig != 0]
                t = act.mean() / act.std() * np.sqrt(len(act)) if len(act) > 2 else np.nan
                out.append((sym, h, col, wname, len(act), ic, act.mean(), act.sum(), t, (act > 0).mean()))
r = pd.DataFrame(out, columns=["sym", "h", "signal", "window", "trades", "IC", "net%/trade", "net% total", "t", "win"])
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
print(r.round(3).to_string(index=False))
r.to_csv(f"{S}/part_results.csv", index=False)
