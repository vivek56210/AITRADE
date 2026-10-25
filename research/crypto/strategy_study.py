"""Crypto strategy study: 7 pre-registered strategies on BTC/ETH, hourly execution, Delta India costs.

IS 2018-01-01 .. 2022-12-31 (selection), OOS 2023-01-01 .. 2026-10-23 (confirmation).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/crypto")
TAKER = 0.0005 * 1.18 + 0.0002   # fee incl GST + slippage, per side
MAKER = 0.0002 * 1.18
DEFAULT_FUNDING = 0.0001          # per 8h, before Binance perp history starts (longs pay)
RISK = 0.01                       # equity risked per stop-based trade
TARGET_VOL = 0.20
MAX_LEV = 2.0


def load(sym):
    cols = ["ot", "open", "high", "low", "close", "vol", "ct", "qv", "n", "tbv", "tbq", "x"]
    fr = []
    for p in sorted((ROOT / "spot1h" / sym).glob("*.csv")):
        t = pd.read_csv(p, header=None, names=cols)
        t = t[pd.to_numeric(t.ot, errors="coerce").notna()]
        fr.append(t)
    h = pd.concat(fr)
    ot = h.ot.astype("int64")
    ot = np.where(ot > 10 ** 14, ot // 1000, ot)  # 2025+ archives are in microseconds
    h.index = pd.to_datetime(ot, unit="ms", utc=True)
    h = h[["open", "high", "low", "close", "vol", "tbv"]].astype(float)
    h = h[~h.index.duplicated()].sort_index()
    f = []
    for p in sorted((ROOT / "funding" / sym).glob("*.csv")):
        t = pd.read_csv(p)
        t.columns = [c.strip() for c in t.columns]
        f.append(t)
    f = pd.concat(f)
    tcol = [c for c in f.columns if "time" in c.lower()][0]
    rcol = [c for c in f.columns if "rate" in c.lower()][0]
    fund = pd.Series(f[rcol].astype(float).values, index=pd.to_datetime(f[tcol].astype("int64"), unit="ms", utc=True))
    fund = fund.sort_index()
    fund.index = fund.index.floor("h")
    fund = fund[~fund.index.duplicated()]
    return h, fund


def composite_profile(h, days=20, bins=120, va=0.70):
    """Per UTC day: POC/VAH/VAL of the volume profile over the last `days` days of hourly bars."""
    day = h.index.floor("D")
    udays = day.unique()
    lo, hi, vol = h.low.values, h.high.values, h.vol.values
    pos = np.searchsorted(day.values, udays.values)
    out = {}
    for i in range(days - 1, len(udays)):
        a, b = pos[i - days + 1], (pos[i + 1] if i + 1 < len(udays) else len(h))
        l, u, v = lo[a:b], hi[a:b], vol[a:b]
        pmin, pmax = l.min(), u.max()
        step = (pmax - pmin) / bins or 1.0
        prof = np.zeros(bins)
        i0 = np.clip(((l - pmin) / step).astype(int), 0, bins - 1)
        i1 = np.clip(((u - pmin) / step).astype(int), 0, bins - 1)
        for s, e, w in zip(i0, i1, v):
            prof[s:e + 1] += w / (e - s + 1)
        poc = int(prof.argmax())
        lo_i = hi_i = poc
        tot, acc = prof.sum(), prof[poc]
        while acc < va * tot and (lo_i > 0 or hi_i < bins - 1):
            up = prof[hi_i + 1] if hi_i < bins - 1 else -1
            dn = prof[lo_i - 1] if lo_i > 0 else -1
            if up >= dn:
                hi_i += 1; acc += up
            else:
                lo_i -= 1; acc += dn
        out[udays[i]] = (pmin + (poc + 0.5) * step, pmin + (hi_i + 1) * step, pmin + lo_i * step)
    return pd.DataFrame.from_dict(out, orient="index", columns=["poc", "vah", "val"])


def daily_features(h):
    d = h.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}).dropna()
    r = np.log(d.close).diff()
    d["vol30"] = r.rolling(30).std() * np.sqrt(365)
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(20).mean()
    for L in (20, 60, 120):
        d[f"m{L}"] = np.sign(d.close / d.close.shift(L) - 1)
    d["tsmom"] = d[["m20", "m60", "m120"]].mean(axis=1)
    d["ema100"] = d.close.ewm(span=100, adjust=False).mean()
    # channels end yesterday, so today's close can break them
    d["hh20"], d["ll20"] = d.high.rolling(20).max().shift(1), d.low.rolling(20).min().shift(1)
    d["hh10"], d["ll10"] = d.high.rolling(10).max().shift(1), d.low.rolling(10).min().shift(1)
    vp = composite_profile(h)
    d = d.join(vp)
    d["poc_prev5"] = d.poc.shift(5)
    d["va_width"] = (d.vah - d.val) / d.close
    d["va_width_med"] = d.va_width.rolling(120).median()
    return d


# ---- strategies: decide(t, d, row, state) at the close of day t -> order dict --------------------
# order keys: target (signed fraction of equity notional, or None = unchanged), stop, limit (pending
# limit entry with target), exit_now

def vol_size(row, frac=1.0):
    v = row.vol30 if row.vol30 and row.vol30 > 0 else 1.0
    return float(np.clip(TARGET_VOL / v, 0, MAX_LEV)) * frac


def risk_size(entry, stop, eq_unused=None):
    dist = abs(entry - stop) / entry
    return float(min(RISK / dist, MAX_LEV)) if dist > 0 else 0.0


def s1(row, st, long_only=False):
    sig = row.tsmom
    if long_only:
        sig = max(sig, 0.0)
    tgt = np.sign(sig) * vol_size(row, abs(sig))
    return {"target": tgt, "band": 0.25}


def s1l(row, st):
    return s1(row, st, long_only=True)


def s2(row, st):
    p = st["pos"]
    if p == 0:
        if row.close >= row.hh20:
            stop = row.close - 2 * row.atr
            return {"target": risk_size(row.close, stop), "stop": stop}
        if row.close <= row.ll20:
            stop = row.close + 2 * row.atr
            return {"target": -risk_size(row.close, stop), "stop": stop}
        return {}
    if p > 0 and row.close <= row.ll10:
        return {"target": 0.0}
    if p < 0 and row.close >= row.hh10:
        return {"target": 0.0}
    return {}


def s3(row, st):
    return {"target": vol_size(row) if row.close > row.ema100 else 0.0, "band": 0.25}


def s4(row, st):
    p = st["pos"]
    up, dn = row.poc > row.poc_prev5, row.poc < row.poc_prev5
    if p == 0:
        if row.close > row.vah and up:
            return {"target": risk_size(row.close, row.poc), "stop": row.poc}
        if row.close < row.val and dn:
            return {"target": -risk_size(row.close, row.poc), "stop": row.poc}
        return {}
    if p > 0 and row.close < row.poc:
        return {"target": 0.0}
    if p < 0 and row.close > row.poc:
        return {"target": 0.0}
    return {}


def s5(row, st):
    """Balance fade: narrow value + no migration; yesterday outside value, today closed back inside."""
    p = st["pos"]
    prev = st.get("prev")
    st["prev"] = row
    if p != 0:
        hit = (p > 0 and row.close >= st["tp"]) or (p < 0 and row.close <= st["tp"])
        return {"target": 0.0} if hit or st["held"] >= 5 else {}
    if prev is None or not (row.va_width < row.va_width_med) or abs(row.poc / row.poc_prev5 - 1) > 0.01:
        return {}
    if prev.close < prev.val and row.val <= row.close < row.poc:
        stop = min(prev.low, row.low) - 0.25 * row.atr
        st["tp"] = row.poc
        return {"target": risk_size(row.close, stop), "stop": stop}
    if prev.close > prev.vah and row.poc < row.close <= row.vah:
        stop = max(prev.high, row.high) + 0.25 * row.atr
        st["tp"] = row.poc
        return {"target": -risk_size(row.close, stop), "stop": stop}
    return {}


def s6(row, st):
    """Trend (all three lookbacks agree) + buy the pullback to composite POC with a resting limit."""
    p = st["pos"]
    trend = row.tsmom
    if p != 0:
        if (p > 0 and trend <= 0) or (p < 0 and trend >= 0):
            return {"target": 0.0}
        return {}
    if trend == 1 and row.close > row.poc:
        stop = row.val - 0.5 * row.atr
        if stop < row.poc:
            return {"limit": row.poc, "target": risk_size(row.poc, stop), "stop": stop}
    if trend == -1 and row.close < row.poc:
        stop = row.vah + 0.5 * row.atr
        if stop > row.poc:
            return {"limit": row.poc, "target": -risk_size(row.poc, stop), "stop": stop}
    return {"cancel": True}


def s7(row, st):
    """S1L with volume profile as a risk throttle: half size while price is accepted below the 20-day POC."""
    o = s1(row, st, long_only=True)
    if o["target"] > 0 and row.close < row.poc:
        o["target"] *= 0.5
    return o


STRATS = {"S1": s1, "S1L": s1l, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6, "S7": s7}


def run(h, d, fund, strat):
    """Hourly event loop. Decisions at each UTC day close; fills at the next hour's open.

    Equity is marked from `mark` (the last price the position was valued at), so a fill is valued
    from its own fill price.
    """
    eq, qty, stop, pend, mark = 1.0, 0.0, None, None, None
    st = {"pos": 0, "held": 0}
    trades, curve = [], []
    entry_eq = None
    days = d.index
    dec_at = {days[i + 1]: t for i, t in enumerate(days[:-1])}
    fidx = fund.reindex(h.index).values
    hv = h[["open", "high", "low", "close"]].values

    def close_trade():
        trades.append(eq / entry_eq - 1)

    for k, ts in enumerate(h.index):
        o, hi, lo, c = hv[k]
        if qty != 0:  # value the position at this hour's open first
            eq += qty * (o - mark); mark = o
        if ts in dec_at:
            row = d.loc[dec_at[ts]]
            ready = not (np.isnan(row.poc) or np.isnan(row.vol30) or np.isnan(row.tsmom) or np.isnan(row.atr))
            st["pos"] = int(np.sign(qty))
            st["held"] = st["held"] + 1 if qty else 0
            order = strat(row, st) if ready else {}
            if order.get("cancel"):
                pend = None
            if "limit" in order:
                pend = order if qty == 0 else None
            elif "target" in order:
                tgt = order["target"]
                cur = qty * o / eq if eq > 0 else 0.0
                band = order.get("band", 0.0)
                if (tgt == 0 and qty != 0) or (tgt != 0 and (np.sign(tgt) != np.sign(cur) or abs(tgt - cur) > band * abs(cur))):
                    new_qty = tgt * eq / o
                    eq -= abs(new_qty - qty) * o * TAKER
                    if qty != 0 and (new_qty == 0 or np.sign(new_qty) != np.sign(qty)):
                        close_trade()
                    if new_qty != 0 and (qty == 0 or np.sign(new_qty) != np.sign(qty)):
                        entry_eq = eq
                    qty, mark = new_qty, o
                    stop = order.get("stop") if new_qty != 0 else None
                    if new_qty != 0 and "stop" not in order and np.sign(new_qty) == np.sign(cur):
                        pass
        if pend is not None and qty == 0:
            lim = pend["limit"]
            if (pend["target"] > 0 and lo < lim) or (pend["target"] < 0 and hi > lim):
                px = min(o, lim) if pend["target"] > 0 else max(o, lim)
                qty = pend["target"] * eq / px
                eq -= abs(qty) * px * MAKER
                entry_eq, mark = eq, px
                stop, pend = pend["stop"], None
        if qty != 0 and stop is not None and ((qty > 0 and lo <= stop) or (qty < 0 and hi >= stop)):
            px = min(o, stop) if qty > 0 else max(o, stop)
            eq += qty * (px - mark)
            eq -= abs(qty) * px * TAKER
            close_trade()
            qty, stop, mark = 0.0, None, None
        if qty != 0:
            eq += qty * (c - mark); mark = c
            if ts.hour % 8 == 0:
                r = fidx[k]
                eq -= qty * o * (DEFAULT_FUNDING if np.isnan(r) else r)
        curve.append(eq)
        if eq <= 0:
            break
    return pd.Series(curve, index=h.index[:len(curve)]), trades


def stats(eq, trades, a, b):
    e = eq.loc[a:b]
    if len(e) < 100:
        return None
    dly = e.resample("1D").last().dropna()
    r = dly.pct_change().dropna()
    yrs = (dly.index[-1] - dly.index[0]).days / 365.25
    cagr = (dly.iloc[-1] / dly.iloc[0]) ** (1 / yrs) - 1
    dd = (dly / dly.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0
    yr = dly.resample("YE").last().pct_change()
    yr.iloc[0] = dly.resample("YE").last().iloc[0] / dly.iloc[0] - 1
    return {"cagr": cagr, "maxdd": dd, "sharpe": sharpe, "yrs": " ".join(f"{i.year}:{v:+.0%}" for i, v in yr.items())}


if __name__ == "__main__":
    res = []
    for sym in ("BTCUSDT", "ETHUSDT"):
        h, fund = load(sym)
        h = h.loc["2017-09-01":]
        d = daily_features(h)
        bh = (h.close / h.close.loc["2018-01-01":].iloc[0])
        names = sys.argv[2].split(",") if len(sys.argv) > 2 else ["BH"] + list(STRATS)
        for name in names:
            if name == "BH":
                eq, tr = bh, []
            else:
                eq, tr = run(h, d, fund, STRATS[name])
            eq.to_frame("eq").to_parquet(ROOT.parent / f"eq_{sym}_{name}.parquet")
            for w, a, b in (("IS", "2018-01-01", "2022-12-31"), ("OOS", "2023-01-01", "2026-10-31")):
                s = stats(eq, tr, a, b)
                n = len(tr)
                res.append({"sym": sym[:3], "strat": name, "win": w, **(s or {}), "trades_total": n,
                            "trade_win": (np.mean([x > 0 for x in tr]) if tr else np.nan)})
            print(sym, name, "done", flush=True)
    r = pd.DataFrame(res)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    print(r.round(3).to_string(index=False))
    r.to_csv(ROOT.parent / "crypto_study.csv", index=False)
