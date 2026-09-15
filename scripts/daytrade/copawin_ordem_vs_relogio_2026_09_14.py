"""copa_win: a 1a operacao do dia e' ruim por ser a PRIMEIRA ou por ser CEDO?

Achado que motiva (2026-09-14, `copawin_onde_perde_2026_09_14.py`): a 1a
operacao do pregao concentra 62,1% dos STOPS (36 de 58), tem P(stop)=18,8%
contra 7,2% da 2a, e e' 33,9% dos trades para 3,0% do lucro (-R$0,31/trade
no OOS). O padrao SOBREVIVE ao OOS (63,2% dos stops no IS, 60,0% no OOS) --
diferente da quebra por hora do dia, que se embaralha entre as janelas.

O problema: "pular a 1a operacao" nao existe -- se pular, a 2a VIRA a 1a.
Duas causas incompativeis explicam o mesmo numero, e este script as separa:

  (ORDEM)   a 1a entrada e' a unica tomada sem nenhuma informacao sobre
            como o dia esta se comportando. Se for isto, pular os primeiros
            N sinais NAO resolve: a perda MIGRA para a nova primeira.
  (RELOGIO) a 1a quase sempre cai as 09h-10h, quando a calibracao de
            volatilidade do dia ainda e' fina. Se for isto, proibir entrada
            antes de um horario RESOLVE, e a nova primeira fica sa.

O DIAGNOSTICO NAO E' O LIQUIDO -- e' se o defeito MIGRA ou SOME. Por isso a
saida mostra, para cada variante, P(stop) e R$/trade da NOVA 1a operacao ao
lado do liquido. Um braco que melhora o liquido mas mantem a nova 1a
doente nao respondeu a pergunta, so' operou menos.

Reaproveita carregador/config de `copawin_encerrar_mais_cedo_2026_09_14.py`.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base_evr", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL
#: Capital NOCIONAL para o braco DIAGNOSTICO. Nao e' o capital do slot e nao
#: descreve nenhum futuro possivel (CLAUDE.md manda medir com o minimo real) --
#: existe SO' para tirar o portao de capital da equacao. Motivo, medido na 1a
#: rodada deste script: a R$3.000 as intervencoes mudam a trajetoria de caixa
#: o bastante para CENSURAR a janela (117/191 pregoes com operacao no braco
#: "pula 1o sinal", que ainda zerou a conta), e ai o liquido mede o portao, nao
#: a causa. As metricas do diagnostico (P(stop) e win% da NOVA 1a) sao livres
#: de escala; o liquido desta rodada NAO deve ser citado como resultado.
CAPITAL_NOCIONAL = 300_000.0
FOLGA = 5
BRT = "America/Sao_Paulo"

#: (rotulo, pular_n_sinais, nao_entrar_antes_hhmm_brt)
VARIANTES = [
    ("CONTROLE (producao)", 0, None),
    ("ORDEM: pula 1o sinal", 1, None),
    ("ORDEM: pula 2 sinais", 2, None),
    ("RELOGIO: apos 10h", 0, (10, 0)),
    ("RELOGIO: apos 11h", 0, (11, 0)),
]


def br(x, casas=2):
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _estrategia(pular_n: int, antes):
    sys.path.insert(0, str(ROOT / "src"))
    from datetime import time as _time

    from strategy.daytrade.base import Enter, EnterLimit
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    limite = None if antes is None else _time(*antes)

    class CopaWinOrdemRelogio(CopaWin):
        """Filtra APENAS acoes de entrada. `Exit`/`AdjustStop` de posicao ja
        aberta nunca sao bloqueadas, e o achatamento continua intacto -- o
        experimento muda QUANDO o robo abre, nunca como ele sai.

        Contagem de sinal: incrementa a cada BARRA em que o robo pediria uma
        entrada, nao a cada trade preenchido (o motor nao avisa a estrategia
        do fill). Com `entrada_ttl_barras=5` os dois numeros andam juntos,
        mas a diferenca existe e esta' declarada aqui em vez de escondida."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._sinais_hoje = 0

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            self._sinais_hoje = 0

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
            if not any(isinstance(a, (Enter, EnterLimit)) for a in acoes):
                return acoes
            bloquear = False
            if limite is not None and ts.tz_convert(BRT).time() < limite:
                bloquear = True
            if pular_n > 0:
                self._sinais_hoje += 1
                if self._sinais_hoje <= pular_n:
                    bloquear = True
            if bloquear:
                acoes = [a for a in acoes if not isinstance(a, (Enter, EnterLimit))]
            return acoes

    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = _base.SYMBOL
    return CopaWinOrdemRelogio(**kwargs)


