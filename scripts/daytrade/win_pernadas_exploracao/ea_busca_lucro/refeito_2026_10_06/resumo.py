import json, glob, os, re, collections
out = os.path.join(os.path.dirname(__file__), "out")
agg = collections.defaultdict(lambda: dict(runs=0, n=0, ff=0, ultima=0))
for f in sorted(glob.glob(out + "/*.jsonl")):
    stem = os.path.basename(f)[:-6]
    for l in open(f, encoding="utf-8"):
        d = json.loads(l)
        if "erro" in d: continue
        a = agg[stem]; a["runs"] += 1
        for k in ("n", "ff", "ultima"): a[k] += d[k]
print(f"{'script_modo':<34}{'celulas':>8}{'trades':>8}{'forcadas':>9}{'na ultima':>10}{'% trades':>9}")
for k, a in agg.items():
    p = 100 * a["ultima"] / a["n"] if a["n"] else float("nan")
    print(f"{k:<34}{a['runs']:>8}{a['n']:>8}{a['ff']:>9}{a['ultima']:>10}{p:>8.1f}%")
