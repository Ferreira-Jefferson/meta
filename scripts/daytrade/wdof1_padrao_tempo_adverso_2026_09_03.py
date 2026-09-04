"""Pesquisa/analise DESCRITIVA pedida pelo dono em 2026-09-03: existe um
PADRAO entre "quanto tempo, dentro da vida do trade, o preco fica do lado
ADVERSO (perto do stop) vs do lado FAVORAVEL (perto do alvo)" e o resultado
final (fechou por STOP ou por TARGET)? Pergunta literal do dono: "se quando
abre a operacao e nos primeiros 10% do tempo ele fica abaixo, ele stopa no
final? ou se nos 50% ou 80%? ... e o mesmo pro alvo".

## Ressalva de look-ahead -- leia antes de usar isto pra qualquer coisa que
## nao seja pesquisa

"Fracao do tempo TOTAL do trade" so' e' conhecida DEPOIS que o trade fecha --
enquanto a posicao esta aberta, a duracao final e' desconhecida (voce nao
sabe se o trade vai durar mais 2 ticks ou mais 2.000). Este script e'
portanto uma analise RETROSPECTIVA sobre trades ja fechados, NAO uma regra de
execucao ao vivo: uma regra ao vivo so' pode usar tempo/numero de ticks
ABSOLUTOS decorridos desde a entrada, nunca fracao do total (que exige saber
o futuro do proprio trade que ainda esta aberto). Nenhuma regra de saida e'
proposta ou implementada aqui -- so' o padrao cru, para o dono decidir se
vale a pena reformular em tempo absoluto depois (proximo passo possivel, NAO
feito aqui).

## Estrategia, config, dado

`WdoGridReloadMaker` (`strategy/daytrade/lab/wdo_grid_reload_maker.py`),
config de PRODUCAO "T1 S16 x1" (`level_spacing_ticks=1, profit_ticks=1,
stop_ticks=16`) via `wdo_grid_reload_f1_lab.montar_config()`/`rodar()` -- SEM
nenhum parametro de defesa novo (`defesa_ativa` fica no default `False` da
classe porque o kwarg nunca e' passado aqui; mesmo que o trabalho paralelo de
`wdof1_defesa_recuo_sweep_2026_09_03.py` tenha adicionado esse parametro a
classe, este script roda o comportamento NATURAL do robo, sem saida
antecipada nenhuma).

Historico TICK (nao M1 -- a pergunta e' sobre o CAMINHO intra-trade,
resolucao importa) do cache `data/raw_ticks/WDO_A_f1.parquet`: 123 pregoes
com tick disponivel (72 IS + 51 OOS, 2026-02-27 -> 2026-08-25). NOTA: isto e'
menos que os ~177 pregoes do historico M1 completo salvo em disco -- tick
history retido pelo terminal/corretora nao cobre os 51 PRIMEIROS pregoes do
IS (ver `wdo_grid_reload_f1_tick_lab.py`). 123 pregoes e' o universo MAXIMO
disponivel com precisao tick; nao ha' como estender sem cair de volta pra
M1 (que teria menos resolucao intra-trade, o oposto do que a pergunta pede).

## Metodo

1. Roda o backtest baseline (config acima, historico tick completo), pega
   `resultado.trades`, descarta tudo que nao fechou por STOP ou TARGET
   (`FORCED_FLATTEN` no fim do pregao nao e' uma resolucao de stop/alvo).
2. Para cada trade, fatia `entry_ts..exit_ts` (INCLUSIVE) no parquet de tick
   (via `searchsorted` sobre o array de timestamps, ja ordenado) e calcula
   por tick: `frac_tempo` = posicao temporal normalizada 0..1 dentro da
   janela do trade, e `lado` = favoravel/adverso/neutro em relacao a
   `entry_price` (considerando `side`: long favorece preco > entrada, short
   favorece preco < entrada).
3. Para os checkpoints 10%..90% (passo 10pp), acha o ULTIMO tick conhecido
   com `frac_tempo <= checkpoint` (estado mais recente naquele ponto -- nunca
   um tick FUTURO em relacao ao checkpoint) e registra `lado_no_checkpoint` e
   `frac_tempo_adverso_acumulada_ate_checkpoint` (fracao dos ticks VISTOS ate
   ali, do inicio do trade ate o checkpoint, que estavam do lado adverso --
   metrica mais rica que so' o estado pontual).
4. Duas tabelas cruas, sem veredito (convencao do projeto -- tabela primeiro,
   opiniao depois): (a) por `lado_no_checkpoint` pontual, (b) por FAIXA de
   `frac_tempo_adverso_acumulada_ate_checkpoint` (buckets de 20pp) -- em
   ambas, N, %STOP e %TARGET por celula.
5. Salva o dataset trade x checkpoint em CSV
   (`scripts/daytrade/wdof1_padrao_tempo_adverso_2026_09_03.csv`) para o dono
   abrir depois se quiser.

Sem `ProcessPoolExecutor`/pool pesado neste script DE PROPOSITO -- outro
processo (`wdof1_defesa_recuo_sweep_2026_09_03.py`, ~12-13 nucleos) ja esta
rodando no momento desta analise. Tudo aqui e' pandas/numpy vetorizado,
single-process: o trabalho por trade e' O(ticks dentro da janela do trade),
e a soma sobre todos os trades e' <= o total de ticks do cache (so' 1
posicao aberta por vez), entao o custo total e' comparavel a UMA passada
pelo parquet inteiro.

Uso: `python scripts/daytrade/wdof1_padrao_tempo_adverso_2026_09_03.py`
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.models import IntradayExitReason  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from wdo_grid_reload_f1_lab import CAPITAL_NOCIONAL, montar_config, rodar  # noqa: E402

CACHE = ROOT / "data" / "raw_ticks" / "WDO_A_f1.parquet"
OUT_CSV = Path(__file__).resolve().parent / "wdof1_padrao_tempo_adverso_2026_09_03.csv"

#: Checkpoints de fracao de tempo decorrido ATE O FECHAMENTO (pedido do
#: dono: 10%, 20%, ..., 90%).
CHECKPOINTS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)

#: Faixas de `frac_tempo_adverso_acumulada_ate_checkpoint` para a tabela 2
#: (passo 5 da missao) -- 20pp cada, ultima inclusiva de 100%.
FAIXAS_ACUMULADA = [
    (0.0, 0.2, "0-20%"),
    (0.2, 0.4, "20-40%"),
    (0.4, 0.6, "40-60%"),
    (0.6, 0.8, "60-80%"),
    (0.8, 1.0 + 1e-9, "80-100%"),
]

_EXIT_RESOLVIDOS = (IntradayExitReason.STOP, IntradayExitReason.TARGET)


def carregar_ticks() -> pd.DataFrame:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_padrao_tempo_adverso] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    df = pd.read_parquet(CACHE)
    df = df.sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def rodar_baseline(bars: pd.DataFrame):
    """Config de producao (T1 S16 x1), SEM defesa (kwarg nunca passado ->
    `defesa_ativa=False`, default da classe)."""
    cfg = montar_config()
    return rodar(bars, cfg)


def extrair_checkpoints(trades: list, times_ns: np.ndarray, closes: np.ndarray) -> pd.DataFrame:
    """Para cada trade resolvido (STOP/TARGET), calcula os checkpoints de
    fracao de tempo. Devolve 1 linha por (trade, checkpoint).

    `times_ns` DEVE estar em nanosegundos verdadeiros (`DatetimeIndex.as_unit
    ("ns").asi8`, nunca so' `.asi8`) -- o parquet de tick guarda o indice em
    resolucao de MILISSEGUNDO (`datetime64[ms, UTC]`, pandas 3.x preserva a
    unidade de armazenamento), enquanto `pd.Timestamp.value` sempre devolve
    nanosegundos independente da unidade de armazenamento. As duas escalas
    divergem por 1e6x; usar `.asi8` cru aqui faz TODO `searchsorted` cair no
    fim do array (`start == end == len(times_ns)` para qualquer trade),
    marcando 100% dos trades como "duracao zero" -- bug real encontrado e
    corrigido nesta rodada (nao e' um achado sobre a estrategia)."""
    linhas: list[dict] = []
    pulados_duracao_zero_wallclock = 0
    pulados_sem_ticks_na_janela = 0
    for trade_id, t in enumerate(trades):
        entry_ns = t.entry_ts.value
        exit_ns = t.exit_ts.value
        if exit_ns <= entry_ns:
            pulados_duracao_zero_wallclock += 1
            continue  # duracao 0 (fecha no mesmo tick da entrada) -- fracao indefinida

        start = int(np.searchsorted(times_ns, entry_ns, side="left"))
        end = int(np.searchsorted(times_ns, exit_ns, side="right"))
        if end <= start:
            pulados_sem_ticks_na_janela += 1
            continue

        tt = times_ns[start:end].astype(np.float64)
        cc = closes[start:end]
        frac_tempo = (tt - entry_ns) / (exit_ns - entry_ns)
        np.clip(frac_tempo, 0.0, 1.0, out=frac_tempo)

        if t.side == "long":
            lado = np.where(cc > t.entry_price, "favoravel",
                             np.where(cc < t.entry_price, "adverso", "neutro"))
        else:
            lado = np.where(cc < t.entry_price, "favoravel",
                             np.where(cc > t.entry_price, "adverso", "neutro"))

        adverso_bin = (lado == "adverso").astype(np.float64)
        cum_adverso = np.cumsum(adverso_bin)
        n_visto = np.arange(1, len(lado) + 1, dtype=np.float64)
        frac_acumulada = cum_adverso / n_visto

        exit_reason_txt = t.exit_reason.value
        for chk in CHECKPOINTS:
            idx = int(np.searchsorted(frac_tempo, chk, side="right")) - 1
            if idx < 0:
                idx = 0
            linhas.append(dict(
                trade_id=trade_id,
                checkpoint=chk,
                lado_no_checkpoint=lado[idx],
                frac_tempo_adverso_acumulada_ate_checkpoint=float(frac_acumulada[idx]),
                exit_reason=exit_reason_txt,
                side=t.side,
                entry_ts=t.entry_ts,
                exit_ts=t.exit_ts,
            ))

    if pulados_duracao_zero_wallclock:
        print(f"[wdof1_padrao_tempo_adverso] {pulados_duracao_zero_wallclock} trade(s) com "
              f"duracao 0 (fecham no mesmo tick/timestamp da entrada) pulado(s) -- fracao de "
              f"tempo indefinida. Achado genuino (nao bug): ver nota no relatorio final.")
    if pulados_sem_ticks_na_janela:
        print(f"[wdof1_padrao_tempo_adverso] {pulados_sem_ticks_na_janela} trade(s) sem tick "
              f"localizavel na janela entry_ts..exit_ts pulado(s) (inesperado -- investigar se > 0).")
    colunas = ["trade_id", "checkpoint", "lado_no_checkpoint",
               "frac_tempo_adverso_acumulada_ate_checkpoint", "exit_reason", "side",
               "entry_ts", "exit_ts"]
    if not linhas:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame(linhas)


def tabela_pontual(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela 1 -- estado PONTUAL no checkpoint. Linhas = checkpoint,
    colunas = N/%STOP/%TARGET para adverso e favoravel (neutro fica de fora
    das colunas, mas o N e' reportado a parte para o total bater)."""
    linhas = []
    for chk in CHECKPOINTS:
        sub = df[df["checkpoint"] == chk]
        row: dict = {"checkpoint_%": chk * 100.0}
        for lado in ("adverso", "favoravel"):
            cel = sub[sub["lado_no_checkpoint"] == lado]
            n = len(cel)
            pct_stop = 100.0 * (cel["exit_reason"] == "stop").mean() if n else float("nan")
            pct_target = 100.0 * (cel["exit_reason"] == "target").mean() if n else float("nan")
            row[f"N_{lado}"] = n
            row[f"%STOP|{lado}"] = pct_stop
            row[f"%TARGET|{lado}"] = pct_target
        row["N_neutro"] = int((sub["lado_no_checkpoint"] == "neutro").sum())
        linhas.append(row)
    return pd.DataFrame(linhas)


def tabela_acumulada(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela 2 -- por FAIXA de `frac_tempo_adverso_acumulada_ate_checkpoint`
    (quanto do tempo DECORRIDO ate o checkpoint o preco passou do lado
    adverso), mesma metrica de saida (N/%STOP/%TARGET), por checkpoint."""
    linhas = []
    for chk in CHECKPOINTS:
        sub = df[df["checkpoint"] == chk]
        row: dict = {"checkpoint_%": chk * 100.0}
        for lo, hi, rotulo in FAIXAS_ACUMULADA:
            frac = sub["frac_tempo_adverso_acumulada_ate_checkpoint"]
            cel = sub[(frac >= lo) & (frac < hi)]
            n = len(cel)
            pct_stop = 100.0 * (cel["exit_reason"] == "stop").mean() if n else float("nan")
            pct_target = 100.0 * (cel["exit_reason"] == "target").mean() if n else float("nan")
            row[f"N_{rotulo}"] = n
            row[f"%STOP|{rotulo}"] = pct_stop
            row[f"%TARGET|{rotulo}"] = pct_target
        linhas.append(row)
    return pd.DataFrame(linhas)


def _fmt_tabela(tab: pd.DataFrame) -> str:
    """Formata numeros em BR (virgula decimal), mesma convencao do resto do
    repo (`backtest/intraday/report.num_br`), sem alterar a estrutura."""
    out = tab.copy()
    for col in out.columns:
        if col.startswith("checkpoint"):
            out[col] = out[col].map(lambda v: f"{num_br(v, 0)}%")
        elif col.startswith("N_"):
            out[col] = out[col].astype(int)
        elif col.startswith("%"):
            out[col] = out[col].map(lambda v: "-" if pd.isna(v) else f"{num_br(v, 1)}%")
    return out.to_string(index=False)


def main() -> None:
    t0 = time.perf_counter()
    bars = carregar_ticks()
    n_dias = len(set(bars.index.date))
    print(f"[wdof1_padrao_tempo_adverso] {len(bars):,} ticks, {n_dias} pregoes "
          f"({bars.index.min()} -> {bars.index.max()})")

    resultado = rodar_baseline(bars)
    dt_motor = time.perf_counter() - t0
    print(f"[wdof1_padrao_tempo_adverso] motor: {dt_motor:.1f}s, "
          f"{len(resultado.trades)} trades totais")

    item = linha_de_resultado("wdo_grid_reload T1 S16 x1 (TICK, 123 pregoes IS+OOS, baseline sem defesa)",
                               resultado, CAPITAL_NOCIONAL, capital_nocional=True)
    print("\n=== resultado do backtest baseline (tabela padrao do repo) ===")
    print(cabecalho())
    print(linha(item))

    contagem_motivos = pd.Series([t.exit_reason.value for t in resultado.trades]).value_counts()
    print(f"\ndistribuicao de exit_reason (todos os {len(resultado.trades)} trades):")
    print(contagem_motivos.to_string())

    trades_resolvidos = [t for t in resultado.trades if t.exit_reason in _EXIT_RESOLVIDOS]
    print(f"\n{len(trades_resolvidos)} trades resolvidos por STOP ou TARGET "
          f"({len(resultado.trades) - len(trades_resolvidos)} descartados -- "
          f"FORCED_FLATTEN/MANUAL/SIGNAL, nao e' resolucao de stop/alvo).")

    # `.as_unit("ns")` ANTES de `.asi8` -- ver a docstring de `extrair_checkpoints`
    # para o motivo (o parquet guarda o indice em datetime64[ms, UTC], `.asi8`
    # cru daria milissegundos, nao nanosegundos, e quebraria TODO searchsorted
    # contra `pd.Timestamp.value` (sempre em ns) das linhas 4 abaixo).
    times_ns = bars.index.as_unit("ns").asi8
    closes = bars["close"].to_numpy()

    t1 = time.perf_counter()
    df_checkpoints = extrair_checkpoints(trades_resolvidos, times_ns, closes)
    dt_checkpoints = time.perf_counter() - t1
    n_trades_no_dataset = df_checkpoints["trade_id"].nunique()
    print(f"[wdof1_padrao_tempo_adverso] extracao de checkpoints: {dt_checkpoints:.1f}s, "
          f"{n_trades_no_dataset} trades no dataset final "
          f"({len(df_checkpoints)} linhas trade x checkpoint)")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_checkpoints.to_csv(OUT_CSV, index=False)
    print(f"[wdof1_padrao_tempo_adverso] dataset salvo em {OUT_CSV}")

    print("\n=== Tabela 1: estado PONTUAL no checkpoint (lado_no_checkpoint) ===")
    print("(N_neutro = trades onde o preco estava EXATAMENTE na entrada naquele "
          "checkpoint -- fora das colunas adverso/favoravel, reportado a parte)")
    tab1 = tabela_pontual(df_checkpoints)
    print(_fmt_tabela(tab1))

    print("\n=== Tabela 2: por FAIXA de frac_tempo_adverso_acumulada_ate_checkpoint ===")
    print("(fracao dos ticks vistos DESDE A ENTRADA ate o checkpoint que estavam do lado adverso)")
    tab2 = tabela_acumulada(df_checkpoints)
    print(_fmt_tabela(tab2))

    dt_total = time.perf_counter() - t0
    print(f"\n[wdof1_padrao_tempo_adverso] total: {dt_total:.1f}s")
    print("\nNOTA (repetida do topo do arquivo): fracao de tempo e' conhecida so' "
          "DEPOIS que o trade fecha -- isto e' analise RETROSPECTIVA, nao regra "
          "de execucao ao vivo. Nenhuma regra foi implementada aqui.")


if __name__ == "__main__":
    main()
