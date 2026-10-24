"""Parse NSE participant-wise OI / volume CSVs into one daily table."""
import csv, io, json
from pathlib import Path
import pandas as pd
COLS = ["fut_idx_long", "fut_idx_short", "fut_stk_long", "fut_stk_short", "opt_idx_call_long", "opt_idx_put_long",
        "opt_idx_call_short", "opt_idx_put_short", "opt_stk_call_long", "opt_stk_put_long", "opt_stk_call_short",
        "opt_stk_put_short", "total_long", "total_short"]
def load(kind, folder="data/participant"):
    recs = []
    for p in sorted(Path(folder).glob(f"{kind}_*.csv")):
        day = p.stem.split("_")[1]
        for row in csv.reader(io.StringIO(p.read_text(errors="ignore"))):
            if row and row[0].strip() in ("Client", "DII", "FII", "Pro"):
                try:
                    vals = [float(x.replace(",", "").strip() or 0) for x in row[1:15]]
                except ValueError:
                    continue
                recs.append({"date": day, "who": row[0].strip(), **dict(zip(COLS, vals))})
    df = pd.DataFrame(recs)
    return df.pivot(index="date", columns="who")
def daily(name, S):
    d = json.load(open(f"{S}/daily_{name}.json"))
    return pd.DataFrame.from_dict(d, orient="index", columns=["open", "high", "low", "close"]).sort_index()
