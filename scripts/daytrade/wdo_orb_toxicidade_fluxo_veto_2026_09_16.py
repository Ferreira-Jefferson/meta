"""VETO POR TOXICIDADE DE FLUXO (2026-09-16) -- teste pequeno, 5 pregoes.

## O que este script testa

Achado de pesquisa anterior (nao repetido aqui): quando o desequilibrio de
fluxo comprador/vendedor numa janela de 60s fica no TOP DECIL, a volatilidade
dos 2-5 minutos seguintes CAI 3-6x -- o oposto do VPIN classico. Hipotese:
para um robo de ROMPIMENTO como o `wdo_orb`, um rompimento que acontece logo
depois de um pico de toxicidade tem menos chance de continuar ate' o alvo --
vetar a ENTRADA por ~2 minutos depois do pico deveria evitar os rompimentos
mais fracos.

## A limitacao que domina este script -- ler antes de qualquer numero

So' existem 5 pregoes com campo `flags` CONFIAVEL (variando de verdade, nao
constante): 2026-08-28 (sozinho) e 2026-09-08..11 (4 pregoes). O parquet
canonico que cobre a IS/OOS oficial do `wdo_orb` (fev-ago) tem `flags`
constante -- e' LIXO para classificar comprador/vendedor, entao nao entra
aqui. Consequencia:

  * o corte de "top decil de toxicidade" e' calibrado SO' no dia 08-28
    (tratado como exploracao/IS) e congelado;
  * o MESMO corte, sem recalibrar, e' aplicado aos 4 pregoes de 09-08 a
    09-11 (a "confirmacao", mesmo sendo so' 4 dias -- NAO e' a OOS oficial
    de 51 pregoes);
  * o proprio 08-28 e' reportado separado, deixado claro que e'
    autoajustado (referencia, nao prova).

NAO e' a IS/OOS oficial de 72/51 pregoes do `wdo_orb`. E' um teste pequeno
em 5 pregoes com dado real de flags -- o veredito tem de ser do tamanho da
amostra, nao do tamanho da hipotese.

## Decisao de dado: por que NAO uniu canonico + arquivo de flags por join

`WDO_A_.parquet` (canonico) cobre so' ate' 2026-09-04 -- para 09-08..11 ele
NAO TEM dado nenhum, entao o unico caminho possivel ja' e' usar
`WDO_A_semana_2026_09_08.parquet`. Para 08-28 o canonico TEM dado
(min/max de `last` identicos: 5160,0-5232,5 nos dois arquivos), mas
`WDOU26_2026_08_28.parquet` tem 140.935 negocios contra 132.420 do canonico
para o mesmo dia -- os precos batem, a CONTAGEM nao. Juntar os dois por join
de timestamp arriscaria desalinhar ordem/duplicar/perder ticks sem
necessidade nenhuma, ja' que o arquivo de flags SOZINHO ja' tem tudo que o
motor precisa (bid/ask/last/volume/volume_real/flags). Caminho escolhido:
**alimentar o motor DIRETO com os dois arquivos de flags boas** -- 08-28 de
`WDOU26_2026_08_28.parquet`, 09-08..11 de `WDO_A_semana_2026_09_08.parquet`
-- e usar o MESMO stream de ticks (em memoria, sem reler) tanto para montar
as barras do motor quanto para calcular a serie de toxicidade. Isso elimina
o risco de desalinhamento por join: preco e toxicidade vem exatamente do
mesmo negocio, sempre.

## Como a toxicidade e' calculada -- causal, terminando em "agora"

Para cada NEGOCIO classificavel (`flags & 32` = agressor comprador XOR
`flags & 64` = agressor vendedor -- ticks so' de cotacao ou com as duas
flags juntas, ~8% do dia, sao excluidos da classificacao):

    peso = 1x, ou `PESO_EXTRA_P90` (3x) se o TAMANHO do negocio (contratos)
           for >= ao p90 do dia de calibracao (08-28), CONGELADO -- mesma
           logica de "calibra uma vez, congela, aplica" do corte principal.
    toxicidade(t) = |vol_compra_ponderado - vol_venda_ponderado| / vol_total
                    numa janela [t-60s, t], SO' com negocios ATE' `t`
                    (`pandas.rolling("60s")`, que e' right-closed: nunca olha
                    o futuro).

O CORTE (top decil) e' o percentil 90 dessa serie no dia 08-28. Cruzar o
corte VETA entradas novas pelos 120s seguintes -- "espera", nao "pula o dia"
(o robo pode tentar de novo depois que a janela de veto expira, exatamente
como o pedido do dono: suprimir ~2 minutos, nao descartar o pregao).

## O que e' vetado

SO' `EnterLimit` de ABERTURA de posicao -- rompimento original E fade (a
literatura anterior nao deu motivo para poupar o fade da toxicidade, ao
contrario do veto de lateralizacao de 2026-09-15 que poupava o fade por
razao especifica daquele teste). Stop, saida por alvo, `AdjustTarget` e
fechamento de posicao aberta NUNCA sao tocados -- o padrao e' identico ao de
`wdo_orb_veto_lateralizacao_2026_09_15.py` (chama `super().on_bar()`, so'
descarta a `EnterLimit` se o veto estiver ativo, restaura o estado que o pai
marcou para o robo continuar tentando).

Uso: `python -u scripts/daytrade/wdo_orb_toxicidade_fluxo_veto_2026_09_16.py`
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
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import EnterLimit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, monta_config,
)

# ---------------------------------------------------------------------------
# dado -- os DOIS arquivos com `flags` de verdade, um por trecho de calendario
# ---------------------------------------------------------------------------

ARQ_08_28 = RAIZ / "data" / "raw_ticks" / "WDOU26_2026_08_28.parquet"
ARQ_SEMANA_09 = RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_08.parquet"

DIA_CALIBRACAO = "2026-08-28"
DIAS_CONFIRMACAO = ["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]
TODOS_OS_DIAS = [DIA_CALIBRACAO] + DIAS_CONFIRMACAO

LOOKBACK_TOX_SEG = 60
VETO_SEG = 120
PESO_EXTRA_P90 = 3.0

SAIDA = RAIZ / "scratch" / "wdo_orb_toxicidade_2026_09_16"


def carregar_ticks_dia(dia: str) -> pd.DataFrame:
    """Ticks (bid/ask/last/volume/volume_real/flags) do dia, do arquivo de
    flags boas correspondente -- NUNCA do canonico (flags constante = lixo)."""
    ini = pd.Timestamp(dia, tz="UTC")
    fim = ini + pd.Timedelta(days=1)
    arquivo = ARQ_08_28 if dia == DIA_CALIBRACAO else ARQ_SEMANA_09
    col_tempo = "time_msc" if arquivo is ARQ_08_28 else "time"
    df = pd.read_parquet(
        arquivo, filters=[(col_tempo, ">=", ini), (col_tempo, "<", fim)],
    )
    return df.sort_index(kind="mergesort")


# ---------------------------------------------------------------------------
# toxicidade -- causal, rolling 60s terminando em "agora"
# ---------------------------------------------------------------------------

def negocios_classificados(ticks: pd.DataFrame) -> pd.DataFrame:
    """So' os negocios com agressor CLARO (comprador XOR vendedor). Ticks de
    cotacao pura (nenhuma das duas flags) ou ambiguos (as duas juntas) ficam
    de fora -- no dia de calibracao isso e' ~8% dos ticks, quase todos
    atualizacao de bid/ask sem negocio novo."""
    fl = ticks["flags"].astype(int)
    buy = (fl & 32) > 0
    sell = (fl & 64) > 0
    claro = buy ^ sell
    out = ticks.loc[claro, ["volume", "volume_real"]].copy()
    out["is_buy"] = buy.loc[claro]
    out["volume_contratos"] = out["volume_real"].where(
        out["volume_real"] > 0, out["volume"]).astype(float)
    return out


def serie_toxicidade(negocios: pd.DataFrame, p90_tamanho: float) -> pd.Series:
    """Toxicidade(t) = |compra_ponderada - venda_ponderada| / total, rolling
    60s CAUSAL (`rolling` do pandas e' right-closed: a janela [t-60s, t] usa
    so' negocios ate' `t`, nunca depois). `nan` quando a janela nao teve
    negocio classificavel nenhum."""
    peso = np.where(negocios["volume_contratos"] >= p90_tamanho, PESO_EXTRA_P90, 1.0)
    vol_pond = negocios["volume_contratos"].to_numpy() * peso
    buy_w = pd.Series(np.where(negocios["is_buy"].to_numpy(), vol_pond, 0.0),
                       index=negocios.index)
    sell_w = pd.Series(np.where(~negocios["is_buy"].to_numpy(), vol_pond, 0.0),
                        index=negocios.index)
    roll_buy = buy_w.rolling(f"{LOOKBACK_TOX_SEG}s").sum()
    roll_sell = sell_w.rolling(f"{LOOKBACK_TOX_SEG}s").sum()
    total = roll_buy + roll_sell
    tox = (roll_buy - roll_sell).abs() / total.replace(0.0, np.nan)
    return tox


def gatilhos_de_veto(tox: pd.Series, corte: float) -> np.ndarray:
    """Timestamps (ordenados, unicos) em que a toxicidade CRUZOU o corte --
    cada um abre uma janela de veto de `VETO_SEG` segundos."""
    disparo = tox.index[(tox > corte).to_numpy()]
    return np.unique(disparo.values)  # datetime64[ns], ordenado


def indice_gatilho_ativo(ts, gatilhos: np.ndarray) -> int:
    """Indice do gatilho que esta' cobrindo `ts` agora, ou -1 se nenhum. Como
    os gatilhos sao monotonicos, o mais recente <= ts e' o UNICO que pode
    alcancar `ts` (qualquer gatilho anterior tem janela igual ou mais curta
    a partir dali). O indice (nao so' um bool) deixa agrupar tentativas
    vetadas consecutivas pertencentes ao MESMO episodio de pico."""
    if gatilhos.size == 0:
        return -1
    ts64 = np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ns")
    i = int(np.searchsorted(gatilhos, ts64, side="right") - 1)
    if i < 0:
        return -1
    if ts64 < gatilhos[i] + np.timedelta64(VETO_SEG, "s"):
        return i
    return -1


# ---------------------------------------------------------------------------
# a estrategia -- copia o padrao de wdo_orb_veto_lateralizacao_2026_09_15.py
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbToxicidade(WdoOrbInstrumentado):
    """Producao + veto de ENTRADA (rompimento e fade) por pico de toxicidade
    de fluxo. Nada mais muda -- stop/alvo/AdjustTarget nunca sao tocados."""

    ativo: bool = True
    _gatilhos: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"),
                                   init=False, repr=False)
    _vetos: list = field(default_factory=list, init=False, repr=False)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        if not self.ativo:
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        antes = (self._armou_hoje, self._limite_posto, self._lado_primeiro,
                 self._fades_no_dia)
        n_log = len(self._log_ordens)
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)

        saida = []
        for a in acoes:
            if not isinstance(a, EnterLimit):
                saida.append(a)
                continue
            ordem = self._log_ordens[-1] if len(self._log_ordens) > n_log else None
            idx_gatilho = indice_gatilho_ativo(ts, self._gatilhos) if ordem is not None else -1
            if ordem is None or idx_gatilho < 0:
                saida.append(a)
                continue

            # Um veto por EPISODIO (mesmo gatilho controlando), nao por
            # tentativa: em base de tick o robo reavalia a cada negocio
            # enquanto o preco fica fora da faixa, entao um unico pico de
            # toxicidade pode gerar centenas de tentativas bloqueadas
            # seguidas -- contar tentativa a tentativa so' infla o numero.
            if self._vetos and self._vetos[-1]["idx_gatilho"] == idx_gatilho:
                self._vetos[-1]["barras"] += 1
                self._vetos[-1]["ts_fim"] = ts
            else:
                self._vetos.append({
                    "ts": ts, "ts_fim": ts, "idx_gatilho": idx_gatilho,
                    "tipo": ordem["tipo"], "side": ordem["side"], "barras": 1,
                })
            # a ordem nunca existiu: tira do log e desfaz o estado que o pai
            # marcou, senao o robo acha que armou e cala o pregao inteiro.
            self._log_ordens.pop()
            (self._armou_hoje, self._limite_posto, self._lado_primeiro,
             self._fades_no_dia) = antes
        return saida


# ---------------------------------------------------------------------------
# calibracao (SO' 08-28) -- corte de toxicidade e p90 de tamanho, congelados
# ---------------------------------------------------------------------------

def calibra(dia: str = DIA_CALIBRACAO) -> tuple[float, float]:
    ticks = carregar_ticks_dia(dia)
    negocios = negocios_classificados(ticks)
    p90_tamanho = float(negocios["volume_contratos"].quantile(0.90))
    tox = serie_toxicidade(negocios, p90_tamanho)
    corte = float(tox.dropna().quantile(0.90))
    return corte, p90_tamanho


# ---------------------------------------------------------------------------
# roda 1 pregao -- BASE (sem veto) e TOX (com veto), mesmo capital, mesma barra
# ---------------------------------------------------------------------------

def roda_pregao(dia: str, corte: float, p90_tamanho: float) -> dict:
    ticks = carregar_ticks_dia(dia)
    if ticks.empty:
        return {"dia": dia, "erro": "sem ticks"}
    bars = ticks_to_degenerate_bars(ticks)
    negocios = negocios_classificados(ticks)
    tox = serie_toxicidade(negocios, p90_tamanho)
    gatilhos = gatilhos_de_veto(tox, corte)

    strat_base = WdoOrbInstrumentado()
    res_base = run_intraday_backtest(bars, strat_base, monta_config(strat_base, CAPITAL_PARTIDA_BRL))

    strat_tox = WdoOrbToxicidade()
    strat_tox._gatilhos = gatilhos
    res_tox = run_intraday_backtest(bars, strat_tox, monta_config(strat_tox, CAPITAL_PARTIDA_BRL))

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
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S.%f"),
                "entrada_brt": entry_brt.strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2),
                "exit_reason": razao,
                "caixa_antes": round(caixa, 2),
            })
            caixa += t.pnl_brl
        caixa_min = min([CAPITAL_PARTIDA_BRL] + [l["caixa_antes"] + l["pnl_brl"] for l in linhas])
        return linhas, caixa_min

    linhas_base, caixa_min_base = extrai("BASE", strat_base, res_base)
    linhas_tox, caixa_min_tox = extrai("TOX", strat_tox, res_tox)

    vetos = [{"dia": dia, "ts": pd.Timestamp(v["ts"]).tz_convert("America/Sao_Paulo").strftime("%H:%M:%S"),
              "tipo": v["tipo"], "side": v["side"], "barras": v["barras"]}
             for v in strat_tox._vetos]

    return {
        "dia": dia, "erro": "",
        "trades": linhas_base + linhas_tox,
        "vetos": vetos,
        "n_gatilhos_toxicidade": int(gatilhos.size),
        "resumo": {
            "dia": dia,
            "base_trades": len(linhas_base), "base_liquido": round(sum(l["pnl_brl"] for l in linhas_base), 2),
            "base_win_pct": round(100.0 * sum(1 for l in linhas_base if l["pnl_brl"] > 0) / len(linhas_base), 1) if linhas_base else float("nan"),
            "base_maxdd": round(max(0.0, CAPITAL_PARTIDA_BRL - caixa_min_base), 2),
            "tox_trades": len(linhas_tox), "tox_liquido": round(sum(l["pnl_brl"] for l in linhas_tox), 2),
            "tox_win_pct": round(100.0 * sum(1 for l in linhas_tox if l["pnl_brl"] > 0) / len(linhas_tox), 1) if linhas_tox else float("nan"),
            "tox_maxdd": round(max(0.0, CAPITAL_PARTIDA_BRL - caixa_min_tox), 2),
            "vetados": len(vetos),
        },
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    corte, p90_tamanho = calibra()
    print(f"[toxicidade] calibrado em {DIA_CALIBRACAO} (IS/exploracao, autoajustado):")
    print(f"  p90 tamanho do negocio = {p90_tamanho:.1f} contratos (peso extra {PESO_EXTRA_P90}x acima disso)")
    print(f"  corte top-decil de toxicidade = {corte:.4f}")
    print(f"[toxicidade] este MESMO corte e' congelado e aplicado, sem recalibrar, aos "
          f"{len(DIAS_CONFIRMACAO)} pregoes de confirmacao (09-08..09-11)\n", flush=True)

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
            print(f"[{dia}] gatilhos={r['n_gatilhos_toxicidade']:>4} vetados={s['vetados']:>2} | "
                  f"BASE {s['base_trades']:>2}op win{s['base_win_pct']:>5}% "
                  f"liq R${s['base_liquido']:>9,.2f} DD R${s['base_maxdd']:>7,.2f} | "
                  f"TOX {s['tox_trades']:>2}op win{s['tox_win_pct']:>5}% "
                  f"liq R${s['tox_liquido']:>9,.2f} DD R${s['tox_maxdd']:>7,.2f}", flush=True)

    todas_trades = pd.concat(
        [pd.DataFrame(r["trades"]) for r in resultados.values() if r["erro"] == ""],
        ignore_index=True)
    todos_vetos = pd.concat(
        [pd.DataFrame(r["vetos"]) for r in resultados.values() if r["erro"] == "" and r["vetos"]],
        ignore_index=True) if any(r.get("vetos") for r in resultados.values()) else pd.DataFrame()
    todas_trades.to_csv(SAIDA / "trades.csv", index=False, encoding="utf-8")
    todos_vetos.to_csv(SAIDA / "vetos.csv", index=False, encoding="utf-8")

    # ---- contrafactual: o que o BASE fez com as entradas que o TOX vetou ---
    print("\n" + "=" * 100)
    print("CONTRAFACTUAL -- o que a BASE (sem veto) fez com as operacoes que o TOX removeu")
    print("  (casado por (data, entrada_brt) -- se a operacao removida NAO aparece do outro")
    print("   lado, o veto mudou o estado do dia e nao ha' contrafactual direto para ela)")
    print("=" * 100)
    base = todas_trades[todas_trades.celula == "BASE"].set_index(["data", "entrada_brt"])
    tox = todas_trades[todas_trades.celula == "TOX"].set_index(["data", "entrada_brt"])
    sumiram = base.loc[base.index.difference(tox.index)]
    surgiram = tox.loc[tox.index.difference(base.index)]
    print(f"sumiram (BASE tinha, TOX vetou -- via a MESMA entrada) : {len(sumiram)} op, "
          f"R${sumiram.pnl_brl.sum():+,.2f}, {int((sumiram.pnl_brl > 0).sum())} eram GANHADORAS "
          f"(R${sumiram[sumiram.pnl_brl > 0].pnl_brl.sum():+,.2f}), "
          f"{int((sumiram.pnl_brl <= 0).sum())} eram PERDEDORAS "
          f"(R${sumiram[sumiram.pnl_brl <= 0].pnl_brl.sum():+,.2f})")
    print(f"surgiram (TOX tem, BASE nao tinha -- reordenacao de estado do dia): {len(surgiram)} op, "
          f"R${surgiram.pnl_brl.sum():+,.2f}")

    # ---- agregado, separando calibracao (autoajustado) de confirmacao -----
    for rotulo, dias in [("CALIBRACAO (08-28, autoajustado -- NAO conta como prova)", [DIA_CALIBRACAO]),
                         ("CONFIRMACAO (09-08..09-11, corte congelado)", DIAS_CONFIRMACAO)]:
        print("\n" + "=" * 100)
        print(rotulo)
        print("=" * 100)
        sub = todas_trades[todas_trades.data.isin(dias)]
        for cel in ("BASE", "TOX"):
            ops = sub[sub.celula == cel]
            n = len(ops)
            liq = ops.pnl_brl.sum()
            win = 100.0 * (ops.pnl_brl > 0).mean() if n else float("nan")
            print(f"  {cel}: {n:>3} trades | liquido R${liq:>10,.2f} | win {win:>5.1f}% | "
                  f"R$/op {liq / n if n else float('nan'):>7.2f}")
        v = todos_vetos[todos_vetos.dia.isin(dias)] if not todos_vetos.empty else pd.DataFrame()
        print(f"  vetos (episodios): {len(v)}")

    print(f"\n[toxicidade] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
