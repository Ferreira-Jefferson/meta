"""WDO F1 (grid maker puro, T2/S16): fecha o ponto cego levantado pelo item
6.33 de `LICOES_DE_PRODUCAO.md` -- lá, um parâmetro de EXECUÇÃO herdado do
`copa_win` (`entrada_ttl_barras=15`, nunca varrido contra RESULTADO, só
contra segurança de envio) mudou o veredito de uma família inteira sozinho.
Este robô (`wdo_grid_reload_maker`) tem o mesmo formato de ponto cego:
`reancora_min_segundos` (freio de cadência, default de classe 10.0s) foi
calibrado em 2026-09-07 contra ENVIOS POR MINUTO (evitar estourar
`COTA_ENVIOS_POR_MINUTO=120`), nunca contra líquido/win%.

DIFERENÇA frente às 13 hipóteses já refutadas desta família (7 sinais de
timing de entrada + 5 ajustes estruturais + o atraso de cadência no REARME
PÓS-FILL, `wdof1_reload_delay_is_oos_2026_09_11.py`): aquele último script
testou um freio NOVO, nunca antes existente, no rearme depois de um
FECHAMENTO (alvo ou stop). Este aqui testa um parâmetro que JÁ EXISTE em
produção e já tem um número escolhido -- mas o número foi escolhido pela
pergunta errada. `reancora_min_segundos` governa dois caminhos, e nenhum dos
dois é o reload pós-fechamento (esse não tem freio, de propósito -- ver a
docstring da classe):
  1. reprecificação de uma `EnterLimit` AINDA pendente (nunca preencheu);
  2. rearme depois de uma RECUSA por capital insuficiente.
A própria docstring do parâmetro em `wdo_grid_reload_maker.py` já registra
uma varredura 6/10/15s -- mas rodada em 2026-09-07, ANTES de: a calibração de
fila real (329/489 -> hoje 329/494, Kaplan-Meier), `anchor_exits_at_fill`,
`fatiar_saida_alvo` + sem-prazo, e a decisão final T2/S16. Aquela varredura
também descartou o líquido de propósito ("LIQUIDO ficou FORA da escolha") por
ficar dentro do ruído do piso de capital -- o que este script reavalia no
motor atual, com o mesmo rigor (Wilson IC95% do win% contra o breakeven
empírico) das 13 hipóteses anteriores.

MOTOR: o de PRODUÇÃO completo, sem relaxar nada -- `reancora_min_segundos` é
um parâmetro NATIVO do `__init__` de `WdoGridReloadMaker` (não precisa de
subclasse, diferente do `reload_min_segundos` do script de atraso pós-fill):
pega os kwargs reais de `get_daytrade_robot("wdo_grid_reload_maker")`
(T2/S16, `fatiar_saida_alvo=True`, `EXIT_TTL_BARS_SEM_PRAZO`,
`anchor_exits_at_fill=True`, `margin_per_contract_brl`/`risco_pct_por_trade`
dinâmicos) e sobrescreve só `reancora_min_segundos`. Fila calibrada
automaticamente por `config_for`/`backtest.intraday.fidelidade` (NUNCA
digitada na mão -- e o valor vigente em 2026-09-11 é 329/494, não os 438/489
de versões antigas da docstring). Capital real R$375/pregão, nunca reposto
entre pregões (mesmo padrão dos 13 testes anteriores).

BASE E SPLIT IS/OOS: mesma lógica de `wdof1_combo_t3_is_oos_real_2026_09_11.py`
e `wdof1_reload_delay_is_oos_2026_09_11.py` -- `data/raw_ticks/WDO_A_.parquet`
+ os dias extras já cacheados em barra degenerada, corte cronológico 2/3-1/3
sem sobreposição:

    IS  = 2026-02-27 .. 2026-07-06  (88 pregões)
    OOS = 2026-07-07 .. 2026-09-09  (44 pregões, reservado)

MÉTODO: varredura no IS em {2, 5, 10 (controle/produção atual), 20, 30, 60}
segundos, `ProcessPoolExecutor` com `submit`/`as_completed`, streaming de
resultado por célula. Só confirma no OOS o valor que passar no IS com IC95%
de Wilson do win% inteiramente ACIMA do breakeven empírico, líquido positivo
E censura controlada -- disciplina idêntica às 13 hipóteses anteriores (1 só
candidato gasta o teste cego)."""
from __future__ import annotations

