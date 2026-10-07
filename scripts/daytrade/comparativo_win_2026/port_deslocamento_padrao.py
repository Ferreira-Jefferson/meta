"""WinDeslocamentoMatinal PADRAO = EA mt5/WinDeslocamentoMatinal.mq5 v1.31 (v1.30 + NaoOperarGapATR = 1,0).

v1.31 (2026-10-06, frente Z8): nenhuma entrada no dia em que |abertura - fechamento anterior| >= 1,0 x ATR14 D1
(`filtro_gap.py`, mesma definicao do z7.py; 2026: 03/03, 08/04, 05/10). Aqui NAO basta tirar as operacoes do CSV: o
teto de risco (RiscoMaxPct = 10% do SALDO corrente) aperta o stop pelo saldo, e o saldo muda quando um dia some. Por
isso o port `port_deslocamento.py` roda de novo, SEM ser editado, com o dia bloqueado via monkeypatch: nos dias
bloqueados `atr_d1` devolve 0 e o port passa o dia em branco (sem ordem), exatamente no ponto da decisao das 10:30.
O zeramento de posicao de pregao anterior ('overnight') vem antes desse ponto e continua normal, como no EA (a regra
so' impede entrada nova). No EA o bloqueio fica depois do sinal, logo antes de enviar a limite: mesmo efeito, nenhuma
ordem no dia, e o diagnostico do port conta esses dias como 'sem_atr' (o contador `gap` separa os bloqueados).

Uso: python port_deslocamento_padrao.py   -> resultados/WinDeslocamentoMatinal.csv (2026-01-02 .. 2026-10-05)
"""
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados  # noqa: E402
import filtro_gap  # noqa: E402
import port_deslocamento as P  # noqa: E402

K_GAP = filtro_gap.K_PADRAO
_atr0 = P.atr_d1
BLOQ = {"dias": set(), "gap": 0}


def _atr_com_gap(d1, dia, n):
    if dia in BLOQ["dias"]:
        BLOQ["gap"] += 1
        return 0.0
    return _atr0(d1, dia, n)


def instala(dias_bloq=None):
    """Liga a regra no port (monkeypatch de `atr_d1`). dias_bloq None = dias do WIN$N (filtro_gap, k=1,0)."""
    BLOQ["dias"] = filtro_gap.bloqueados(K_GAP) if dias_bloq is None else set(dias_bloq)
    BLOQ["gap"] = 0
    P.atr_d1 = _atr_com_gap


def final():
    instala()
    dias = dados.dias()

    def gt(d):
        t, p, v, r = dados.ticks(d)
        return t, p
    trades, saldo, quebrou, diag = P.rodar(dias, dados.m1(), gt)
    out = dados.salvar(P.NOME, trades)
    df = pd.DataFrame(trades)
    print("dias bloqueados no periodo:", sorted(str(d) for d in BLOQ["dias"] if dias[0] <= d <= dias[-1]),
          "| dias em branco pelo gap:", BLOQ["gap"], flush=True)
    print("diag:", diag, "| quebrou:", quebrou, "| saldo final:", round(saldo, 2), flush=True)
    if len(df):
        df["mes"] = df.saida.str[:7]
        print(df.groupby("mes").rs.agg(trades="count", liquido="sum").round(2).to_string(), flush=True)
        print("total", len(df), "trades, R$", round(df.rs.sum(), 2), "c/ custo", round(df.rs.sum() - 2 * len(df), 2), flush=True)
    print(out, flush=True)


if __name__ == "__main__":
    final()
