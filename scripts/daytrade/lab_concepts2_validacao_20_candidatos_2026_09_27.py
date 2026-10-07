"""Validação estatística dos 20 candidatos que sobreviveram ao filtro grosso
de `lab_concepts2_sweep_2026_09_27.py` (348 conceitos do segundo lote do
catálogo WDO — volume/microestrutura, estatística/quant, regime/adaptação,
exótico/físico/caótico, calendário; ver
`wdo_189_conceitos_tecnicos_price_action_2026_09_27.md` para o histórico do
primeiro lote e o método).

## Por que este script existe (mesmo raciocínio do lote anterior)

O filtro grosso ("líquido>0 e >=10 trades") rodou nos ÚLTIMOS 3 MESES de
WDO@ salvo (65 pregões, 2026-06-15..2026-09-15) — foi essa janela que
ESCOLHEU os 20 candidatos entre 348. Rodar validação estatística NESSA MESMA
janela seria julgar o achado com o dado que o produziu (viés de seleção).

- **IS = a janela que já foi vista** (2026-06-15..2026-09-15) — descreve o
  que ESCOLHEU os candidatos, não valida nada.
- **OOS = tudo ANTES dela** (2025-12-09..2026-06-14, ~123 pregões) — nunca
  foi olhado nesta investigação. É o único teste cego que existe aqui. MESMO
  corte (`CORTE_IS_OOS`) do lote anterior — a mesma amostra de dado salvo.

## O critério (itens 6.22/6.23 de LICOES_DE_PRODUCAO.md)

IC95% (Wilson) do win% real fica inteiro ACIMA do breakeven EMPÍRICO
`perda_média/(ganho_média+perda_média)`. Três vereditos por janela:
POSITIVO, NEGATIVO, INDEFINIDO (breakeven dentro do IC — leitura mais comum
com poucas centenas de trades). Bootstrap por TRADE (5.000 reamostragens)
como segunda lente.

## O que este script NÃO faz

Não recalibra nenhum parâmetro. Os 20 candidatos rodam com EXATAMENTE os
parâmetros default escolhidos pelos agentes que os implementaram.

Uso: `python -u scripts/daytrade/lab_concepts2_validacao_20_candidatos_2026_09_27.py`
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

from strategy.daytrade.lab.lab_concepts2.c302_climax_de_venda import ClimaxDeVenda  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c319_compressao_sequencial_range_volume import (  # noqa: E402
    CompressaoSequencialDeRangeEVolume,
)
from strategy.daytrade.lab.lab_concepts2.c340_absorcao_venda_fundo import AbsorcaoDeVendaNoFundo  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c368_gap_volume_baixo_espera_fechamento import (  # noqa: E402
    GapDeAberturaComVolumeBaixoEsperaFechamento,
)
from strategy.daytrade.lab.lab_concepts2.c372_concentracao_volume_poucas_barras import (  # noqa: E402
    ConcentracaoDeVolumeEmPoucasBarras,
)
from strategy.daytrade.lab.lab_concepts2.c373_correlacao_volume_preco_invertendo import (  # noqa: E402
    CorrelacaoVolumePrecoInvertendoNaJanela,
)
from strategy.daytrade.lab.lab_concepts2.c401_zscore_mad_robusto import ZScoreMADRobusto  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c509_distancia_media_regime import DistanciaMediaRegime  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c521_janela_almoco_lateralizacao import (  # noqa: E402
    JanelaAlmocoLateralizacao,
)
from strategy.daytrade.lab.lab_concepts2.c523_bloqueio_pre_abertura import BloqueioPreAbertura  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c529_inside_bar_sequencial import InsideBarSequencial  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c534_triangulo_convergente import TrianguloConvergente  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c535_filtro_m15_sobre_m1 import FiltroM15SobreM1  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c537_alinhamento_multiescala_ma import (  # noqa: E402
    AlinhamentoMultiEscalaMa,
)
from strategy.daytrade.lab.lab_concepts2.c539_regime_dominante_do_dia import RegimeDominanteDoDia  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c633_complexidade_kolmogorov_aproximada import (  # noqa: E402
    ComplexidadeKolmogorovAproximada,
)
from strategy.daytrade.lab.lab_concepts2.c650_onda_de_wolfe_nao_linear import OndaDeWolfeNaoLinear  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c653_onda_temporal_alternancia import (  # noqa: E402
    OndaTemporalAlternancia,
)
from strategy.daytrade.lab.lab_concepts2.c657_logica_fuzzy_indicadores import LogicaFuzzyIndicadores  # noqa: E402
from strategy.daytrade.lab.lab_concepts2.c705_fechamento_rush_volume import FechamentoRushVolume  # noqa: E402

SYMBOL = "WDO@"
ECONOMIA_WDO = (0.01, 0.001)
CAPITAL_TESTE_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 400
#: mesmo corte do lote anterior -- mesma janela que o filtro grosso usou.
CORTE_IS_OOS = pd.Timestamp("2026-06-15")

CANDIDATOS = {
    "AbsorcaoDeVendaNoFundo": AbsorcaoDeVendaNoFundo,
    "AlinhamentoMultiEscalaMa": AlinhamentoMultiEscalaMa,
    "BloqueioPreAbertura": BloqueioPreAbertura,
    "FiltroM15SobreM1": FiltroM15SobreM1,
    "FechamentoRushVolume": FechamentoRushVolume,
    "DistanciaMediaRegime": DistanciaMediaRegime,
    "OndaTemporalAlternancia": OndaTemporalAlternancia,
    "JanelaAlmocoLateralizacao": JanelaAlmocoLateralizacao,
    "CompressaoSequencialDeRangeEVolume": CompressaoSequencialDeRangeEVolume,
    "ZScoreMADRobusto": ZScoreMADRobusto,
    "TrianguloConvergente": TrianguloConvergente,
    "RegimeDominanteDoDia": RegimeDominanteDoDia,
    "OndaDeWolfeNaoLinear": OndaDeWolfeNaoLinear,
    "ClimaxDeVenda": ClimaxDeVenda,
    "InsideBarSequencial": InsideBarSequencial,
    "ConcentracaoDeVolumeEmPoucasBarras": ConcentracaoDeVolumeEmPoucasBarras,
    "GapDeAberturaComVolumeBaixoEsperaFechamento": GapDeAberturaComVolumeBaixoEsperaFechamento,
    "CorrelacaoVolumePrecoInvertendoNaJanela": CorrelacaoVolumePrecoInvertendoNaJanela,
    "ComplexidadeKolmogorovAproximada": ComplexidadeKolmogorovAproximada,
    "LogicaFuzzyIndicadores": LogicaFuzzyIndicadores,
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
    print(f"[validacao_20_candidatos] {SYMBOL}")
    print(f"OOS (cego, nunca visto): {pregoes_oos[0]}..{pregoes_oos[-1]} ({len(pregoes_oos)} pregoes)")
    print(f"IS  (janela do filtro grosso, ja vista): {pregoes_is[0]}..{pregoes_is[-1]} ({len(pregoes_is)} pregoes)")
    print(f"capital R${num_br(CAPITAL_TESTE_BRL, 0)}\n", flush=True)

    profile = profile_for(SYMBOL)
    resumo: list[dict] = []

    for nome, cls in CANDIDATOS.items():
        print(f"{'=' * 78}\n{nome}\n{'=' * 78}")
        linha_resumo = dict(nome=nome)
        for rotulo, bars_janela, chave in (
            ("OOS (cego)", bars_oos, "oos"), ("IS (ja vista)", bars_is, "is"),
        ):
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

            item = linha_de_resultado(rotulo, resultado, CAPITAL_TESTE_BRL)
            print(cabecalho())
            print(linha(item))
            linha_resumo[f"{chave}_veredito"] = analise["veredito"]
            linha_resumo[f"{chave}_n"] = analise["n"]
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
        resumo.append(linha_resumo)

    print(f"{'=' * 78}\nRESUMO -- leia OOS como o teste que decide, IS como o que ESCOLHEU o candidato\n{'=' * 78}")
    print(f"{'nome':<42}{'OOS veredito':<14}{'OOS n':<8}{'IS veredito':<14}{'IS n':<8}")
    for r in resumo:
        print(f"{r['nome']:<42}{r.get('oos_veredito','-'):<14}{r.get('oos_n',0):<8}"
              f"{r.get('is_veredito','-'):<14}{r.get('is_n',0):<8}")

    saida_csv = ROOT / "scripts" / "daytrade" / "lab_concepts2_validacao_20_candidatos_2026_09_27_resumo.csv"
    pd.DataFrame(resumo).to_csv(saida_csv, index=False)
    print(f"\nresumo salvo em {saida_csv}")


if __name__ == "__main__":
    main()