import inspect
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

VALORES_IS = [2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
CONTROLE = 10.0  # producao atual -- default de classe de WdoGridReloadMaker


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


# ------------------------------------------------------------- cache de barras
def _bars_path(dia: date) -> Path:
    dia_str = dia.isoformat()
    for prefixo in ("WDOV26_", "WDO_at_", "WDO_hist_"):
        p = BARS_DIR / f"{prefixo}{dia_str}.parquet"
        if p.exists():
            return p
    return BARS_DIR / f"WDO_hist_{dia_str}.parquet"


def preparar_cache_de_barras(dias: list[date]) -> None:
    """Reusa o cache de barra degenerada já produzido pelos scripts irmãos
    desta mesma sessão (`wdof1_combo_t3_is_oos_real_2026_09_11.py`,
    `wdof1_reload_delay_is_oos_2026_09_11.py`) -- converte só o que ainda não
    existe."""
    faltando = {d for d in dias if not _bars_path(d).exists()}
    if not faltando:
        print(f"[cache] {len(dias)} pregoes ja cacheados em barra degenerada -- nada a converter.", flush=True)
        return
    print(f"[cache] convertendo {len(faltando)} pregoes de tick local -> barra "
          f"degenerada (fonte: {TICK_PARQUET_LOCAL.name}) ...", flush=True)
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars

    ticks = pd.read_parquet(TICK_PARQUET_LOCAL)
    convertidos = 0
    for d, sub in ticks.groupby(ticks.index.date):
        if d not in faltando or sub.empty:
            continue
        bars = ticks_to_degenerate_bars(sub)
        bars.to_parquet(BARS_DIR / f"WDO_hist_{d.isoformat()}.parquet")
        convertidos += 1
    del ticks
    print(f"[cache] {convertidos}/{len(faltando)} pregoes convertidos e gravados em {BARS_DIR}", flush=True)
    ainda_faltando = sorted(d for d in faltando if not _bars_path(d).exists())
    if ainda_faltando:
        print(f"[cache] AVISO -- sem tick local para: {ainda_faltando} (seguem de fora do teste)")


# ------------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia = spec["dia"]
    valor = spec["valor"]
    caminho = _bars_path(dia)
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    # kwargs REAIS de producao (T2/S16, fatiar_saida_alvo, sem prazo,
    # anchor_exits_at_fill, dimensionamento dinamico por caixa/risco) --
    # sobrescreve SO' reancora_min_segundos.
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    kwargs = {p: getattr(robo, p) for p in params}
    kwargs["reancora_min_segundos"] = valor
    strat = WdoGridReloadMaker(**kwargs)

    _contador = {"recusas": 0}
    _on_rejected_original = strat.on_order_rejected

    def _on_order_rejected_contado(ts, _orig=_on_rejected_original, _c=_contador):
        _c["recusas"] += 1
        return _orig(ts)

    strat.on_order_rejected = _on_order_rejected_contado

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    equity = res.equity_curve
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl < 0]
    return {
        "spec": {"dia": dia.isoformat(), "valor": valor},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "maxdd_brl": _maxdd(equity),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "recusas_capital": _contador["recusas"],
        "fila_entrada_qty": float(getattr(res, "fila_entrada_qty", 0.0) or 0.0),
        "fila_saida_qty": float(getattr(res, "fila_saida_qty", 0.0) or 0.0),
        "deslize_alvo_ticks": float(getattr(res, "deslize_alvo_ticks", 0.0) or 0.0),
    }


def _maxdd(equity: pd.Series) -> float:
    if equity is None or equity.empty:
        return 0.0
    pico = equity.cummax()
    return float((pico - equity).max())