def _roda(dias_janela, pular_n, antes, capital):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import _recua, config_for, profile_for

    df, _ = _base._df()
    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _estrategia(pular_n, antes)
    profile = profile_for(_base.SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                     initial_capital=capital,
                     target_fills_as_maker=strat.target_fills_as_maker,
                     limit_fill_capped_by_volume=True,
                     queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    cfg = dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, FOLGA))
    return run_intraday_backtest(bars, strat, cfg)


def _perfil_da_primeira(trades):
    """P(stop), R$/trade, win% e n da 1a operacao de cada pregao."""
    por_dia = defaultdict(list)
    for t in trades:
        por_dia[t.entry_ts.date()].append(t)
    primeiras = [sorted(ts, key=lambda x: x.entry_ts)[0] for ts in por_dia.values()]
    if not primeiras:
        return dict(n=0, p_stop=0.0, por_trade=0.0, win=0.0, hora="-")
    stops = sum(1 for t in primeiras if t.exit_reason.value == "stop")
    horas = sorted(t.entry_ts.tz_convert(BRT).hour for t in primeiras)
    return dict(
        n=len(primeiras),
        p_stop=100.0 * stops / len(primeiras),
        por_trade=sum(t.pnl_brl for t in primeiras) / len(primeiras),
        win=100.0 * sum(1 for t in primeiras if t.pnl_brl > 0) / len(primeiras),
        hora=f"{horas[len(horas) // 2]:02d}h",
    )


def _unidade(args):
    janela_nome, dias_janela, rot, pular_n, antes, capital = args
    with redirect_stdout(StringIO()):
        res = _roda(dias_janela, pular_n, antes, capital)
    trades = list(res.trades)
    return dict(janela=janela_nome, rot=rot, liquido=sum(t.pnl_brl for t in trades),
                trades=len(trades),
                stops=sum(1 for t in trades if t.exit_reason.value == "stop"),
                prim=_perfil_da_primeira(trades),
                dias_com=len({t.entry_ts.date() for t in trades}),
                dias=len(dias_janela))


def main():
    import pandas as pd

    _df_, dias = _base._df()
    corte = pd.Timestamp("2026-06-13").date()
    janelas = [("IS", [d for d in dias if d < corte]),
               ("OOS", [d for d in dias if d >= corte]),
               ("COMPLETO", dias)]
    print("=" * 112)
    print("copa_win -- a 1a operacao e' ruim por ser a PRIMEIRA (ordem) ou por ser CEDO (relogio)?")
    print("=" * 112)
    print(f"{len(dias)} pregoes | capital NOCIONAL R$ {br(CAPITAL_NOCIONAL, 0)} (so para tirar o portao de capital da equacao) | achatamento: producao (folga {FOLGA}min)")
    print("RESSALVA: WIN@ sem fila calibrada; OOS ja' gasto. O diagnostico e' a MIGRACAO, nao o liquido.\n",
          flush=True)

    tarefas = [(jn, jd, rot, pn, ant, CAPITAL_NOCIONAL)
               for jn, jd in janelas for rot, pn, ant in VARIANTES]
    saida: dict = defaultdict(dict)
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            saida[r["janela"]][r["rot"]] = r
            p = r["prim"]
            print(f"  [{r['janela']:<8}] {r['rot']:<22} liquido={br(r['liquido']):>11}  "
                  f"trades={r['trades']:>4}  1a: P(stop)={br(p['p_stop'], 1):>5}%  "
                  f"R$/trade={br(p['por_trade']):>8}  hora_med={p['hora']}", flush=True)

    for jn, _ in janelas:
        print("\n" + "=" * 112)
        print(f"JANELA {jn}")
        print("=" * 112)
        hdr = (f"{'variante':<24}{'liquido R$':>13}{'trades':>8}{'stops':>7}"
               f"{'dias c/ op':>12}{'| NOVA 1a: n':>14}{'P(stop)':>10}{'win%':>8}"
               f"{'R$/trade':>11}{'hora med':>10}")
        print(hdr)
        print("-" * len(hdr))
        for rot, _, _ in VARIANTES:
            r = saida[jn][rot]
            p = r["prim"]
            print(f"{rot:<24}{br(r['liquido']):>13}{r['trades']:>8}{r['stops']:>7}"
                  f"{str(r['dias_com']) + '/' + str(r['dias']):>12}{p['n']:>14}"
                  f"{br(p['p_stop'], 1) + '%':>10}{br(p['win'], 1) + '%':>8}"
                  f"{br(p['por_trade']):>11}{p['hora']:>10}")

    print("\n\nLEITURA: se a NOVA 1a mantiver P(stop) alto e R$/trade perto de zero, o defeito "
          "MIGROU -> a causa e' a ORDEM (inconsertavel por filtro).")
    print("Se a NOVA 1a ficar sa, a causa era o RELOGIO -> atrasar o inicio resolve.\n\nFIM.")


if __name__ == "__main__":
    main()
