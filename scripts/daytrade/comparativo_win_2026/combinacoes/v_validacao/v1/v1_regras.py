"""V1 -- as 13 candidatas como UMA funcao cada, regra_Ck(votos, eventos, resultados, dados, com_wdo=False) -> trades.

A MESMA regra das frentes (mesmo script, mesma grade, mesmo walk-forward, mesmos parametros); so' muda
  (a) o conjunto de votantes/posicoes: sem o WdoRetangulo (com_wdo=False) ou com ele (com_wdo=True, so' para provar
      a reproducao do CSV original da frente em 2026);
  (b) o calendario do walk-forward: as frentes fazem `for m in range(1, 11)` (jan..out/2026); aqui o mes e' uma chave
      sequencial (ano*12+mes) e o laco percorre os meses da JANELA (2026: jan..out; VAL: 2024-07..2025-09). A regra de
      escolha (passado = meses anteriores, expansivo) e' identica. No VAL o passado inclui 2024-01..06.
Os scripts das frentes sao IMPORTADOS (nenhum e' editado): consenso_filtro (mascaras), consenso_gatilho (prepara,
gatilhos, rodar), b_nota.comum (carrega, preve_mes, escolhe_limiar, logit), f0_fundacao.saida (simulador),
e_saida_virada.virada (prepara, conds, primeiro, diffs_de_k, sorteio_instante). Limites de modulos sao trocados em
tempo de execucao (VOT/FAM, ESTR, V/CLOSE/IDX, leitura de parquet) -- monkeypatch no processo, arquivos intactos.

Cada _core_Ck devolve (trades, estado); controle_Ck(estado, n, seed) devolve os n deltas (R$, com custo) do sorteio
nulo, contra o original do mesmo robo na janela. Uso: init('2026'|'val') UMA vez por processo, antes de tudo.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

AQ = Path(__file__).resolve().parent
COMB = AQ.parents[1]
BASE = COMB.parent
V0 = AQ.parent / "v0"
CUSTO = 2.0
RS_PT = 0.2
VOT5 = ["Win", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "WdoRetangulo"]
VOT4 = VOT5[:4]
FAM = {"Win": "T", "WinCincoMedias": "T", "WinDeslocamentoMatinal": "T", "WinRetanguloEma34": "R", "WdoRetangulo": "R"}
WDO = "WdoRetangulo"
COLS = ["estrategia", "entrada", "saida", "lado", "qtd", "preco_entrada", "preco_saida", "motivo", "pontos", "rs"]

MODO = None
MESES = []        # chaves de mes (ano*12+mes) da janela
MK0 = None        # chave do mes 1 do indice sequencial (o mes 1 de "mes" nas frentes de B)
mods: dict = {}


def mk(x):
    """Chave sequencial de mes. Aceita Series datetime (via .dt), DatetimeIndex ou Timestamp."""
    if isinstance(x, pd.Series):
        return (x.dt.year * 12 + x.dt.month).to_numpy()
    if isinstance(x, pd.DatetimeIndex):
        return (x.year * 12 + x.month).to_numpy()
    return x.year * 12 + x.month


def init(modo: str):
    """Fixa o modulo `dados` do processo e importa os scripts das frentes. UMA vez por processo."""
    global MODO, MESES, MK0
    assert MODO is None, "init ja' chamado"
    MODO = modo
    for p in (BASE, COMB / "f0_fundacao", COMB / "a_consenso", COMB / "b_nota", COMB / "e_saida_virada"):
        sys.path.insert(0, str(p))
    if modo == "val":
        sys.path.insert(0, str(V0))
        import dados_val
        sys.modules["dados"] = dados_val
        dados = dados_val
        MESES = list(range(2024 * 12 + 7, 2025 * 12 + 10))          # 2024-07 .. 2025-09
        import os
        if os.environ.get("V1_SMOKE"):                                # teste de fumaca em 2024-04..06 (aquecimento, NAO e' VAL)
            MESES = list(range(2024 * 12 + 4, 2024 * 12 + 7))
        MK0 = 2024 * 12 + 1
    else:
        import dados
        MESES = list(range(2026 * 12 + 1, 2026 * 12 + 11))          # jan .. out/2026
        MK0 = 2026 * 12 + 1
    from functools import lru_cache
    import saida as S
    S._ticks = lru_cache(maxsize=None)(S._ticks.__wrapped__)
    import consenso_filtro as cf
    import consenso_gatilho as cg
    import comum
    import virada
    mods.update(D=dados, S=S, cf=cf, cg=cg, comum=comum, virada=virada)
    return dados


def carrega_ctx(modo: str | None = None):
    """-> (votos, eventos, resultados{robo: df}, dados)"""
    modo = modo or MODO
    if modo == "val":
        votos = pd.read_parquet(V0 / "votos_val.parquet"); eventos = pd.read_parquet(V0 / "eventos_val.parquet")
        pasta = V0 / "resultados"
    else:
        votos = pd.read_parquet(COMB / "f0_fundacao" / "votos.parquet"); eventos = pd.read_parquet(COMB / "f0_fundacao" / "eventos.parquet")
        pasta = BASE / "resultados"
    res = {}
    for n in ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]:
        t = pd.read_csv(pasta / f"{n}.csv")
        t["entrada"] = pd.to_datetime(t.entrada, format="mixed"); t["saida"] = pd.to_datetime(t.saida, format="mixed")
        res[n] = t
    return votos, eventos, res, mods["D"]


def na_janela(entrada: pd.Series) -> np.ndarray:
    k = mk(entrada)
    return (k >= MESES[0]) & (k <= MESES[-1])


def original_janela(resultados, robo) -> pd.DataFrame:
    t = resultados[robo]
    return t[na_janela(t.entrada)].reset_index(drop=True)


def _fmt(df, robo) -> pd.DataFrame:
    d = df.copy()
    d["estrategia"] = robo
    if "qtd" not in d: d["qtd"] = 1.0
    return d[COLS].reset_index(drop=True)


class _Pd:
    """Proxy do pandas que devolve um DataFrame fixo em read_parquet (para reaproveitar carrega()/prepara() sem editar)."""
    def __init__(self, df): self._df = df
    def __getattr__(self, k): return getattr(pd, k)
    def read_parquet(self, *a, **k): return self._df.copy()


# =============================================================================== controles genericos
def delta_filtro_sorteio(orig_rs: np.ndarray, n_keep: int, n: int, seed: int) -> np.ndarray:
    """n sorteios: mantem ao acaso n_keep das entradas do original (mesma fracao cortada). Delta (R$, com custo) por sorteio."""
    rng = np.random.default_rng(seed)
    net = orig_rs - CUSTO
    tot = net.sum()
    out = np.empty(n)
    for i in range(n):
        out[i] = net[rng.choice(len(net), n_keep, replace=False)].sum() - tot
    return out


# =============================================================================== A1 (C2, C3, C4)
def _a1(eventos, com_wdo, escopo, robo):
    cf = mods["cf"]
    VOT = VOT5 if com_wdo else VOT4
    cf.VOT = VOT; cf.FAM = FAM
    e = eventos[eventos.estrategia.isin(VOT)].reset_index(drop=True).copy()
    V = np.stack([e[f"{v}.voto"].to_numpy(float) for v in VOT], 1)
    F = np.stack([e[f"{v}.forca"].to_numpy(float) for v in VOT], 1)
    old = e.voto_mesmo_dia.to_numpy() == 0
    V[old] = 0; F[old] = 0
    masks = cf.mascaras(e, V, F)
    ke, ks = mk(e.entrada), mk(e.saida)
    rs2 = e.rs.to_numpy() - CUSTO
    est = e.estrategia.to_numpy()

    def walk(rs_net, k_ent, k_sai, mks, default="maj"):
        keep = np.zeros(len(rs_net), bool); esc = {}
        for m in MESES:
            past = k_sai < m
            best = default
            if past.any():
                sc = {v: rs_net[past & mks[v]].sum() for v in cf.VARS}
                best = max(cf.VARS, key=lambda v: (sc[v], -cf.VARS.index(v)))
            esc[m] = best
            sel = k_ent == m
            keep[sel] = mks[best][sel]
        return keep, esc

    if escopo == "comum":
        keep, esc = walk(rs2, ke, ks, masks)
    else:
        keep = np.zeros(len(e), bool); esc = {}
        for x in VOT:
            s = est == x
            k, ex = walk(rs2[s], ke[s], ks[s], {v: masks[v][s] for v in cf.VARS})
            keep[np.flatnonzero(s)[k]] = True
            esc[x] = ex
    sel = keep & (est == robo) & na_janela(e.entrada)
    return _fmt(e[sel], robo), dict(esc=esc, n_total_janela=int(((est == robo) & na_janela(e.entrada)).sum()))


# =============================================================================== B generico (C1, C12)
def _carrega_b(eventos, com_wdo):
    comum = mods["comum"]
    old = comum.pd; comum.pd = _Pd(eventos)
    try:
        e = comum.carrega()
    finally:
        comum.pd = old
    if not com_wdo:
        e = e[e.estrategia != WDO].reset_index(drop=True)
    e["mes"] = mk(e.entrada) - MK0 + 1            # indice sequencial (2026: 1..10; VAL: 2024-01 = 1)
    e["cheg_lucro"] = 0; e["cheg_prej"] = 0        # so' o modelo 'logit' usa a ordem de chegada; 'tabela' e 'nota' nao
    return e


def _previsoes_b(e, modelos):
    comum = mods["comum"]
    D = comum.monta(e); y = e.y.to_numpy(); K = int(e.mes.max())
    P = {k: np.full(len(y), np.nan) for k in modelos}
    for m in range(2, K + 1):
        te = D["mes"] == m
        for k, v in comum.preve_mes(D, y, m, modelos).items():
            P[k][te] = v
    return D, y, P


def _mantidos_b(mes, p, rs_liq):
    comum = mods["comum"]
    keep = np.ones(len(mes), bool); info = []
    for mkey in MESES:
        m = mkey - MK0 + 1
        f, thr = comum.escolhe_limiar(mes, p, m, rs_liq)
        mm = mes == m
        if f > 0:
            keep[mm] = np.where(np.isnan(p[mm]), True, p[mm] >= thr)
        info.append((m, f, thr))
    return keep, info


def _core_c1(votos, eventos, resultados, dados, com_wdo=False):
    e = _carrega_b(eventos, com_wdo)
    D, y, P = _previsoes_b(e, ("tabela",))
    est = e.estrategia.to_numpy(); rs = e.rs.to_numpy()
    rsl_sel = np.where(est != "Win_c1", rs - CUSTO, 0.0)
    keep, info = _mantidos_b(e.mes.to_numpy(), P["tabela"], rsl_sel)
    sel = keep & (est == "Win_c1") & na_janela(e.entrada)
    return _fmt(e[sel], "Win_c1"), dict(info=info)


def _arred(x):
    return np.maximum(np.round(np.asarray(x, float) / 5.0) * 5.0, 5.0)


def _niveis(modo):
    return pd.read_csv(COMB / "b_nota" / "retema34_niveis.csv") if modo != "val" else pd.read_csv(AQ / "retema34_niveis_val.csv")


MA = [1.0, 1.25, 1.5]; MS = [1.0, 0.75, 0.5]
CELULAS = [(ma, ms) for ma in MA for ms in MS]


def _core_c12(votos, eventos, resultados, dados, com_wdo=False):
    S = mods["S"]
    e = _carrega_b(eventos, com_wdo)
    D, y, P = _previsoes_b(e, ("nota",))
    est = e.estrategia.to_numpy(); mes = e.mes.to_numpy()
    r_idx = np.flatnonzero(est == "WinRetanguloEma34")
    er = e.iloc[r_idx].reset_index(drop=True)
    niv = _niveis(MODO)
    m_ = er.merge(niv[["t_ent", "stop_pts", "alvo0_pts"]], left_on="t_entrada_ms", right_on="t_ent", how="left")
    assert m_.stop_pts.notna().all() and len(m_) == len(er), "join dos niveis falhou"
    STOP0 = m_.stop_pts.to_numpy(); ALVO0 = m_.alvo0_pts.to_numpy()
    LADO = er.lado.to_numpy(); PE = er.preco_entrada.to_numpy(); TE = er.t_entrada_ms.to_numpy()

    def resim(sm, am):
        o = S.simula_saida_lote(TE, LADO, PE, _arred(STOP0 * sm), _arred(ALVO0 * am), hora_zera="17:00", alvo_limite=True)
        return o.pontos.to_numpy() * RS_PT
    base_r = resim(1.0, 1.0)
    sims = {(1.0, 1.0): base_r}
    for ma in MA[1:]: sims[(1.0, ma)] = resim(1.0, ma)
    for ms in MS[1:]: sims[(ms, 1.0)] = resim(ms, 1.0)
    mm = mes[r_idx]
    MIN_MES = mods["comum"].MES_MIN_FILTRO

    def sim_get(cel, high):
        ma, ms = cel
        return np.where(high, sims[(1.0, ma)], sims[(ms, 1.0)]) - CUSTO

    def wf(score):
        final = sim_get((1.0, 1.0), np.ones(len(r_idx), bool)).copy(); esc = {}
        for mkey in MESES:
            m = mkey - MK0 + 1
            if m < MIN_MES: continue
            past = (mm >= 2) & (mm < m) & ~np.isnan(score)
            if past.sum() < 20: continue
            thr = np.median(score[past]); high = np.where(np.isnan(score), True, score >= thr)
            best, bv = (1.0, 1.0), sim_get((1.0, 1.0), high)[past].sum()
            for c in CELULAS:
                v = sim_get(c, high)[past].sum()
                if v > bv + 1e-9: best, bv = c, v
            esc[m] = (best, thr)
            cur = mm == m
            final[cur] = sim_get(best, high)[cur]
        return final, esc
    sc = P["nota"][r_idx]
    final, esc = wf(sc)
    smul = np.ones(len(er)); amul = np.ones(len(er))
    for m, (cel, thr) in esc.items():
        ma, ms = cel
        high = np.where(np.isnan(sc), True, sc >= thr)
        sel = mm == m
        amul[sel & high] = ma; smul[sel & ~high] = ms
    o = S.simula_saida_lote(TE, LADO, PE, _arred(STOP0 * smul), _arred(ALVO0 * amul), hora_zera="17:00", alvo_limite=True)
    out = pd.DataFrame(dict(estrategia="WinRetanguloEma34", entrada=er.entrada, saida=pd.to_datetime(o.t_saida_ms.to_numpy(), unit="ms"),
                            lado=er.lado, qtd=1.0, preco_entrada=er.preco_entrada, preco_saida=o.preco_saida.to_numpy(),
                            motivo=o.motivo.to_numpy(), pontos=o.pontos.to_numpy()))
    out["rs"] = out.pontos * RS_PT
    janela = na_janela(out.entrada)
    chk = (out.rs - CUSTO).to_numpy()[janela].sum() - final[janela].sum()
    assert abs(chk) < 0.5, f"resize: trades x acumulado diferem {chk}"
    return out[janela][COLS].reset_index(drop=True), dict(wf=wf, mm=mm, janela=janela, esc=esc, n_ev=len(r_idx))


def _ctrl_c12(estado, resultados, n, seed):
    rng = np.random.default_rng(seed)
    wf, mm, janela = estado["wf"], estado["mm"], estado["janela"]
    orig = original_janela(resultados, "WinRetanguloEma34")
    tot = (orig.rs - CUSTO).sum()
    out = np.empty(n)
    for i in range(n):
        s2 = rng.uniform(size=len(mm)); s2[mm == 1] = np.nan
        out[i] = wf(s2)[0][janela].sum() - tot
    return out


# =============================================================================== E (C5..C11)
def _core_e(votos, eventos, resultados, dados, com_wdo, robo, var, p):
    V = mods["virada"]
    ESTR = VOT5 if com_wdo else VOT4
    V.ESTR = ESTR; V.FAM = FAM
    V.D = dados
    V.BASE = BASE if MODO != "val" else V0
    if com_wdo:
        # resultados/WdoRetangulo.csv foi apagado do repo (exclusao do dono): reconstroi das proprias operacoes em eventos.parquet
        import shutil
        d = AQ / "_base_com_wdo" / "resultados"; d.mkdir(parents=True, exist_ok=True)
        for x in VOT4:
            shutil.copy(BASE / "resultados" / f"{x}.csv", d / f"{x}.csv")
        w = eventos[eventos.estrategia == WDO][["estrategia", "entrada", "saida", "lado", "preco_entrada", "preco_saida", "motivo", "pontos", "rs"]].copy()
        w.insert(4, "qtd", 1.0)
        w.to_csv(d / f"{WDO}.csv", index=False)
        V.BASE = AQ / "_base_com_wdo"
    V.V = votos; V.IDX = votos.index.values.astype("datetime64[ms]").astype(np.int64); V.N = len(votos)
    V.CLOSE = dados.m1().close.reindex(votos.index).to_numpy(float)
    V.VOTO = {x: votos[f"{x}.voto"].to_numpy(np.int8) for x in ESTR}
    t = V.carrega_trades()
    t = t[(t.estrategia == robo) & na_janela(pd.to_datetime(t.entrada, format="mixed"))].reset_index(drop=True)
    prep = V.prepara(t)
    cond = V.conds(V.VOTO)
    ks = V.primeiro(prep, t, cond, var, p)
    d, px, tsn = V.diffs_de_k(prep, t, ks)
    af = ks >= 0
    o = t[["estrategia", "entrada", "saida", "lado", "preco_entrada", "preco_saida", "motivo"]].copy()
    o.insert(4, "qtd", 1.0)
    o.loc[af, "saida"] = [str(dados.ts(x)) for x in tsn[af]]
    o.loc[af, "preco_saida"] = px[af]
    o.loc[af, "motivo"] = "virada_" + var + p
    o["pontos"] = t.lado * (o.preco_saida - o.preco_entrada); o["rs"] = np.round(o.pontos * RS_PT, 2)
    o["entrada"] = pd.to_datetime(o.entrada, format="mixed"); o["saida"] = pd.to_datetime(o.saida, format="mixed")
    return o[COLS].reset_index(drop=True), dict(prep=prep, t=t, ks=ks, p=p, delta_real=float(d.sum()), afetadas=int(af.sum()))


def _ctrl_e(estado, n, seed):
    V = mods["virada"]
    rng = np.random.default_rng(seed)
    return np.array([V.sorteio_instante(estado["prep"], estado["t"], estado["ks"], estado["p"], rng).sum() for _ in range(n)])


# =============================================================================== C13 (A2, gatilho)
def _core_c13(votos, eventos, resultados, dados, com_wdo=False):
    cg = mods["cg"]
    VOT = VOT5 if com_wdo else VOT4
    cg.VOT = VOT
    old = cg.pd; cg.pd = _Pd(votos)
    try:
        P = cg.prepara()
    finally:
        cg.pd = old
    rows, lados = cg.gatilhos(P)

    def com_chave(df):
        if len(df):
            df["mes_ent"] = mk(df.entrada); df["mes_sai"] = mk(df.saida)
        return df
    trs = {}
    for c in cg.CELLS:
        trs[c] = com_chave(cg.rodar(P, rows, lados, lambda m, c=c: c))
    esc = {}
    for m in MESES:
        best = cg.DEFAULT_CELL
        sc = {}
        for c in cg.CELLS:
            d = trs[c]
            sc[c] = (d[d.mes_sai < m].rs - CUSTO).sum() if len(d) else 0.0
        if any(len(trs[c][trs[c].mes_sai < m]) for c in cg.CELLS):
            best = max(cg.CELLS, key=lambda c: (sc[c], -cg.CELLS.index(c)))
        esc[m] = best

    def compoe(trd):
        parts = [trd[esc[m]][trd[esc[m]].mes_ent == m] for m in MESES]
        parts = [x for x in parts if len(x)]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(trs[cg.CELLS[0]].columns))
    wf = compoe(trs)
    out = pd.DataFrame(dict(estrategia="ConsensoGatilho", entrada=wf.entrada, saida=wf.saida, lado=wf.lado, qtd=1.0,
                            preco_entrada=wf.preco_entrada, preco_saida=wf.preco_saida, motivo=wf.motivo, pontos=wf.pontos, rs=wf.rs))
    out = out.sort_values("entrada").reset_index(drop=True)
    return out[COLS], dict(P=P, rows=rows, lados=lados, esc=esc, cells=sorted(set(esc.values())), n_gatilhos=len(rows), trs=trs)


def _ctrl_c13_um(estado, seed):
    cg = mods["cg"]
    rng = np.random.default_rng(seed)
    ld = rng.choice([-1.0, 1.0], len(estado["rows"]))
    esc = estado["esc"]
    soma = 0.0; n = 0
    por_cel = {c: cg.rodar(estado["P"], estado["rows"], ld, lambda m, c=c: c) for c in estado["cells"]}
    for m in MESES:
        d = por_cel[esc[m]]
        if len(d):
            x = d[mk(d.entrada) == m]
            soma += (x.rs - CUSTO).sum(); n += len(x)
    return soma


# =============================================================================== as 13 funcoes
def regra_C1(votos, eventos, resultados, dados, com_wdo=False):  return _core_c1(votos, eventos, resultados, dados, com_wdo)[0]
def regra_C2(votos, eventos, resultados, dados, com_wdo=False):  return _a1(eventos, com_wdo, "comum", "WinCincoMedias")[0]
def regra_C3(votos, eventos, resultados, dados, com_wdo=False):  return _a1(eventos, com_wdo, "individual", "WinDeslocamentoMatinal")[0]
def regra_C4(votos, eventos, resultados, dados, com_wdo=False):  return _a1(eventos, com_wdo, "comum", "WinDeslocamentoMatinal")[0]
def regra_C5(votos, eventos, resultados, dados, com_wdo=False):  return _core_e(votos, eventos, resultados, dados, com_wdo, "Win", "V2", "b")[0]
def regra_C6(votos, eventos, resultados, dados, com_wdo=False):  return _core_e(votos, eventos, resultados, dados, com_wdo, "Win", "V1", "a")[0]
def regra_C7(votos, eventos, resultados, dados, com_wdo=False):  return _core_e(votos, eventos, resultados, dados, com_wdo, "Win", "V1", "b")[0]
def regra_C8(votos, eventos, resultados, dados, com_wdo=False):  return _core_e(votos, eventos, resultados, dados, com_wdo, "WinCincoMedias", "V3", "b")[0]
def regra_C9(votos, eventos, resultados, dados, com_wdo=False):  return _core_e(votos, eventos, resultados, dados, com_wdo, "WinCincoMedias", "V3", "a")[0]
def regra_C10(votos, eventos, resultados, dados, com_wdo=False): return _core_e(votos, eventos, resultados, dados, com_wdo, "WinDeslocamentoMatinal", "V3", "a")[0]
def regra_C11(votos, eventos, resultados, dados, com_wdo=False): return _core_e(votos, eventos, resultados, dados, com_wdo, "WinDeslocamentoMatinal", "V3", "b")[0]
def regra_C12(votos, eventos, resultados, dados, com_wdo=False): return _core_c12(votos, eventos, resultados, dados, com_wdo)[0]
def regra_C13(votos, eventos, resultados, dados, com_wdo=False): return _core_c13(votos, eventos, resultados, dados, com_wdo)[0]

# id -> (robo, descricao, tipo, nome do CSV da frente, escopo no CSV)
CAND = {
    "C1":  ("Win_c1", "B filtro tabela", "filtro", "b_nota/trades/Win_c1_filtro_tabela.csv"),
    "C2":  ("WinCincoMedias", "A1 filtro consenso, comum", "filtro", "a_consenso/trades/A1_filtro_conjunto_comum.csv"),
    "C3":  ("WinDeslocamentoMatinal", "A1 filtro consenso, individual", "filtro", "a_consenso/trades/A1_filtro_conjunto_individual.csv"),
    "C4":  ("WinDeslocamentoMatinal", "A1 filtro consenso, comum", "filtro", "a_consenso/trades/A1_filtro_conjunto_comum.csv"),
    "C5":  ("Win", "E V2b", "saida", "e_saida_virada/trades/V2b.csv"),
    "C6":  ("Win", "E V1a", "saida", "e_saida_virada/trades/V1a.csv"),
    "C7":  ("Win", "E V1b", "saida", "e_saida_virada/trades/V1b.csv"),
    "C8":  ("WinCincoMedias", "E V3b", "saida", "e_saida_virada/trades/V3b.csv"),
    "C9":  ("WinCincoMedias", "E V3a", "saida", "e_saida_virada/trades/V3a.csv"),
    "C10": ("WinDeslocamentoMatinal", "E V3a", "saida", "e_saida_virada/trades/V3a.csv"),
    "C11": ("WinDeslocamentoMatinal", "E V3b", "saida", "e_saida_virada/trades/V3b.csv"),
    "C12": ("WinRetanguloEma34", "B resize pela nota", "resize", "b_nota/trades/WinRetanguloEma34_resize_nota.csv"),
    "C13": ("ConsensoGatilho", "A2 gatilho de consenso WF", "nova", "a_consenso/trades/A2_gatilho_walkforward.csv"),
}


def roda(cid, votos, eventos, resultados, dados, com_wdo=False):
    """-> (trades, estado). Mesma coisa que regra_Ck, mas devolvendo o estado para o controle."""
    a = (votos, eventos, resultados, dados)
    if cid == "C1": return _core_c1(*a, com_wdo)
    if cid == "C2": return _a1(eventos, com_wdo, "comum", "WinCincoMedias")
    if cid == "C3": return _a1(eventos, com_wdo, "individual", "WinDeslocamentoMatinal")
    if cid == "C4": return _a1(eventos, com_wdo, "comum", "WinDeslocamentoMatinal")
    e = {"C5": ("Win", "V2", "b"), "C6": ("Win", "V1", "a"), "C7": ("Win", "V1", "b"), "C8": ("WinCincoMedias", "V3", "b"),
         "C9": ("WinCincoMedias", "V3", "a"), "C10": ("WinDeslocamentoMatinal", "V3", "a"), "C11": ("WinDeslocamentoMatinal", "V3", "b")}
    if cid in e: return _core_e(*a, com_wdo, *e[cid])
    if cid == "C12": return _core_c12(*a, com_wdo)
    if cid == "C13": return _core_c13(*a, com_wdo)
    raise KeyError(cid)


def controle(cid, estado, trades, resultados, n=2000, seed=20261006):
    """Deltas (R$, com custo) de n sorteios nulos contra o original do mesmo robo (C13: soma liquida do sorteio de lado)."""
    robo, _d, tipo, _f = CAND[cid]
    if tipo == "filtro":
        return delta_filtro_sorteio(original_janela(resultados, robo).rs.to_numpy(), len(trades), n, seed)
    if tipo == "saida":
        return _ctrl_e(estado, n, seed)       # delta bruto = delta com custo (mesmo numero de operacoes)
    if tipo == "resize":
        return _ctrl_c12(estado, resultados, n, seed)
    raise ValueError("C13 usa _ctrl_c13_um (em paralelo)")
