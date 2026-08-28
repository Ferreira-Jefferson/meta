"""Re-rodada PARALELA do WDO F1 maker (`WdoGridReloadMaker`, WDO@, T1 S16 x1,
leitura tick) -- mesma tabela da versao serial, usando todos os nucleos.

## Por que o split por PREGAO e' exato aqui (o portao de correcao)

`run_intraday_backtest` ja processa uma sessao por vez (`engine.py:167`,
`bars.groupby(bars.index.date)`). O que poderia acoplar sessoes vizinhas:

1. `strategy.on_session_start` -> `WdoGridReloadMaker` RESETA `self._state`
   inteiro (`wdo_grid_reload_maker.py:234-235`). Sem memoria entre pregoes --
   diferente da familia `Gremah`, que tem `repetir_ultimo_vencedor` e NAO
   poderia ser dividida assim.
2. `seed_volume_window` / `seed_daily_volatility` / `seed_typical_trade_size`:
   o motor passa a cauda dos 60 pregoes anteriores, mas os tres sao **no-op no
   default** (`strategy/daytrade/base.py:469-503`) e esta estrategia nao
   sobrescreve nenhum. Se algum dia sobrescrever, este script passa a precisar
   de aquecimento de `_CAUDA_DIAS_MAXIMA`=60 pregoes por bloco.
3. `enforce_capital_minimo` (le `machine.realized_pnl` acumulado): DESLIGADO
   nesta frente, porque o perfil declara `max_open_contracts` -- o limitador e'
   o teto de contratos, nao o caixa.
4. Tamanho de posicao: fixo em 1 contrato, sem `margin_per_contract_brl` e sem
   realocacao dinamica. Nada depende do patrimonio corrente.

Logo os trades de um pregao nao dependem de nenhum outro, e blocos de pregoes
podem rodar em processos separados SEM sobreposicao de aquecimento. O script
VALIDA isso contra a referencia serial em vez de confiar no argumento acima.

## O outro ganho, independente do paralelismo

A janela IS+OOS nao e' rodada: ela e' a CONCATENACAO das duas -- mesmo metodo
que a escada de capital desta frente ja validou byte-a-byte na fronteira. Isso
corta metade do trabalho total (8,0M -> 4,0M barras) antes de qualquer nucleo
extra entrar na conta.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

#: Referencia SERIAL (rodada de 2026-08-27, `wdof1_rerun_tabela_2026_08_27.py`),
#: que por sua vez bate com o que ja estava registrado no projeto. O paralelo
#: tem que reproduzir isto exatamente, ou o split esta errado.
REFERENCIA = {"IS": (2773, 11233.50), "OOS": (1740, 7080.00)}

N_WORKERS = max(1, os.cpu_count() or 4)


#: Parquet lido UMA vez por processo, nao por tarefa (na 1a versao, 24 tarefas
#: em 12 processos liam o arquivo de 4M linhas 24 vezes).
_DF_PROC = None


def _df_do_processo():
    global _DF_PROC
    if _DF_PROC is None:
        _DF_PROC = pd.read_parquet(CACHE)
    return _DF_PROC


def _roda_bloco(args):
    """Executado no processo filho: corta os pregoes do bloco e roda o motor.
    Devolve tuplas leves (nao objetos do motor) para o pickle de volta ser
    barato."""
    janela, dias = args
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wdo_grid_reload_f1_lab import montar_config, rodar

    df = _df_do_processo()
    # filtro VETORIZADO nas duas dimensoes (a coluna `dia` existe justamente
    # para isto -- ver `wdof1_tick_cache_2026_08_27.py`)
    sel = (df["janela"] == janela) & (df["dia"].isin(dias))
    df = df.loc[sel, ["open", "high", "low", "close", "volume"]]
    res = rodar(df, montar_config())
    return [(t.entry_ts, t.exit_ts, t.pnl_brl, t.exit_reason) for t in res.trades]


def blocos_balanceados(peso_por_dia, k):
    """Distribui pregoes em `k` blocos equilibrados por NUMERO DE BARRAS (LPT:
    maior primeiro, sempre no bloco mais leve). Blocos de tamanho igual em
    QUANTIDADE de pregoes desequilibram o tempo, porque pregao movimentado tem
    muito mais tick que pregao parado."""
    bins = [[] for _ in range(k)]
    carga = [0] * k
    for dia, peso in sorted(peso_por_dia.items(), key=lambda kv: -kv[1]):
        i = carga.index(min(carga))
        bins[i].append(dia)
        carga[i] += peso
    return [b for b in bins if b], carga


def maxdd(pnls):
    eq = pico = dd = 0.0
    for p in pnls:
        eq += p
        pico = max(pico, eq)
        dd = max(dd, pico - eq)
    return dd


def br(v, dec=2):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha(rotulo, trades):
    pnls = [t[2] for t in trades]
    liq = sum(pnls)
    dd = maxdd(pnls)
    npreg = len({t[1].date() for t in trades})
    return dict(janela=rotulo, pregoes=npreg, trades=len(trades), liquido=liq,
                por_pregao=liq / npreg if npreg else float("nan"),
                por_trade=liq / len(trades) if trades else float("nan"),
                maxdd=dd, calmar=liq / dd if dd > 0 else float("inf"))


def main():
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}\nrode antes: wdof1_tick_cache_2026_08_27.py")
    t0 = time.perf_counter()
    meta = pd.read_parquet(CACHE, columns=["janela", "dia"])
    peso = meta.groupby(["janela", "dia"]).size()
    barras_por_janela = {j: int(peso.loc[j].sum()) for j in ("IS", "OOS")}
    total_barras = sum(barras_por_janela.values())
    print(f"cache: {len(meta):,} barras | "
          + " | ".join(f"{j} {len(peso.loc[j])} pregoes / {barras_por_janela[j]:,} barras"
                       for j in ("IS", "OOS"))
          + f" | {N_WORKERS} processos", flush=True)

    # Nucleos repartidos por BARRAS, nao por janela: o IS tem 2,4x as barras do
    # OOS, dar 6 e 6 deixaria metade dos processos ociosa esperando o IS.
    k_is = max(1, min(N_WORKERS - 1,
                      round(N_WORKERS * barras_por_janela["IS"] / total_barras)))
    k_por_janela = {"IS": k_is, "OOS": N_WORKERS - k_is}

    tarefas = []
    dias_por_janela = {}
    for jan in ("IS", "OOS"):
        p = {d: int(n) for (d, n) in peso.loc[jan].items()}
        dias_por_janela[jan] = sorted(p)
        bins, carga = blocos_balanceados(p, k_por_janela[jan])
        for bl in bins:
            tarefas.append((jan, bl))
        print(f"  {jan}: {k_por_janela[jan]} blocos, carga "
              f"{min(carga):,}..{max(carga):,} barras "
              f"(desbalanco {100*(max(carga)-min(carga))/max(carga):.1f}%)")
    print(f"{len(tarefas)} tarefas para {N_WORKERS} processos\n", flush=True)

    t_motor = time.perf_counter()
    por_janela = {"IS": [], "OOS": []}
    with ProcessPoolExecutor(max_workers=N_WORKERS) as ex:
        for (jan, _), trades in zip(tarefas, ex.map(_roda_bloco, tarefas)):
            por_janela[jan].extend(trades)
    dt_motor = time.perf_counter() - t_motor

    for jan in por_janela:
        por_janela[jan].sort(key=lambda t: t[1])

    comb = sorted(por_janela["IS"] + por_janela["OOS"], key=lambda t: t[1])
    linhas = [linha("IS", por_janela["IS"]), linha("OOS", por_janela["OOS"]),
              linha("IS+OOS", comb)]

    print(f"motor: {dt_motor:.1f}s em {N_WORKERS} processos "
          f"(total do script {time.perf_counter() - t0:.1f}s)\n")

    print("VALIDACAO contra a referencia serial:")
    ok = True
    for l in linhas[:2]:
        esp_n, esp_liq = REFERENCIA[l["janela"]]
        bate = l["trades"] == esp_n and abs(l["liquido"] - esp_liq) < 0.005
        ok = ok and bate
        print(f"  {l['janela']:6s} {l['trades']} trades / R$ {br(l['liquido'])}  "
              f"esperado {esp_n} / R$ {br(esp_liq)}  -> "
              f"{'IDENTICO' if bate else 'DIVERGE'}")
    if not ok:
        raise SystemExit("\nDIVERGENCIA: o split por pregao NAO e' exato nesta config. "
                         "Nao usar este resultado.")

    print()
    print(f"| {'Candidato':13s} | {'Janela':7s} | {'Trades':>7s} | {'Liquido':>11s} | "
          f"{'R$/pregao':>10s} | {'Lucro/trade':>11s} | {'MaxDD':>8s} | {'Calmar':>7s} |")
    print("|" + "|".join(["-" * 15, "-" * 9, "-" * 9, "-" * 13, "-" * 12,
                          "-" * 13, "-" * 10, "-" * 9]) + "|")
    for l in linhas:
        print(f"| {'WDO F1 maker':13s} | {l['janela']:7s} | {l['trades']:>7,} | "
              f"{br(l['liquido']):>11s} | {br(l['por_pregao']):>10s} | "
              f"{br(l['por_trade'], 3):>11s} | {br(l['maxdd']):>8s} | "
              f"{br(l['calmar'], 1):>7s} |")
    print("\npregoes: " + " . ".join(f"{l['janela']}={l['pregoes']}" for l in linhas))


if __name__ == "__main__":
    main()
