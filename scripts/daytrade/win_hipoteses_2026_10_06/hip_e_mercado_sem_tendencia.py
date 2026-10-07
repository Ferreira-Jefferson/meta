"""Hipotese E -- reconhecer mercado sem tendencia / em inversao e PAUSAR (WIN, MELHOR ATUAL).

Etapa 1: diagnostico (pts/op por quintil de cada medida no instante da entrada).
Etapa 2: simulacao real (kit) bloqueando sinais quando a medida indica "choppy".

Declaracoes:
 - Medidas M5 usam so' dados do proprio contrato (seg) ate o fechamento da barra.
 - Medidas "D" (dias) usam o arquivo diario AJUSTADO WIN@D (so' para medidas, nunca
   preco de execucao), SEMPRE com shift de 1 dia (so' pregoes anteriores ao do sinal).
 - Limiares = quantis (20/33/50%) da distribuicao da medida nas entradas do baseline
   (informacao da amostra inteira -> leve vies in-sample, declarado).
 - Estado do dia (paradas por k perdas / -R$X): derivado dos trades do baseline; e' exato
   porque pausar so' remove trades POSTERIORES ao gatilho no mesmo dia.
 - No diagnostico a medida e' lida na barra anterior a da ENTRADA (a barra do sinal esta
   entre 1 e 5 barras antes); na simulacao o hook e' lido exatamente na barra do sinal.
"""
import importlib.util as u
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
_s = u.spec_from_file_location("kit", AQUI.parent / "win_melhor_kit.py")
kit = u.module_from_spec(_s); _s.loader.exec_module(kit)
b = kit.b

DIARIO = kit.DADOS / "WIN@D_M5_202110010900_202610011715.csv"
QUANTIS = (0.20, 0.33, 0.50)


# ----------------------------------------------------------------- medidas
def _diario():
    d = pd.read_csv(DIARIO, sep="\t"); d.columns = [c.strip("<>") for c in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"OPEN": "o", "HIGH": "h", "LOW": "l", "CLOSE": "c"})
    g = d.groupby(d.index.normalize()).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return g


def _er(c, n):
    return (c - c.shift(n)).abs() / c.diff().abs().rolling(n).sum()


def _adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = 1 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=h.index).ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * pd.Series(mdm, index=h.index).ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=a, adjust=False).mean()


