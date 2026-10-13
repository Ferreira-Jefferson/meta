"""Catálogo de estratégias quantitativas: regras 100% objetivas, declaradas.

Cada estratégia é uma "receita de bolo" (a imagem do vídeo): fatores com direção,
filtros de elegibilidade, e o motor faz o resto — ranqueia o universo inteiro,
pega as N melhores, pesos iguais, rebalanceia a cada M meses.

Com mais de um fator, a nota é a MÉDIA DOS PERCENTIS (soma de ranks, como na
Fórmula Mágica): nenhum fator domina por ter escala maior que o outro.

Para criar uma estratégia nova, acrescente uma entrada em ESTRATEGIAS. O nome
de cada coluna é o de `base.Base.painel`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

INDICADORES = {
    "pl_ind": ("P/L", "preço ÷ lucro por ação (LTM)"),
    "ey": ("Earnings yield", "lucro ÷ valor de mercado"),
    "pvp": ("P/VP", "preço ÷ valor patrimonial"),
    "ev_ebit": ("EV/EBIT", "valor da firma ÷ EBIT (LTM)"),
    "roe": ("ROE", "lucro ÷ patrimônio líquido"),
    "roic": ("ROIC", "EBIT×(1−34%) ÷ (PL + dívida − caixa)"),
    "roa": ("ROA", "lucro ÷ ativo total"),
    "margem_bruta": ("Margem bruta", "lucro bruto ÷ receita"),
    "margem_ebit": ("Margem EBIT", "EBIT ÷ receita"),
    "margem_liquida": ("Margem líquida", "lucro ÷ receita"),
    "div_liq_pl": ("Dív. líq./PL", "(dívida − caixa) ÷ PL"),
    "dy": ("DY 12m", "proventos 12m ÷ preço"),
    "dy_med_3a": ("DY médio 3a", "média do DY em D, D−1a e D−2a"),
    "mom_12_1": ("Momento 12−1", "retorno de 12 meses sem o último mês"),
    "mom_6": ("Momento 6m", "retorno dos últimos 6 meses"),
    "vol_1a": ("Volatilidade 1a", "desvio-padrão anualizado dos retornos diários"),
    "liquidez": ("Liquidez", "volume financeiro médio de 21 pregões (R$)"),
    "mcap": ("Valor de mercado", "preço × ações (R$)"),
}


@dataclass(frozen=True)
class Fator:
    coluna: str
    maior_melhor: bool
    peso: float = 1.0


@dataclass(frozen=True)
class Estrategia:
    chave: str
    nome: str
    descricao: str
    fatores: tuple[Fator, ...]
    excluir_financeiras: bool = False
    exige_lucro: bool = False
    exige_pagou_3a: bool = False
    origem: str = ""
    filtros_extra: tuple[str, ...] = field(default=())

    def elegiveis(self, p: pd.DataFrame) -> pd.DataFrame:
        if p.empty or any(f.coluna not in p for f in self.fatores):
            return p.iloc[0:0]
        m = pd.Series(True, index=p.index)
        for f in self.fatores:
            m &= p[f.coluna].notna()
        if self.excluir_financeiras:
            m &= ~p.financeira.astype(bool)
        if self.exige_lucro:
            m &= p.lucro_contr > 0
        if self.exige_pagou_3a:
            m &= p.pagou_3a.astype(bool)
        return p[m]

    def nota(self, p: pd.DataFrame) -> pd.Series:
        """Média ponderada dos percentis (1 = melhor do universo)."""
        tot = sum(f.peso for f in self.fatores)
        s = 0.0
        for f in self.fatores:
            s = s + f.peso * p[f.coluna].rank(pct=True, ascending=f.maior_melhor)
        return s / tot

    def ranquear(self, p: pd.DataFrame, liquidez_min: float) -> pd.DataFrame:
        if p.empty or "liquidez" not in p:
            return pd.DataFrame(columns=["ticker", "cnpj", "nota"])
        e = self.elegiveis(p[p.liquidez >= liquidez_min])
        if e.empty:
            return e.assign(nota=pd.Series(dtype=float))
        return e.assign(nota=self.nota(e)).sort_values("nota", ascending=False)


ESTRATEGIAS: dict[str, Estrategia] = {e.chave: e for e in (
    # Primeira (e única até agora) estratégia que passou nas TRÊS etapas: escolhida na
    # busca de 377 combinações usando só o IS, confirmada no OOS (21,3% a.a. vs CDI 10,2%,
    # p=0,005, BH ok) e no VIRGEM em teste único pré-registrado (44,8% a.a. vs Ibov 37,8%
    # e CDI 14,3%, p=0,025). Parâmetros de uso: 10 ações, rebalanceamento a cada 3 meses.
    # Ver quantum/dados/estudos/2026-10-13_virgem/.
    Estrategia("barata_subindo_calma", "Barata, subindo e calma",
               "P/VP baixo + momento de 6 meses + baixa volatilidade. Use 10 ações, rebalanceando a cada 3 meses.",
               (Fator("pvp", False), Fator("mom_6", True), Fator("vol_1a", False)),
               origem="busca 2026-10-12 (finalista nº 1) · confirmada no OOS e no VIRGEM"),
    Estrategia("dy3a", "Dividendos 3 anos",
               "Maior dividend yield médio dos últimos 3 anos, só quem pagou nos 3.",
               (Fator("dy_med_3a", True),), exige_pagou_3a=True,
               origem="exemplo do vídeo (DY médio 3a, 14,2% a.a. 2013–2024 segundo o autor)"),
    Estrategia("valor_momento", "Valor + Momento",
               "Barata (lucro alto sobre o preço) e subindo (momento 12−1).",
               (Fator("ey", True), Fator("mom_12_1", True)), exige_lucro=True,
               origem="vídeo cita 'valor momento' com 2 indicadores sem dizê-los; esta é a combinação clássica da literatura"),
    Estrategia("formula_magica", "Fórmula Mágica",
               "Greenblatt: EV/EBIT baixo + ROIC alto. Exclui bancos e seguradoras.",
               (Fator("ev_ebit", False), Fator("roic", True)), excluir_financeiras=True,
               origem="Greenblatt (2006)"),
    Estrategia("roic", "ROIC alto",
               "Maior retorno sobre o capital investido (exemplo do vídeo).",
               (Fator("roic", True),), excluir_financeiras=True, origem="exemplo do vídeo"),
    Estrategia("pl_baixo", "P/L baixo", "Menor preço sobre lucro, só empresas lucrativas.",
               (Fator("pl_ind", False),), exige_lucro=True, origem="hipótese 'ações baratas' do vídeo"),
    Estrategia("pvp_baixo", "P/VP baixo", "Menor preço sobre valor patrimonial.",
               (Fator("pvp", False),), origem="hipótese 'ações baratas' do vídeo"),
    Estrategia("ev_ebit_baixo", "EV/EBIT baixo", "Menor valor da firma sobre EBIT.",
               (Fator("ev_ebit", False),), excluir_financeiras=True, origem="hipótese 'ações baratas' do vídeo"),
    Estrategia("momento", "Momento 12−1", "Maior retorno de 12 meses, pulando o último mês.",
               (Fator("mom_12_1", True),), origem="Jegadeesh & Titman (1993)"),
    Estrategia("qualidade", "Qualidade", "ROE alto + margem líquida alta + pouca dívida.",
               (Fator("roe", True), Fator("margem_liquida", True), Fator("div_liq_pl", False)),
               excluir_financeiras=True, origem="fator qualidade (Novy-Marx, Asness)"),
    Estrategia("baixa_vol", "Baixa volatilidade", "Menor volatilidade dos últimos 12 meses.",
               (Fator("vol_1a", False),), origem="anomalia de baixa volatilidade"),
)}
