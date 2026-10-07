# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 23
(`WinBuscaLucroG23AmplitudeIbov`) -- Fase 3 (fonte EXTERNA), ORQUESTRACAO.md.

Reaproveita `g21_base` (CAPITAL=1.000, censura_separada/ruina_do_resultado/
concentracao_topn/maior_sequencia_perdas/constancia_motor, ja' compostos la'
a partir de g05_base/g13_base/g15_base) -- mesmo molde que g21_base reaproveitou
de g05/g13/g15, nenhuma logica duplicada.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
  OOS-2 = set/2026 (SO' se OOS-1 passar "com folga" -- ver a limitacao de
          cobertura de dado abaixo, que ja ANTECIPA que OOS-2 nao vai rodar
          com a cesta de acoes)
Nunca abre 2025 ou anterior.

## A cesta de acoes liquidas (fonte EXTERNA desta geracao)

`data/raw_intraday/*.parquet` -- 162 acoes da B3, M1, indice em UTC. Esta
base carrega um SUBCONJUNTO de ~24 papeis de alta liquidez/peso no Ibovespa
(os maiores componentes confirmados como presentes nos 162 arquivos --
B3SA3 nao esta' entre os 162, varios outros grandes tambem faltam: ELET3,
PRIO3, RAIZ4, JBSS3, MGLU3, VBBR3, NTCO3 -- usa-se os que EXISTEM, 24 papeis
e' amostra razoavel de amplitude de mercado).

**Cobertura real confirmada (checada papel a papel, nao assumida):** toda a
cesta cobre no minimo 2025-09 a 2026-08-21 -- ou seja, cobre o IS inteiro
(jan-jun/2026) e a MAIOR PARTE do OOS-1 (jul-ago/2026, mas so' ate 21/08,
faltam os ~9 ultimos pregoes de agosto) e NAO cobre nada de set/2026
(OOS-2). Isto e' uma LIMITACAO DECLARADA da fonte de dado, nao um bug: o
OOS-1 desta geracao roda truncado em 21/08/2026 (nunca estende o corte para
"inventar" cobertura), e o OOS-2 esta' estruturalmente fora de alcance com
este dado -- se uma celula for promovida, o relato tem que dizer isso
explicitamente, por instrucao do mandato ("confirme a cobertura de CADA
arquivo antes de prometer OOS-2").

**Fuso.** O indice dos parquets e' UTC; o Brasil nao tem horario de verao
desde 2019, entao BRT = UTC-3 o ano INTEIRO (sem variacao sazonal) -- basta
`tz_convert("America/Sao_Paulo")` e depois `tz_localize(None)` para alinhar
com os timestamps NAIVE (ja em BRT) do `WIN@D_M1...csv` usado pelo resto da
busca. Ver `b3_session_clock_fix` na memoria do projeto para o bug analogo
ja encontrado (e corrigido) noutro robo deste repo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g21_retangulo_1000"))
import g21_base as g21b  # noqa: E402

br = g21b.br
carrega_win = g21b.carrega_win
dias_da_janela = g21b.dias_da_janela
bars_dos_dias = g21b.bars_dos_dias
ic95_wilson = g21b.ic95_wilson
consistencia = g21b.consistencia
CAPITAL = g21b.CAPITAL                      # R$1.000
MARGEM_WIN_BRL = g21b.MARGEM_WIN_BRL        # R$100
CORTE_IS_INICIO = g21b.CORTE_IS_INICIO
CORTE_IS_FIM = g21b.CORTE_IS_FIM
CORTE_OOS1_FIM = g21b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g21b.CORTE_OOS2_FIM
concentracao_topn = g21b.concentracao_topn
maior_sequencia_perdas = g21b.maior_sequencia_perdas
censura_separada = g21b.censura_separada
ruina_do_resultado = g21b.ruina_do_resultado
monta_config = g21b.monta_config

#: Corte REAL de cobertura da cesta de acoes (checado por amostragem em
#: 2026-10-05, ver docstring do modulo) -- NUNCA estender sem reconferir.
CORTE_COBERTURA_CESTA = pd.Timestamp("2026-08-22")  # exclusivo

DIR_CESTA = ROOT / "data" / "raw_intraday"

#: ~24 papeis de alta liquidez/peso confirmados como presentes nos 162
#: arquivos disponiveis (checado por `ls`, nao suposto).
TICKERS_CESTA = [
    "VALE3", "PETR4", "PETR3", "ITUB4", "BBDC4", "BBAS3", "ABEV3", "WEGE3",
    "RENT3", "SUZB3", "BPAC11", "LREN3", "EQTL3", "RADL3", "GGBR4", "CSAN3",
    "HAPV3", "VIVT3", "ITSA4", "CSNA3", "CMIG4", "SBSP3", "RDOR3", "KLBN11",
]

_CACHE: dict = {}


def carrega_cesta() -> dict[str, pd.Series]:
    """Fechamento M1 de cada papel da cesta, indice convertido de UTC para
    BRT NAIVE (ver docstring do modulo sobre o fuso). Cacheado -- carregado
    uma unica vez por processo."""
    if "cesta" in _CACHE:
        return _CACHE["cesta"]
    cesta: dict[str, pd.Series] = {}
    for tk in TICKERS_CESTA:
        caminho = DIR_CESTA / f"{tk}.parquet"
        df = pd.read_parquet(caminho, columns=["close"])
        idx_brt = df.index.tz_convert("America/Sao_Paulo").tz_localize(None)
        s = pd.Series(df["close"].to_numpy(), index=idx_brt).sort_index()
        s = s[~s.index.duplicated(keep="first")]
        cesta[tk] = s
    _CACHE["cesta"] = cesta
    return cesta


def cobertura_cesta() -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """(min, max) de cada papel da cesta, ja' em BRT -- usado so' para
    CONFERIR a janela antes de prometer qualquer coisa, nunca para decidir
    o sinal."""
    cesta = carrega_cesta()
    return {tk: (s.index.min(), s.index.max()) for tk, s in cesta.items()}


def computa_folego(dias: list, janela_min: int = 15, ffill_limite_min: int = 10,
                    min_fracao_validos: float = 0.5) -> pd.Series:
    """Pre-computa o folego da cesta (`win_busca_lucro_g23_amplitude_ibov.
    folego_ibov`) na GRADE das proprias barras do WIN@ nos `dias` informados
    -- import tardio para nao obrigar quem so' usa helpers genericos (ex.: o
    script de cobertura) a carregar o motor inteiro."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.win_busca_lucro_g23_amplitude_ibov import folego_ibov

    win = bars_dos_dias(carrega_win(), dias)
    grade = win.index
    cesta = carrega_cesta()
    return folego_ibov(cesta, grade, janela_min=janela_min,
                        ffill_limite_min=ffill_limite_min,
                        min_fracao_validos=min_fracao_validos)


def roda(dias_operar: list, janela_min: int = 15, capital: float = CAPITAL,
         congelado: bool = False, **kwargs_estrategia):
    """Devolve `(result, strategy)`. Pre-computa o folego so' com os
    `dias_operar` (a busca do IS so' olha o proprio IS; o OOS-1 congelado
    passa so' os dias do OOS-1 -- o folego e' CAUSAL dentro de cada dia, nao
    acumula historia entre pregoes, entao nao ha' vazamento IS->OOS-1 aqui,
    diferente do quantil causal da G4)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g23_amplitude_ibov_congelado_v23 import (
            WinBuscaLucroG23AmplitudeIbov as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g23_amplitude_ibov import (
            WinBuscaLucroG23AmplitudeIbov as Estrategia,
        )

    folego = computa_folego(dias_operar, janela_min=janela_min)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(folego=folego, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat
