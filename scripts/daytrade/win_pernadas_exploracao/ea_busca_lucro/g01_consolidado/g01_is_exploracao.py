# -*- coding: utf-8 -*-
"""Geracao 1 (`WinBuscaLucroG01`) -- EXPLORACAO NO IS (jan-jun/2026), as 3
variantes (R61 isolado, R65 isolado, combinado) com a tabela padrao do repo.

Capital: R$250,00 -- piso de PARTIDA REAL do WIN@ (margem crua R$100 x
buffer 2,0 x reserva 1,25), nunca um valor "com folga" (regra do dono,
CLAUDE.md "Capital inicial: sempre o minimo real do instrumento" -- rodar
bateria com mais capital so' para separar geometria de censura e' tempo de
maquina gasto quando o dono nao tem esse capital).

Fila: WIN@ sem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0`, `exit_queue_ahead_qty=0`), premissa otimista declarada.

Regra do protocolo (ORQUESTRACAO.md / mandato do dono, 2026-10-04): so' passa
para o OOS-1 (jul-ago/2026) quem terminar o IS com liquido > 0 E NAO
censurado (conferir trades e pregoes sem trade). Este script SO' MEDE o IS --
a decisao de rodar o OOS-1 e' tomada depois de ler esta tabela, nunca antes.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g01_consolidado/g01_is_exploracao.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g01_base as b  # noqa: E402

VARIANTES = [
    ("1 R61 isolado", dict(modo="r61")),
    ("2 R65 isolado", dict(modo="r65")),
    ("3 combinado (R61+R65)", dict(modo="combinado")),
]


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    df = b.carrega_df()
    dias = b.dias_da_janela(df, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 110)
    print("WinBuscaLucroG01 -- IS (jan-jun/2026), capital R$ %s (piso de partida real do WIN@)"
          % b.br(b.CAPITAL, 0))
    print("=" * 110)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE "
          "(queue_ahead_qty=0, exit_queue_ahead_qty=0).\n", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "seq-", "n_stop", "pts/op", "sem_tr")
    linhas = []
    for rot, kw in VARIANTES:
        res = b.roda(dias, **kw)
        trades = list(res.trades)
        c = b.consistencia(trades, dias)
        be_nom = (kw.get("modo") == "r61") and (1.0 / 3.0) / (1.0 + 1.0 / 3.0) or float("nan")
        extras = {
            "BEnom%": (b.br(100 * be_nom, 1) + "%") if be_nom == be_nom else "--",
            "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
            "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
            "veredito": c["veredito"],
            "seq-": str(c["seq_neg"]),
            "n_stop": str(c["n_stops"]),
            "pts/op": b.br(c["pontos_por_op"], 2),
            "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
        }
        linhas.append(linha_de_resultado(rot, res, b.CAPITAL, extras=extras))
        print(f"  {rot:<24} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
              f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
              f"ordens_recusadas_capital={res.ordens_recusadas_por_capital:>4}  "
              f"equity_min={b.br(float(res.equity_curve.min()) if len(res.equity_curve) else float('nan')):>9}",
              flush=True)

    print()
    print(tabela(linhas, extras=EXTRAS))

    print("\nGATE para OOS-1 (regra do protocolo): liquido > 0 E nao censurado.")
    for (rot, kw), linha in zip(VARIANTES, linhas):
        censurado = linha.trades == 0 or (linha.aviso and "ZERADO" in linha.aviso)
        passa = linha.liquido_brl > 0 and linha.trades > 0
        print(f"  {rot:<24} liquido={b.br(linha.liquido_brl):>10}  "
              f"trades={linha.trades:>4}  -> {'PASSA (roda OOS-1)' if passa else 'NAO PASSA (morta no IS)'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
