"""A3 refazer: as candidatas congeladas das rodadas b-f e suas validacoes, rodadas com o MESMO codigo em 4 configuracoes:
  A = (bruto, WIN@)  = antes, base original      B = (bruto, WIN$N) = antes, base WIN$N
  D = (sl,    WIN@)  = depois, base original      C = (sl,    WIN$N) = depois, base WIN$N
'bruto' = barras com leilao e zera em c[-1] (call); 'sl' = sem leiloes, zera na ultima barra continua.
Uso: python candidatas_antes_depois.py   -> resultado_candidatas.jsonl (uma linha por candidata x ano, na ordem em que terminam)"""
import json, os, sys, io, contextlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DT = AQUI.parents[2]
CFG = {"A": ("bruto", "WIN@"), "B": ("bruto", "WIN$N"), "C": ("sl", "WIN$N"), "D": ("sl", "WIN@")}
V1 = dict(periodos=(9, 21, 34, 100, 200), ema_saida=21)   # padrao da lib na epoca da validacao b (v1)
V200 = dict(saida_vol=False, aperta=None, saida_st=None)


def _fmt(r):
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()}


def familia_b(w, cfg):
    """validacao_2025.py (b): 9 candidatas congeladas, v2.00-sem-vol/stop/ST (era a lib da epoca), anos 2026 e 2025."""
    CONG = [
        ("ATUAL 9/21/34/100/200 M5", "5min", {}),
        ("ref: 5 medias SEM filtro do mes", "5min", dict(filtro_mes=False)),
        ("b1-1 9/21/34/55/100/150/200/300", "5min", dict(periodos=(9, 21, 34, 55, 100, 150, 200, 300))),
        ("b1-2 9/21/34/55/100/200", "5min", dict(periodos=(9, 21, 34, 55, 100, 200))),
        ("b1-3 9/21/34/55/100/150/200/300/400", "5min", dict(periodos=(9, 21, 34, 55, 100, 150, 200, 300, 400))),
        ("b2-1 M15 3/7/11/33/67 saida7", "15min", dict(periodos=(3, 7, 11, 33, 67), ema_saida=7)),
        ("b2-2 M30 2/4/6/17/33 saida4", "30min", dict(periodos=(2, 4, 6, 17, 33), ema_saida=4)),
        ("b2-3 M10 9/21/34/100/200", "10min", {}),
        ("b3 corpo>EMA9, inclina nenhuma", "5min", dict(zona="corpo>m1", inclina=())),
    ]
    for nome, tf, kw in CONG:
        for ano in (2026, 2025):
            _, r = w.rodar_janelas(ano, tf, **{**V200, **V1, **kw})
            yield dict(familia="b", cand=nome, ano=ano, **_fmt(r))


def familia_c(w, cfg):
    sys.path[:0] = [str(DT), str(AQUI / "copias")]
    orig = w.simula
    import c2_volume_saida_contexto_semleilao as c2
    w.simula = orig   # o import do c2 troca w.simula; a baseline usa a da lib
    for ano in (2026, 2025):
        d = w.carregar(ano)
        yield dict(familia="c", cand="BASELINE v2.00", ano=ano, **_fmt(w.rodar_janelas(ano, dados=d, **V200)[1]))
        for nome, fn in (("c2a climax volume q90", c2.fn_climax("v_rel", 0.90, "contra")),
                         ("controle: climax range", c2.fn_climax("r_rel", 0.90, "contra"))):
            d2 = c2.features(d)
            orig = w.simula
            w.simula = c2.simula
            try:
                r = w.rodar_janelas(ano, dados=d2, saida_fn=fn, saida_escopo="todos")[1]
            finally:
                w.simula = orig
            yield dict(familia="c", cand=nome, ano=ano, **_fmt(r))


def familia_d(w, cfg):
    sys.path[:0] = [str(DT), str(AQUI / "copias")]
    import d1_candidatas_semleilao as d1, d2_candidatas_semleilao as d2
    for ano in (2026, 2025):
        d = w.carregar(ano)
        yield dict(familia="d", cand="BASELINE v2.01", ano=ano, **_fmt(w.rodar_janelas(ano, dados=d, aperta=None, saida_st=None)[1]))
        for n, f in d1.CANDIDATAS.items():
            yield dict(familia="d", cand=n, ano=ano, **_fmt(f(ano, d.copy())))
        dv = w.colunas_volume(d)
        for n, f in d2.CANDIDATAS.items():
            yield dict(familia="d", cand=n, ano=ano, **_fmt(f(ano, dv.copy())))


def familia_f1(w, cfg):
    sys.path[:0] = [str(DT), str(AQUI / "copias")]
    import f1_candidatas_semleilao as m
    for ano in (2026, 2025, 2022, 2023, 2024):
        d = w.carregar(ano)
        yield dict(familia="f1", cand="BASE v2.02", ano=ano, **_fmt(w.rodar_janelas(ano, dados=d)[1]))
        for n, f in m.CANDIDATAS.items():
            yield dict(familia="f1", cand=n, ano=ano, **_fmt(f(ano, d)))


def familia_f3(w, cfg):
    sys.path[:0] = [str(DT), str(AQUI / "copias")]
    import f3_candidatas_semleilao as m
    for ano in (2026, 2025, 2022, 2023, 2024):
        d = w.carregar(ano)
        yield dict(familia="f3", cand="BASE v2.02", ano=ano, **_fmt(m.W.rodar_janelas(ano, dados=d)[1]))
        for n, f in (("ST_H1_SAIDA", m.st_h1_saida), ("ADX_DI_ENTRADA", m.adx_di_entrada), ("COMBO", m.combo)):
            yield dict(familia="f3", cand=n, ano=ano, **_fmt(f(ano, d)))


FAM = dict(b=familia_b, c=familia_c, d=familia_d, f1=familia_f1, f3=familia_f3)


def unidade(cfg, fam):
    modo, base = CFG[cfg]
    os.environ["WINCM_MODO"] = modo; os.environ["WINCM_BASE"] = base
    sys.path.insert(0, str(DT))
    import win_cinco_medias_semleilao as w
    assert w.MODO == modo and w.BASE == base
    if fam in ("f1", "f3"):
        w.usar_v202()
    out = []
    for lin in FAM[fam](w, cfg):
        lin["cfg"] = cfg; out.append(lin)
    return out


if __name__ == "__main__":
    fams = sys.argv[1].split(",") if len(sys.argv) > 1 else list(FAM)
    with ProcessPoolExecutor(max_workers=6, max_tasks_per_child=1) as ex, open(AQUI / "resultado_candidatas.jsonl", "a" if len(sys.argv) > 1 else "w", encoding="utf-8") as f:
        fut = {ex.submit(unidade, c, fm): (c, fm) for fm in fams for c in CFG}
        for x in as_completed(fut):
            try:
                for lin in x.result():
                    f.write(json.dumps(lin) + "\n"); f.flush()
                print("ok", fut[x], flush=True)
            except Exception as e:
                import traceback; print("ERRO", fut[x], repr(e), flush=True); traceback.print_exc()
