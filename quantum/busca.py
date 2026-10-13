"""Busca da combinação de indicadores que melhor escolhe as melhores empresas.

Pedido do dono (2026-10-12): "usar 100 empresas pra fazer a combinação que achar
mais assertiva... descobrir as melhores empresas, e dependendo do caso usar até
mais empresas para montar a carteira mais assertiva pro mercado brasileiro".

O QUE É TESTADO
  13 indicadores, cada um com DIREÇÃO FIXADA PELA TEORIA (nunca estimada nos dados):
  todas as combinações de 1, 2 e 3 deles (377), nota = média dos percentis (pesos
  iguais), carteira de N ∈ {10, 20, 30, 50, 100} ações, rebalanceamento a cada
  {3, 6, 12} meses → 377 × 15 = 5.655 backtests.

  Por que pesos iguais e sinal fixo: neste mesmo repo, pesos aprendidos sobre muitas
  perguntas não sobreviveram à troca de regime (correlação de pesos entre períodos
  entre 0,02 e −0,29); contagem simples com sinal fixado de antemão foi mais robusta.

REGRAS DE ESCOLHA — escritas ANTES de rodar, não mudar depois de ver resultado
  1. A busca inteira usa SÓ o IS (2013–2020).
  2. Nota da combinação = MEDIANA do Sharpe nas suas 15 células (N × rebal.), não a
     melhor célula. Uma combinação boa é uma REGIÃO boa; célula isolada é sorte.
  3. Filtro de estabilidade: a mediana, entre as 15 células, do PIOR excesso de CAGR
     sobre o Ibovespa nas duas metades do IS (2013–2016 e 2017–2020) tem de ser > 0 —
     a combinação precisa ter vencido o MERCADO nos dois regimes.
     REVISÃO 1 (2026-10-12, feita olhando SÓ o IS): a versão original exigia Sharpe
     sobre o CDI > 0 nas duas metades. Nenhuma das 377 passou — em 2013–2016 a bolsa
     perdeu do CDI de 11–14% e nenhuma carteira de ações conseguiria; o filtro media o
     regime, não a combinação. Nenhum resultado OOS por combinação foi olhado antes da
     revisão (só a correlação agregada do diagnóstico, 0,32).
  4. Finalistas = as 5 maiores notas que passam no filtro. Para cada uma, a célula é
     a de maior Sharpe no IS entre as 15 dela.
  5. Só as 5 finalistas vão ao OOS, com nulo (sorteio) e Benjamini-Hochberg sobre 5.
  6. Diagnóstico (não decide nada): correlação de Spearman entre o Sharpe IS e o
     Sharpe OOS de TODAS as 377 combinações na célula escolhida. Perto de zero =
     o passado não ordena o futuro e a busca inteira não vale; isso é dito, não escondido.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from datetime import datetime

import numpy as np
import pandas as pd

from . import armazem, config, metricas

FATORES = (  # (coluna, maior_melhor)
    ("ey", True), ("pvp", False), ("ev_ebit", False), ("roe", True), ("roic", True),
    ("margem_liquida", True), ("div_liq_pl", False), ("dy", True), ("dy_med_3a", True),
    ("mom_12_1", True), ("mom_6", True), ("vol_1a", False), ("mcap", False),
)
GRADE_N = (10, 20, 30, 50, 100)
GRADE_MESES = (3, 6, 12)
MAX_FATORES = 3
N_FINALISTAS = 5
METADE_IS = "2016-12-31"

_B = None   # Base por processo (inicializada uma vez em cada trabalhador)
_P = None


def combinacoes() -> list[tuple[tuple[str, bool], ...]]:
    out = []
    for k in range(1, MAX_FATORES + 1):
        out.extend(itertools.combinations(FATORES, k))
    return out


def nome_combo(combo) -> str:
    return " + ".join(f"{c}{'↑' if m else '↓'}" for c, m in combo)


def _estrategia(combo):
    from .estrategias import Estrategia, Fator
    return Estrategia("busca:" + nome_combo(combo), nome_combo(combo), "busca",
                      tuple(Fator(c, m) for c, m in combo))


def _sharpe(s: pd.Series, cdi: pd.Series) -> float:
    s = s.dropna()
    if len(s) < 30:
        return np.nan
    rc = s.pct_change().dropna()
    exc = rc - cdi.reindex(s.index).ffill().pct_change().reindex(rc.index).fillna(0)
    return float(exc.mean() / exc.std() * np.sqrt(metricas.DIAS_ANO)) if exc.std() > 0 else np.nan


def _excesso(s: pd.Series, ibov: pd.Series) -> float:
    """CAGR da carteira menos CAGR do Ibovespa no mesmo trecho."""
    s = s.dropna()
    if len(s) < 30:
        return np.nan
    return metricas._cagr(s) - metricas._cagr(ibov.reindex(s.index).ffill())


def _resumo(r, b) -> dict:
    s = r.serie.dropna()
    ops = r.operacoes
    return {
        "sharpe": _sharpe(s, b.cdi),
        "cagr": metricas._cagr(s),
        "max_dd": float((s / s.cummax() - 1).min()),
        "acerto": float((ops.retorno > 0).mean()) if len(ops) else np.nan,
        "bate_ibov": float((ops.retorno > ops.retorno_ibov).mean()) if len(ops) else np.nan,
        "acoes_media": float(r.carteiras.groupby("data_decisao").size().mean()) if len(r.carteiras) else 0.0,
        "sharpe_h1": _sharpe(s.loc[:METADE_IS], b.cdi),
        "sharpe_h2": _sharpe(s.loc[METADE_IS:], b.cdi),
        "excesso_h1": _excesso(s.loc[:METADE_IS], b.ibov),
        "excesso_h2": _excesso(s.loc[METADE_IS:], b.ibov),
    }


def _iniciar():
    global _B, _P
    from .backtest import _Precos
    from .base import Base
    with redirect_stdout(open(os.devnull, "w")):
        _B = Base()
        _P = _Precos(_B)


def _unidade(i: int, combo) -> dict:
    """Uma combinação: 15 células no IS + a célula escolhida no OOS (diagnóstico)."""
    from .backtest import rodar
    from .estudos import _limites
    est = _estrategia(combo)
    ini, fim = _limites("IS", _B)
    celulas = []
    for n in GRADE_N:
        for meses in GRADE_MESES:
            r = rodar(_B, est, n, meses, ini, fim, precos=_P)
            celulas.append({"n": n, "meses": meses, **_resumo(r, _B)})
    g = pd.DataFrame(celulas)
    pior_metade = g[["excesso_h1", "excesso_h2"]].min(axis=1)
    melhor = g.loc[g.sharpe.idxmax()]
    io, fo = _limites("OOS", _B)
    r_oos = rodar(_B, est, int(melhor.n), int(melhor.meses), io, fo, precos=_P)
    oos = _resumo(r_oos, _B)
    return {"i": i, "combo": [list(x) for x in combo], "nome": nome_combo(combo),
            "nota_is": float(g.sharpe.median()), "estabilidade_is": float(pior_metade.median()),
            "melhor_n": int(melhor.n), "melhor_meses": int(melhor.meses),
            "melhor_is": {k: melhor[k] for k in ("sharpe", "cagr", "max_dd", "acerto", "bate_ibov", "acoes_media")},
            "celulas_is": celulas, "oos_diag": oos}


def rodar_busca(trabalhadores: int | None = None, progresso=print) -> str:
    combos = combinacoes()
    trabalhadores = trabalhadores or max(1, (os.cpu_count() or 2))
    nome = datetime.now().strftime("%Y-%m-%d_%H%M") + "_busca"
    pasta = config.ESTUDOS / nome
    pasta.mkdir(parents=True, exist_ok=True)
    progresso(f"busca: {len(combos)} combinações × {len(GRADE_N) * len(GRADE_MESES)} células, {trabalhadores} processos")
    t0 = time.time()
    res = []
    with ProcessPoolExecutor(max_workers=trabalhadores, initializer=_iniciar) as ex:
        futuros = {ex.submit(_unidade, i, c): i for i, c in enumerate(combos)}
        for k, f in enumerate(as_completed(futuros), start=1):
            r = f.result()
            res.append(r)
            # só o IS é impresso durante a busca: o OOS de cada combinação é diagnóstico
            progresso(f"  [{k:3d}/{len(combos)}] {r['nome']:42s} nota IS {r['nota_is']:6.2f} "
                      f"estab. {r['estabilidade_is']:6.2f} · melhor N={r['melhor_n']} {r['melhor_meses']}m "
                      f"({time.time() - t0:5.0f}s)")
    return concluir(res, nome, progresso)


def concluir(res: list[dict], nome: str, progresso=print) -> str:
    from .backtest import _Precos, rodar
    from .base import Base
    from .estudos import _limites, _nulo, _serie_json, benjamini_hochberg
    pasta = config.ESTUDOS / nome
    tab = pd.DataFrame([{"nome": r["nome"], "nota_is": r["nota_is"], "estabilidade_is": r["estabilidade_is"],
                         "n": r["melhor_n"], "meses": r["melhor_meses"],
                         **{f"is_{k}": v for k, v in r["melhor_is"].items()},
                         **{f"oos_{k}": v for k, v in r["oos_diag"].items()}} for r in res])
    tab = tab.sort_values("nota_is", ascending=False)
    tab.to_csv(pasta / "todas_combinacoes.csv", index=False, sep=";", decimal=",")
    pd.DataFrame([{"nome": r["nome"], **c} for r in res for c in r["celulas_is"]]).to_csv(
        pasta / "celulas_is.csv", index=False, sep=";", decimal=",")

    # regras 3 e 4
    candidatas = tab[tab.estabilidade_is > 0]
    finalistas = candidatas.head(N_FINALISTAS)
    rho = float(tab[["is_sharpe", "oos_sharpe"]].corr(method="spearman").iloc[0, 1])
    rho_nota = float(tab[["nota_is", "oos_sharpe"]].corr(method="spearman").iloc[0, 1])
    progresso(f"  diagnóstico: Spearman(Sharpe IS, Sharpe OOS) = {rho:.2f} · (nota IS, Sharpe OOS) = {rho_nota:.2f}")

    b = Base()
    precos = _Precos(b)
    por_nome = {r["nome"]: r for r in res}
    detalhes = []
    for _, f in finalistas.iterrows():
        combo = [tuple(x) for x in por_nome[f.nome]["combo"]]
        est = _estrategia(combo)
        per = {}
        for i, p in enumerate(("IS", "OOS")):
            ini, fim = _limites(p, b)
            r = rodar(b, est, int(f.n), int(f.meses), ini, fim, precos=precos)
            m = metricas.calcular(r.serie, b.ibov, b.cdi, r.operacoes, r.giro)
            nulo = _nulo(b, est, int(f.n), int(f.meses), ini, fim, m["risco"]["sharpe"], precos,
                         config.PREMISSAS.n_sorteios_nulo, seed=2000 + i)
            per[p] = {"metricas": m, "resumo": metricas.resumo(m), "nulo": nulo, "serie": _serie_json(r, b)}
        hoje = est.ranquear(b.painel(b.datas[-1]), config.PREMISSAS.liquidez_min).head(int(f.n))
        detalhes.append({"nome": f.nome, "combo": [list(x) for x in combo], "n": int(f.n), "meses": int(f.meses),
                         "nota_is": float(f.nota_is), "estabilidade_is": float(f.estabilidade_is),
                         "periodos": per, "carteira_hoje": hoje[["ticker", "cnpj", "nota"]].to_dict("records")})
        o = per["OOS"]["resumo"]
        progresso(f"  FINALISTA {f.nome}: N={int(f.n)} {int(f.meses)}m · OOS CAGR {o['cagr']:.1%} "
                  f"Sharpe {o['sharpe']:.2f} p={per['OOS']['nulo']['p_valor']:.3f}")
    bh = benjamini_hochberg({d["nome"]: d["periodos"]["OOS"]["nulo"]["p_valor"] for d in detalhes})
    from .estudos import veredito
    for d in detalhes:
        d["bh_aprovada"] = bool(bh[d["nome"]])
        d["veredito"] = veredito(d, d["bh_aprovada"])

    resultado = {
        "regras": __doc__.split("REGRAS DE ESCOLHA")[1].split("\"\"\"")[0].strip(),
        "n_combinacoes": len(res), "n_celulas": len(res) * len(GRADE_N) * len(GRADE_MESES),
        "spearman_is_oos": rho, "spearman_nota_oos": rho_nota,
        "finalistas": detalhes,
        "top_is": tab.head(30)[["nome", "nota_is", "estabilidade_is", "n", "meses", "is_sharpe", "is_cagr",
                                "is_max_dd", "is_acerto"]].to_dict("records"),
        "dispersao": tab[["nome", "is_sharpe", "oos_sharpe", "nota_is"]].to_dict("records"),
    }
    with armazem.conexao() as con:
        armazem.salvar_estudo(con, nome, "busca", "busca_combinacoes",
                              {"fatores": FATORES, "grade_n": GRADE_N, "grade_meses": GRADE_MESES}, resultado)
    (pasta / "busca.json").write_text(json.dumps(resultado, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    progresso(f"  busca {nome} gravada em {pasta}")
    return nome


if __name__ == "__main__":
    rodar_busca(int(sys.argv[1]) if len(sys.argv) > 1 else None,
                progresso=lambda m: print(m, flush=True))
