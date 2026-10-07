"""Regra NaoOperarGapATR (Z8, regra G1 k=1,0 aprovada na Z7): nao abre posicao nova no dia em que
|abertura do pregao - fechamento do pregao anterior| >= k x ATR14 D1.

Mesma definicao de `combinacoes/z7_dias_extremos/z7.py` (as linhas abaixo sao copia dela; o z7.py e' script e nao
pode ser importado sem rodar o estudo inteiro):
  - diarias montadas das M1 com abertura <= 18:25 (o, h, l, c = 1a abertura, max, min, ultimo fechamento do dia);
  - ATR14 D1 = media SIMPLES do True Range dos 14 pregoes ANTERIORES (sem o dia corrente);
  - simbolo CONTINUO (WIN$N/WIN@/WIN$): o dia do vencimento do WIN (quarta mais proxima do dia 15 dos meses pares;
    se nao houver pregao nesse dia, o 1o pregao depois dele, ate' 3 dias) e' o dia em que a serie troca de contrato.
    Nesse dia (a) o gap NAO bloqueia, porque o salto e' da troca de contrato, e (b) o True Range vale so' a amplitude
    do dia (ignora o salto) -- para o ATR dos dias seguintes.
  - CONTRATO especifico (ex.: WINV26): nao ha salto de rolagem, entao nao ha exclusao e o True Range e' o completo
    (`continuo=False`). E' o que o EA faz quando o nome do simbolo nao tem '$' nem '@'.

Uso nos ports: `bloqueados()` -> set de datas (2022-2026, WIN$N); `filtra(trades)` remove as operacoes com ENTRADA
num dia bloqueado (so' vale para robos sem estado de saldo entre dias; o Deslocamento usa o teto pelo saldo e roda
de novo com o dia bloqueado).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[2]
DADOS = ROOT / "data" / "comparativo_win_2026"
K_PADRAO = 1.0           # input NaoOperarGapATR dos EAs (0 desliga)
HORA_FIM = "18:25"       # velas M1 com abertura <= 18:25 (o tick isolado das 18:30 do WIN$N nao entra)


def venc(ano, mes):
    """Vencimento do WIN: quarta-feira mais proxima do dia 15 (igual ao z7.py e ao EA)."""
    t15 = date(ano, mes, 15); mql = (t15.weekday() + 1) % 7
    dif = 3 - mql
    if dif > 3: dif -= 7
    if dif < -3: dif += 7
    return t15 + timedelta(days=dif)


ROLAGENS = {venc(a, m) for a in range(2021, 2028) for m in (2, 4, 6, 8, 10, 12)}


def m1_continuo() -> pd.DataFrame:
    """WIN$N 2022-2025 + 2026 (as mesmas duas bases do z7.py)."""
    m = pd.concat([pd.read_parquet(DADOS / "m1_WIN$N_2022_2025.parquet"), pd.read_parquet(DADOS / "m1_WIN$N.parquet")])
    return m[~m.index.duplicated(keep="first")].sort_index()


def diarias(m1: pd.DataFrame | None = None, continuo: bool = True) -> pd.DataFrame:
    """Tabela diaria com gap, ATR14 (14 pregoes anteriores), gap_atr e flag de rolagem."""
    m = m1_continuo() if m1 is None else m1
    m = m[m.index.time <= pd.Timestamp(HORA_FIM).time()].copy()
    m["d"] = m.index.date
    g = m.groupby("d")
    D = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
    dias = list(D.index)
    roll_dias = set()
    if continuo:
        for r in ROLAGENS:
            nxt = [d for d in dias if d >= r]
            if nxt and (nxt[0] - r).days < 4: roll_dias.add(nxt[0])
    pc = D.c.shift(1)
    D["gap"] = (D.o - pc).abs(); D["gap_s"] = D.o - pc
    D["roll"] = [d in roll_dias for d in D.index]
    amp = D.h - D.l
    tr = np.maximum.reduce([amp, (D.h - pc).abs(), (D.l - pc).abs()])
    tr = pd.Series(np.where(D.roll, amp, tr), index=D.index)
    D["atr"] = tr.shift(1).rolling(14).mean()
    D["gap_atr"] = D.gap / D.atr
    return D


def bloqueados(k: float = K_PADRAO, m1: pd.DataFrame | None = None, continuo: bool = True) -> set:
    if k <= 0:
        return set()
    D = diarias(m1, continuo)
    mask = ((D.gap_atr >= k) & ~D.roll).fillna(False)
    return set(D.index[mask.values])


_cache: dict = {}


def bloqueados_padrao(k: float = K_PADRAO) -> set:
    if k not in _cache:
        _cache[k] = bloqueados(k)
    return _cache[k]


def filtra(trades: list, dias_bloq: set | None = None) -> list:
    """Remove as operacoes (dicts no formato de dados.trade) cuja ENTRADA cai num dia bloqueado."""
    b = bloqueados_padrao() if dias_bloq is None else dias_bloq
    return [t for t in trades if date.fromisoformat(str(t["entrada"])[:10]) not in b]


if __name__ == "__main__":
    D = diarias()
    b = sorted(bloqueados())
    print(len(b), "dias bloqueados (WIN$N, k=1,0):", flush=True)
    for d in b:
        r = D.loc[d]
        print(f"  {d}  gap {r.gap_s:+.0f} pts = {r.gap_atr:.2f} ATR (ATR {r.atr:.1f})", flush=True)
