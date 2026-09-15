"""IMPACTO (2026-09-14) -- a folga de 5 min no achatamento mexe no wdo_orb?

## O que mudou no repo (outra frente, nao esta)

`core.b3_session.FOLGA_ACHATAMENTO_MINUTOS = 5`: o motor passou a achatar a
posicao 5 minutos ANTES do fim do pregao, em vez de na ultima barra. No WDO@
isso leva o corte de **21:30 para 21:25 UTC** (18:30 -> 18:25 de Brasilia).

O motivo veio do lado ao VIVO, nao do backtest: `session_end_time` respondia a
tres perguntas ao mesmo tempo, e duas delas sao incompativeis no mesmo
instante -- `live.clock.phase_em_janela` desligava o robo exatamente na barra
que carregaria o achatamento, entao ela nunca era lida. Resultado medido: ZERO
eventos FLATTEN em toda a historia de `db/live.sqlite`.

## Por que medir mesmo assim, se o wdo_orb quase nao usa o sino

Nos 134 pregoes ja' coletados, **1 operacao em 195 (0,5%)** sai por
`forced_flatten` -- o `saida_limite_minutos=60` resolve a posicao cerca de uma
hora depois da entrada, e as entradas acontecem entre 09:16 e 11:35. O robo
raramente chega ao fim do pregao com posicao. Contraste: o backtest do
`copa_win` credita **39,1%** das saidas ao sino.

Medir assim mesmo custa dois minutos de maquina e responde uma pergunta que
"0,5% das saidas" NAO responde: o corte mais cedo pode **encurtar a janela de
atividade** e matar operacoes que existiam, ou mudar o preco daquela saida.
Numero pequeno esperado nao dispensa a medicao -- dispensa a preocupacao
DEPOIS que ela sai.

## O desenho: isolar a mudanca, nao comparar contra o default

As duas variantes passam `session_end_time` EXPLICITO (21:30 e 21:25) sobre a
config montada por `config_for`. Comparar "antes" contra o default atual seria
medir tambem qualquer outra edicao em andamento no repo -- ha' outra sessao
trabalhando nestes arquivos agora. Assim o unico eixo que muda e' o corte.

Geometria: a de PRODUCAO de hoje, ja com `alvo_multiplo=1.5` promovido.

Uso: `python -u scripts/daytrade/wdo_orb_impacto_folga_achatamento_2026_09_14.py`
"""
from __future__ import annotations

import dataclasses
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import time
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)

#: 18:30 e 18:25 de Brasilia. O fecho MEDIDO do WDO@ e' 18:29.
CORTES = [("ANTIGO_21:30", time(21, 30)), ("NOVO_21:25", time(21, 25))]
SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


def roda_pregao(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, corte in CORTES:
        strat = WdoOrbInstrumentado()          # producao: alvo 1,5x
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
        cfg = dataclasses.replace(cfg, session_end_time=corte,
                                  session_end_policy="fixed")
        res = run_intraday_backtest(bars, strat, cfg)
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        for i, t in enumerate(sorted(res.trades, key=lambda x: x.entry_ts)):
            ordem = None
            for o in ordens:
                if o["sinal_ts"] <= t.entry_ts:
                    ordem = o
                else:
                    break
            pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                          else (t.entry_price - t.exit_price)) / TICK_SIZE)
            razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                     else str(t.exit_reason))
            linhas.append({
                "corte": nome, "data": dia, "op_do_dia": i + 1,
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S"),
                "saida_utc": pd.Timestamp(t.exit_ts).strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2),
                "saida_efetiva": classifica_saida(razao, pnl_ticks,
                                                  ordem["alvo_ticks"] if ordem else float("nan")),
            })
    return linhas


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    print(f"[folga] {len(todos)} pregoes x {len(CORTES)} cortes "
          f"({[c for c, _ in CORTES]}), {MAX_WORKERS} processos\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 40 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "95_folga_achatamento.csv", index=False, encoding="utf-8")

    print("\n" + "=" * 104)
    print("IMPACTO POR JANELA")
    print("=" * 104)
    linhas_tab = []
    for rotulo, _, _, _ in JANELAS:
        for nome, _ in CORTES:
            s = df[(df.janela == rotulo) & (df.corte == nome)]
            linhas_tab.append({
                "janela": rotulo, "corte": nome, "trades": len(s),
                "liquido": round(s.pnl_brl.sum(), 2),
                "rs_por_op": round(s.pnl_brl.mean(), 2) if len(s) else float("nan"),
                "flatten": int((s.saida_efetiva == "forced_flatten").sum()),
            })
    tab = pd.DataFrame(linhas_tab)
    print(tab.to_string(index=False))

    print("\n" + "=" * 104)
    print("AS OPERACOES QUE MUDARAM  (chave: data + ordem no dia)")
    print("=" * 104)
    a = df[df.corte == CORTES[0][0]].set_index(["data", "op_do_dia"])
    b = df[df.corte == CORTES[1][0]].set_index(["data", "op_do_dia"])
    so_antigo = a.index.difference(b.index)
    so_novo = b.index.difference(a.index)
    comuns = a.index.intersection(b.index)
    difs = []
    for k in comuns:
        ra, rb = a.loc[k], b.loc[k]
        if abs(ra.pnl_brl - rb.pnl_brl) > 1e-9 or ra.saida_efetiva != rb.saida_efetiva:
            difs.append({"data": k[0], "op": k[1],
                         "antigo_saida": ra.saida_efetiva, "antigo_pnl": ra.pnl_brl,
                         "antigo_hora": ra.saida_utc,
                         "novo_saida": rb.saida_efetiva, "novo_pnl": rb.pnl_brl,
                         "novo_hora": rb.saida_utc,
                         "delta": round(rb.pnl_brl - ra.pnl_brl, 2)})
    if difs:
        d = pd.DataFrame(difs)
        print(d.to_string(index=False))
        print(f"\n  delta TOTAL das operacoes que mudaram: "
              f"R${d.delta.sum():+,.2f} em {len(d)} operacoes")
    else:
        print("  NENHUMA operacao mudou de resultado.")
    if len(so_antigo):
        print(f"\n  operacoes que SO' existem com o corte ANTIGO: {len(so_antigo)}")
        print(a.loc[so_antigo][["entrada_utc", "saida_utc", "saida_efetiva", "pnl_brl"]].to_string())
    if len(so_novo):
        print(f"\n  operacoes que SO' existem com o corte NOVO: {len(so_novo)}")
        print(b.loc[so_novo][["entrada_utc", "saida_utc", "saida_efetiva", "pnl_brl"]].to_string())

    tot_a = df[df.corte == CORTES[0][0]].pnl_brl.sum()
    tot_b = df[df.corte == CORTES[1][0]].pnl_brl.sum()
    print(f"\n  TOTAL antigo R${tot_a:+,.2f} | novo R${tot_b:+,.2f} | "
          f"delta R${tot_b - tot_a:+,.2f}")
    print(f"\n[folga] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
