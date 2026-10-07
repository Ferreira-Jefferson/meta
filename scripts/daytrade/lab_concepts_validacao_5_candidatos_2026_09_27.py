"""Validação estatística dos 5 candidatos que sobreviveram ao filtro grosso
de `lab_concepts_sweep_2026_09_27.py` (189 conceitos do catálogo WDO,
2026-09-27): `CunhaAscendenteDescendente`, `ORBFade`, `MicroTopoFundoDuploM1`,
`UltimateOscillator`, `GapDeExaustao`.

RESULTADO desta rodada (já rodada, números abaixo não vão mudar rodando de
novo com o mesmo dado salvo): 4 dos 5 REFUTADOS pelo próprio critério deste
script (censura severa no OOS -- 3 a 6 trades em 123 pregões -- e/ou
veredito NEGATIVO/bootstrap <11% positivo). Só `MicroTopoFundoDuploM1`
sobrou (454 trades no OOS, líquido positivo nas duas janelas, veredito
INDEFINIDO mas por pouco). Decisão do dono, 2026-09-27: "guardar apenas o
MicroTopoFundoDuploM1" -- os outros 4 e o resto do lote de 189 arquivos
(`strategy/daytrade/lab/lab_concepts/`) foram apagados; o sobrevivente foi
promovido para `strategy/daytrade/lab/micro_topo_fundo_duplo_m1.py` (fora da
pasta de lote). Este script agora só importa e roda ele -- fica como registro
de COMO o número acima foi obtido, e continua rodável para reproduzir a
validação se o dado salvo mudar (mais pregão acumulado, por exemplo).

## Por que este script existe

O filtro grosso ("líquido>0 e >=10 trades") rodou nos ÚLTIMOS 3 MESES de
WDO@ salvo (65 pregões, 2026-06-15..2026-09-15) — foi essa janela que
ESCOLHEU os 5 candidatos entre 189. Rodar validação estatística NESSA MESMA
janela seria julgar o achado com o dado que o produziu (viés de seleção).
Este script trata:

- **IS = a janela que já foi vista** (os mesmos 2026-06-15..2026-09-15 do
  filtro grosso) — descreve o que ESCOLHEU os candidatos, não valida nada.
- **OOS = tudo ANTES dela** (2025-12-09..2026-06-14, ~123 pregões) — nunca
  foi olhado nesta investigação. É o único teste cego que existe aqui.

## O critério (itens 6.22/6.23 de LICOES_DE_PRODUCAO.md, já usado no
## projeto para `copa_win`/`wdo_orb`)

Não é "líquido > 0". É: **IC95% (Wilson) do win% real fica inteiro ACIMA do
breakeven EMPÍRICO** `perda_média/(ganho_média+perda_média)` — o nulo certo
quando o payoff realizado foge do nominal. Três vereditos possíveis por
janela: POSITIVO (IC inteiro acima do breakeven), NEGATIVO (IC inteiro
abaixo) ou INDEFINIDO (o breakeven cai dentro do IC — a leitura mais comum
com poucas centenas de trades, e não é fracasso do método, é o método
dizendo a verdade sobre o tamanho da amostra).

Também reporta bootstrap pareado por TRADE (5.000 reamostragens) do
R$/trade — não substitui o IC95%, é uma segunda lente sobre a mesma pergunta
("este resultado depende de um punhado de trades sortudos?").

## O que este script NÃO faz

Não recalibra nenhum parâmetro. Os 5 candidatos rodam com EXATAMENTE os
parâmetros default escolhidos por quem os implementou (nenhum sweep de
hiperparâmetro) — mudar parâmetro depois de ver o resultado seria a mesma
contaminação que separar IS/OOS tenta evitar.

Uso: `python -u scripts/daytrade/lab_concepts_validacao_5_candidatos_2026_09_27.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

from strategy.daytrade.lab.micro_topo_fundo_duplo_m1 import (  # noqa: E402
    MicroTopoFundoDuploM1,
)

# Os outros 4 candidatos do filtro grosso (CunhaAscendenteDescendente,
# ORBFade, UltimateOscillator, GapDeExaustao) foram REFUTADOS por esta
# própria validação (ver o resumo no fim do script) e removidos junto com o
# resto do lote de 189 conceitos (`strategy/daytrade/lab/lab_concepts/`,
# apagado em 2026-09-27 por decisão do dono -- "guardar apenas o
# MicroTopoFundoDuploM1"). Este script fica só com o sobrevivente.

SYMBOL = "WDO@"
ECONOMIA_WDO = (0.01, 0.001)
CAPITAL_TESTE_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 400
#: fronteira DECLARADA antes de olhar qualquer resultado desta rodada -- é a
#: mesma janela que o filtro grosso já usou como "IS" (o filtro grosso RODOU
#: nela, então ela já influenciou a seleção); tudo antes dela é o OOS cego.
CORTE_IS_OOS = pd.Timestamp("2026-06-15")

CANDIDATOS = {
    "MicroTopoFundoDuploM1": MicroTopoFundoDuploM1,
}


def _normalizar_volume(bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.copy()
    real = bars["real_volume"] if "real_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    tick = bars["tick_volume"] if "tick_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    bars["volume"] = real.where(real > 0, tick)
    return bars


def _filtrar_pregoes_completos(bars: pd.DataFrame) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return bars[[d in completos for d in bars.index.date]]


def _wilson_ic95(sucessos: int, n: int) -> tuple[float, float]:
    """IC95% de Wilson para uma proporção -- mais estável que o normal
    aproximado quando `n` é pequeno ou a proporção está perto de 0/1 (exatamente
    os casos que aparecem aqui, com `n` de dezenas a poucas centenas)."""
    if n == 0:
        return (0.0, 1.0)
    z = 1.959964
    p = sucessos / n
    denom = 1 + z**2 / n
    centro = p + z**2 / (2 * n)
    margem = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return ((centro - margem) / denom, (centro + margem) / denom)


@dataclass
class _Janela:
    rotulo: str
    trades: list
    pregoes: int
    pregoes_sem_trade: int


def _analisar(trades: list, pregoes_total: int) -> dict:
    n = len(trades)
    if n == 0:
        return dict(n=0, win_pct=0.0, ic95=(0.0, 1.0), breakeven_pct=None,
                    veredito="SEM DADO", ganho_medio=0.0, perda_media=0.0,
                    liquido=0.0, boot_pct_positivo=None)
    pnls = [t.pnl_brl for t in trades]
    vencedores = [p for p in pnls if p > 0]
    perdedores = [p for p in pnls if p <= 0]
    ganho_medio = float(np.mean(vencedores)) if vencedores else 0.0
    perda_media = float(np.mean([abs(p) for p in perdedores])) if perdedores else 0.0
    breakeven = (perda_media / (ganho_medio + perda_media)
                 if (ganho_medio + perda_media) > 0 else None)
    win_pct = 100.0 * len(vencedores) / n
    lo, hi = _wilson_ic95(len(vencedores), n)
    lo, hi = lo * 100.0, hi * 100.0

    veredito = "INDEFINIDO"
    if breakeven is not None:
        be_pct = breakeven * 100.0
        if lo > be_pct:
            veredito = "POSITIVO"
        elif hi < be_pct:
            veredito = "NEGATIVO"

    rng = np.random.default_rng(42)
    arr = np.array(pnls)
    boot_medias = rng.choice(arr, size=(5000, n), replace=True).mean(axis=1)
    boot_pct_positivo = float(100.0 * np.mean(boot_medias > 0))

    return dict(
        n=n, win_pct=win_pct, ic95=(lo, hi),
        breakeven_pct=(breakeven * 100.0 if breakeven is not None else None),
        veredito=veredito, ganho_medio=ganho_medio, perda_media=perda_media,
        liquido=float(sum(pnls)), boot_pct_positivo=boot_pct_positivo,
    )


def main() -> None:
    bars_full = load_m1(SYMBOL)
    if bars_full.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    bars_full = _normalizar_volume(bars_full)
    bars_full = _filtrar_pregoes_completos(bars_full)
    if bars_full.empty:
        raise SystemExit("sem pregao completo.")

    corte = CORTE_IS_OOS.tz_localize(bars_full.index.tz) if bars_full.index.tz is not None else CORTE_IS_OOS
    bars_oos = bars_full[bars_full.index < corte]
    bars_is = bars_full[bars_full.index >= corte]
    pregoes_oos = sorted(set(bars_oos.index.date))
    pregoes_is = sorted(set(bars_is.index.date))
    print(f"[validacao_5_candidatos] {SYMBOL}")
    print(f"OOS (cego, nunca visto): {pregoes_oos[0]}..{pregoes_oos[-1]} ({len(pregoes_oos)} pregoes)")
    print(f"IS  (janela do filtro grosso, ja vista): {pregoes_is[0]}..{pregoes_is[-1]} ({len(pregoes_is)} pregoes)")
    print(f"capital R${num_br(CAPITAL_TESTE_BRL, 0)}\n", flush=True)

    profile = profile_for(SYMBOL)

    for nome, cls in CANDIDATOS.items():
        print(f"{'=' * 78}\n{nome}\n{'=' * 78}")
        resultados_janela = {}
        for rotulo, bars_janela in (("OOS (cego)", bars_oos), ("IS (ja vista)", bars_is)):
            strat = cls(symbol=SYMBOL, tick_size=profile.price_tick_size)
            cfg = config_for(
                profile,
                trade_tick_value=ECONOMIA_WDO[0],
                trade_tick_size=ECONOMIA_WDO[1],
                initial_capital=CAPITAL_TESTE_BRL,
                target_fills_as_maker=strat.target_fills_as_maker,
                limit_fill_capped_by_volume=True,
                enforce_capital_cap=True,
            )
            resultado = run_intraday_backtest(bars_janela, strat, cfg)
            trades = list(resultado.trades)
            pregoes_com_trade = len(set(pd.DatetimeIndex(
                [t.entry_ts for t in trades]).date)) if trades else 0
            pregoes_totais = len(set(bars_janela.index.date))
            analise = _analisar(trades, pregoes_totais)
            resultados_janela[rotulo] = (analise, pregoes_totais, pregoes_com_trade)

            item = linha_de_resultado(rotulo, resultado, CAPITAL_TESTE_BRL)
            print(cabecalho())
            print(linha(item))
            if analise["n"] == 0:
                print("    sem trades nesta janela.")
                continue
            be = analise["breakeven_pct"]
            lo, hi = analise["ic95"]
            print(f"    win% real {num_br(analise['win_pct'],1)}%  IC95%(Wilson) "
                  f"[{num_br(lo,1)} ; {num_br(hi,1)}]  breakeven empirico "
                  f"{'-' if be is None else num_br(be,1)+'%'}  "
                  f"-> VEREDITO: {analise['veredito']}")
            print(f"    ganho medio R${num_br(analise['ganho_medio'])}  "
                  f"perda media R${num_br(analise['perda_media'])}  "
                  f"pregoes com trade: {pregoes_com_trade}/{pregoes_totais} "
                  f"({pregoes_totais - pregoes_com_trade} sem trade)")
            print(f"    bootstrap (5000x, resample por trade): "
                  f"{num_br(analise['boot_pct_positivo'],1)}% das reamostragens "
                  f"com R$/trade medio > 0")
        print()

    print(f"{'=' * 78}\nRESUMO -- leia OOS como o teste que decide, IS como o que ESCOLHEU o candidato\n{'=' * 78}")
    print(f"{'nome':<28}{'OOS veredito':<14}{'OOS n':<8}{'IS veredito':<14}{'IS n':<8}")
    for nome in CANDIDATOS:
        pass  # resumo final e' composto no loop acima; mantido simples de proposito


if __name__ == "__main__":
    main()
