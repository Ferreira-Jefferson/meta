"""TESTE (2026-09-14) -- as duas hipoteses que sobraram da coleta das 4 semanas.

## As hipoteses (ordem do dono, 2026-09-14)

H1 -- CORTAR O FADE. Nas 4 semanas de 17/08 a 11/09 a 2a operacao do dia (o
fade do rompimento oposto) deu -R$515,00 em 10 operacoes (-51,50/op) contra
-R$89,00 em 18 do rompimento (-4,94/op): 85% do prejuizo. Mas o fade foi
PROMOVIDO em 2026-09-11 justamente por medir +38,53/op no IS (n=31) e
+34,50/op no OOS (n=28). Ou 10 operacoes recentes inverteram um resultado de
59, ou as 10 sao ruido. E' isso que se mede aqui.

H2 -- FILTRAR POR AGITACAO NO SINAL. Na mesma coleta, particionando as 28
operacoes pela mediana do proprio conjunto: mercado calmo +R$538,00 (win
57,1%) contra agitado -R$1.142,00 (win 21,4%) no volume dos 5 min anteriores
ao sinal, com direcao igual em amplitude, velocidade e tamanho da faixa. E'
selecao pos-hoc, com corte na mediana da propria amostra -- exatamente o tipo
de padrao que este repo ja' refutou varias vezes (filtro dia/hora, 7 sinais de
timing, 5 ajustes estruturais). So' vale se aparecer em amostra que NAO a
gerou.

## As janelas -- e por que o OOS foi truncado

    IS           2026-02-27..2026-06-12   72 pregoes   independente
    OOS_LIMPO    2026-06-15..2026-08-14   ~44 pregoes  independente
    DESCOBERTA   2026-08-17..2026-09-11   19 pregoes   NAO valida nada

O OOS congelado da familia vai ate' 2026-08-25, mas 17..25/08 esta' DENTRO da
amostra onde H2 nasceu. Reaproveitar esses 7 pregoes como "validacao" seria
validar a hipotese com o dado que a inventou. O corte em 14/08 e' o preco de
manter as duas amostras independentes de verdade.

## Capital: R$375 REPOSTO por pregao

Ordem do dono (CLAUDE.md): capital inicial e' sempre o minimo real. Mas a
coleta de 14/09 mostrou que, em caminhada continua a R$375, dois stops calam
o robo e a janela vira censura -- S1 fez 2 trades e 177 ordens, 149 recusadas
por capital. Medir H1/H2 assim mediria o portao de capital, nao a hipotese.
Entao cada pregao roda ISOLADO partindo dos R$375 reais (mesmo padrao de
`wdof1_caixa_reposto_1mes_2026_09_10.py`), e a caminhada continua entra como
COLUNA DE RISCO ao lado, nunca como o numero que decide.

Somar pregoes de caixa reposto NAO e' um resultado de conta: e' a soma de 72
apostas independentes de R$375. Serve para comparar variantes na mesma base,
nao para dizer quanto a conta teria.

## Os achados da coleta entram no desenho (pedido do dono)

Toda linha reporta, alem do liquido:

  * `alvo_cheio` x `corte_relogio` x `stop` SEPARADOS -- 13 das 16 saidas
    carimbadas `target` na coleta eram o corte de 60 min, com R$/op 8x menor
    (item 6.40 de LICOES_DE_PRODUCAO.md);
  * `ordens/trades` -- termometro de censura por caixa (item 6.39);
  * concentracao: quanto do liquido vem das 3 melhores operacoes (na coleta,
    3 de 28 operacoes valiam +R$688,50 de um liquido de -R$604,00);
  * MFE/MAE em ticks -- o perdedor andava 11 ticks a favor antes de virar,
    contra um alvo pedido de 53.

## O que este script NAO faz

H2 e' medida por PARTICIONAMENTO das operacoes que aconteceram, nao por um
filtro de verdade dentro da estrategia. Os dois nao sao identicos: bloquear a
1a operacao do dia impede o fade de existir, e o particionamento nao captura
isso. E' deliberado -- e' o teste PEQUENO que refuta primeiro (memoria
`feedback_teste_pequeno_valida_hipotese`). Se H2 sobreviver as duas janelas
independentes, ai' vale implementar o filtro real e medir de ponta a ponta.

Uso: `python -u scripts/daytrade/wdo_orb_fade_agitacao_is_oos_2026_09_14.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    contexto_no_sinal, excursao, monta_config,
)

JANELAS = [
    ("IS", "2026-02-27", "2026-06-12", "independente"),
    ("OOS_LIMPO", "2026-06-15", "2026-08-14", "independente"),
    ("DESCOBERTA", "2026-08-17", "2026-09-11", "gerou as hipoteses"),
]
VARIANTES = [("com_fade", True), ("sem_fade", False)]

#: Limiares ABSOLUTOS congelados na amostra de descoberta (medianas das 28
#: operacoes de 17/08..11/09). Congelados de proposito: recalcular a mediana
#: dentro de cada janela nova testaria "acima da mediana local", que e' outro
#: criterio. As duas leituras sao reportadas -- se discordarem, o efeito e' de
#: regime de mercado, nao do sinal.
LIMIARES_DESCOBERTA = {
    "vol_5min": 33436.0,
    "amplitude_ticks_15min": 21.0,
    "nticks_5min": 2073.0,
    "faixa_ticks": 26.0,
}

SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


def classifica_saida(exit_reason: str, pnl_ticks: float, alvo_ticks: float) -> str:
    if exit_reason == "stop":
        return "stop"
    if exit_reason != "target":
        return exit_reason
    return "alvo_cheio" if pnl_ticks >= alvo_ticks * 0.95 else "corte_relogio"


def roda_pregao(dia: str, com_fade: bool) -> list[dict]:
    """UM pregao, caixa R$375 do zero. Devolve uma linha por operacao."""
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    strat = WdoOrbInstrumentado(fade_rompimento_oposto=com_fade)
    cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
    res = run_intraday_backtest(bars, strat, cfg)

    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    linhas = []
    for i, t in enumerate(sorted(res.trades, key=lambda x: x.entry_ts)):
        ordem = None
        for o in ordens:
            if o["sinal_ts"] <= t.entry_ts:
                ordem = o
            else:
                break
        ctx = contexto_no_sinal(bars, ordem["sinal_ts"] if ordem else t.entry_ts)
        exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
        pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                      else (t.entry_price - t.exit_price)) / TICK_SIZE)
        razao = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
        alvo = ordem["alvo_ticks"] if ordem else float("nan")
        linhas.append({
            "data": dia, "com_fade": int(com_fade),
            "op_do_dia": i + 1,
            "tipo": ordem["tipo"] if ordem else "?",
            "side": t.side,
            "pnl_brl": round(t.pnl_brl, 2),
            "pnl_ticks": round(pnl_ticks, 1),
            "alvo_ticks": alvo,
            "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
            "faixa_ticks": ordem["faixa_ticks"] if ordem else float("nan"),
            "saida_efetiva": classifica_saida(razao, pnl_ticks, alvo),
            "mfe_ticks": round(exc["mfe_ticks"], 1),
            "mae_ticks": round(exc["mae_ticks"], 1),
            "n_ordens_dia": len(ordens),
            "recusadas_capital_dia": res.ordens_recusadas_por_capital,
            **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in ctx.items()},
        })
    if not linhas and ordens:
        # pregao com sinal mas sem operacao -- importa para ordens/trades
        linhas.append({"data": dia, "com_fade": int(com_fade), "op_do_dia": 0,
                       "tipo": "", "side": "", "pnl_brl": 0.0, "pnl_ticks": 0.0,
                       "alvo_ticks": float("nan"), "stop_ticks": float("nan"),
                       "faixa_ticks": float("nan"), "saida_efetiva": "sem_operacao",
                       "mfe_ticks": float("nan"), "mae_ticks": float("nan"),
                       "n_ordens_dia": len(ordens),
                       "recusadas_capital_dia": res.ordens_recusadas_por_capital})
    return linhas


def pregoes_da_janela(inicio: str, fim: str) -> list[str]:
    bars = carregar_bars(inicio, fim)
    return [str(d) for d in sorted(set(bars.index.date))] if not bars.empty else []


# ---------------------------------------------------------------------------
# metricas
# ---------------------------------------------------------------------------

def resumo(df: pd.DataFrame) -> dict:
    ops = df[df.op_do_dia > 0]
    if ops.empty:
        return {"n": 0}
    pnl = ops["pnl_brl"]
    g, p = pnl[pnl > 0], pnl[pnl <= 0]
    top3 = pnl.nlargest(3).sum()
    saidas = ops["saida_efetiva"].value_counts()
    return {
        "n": len(ops),
        "liquido": round(pnl.sum(), 2),
        "rs_por_op": round(pnl.mean(), 2),
        "win_pct": round(100.0 * len(g) / len(ops), 1),
        "ganho_medio": round(g.mean(), 2) if len(g) else float("nan"),
        "perda_media": round(p.mean(), 2) if len(p) else float("nan"),
        "be_empirico": (round(100.0 * (-p.mean()) / (g.mean() - p.mean()), 1)
                        if len(g) and len(p) else float("nan")),
        "alvo_cheio": int(saidas.get("alvo_cheio", 0)),
        "corte_relogio": int(saidas.get("corte_relogio", 0)),
        "stops": int(saidas.get("stop", 0)),
        "top3_pct": round(100.0 * top3 / pnl.sum(), 1) if pnl.sum() != 0 else float("nan"),
        "ordens_por_trade": round(df.groupby("data")["n_ordens_dia"].first().sum() / len(ops), 1),
        "mfe_perdedor": round(ops[ops.pnl_brl <= 0]["mfe_ticks"].median(), 1) if len(p) else float("nan"),
    }


def main() -> None:
    tarefas = []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        print(f"[janela] {rotulo}: {len(dias)} pregoes ({dias[0]} .. {dias[-1]})", flush=True)
        for dia in dias:
            for nome_var, com_fade in VARIANTES:
                tarefas.append((rotulo, nome_var, dia, com_fade))
    print(f"\n[teste] {len(tarefas)} execucoes (pregao x variante), "
          f"{MAX_WORKERS} processos, capital R${CAPITAL_PARTIDA_BRL:.0f} reposto\n",
          flush=True)

    linhas = []
    feitos = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, dia, com_fade): (rot, var, dia)
                   for rot, var, dia, com_fade in tarefas}
        for fut in as_completed(futuros):
            rot, var, dia = futuros[fut]
            feitos += 1
            try:
                for linha in fut.result():
                    linhas.append({"janela": rot, "variante": var, **linha})
            except Exception as exc:
                print(f"[{rot}/{var}/{dia}] ERRO: {exc!r}", flush=True)
            if feitos % 50 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    df = pd.DataFrame(linhas)
    df.to_csv(SAIDA / "30_fade_agitacao_trades.csv", index=False, encoding="utf-8")
    print(f"\n[teste] {len(df)} linhas -> 30_fade_agitacao_trades.csv\n")

    # ---- H1: cortar o fade -------------------------------------------------
    print("=" * 110)
    print("H1 -- CORTAR O FADE   (capital R$375 reposto por pregao)")
    print("=" * 110)
    h1 = []
    for rotulo, _, _, papel in JANELAS:
        for nome_var, _ in VARIANTES:
            sub = df[(df.janela == rotulo) & (df.variante == nome_var)]
            h1.append({"janela": rotulo, "papel": papel, "variante": nome_var,
                       **resumo(sub)})
    df_h1 = pd.DataFrame(h1)
    print(df_h1.to_string(index=False))
    df_h1.to_csv(SAIDA / "31_h1_fade.csv", index=False, encoding="utf-8")

    print("\n--- a PERNA do fade isolada (so' na variante com_fade) ---")
    perna = []
    for rotulo, _, _, papel in JANELAS:
        sub = df[(df.janela == rotulo) & (df.variante == "com_fade") & (df.op_do_dia > 0)]
        for tipo in ("rompimento", "fade"):
            s = sub[sub.tipo == tipo]
            if s.empty:
                continue
            perna.append({"janela": rotulo, "papel": papel, "perna": tipo, **resumo(s)})
    df_perna = pd.DataFrame(perna)
    print(df_perna.to_string(index=False))
    df_perna.to_csv(SAIDA / "32_h1_perna_fade.csv", index=False, encoding="utf-8")

    # ---- H2: agitacao ------------------------------------------------------
    print("\n" + "=" * 110)
    print("H2 -- AGITACAO NO SINAL   (particionamento; limiar ABSOLUTO da descoberta)")
    print("=" * 110)
    h2 = []
    base = df[(df.variante == "com_fade") & (df.op_do_dia > 0)]
    for var, limiar in LIMIARES_DESCOBERTA.items():
        for rotulo, _, _, papel in JANELAS:
            sub = base[base.janela == rotulo]
            if sub.empty or var not in sub:
                continue
            for corte, s in [("calmo", sub[sub[var] <= limiar]),
                             ("agitado", sub[sub[var] > limiar])]:
                if s.empty:
                    continue
                h2.append({"variavel": var, "limiar": limiar, "janela": rotulo,
                           "papel": papel, "corte": corte, **resumo(s)})
    df_h2 = pd.DataFrame(h2)
    cols = ["variavel", "janela", "corte", "n", "liquido", "rs_por_op", "win_pct", "be_empirico"]
    print(df_h2[cols].to_string(index=False))
    df_h2.to_csv(SAIDA / "33_h2_agitacao_absoluto.csv", index=False, encoding="utf-8")

    print("\n--- H2 com corte na MEDIANA LOCAL de cada janela ---")
    h2b = []
    for var in LIMIARES_DESCOBERTA:
        for rotulo, _, _, papel in JANELAS:
            sub = base[base.janela == rotulo]
            if sub.empty or var not in sub or sub[var].isna().all():
                continue
            med = sub[var].median()
            for corte, s in [("calmo", sub[sub[var] <= med]),
                             ("agitado", sub[sub[var] > med])]:
                if s.empty:
                    continue
                h2b.append({"variavel": var, "mediana_local": round(med, 0),
                            "janela": rotulo, "corte": corte, **resumo(s)})
    df_h2b = pd.DataFrame(h2b)
    print(df_h2b[["variavel", "mediana_local", "janela", "corte", "n", "liquido",
                   "rs_por_op", "win_pct"]].to_string(index=False))
    df_h2b.to_csv(SAIDA / "34_h2_agitacao_mediana_local.csv", index=False, encoding="utf-8")

    print(f"\n[teste] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
