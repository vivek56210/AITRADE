"""Download NSE participant-wise OI and trading volume for every F&O trading day into data/participant/."""
import csv, io, sqlite3, sys, time, urllib.request
from datetime import date, timedelta
from pathlib import Path
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
out = Path("data/participant"); out.mkdir(parents=True, exist_ok=True)
days = [r[0] for r in sqlite3.connect("E:/vivek/TradeAI/hist/options.db").execute(
    "select trade_date from days where status='ok' order by 1")]
d = date(2026, 9, 8)
while d <= date(2026, 10, 23):
    if d.weekday() < 5: days.append(d.isoformat())
    d += timedelta(days=1)
for kind in ("oi", "vol"):
    for ds in days:
        p = out / f"{kind}_{ds}.csv"
        if p.exists(): continue
        y, m, dd = ds.split("-")
        url = f"https://nsearchives.nseindia.com/content/nsccl/fao_participant_{kind}_{dd}{m}{y}.csv"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                    p.write_bytes(r.read()); break
            except urllib.error.HTTPError as e:
                if e.code == 404: p.with_suffix(".missing").write_text(""); break
                time.sleep(2 ** attempt)
            except Exception:
                time.sleep(2 ** attempt)
        time.sleep(0.15)
    print(kind, "done", len(list(out.glob(f"{kind}_*.csv"))), flush=True)
