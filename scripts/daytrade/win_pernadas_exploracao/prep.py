import pandas as pd, json, sys
p = r"data/wdo-mt5/WINV26_M1_202604151210_202610011824.csv"
df = pd.read_csv(p, sep="\t")
df.columns = [c.strip("<>").lower() for c in df.columns]
df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
df = df[(df.ts >= "2026-09-01") & (df.ts < "2026-10-01")].set_index("ts")
out = {}
for name, rule in [("M5","5min"),("M15","15min"),("H1","60min")]:
    r = df.resample(rule, label="left", closed="left").agg({"open":"first","high":"max","low":"min","close":"last","vol":"sum"}).dropna()
    days = {}
    for ts, row in r.iterrows():
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append([ts.strftime("%H:%M"), int(row.open), int(row.high), int(row.low), int(row.close), int(row.vol)])
    out[name] = days
    print(name, len(r), len(days), file=sys.stderr)
open(sys.argv[1], "w").write(json.dumps(out, separators=(",",":")))
