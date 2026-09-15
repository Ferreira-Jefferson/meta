# -*- coding: utf-8 -*-
"""copa_win: o sino da' vantagem, ou uma REGRA DE PARADA DO DIA e' melhor?

PERGUNTA DO DONO, 2026-09-14. `copa_win` (TOP-1, config de PRODUCAO --
`janela_rompimento=10, alvo_vol=7.6, stop_vol=12.0, entrada_ttl_barras=5,
entrada_maker=True, fatiar_saida_alvo=True`, importada DIRETO de
`strategy.daytrade.registry._KWARGS_PADRAO` -- nunca redigitada aqui) sai do
pregao por ALVO, STOP ou pelo ACHATAMENTO de fim de pregao (o "sino"). Compara
quatro regras:

  A -- baseline: como esta' hoje, so' que sob o CORTE DE ACHATAMENTO NOVO de
       2026-09-14 (fim - 5min, ver `SymbolProfile.flatten_cut_time` /
       `config_for` -- ja e' automatico, ninguem digita horario aqui). Todo
       numero anterior do copa_win foi medido com o corte ANTIGO (fim exato),
       entao A precisa ser REMEDIDO, nao copiado de nenhuma memoria.
  B -- "para na 1a vitoria": assim que um TRADE FECHA POSITIVO (individual,
       nao acumulado), nao abre mais entrada no pregao. A posicao aberta (se
       houver) continua sendo gerida normalmente ate alvo/stop/sino.
  C -- "recupera e sai": monitora se o acumulado do dia ja' esteve NEGATIVO;
       a partir do momento em que ele volta a >= 0, para de abrir entradas.
       Se o dia nunca foi negativo, esta regra nunca dispara (o robo opera o
       pregao inteiro, MESMO regime da producao).
  D -- generalizacao: para de abrir entradas assim que o acumulado do dia >
       0, em QUALQUER momento -- nao exige ter passado por negativo antes
       (diferenca de C) e usa o ACUMULADO, nao o trade individual (diferenca
       de B). B e C sao casos particulares desta regra geral; a medicao abaixo
       mostra se a distincao entre as tres muda alguma coisa.

Em TODAS, o sino continua existindo como REDE -- a posicao aberta tem de
fechar no fim do pregao (achatamento). Nenhuma das quatro cancela ordem de
reteste ja' pendente no book quando o gatilho dispara no meio da espera --
so' impede que `_entrada()` EMITA uma NOVA ordem dali pra frente (ver a
docstring de `CopaWinParadaDia` abaixo).

## O VIES A ATACAR

"Parar quando esta ganhando" corta a cauda DIREITA e deixa a esquerda
inteira -- sobe win% e frac de dias positivos enquanto o liquido pode CAIR.
O projeto ja refutou duas ideias da mesma familia (`wdo_orb_parada_por_
contagem_refutado_2026_09_11`, escada `teto_perda_abs_brl` do proprio
copa_win, desligada venceu em 8 de 8). Por isso a funcao objetivo e'
DECLARADA antes de rodar (mesmo criterio de `copawin_consistencia_
diagnostico_2026_09_11.py`, aqui estendido para comparar REGRAS de parada em
vez de PARAMETROS de geometria):

  1. fracao de PREGOES individuais positivos (preg+)
  2. fracao de BLOCOS ROLANTES de 20 pregoes positivos (bl20+)
  3. fracao de MESES positivos (mes+)
  4. concentracao nos 5 melhores dias (top5)
  5. maior sequencia de pregoes NEGATIVOS consecutivos (seq-)
  6. liquido, MaxDD, lucro/DD (tabela padrao)
  7. quanto do liquido vem do ACHATAMENTO (flat$) -- a metrica que motivou a
     config atual (7,6/ttl5, ver registry.py)
  8. o par que resolve a confusao do dono ("100% dos dias de lucro"):
     fracao de PREGOES individuais positivos  x  fracao de DATAS DE INICIO
     cuja curva acumulada de 40 pregoes termina positiva (76 datas de
     inicio, mesma metodologia de `copawin_piso_por_data_de_inicio_2026_09_
     11.py`, capital R$3.000) -- SO' para a config A (producao), porque e'
     ela que gerou a confusao.

Veredito de EDGE continua sendo o de sempre (itens 6.22/6.23): IC95% do
win% contra o BREAKEVEN EMPIRICO `perda_media/(ganho_media+perda_media)`.
As seis metricas de constancia ORDENAM, nao promovem.

Capital: R$3.000 (o que o slot usa hoje, `db/live_process.json`) decide.
R$250 roda tambem, para contexto -- e' esperado que censure (ver a docstring
de `CopaWin.capital_minimo_recomendado_brl`: a R$600 a producao ja' morre
mediano; R$250 e' ainda mais abaixo do piso de R$3.000 medido).

Janelas: IS (< 2026-06-13), OOS (>= 2026-06-13) e HISTORICO COMPLETO (191
pregoes, 2025-12-01 a 2026-09-10 -- 2026-09-11 tem so' 367 barras, fica de
fora pelo mesmo filtro `MIN_BARRAS_POR_PREGAO` de sempre).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_parada_dia_is_oos_2026_09_14.py`
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
BLOCO = 20                          # pregoes por bloco rolante de constancia
HORIZONTE_INICIO = 40               # pregoes a frente, robustez por data de inicio
PASSO_INICIO = 2                    # 1 a cada N pregoes como data de inicio
CAPITAL_DECIDE = 3_000.0            # o que o slot usa hoje
CAPITAIS = [3_000.0, 250.0]         # 250 = contexto (censura esperada)

VARIANTES = {
    "A baseline (sino)": "nenhuma",
    "B 1a vitoria": "b_primeira_vitoria",
    "C recupera e sai": "c_recupera_e_sai",
    "D pnl_dia>0": "d_generalizacao",
}

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    """Wilson score, mesma formula de `copawin_consistencia_diagnostico_
    2026_09_11.py` -- reproduzida aqui (nao importada) porque aquele script
    nao expoe a funcao como modulo publico."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


