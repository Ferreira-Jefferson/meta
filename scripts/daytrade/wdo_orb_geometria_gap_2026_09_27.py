"""TESTE (2026-09-27) -- a geometria do wdo_orb condicionada ao TAMANHO DO GAP
overnight do dia.

## A hipotese, e de onde ela vem

`wdo_gap_padrao_nao_linear_2026_09_27.py` (estagio 1, sem motor, so'
correlacao) mediu 28 celulas de padrao nao-linear do gap overnight do WDO@
(fechamento[d-1] -> abertura[d]) contra o comportamento do PREGAO. Direcao
nao tem sinal (0/18 numa sonda linear separada), mas 3 celulas sobrevivem
Bonferroni sobre VOLATILIDADE (nao direcao) -- |gap| grande prediz pregao
mais negociado/volatil, nao para qual lado:

    |gap| x volume nos 60min iniciais        n=122  corr=+0,336  p=0,0002
    |gap| x variancia realizada do dia todo  n=122  corr=+0,271  p=0,0035
    fill-rate: gap pequeno vs grande         n=78   89,2% x 41,5%  p=0,00005

O `wdo_orb` (unica candidata viva do projeto, em PRODUCAO) tira a geometria
do tamanho da FAIXA de abertura, mas trava o stop num teto FIXO de 30 ticks
independente do dia (`stop_max_ticks`, ver a docstring de `WdoOrb`): medido
no IS congelado dos 72 pregoes, o teto MORDE em 61,1% dos pregoes (mais da
metade -- a mediana da faixa ja' e' 35, acima do teto). Se gap grande prediz
faixa mais larga, os dias de gap grande sao candidatos naturais a serem
justamente os dias em que o teto mais morde -- e a pergunta e' se destravar
o teto SO' nesses dias captura mais do movimento real sem mudar nada nos
dias normais.

## O que este script NAO faz

Nao edita `strategy/daytrade/lab/wdo_orb.py` (producao viva). Subclassa
`WdoOrb` (o mesmo padrao de `WdoOrbInstrumentado`, ja' usado por toda a
familia de scripts de 2026-09-14) e passa `stop_max_ticks` maior via
CONSTRUTOR, so' nos dias cujo tercil de gap bate com o alvo da celula -- uma
instancia NOVA por pregao, com kwargs daquele pregao (o padrao ja' existe em
`wdo_orb_geometria_is_oos_2026_09_14.roda_pregao_todas_celulas`, reaproveitado
aqui). A estrategia continua PURA: quem decide o kwarg e' o SCRIPT, nunca a
classe.

## O tercil de gap e' CAUSAL, nao global

Classificar o dia D usando terzis calculados sobre a amostra INTEIRA (IS+OOS)
usaria informacao de pregoes FUTUROS para rotular um pregao passado -- exatamente
o tipo de look-ahead que este repo proibe (AGENTS.md, regra 4). Em vez disso,
cada dia e' classificado contra os terzis de |gap| calculados so' com os dias
ANTERIORES a ele (`pandas.Series.expanding().quantile()`, deslocado 1 dia).
Isso exige um AQUECIMENTO minimo (`N_WARMUP=20` pregoes de historico) antes de
classificar de verdade -- antes disso o dia cai em "medio" por definicao (sem
ajuste, reproduz a producao). Custo do metodo, honesto: como o CSV de gap
comeca exatamente no primeiro dia do IS, os ~20 primeiros pregoes do IS ficam
sem classificacao real -- e a classificacao causal, sendo mais ruidosa que uma
classificacao global, da' MENOS dias "grande" que um corte global daria (12 no
IS, so' 5 no OOS_LIMPO, contra ~24/~15 que um corte global de 1/3 daria). Essa
perda de n e' o preco de nao olhar o futuro.

Dado de origem: `wdo_gap_padrao_nao_linear_2026_09_27_sessoes.csv` (a mesma
tabela por pregao do estudo de correlacao), que cobre 2026-02-27..2026-08-25 --
cobre os DOIS janelas usadas aqui por inteiro, exceto 1 pregao (2026-07-31,
dia com so' 3.847 ticks a partir das 15:32 -- residuo conhecido e nao
recuperavel, ver memoria `wdo_tick_canonico_regenerado_2026_09_07`), que cai
em "medio" por falta de dado.

## As 4 celulas -- eixo unico: teto do stop, condicionado ao tercil do dia

    BASE               stop_max_ticks=30 sempre (producao, sem mudanca)
    GAP_GRANDE_S40     teto 40 (+33%) SO' em dias de gap GRANDE; 30 nos demais
    GAP_GRANDE_S45     teto 45 (+50%) SO' em dias de gap GRANDE; 30 nos demais
    CTRL_PEQUENO_S40   teto 40 SO' em dias de gap PEQUENO (controle de
                       especificidade -- se o ganho aparecer aqui tambem, o
                       efeito e' "destravar o teto em qualquer dia", nao
                       "destravar em dia de gap grande")

`alvo_multiplo` continua 1,5x o stop (producao): quando o teto sobe e o range
do dia o justifica, o alvo cresce PROPORCIONALMENTE, sem precisar de um
parametro separado.

Em dias fora do alvo da celula (ex.: dia "medio"/"pequeno" para uma celula
GAP_GRANDE_*), a celula roda com kwargs VAZIOS -- ou seja, produz o MESMO
trade que a BASE produziria no mesmo dia. Isso e' verificado (nao suposto): a
tabela de "eixo morto" confirma que BASE e a celula condicionada sao
IDENTICAS fora do dia-alvo, e so' DIVERGEM nos dias-alvo -- o design elimina
sozinho a comparacao espuria.

## Metodo de decisao (reaproveitado de `wdo_orb_t15_robustez_2026_09_14.py`)

Duas janelas independentes (mesmas de `wdo_orb_fade_agitacao_is_oos_2026_09_14
.JANELAS`): IS (72 pregoes) e OOS_LIMPO (44 pregoes, 1 sem dado de gap).
Capital real R$375 REPOSTO por pregao (mede geometria, nao o portao de
capital -- mesma razao de toda a familia 2026-09-14).

A comparacao que decide NAO e' o liquido da janela inteira (a maioria dos
dias e' identica entre BASE e a celula condicionada, por design) -- e' o
PAREADO restrito aos dias-alvo: BASE x celula, SO' nos dias onde a celula
tem licenca de agir, bootstrap por PREGAO (5.000 reamostragens, emparelhado).
Reporta tambem `teto_bind`: fracao dos dias-alvo em que a faixa do dia
realmente ULTRAPASSAVA o teto antigo de 30 -- se o teto novo nao morde
tambem, a celula nao teve chance de mudar nada.

Tabela padrao via `backtest/intraday/report.py` (`LinhaResultado`/`tabela()`)
para o panorama de janela inteira -- o MaxDD ali e' de uma caminhada de caixa
VIRTUAL (capital reposto concatenado, nunca reseta), carimbado no `aviso`;
quem decide e' a tabela pareada restrita aos dias-alvo, nao esta.

Uso: `python -u scripts/daytrade/wdo_orb_geometria_gap_2026_09_27.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.report import (  # noqa: E402
    LinhaResultado, cabecalho, linha, maxdd_brl, num_br, tabela,
)
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    excursao, monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    classifica_saida, pregoes_da_janela,
)
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402

GAP_CSV = (Path(__file__).resolve().parent
           / "wdo_gap_padrao_nao_linear_2026_09_27_sessoes.csv")

#: mesmas janelas de `wdo_orb_fade_agitacao_is_oos_2026_09_14.JANELAS`
JANELAS = [
    ("IS", "2026-02-27", "2026-06-12"),
    ("OOS_LIMPO", "2026-06-15", "2026-08-14"),
]

#: pregoes de historico exigidos antes de classificar o gap de verdade --
#: menos que isso, o dia cai em "medio" (sem ajuste) por definicao.
N_WARMUP = 20

STOP_MAX_PRODUCAO = 30  # ver WdoOrb.stop_max_ticks

#: (nome, gap_alvo ou None p/ sempre, kwargs aplicados SO' no dia-alvo)
CELULAS = [
    ("BASE", None, {}),
    ("GAP_GRANDE_S40", "grande", dict(stop_max_ticks=40)),
    ("GAP_GRANDE_S45", "grande", dict(stop_max_ticks=45)),
    ("CTRL_PEQUENO_S40", "pequeno", dict(stop_max_ticks=40)),
]

SAIDA = RAIZ / "scratch" / "wdo_orb_geometria_gap_2026_09_27"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


# ---------------------------------------------------------------------------
# 1. classificacao CAUSAL do gap -- so' olha para TRAS
# ---------------------------------------------------------------------------

def classifica_gap_causal(min_hist: int = N_WARMUP) -> dict[str, str]:
    """`{data_str: "pequeno"/"medio"/"grande"}`, terzis de |gap| calculados
    so' com dias ANTERIORES ao classificado (expanding + shift(1)). Dia sem
    historico suficiente, ou sem gap valido (ex.: 1o pregao da serie, ou
    2026-07-31 sem dado), cai em "medio" -- reproduz a producao, sem ajuste."""
    df = pd.read_csv(GAP_CSV, index_col=0)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    abs_gap = df["gap_ticks"].abs()

    q1 = abs_gap.expanding(min_periods=min_hist).quantile(1 / 3).shift(1)
    q2 = abs_gap.expanding(min_periods=min_hist).quantile(2 / 3).shift(1)

    rotulos: dict[str, str] = {}
    for data, valor in abs_gap.items():
        chave = str(data.date())
        t1, t2 = q1.get(data), q2.get(data)
        if pd.isna(t1) or pd.isna(t2) or pd.isna(valor):
            rotulos[chave] = "medio"
            continue
        if valor <= t1:
            rotulos[chave] = "pequeno"
        elif valor <= t2:
            rotulos[chave] = "medio"
        else:
            rotulos[chave] = "grande"
    return rotulos


# ---------------------------------------------------------------------------
# 2. UM pregao, as 4 celulas -- tick lido uma vez
# ---------------------------------------------------------------------------

def roda_pregao_todas_celulas(dia: str, rotulo_gap: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, gap_alvo, kwargs_alvo in CELULAS:
        kwargs = dict(kwargs_alvo) if (gap_alvo is None or gap_alvo == rotulo_gap) else {}
        aplicado = bool(kwargs)
        strat = WdoOrbInstrumentado(**kwargs)
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
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
            alvo = ordem["alvo_ticks"] if ordem else float("nan")
            faixa = ordem["faixa_ticks"] if ordem else float("nan")
            exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
            linhas.append({
                "celula": nome, "data": dia, "gap_tercil": rotulo_gap,
                "kwargs_aplicado": int(aplicado),
                "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
                "op_do_dia": i + 1,
                "tipo": ordem["tipo"] if ordem else "?",
                "pnl_brl": round(t.pnl_brl, 2),
                "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "faixa_ticks": faixa,
                "teto_bind": bool(faixa is not None and not pd.isna(faixa)
                                  and faixa > STOP_MAX_PRODUCAO),
                "saida_efetiva": classifica_saida(razao, pnl_ticks, alvo),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


# ---------------------------------------------------------------------------
# 3. resumo por celula (mesmo molde de `wdo_orb_geometria_is_oos_2026_09_14.
# resumo_celula`)
# ---------------------------------------------------------------------------

def resumo_celula(ops: pd.DataFrame, pregoes_no_escopo: int) -> dict:
    if ops.empty:
        return {"n": 0}
    pnl = ops["pnl_brl"]
    g, p = pnl[pnl > 0], pnl[pnl <= 0]
    por_dia = ops.groupby("data")["pnl_brl"].sum()
    saidas = ops["saida_efetiva"].value_counts()
    top3 = pnl.nlargest(3).sum()
    return {
        "n": len(ops),
        "liquido": round(pnl.sum(), 2),
        "rs_por_op": round(pnl.mean(), 2),
        "desvio_op": round(pnl.std(ddof=1), 2) if len(ops) > 1 else float("nan"),
        "win_pct": round(100.0 * len(g) / len(ops), 1),
        "be_emp": (round(100.0 * (-p.mean()) / (g.mean() - p.mean()), 1)
                   if len(g) and len(p) else float("nan")),
        "pregoes_pos_pct": round(100.0 * (por_dia > 0).sum() / len(por_dia), 1) if len(por_dia) else float("nan"),
        "top3_pct": round(100.0 * top3 / pnl.sum(), 1) if pnl.sum() != 0 else float("nan"),
        "alvo_medio": round(ops["alvo_ticks"].mean(), 1),
        "stop_medio": round(ops["stop_ticks"].mean(), 1),
        "alvo_cheio": int(saidas.get("alvo_cheio", 0)),
        "corte_rel": int(saidas.get("corte_relogio", 0)),
        "stops": int(saidas.get("stop", 0)),
        "sem_trade": pregoes_no_escopo - ops["data"].nunique(),
        "dias": ops["data"].nunique(),
    }


# ---------------------------------------------------------------------------
# 4. bootstrap pareado por pregao (mesmo metodo de
# `wdo_orb_t15_robustez_2026_09_14.py`), restrito a um conjunto de dias
# ---------------------------------------------------------------------------

def bootstrap_pareado(df: pd.DataFrame, atual: str, candidata: str,
                       dias_alvo: list[str], n_boot: int = 5000,
                       seed: int = 20260927) -> dict:
    base = df[df.celula.isin([atual, candidata]) & df.data.isin(dias_alvo)]
    if base.empty or base.data.nunique() < 3:
        return {"n_dias": base.data.nunique() if not base.empty else 0}

    rng = np.random.default_rng(seed)
    dias = np.array(sorted(dias_alvo))
    agr = {}
    for cel in (atual, candidata):
        g = base[base.celula == cel].groupby("data")["pnl_brl"]
        agr[cel] = pd.DataFrame({"soma": g.sum(), "n": g.count()}).reindex(dias).fillna(0.0)

    ganhou_rs = ganhou_preg = ganhou_ambos = 0
    difs_rs, difs_preg = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, len(dias), len(dias))
        res = {}
        for cel in (atual, candidata):
            somas = agr[cel]["soma"].values[idx]
            ns = agr[cel]["n"].values[idx]
            total_n = ns.sum()
            res[cel] = {
                "rs": somas.sum() / total_n if total_n else np.nan,
                "preg": 100.0 * (somas > 0).sum() / max((ns > 0).sum(), 1),
            }
        d_rs = res[candidata]["rs"] - res[atual]["rs"]
        d_pr = res[candidata]["preg"] - res[atual]["preg"]
        difs_rs.append(d_rs); difs_preg.append(d_pr)
        if d_rs > 0: ganhou_rs += 1
        if d_pr > 0: ganhou_preg += 1
        if d_rs > 0 and d_pr > 0: ganhou_ambos += 1

    difs_rs = np.array(difs_rs); difs_preg = np.array(difs_preg)
    return {
        "n_dias": len(dias),
        "n_trades_atual": int(base[base.celula == atual].shape[0]),
        "n_trades_cand": int(base[base.celula == candidata].shape[0]),
        "pct_ganha_rs": round(100.0 * ganhou_rs / n_boot, 1),
        "pct_ganha_preg": round(100.0 * ganhou_preg / n_boot, 1),
        "pct_ganha_ambos": round(100.0 * ganhou_ambos / n_boot, 1),
        "mediana_dif_rs": round(float(np.median(difs_rs)), 2),
        "ic95_dif_rs": (round(float(np.percentile(difs_rs, 2.5)), 2),
                        round(float(np.percentile(difs_rs, 97.5)), 2)),
        "mediana_dif_preg": round(float(np.median(difs_preg)), 2),
        "ic95_dif_preg": (round(float(np.percentile(difs_preg, 2.5)), 2),
                          round(float(np.percentile(difs_preg, 97.5)), 2)),
    }


# ---------------------------------------------------------------------------
# 5. tabela padrao (report.py) -- panorama de janela inteira, caixa VIRTUAL
# ---------------------------------------------------------------------------

def linha_padrao(nome: str, ops: pd.DataFrame, pregoes_no_escopo: int,
                  capital_inicial: float) -> LinhaResultado:
    if ops.empty:
        return LinhaResultado(nome, 0.0, 0.0, 0.0, 0, pregoes_no_escopo,
                               retorno_pct=0.0, maxdd_pct=0.0,
                               capital_final=capital_inicial,
                               aviso="sem trades")
    ops_ord = ops.sort_values("entry_ts")
    equity = pd.Series(
        capital_inicial + ops_ord["pnl_brl"].cumsum().to_numpy(),
        index=pd.DatetimeIndex(ops_ord["entry_ts"]),
    )
    liquido = float(ops_ord["pnl_brl"].sum())
    dd = maxdd_brl(equity)
    vencedores = int((ops_ord["pnl_brl"] > 0).sum())
    return LinhaResultado(
        variante=nome,
        liquido_brl=liquido,
        maxdd_brl=dd,
        win_rate_pct=100.0 * vencedores / len(ops_ord),
        trades=len(ops_ord),
        pregoes=pregoes_no_escopo,
        retorno_pct=100.0 * liquido / capital_inicial,
        maxdd_pct=100.0 * dd / capital_inicial,
        capital_final=capital_inicial + liquido,
        aviso=("capital REPOSTO por pregao -- MaxDD e' da caminhada VIRTUAL "
               "concatenada (nunca reseta de verdade), nao da conta real"),
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    rotulos_gap = classifica_gap_causal()

    dias_por_janela: dict[str, list[str]] = {}
    tarefas: list[tuple[str, str]] = []
    for rotulo, ini, fim in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = dias
        contagem = pd.Series([rotulos_gap.get(d, "medio") for d in dias]).value_counts()
        print(f"[janela] {rotulo}: {len(dias)} pregoes ({dias[0]} .. {dias[-1]}) "
              f"| tercil gap causal: {contagem.to_dict()}", flush=True)
        for d in dias:
            tarefas.append((d, rotulos_gap.get(d, "medio")))

    print(f"\n[gap] {len(tarefas)} pregoes x {len(CELULAS)} celulas, "
          f"{MAX_WORKERS} processos, capital R${CAPITAL_PARTIDA_BRL:.0f} reposto, "
          f"teto producao={STOP_MAX_PRODUCAO}t\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao_todas_celulas, d, g): d
                   for d, g in tarefas}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{dia}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(tarefas)} pregoes", flush=True)

    df = pd.DataFrame(linhas)
    df.to_csv(SAIDA / "10_trades.csv", index=False, encoding="utf-8")
    print(f"\n[gap] {len(df)} operacoes -> 10_trades.csv")

    resultados_bootstrap = []
    for rotulo, ini, fim in JANELAS:
        dias = dias_por_janela[rotulo]
        dfj = df[df.data.isin(dias)]
        n_pregoes = len(dias)

        # ---- (A) panorama de janela inteira, tabela padrao report.py ------
        print("\n" + "=" * 132)
        print(f"JANELA {rotulo} ({n_pregoes} pregoes) -- panorama (report.py, caixa VIRTUAL)")
        print("=" * 132)
        linhas_padrao = []
        for nome, _, _ in CELULAS:
            ops = dfj[dfj.celula == nome]
            linhas_padrao.append(linha_padrao(nome, ops, n_pregoes, CAPITAL_PARTIDA_BRL))
        print(tabela(linhas_padrao))

        # ---- checagem de eixo morto: fora do dia-alvo, celula == BASE -----
        base_ops = dfj[dfj.celula == "BASE"][["data", "op_do_dia", "pnl_brl"]]
        for nome, gap_alvo, _ in CELULAS:
            if gap_alvo is None:
                continue
            cel_ops = dfj[dfj.celula == nome]
            fora_alvo = cel_ops[cel_ops.gap_tercil != gap_alvo]
            fora_base = base_ops.merge(
                fora_alvo[["data", "op_do_dia"]], on=["data", "op_do_dia"])
            comp = fora_alvo.merge(
                fora_base, on=["data", "op_do_dia"], suffixes=("_cel", "_base"))
            diverge = comp[(comp.pnl_brl_cel - comp.pnl_brl_base).abs() > 0.005]
            status = "OK (identico fora do alvo)" if diverge.empty else f"DIVERGIU em {len(diverge)} trades!"
            print(f"  [eixo] {nome} fora de dias '{gap_alvo}': {status}")

        # ---- (B) restrito aos dias-ALVO: BASE x celula condicionada -------
        print(f"\n--- {rotulo}: restrito aos dias-ALVO de cada celula (onde ela tem licenca de agir) ---")
        linhas_alvo = []
        for nome, gap_alvo, _ in CELULAS:
            if gap_alvo is None:
                continue
            dias_alvo = [d for d in dias if rotulos_gap.get(d, "medio") == gap_alvo]
            ops_cel = dfj[(dfj.celula == nome) & (dfj.data.isin(dias_alvo))]
            ops_base = dfj[(dfj.celula == "BASE") & (dfj.data.isin(dias_alvo))]
            n_dias_alvo = len(dias_alvo)
            teto_bind_pct = (round(100.0 * ops_base.groupby("data")["teto_bind"].first().mean(), 1)
                              if n_dias_alvo else float("nan"))
            for rot_linha, ops in (("BASE" + f"({gap_alvo})", ops_base), (nome, ops_cel)):
                linhas_alvo.append({
                    "gap_alvo": gap_alvo, "celula": rot_linha,
                    "n_dias_alvo": n_dias_alvo, "teto_bind_pct": teto_bind_pct,
                    **resumo_celula(ops, n_dias_alvo)})
        tab_alvo = pd.DataFrame(linhas_alvo)
        print(tab_alvo.to_string(index=False))
        tab_alvo.to_csv(SAIDA / f"20_{rotulo}_restrito_alvo.csv", index=False, encoding="utf-8")

        # ---- (C) bootstrap pareado, restrito aos dias-ALVO -----------------
        print(f"\n--- {rotulo}: bootstrap pareado por pregao (5.000 reamostragens), restrito aos dias-ALVO ---")
        for nome, gap_alvo, _ in CELULAS:
            if gap_alvo is None:
                continue
            dias_alvo = [d for d in dias if rotulos_gap.get(d, "medio") == gap_alvo]
            r = bootstrap_pareado(dfj, "BASE", nome, dias_alvo)
            r["janela"] = rotulo; r["celula"] = nome; r["gap_alvo"] = gap_alvo
            resultados_bootstrap.append(r)
            if r.get("n_dias", 0) < 3:
                print(f"  [{nome}] dias-alvo insuficientes ({r.get('n_dias', 0)}) -- nao bootstrapado")
                continue
            print(f"  [{nome}] {r['n_dias']} dias-alvo, {r['n_trades_atual']} trades BASE / "
                  f"{r['n_trades_cand']} trades {nome}")
            print(f"      R$/op maior em          {r['pct_ganha_rs']:5.1f}%  "
                  f"(mediana {r['mediana_dif_rs']:+.2f}, IC95 {r['ic95_dif_rs']})")
            print(f"      mais pregoes positivos: {r['pct_ganha_preg']:5.1f}%  "
                  f"(mediana {r['mediana_dif_preg']:+.2f}pp, IC95 {r['ic95_dif_preg']})")

    pd.DataFrame(resultados_bootstrap).to_csv(
        SAIDA / "30_bootstrap_resumo.csv", index=False, encoding="utf-8")

    # ---- leitura cruzada: so' vale se sobreviver as DUAS janelas -----------
    print("\n" + "=" * 132)
    print("LEITURA CRUZADA -- a celula so' merece considerar promocao se ganhar nas DUAS janelas "
          "independentes (IS e OOS_LIMPO) no bootstrap pareado restrito aos dias-alvo")
    print("=" * 132)
    piv = pd.DataFrame(resultados_bootstrap)
    if not piv.empty:
        cols = ["janela", "celula", "n_dias", "pct_ganha_rs", "pct_ganha_preg", "pct_ganha_ambos"]
        print(piv[[c for c in cols if c in piv.columns]].to_string(index=False))
    print(f"\n[gap] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