# ------------------------------------------------------------------- agregacao
def _resumir(cels: list[dict]) -> dict:
    n = sum(c["n"] for c in cels)
    n_ganhos = sum(c["n_ganhos"] for c in cels)
    n_perdas = sum(c["n_perdas"] for c in cels)
    soma_ganhos = sum(c["soma_ganhos"] for c in cels)
    soma_perdas = sum(c["soma_perdas"] for c in cels)
    liquido_total = sum(c["pnl"] for c in cels)
    maxdd_total = max((c["maxdd_brl"] for c in cels), default=0.0)
    n_dias = len(cels)
    n_pos = sum(1 for c in cels if c["pnl"] > 0)
    n_neg = sum(1 for c in cels if c["pnl"] < 0)
    n_zero = sum(1 for c in cels if c["n"] == 0)
    n_cens = sum(1 for c in cels if c["recusas_capital"] > 0)
    caixa_min = min((c["caixa_min"] for c in cels), default=float("nan"))
    ganho_medio = soma_ganhos / n_ganhos if n_ganhos else float("nan")
    perda_media = abs(soma_perdas / n_perdas) if n_perdas else float("nan")
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if n_ganhos and n_perdas else float("nan"))
    win = 100.0 * n_ganhos / n if n else float("nan")
    lo, hi = ic_wilson(n_ganhos, n)
    if n == 0 or math.isnan(be_emp):
        veredito = "sem dado"
    elif hi < be_emp:
        veredito = "NEGATIVA"
    elif lo > be_emp:
        veredito = "POSITIVA"
    else:
        veredito = "indefinido"
    liq_preg = liquido_total / n_dias if n_dias else float("nan")
    trd_preg = n / n_dias if n_dias else float("nan")
    return dict(n=n, n_ganhos=n_ganhos, n_perdas=n_perdas, win=win,
                ganho_medio=ganho_medio, perda_media=perda_media, be_emp=be_emp,
                lo=lo, hi=hi, veredito=veredito, liquido_total=liquido_total,
                liq_preg=liq_preg, trd_preg=trd_preg, n_pos=n_pos, n_neg=n_neg,
                n_zero=n_zero, n_cens=n_cens, n_dias=n_dias, maxdd_total=maxdd_total,
                caixa_min=caixa_min)


def _imprime_tabela(titulo: str, resumo: dict, valores: list[float]) -> None:
    print("=" * 160)
    print(titulo)
    print("=" * 160)
    cab = (f"{'valor(s)':<10}{'n':>6}{'win%':>8}{'ganho_med':>11}{'perda_med':>11}"
           f"{'BE emp.':>9}{'IC95 win%':>18}{'veredito':>12}{'liq. total':>13}"
           f"{'liq/preg':>11}{'trd/preg':>9}{'MaxDD R$':>11}{'caixa min':>11}"
           f"{'preg +':>7}{'preg -':>7}{'preg 0':>7}{'preg cens.':>11}{'pregoes':>9}")
    print(cab)
    print("-" * len(cab))
    for v in valores:
        r = resumo[v]
        ic_txt = f"[{r['lo']:.2f};{r['hi']:.2f}]"
        print(f"{v:<10.1f}{r['n']:>6}{r['win']:>7.2f}%{r['ganho_medio']:>11.2f}"
              f"{r['perda_media']:>11.2f}{r['be_emp']:>8.2f}%"
              f"{ic_txt:>18}{r['veredito']:>12}"
              f"{r['liquido_total']:>13.2f}{r['liq_preg']:>11.2f}{r['trd_preg']:>9.1f}"
              f"{r['maxdd_total']:>11.2f}{r['caixa_min']:>11.2f}"
              f"{r['n_pos']:>7}{r['n_neg']:>7}{r['n_zero']:>7}{r['n_cens']:>11}{r['n_dias']:>9}")
    print("-" * len(cab))


