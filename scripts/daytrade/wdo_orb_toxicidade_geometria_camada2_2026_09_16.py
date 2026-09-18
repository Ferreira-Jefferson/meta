"""AJUSTE DE GEOMETRIA POS-TOXICIDADE -- CAMADA 2: sanidade no robo real
(2026-09-16).

## O que este script e', e o que ele NAO e'

Isto e' so' SANIDADE PRATICA (~10 operacoes reais do `wdo_orb` em 5 pregoes)
-- n pequeno demais para provar qualquer coisa sozinho. A prova (ou a
refutacao) mora na Camada 1 (`wdo_orb_toxicidade_geometria_camada1_2026_09_16.py`),
que simula MILHARES de corridas alvo/stop genericas por pregao e tem poder
estatistico de verdade. Aqui so' confirmamos que o mecanismo (ajustar
`alvo_ticks` na criacao da ordem, sem tocar em mais nada do robo) funciona
de ponta a ponta no motor real, e olhamos se o punhado de trades reais
concorda ou destoa da Camada 1.

## Os dois ajustes (mesmos das hipoteses H_A e H_C da Camada 1)

  HA -- quando a ordem (rompimento OU fade) nasce durante uma janela de
        toxicidade ALTA (mesmo corte/janela de 120s ja' calibrado e
        congelado em 08-28), o alvo daquela entrada e' multiplicado por
        `FATOR_HA` (0,75 -- a razao medida de contracao do range). Stop,
        offset, prazo, fade -- nada mais muda.
  HC -- alvo escalado CONTINUAMENTE pelo percentil de toxicidade do dia no
        instante do sinal (`alvo x (1 - 0,5 x percentil)`), piso de 2 ticks.
        Fora de qualquer janela de pico (percentil baixo), o ajuste e'
        proximo de zero -- nao e' "liga/desliga" como o HA.

O mecanismo: subclasse de `WdoOrb` que so' sobrescreve `_ordem` (o metodo
PURO que recebe `stop_ticks, alvo_ticks` ja' calculados por `_geometria()` e
constroi a `EnterLimit`) -- ajusta `alvo_ticks` ali, ANTES de chamar
`super()._ordem(...)`. Mais simples e mais fiel que interceptar a acao
depois de criada (como o veto fazia): aqui a ordem NASCE com o alvo certo,
em vez de nascer errada e ser descartada/reescrita.

## Dado -- a MESMA limitacao das duas pecas anteriores desta investigacao

So' 5 pregoes com `flags` confiavel: 2026-08-28 (exploracao) e 2026-09-08..11
(confirmacao). NAO e' a IS/OOS oficial de 72/51 pregoes do `wdo_orb`.

Uso: `python -u scripts/daytrade/wdo_orb_toxicidade_geometria_camada2_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wdo_orb_toxicidade_fluxo_veto_2026_09_16 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, DIA_CALIBRACAO, DIAS_CONFIRMACAO, TODOS_OS_DIAS,
    VETO_SEG, WdoOrbInstrumentado, calibra, carregar_ticks_dia,
    gatilhos_de_veto, indice_gatilho_ativo, monta_config,
    negocios_classificados, serie_toxicidade,
)
from wdo_orb_toxicidade_geometria_camada1_2026_09_16 import (  # noqa: E402
    ALVO_MIN_TICKS, FATOR_HA, K_HC,
)

SAIDA = RAIZ / "scratch" / "wdo_orb_toxicidade_geometria_camada2_2026_09_16"


# ---------------------------------------------------------------------------
# duas subclasses -- so' `_ordem` muda, nada mais
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbAjustaAlvoHA(WdoOrbInstrumentado):
    """Alvo x FATOR_HA quando a ordem nasce dentro de uma janela de
    toxicidade ALTA (120s pos-pico). Fora da janela, identico ao robo de
    producao."""

    ativo: bool = True
    _gatilhos: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"),
                                   init=False, repr=False)
    _ajustes: list = field(default_factory=list, init=False, repr=False)

    def _ordem(self, side, limite, stop_ticks, alvo_ticks, reason):
        if self.ativo and indice_gatilho_ativo(self._ts_corrente, self._gatilhos) >= 0:
            alvo_ajustado = max(ALVO_MIN_TICKS, round(alvo_ticks * FATOR_HA))
            self._ajustes.append({
                "ts": self._ts_corrente, "reason": reason, "side": side,
                "alvo_original": alvo_ticks, "alvo_ajustado": alvo_ajustado,
            })
            alvo_ticks = alvo_ajustado
        return super()._ordem(side, limite, stop_ticks, alvo_ticks, reason)


@dataclass
class WdoOrbAjustaAlvoHC(WdoOrbInstrumentado):
    """Alvo x (1 - K_HC x percentil_toxicidade_do_dia) no instante do sinal --
    regua CONTINUA, sem corte binario. Percentil 0 (sem info de toxicidade
    ainda, ou mercado calmo) => ajuste ~0; percentil 1 (pico maximo do dia)
    => alvo reduzido pela metade (K_HC=0,5), nunca abaixo de ALVO_MIN_TICKS."""

    _tox_times_ns: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int64),
                                       init=False, repr=False)
    _tox_vals_ordenados: np.ndarray = field(default_factory=lambda: np.array([], dtype=float),
                                             init=False, repr=False)
    _tox_vals: np.ndarray = field(default_factory=lambda: np.array([], dtype=float),
                                   init=False, repr=False)
    _ajustes: list = field(default_factory=list, init=False, repr=False)

    def _percentil_agora(self) -> float:
        if self._tox_times_ns.size == 0:
            return 0.0
        ts64 = np.datetime64(pd.Timestamp(self._ts_corrente).tz_convert("UTC").tz_localize(None), "ns")
        ts64_i = ts64.astype(np.int64)
        pos = int(np.searchsorted(self._tox_times_ns, ts64_i, side="right")) - 1
        if pos < 0:
            return 0.0
        val = self._tox_vals[pos]
        if np.isnan(val):
            return 0.0
        return float(np.searchsorted(self._tox_vals_ordenados, val) / self._tox_vals_ordenados.size)

    def _ordem(self, side, limite, stop_ticks, alvo_ticks, reason):
        percentil = self._percentil_agora()
        alvo_ajustado = max(ALVO_MIN_TICKS, round(alvo_ticks * (1.0 - K_HC * percentil)))
        if alvo_ajustado != alvo_ticks:
            self._ajustes.append({
                "ts": self._ts_corrente, "reason": reason, "side": side,
                "alvo_original": alvo_ticks, "alvo_ajustado": alvo_ajustado,
                "percentil": round(percentil, 3),
            })
        return super()._ordem(side, limite, stop_ticks, alvo_ajustado, reason)


# ---------------------------------------------------------------------------
# roda 1 pregao -- BASE, HA e HC, mesmo capital real (R$375), mesma barra
# ---------------------------------------------------------------------------

def roda_pregao(dia: str, corte: float, p90_tamanho: float) -> dict:
    ticks = carregar_ticks_dia(dia)
    if ticks.empty:
        return {"dia": dia, "erro": "sem ticks"}
    bars = ticks_to_degenerate_bars(ticks)
    negocios = negocios_classificados(ticks)
    tox = serie_toxicidade(negocios, p90_tamanho)
    gatilhos = gatilhos_de_veto(tox, corte)

    tox_validos = tox.dropna()
    tox_times_ns = tox_validos.index.values.astype("datetime64[ns]").astype(np.int64)
    tox_vals = tox_validos.to_numpy(dtype=float)
    tox_vals_ordenados = np.sort(tox_vals) if tox_vals.size else np.array([], dtype=float)

    strat_base = WdoOrbInstrumentado()
    res_base = run_intraday_backtest(bars, strat_base, monta_config(strat_base, CAPITAL_PARTIDA_BRL))

    strat_ha = WdoOrbAjustaAlvoHA()
    strat_ha._gatilhos = gatilhos
    res_ha = run_intraday_backtest(bars, strat_ha, monta_config(strat_ha, CAPITAL_PARTIDA_BRL))

    strat_hc = WdoOrbAjustaAlvoHC()
    strat_hc._tox_times_ns = tox_times_ns
    strat_hc._tox_vals = tox_vals
    strat_hc._tox_vals_ordenados = tox_vals_ordenados
    res_hc = run_intraday_backtest(bars, strat_hc, monta_config(strat_hc, CAPITAL_PARTIDA_BRL))

    def extrai(nome, strat, res):
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        linhas = []
        caixa = CAPITAL_PARTIDA_BRL
        for t in sorted(res.trades, key=lambda x: x.entry_ts):
            ordem = None
            for o in ordens:
                if o["sinal_ts"] <= t.entry_ts:
                    ordem = o
                else:
                    break
            razao = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
            entry_brt = pd.Timestamp(t.entry_ts).tz_convert("America/Sao_Paulo")
            linhas.append({
                "celula": nome, "data": dia,
                "entrada_brt": entry_brt.strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "alvo_ticks": ordem["alvo_ticks"] if ordem else None,
                "stop_ticks": ordem["stop_ticks"] if ordem else None,
                "pnl_brl": round(t.pnl_brl, 2),
                "exit_reason": razao,
                "caixa_antes": round(caixa, 2),
            })
            caixa += t.pnl_brl
        caixa_min = min([CAPITAL_PARTIDA_BRL] + [l["caixa_antes"] + l["pnl_brl"] for l in linhas])
        return linhas, caixa_min

    linhas_base, caixa_min_base = extrai("BASE", strat_base, res_base)
    linhas_ha, caixa_min_ha = extrai("HA", strat_ha, res_ha)
    linhas_hc, caixa_min_hc = extrai("HC", strat_hc, res_hc)

    def resumo(nome, linhas, caixa_min):
        n = len(linhas)
        liq = sum(l["pnl_brl"] for l in linhas)
        win = 100.0 * sum(1 for l in linhas if l["pnl_brl"] > 0) / n if n else float("nan")
        dd = round(max(0.0, CAPITAL_PARTIDA_BRL - caixa_min), 2)
        return {f"{nome}_trades": n, f"{nome}_liquido": round(liq, 2),
                f"{nome}_win_pct": round(win, 1), f"{nome}_maxdd": dd,
                f"{nome}_caixa_min": round(caixa_min, 2)}

    res_dict = {"dia": dia}
    res_dict.update(resumo("base", linhas_base, caixa_min_base))
    res_dict.update(resumo("ha", linhas_ha, caixa_min_ha))
    res_dict.update(resumo("hc", linhas_hc, caixa_min_hc))
    res_dict["ajustes_ha"] = len(strat_ha._ajustes)
    res_dict["ajustes_hc"] = len(strat_hc._ajustes)

    return {
        "dia": dia, "erro": "",
        "trades": linhas_base + linhas_ha + linhas_hc,
        "ajustes_ha": [{**a, "dia": dia, "ts": pd.Timestamp(a["ts"]).tz_convert("America/Sao_Paulo").strftime("%H:%M:%S")}
                       for a in strat_ha._ajustes],
        "ajustes_hc": [{**a, "dia": dia, "ts": pd.Timestamp(a["ts"]).tz_convert("America/Sao_Paulo").strftime("%H:%M:%S")}
                       for a in strat_hc._ajustes],
        "n_gatilhos_toxicidade": int(gatilhos.size),
        "resumo": res_dict,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    corte, p90_tamanho = calibra()
    print(f"[camada2] toxicidade calibrada em {DIA_CALIBRACAO} (congelada): "
          f"corte={corte:.4f}, p90 tamanho={p90_tamanho:.1f}")
    print(f"[camada2] capital real de partida: R${CAPITAL_PARTIDA_BRL:.2f} | "
          f"FATOR_HA={FATOR_HA} | K_HC={K_HC}\n", flush=True)

    resultados = {}
    with ProcessPoolExecutor(max_workers=min(5, len(TODOS_OS_DIAS))) as pool:
        futuros = {pool.submit(roda_pregao, d, corte, p90_tamanho): d for d in TODOS_OS_DIAS}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            try:
                r = fut.result()
            except Exception as exc:
                print(f"[{dia}] ERRO: {exc!r}", flush=True)
                continue
            resultados[dia] = r
            if r["erro"]:
                print(f"[{dia}] {r['erro']}", flush=True)
                continue
            s = r["resumo"]
            print(f"[{dia}] gatilhos={r['n_gatilhos_toxicidade']:>4} ajustesHA={s['ajustes_ha']:>2} "
                  f"ajustesHC={s['ajustes_hc']:>2} | "
                  f"BASE {s['base_trades']:>2}op win{s['base_win_pct']:>5}% liq R${s['base_liquido']:>9,.2f} caixaMin R${s['base_caixa_min']:>7,.2f} | "
                  f"HA {s['ha_trades']:>2}op win{s['ha_win_pct']:>5}% liq R${s['ha_liquido']:>9,.2f} caixaMin R${s['ha_caixa_min']:>7,.2f} | "
                  f"HC {s['hc_trades']:>2}op win{s['hc_win_pct']:>5}% liq R${s['hc_liquido']:>9,.2f} caixaMin R${s['hc_caixa_min']:>7,.2f}",
                  flush=True)

    ok = {d: r for d, r in resultados.items() if r["erro"] == ""}
    if not ok:
        print("Nenhum pregao produziu dado. Abortando.")
        return

    todas_trades = pd.concat([pd.DataFrame(r["trades"]) for r in ok.values()], ignore_index=True)
    todos_ajustes_ha = pd.concat([pd.DataFrame(r["ajustes_ha"]) for r in ok.values() if r["ajustes_ha"]],
                                  ignore_index=True) if any(r["ajustes_ha"] for r in ok.values()) else pd.DataFrame()
    todos_ajustes_hc = pd.concat([pd.DataFrame(r["ajustes_hc"]) for r in ok.values() if r["ajustes_hc"]],
                                  ignore_index=True) if any(r["ajustes_hc"] for r in ok.values()) else pd.DataFrame()
    todas_trades.to_csv(SAIDA / "trades.csv", index=False, encoding="utf-8")
    todos_ajustes_ha.to_csv(SAIDA / "ajustes_ha.csv", index=False, encoding="utf-8")
    todos_ajustes_hc.to_csv(SAIDA / "ajustes_hc.csv", index=False, encoding="utf-8")

    # ---- contrafactual: quais trades tiveram o alvo REALMENTE mudado ------
    print("\n" + "=" * 100)
    print("QUAIS TRADES O ALVO REALMENTE MUDOU -- casado por (data, entrada_brt)")
    print("=" * 100)
    base = todas_trades[todas_trades.celula == "BASE"].set_index(["data", "entrada_brt"])
    for nome, cel in [("HA", "HA"), ("HC", "HC")]:
        var = todas_trades[todas_trades.celula == cel].set_index(["data", "entrada_brt"])
        comuns = base.index.intersection(var.index)
        mudou = comuns[(base.loc[comuns, "alvo_ticks"].to_numpy()
                        != var.loc[comuns, "alvo_ticks"].to_numpy())]
        print(f"\n{nome}: {len(mudou)}/{len(comuns)} trades com alvo diferente do BASE")
        for idx in mudou:
            b = base.loc[idx]
            v = var.loc[idx]
            print(f"  {idx[0]} {idx[1]} BRT | alvo BASE={b['alvo_ticks']}t (pnl R${b['pnl_brl']:+.2f}, "
                  f"{b['exit_reason']}) -> alvo {nome}={v['alvo_ticks']}t (pnl R${v['pnl_brl']:+.2f}, {v['exit_reason']})")

    # ---- agregado, separando calibracao (autoajustado) de confirmacao -----
    for rotulo, dias in [("CALIBRACAO (08-28, autoajustado -- NAO conta como prova)", [DIA_CALIBRACAO]),
                         ("CONFIRMACAO (09-08..09-11, corte congelado)", DIAS_CONFIRMACAO),
                         ("AGREGADO (5 pregoes)", TODOS_OS_DIAS)]:
        print("\n" + "=" * 100)
        print(rotulo)
        print("=" * 100)
        sub = todas_trades[todas_trades.data.isin(dias)]
        for cel in ("BASE", "HA", "HC"):
            ops = sub[sub.celula == cel]
            n = len(ops)
            liq = ops.pnl_brl.sum()
            win = 100.0 * (ops.pnl_brl > 0).mean() if n else float("nan")
            print(f"  {cel}: {n:>3} trades | liquido R${liq:>10,.2f} | win {win:>5.1f}% | "
                  f"R$/op {liq / n if n else float('nan'):>7.2f}")

    print(f"\n[camada2] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
