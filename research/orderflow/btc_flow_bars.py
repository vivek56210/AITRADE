"""aggTrades -> 1-minute bars with true taker buy / sell volume (BTCUSDT perp)."""
import sys
from pathlib import Path
import pyarrow.parquet as pq, pandas as pd, numpy as np
src = Path("E:/vivek/TradeAI/data/parquet/futures/um/aggTrades/BTCUSDT"); out = Path(sys.argv[1])
for f in sorted(src.glob("*.parquet")):
    o = out / f.name
    if o.exists(): continue
    pf = pq.ParquetFile(f); parts = []
    for i in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(i, columns=["ts", "price", "quantity", "is_buyer_maker"]).to_pandas()
        t["m"] = t.ts.dt.floor("min"); t["buy"] = np.where(t.is_buyer_maker, 0.0, t.quantity)
        t["n"] = t.price * t.quantity
        parts.append(t.groupby("m").agg(open=("price", "first"), high=("price", "max"), low=("price", "min"),
                     close=("price", "last"), vol=("quantity", "sum"), buy=("buy", "sum"), notional=("n", "sum"),
                     trades=("price", "size")))
    b = pd.concat(parts); b = b.groupby(level=0).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), vol=("vol", "sum"), buy=("buy", "sum"), notional=("notional", "sum"), trades=("trades", "sum"))
    b.to_parquet(o); print(f.name, len(b), flush=True)