def main() -> None:
    t_inicio = time.perf_counter()

    if not TICK_PARQUET_LOCAL.exists():
        raise SystemExit(f"[erro] nao encontrei {TICK_PARQUET_LOCAL}")

    print(f"[dado] carregando lista de pregoes de {TICK_PARQUET_LOCAL} ...", flush=True)
    ticks_meta = pd.read_parquet(TICK_PARQUET_LOCAL, columns=["last"])
    dias_locais = sorted(set(ticks_meta.index.date))
    del ticks_meta
    dias_extras = [d for d in (date(2026, 9, 8), date(2026, 9, 9))
                   if _bars_path(d).exists()]
    dias_todos = sorted(set(dias_locais) | set(dias_extras))
    print(f"[dado] {len(dias_locais)} pregoes no parquet canonico local "
          f"({dias_locais[0]} .. {dias_locais[-1]}) + {len(dias_extras)} pregoes "
          f"ja cacheados ({[d.isoformat() for d in dias_extras]}) = "
          f"{len(dias_todos)} pregoes reais totais.\n", flush=True)

    n = len(dias_todos)
    corte = round(n * 2 / 3)
    IS_DIAS = dias_todos[:corte]
    OOS_DIAS = dias_todos[corte:]
    print(f"[split] IS  = {IS_DIAS[0]} .. {IS_DIAS[-1]}  ({len(IS_DIAS)} pregoes)")
    print(f"[split] OOS = {OOS_DIAS[0]} .. {OOS_DIAS[-1]}  ({len(OOS_DIAS)} pregoes)\n", flush=True)

    preparar_cache_de_barras(dias_todos)

    # -------------------------------------------------------------- IS
    specs_is = [{"dia": d, "valor": v} for d in IS_DIAS for v in VALORES_IS]
    print(f"[IS] {len(specs_is)} celulas ({len(VALORES_IS)} valores de "
          f"reancora_min_segundos x {len(IS_DIAS)} pregoes), motor de producao "
          f"(T2/S16, fatiar_saida_alvo, sem prazo, anchor_exits_at_fill), "
          f"capital R${CAPITAL_REAL_BRL:.0f}/pregao NUNCA reposto, fila calibrada\n", flush=True)

    resultados_is: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs_is}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados_is.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs_is)}] {s['dia']} valor={s['valor']}s: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs_is)}] {s['dia']} valor={s['valor']:>5.1f}s  "
                      f"n={r['n']:>4}  pnl=R${r['pnl']:>9.2f}  caixa_min=R${r['caixa_min']:>7.2f}  "
                      f"recusas={r['recusas_capital']}", flush=True)

    print(f"\n[IS] {len(resultados_is)} celulas em "
          f"{(time.perf_counter()-t_inicio)/60:.1f} min\n", flush=True)

    por_valor_is: dict[float, list[dict]] = {v: [] for v in VALORES_IS}
    for r in resultados_is:
        if "erro" not in r:
            por_valor_is[r["spec"]["valor"]].append(r)

    resumo_is = {v: _resumir(cels) for v, cels in por_valor_is.items()}
    _imprime_tabela("RESULTADO IS -- varredura de reancora_min_segundos "
                     f"(controle/producao atual = {CONTROLE}s)",
                     resumo_is, VALORES_IS)

    print("\nLEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media), nulo EMPIRICO de cada celula.")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled dentro de cada valor.")
    print(" - veredito POSITIVA exige IC95 inteiro ACIMA do BE empirico.")
    print(" - 'preg cens.' = pregoes com >=1 recusa de capital (portao de R$375, nao geometria).")
    print(" - 'preg 0' = pregoes sem NENHUM trade (censura total -- robo mudo).")
    fila_ent = next((c["fila_entrada_qty"] for cels in por_valor_is.values() for c in cels), 0.0)
    fila_sai = next((c["fila_saida_qty"] for cels in por_valor_is.values() for c in cels), 0.0)
    print(f" - fila calibrada usada: entrada={fila_ent:.0f} / saida={fila_sai:.0f} "
          f"(backtest.intraday.fidelidade, herdada de config_for)")

    r_controle = resumo_is[CONTROLE]
    print(f"\n[controle] reancora_min_segundos={CONTROLE}s (producao atual): "
          f"liquido R${r_controle['liquido_total']:.2f}, win% {r_controle['win']:.2f}%, "
          f"BE emp. {r_controle['be_emp']:.2f}%, veredito {r_controle['veredito']}, "
          f"{r_controle['n_zero']}/{r_controle['n_dias']} pregoes sem trade")

    # ------------------------------------------------- escolha do candidato
    candidatos = []
    for v in VALORES_IS:
        if v == CONTROLE:
            continue  # controle nao compete consigo mesmo -- so' alternativas
        r = resumo_is[v]
        censura_ok = r["n_cens"] <= 0.1 * r["n_dias"]  # <=10% dos pregoes censurados
        mudo_ok = r["n_zero"] <= 0.1 * r["n_dias"]  # <=10% dos pregoes sem trade
        if (r["veredito"] == "POSITIVA" and r["liquido_total"] > 0
                and censura_ok and mudo_ok
                and r["liquido_total"] > r_controle["liquido_total"]):
            candidatos.append(v)

    print(f"\n[decisao] candidatos que passam (POSITIVA + liquido>0 + censura<=10% + "
          f"mudo<=10% + liquido>controle no IS): {candidatos if candidatos else 'NENHUM'}", flush=True)

    if not candidatos:
        print("\n[VEREDITO] Nenhum valor alternativo de reancora_min_segundos produziu IC95% "
              "do win% inteiramente acima do breakeven empirico com liquido positivo, MAIOR "
              "que o controle (10s) e censura/mudez controladas no IS. Hipotese 14 "
              "(freio de cadencia de reprecificacao/rearme-pos-recusa contra RESULTADO, nao "
              "so' contra taxa de envio) e' REFUTADA/NULA pelo mesmo criterio das 13 "
              "anteriores -- OOS NAO sera' rodado (disciplina de nao gastar o teste cego sem "
              "candidato do IS).")
        print(f"\n[fim] tempo total {(time.perf_counter()-t_inicio)/60:.1f} min", flush=True)
        return

    # Disciplina anti multiple-comparison: escolhe 1 so' candidato (o de
    # maior liquido total dentre os que passaram) para confirmar no OOS.
    escolhido = max(candidatos, key=lambda v: resumo_is[v]["liquido_total"])
    print(f"[decisao] candidato UNICO escolhido para confirmacao OOS: "
          f"reancora_min_segundos={escolhido}s (maior liquido total entre os aprovados)\n", flush=True)

    specs_oos = [{"dia": d, "valor": v} for d in OOS_DIAS for v in (CONTROLE, escolhido)]
    print(f"[OOS] {len(specs_oos)} celulas (controle {CONTROLE}s + candidato {escolhido}s x "
          f"{len(OOS_DIAS)} pregoes)\n", flush=True)

    resultados_oos: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs_oos}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados_oos.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs_oos)}] {s['dia']} valor={s['valor']}s: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs_oos)}] {s['dia']} valor={s['valor']:>5.1f}s  "
                      f"n={r['n']:>4}  pnl=R${r['pnl']:>9.2f}  caixa_min=R${r['caixa_min']:>7.2f}  "
                      f"recusas={r['recusas_capital']}", flush=True)

    por_valor_oos: dict[float, list[dict]] = {CONTROLE: [], escolhido: []}
    for r in resultados_oos:
        if "erro" not in r:
            por_valor_oos[r["spec"]["valor"]].append(r)
    resumo_oos = {v: _resumir(cels) for v, cels in por_valor_oos.items()}
    _imprime_tabela(f"RESULTADO OOS -- confirmacao do candidato {escolhido}s vs controle {CONTROLE}s",
                     resumo_oos, [CONTROLE, escolhido])

    r_oos_cand = resumo_oos[escolhido]
    r_oos_ctrl = resumo_oos[CONTROLE]
    if (r_oos_cand["veredito"] == "POSITIVA" and r_oos_cand["liquido_total"] > 0
            and r_oos_cand["liquido_total"] > r_oos_ctrl["liquido_total"]):
        print(f"\n[VEREDITO] reancora_min_segundos={escolhido}s CONFIRMADO no OOS: "
              f"win% IC95% acima do BE empirico, liquido R${r_oos_cand['liquido_total']:.2f} "
              f"> controle R${r_oos_ctrl['liquido_total']:.2f}. Candidato a mudanca de producao "
              f"(pendente decisao do dono).")
    else:
        print(f"\n[VEREDITO] reancora_min_segundos={escolhido}s NAO se confirma no OOS "
              f"(veredito {r_oos_cand['veredito']}, liquido R${r_oos_cand['liquido_total']:.2f} "
              f"contra controle R${r_oos_ctrl['liquido_total']:.2f}) -- REFUTADA. O default de "
              f"producao ({CONTROLE}s) fica como esta.")

    print(f"\n[fim] tempo total {(time.perf_counter()-t_inicio)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
