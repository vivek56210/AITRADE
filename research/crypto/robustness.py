"""Robustness of the trend family: portfolio, parameter plateau, cost stress, monthly consistency."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, sys.argv[2])
import strategy_study as cs

ROOT = sys.argv[1]
cs.ROOT = __import__("pathlib").Path(ROOT)
data = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    h, fund = cs.load(sym)
    h = h.loc["2017-09-01":]
    data[sym] = (h, fund)


def feats(h, lbs):
    d = cs.daily_features(h)
    for L in lbs:
        d[f"x{L}"] = np.sign(d.close / d.close.shift(L) - 1)
    d["tsmom"] = d[[f"x{L}" for L in lbs]].mean(axis=1)
    return d


def summary(eq_by_sym, label):
    rets = pd.concat({k: v.resample("1D").last().pct_change() for k, v in eq_by_sym.items()}, axis=1).dropna()
    port = (1 + rets.mean(axis=1)).cumprod()
    out = {"cfg": label}
    for w, a, b in (("IS", "2018-01-01", "2022-12-31"), ("OOS", "2023-01-01", "2026-10-31"), ("ALL", "2018-01-01", "2026-10-31")):
        p = port.loc[a:b]; r = p.pct_change().dropna()
        yrs = (p.index[-1] - p.index[0]).days / 365.25
        out[f"{w}_cagr"] = (p.iloc[-1] / p.iloc[0]) ** (1 / yrs) - 1
        out[f"{w}_sharpe"] = r.mean() / r.std() * np.sqrt(365)
        out[f"{w}_dd"] = (p / p.cummax() - 1).min()
    p = port.loc["2018-01-01":]
    m = p.resample("ME").last().pct_change().dropna()
    y = p.resample("YE").last().pct_change().dropna()
    out["pos_months"] = (m > 0).mean(); out["worst_month"] = m.min(); out["pos_years"] = f"{(y > 0).sum()}/{len(y)}"
    under = p / p.cummax() < 1
    runs = (under != under.shift()).cumsum()[under]
    out["longest_dd_days"] = int(runs.value_counts().max()) if len(runs) else 0
    out["years"] = " ".join(f"{i.year}:{v:+.0%}" for i, v in y.items())
    return out, port


rows = []
base_lbs = (20, 60, 120)
configs = [
    ("S1L base 20/60/120 vol20 band25", cs.s1l, base_lbs, {}),
    ("S1 L/S base", cs.s1, base_lbs, {}),
    ("S1L lookbacks 10/30/90", cs.s1l, (10, 30, 90), {}),
    ("S1L lookbacks 30/90/180", cs.s1l, (30, 90, 180), {}),
    ("S1L lookbacks 20/60/120/250", cs.s1l, (20, 60, 120, 250), {}),
    ("S1L target vol 15%", cs.s1l, base_lbs, {"TARGET_VOL": 0.15}),
    ("S1L target vol 30%", cs.s1l, base_lbs, {"TARGET_VOL": 0.30}),
    ("S1L band 10%", cs.s1l, base_lbs, {"BAND": 0.10}),
    ("S1L band 50%", cs.s1l, base_lbs, {"BAND": 0.50}),
    ("S1L costs x2", cs.s1l, base_lbs, {"TAKER": 2 * cs.TAKER}),
    ("S1L costs x3", cs.s1l, base_lbs, {"TAKER": 3 * cs.TAKER}),
]
defaults = {"TARGET_VOL": cs.TARGET_VOL, "TAKER": cs.TAKER}
feat_cache = {}
for label, fn, lbs, over in configs:
    for k, v in defaults.items():
        setattr(cs, k, v)
    for k, v in over.items():
        if k != "BAND":
            setattr(cs, k, v)
    band = over.get("BAND")
    strat = fn if band is None else (lambda row, st, fn=fn, band=band: {**fn(row, st), "band": band})
    eqs = {}
    for sym, (h, fund) in data.items():
        key = (sym, lbs)
        if key not in feat_cache:
            feat_cache[key] = feats(h, lbs)
        eq, _ = cs.run(h, feat_cache[key], fund, strat)
        eqs[sym] = eq
    s, port = summary(eqs, label)
    rows.append(s)
    if label.startswith("S1L base"):
        port.to_frame("eq").to_parquet(f"{ROOT}/../port_S1L.parquet")
    print(label, "done", file=sys.stderr, flush=True)
r = pd.DataFrame(rows)
pd.set_option("display.width", 300); pd.set_option("display.max_colwidth", 200)
print(r.drop(columns=["years"]).round(3).to_string(index=False))
print()
for _, x in r.iterrows():
    print(f"{x.cfg:<32} {x.years}")
