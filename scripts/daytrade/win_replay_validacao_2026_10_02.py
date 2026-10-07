"""Regressao WINV26 + validacao cruzada WINV26 x WIN@D (ago/set 2026) + WIN@D mensal mar-set. Uso: python win_replay_validacao_2026_10_02.py [reg|cruz|mensal]"""
import sys, json
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_replay_ticks as rp
pr = lambda k, n, m: print(f"  [{k}/{n}] {m}", flush=True) if k % 20 == 0 else None
def r(ini, fim, lat, ativo, m15):
    return rp.replay(date.fromisoformat(ini), date.fromisoformat(fim), lat, "fixa", {"alinhar_m15": m15}, ativo, pr)
def resumo(x): return {k: x["resumo"][k] for k in ("n", "liquido", "dd", "pf", "win")}
modo = sys.argv[1]
if modo == "reg":
    for m15 in (False, True):
        for ini, fim in (("2026-09-01", "2026-09-30"), ("2026-08-01", "2026-08-31")):
            print("REG", m15, ini, resumo(r(ini, fim, 0, "WINV26", m15)), flush=True)
if modo == "cruz":
    import pickle
    out = {}
    for lat in (0, 5):
        for ativo in ("WINV26", "WIN@D"):
            x = r("2026-08-12", "2026-09-30", lat, ativo, False); out[(ativo, lat)] = x
            print("CRUZ", ativo, lat, resumo(x), x["dias_sem_ticks"], x["avisos"][:2], flush=True)
    pickle.dump(out, open(Path(__file__).with_name("_cruz.pkl"), "wb"))
if modo == "mensal":
    for lat in (0,):
        x = r("2026-03-01", "2026-09-30", lat, "WIN@D", False)
        print("MENSAL lat", lat, resumo(x), x["dias_sem_ticks"], x["avisos"][:3], flush=True)
        for m in x["por_mes"]: print("  ", m, flush=True)
