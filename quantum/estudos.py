"""Estudos com separação IS / OOS / VIRGEM (pedido do dono, 2026-10-12).

Protocolo de uma rodada, escrito antes de rodar e aplicado igual a toda estratégia:

  1. GRADE NO IS — N ∈ {5,10,15,20,30} × rebalanceamento ∈ {3,6,12} meses,
     medidos SÓ no período de escolha.
  2. ESCOLHA — a célula de maior Sharpe no IS (critério fixo em config). Nada
     do OOS entra nessa escolha.
  3. CONFIRMAÇÃO NO OOS — só a célula escolhida roda no OOS.
  4. NULO — a mesma célula com as N ações SORTEADAS do mesmo universo elegível,
     mesmo calendário. p = fração de sorteios com Sharpe ≥ o da estratégia.
  5. MÚLTIPLOS TESTES — Benjamini-Hochberg (q=0,10) sobre os p do OOS de todas
     as estratégias da rodada. Dez estratégias testadas = dez chances de achar
     uma por sorte; o BH desconta isso.
  6. VIRGEM — trancado. Só roda depois de `revelar_virgem()`, que fica registrado.

O p do IS é mostrado mas NÃO é teste honesto: a célula foi escolhida justamente
por ser a melhor das 15 no IS. Só o OOS testa.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from . import armazem, config, metricas
from .backtest import _Precos, rodar
from .base import Base
from .estrategias import ESTRATEGIAS, Estrategia, Fator


def _limites(nome: str, base: Base) -> tuple[pd.Timestamp, pd.Timestamp]:
    p = config.PERIODO[nome]
    fim = min(pd.Timestamp(p.fim), base.datas[-1])
    return pd.Timestamp(p.inicio), fim


def benjamini_hochberg(pvals: dict[str, float], q: float = config.FDR_Q) -> dict[str, bool]:
    itens = sorted((p, k) for k, p in pvals.items() if p is not None and not np.isnan(p))
    m = len(itens)
    corte = 0
    for i, (p, _) in enumerate(itens, start=1):
        if p <= q * i / m:
            corte = i
    aprovados = {k for _, k in itens[:corte]}
    return {k: (k in aprovados) for k in pvals}


def _nulo(base, est, n, meses, ini, fim, alvo_sharpe, precos, sorteios, seed) -> dict:
    rng = np.random.default_rng(seed)
    sharpes, cagrs = [], []
    for _ in range(sorteios):
        r = rodar(base, est, n, meses, ini, fim, sorteio=rng, precos=precos)
        # só Sharpe e CAGR: os 4Ds completos (ciclos, ano a ano) custariam 400× por estratégia
        s = r.serie.dropna()
        rc = s.pct_change().dropna()
        cdi = base.cdi.reindex(s.index).ffill().pct_change()   # mesma conta de metricas.calcular
        exc = rc - cdi.reindex(rc.index).fillna(0)
        sharpes.append(float(exc.mean() / exc.std() * np.sqrt(metricas.DIAS_ANO)) if exc.std() > 0 else np.nan)
        cagrs.append(metricas._cagr(s))
    sh = np.array(sharpes)
    return {"p_valor": float((np.sum(sh >= alvo_sharpe) + 1) / (len(sh) + 1)),
            "sharpe_nulo_mediana": float(np.nanmedian(sh)),
            "sharpe_nulo_p95": float(np.nanpercentile(sh, 95)),
            "cagr_nulo_mediana": float(np.nanmedian(cagrs)),
            "sorteios": sorteios}


def _serie_json(r, base) -> dict:
    s = r.serie
    ib = base.ibov.reindex(s.index).ffill()
    cd = base.cdi.reindex(s.index).ffill()
    semanal = pd.DataFrame({"carteira": s, "ibov": ib / ib.iloc[0], "cdi": cd / cd.iloc[0]}).resample("W-FRI").last()
    return {"datas": [d.strftime("%Y-%m-%d") for d in semanal.index],
            **{c: [None if pd.isna(v) else round(float(v), 5) for v in semanal[c]] for c in semanal}}


def estudar_estrategia(base: Base, est: Estrategia, precos: _Precos, incluir_virgem: bool,
                       sorteios: int, progresso=print, grade_n: tuple[int, ...] | None = None) -> dict:
    ini_is, fim_is = _limites("IS", base)
    grade = []
    for n in (grade_n or config.GRADE_N):
        for meses in config.GRADE_MESES:
            r = rodar(base, est, n, meses, ini_is, fim_is, precos=precos)
            m = metricas.calcular(r.serie, base.ibov, base.cdi, r.operacoes, r.giro)
            grade.append({"n": n, "meses": meses, **metricas.resumo(m)})
    g = pd.DataFrame(grade)
    escolhida = g.loc[g[config.CRITERIO_ESCOLHA].idxmax()]
    n, meses = int(escolhida.n), int(escolhida.meses)
    progresso(f"    {est.chave}: grade IS feita, escolhida N={n} a cada {meses}m")

    periodos = {}
    nomes = ["IS", "OOS"] + (["VIRGEM"] if incluir_virgem else [])
    for i, nome in enumerate(nomes):
        ini, fim = _limites(nome, base)
        if ini >= fim:
            continue
        r = rodar(base, est, n, meses, ini, fim, precos=precos)
        m = metricas.calcular(r.serie, base.ibov, base.cdi, r.operacoes, r.giro)
        nulo = _nulo(base, est, n, meses, ini, fim, m["risco"]["sharpe"], precos, sorteios, seed=1000 + i)
        ult = r.carteiras[r.carteiras.data_decisao == r.carteiras.data_decisao.max()]
        periodos[nome] = {"metricas": m, "resumo": metricas.resumo(m), "nulo": nulo,
                          "serie": _serie_json(r, base),
                          "ultima_carteira": ult[["ticker", "nota", "posicao"]].to_dict("records"),
                          "operacoes": int(len(r.operacoes)),
                          # quantas ações a carteira REALMENTE teve: com N grande e filtro
                          # restritivo, pode faltar elegível e a carteira vira o universo
                          "acoes_por_rebal": {"media": float(r.carteiras.groupby("data_decisao").size().mean()),
                                              "minimo": int(r.carteiras.groupby("data_decisao").size().min())}}
        progresso(f"    {est.chave} {nome}: CAGR {m['rentabilidade']['cagr']:.1%} vs Ibov "
                  f"{m['rentabilidade']['cagr_ibov']:.1%}, Sharpe {m['risco']['sharpe']:.2f}, p={nulo['p_valor']:.3f}")
    return {"estrategia": est.chave, "nome": est.nome, "grade_is": grade,
            "escolha": {"n": n, "meses": meses, "criterio": config.CRITERIO_ESCOLHA},
            "periodos": periodos}


def veredito(e: dict, aprovada_bh: bool) -> str:
    oos = e["periodos"].get("OOS")
    if not oos:
        return "sem OOS"
    r = oos["resumo"]
    if aprovada_bh and r["excesso_ibov"] > 0 and r["excesso_cdi"] > 0:
        return "confirmada"
    if r["excesso_ibov"] > 0 and r["excesso_cdi"] > 0:
        return "promissora, sem significância"
    return "não confirmada"


def rodada(base: Base | None = None, chaves: list[str] | None = None, sorteios: int | None = None,
           progresso=print, grade_n: tuple[int, ...] | None = None) -> str:
    """Roda o protocolo para as estratégias e grava no banco + dados/estudos/<rodada>/."""
    base = base or Base()
    precos = _Precos(base)
    sorteios = sorteios or config.PREMISSAS.n_sorteios_nulo
    nome_rodada = datetime.now().strftime("%Y-%m-%d_%H%M") + (f"_N{'-'.join(map(str, grade_n))}" if grade_n else "")
    with armazem.conexao() as con:
        virgem = armazem.periodo_revelado(con, "VIRGEM")
    resultados = []
    for chave in (chaves or list(ESTRATEGIAS)):
        progresso(f"  estudando {chave}...")
        resultados.append(estudar_estrategia(base, ESTRATEGIAS[chave], precos, virgem, sorteios, progresso, grade_n))

    pvals = {e["estrategia"]: e["periodos"].get("OOS", {}).get("nulo", {}).get("p_valor") for e in resultados}
    bh = benjamini_hochberg(pvals)
    pasta = config.ESTUDOS / nome_rodada
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = []
    with armazem.conexao() as con:
        for e in resultados:
            e["bh_aprovada"] = bool(bh.get(e["estrategia"], False))
            e["veredito"] = veredito(e, e["bh_aprovada"])
            armazem.salvar_estudo(con, nome_rodada, "protocolo", e["estrategia"],
                                  {"sorteios": sorteios, "virgem": virgem, "grade_n": grade_n or config.GRADE_N,
                                   "premissas": config.PREMISSAS.__dict__}, e)
            for per, d in e["periodos"].items():
                linhas.append({"estrategia": e["estrategia"], "periodo": per, "n": e["escolha"]["n"],
                               "meses": e["escolha"]["meses"], **d["resumo"], "p_nulo": d["nulo"]["p_valor"],
                               "bh_aprovada": e["bh_aprovada"] if per == "OOS" else None,
                               "veredito": e["veredito"]})
            pd.DataFrame(e["grade_is"]).to_csv(pasta / f"grade_is_{e['estrategia']}.csv", index=False, decimal=",", sep=";")
    pd.DataFrame(linhas).to_csv(pasta / "resumo.csv", index=False, decimal=",", sep=";")
    (pasta / "rodada.json").write_text(json.dumps(resultados, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    progresso(f"  rodada {nome_rodada} gravada em {pasta}")
    return nome_rodada


def estudo_fator(base: Base, coluna: str, maior_melhor: bool, periodo: str = "IS",
                 grupos: int = 5, meses: int = 3) -> dict:
    """Quintis de um indicador: o fator separa vencedoras de perdedoras?

    Se o grupo 1 (melhores pelo indicador) não rende mais que o grupo 5 de forma
    monotônica, o indicador não ordena retorno — mesmo que o top-N pareça bom.
    """
    ini, fim = _limites(periodo, base)
    est = Estrategia(f"fator_{coluna}", coluna, "", (Fator(coluna, maior_melhor),))
    precos = _Precos(base)
    saida = []
    for k in range(grupos):
        r = rodar(base, est, 0, meses, ini, fim, precos=precos, fatia=(k, grupos))
        m = metricas.calcular(r.serie, base.ibov, base.cdi, r.operacoes, r.giro)
        saida.append({"grupo": k + 1, **metricas.resumo(m), "serie": _serie_json(r, base)})
    return {"coluna": coluna, "periodo": periodo, "grupos": saida}


def revelar_virgem(motivo: str) -> None:
    with armazem.conexao() as con:
        armazem.revelar_periodo(con, "VIRGEM", motivo)
