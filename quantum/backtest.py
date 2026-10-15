"""Motor de backtest de carteira por ranking (o método do vídeo).

Ciclo, a cada M meses:
  1. DECIDE no fechamento do 1º pregão do mês (D), com o painel de D
     (balanços entregues antes de D, preços até D);
  2. EXECUTA no fechamento do pregão seguinte (D+1) — nunca no mesmo preço
     que gerou o sinal;
  3. pesos iguais nas N primeiras do ranking; os pesos derivam até o próximo
     rebalanceamento (compra e segura, sem rebalancear todo dia);
  4. custo por lado sobre o giro efetivo (|peso novo − peso derivado|).

Ação que para de negociar no meio do período fica parada no último preço
(equivale a sair pelo último negócio). O retorno usa o preço ajustado por
proventos: dividendos reinvestidos, como no estudo do vídeo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .base import Base
from .estrategias import Estrategia


@dataclass
class Resultado:
    serie: pd.Series                  # valor diário da carteira (base 1,0)
    carteiras: pd.DataFrame           # data_decisao, data_execucao, ticker, nota, posicao
    operacoes: pd.DataFrame           # ticker, entrada, saida, retorno, retorno_ibov
    giro: pd.Series                   # giro por rebalanceamento
    params: dict = field(default_factory=dict)


def datas_decisao(base: Base, inicio, fim, meses: int) -> list[pd.Timestamp]:
    out = []
    m = pd.Timestamp(inicio).to_period("M")
    fim = pd.Timestamp(fim)
    while m.to_timestamp() <= fim:
        i = base.datas.searchsorted(m.to_timestamp())
        if i < len(base.datas) and base.datas[i] <= fim:
            out.append(base.datas[i])
        m += meses
    return out


class _Precos:
    """Matriz de preço ajustado com ffill, para as contas de período sem pandas."""

    def __init__(self, base: Base):
        self.adj = base.adj.ffill()
        self.A = self.adj.to_numpy()
        self.col = {t: i for i, t in enumerate(self.adj.columns)}
        self.pos = {d: i for i, d in enumerate(self.adj.index)}
        self.datas = self.adj.index


def _ibov_ret(base: Base, a, b) -> float:
    s = base.ibov
    try:
        return float(s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1)
    except (IndexError, KeyError):
        return np.nan


def rodar(base: Base, est: Estrategia, n: int, meses: int, inicio, fim,
          liquidez_min: float = config.PREMISSAS.liquidez_min,
          custo_lado: float = config.PREMISSAS.custo_lado,
          sorteio: np.random.Generator | None = None,
          precos: _Precos | None = None,
          fatia: tuple[int, int] | None = None) -> Resultado:
    """Roda a estratégia. Com `sorteio`, escolhe N ao ACASO entre os elegíveis
    (o nulo: mesmo universo, mesma quantidade, mesmo calendário)."""
    pr = precos or _Precos(base)
    decisoes = datas_decisao(base, inicio, fim, meses)
    fim_ts = base.pregao_ate(fim)
    execs = [base.pregao_depois(d) for d in decisoes]
    pares = [(d, e) for d, e in zip(decisoes, execs) if e is not None and e <= fim_ts]
    if not pares:
        raise ValueError("período sem datas de rebalanceamento com preço")

    valores, idx_val, carteiras, operacoes, giros = [], [], [], [], []
    v = 1.0
    pesos_derivados: dict[str, float] = {}
    for k, (d, e) in enumerate(pares):
        prox = pares[k + 1][1] if k + 1 < len(pares) else fim_ts
        rank = est.ranquear(base.painel(d), liquidez_min)
        if sorteio is not None:
            escolha = rank.sample(n=min(n, len(rank)), random_state=sorteio) if len(rank) else rank
        elif fatia is not None:  # estudo de fator: k-ésimo de q grupos do ranking
            k_, q_ = fatia
            escolha = rank.iloc[len(rank) * k_ // q_: len(rank) * (k_ + 1) // q_]
        else:
            escolha = rank.head(n)
        tks = [t for t in escolha.ticker if t in pr.col]
        alvo = {t: 1.0 / len(tks) for t in tks} if tks else {}
        giro = sum(abs(alvo.get(t, 0) - pesos_derivados.get(t, 0)) for t in set(alvo) | set(pesos_derivados))
        if k == 0:
            giro = 1.0
        v *= 1 - custo_lado * giro
        giros.append((e, giro))
        i0, i1 = pr.pos[e], pr.pos[prox]
        if tks:
            cols = [pr.col[t] for t in tks]
            bloco = pr.A[i0:i1 + 1, cols] / pr.A[i0, cols]
            curva = np.nanmean(bloco, axis=1)
            rel_fim = bloco[-1]
        else:  # nada elegível: fica em caixa sem rendimento (raro; aparece no giro)
            curva = np.ones(i1 - i0 + 1)
            rel_fim = np.array([])
        trecho = v * curva
        # o primeiro ponto de cada trecho repete o último do anterior
        if valores:
            trecho, datas_tr = trecho[1:], pr.datas[i0 + 1:i1 + 1]
        else:
            datas_tr = pr.datas[i0:i1 + 1]
        valores.extend(trecho)
        idx_val.extend(datas_tr)
        v = float(v * curva[-1]) if len(curva) else v
        tot = np.nansum(rel_fim) if len(rel_fim) else 1.0
        pesos_derivados = {t: float(r / tot) for t, r in zip(tks, rel_fim)} if len(rel_fim) else {}
        r_ibov = _ibov_ret(base, e, prox)
        nota = dict(zip(escolha.ticker, escolha.nota))
        for pos_, (t, r) in enumerate(zip(tks, rel_fim)):
            carteiras.append((d, e, t, nota.get(t), pos_ + 1))
            operacoes.append((t, e, prox, float(r - 1), r_ibov))

    serie = pd.Series(valores, index=pd.DatetimeIndex(idx_val), name="carteira")
    return Resultado(
        serie=serie,
        carteiras=pd.DataFrame(carteiras, columns=["data_decisao", "data_execucao", "ticker", "nota", "posicao"]),
        operacoes=pd.DataFrame(operacoes, columns=["ticker", "entrada", "saida", "retorno", "retorno_ibov"]),
        giro=pd.Series(dict(giros), name="giro"),
        params={"estrategia": est.chave, "n": n, "meses": meses, "inicio": str(pd.Timestamp(inicio).date()),
                "fim": str(pd.Timestamp(fim).date()), "liquidez_min": liquidez_min, "custo_lado": custo_lado},
    )
