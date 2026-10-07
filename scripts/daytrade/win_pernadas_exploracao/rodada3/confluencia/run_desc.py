import sys, runner
if __name__ == "__main__":
    ns, nu = int(sys.argv[1]), int(sys.argv[2])
    cfg = dict(load_end="2026.06.30", Ds=[300, 600], Ns=[100, 200], split="2026-04-01", win=("2026-01-01", "2026-06-30"))
    if len(sys.argv) > 3 and sys.argv[3] == "smoke":
        cfg["only"] = ["vwap", "m15_ema50"]
    runner.run_all(cfg, ns, nu, "desc_smoke.pkl" if len(sys.argv) > 3 else "desc.pkl")
