import sys, json, runner
if __name__ == "__main__":
    fz = json.load(open("frozen.json"))
    fams = sorted({c[0] for c in fz["configs"]})
    cfg = dict(load_end="2026.08.31", Ds=[300, 600], Ns=[100, 200], split="2026-08-01", win=("2026-07-01", "2026-08-31"), only=fams)
    runner.run_all(cfg, 40, 16, "conf.pkl")
