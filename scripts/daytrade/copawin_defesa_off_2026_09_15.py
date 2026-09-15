"""copa_win: desligar `defesa_ativa` -- o teste direto do achado do Q1.

Q1 (`copawin_cinco_restantes_2026_09_15.py`) mediu, na base de trajetoria
LIVRE, que dos 109 trades em que a `defesa` TERIA disparado, **101 foram
para o ALVO** (+R$217/trade) -- a populacao inteira vale +R$193,53/trade sem
a regra, contra os ~+R$97/trade que as saidas por sinal entregam em
producao. Ou seja: a defesa parece estar abortando vencedores.

Aquela leitura tem um confundidor declarado: a base LIVRE tem as DUAS regras
desligadas, entao alguns daqueles 101 alvos poderiam ter sido cortados pelo
`corte_persistencia` numa config que so' desliga a defesa. Este script tira
a duvida rodando a config de producao EXATA com um unico bit trocado.

Quatro bracos: producao; so' defesa desligada; so' corte desligado; as duas
desligadas. Assim o efeito de cada regra aparece isolado e o da interacao
tambem.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location(
    "_base_def", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL
BRACOS = [
    ("PRODUCAO (as duas ligadas)", True, True),
    ("so' DEFESA desligada", False, True),
    ("so' CORTE desligado", True, False),
    ("as DUAS desligadas", False, False),
]


def br(x, c=2):
    return f"{x:,.{c}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _unidade(args):
    nome, defesa, corte, janela_nome, dias = args
    with redirect_stdout(StringIO()):
        sys.path.insert(0, str(ROOT / "src"))
        from backtest.intraday.engine import run_intraday_backtest
        from backtest.intraday.profiles import config_for, profile_for
        from strategy.daytrade.lab.copa_win import CopaWin
        from strategy.daytrade.registry import _KWARGS_PADRAO

        kw = dict(_KWARGS_PADRAO["copa_win"])
        kw["symbol"] = _base.SYMBOL
        kw["defesa_ativa"] = defesa
        kw["corte_persistencia_ativo"] = corte
        strat = CopaWin(**kw)
        p = profile_for(_base.SYMBOL)
        cfg = config_for(p, trade_tick_value=0.20, trade_tick_size=1.0,
                         initial_capital=CAPITAL,
                         target_fills_as_maker=strat.target_fills_as_maker,
                         limit_fill_capped_by_volume=True,
                         queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
        cfg = dataclasses.replace(cfg, session_end_time=p.flatten_cut_time)
        df, _ = _base._df()
        alvo = set(dias)
        res = run_intraday_backtest(df[[d in alvo for d in df.index.date]], strat, cfg)
    t = list(res.trades)
    por = {}
    for x in t:
        por[x.exit_reason.value] = por.get(x.exit_reason.value, 0.0) + x.pnl_brl
    return dict(nome=nome, janela=janela_nome, n=len(t),
                liquido=sum(x.pnl_brl for x in t),
                stops=sum(1 for x in t if x.exit_reason.value == "stop"),
                alvos=sum(1 for x in t if x.exit_reason.value == "target"),
                dias_com=len({x.entry_ts.date() for x in t}), dias=len(dias), por=por)


def main():
    df, dias = _base._df()
    corte_oos = pd.Timestamp("2026-06-13").date()
    janelas = [("IS", [d for d in dias if d < corte_oos]),
               ("OOS", [d for d in dias if d >= corte_oos]),
               ("COMPLETO", dias)]
    print("=" * 108)
    print("copa_win -- DESLIGAR `defesa_ativa` / `corte_persistencia_ativo` (config de producao)")
    print("=" * 108)
    print(f"{len(dias)} pregoes | capital R$ {br(CAPITAL, 0)} | corte de achatamento de producao\n")
    tarefas = [(n, d, c, jn, jd) for n, d, c in BRACOS for jn, jd in janelas]
    saida = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for f in as_completed(futs):
            r = f.result()
            saida[(r["nome"], r["janela"])] = r
            print(f"  [{r['janela']:<9}] {r['nome']:<28} liquido={br(r['liquido']):>12} "
                  f"trades={r['n']:>4} stops={r['stops']:>3} alvos={r['alvos']:>4} "
                  f"sem_trade={r['dias'] - r['dias_com']:>3}d", flush=True)
    for jn, _ in janelas:
        print("\n" + "=" * 108)
        print(f"JANELA {jn}")
        print("=" * 108)
        hdr = f"{'braco':<30}{'liquido R$':>14}{'vs producao':>14}{'trades':>8}{'stops':>7}{'alvos':>7}{'sem trade':>11}"
        print(hdr); print("-" * len(hdr))
        base = saida[(BRACOS[0][0], jn)]["liquido"]
        for nome, _, _ in BRACOS:
            r = saida[(nome, jn)]
            print(f"{nome:<30}{br(r['liquido']):>14}{br(r['liquido'] - base):>14}"
                  f"{r['n']:>8}{r['stops']:>7}{r['alvos']:>7}"
                  f"{str(r['dias'] - r['dias_com']) + '/' + str(r['dias']):>11}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