def medidas(seg: pd.DataFrame) -> dict:
    """name -> array alinhado a seg.index; ALTO = tendencia, BAIXO = choppy."""
    c, h, l, v = seg.c, seg.h, seg.l, seg.vol
    M = {}
    for n in (48, 96, 288):
        M[f"ER_M5_{n}"] = _er(c, n)
    M["ADX14_M5"] = _adx(h, l, c)
    dia = seg.index.normalize()
    tp = (h + l + c) / 3
    sem = seg.index.to_period("W-SUN")
    for nome, chave in (("d", dia), ("w", sem)):
        vw = (tp * v).groupby(chave).cumsum() / v.groupby(chave).cumsum()
        sg = np.sign(c - vw)
        cruz = ((sg != sg.shift()) & (sg != 0) & (sg.shift() != 0)).astype(float)
        for n in (48, 96):
            M[f"VWAP{nome}_cruz_{n}"] = -cruz.rolling(n).sum()
    # alinhamento das EMAs
    es = [b.media(c, p, "EMA") for p in (9, 21, 34, 100, 200)]
    up = pd.Series(True, index=seg.index); dn = up.copy()
    for a_, b_ in zip(es, es[1:]):
        up &= a_ > b_; dn &= a_ < b_
    for e in es:
        up &= e.diff() > 0; dn &= e.diff() < 0
    al = (up | dn).astype(float)
    for n in (24, 48, 96):
        M[f"ALINH_{n}"] = al.rolling(n).mean()
    # diarias (shift 1 dia)
    D = _diario()
    atr = pd.concat([D.h - D.l, (D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean()
    DD = {}
    for n in (3, 5, 10):
        DD[f"ER_D_{n}"] = _er(D.c, n)
        DD[f"RANGE_D_{n}/ATR"] = (D.h.rolling(n).max() - D.l.rolling(n).min()) / atr
    DD["ADX14_D"] = _adx(D.h, D.l, D.c)
    for k, s in DD.items():
        s = s.shift(1)
        M[k] = s.reindex(dia).values
    return {k: np.asarray(v, float) for k, v in M.items()}


# ----------------------------------------------------------------- hooks
def hook_medida(nome, thr):
    def f(seg):
        m = medidas(seg)[nome]
        return ~(m < thr)          # NaN (aquecimento) -> permite
    return f


def hook_estado(trades_seg: pd.DataFrame, modo: str, x: float):
    """Bloqueia sinais do dia apos o gatilho. modo: 'perdas' k=x | 'consec' k=x | 'cum' -X."""
    def f(seg):
        ok = np.ones(len(seg), bool)
        if len(trades_seg):
            tr = trades_seg.sort_values("t_saida")
            dias = seg.index.normalize()
            for dia, g in tr.groupby("dia"):
                gat = None; nl = 0; cons = 0; cum = 0.0
                for r in g.itertuples():
                    cum += r.pnl
                    if r.pnl < 0:
                        nl += 1; cons += 1
                    else:
                        cons = 0
                    if (modo == "perdas" and nl >= x) or (modo == "consec" and cons >= x) or (modo == "cum" and cum <= -x):
                        gat = r.t_saida; break
                if gat is not None:
                    ok &= ~((dias == pd.Timestamp(dia).normalize()) & (seg.index >= gat))
        return ok
    return f


# ----------------------------------------------------------------- execucao
_M5 = None


def _m5():
    global _M5
    if _M5 is None:
        _M5 = kit.carregar_m5()
    return _M5


def rodar(task):
    nome, kind, a, bb, tr = task
    m5 = _m5()
    if kind == "medida":
        hk = hook_medida(a, bb)
        res = kit.rodar_meses(m5, permite_long=hk, permite_short=hk)
    else:
        trd = tr
        def hk(seg):
            return hook_estado(trd[trd.contrato == seg_nome(seg)].drop(columns="contrato"), a, bb)(seg)
        res = kit.rodar_meses(m5, permite_long=hk, permite_short=hk)
    liq = [float(r["eq"].iloc[-1] - b.CAP0) for r in res]
    return nome, kind, a, bb, kit.resumo(res), liq, [r["janela"] for r in res], \
        [r["trades"] for r in res] if kind == "diag" else None


def seg_nome(seg):
    for nm, s, _, _ in kit.segmentos(_m5()):
        if s.index[0] == seg.index[0]:
            return nm


# ----------------------------------------------------------------- principal
def fmt(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    m5 = kit.carregar_m5()
    base = kit.rodar_meses(m5)
    rb = kit.resumo(base)
    liq_b = [float(r["eq"].iloc[-1] - b.CAP0) for r in base]
    jan = [r["janela"] for r in base]
    print("BASELINE", rb, flush=True)

    # trades com contrato
    segs = {nm: s for nm, s, _, _ in kit.segmentos(m5)}
    T = pd.concat([r["trades"].assign(contrato=r["contrato"]) for r in base], ignore_index=True)
    # ---- Etapa 1: medidas na entrada
    rows = []
    cache = {nm: medidas(s) for nm, s in segs.items()}
    nomes = list(next(iter(cache.values())).keys())
    for r in T.itertuples():
        s = segs[r.contrato]
        pos = s.index.searchsorted(r.t) - 1
        d = dict(pnl=r.pnl, pts=r.pts, dia=r.dia, lado=r.lado, t=r.t)
        for k in nomes:
            d[k] = cache[r.contrato][k][pos] if pos >= 0 else np.nan
        rows.append(d)
    X = pd.DataFrame(rows)
    # estado do dia no instante da entrada
    X = X.sort_values("t").reset_index(drop=True)
    sv = T.sort_values("t_saida")
    nprev, cumprev, lossprev = [], [], []
    for r in X.itertuples():
        p = sv[(sv.dia == r.dia) & (sv.t_saida <= r.t)]
        nprev.append(len(p)); cumprev.append(p.pnl.sum()); lossprev.append(int((p.pnl < 0).sum()))
    X["ESTADO_perdas_no_dia"] = lossprev
    X["ESTADO_pnl_dia"] = cumprev

    diag = []
    for k in nomes:
        v = X[k]; ok = v.notna()
        if ok.sum() < 50:
            continue
        q = pd.qcut(v[ok].rank(method="first"), 5, labels=False)
        pts = X.pts[ok].groupby(q).mean(); rs = X.pnl[ok].groupby(q).sum()
        rho = pd.Series(range(5)).rank().corr(pts.reset_index(drop=True).rank())
        diag.append((k, pts.round(1).tolist(), rs.round(0).tolist(), rho, int(ok.sum())))
    # estado
    for k, bins in (("ESTADO_perdas_no_dia", [(0, 0), (1, 1), (2, 2), (3, 99)]),):
        pass
    est_rows = []
    for lo, hi in ((0, 0), (1, 1), (2, 2), (3, 3), (4, 99)):
        g = X[(X.ESTADO_perdas_no_dia >= lo) & (X.ESTADO_perdas_no_dia <= hi)]
        est_rows.append((f"{lo}" if lo == hi else f"{lo}+", len(g), g.pts.mean(), g.pnl.sum()))
    est_cum = []
    for lo, hi in ((-1e9, -300), (-300, -150), (-150, -50), (-50, 1e-9), (1e-9, 1e9)):
        g = X[(X.ESTADO_pnl_dia > lo) & (X.ESTADO_pnl_dia <= hi)]
        est_cum.append((f"({lo:.0f},{hi:.0f}]", len(g), g.pts.mean(), g.pnl.sum()))

    # ---- Etapa 2: tarefas
    thr = {}
    tasks = []
    for k in nomes:
        v = X[k].dropna()
        for qn in QUANTIS:
            t_ = float(v.quantile(qn)); thr[(k, qn)] = t_
            tasks.append((f"{k} < q{int(qn*100)}", "medida", k, t_, None))
    Tt = T[["pnl", "dia", "pts", "t", "lado", "t_saida", "qty", "contrato"]]
    for kx in (2, 3, 4, 5):
        tasks.append((f"parar apos {kx} perdas no dia", "estado", "perdas", kx, Tt))
    for kx in (2, 3, 4):
        tasks.append((f"parar apos {kx} perdas seguidas", "estado", "consec", kx, Tt))
    for x in (75, 150, 250, 400):
        tasks.append((f"parar se dia <= -R${x}", "estado", "cum", x, Tt))
    print(f"{len(tasks)} simulacoes na etapa 2", flush=True)

    out = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fut = {ex.submit(rodar, t): t for t in tasks}
        for f in as_completed(fut):
            nome, kind, a, bb, rs, liq, jn, _ = f.result()
            out[nome] = (kind, a, bb, rs, liq)
            print(f"{nome:42s} liq={rs['liquido_total']:>9} jan+={rs['janelas_pos']:>6} pior={rs['pior_janela']:>8} "
                  f"trades={rs['trades']:>4} DD={rs['maior_DD_R$']}", flush=True)

    # ---- avaliacao
    ib = int(np.argmax(liq_b))
    def aval(nome):
        kind, a, bb, rs, liq = out[nome]
        d = np.array(liq) - np.array(liq_b)
        dl = float(sum(liq) - sum(liq_b))
        sem_top = dl - d[ib]
        lowo_min = float(min(dl - x for x in d))
        frac = rs["trades"] / rb["trades"]
        exc = float(sum(liq) - sum(liq_b) * frac)  # contra corte aleatorio proporcional
        return dict(nome=nome, rs=rs, dl=dl, sem_top=sem_top, lowo_min=lowo_min, exc=exc,
                    melhora=int((d > 1e-9).sum()), piora=int((d < -1e-9).sum()))
    A = {n: aval(n) for n in out}

    def linha(n, a):
        rs = a["rs"]
        return (f"| {n} | {fmt(rs['liquido_total'],0)} | {rs['janelas_pos']} | {fmt(rs['pior_janela'],0)} | "
                f"{str(rs['PF']).replace('.',',')} | {str(rs['pts/op']).replace('.',',')} | {rs['trades']} | "
                f"{fmt(rs['maior_DD_R$'],0)} / {str(rs['maior_DD%']).replace('.',',')}% | "
                f"{str(rs['fator_recup']).replace('.',',')} | {fmt(a['dl'],0)} | {fmt(a['sem_top'],0)} | "
                f"{fmt(a['exc'],0)} | {a['melhora']}/{a['piora']} |")
    cab = ("| variante | liquido R$ | jan+ | pior jan R$ | PF | pts/op | trades | maior DD R$ / % | fat.recup | "
           "d vs base | d sem a melhor jan | excesso vs corte aleatorio | jan melhora/piora |\n"
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    a0 = dict(rs=rb, dl=0.0, sem_top=0.0, exc=0.0, melhora=0, piora=0)

    # candidatas: monotonia/plato por medida (3 quantis todos com d>0 e excesso>0)
    cands = []
    for k in nomes:
        ns = [f"{k} < q{int(q*100)}" for q in QUANTIS]
        if all(A[n]["dl"] > 0 for n in ns):
            cands.append(k)
    cands_estrito = []
    for k in nomes:
        ns = [f"{k} < q{int(q*100)}" for q in QUANTIS]
        if all(A[n]["dl"] > 0 and A[n]["sem_top"] > 0 and A[n]["rs"]["pior_janela"] >= rb["pior_janela"]
               and A[n]["rs"]["maior_DD_R$"] <= rb["maior_DD_R$"] for n in ns):
            cands_estrito.append(k)

    md = []
    md.append("# Hipotese E -- mercado sem tendencia / em inversao: quando NAO operar (WIN, MELHOR ATUAL)\n")
    md.append("Baseline: 14 janelas mensais de 2026, R$1.000/janela, 1 contrato, contrato principal real. "
              "Medidas M5 so' do proprio contrato; medidas diarias (D) do arquivo ajustado WIN@D, shift de 1 dia, "
              "so' como medida (nunca preco de execucao). Limiares = quantis 20/33/50% da medida nas entradas do baseline "
              "(leve vies in-sample, declarado). Bloqueio = sinal ignorado quando medida < limiar.\n")
    md.append("## Etapa 1 -- diagnostico: pts/op e R$ por quintil da medida na entrada (Q1 = mais choppy ... Q5 = mais tendencia)\n")
    md.append(f"988 trades; baseline pts/op = {rb['pts/op']}. rho = Spearman entre quintil e pts/op (+1 = tendencia ajuda).\n")
    md.append("| medida | pts/op Q1..Q5 | R$ Q1..Q5 | rho |\n|---|---|---|---|")
    for k, pts, rs_, rho, n in sorted(diag, key=lambda x: -abs(x[3] if x[3] == x[3] else 0)):
        md.append(f"| {k} | {' / '.join(fmt(x,1) for x in pts)} | {' / '.join(fmt(x) for x in rs_)} | {rho:+.2f} |".replace("+0.", "+0,").replace("-0.", "-0,").replace("+1.", "+1,"))
    md.append("\nEstado do proprio dia no instante da entrada:\n")
    md.append("| perdas ja realizadas no dia | n | pts/op | R$ |\n|---|---|---|---|")
    for a_, n_, p_, r_ in est_rows:
        md.append(f"| {a_} | {n_} | {fmt(p_,1)} | {fmt(r_)} |")
    md.append("\n| P&L do dia antes da entrada (R$) | n | pts/op | R$ |\n|---|---|---|---|")
    for a_, n_, p_, r_ in est_cum:
        md.append(f"| {a_} | {n_} | {fmt(p_,1)} | {fmt(r_)} |")

    md.append("\n## Etapa 2 -- simulacao real (kit) vs baseline\n")
    md.append(f"{len(tasks)} simulacoes ({len(nomes)} medidas x {len(QUANTIS)} limiares + 11 regras de estado do dia). "
              "'excesso vs corte aleatorio' = liquido - liquido_base x (trades_var/trades_base): quanto a variante "
              "ganha alem de simplesmente cortar a mesma fracao de trades ao acaso.\n")
    md.append(cab)
    md.append(linha("**BASELINE**", a0))
    for n in sorted(A, key=lambda n: -A[n]["dl"]):
        md.append(linha(n, A[n]))
    md.append(f"\nMedidas com melhora em liquido nos 3 limiares (monotonia/plato minimos): {cands if cands else 'nenhuma'}.")
    md.append(f"Medidas que ainda melhoram janela-pior e DD e sobrevivem sem a melhor janela nos 3 limiares: "
              f"{cands_estrito if cands_estrito else 'nenhuma'}.")
    md.append(f"\nMelhor janela do baseline (removida no teste 'sem a melhor jan'): {jan[ib]} ({fmt(liq_b[ib])}).")
    best = max(A, key=lambda n: A[n]["dl"])
    md.append(f"\n## Mes a mes -- melhor variante por liquido: {best}\n")
    md.append("| janela | baseline R$ | variante R$ | delta |\n|---|---|---|---|")
    for j, x, y in zip(jan, liq_b, out[best][4]):
        md.append(f"| {j} | {fmt(x)} | {fmt(y)} | {fmt(y-x)} |")
    for k in cands_estrito[:2]:
        n = f"{k} < q33"
        md.append(f"\n### Mes a mes -- {n}\n\n| janela | baseline R$ | variante R$ | delta |\n|---|---|---|---|")
        for j, x, y in zip(jan, liq_b, out[n][4]):
            md.append(f"| {j} | {fmt(x)} | {fmt(y)} | {fmt(y-x)} |")
    md.append(f"\n## Contagem de testes\n\n{len(nomes)} medidas avaliadas no diagnostico (+2 de estado do dia); "
              f"{len(tasks)} simulacoes completas de 14 janelas. Com ~{len(tasks)} variantes, ~5% (3-4) "
              "melhoram por acaso mesmo sem efeito.\n")
    (AQUI / "hip_e_mercado_sem_tendencia_tabelas.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md), flush=True)


if __name__ == "__main__":
    main()
