"""RODADA 2 (de ate' 3) do refino do candidato `continuidade_diaria_reversal`
em WIN@ (+R$8.832,30 IS, 127 trades, 55,9% acerto -- rodada `continuidade_*`
de 2026-08-27). Aplica os 3 proximos-passos LIMITADOS que o CRITICO da
rodada 1 pediu explicitamente (ver `win_daily_continuidade_refino_
diagnostico.py` e `win_daily_continuidade_refino_variantes.py` para a
rodada 1 inteira -- NAO reabre escopo novo, so' os 3 itens abaixo):

1) SIGNIFICANCIA DIRETA do "achado central" (o tercio "forte" de |retorno
   D-1|, calculado DENTRO de cada metade, inverte de sinal: M1
   R$209,20/trade -> M2 R$-50,54/trade): teste de PERMUTACAO (label-shuffle
   M1/M2 dentro do pool de trades "forte") na diferenca de medias, em vez
   de so' comparar R$/trade agregado. O critico reportou p2s~=0,085 com um
   shuffle de 20.000/seed fixa -- aqui reproduzimos com 5 SEMENTES x 20.000
   tiragens (disciplina desta investigacao: "numero sem dispersao nao e'
   resultado" -- reportar 1 unico shuffle seria exatamente esse erro).

2) CROSS-CHECK REVERSO (resolve a circularidade do refino da rodada 1: os
   cortes de magnitude/vol foram calculados SO' na metade1 e "confirmados"
   olhando a metade2 -- nao e' um teste cego): recalcula os MESMOS cortes
   (mesmo metodo, quantile 2/3) usando SO' a metade2, e aplica esse corte
   (sem reajuste nenhum) tanto na metade1 quanto no periodo INTEIRO. Roda o
   MESMO trio (regra completa, teste de metade, nulo sign-flip) para cada
   corte. Se o corte-de-M2 SO' funciona em M2 (nao estabiliza quando
   aplicado ao periodo/M1 "de tras pra frente") -- assimetria, evidencia de
   artefato/overfitting de direcao. Se funciona nos dois sentidos --
   simetria, evidencia genuina.

   IMPORTANTE (nao e' look-ahead disfarcado): este cross-check calibra um
   corte com dado da metade2 e aplica retroativamente a' metade1/periodo
   inteiro DE PROPOSITO, como diagnostico de simetria -- NUNCA como regra
   candidata a viver ao vivo (uma regra ao vivo real so' pode calibrar com
   passado, como o `ContinuidadeDiariaDirecaoRolante` da rodada 1). Nenhuma
   das duas direcoes deste cross-check e' proposta para producao.

3) CONCENTRACAO: top-1/top-3 trade como % do lucro liquido total, para o
   BASELINE (reproduzido aqui, deve bater 17,0%/43,3% do critico) E para a
   variante MAGNITUDE CAP (corte da metade1, a que "resolve" a
   instabilidade na rodada 1) -- se a variante que estabiliza h1/h2 ainda
   depender de poucos trades de sorte, isso pesa CONTRA promocao mesmo com
   lucro/DD parelho.

Reusa (IMPORTA, nunca copia/cola):
  - `carregar_is_bars` de `continuidade_stats.py`;
  - `CAPITAL_NOCIONAL`, `_config`, `_metade`, `nulo_sign_flip`, `rodar` de
    `continuidade_daily_rule.py`;
  - `ContinuidadeDiaria` de `strategy.daytrade.lab.continuidade_daily`;
  - `ContinuidadeDiariaMagnitudeCap`, `ContinuidadeDiariaVolCap`,
    `CUTOFF_MAGNITUDE_PTS_WIN`, `CUTOFF_VOL_PTS_WIN`, `VOL_JANELA_DIAS_WIN`
    de `strategy.daytrade.lab.win_daily_continuidade_refino` (os cortes
    calculados na metade1, rodada 1 -- usados aqui so' como REFERENCIA de
    comparacao, o corte-de-M2 e' recalculado do zero neste script);
  - `daily_closes`, `daily_range_mediano`, `signal_previous_return`,
    `_trades_diarios` de `win_daily_continuidade_refino_diagnostico.py`
    (rodada 1 -- MESMA formula de magnitude/vol trailing, sem reimplementar
    e arriscar divergir).

NAO edita NENHUM dos arquivos acima. So' WIN@ -- mesmo escopo da rodada 1
("forte candidato" citado pelo dono; WDO@ reversal ja fecha negativo no IS
inteiro)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from continuidade_daily_rule import (  # noqa: E402
    CAPITAL_NOCIONAL,
    _config,
    _metade,
    nulo_sign_flip,
    rodar,
)
from continuidade_stats import carregar_is_bars  # noqa: E402
from win_daily_continuidade_refino_diagnostico import (  # noqa: E402
    _trades_diarios,
    daily_closes,
    daily_range_mediano,
    signal_previous_return,
)
from strategy.daytrade.lab.win_daily_continuidade_refino import (  # noqa: E402
    CUTOFF_MAGNITUDE_PTS_WIN,
    CUTOFF_VOL_PTS_WIN,
    VOL_JANELA_DIAS_WIN,
    ContinuidadeDiariaMagnitudeCap,
    ContinuidadeDiariaVolCap,
)

SYMBOL = "WIN@"
DIRECTION = "reversal"
QUANTIL_TERCIL_FORTE = 2.0 / 3.0  # fronteira medio/forte de um tercil -- MESMO metodo da rodada 1

N_SEEDS_PERMUTACAO = 5
N_PERM_POR_SEMENTE = 20_000
SEED_BASE_PERMUTACAO = 20260827  # data desta rodada, mesma convencao de continuidade_stats.py


# ---------------------------------------------------------------------------
# infra compartilhada entre os 3 itens: alinhar cada trade da regra completa
# a (a) |retorno do dia anterior| e (b) vol trailing, MESMA formula da
# secao 3/4 do diagnostico da rodada 1 -- reimplementado aqui (nao importado
# de dentro de uma funcao privada com efeito colateral) porque a rodada 1
# fez esse alinhamento INLINE dentro de secao_3_magnitude/secao_4_regime_vol
# em vez de expor como funcao reutilizavel; a formula em si (prev_ret.iloc
# [pos-1], trailing_mediano.iloc[pos]) e' copiada byte-a-byte da rodada 1
# para nao divergir.
# ---------------------------------------------------------------------------

def _alinhar_features(df_trades: pd.DataFrame, closes: pd.Series, ranges: pd.Series,
                       meio_data: pd.Timestamp) -> pd.DataFrame:
    df = df_trades.copy()
    prev_ret = signal_previous_return(closes)
    idx_c = closes.index
    sinais = []
    for d in df["data"]:
        pos = idx_c.searchsorted(d)
        sinais.append(prev_ret.iloc[pos - 1] if pos >= 1 else np.nan)
    df["retorno_sinal_pts"] = sinais
    df["retorno_sinal_abs"] = np.abs(df["retorno_sinal_pts"])

    trailing_mediano = ranges.rolling(VOL_JANELA_DIAS_WIN, min_periods=5).median().shift(1)
    idx_r = ranges.index
    vals = []
    for d in df["data"]:
        pos = idx_r.searchsorted(d)
        vals.append(trailing_mediano.iloc[pos] if pos < len(trailing_mediano) else np.nan)
    df["vol_trailing"] = vals

    df["metade"] = np.where(df["data"] < meio_data, "M1", "M2")
    return df


# ---------------------------------------------------------------------------
# 1) SIGNIFICANCIA DIRETA -- permutacao do achado central
# ---------------------------------------------------------------------------

def _welch_t(a: np.ndarray, b: np.ndarray) -> float:
    va, vb = a.var(ddof=1), b.var(ddof=1)
    na, nb = len(a), len(b)
    se = np.sqrt(va / na + vb / nb)
    if se == 0:
        return float("nan")
    return float((a.mean() - b.mean()) / se)


def item_1_permutacao(df_feat: pd.DataFrame) -> dict:
    print(f"\n{'='*100}\n1) SIGNIFICANCIA DIRETA -- permutacao M1-forte vs M2-forte "
          f"(tercil calculado DENTRO de cada metade)\n{'='*100}")

    fortes = []
    for m in ("M1", "M2"):
        sub = df_feat[df_feat["metade"] == m].copy()
        sub["tercil_m"] = pd.qcut(sub["retorno_sinal_abs"], 3, labels=["fraco", "medio", "forte"],
                                   duplicates="drop")
        forte_sub = sub[sub["tercil_m"] == "forte"].copy()
        forte_sub["metade_forte"] = m
        fortes.append(forte_sub)
        print(f"  {m} forte: n={len(forte_sub)}  liquido=R${num_br(float(forte_sub['pnl'].sum()))}  "
              f"R$/trade={num_br(float(forte_sub['pnl'].mean()),2)}")

    pooled = pd.concat(fortes, ignore_index=True)
    n1 = int((pooled["metade_forte"] == "M1").sum())
    n2 = int((pooled["metade_forte"] == "M2").sum())
    pnl = pooled["pnl"].to_numpy(dtype=float)
    labels = pooled["metade_forte"].to_numpy()
    n = len(pnl)

    obs_m1 = pnl[labels == "M1"]
    obs_m2 = pnl[labels == "M2"]
    obs_stat = float(obs_m1.mean() - obs_m2.mean())
    obs_t = _welch_t(obs_m1, obs_m2)
    print(f"\n  pool 'forte' M1+M2: n={n} (n1={n1}, n2={n2})")
    print(f"  estatistica observada: media(M1)-media(M2) = R${num_br(obs_stat,2)}   Welch t={obs_t:.4f}")

    p_valores = []
    for i, seed in enumerate(range(N_SEEDS_PERMUTACAO)):
        rng = np.random.default_rng(SEED_BASE_PERMUTACAO + seed)
        rand = rng.random((N_PERM_POR_SEMENTE, n))
        idx = np.argsort(rand, axis=1)
        grupo1 = pnl[idx[:, :n1]]
        grupo2 = pnl[idx[:, n1:]]
        stats = grupo1.mean(axis=1) - grupo2.mean(axis=1)
        p2s = float((np.abs(stats) >= abs(obs_stat)).mean())
        p_valores.append(p2s)
        print(f"  semente {SEED_BASE_PERMUTACAO+seed}: p2s={num_br(p2s*100,2)}%  "
              f"(={p2s:.4f})  [{N_PERM_POR_SEMENTE} tiragens]")

    media = float(np.mean(p_valores))
    desvio = float(np.std(p_valores))
    print(f"\n  RESUMO (5 sementes x {N_PERM_POR_SEMENTE} tiragens): "
          f"p2s medio={num_br(media*100,2)}%  min={num_br(min(p_valores)*100,2)}%  "
          f"max={num_br(max(p_valores)*100,2)}%  desvio={num_br(desvio*100,3)}%")
    print(f"  {'SIGNIFICANTE' if media < 0.05 else 'NAO significante'} a p<0,05 convencional")

    return {
        "n_pool": n, "n1": n1, "n2": n2, "obs_stat_brl": obs_stat, "obs_welch_t": obs_t,
        "p2s_medio": media, "p2s_min": min(p_valores), "p2s_max": max(p_valores), "p2s_desvio": desvio,
    }


# ---------------------------------------------------------------------------
# 2) CROSS-CHECK REVERSO -- corte calculado SO' na metade2, aplicado a
#    metade1 e ao periodo inteiro
# ---------------------------------------------------------------------------

def _cortes_de_metade2(df_feat: pd.DataFrame) -> tuple[float, float]:
    m2 = df_feat[df_feat["metade"] == "M2"]
    cutoff_mag = float(m2["retorno_sinal_abs"].quantile(QUANTIL_TERCIL_FORTE))
    cutoff_vol = float(m2["vol_trailing"].dropna().quantile(QUANTIL_TERCIL_FORTE))
    return cutoff_mag, cutoff_vol


def _rodar_variante(strat, bars: pd.DataFrame):
    cfg = _config(SYMBOL)
    return run_intraday_backtest(bars, strat, cfg)


def _trio_variante(rotulo: str, strat_factory, bars_full, bars_h1, bars_h2) -> dict:
    print(f"\n--- {rotulo} ---")
    resultado_full = _rodar_variante(strat_factory(), bars_full)
    linha_full = linha_de_resultado(rotulo, resultado_full, CAPITAL_NOCIONAL, capital_nocional=True)
    print(tabela([linha_full]))

    res_h1 = _rodar_variante(strat_factory(), bars_h1)
    res_h2 = _rodar_variante(strat_factory(), bars_h2)
    linha_h1 = linha_de_resultado("metade 1", res_h1, CAPITAL_NOCIONAL, capital_nocional=True)
    linha_h2 = linha_de_resultado("metade 2", res_h2, CAPITAL_NOCIONAL, capital_nocional=True)
    print(tabela([linha_h1, linha_h2]))

    liquido_real, percentis = nulo_sign_flip(resultado_full)
    media_pct = float(np.mean(percentis)) if percentis else float("nan")
    if percentis:
        print(f"  nulo sign-flip: percentis " + ", ".join(f"{num_br(p,2)}%" for p in percentis)
              + f"   media={num_br(media_pct,2)}%")
    else:
        print("  nulo sign-flip: sem trades")

    return {
        "rotulo": rotulo,
        "full_liquido": linha_full.liquido_brl, "full_lucro_dd": linha_full.lucro_por_dd,
        "full_trades": linha_full.trades, "full_win_pct": linha_full.win_rate_pct,
        "h1_liquido": linha_h1.liquido_brl, "h1_lucro_dd": linha_h1.lucro_por_dd, "h1_trades": linha_h1.trades,
        "h2_liquido": linha_h2.liquido_brl, "h2_lucro_dd": linha_h2.lucro_por_dd, "h2_trades": linha_h2.trades,
        "nulo_percentil_medio": media_pct,
        "h1_e_h2_positivas": bool(linha_h1.liquido_brl > 0 and linha_h2.liquido_brl > 0),
        "resultado_full": resultado_full,
    }


def item_2_crosscheck_reverso(df_feat: pd.DataFrame, bars, bars_h1, bars_h2) -> dict:
    print(f"\n{'='*100}\n2) CROSS-CHECK REVERSO -- corte calculado SO' na metade2, "
          f"aplicado (sem reajuste) a metade1 e ao periodo inteiro\n{'='*100}")

    cutoff_mag_m2, cutoff_vol_m2 = _cortes_de_metade2(df_feat)
    print(f"\ncorte MAGNITUDE (quantile {QUANTIL_TERCIL_FORTE:.4f} de |retorno D-1|, SO' M2): "
          f"{num_br(cutoff_mag_m2,1)}pts   (referencia -- corte-de-M1 da rodada 1: "
          f"{num_br(CUTOFF_MAGNITUDE_PTS_WIN,1)}pts)")
    print(f"corte VOL trailing (quantile {QUANTIL_TERCIL_FORTE:.4f} de range mediano 20d, SO' M2): "
          f"{num_br(cutoff_vol_m2,1)}pts   (referencia -- corte-de-M1 da rodada 1: "
          f"{num_br(CUTOFF_VOL_PTS_WIN,1)}pts)")

    resultados = {}
    resultados["mag_m1"] = _trio_variante(
        "MAGNITUDE CAP -- corte de M1 (rodada 1, referencia)",
        lambda: ContinuidadeDiariaMagnitudeCap(symbol=SYMBOL, direction=DIRECTION,
                                                cutoff_pts=CUTOFF_MAGNITUDE_PTS_WIN),
        bars, bars_h1, bars_h2)
    resultados["mag_m2"] = _trio_variante(
        "MAGNITUDE CAP -- corte de M2 aplicado retroativo (cross-check)",
        lambda: ContinuidadeDiariaMagnitudeCap(symbol=SYMBOL, direction=DIRECTION,
                                                cutoff_pts=cutoff_mag_m2),
        bars, bars_h1, bars_h2)
    resultados["vol_m1"] = _trio_variante(
        "VOL CAP -- corte de M1 (rodada 1, referencia)",
        lambda: ContinuidadeDiariaVolCap(symbol=SYMBOL, direction=DIRECTION,
                                          cutoff_pts=CUTOFF_VOL_PTS_WIN),
        bars, bars_h1, bars_h2)
    resultados["vol_m2"] = _trio_variante(
        "VOL CAP -- corte de M2 aplicado retroativo (cross-check)",
        lambda: ContinuidadeDiariaVolCap(symbol=SYMBOL, direction=DIRECTION,
                                          cutoff_pts=cutoff_vol_m2),
        bars, bars_h1, bars_h2)

    print(f"\n--- resumo comparativo (2): assimetria = corte-de-M2 NAO estabiliza fora de M2 ---")
    print(f"{'variante':<45} {'full R$':>12} {'h1 R$':>11} {'h1 l/DD':>9} {'h2 R$':>11} {'h2 l/DD':>9} "
          f"{'h1&h2>0?':>9} {'trades':>7}")
    for k in ("mag_m1", "mag_m2", "vol_m1", "vol_m2"):
        r = resultados[k]
        print(f"{r['rotulo']:<45} {num_br(r['full_liquido']):>12} {num_br(r['h1_liquido']):>11} "
              f"{num_br(r['h1_lucro_dd']) if r['h1_lucro_dd'] is not None else '—':>9} "
              f"{num_br(r['h2_liquido']):>11} "
              f"{num_br(r['h2_lucro_dd']) if r['h2_lucro_dd'] is not None else '—':>9} "
              f"{'SIM' if r['h1_e_h2_positivas'] else 'nao':>9} {r['full_trades']:>7}")

    return {"cutoff_mag_m2": cutoff_mag_m2, "cutoff_vol_m2": cutoff_vol_m2, "resultados": resultados}


# ---------------------------------------------------------------------------
# 3) CONCENTRACAO -- top-1/top-3 trade como % do liquido total
# ---------------------------------------------------------------------------

def _concentracao(resultado, rotulo: str) -> dict:
    pnls = sorted((t.pnl_brl for t in resultado.trades), reverse=True)
    total = sum(pnls)
    n = len(pnls)
    top1 = pnls[0] if n >= 1 else 0.0
    top3 = sum(pnls[:3]) if n >= 3 else sum(pnls)
    media = total / n if n else float("nan")
    desvio = float(np.std(pnls, ddof=1)) if n > 1 else float("nan")
    pct1 = (top1 / total * 100.0) if total else float("nan")
    pct3 = (top3 / total * 100.0) if total else float("nan")
    print(f"\n  [{rotulo}] n={n} trades  liquido total=R${num_br(total)}")
    print(f"    top-1 trade: R${num_br(top1)}  = {num_br(pct1,1)}% do liquido total")
    print(f"    top-3 trades: R${num_br(top3)}  = {num_br(pct3,1)}% do liquido total")
    print(f"    R$/trade: media={num_br(media,2)}  desvio={num_br(desvio,2)}  "
          f"(desvio {'>' if (not np.isnan(desvio) and desvio > abs(media)) else '<='} media -> "
          f"{'cauda gorda' if (not np.isnan(desvio) and desvio > abs(media)) else 'distribuicao mais concentrada no meio'})")
    return {"rotulo": rotulo, "n": n, "total": total, "top1_brl": top1, "top1_pct": pct1,
            "top3_brl": top3, "top3_pct": pct3, "media_por_trade": media, "desvio_por_trade": desvio}


def item_3_concentracao(resultado_baseline, resultado_magcap_m1) -> dict:
    print(f"\n{'='*100}\n3) CONCENTRACAO -- top-1/top-3 trade como % do lucro liquido total\n{'='*100}")
    c_base = _concentracao(resultado_baseline, "BASELINE continuidade_diaria_reversal")
    c_mag = _concentracao(resultado_magcap_m1, "MAGNITUDE CAP (corte de M1, o que 'resolve' a instabilidade)")
    return {"baseline": c_base, "magnitude_cap": c_mag}


def main() -> None:
    print(f"[win_daily_continuidade_refino_rodada2] {SYMBOL} direction={DIRECTION}")
    bars = carregar_is_bars(SYMBOL)
    bars_h1, bars_h2 = _metade(bars, 1), _metade(bars, 2)
    closes = daily_closes(bars)
    ranges = daily_range_mediano(bars)
    meio_idx = len(closes) // 2
    meio_data = closes.index[meio_idx]
    print(f"IS: {len(closes)} pregoes ({closes.index.min().date()} -> {closes.index.max().date()}); "
          f"corte metade1/metade2 em {meio_data.date()}")

    resultado_full = rodar(SYMBOL, bars, DIRECTION)
    linha_full = linha_de_resultado(f"continuidade_diaria_{DIRECTION}", resultado_full,
                                     CAPITAL_NOCIONAL, capital_nocional=True)
    print("\n=== baseline reproduzido (deve bater R$8.832,30 / 127 trades / 55,9%) ===")
    print(tabela([linha_full]))

    df_trades = _trades_diarios(resultado_full)
    df_feat = _alinhar_features(df_trades, closes, ranges, meio_data)

    # -- item 1 --
    resumo_1 = item_1_permutacao(df_feat)

    # -- item 2 --
    resumo_2 = item_2_crosscheck_reverso(df_feat, bars, bars_h1, bars_h2)

    # -- item 3 --
    resultado_magcap_m1 = resumo_2["resultados"]["mag_m1"]["resultado_full"]
    resumo_3 = item_3_concentracao(resultado_full, resultado_magcap_m1)

    # -------------------------------------------------------------------
    # veredito, seguindo EXATAMENTE a arvore de decisao que o critico da
    # rodada 1 pediu: assimetria em (2) E nao-significancia em (1) ->
    # ABANDON; simetria em (2) E (1) perto de p<0,05 -> considerar PROMOTE
    # do magnitude-cap; caso intermediario -> reportar sem forcar veredito.
    # -------------------------------------------------------------------
    print(f"\n{'='*100}\nVEREDITO (arvore de decisao definida pelo critico da rodada 1)\n{'='*100}")
    sig_1 = resumo_2  # placeholder para leitura
    p_medio = resumo_1["p2s_medio"]
    r = resumo_2["resultados"]
    assimetria_mag = r["mag_m1"]["h1_e_h2_positivas"] and not r["mag_m2"]["h1_e_h2_positivas"]
    assimetria_vol = r["vol_m1"]["h1_e_h2_positivas"] and not r["vol_m2"]["h1_e_h2_positivas"]
    print(f"(1) permutacao do achado central: p2s medio = {num_br(p_medio*100,2)}% "
          f"({'< 5% -> significante' if p_medio < 0.05 else '>= 5% -> NAO significante'})")
    print(f"(2) cross-check reverso MAGNITUDE: corte-M1 estabiliza h1&h2>0? "
          f"{r['mag_m1']['h1_e_h2_positivas']}   corte-M2 (retroativo) estabiliza h1&h2>0? "
          f"{r['mag_m2']['h1_e_h2_positivas']}   -> {'ASSIMETRICO' if assimetria_mag else 'simetrico/ambiguo'}")
    print(f"(2) cross-check reverso VOL: corte-M1 estabiliza h1&h2>0? "
          f"{r['vol_m1']['h1_e_h2_positivas']}   corte-M2 (retroativo) estabiliza h1&h2>0? "
          f"{r['vol_m2']['h1_e_h2_positivas']}   -> {'ASSIMETRICO' if assimetria_vol else 'simetrico/ambiguo'}")
    print(f"(3) concentracao: baseline top-1={num_br(resumo_3['baseline']['top1_pct'],1)}% "
          f"top-3={num_br(resumo_3['baseline']['top3_pct'],1)}%   magnitude-cap top-1="
          f"{num_br(resumo_3['magnitude_cap']['top1_pct'],1)}% top-3="
          f"{num_br(resumo_3['magnitude_cap']['top3_pct'],1)}%")

    if (assimetria_mag or assimetria_vol) and p_medio >= 0.05:
        veredito = ("ABANDON -- edge bruto fraco/ruidoso demais para sobreviver a particao: "
                     "corr lag-1 nunca foi significativa (p2s=0,29 na rodada anterior), o achado "
                     "central (tercio 'forte' M1 vs M2) NAO passa p<0,05 em permutacao formal, e o "
                     "corte que 'resolve' a instabilidade so' funciona calibrado na propria metade "
                     "que ele testa -- assimetria, evidencia de artefato de direcao/overfitting, "
                     "nao de causa real.")
    elif not (assimetria_mag or assimetria_vol) and p_medio < 0.10:
        veredito = ("Considerar PROMOTE do magnitude-cap como candidato -- ainda mais fraco que o "
                     "criterio formal desta investigacao por causa do nulo mais baixo (rodada 1: "
                     "92,9% vs baseline 95,6%), mas o corte se mostrou SIMETRICO (funciona calibrado "
                     "em qualquer metade) e a diferenca central ficou proxima de significancia.")
    else:
        veredito = ("Caso intermediario -- nem os 3 criterios da arvore de decisao do critico "
                     "convergem limpo para ABANDON nem para PROMOTE. Reportar os numeros brutos, "
                     "sem forcar um veredito binario.")
    print(f"\n{veredito}")


if __name__ == "__main__":
    main()