# ---------------------------------------------------------------------------
# A REGRA DE PARADA -- wrapper de EXPERIMENTO por cima do CopaWin real.
# ---------------------------------------------------------------------------

def _construir_estrategia(modo_parada: str, capital: float):
    """`CopaWin` de PRODUCAO (kwargs vindos direto de `registry._KWARGS_
    PADRAO`, nunca redigitados) envolvido por `CopaWinParadaDia`, que so'
    intercepta acoes de ENTRADA (`Enter`/`EnterLimit`) -- `Exit`/`AdjustStop`
    de posicao ja' aberta NUNCA sao bloqueados, entao o sino continua valendo
    como rede em TODAS as variantes, exatamente como pedido."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.base import Enter, EnterLimit, IntradayAction
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    class CopaWinParadaDia(CopaWin):
        """`modo_parada`:
          - "nenhuma": byte a byte igual ao `CopaWin` puro (config A).
          - "b_primeira_vitoria": trava assim que um TRADE INDIVIDUAL (nao o
            acumulado) fecha com pnl > 0 -- mesmo com o dia ainda no
            vermelho por causa de perdas anteriores.
          - "c_recupera_e_sai": so' trava se o acumulado do dia JA' ESTEVE
            negativo e agora volta a `>= 0`. Nunca dispara num dia que
            comeca ganhando e nunca fica negativo.
          - "d_generalizacao": trava assim que o acumulado do dia (`session_
            pnl_brl`, so' PnL REALIZADO -- `machine.py` so' incrementa isto
            em `_close_position`, nunca por marcacao intra-barra) fica > 0,
            em qualquer momento, sem exigir ter passado por negativo.

        Deteccao do PNL de um trade individual (para B): como o motor so'
        chama `on_bar` com posicoes ja' PREENCHIDAS/JA' FECHADAS (nunca no
        meio do fill), a transicao "tinha posicao no bar anterior -> nao tem
        mais agora" e' o sinal de fechamento; o PNL do trade e' a diferenca
        entre o `session_pnl_brl` de agora e o valor guardado na ULTIMA vez
        em que o robo estava FLAT (baseline antes de abrir esse trade).

        Simplificacao conhecida, documentada em vez de escondida: uma ordem
        de RETESTE ja' pendente no book (armada num bar ANTES do gatilho
        disparar) pode ainda preencher depois do gatilho -- so' a PROXIMA
        chamada a `_entrada()` (que emitiria uma nova `Enter`/`EnterLimit`)
        e' bloqueada. Ao vivo isso seria "cancele a ordem pendente tambem";
        aqui, com `entrada_ttl_barras=5`, a janela de exposicao residual e'
        de no maximo 5 barras M1 e afeta igualmente as 4 variantes -- nao
        favorece nenhuma na comparacao."""

        def __init__(self, *args, modo_parada: str = "nenhuma", **kwargs):
            super().__init__(*args, **kwargs)
            if modo_parada not in (
                "nenhuma", "b_primeira_vitoria", "c_recupera_e_sai", "d_generalizacao",
            ):
                raise ValueError(f"modo_parada invalido: {modo_parada!r}")
            self.modo_parada = modo_parada
            self._parar_entradas_hoje = False
            self._esteve_negativo_hoje = False
            self._tinha_posicao_bar_anterior = False
            self._pnl_baseline_flat = 0.0

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            self._parar_entradas_hoje = False
            self._esteve_negativo_hoje = False
            self._tinha_posicao_bar_anterior = False
            self._pnl_baseline_flat = 0.0

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            eps = 1e-9
            tinha_agora = bool(positions)

            if not tinha_agora and self._tinha_posicao_bar_anterior:
                trade_pnl = session_pnl_brl - self._pnl_baseline_flat
                if self.modo_parada == "b_primeira_vitoria" and trade_pnl > eps:
                    self._parar_entradas_hoje = True
            self._tinha_posicao_bar_anterior = tinha_agora
            if not tinha_agora:
                self._pnl_baseline_flat = session_pnl_brl

            if session_pnl_brl < -eps:
                self._esteve_negativo_hoje = True
            if (self.modo_parada == "c_recupera_e_sai"
                    and self._esteve_negativo_hoje and session_pnl_brl >= -eps):
                self._parar_entradas_hoje = True
            if self.modo_parada == "d_generalizacao" and session_pnl_brl > eps:
                self._parar_entradas_hoje = True

            acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
            if self._parar_entradas_hoje and not positions:
                acoes = [a for a in acoes if not isinstance(a, (Enter, EnterLimit))]
            return acoes

    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    kwargs["modo_parada"] = modo_parada
    return CopaWinParadaDia(**kwargs)


# ---------------------------------------------------------------------------
# metricas de constancia (mesmas 6 de copawin_consistencia_diagnostico)
# ---------------------------------------------------------------------------

def consistencia(trades, dias_da_janela):
    por_dia: dict = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela],
                       index=pd.to_datetime(dias_da_janela))

    com_trade = list(por_dia.values())
    preg_pos = sum(1 for v in com_trade if v > 0)

    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    blocos_pos = sum(1 for b in blocos if b > 0)

    mes = serie.groupby([serie.index.year, serie.index.month]).sum()
    meses_pos = int((mes > 0).sum())

    ganhos_dia = sorted((v for v in com_trade if v > 0), reverse=True)
    bruto_pos = sum(ganhos_dia)
    top5 = (sum(ganhos_dia[:5]) / bruto_pos) if bruto_pos > 0 else float("nan")

    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0

    liquido = float(serie.sum())
    flat = sum(t.pnl_brl for t in trades if t.exit_reason.value == "forced_flatten")
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = (abs(sum(p) / len(p))) if p else 0.0
    gd = float(pd.Series(g).std(ddof=1)) if len(g) > 1 else 0.0
    pd_ = float(pd.Series(p).std(ddof=1)) if len(p) > 1 else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and n else "--"

    return dict(
        liquido=liquido, n=n, pregoes=len(dias_da_janela),
        com_trade=len(com_trade), sem_trade=len(dias_da_janela) - len(com_trade),
        preg_pos=preg_pos,
        frac_preg=(preg_pos / len(com_trade)) if com_trade else float("nan"),
        blocos=len(blocos), frac_bl=(blocos_pos / len(blocos)) if blocos else float("nan"),
        meses=len(mes), frac_mes=(meses_pos / len(mes)) if len(mes) else float("nan"),
        top5=top5, seq_neg=pior,
        flat_share=(flat / liquido) if liquido else float("nan"),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi, veredito=ver,
        ganho_medio=gm, perda_media=pm, ganho_dp=gd, perda_dp=pd_,
        pnl_dia_media=float(serie.mean()) if len(serie) else float("nan"),
        pnl_dia_dp=float(serie.std(ddof=1)) if len(serie) > 1 else float("nan"),
        serie=serie,
    )


def _df():
    if "df" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(completos) for d in df.index.date]]
        _CACHE["dias"] = completos
    return _CACHE["df"], _CACHE["dias"]


def _roda_janela(capital: float, modo_parada: str, dias_janela: list):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    df, _ = _df()
    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _construir_estrategia(modo_parada, capital)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    return res


def _unidade_tabela(args):
    capital, janela_nome, modo_parada, variante_nome, dias_janela = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda_janela(capital, modo_parada, dias_janela)
    c = consistencia(list(res.trades), dias_janela)
    return dict(
        capital=capital, janela=janela_nome, variante=variante_nome,
        c=c, res=res,
    )


def _unidade_inicio(args):
    capital, variante_nome, modo_parada, i_inicio = args
    buf = StringIO()
    with redirect_stdout(buf):
        df, dias = _df()
        janela = dias[i_inicio:i_inicio + HORIZONTE_INICIO]
        res = _roda_janela(capital, modo_parada, janela)
    trades = list(res.trades)
    com = len({t.entry_ts.date() for t in trades})
    liquido = sum(t.pnl_brl for t in trades)
    zerou = getattr(res, "wiped_out_at", None) is not None
    calou = (len(janela) - com) > 0
    return dict(
        capital=capital, variante=variante_nome, inicio=dias[i_inicio],
        liquido=liquido, positivo=(liquido > 0), zerou=zerou, calou=calou,
        trades=len(trades),
    )


def main() -> None:
    df, dias = _df()
    corte = pd.Timestamp("2026-06-13").date()
    janelas = {
        "IS (<2026-06-13)": [d for d in dias if d < corte],
        "OOS (>=2026-06-13)": [d for d in dias if d >= corte],
        "HISTORICO COMPLETO": dias,
    }

    print("=" * 100)
    print("copa_win -- SINO x REGRA DE PARADA DO DIA, corte de achatamento NOVO (fim-5min)")
    print("=" * 100)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]}), "
          f"IS={len(janelas['IS (<2026-06-13)'])} OOS={len(janelas['OOS (>=2026-06-13)'])}")
    print("config de PRODUCAO importada de registry._KWARGS_PADRAO['copa_win'] "
          "(alvo_vol=7,6 / stop_vol=12,0 / entrada_ttl_barras=5 / entrada_maker=True "
          "/ fatiar_saida_alvo=True) -- nao redigitada aqui.\n", flush=True)

    # ---------------- FASE 1: tabela padrao A x B x C x D, 3 janelas x 2 capitais ----------------
    tarefas = []
    for capital in CAPITAIS:
        for janela_nome, dias_janela in janelas.items():
            for variante_nome, modo in VARIANTES.items():
                tarefas.append((capital, janela_nome, modo, variante_nome, dias_janela))

    print(f"FASE 1: {len(tarefas)} rodadas (tabela padrao)...", flush=True)
    resultados_tabela = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_tabela, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            chave = (r["capital"], r["janela"])
            resultados_tabela.setdefault(chave, {})[r["variante"]] = r
            c = r["c"]
            print(f"  [{br(r['capital'], 0).rjust(6)}] {r['janela']:<20} "
                  f"{r['variante']:<20} liquido={br(c['liquido']).rjust(12)}  "
                  f"trades={c['n']:>5}  sem_trade={c['sem_trade']:>3}d  "
                  f"preg+={br(100*c['frac_preg'],0) if c['frac_preg']==c['frac_preg'] else '--'}%",
                  flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela

    EXTRAS = ("preg+", "bl20+", "mes+", "top5", "seq-", "flat$", "BEemp%", "veredito", "sem_tr")
    for capital in CAPITAIS:
        for janela_nome in janelas:
            bloco = resultados_tabela[(capital, janela_nome)]
            print(f"\n\n===== capital R$ {br(capital,0)} -- {janela_nome} =====")
            linhas = []
            for variante_nome in VARIANTES:  # ordem declarada, A primeiro
                r = bloco[variante_nome]
                c = r["c"]
                extras = {
                    "preg+": (br(100 * c["frac_preg"], 0) + "%") if c["frac_preg"] == c["frac_preg"] else "--",
                    "bl20+": (br(100 * c["frac_bl"], 0) + "%") if c["frac_bl"] == c["frac_bl"] else "--",
                    "mes+": (br(100 * c["frac_mes"], 0) + "%") if c["frac_mes"] == c["frac_mes"] else "--",
                    "top5": (br(100 * c["top5"], 0) + "%") if c["top5"] == c["top5"] else "--",
                    "seq-": str(c["seq_neg"]),
                    "flat$": (br(100 * c["flat_share"], 0) + "%") if c["flat_share"] == c["flat_share"] else "--",
                    "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                    "veredito": c["veredito"],
                    "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
                }
                linhas.append(linha_de_resultado(variante_nome, r["res"], capital, extras=extras))
            print(tabela(linhas, extras=EXTRAS))

            # dispersao: n, media, desvio de trade e de dia, por variante
            print("\n  dispersao (n, media R$, desvio R$) -- trades vencedores / perdedores / dia:")
            for variante_nome in VARIANTES:
                c = bloco[variante_nome]["c"]
                ng = int(round(c["win"] * c["n"])) if c["n"] and c["win"] == c["win"] else 0
                npd = c["n"] - ng
                print(f"    {variante_nome:<20} vencedor: n={ng:>4} media={br(c['ganho_medio']).rjust(10)} "
                      f"dp={br(c['ganho_dp']).rjust(9)}  |  perdedor: n={npd:>4} "
                      f"media=-{br(c['perda_media']).rjust(9)} dp={br(c['perda_dp']).rjust(9)}  |  "
                      f"dia: n={c['pregoes']:>3} media={br(c['pnl_dia_media']).rjust(9)} "
                      f"dp={br(c['pnl_dia_dp']).rjust(9)}")

    # ---------------- FASE 2: os DOIS NUMEROS que resolvem a confusao do "100%" ----------------
    print("\n\n" + "=" * 100)
    print("FASE 2: os dois numeros de CONSISTENCIA (config A, producao, R$3.000, HISTORICO COMPLETO)")
    print("=" * 100)
    c_full_a = resultados_tabela[(CAPITAL_DECIDE, "HISTORICO COMPLETO")]["A baseline (sino)"]["c"]
    print(f"  1) fracao de PREGOES individuais positivos:            "
          f"{br(100*c_full_a['frac_preg'],1)}%  (n={c_full_a['com_trade']} pregoes com operacao "
          f"de {c_full_a['pregoes']} no total, {c_full_a['sem_trade']} sem trade)")

    # datas de inicio, horizonte fixo 40, so' capital que decide, todas as 4 variantes
    inicios = list(range(0, len(dias) - HORIZONTE_INICIO + 1, PASSO_INICIO))
    tarefas_inicio = [(CAPITAL_DECIDE, nome, modo, i)
                       for nome, modo in VARIANTES.items() for i in inicios]
    print(f"\nFASE 2b: robustez por DATA DE INICIO -- {len(inicios)} inicios x {len(VARIANTES)} "
          f"variantes = {len(tarefas_inicio)} rodadas (horizonte fixo {HORIZONTE_INICIO} pregoes, "
          f"R$ {br(CAPITAL_DECIDE,0)})...", flush=True)
    por_variante_inicio: dict = {nome: [] for nome in VARIANTES}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_inicio, t): t for t in tarefas_inicio}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            por_variante_inicio[r["variante"]].append(r)
            done += 1
            if done % 60 == 0:
                print(f"  {done}/{len(tarefas_inicio)}", flush=True)

    print(f"\n  2) fracao de DATAS DE INICIO cuja curva acumulada de {HORIZONTE_INICIO} pregoes "
          f"termina POSITIVA, por variante (n={len(inicios)} inicios cada, R$ {br(CAPITAL_DECIDE,0)}):")
    hdr = ("variante".ljust(20) + "positivas".rjust(11) + "zeraram".rjust(9)
           + "calaram".rjust(9) + "liquido mediano".rjust(17) + "pior liquido".rjust(14)
           + "desvio".rjust(12))
    print("  " + hdr)
    print("  " + "-" * len(hdr))
    for nome in VARIANTES:
        rs = por_variante_inicio[nome]
        liq = pd.Series([r["liquido"] for r in rs])
        pos = sum(1 for r in rs if r["positivo"])
        zerou = sum(1 for r in rs if r["zerou"])
        calou = sum(1 for r in rs if r["calou"] and not r["zerou"])
        print("  " + nome.ljust(20)
              + (br(100 * pos / len(rs), 1) + "%").rjust(11)
              + str(zerou).rjust(9) + str(calou).rjust(9)
              + br(liq.median()).rjust(17) + br(liq.min()).rjust(14)
              + br(float(liq.std(ddof=1))).rjust(12))

    print("\n  CONFIRMACAO: se a linha 1 (preg+) e a linha 'A baseline' da tabela acima "
          "divergirem muito de 59%/100% (os numeros da memoria antiga, medidos sob o CORTE "
          "DE ACHATAMENTO ANTIGO), o motivo e' a mudanca de corte de 2026-09-14 -- nao um bug.")

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
