"""VETO POR REGIME (2026-09-15) -- FASE 2: e se o robo NAO operar?

## O pedido do dono

"Eu quero que meca de maneira honesta para saber os impactos da
lateralizacao."

## O QUE ESTE NUMERO E' E O QUE ELE NAO E' -- ler antes da tabela

O limiar usado aqui (|ER| 15min > 0,4872) foi lido no IS na FASE 1, e a
hipotese que ele testa nasceu OLHANDO o IS e o OOS_LIMPO ao mesmo tempo.
Portanto:

  * este resultado e' IN-SAMPLE nas DUAS janelas. Nao existe janela cega
    sobrando para esta hipotese. Nenhuma linha desta saida e' validacao.
  * o que ele mede de verdade e' TAMANHO DE EFEITO: se o veto nao pagar nem
    aqui, no dado que o sugeriu, ele esta morto sem apelacao. Se pagar, o
    numero e' o TETO otimista, nao a expectativa.

Isso nao e' ressalva de rodape: e' a unica leitura defensavel. O repo ja'
pagou por confundir as duas (item 6.15 e a escolha do Q_saida=489 contra o
600 que "encaixava melhor no dia ja' visto").

## A honestidade tem TRES exigencias, e as tres estao no desenho

1. NAO e' soma de subconjunto. Somar as operacoes nao-laterais da tabela da
   fase 1 daria outro numero, porque o `wdo_orb` carrega estado de dia
   (`_armou_hoje`, `_preencheu_hoje`, `_lado_primeiro`, `_fades_no_dia`): se
   o rompimento nao acontece, o FADE daquele pregao muda ou deixa de
   existir. Aqui o motor roda de novo, com o veto ligado, e o contrafactual
   casa por (data, hora de entrada) -- NUNCA por ordem no dia.

2. O CONFUNDIDOR ENTRA COMO CELULA, nao como nota de rodape. Na fase 1 o
   terco "direcional" tinha faixa de abertura mediana de 36 ticks contra
   27,5 dos outros dois. Como `stop_max_ticks=30`, faixa de 36 bate no teto
   e a geometria muda. Entao "direcional" pode ser so' um apelido de "faixa
   larga demais". A celula B veta pela FAIXA (> 30 ticks, o proprio teto do
   stop -- limiar estrutural, nao ajustado ao resultado). Se B entregar o
   mesmo que A, o achado e' de geometria e a lateralizacao nao explica nada.

3. AS DUAS LEITURAS DE "NAO OPERAR" sao medidas separado, porque sao regras
   diferentes e podem discordar:
     * ESPERA  -- nao manda a ordem agora e continua procurando (o robo
                  desarma o estado e pode romper de novo mais tarde). E' o
                  que um filtro de verdade faz.
     * PULA    -- o pregao inteiro e' descartado depois do primeiro
                  rompimento vetado. E' um filtro de DIA, outra coisa.

## As celulas

    BASE      producao de hoje (alvo 1,5x, teto 1 fade, corte 60 min)
    A         veta ROMPIMENTO se |ER|15min > 0,4872          (espera)
    B         veta ROMPIMENTO se faixa > 30 ticks            (espera)  [confundidor]
    A+B       os dois                                        (espera)
    A_PULA    igual a A, mas descarta o resto do pregao      (filtro de dia)

O fade NAO e' vetado em nenhuma celula: na fase 1 ele ficou positivo nos
tres tercos, nas duas janelas, sem ordenacao. Vetar o fade seria agir contra
o que o dado mostrou so' para honrar a hipotese original -- que ja' esta
refutada e registrada como tal.

## O |ER| dentro do robo, sem olhar o futuro

O robo roda em base de TICK; o ER precisa de fechamento de MINUTO (sobre
tick a razao desaba para ~0,002 e mede microestrutura -- ver
`wdof1_tendencia_confirmacao_2026_08_28.py`). Entao a subclasse mantem a
serie de fechamentos por minuto em streaming: cada barra atualiza o
fechamento do minuto CORRENTE. Na hora da decisao o ultimo ponto e' o preco
de agora -- que e' informacao presente, nao futura. Nenhum minuto e'
completado com dado posterior a barra que decide.

Uso: `python -u scripts/daytrade/wdo_orb_veto_lateralizacao_2026_09_15.py`
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategy.daytrade.base import EnterLimit  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)

SAIDA = RAIZ / "scratch" / "wdo_orb_lateralizacao_2026_09_15"
MAX_WORKERS = min(12, (os.cpu_count() or 4))

#: LIDO NO IS NA FASE 1 (terco superior de |ER| 15min). Nao e' calibracao
#: nova: e' o mesmo corte, transcrito, para nao haver segunda escolha.
CORTE_ER_15MIN = 0.4872
#: O teto do stop (`stop_max_ticks`). Limiar ESTRUTURAL -- acima dele a faixa
#: nao cabe mais na geometria. Escolhido pelo mecanismo, nao pelo resultado.
CORTE_FAIXA_TICKS = 30
LOOKBACK_MIN = 15
MIN_MINUTOS = 4


@dataclass
class WdoOrbVeto(WdoOrbInstrumentado):
    """Producao + veto de ENTRADA por regime. Nada mais muda."""

    veta_por_er: bool = False
    veta_por_faixa: bool = False
    #: True = descarta o resto do pregao no primeiro veto (filtro de DIA).
    #: False = so' nao manda a ordem agora, e continua procurando.
    pula_o_dia: bool = False

    _min_ts: list = field(default_factory=list, init=False, repr=False)
    _min_close: list = field(default_factory=list, init=False, repr=False)
    _min_ts_arr: object = field(default=None, init=False, repr=False)
    _dia_morto: bool = field(default=False, init=False, repr=False)
    _vetos: list = field(default_factory=list, init=False, repr=False)

    # -- a serie de minuto, em streaming -----------------------------------
    def _registra_minuto(self, ts, bar) -> None:
        m = pd.Timestamp(ts).floor("1min")
        if self._min_ts and self._min_ts[-1] == m:
            self._min_close[-1] = bar.close      # atualiza o minuto corrente
        else:
            self._min_ts.append(m)
            self._min_close.append(bar.close)
            self._min_ts_arr = None              # invalida o cache do busca

    def _er_15min(self, ts) -> float:
        """Razao de eficiencia com sinal sobre os fechamentos de minuto dos
        ultimos `LOOKBACK_MIN` minutos. `nan` quando a janela e' curta demais
        ou o preco nao andou -- indefinido, nunca chutado como zero."""
        if not self._min_ts:
            return float("nan")
        limite = pd.Timestamp(ts).floor("1min") - pd.Timedelta(minutes=LOOKBACK_MIN)
        if self._min_ts_arr is None:
            self._min_ts_arr = np.array(self._min_ts)
        i = int(np.searchsorted(self._min_ts_arr, limite, side="left"))
        janela = self._min_close[i:]
        if len(janela) < MIN_MINUTOS:
            return float("nan")
        arr = np.asarray(janela, dtype=float)
        caminho = float(np.abs(np.diff(arr)).sum())
        if caminho <= 0.0:
            return float("nan")
        return float((arr[-1] - arr[0]) / caminho)

    # -- a decisao ----------------------------------------------------------
    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._registra_minuto(ts, bar)
        if self._dia_morto:
            return []
        if not (self.veta_por_er or self.veta_por_faixa):
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
            if ordem is None or ordem["tipo"] != "rompimento":
                saida.append(a)
                continue

            er = self._er_15min(ts)
            faixa = ordem["faixa_ticks"]
            bate_er = self.veta_por_er and er == er and abs(er) > CORTE_ER_15MIN
            bate_fx = (self.veta_por_faixa and faixa is not None
                       and faixa > CORTE_FAIXA_TICKS)
            if not (bate_er or bate_fx):
                saida.append(a)
                continue

            # Um veto por EPISODIO, nao por barra. Com `pula_o_dia=False` o
            # robo desarma e volta a tentar na barra seguinte -- se o preco
            # segue fora da faixa, ele e' vetado centenas de vezes seguidas
            # pelo MESMO evento. O smoke test de 4 pregoes devolveu ~400
            # linhas de veto num dia so'. Contar barra a barra inflaria a
            # contagem e nao diria nada que "vetou este rompimento" ja' nao
            # diga.
            motivo = ("er" if bate_er and not bate_fx else
                      "faixa" if bate_fx and not bate_er else "ambos")
            if self._vetos and self._vetos[-1]["motivo"] == motivo:
                self._vetos[-1]["barras"] += 1
            else:
                self._vetos.append({
                    "ts": ts, "er_15min": er, "faixa_ticks": faixa,
                    "motivo": motivo, "barras": 1,
                })
            # a ordem nunca existiu: tira do log e desfaz o estado que o pai
            # marcou, senao o robo fica achando que armou e cala o pregao.
            self._log_ordens.pop()
            if self.pula_o_dia:
                self._dia_morto = True
            else:
                (self._armou_hoje, self._limite_posto, self._lado_primeiro,
                 self._fades_no_dia) = antes
        return saida


CELULAS = [
    ("BASE",   dict()),
    ("A",      dict(veta_por_er=True)),
    ("B",      dict(veta_por_faixa=True)),
    ("A+B",    dict(veta_por_er=True, veta_por_faixa=True)),
    ("A_PULA", dict(veta_por_er=True, pula_o_dia=True)),
]


def roda_pregao(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, kw in CELULAS:
        strat = WdoOrbVeto(**kw)
        res = run_intraday_backtest(bars, strat, monta_config(strat, CAPITAL_PARTIDA_BRL))
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
                "celula": nome, "data": dia, "op_do_dia": i + 1,
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2),
                "saida_efetiva": classifica_saida(
                    razao, pnl_ticks, ordem["alvo_ticks"] if ordem else float("nan")),
            })
        for v in strat._vetos:
            linhas.append({
                "celula": nome, "data": dia, "op_do_dia": 0,
                "entrada_utc": pd.Timestamp(v["ts"]).strftime("%H:%M:%S"),
                "tipo": "VETADA", "side": v["motivo"], "pnl_brl": 0.0,
                "saida_efetiva": "vetada", "barras_bloqueadas": v["barras"],
            })
    return linhas


def resumo(df: pd.DataFrame, pregoes: int) -> dict:
    ops = df[df.tipo != "VETADA"]
    por_pregao = ops.groupby("data").pnl_brl.sum()
    return {
        "n": len(ops),
        "vetadas": int((df.tipo == "VETADA").sum()),
        "liquido": round(ops.pnl_brl.sum(), 2),
        "rs_por_op": round(ops.pnl_brl.mean(), 2) if len(ops) else float("nan"),
        "win_pct": round(100.0 * (ops.pnl_brl > 0).mean(), 1) if len(ops) else float("nan"),
        "pregoes_pos_pct": round(100.0 * (por_pregao > 0).mean(), 1) if len(por_pregao) else float("nan"),
        "pregoes_com_op": len(por_pregao),
        "sem_trade": pregoes - len(por_pregao),
        "desvio_op": round(ops.pnl_brl.std(), 2) if len(ops) > 1 else float("nan"),
    }


def bootstrap(df: pd.DataFrame, celula: str, n: int = 5000) -> dict:
    """Emparelhado por PREGAO: a mesma lista de pregoes reamostrada vale para
    as duas celulas, entao a diferenca nao carrega o sorteio de quais dias
    entraram. Bloco = pregao, porque as operacoes do mesmo dia nao sao
    independentes (a 2a so' existe depois da 1a)."""
    base = df[df.celula == "BASE"]
    alvo = df[df.celula == celula]
    dias = sorted(set(base.data) | set(alvo.data))
    ops_b = {d: base[(base.data == d) & (base.tipo != "VETADA")].pnl_brl.to_numpy() for d in dias}
    ops_a = {d: alvo[(alvo.data == d) & (alvo.tipo != "VETADA")].pnl_brl.to_numpy() for d in dias}
    rng = np.random.default_rng(20260915)
    g_rs = g_pp = 0
    for _ in range(n):
        am = rng.choice(len(dias), size=len(dias), replace=True)
        b = [ops_b[dias[i]] for i in am]
        a = [ops_a[dias[i]] for i in am]
        fb, fa = np.concatenate(b) if b else np.array([]), np.concatenate(a) if a else np.array([])
        if len(fb) and len(fa) and fa.mean() > fb.mean():
            g_rs += 1
        pb = np.mean([x.sum() > 0 for x in b if len(x)]) if any(len(x) for x in b) else 0.0
        pa = np.mean([x.sum() > 0 for x in a if len(x)]) if any(len(x) for x in a) else 0.0
        if pa > pb:
            g_pp += 1
    return {"rs_maior_pct": round(100.0 * g_rs / n, 1),
            "pregoes_pos_maior_pct": round(100.0 * g_pp / n, 1)}


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"[veto] {len(todos)} pregoes x {len(CELULAS)} celulas "
          f"({[c for c, _ in CELULAS]}), {MAX_WORKERS} processos", flush=True)
    print(f"[veto] corte |ER|15min = {CORTE_ER_15MIN} (lido no IS, FASE 1) | "
          f"corte faixa = {CORTE_FAIXA_TICKS} ticks (teto do stop)\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "10_veto_trades.csv", index=False, encoding="utf-8")
    print(f"\n[veto] {len(df[df.tipo != 'VETADA'])} operacoes "
          f"+ {len(df[df.tipo == 'VETADA'])} vetos -> 10_veto_trades.csv\n", flush=True)

    tabs = []
    for rotulo, _, _, nota in JANELAS:
        sub = df[df.janela == rotulo]
        print("=" * 124)
        print(f"JANELA {rotulo}  ({len(dias_por_janela[rotulo])} pregoes) -- {nota}")
        print("=" * 124)
        lin = []
        for nome, _ in CELULAS:
            r = resumo(sub[sub.celula == nome], len(dias_por_janela[rotulo]))
            r = {"janela": rotulo, "celula": nome, **r}
            lin.append(r)
            tabs.append(r)
        print(pd.DataFrame(lin).drop(columns=["janela"]).to_string(index=False))
        print()

    pd.DataFrame(tabs).to_csv(SAIDA / "11_veto_resumo.csv", index=False, encoding="utf-8")

    # ---- o que o veto de fato tirou, operacao a operacao -------------------
    print("=" * 124)
    print("CONTRAFACTUAL -- o que a PRODUCAO fazia com as operacoes que o veto removeu")
    print("  (casado por (data, hora de entrada), NUNCA por ordem no dia: vetar")
    print("   uma entrada reescreve o resto do pregao)")
    print("=" * 124)
    base = df[(df.celula == "BASE") & (df.tipo != "VETADA")]
    for nome, _ in CELULAS[1:]:
        cel = df[(df.celula == nome) & (df.tipo != "VETADA")]
        print(f"\n--- celula {nome} ---")
        for rotulo, _, _, _ in JANELAS:
            b = base[base.janela == rotulo].set_index(["data", "entrada_utc"])
            c = cel[cel.janela == rotulo].set_index(["data", "entrada_utc"])
            sumiram = b.loc[b.index.difference(c.index)]
            surgiram = c.loc[c.index.difference(b.index)]
            print(f"  [{rotulo}] sumiram {len(sumiram)} op "
                  f"(R${sumiram.pnl_brl.sum():+,.2f}, das quais "
                  f"{int((sumiram.pnl_brl > 0).sum())} eram GANHADORAS valendo "
                  f"R${sumiram[sumiram.pnl_brl > 0].pnl_brl.sum():+,.2f})"
                  f" | surgiram {len(surgiram)} op (R${surgiram.pnl_brl.sum():+,.2f})")

    # ---- bootstrap ---------------------------------------------------------
    print("\n" + "=" * 124)
    print("BOOTSTRAP EMPARELHADO POR PREGAO contra BASE (5000 reamostragens, IS+OOS_LIMPO)")
    print("  LEMBRETE: in-sample nas duas. Isto mede TAMANHO DE EFEITO, nao validacao.")
    print("=" * 124)
    cego = df[df.janela.isin(["IS", "OOS_LIMPO"])]
    for nome, _ in CELULAS[1:]:
        r = bootstrap(cego, nome)
        print(f"\n  {nome} contra BASE:")
        print(f"    R$/op maior em          {r['rs_maior_pct']:>5.1f}%")
        print(f"    mais pregoes positivos: {r['pregoes_pos_maior_pct']:>5.1f}%")
    print(f"\n[veto] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
