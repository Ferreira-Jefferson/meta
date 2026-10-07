"""WinCincoMedias PADRAO = EA mt5/WinCincoMedias.mq5 v2.05 (v2.04 + NaoOperarGapATR): tempo grafico H2, Supertrend H4, zeragem antes do fim real.

Escolha do dono (2026-10-06, frente Z2 de combinacoes/TODO.md). Nao duplica logica: importa o port parametrizado da Y2
(combinacoes/y_tempos/cinco/port_cinco_tf.py) com tf=120 (H2 -> Supertrend H4 pela tabela TF_ST dele) e aplica a zeragem
da X0b (combinacoes/x_fixas/x0b/roda_x0b.py): ZERAR = min(18:24, fim real do pregao - 1 min), por dia, com o fim real =
abertura da ultima M1 do dia + 1 min. Em 2026 todo pregao vai ate' 18:25 ou mais, entao a zeragem fica 18:24 e o
resultado e' identico a y_tempos/cinco/trades/cinco_M120_2026.csv (so' o texto do motivo muda: "Supertrend H4 contra").

O port M30 historico (port_cinco_medias.py) NAO muda: outros estudos dependem dele. O CSV M30 que estava em
resultados/WinCincoMedias.csv foi movido para resultados_M30_historico/.

v2.05 (2026-10-06, frente Z8): regra NaoOperarGapATR = 1,0 -- nenhuma entrada no dia em que |abertura - fechamento
anterior| >= 1,0 x ATR14 D1 (`filtro_gap.py`, mesma definicao do z7.py). A rodada final tira as operacoes com ENTRADA
nesses dias (2026: 03/03, 08/04, 05/10): o robo e' day trade (0 operacoes atravessam a noite) e o replay nao guarda
estado que dependa das operacoes de um dia para o outro (nem saldo). `simular` continua sem a regra.

Uso:
  python port_cinco_medias_padrao.py            -> resultados/WinCincoMedias.csv (2026-01-02 .. 2026-10-05)
  python port_cinco_medias_padrao.py testador   -> numero esperado no Testador: WINV26, 13/08-30/09/2026, sem custo
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "combinacoes" / "y_tempos" / "cinco"))
import dados  # noqa: E402
import filtro_gap  # noqa: E402

TF = 120                      # H2 (o Supertrend vai para H4 por port_cinco_tf.TF_ST)
ZERAR_PADRAO = 18 * 60 + 24
NOME = "WinCincoMedias"


def _fim_por_dia(M: pd.DataFrame) -> dict:
    """Fim real do pregao em minutos do dia = abertura da ultima M1 + 1 (como a X0b)."""
    ult = M.index.to_series().groupby(M.index.date).max()
    return {d: t.hour * 60 + t.minute + 1 for d, t in ult.items()}


class _Shim:
    """`dados` visto pelo port: igual ao real, mas cada pregao ajusta port.ZERAR antes de entregar os ticks."""
    fim: dict = {}

    def __getattr__(self, k):
        return getattr(dados, k)

    def ticks(self, dia):
        port.ZERAR = min(ZERAR_PADRAO, self.fim.get(dia, ZERAR_PADRAO + 1) - 1)
        return dados.ticks(dia)


_shim = _Shim()
_shim.fim = _fim_por_dia(dados.m1())
sys.modules["dados"] = _shim
import port_cinco_tf as port  # noqa: E402  (importa o shim como `dados`)


def prepara(tf=TF, **kw):
    return port.prepara(tf=tf, **kw)


def simular(P, d_ini, d_fim, **kw):
    tr = port.simular(P, d_ini, d_fim, **kw)
    for t in tr:                                  # o port da Y2 escreve o rotulo do M30 original
        if t["motivo"] == "Supertrend H1 contra":
            t["motivo"] = "Supertrend H4 contra"
    return tr


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "final"
    if modo == "testador":
        for fonte, M in (("WINV26", port.m1_winv26()), ("WIN$N", None)):
            P = prepara(M=M)
            tr = simular(P, date(2026, 8, 13), date(2026, 9, 30), verbose=False)
            df = pd.DataFrame(tr, columns=dados.COLUNAS)
            print(f"{fonte}: {len(df)} operacoes, liquido sem custo R$ {df.rs.sum():.2f}", flush=True)
            out = AQUI / "resultados" / f"WinCincoMedias_esperado_testador_{fonte.replace('$', '')}.csv"
            df.to_csv(out, index=False)
            print(f"  -> {out}", flush=True)
        return
    P = prepara()
    tr = simular(P, date(2026, 1, 2), date(2026, 10, 5))
    n0 = len(tr)
    tr = filtro_gap.filtra(tr)                    # v2.05: NaoOperarGapATR = 1,0 (dias do WIN$N)
    print(f"NaoOperarGapATR: {n0 - len(tr)} operacoes removidas em dias bloqueados", flush=True)
    out = AQUI / "resultados" / f"{NOME}.csv"
    df = pd.DataFrame(tr, columns=dados.COLUNAS)
    df.to_csv(out, index=False)
    print(df.groupby(df.entrada.str[:7]).rs.agg(["count", "sum"]).to_string(), flush=True)
    print(f"TOTAL {len(df)} trades, R$ {df.rs.sum():.2f} sem custo -> {out}", flush=True)


if __name__ == "__main__":
    main()
