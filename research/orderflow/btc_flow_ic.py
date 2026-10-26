"""How much does TRUE taker order flow predict BTC returns, at horizons a retail trader can trade, vs fees?"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
def sp(a, b):
    a, b = pd.Series(a).reset_index(drop=True), pd.Series(b).reset_index(drop=True)
    m = a.notna() & b.notna()
    return a[m].rank().corr(b[m].rank())
b = pd.concat(pd.read_parquet(f) for f in sorted(Path(sys.argv[1]).glob("*.parquet"))).sort_index()
b = b[~b.index.duplicated()]
full = pd.date_range(b.index[0], b.index[-1], freq="min"); b = b.reindex(full)
b["close"] = b.close.ffill(); b[["vol", "buy"]] = b[["vol", "buy"]].fillna(0)
b["sell"] = b.vol - b.buy
lr = np.log(b.close)
print(f"bars {len(b):,}  {b.index[0]} -> {b.index[-1]}")
rows = []
for w in (5, 15, 60, 240):
    bv, sv = b.buy.rolling(w).sum(), b.sell.rolling(w).sum()
    imb = (bv - sv) / (bv + sv)
    past = lr - lr.shift(w)  # price change over the same window, to separate flow from momentum
    for h in (5, 15, 60, 240):
        fwd = (lr.shift(-h) - lr) * 1e4  # bps
        step = max(w, h)  # non-overlapping samples
        d = pd.DataFrame({"imb": imb, "past": past, "fwd": fwd}).iloc[::step].dropna()
        d["year"] = d.index.year
        ic = sp(d.imb, d.fwd)
        # flow beyond price: residual of imbalance on the window's own return
        beta = np.polyfit(d.past, d.imb, 1); resid = d.imb - np.polyval(beta, d.past)
        ic_res = sp(resid, d.fwd)
        q = pd.qcut(d.imb, 10, labels=False)
        spread = d.fwd[q == 9].mean() - d.fwd[q == 0].mean()
        by_year = d.groupby("year").apply(lambda g: sp(g.imb, g.fwd))
        rows.append((w, h, len(d), ic, ic_res, spread / 2, d.fwd[q == 9].mean(), d.fwd[q == 0].mean(),
                     " ".join(f"{y}:{v:+.3f}" for y, v in by_year.items())))
print(f"{'win':>4} {'h':>4} {'n':>7} {'IC':>7} {'IC|px':>7} {'edge/side bps':>13} {'top10%':>7} {'bot10%':>7}  IC by year")
for r in rows:
    print(f"{r[0]:>4} {r[1]:>4} {r[2]:>7} {r[3]:+7.3f} {r[4]:+7.3f} {r[5]:13.2f} {r[6]:+7.2f} {r[7]:+7.2f}  {r[8]}")
print("Round-trip taker fee: Binance 0.05%x2 = 10 bps; Delta India 0.05%+GST x2 = 11.8 bps; maker 0.02%x2 = 4 bps")
