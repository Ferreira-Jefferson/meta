"""Port PADRAO do WinRetanguloEma34.mq5 v1.06: M15 AJUSTADO + filtro f3 (k = 0,5) + base SEM velas pos-pregao.

v1.06 (2026-10-06, frente Z6, depois da Z4/Z5): o EA so' ARMA a entrada se a amplitude do pregao ate' a decisao for
>= 0,5 x ATR14 D1 (input FiltroAmplitudeATR; 0 desliga), e ignora velas que abrem depois do fim da sessao (o tick
isolado das 18:30 do WIN$N, que o contrato real nao tem). Este port reaproveita, SEM editar:
  - `combinacoes/y_tempos/retangulo/y4b/port_ret_tf_v2.py` (tf=15, ajustes=True) -- o M15 ajustado da v1.05;
  - `combinacoes/z4_ret2024/port_z4.py` (`instala`): o filtro e' aplicado no instante em que o port ARMA a ordem
    (bloqueio nao muda estado; tenta de novo na vela seguinte) e `sem_pos=True` tira os ticks >= 18:30.
E' exatamente a rodada da Z5 `roda_z5.py 2026 0.5 sempos` (trades/k0.5_2026_sempos.csv). Definicoes (port_z4.Contexto):
  decisao = fim da vela M15 fechada; amplitude = max-min das M1 do dia com abertura <= decisao-1 min;
  ATR14 D1 = media simples do True Range dos 14 pregoes anteriores (D1 montado das M1).
Resultado (Z5, com custo R$2/op): 2026 +1.170; total 2022-2026 +2.818 (sem filtro +1.872), sem quebra. NAO VALIDADA.

`port_retangulo_ema34.py` NAO muda (M1 historico v1.04).

v1.07 (2026-10-06, frente Z8): regra NaoOperarGapATR = 1,0 -- nenhuma entrada no dia em que |abertura - fechamento
anterior| >= 1,0 x ATR14 D1 (`filtro_gap.py`, mesma definicao do z7.py). `roda` tira as operacoes com ENTRADA nesses
dias (2026: 03/03, 08/04, 05/10). Equivale ao EA nao armar no dia: o robo e' day trade, o retangulo e a pendente
reiniciam a cada pregao e o historico de velas nao depende das operacoes. O unico estado que depende delas e' o
`parou` por equity (LIMITE_EQUITY = 0); o __main__ confere que o saldo minimo segue > 0 sem as operacoes removidas.

Rodado como script, grava `resultados/WinRetanguloEma34.csv` (2026-01-02 -> 2026-10-05, formato de `dados.salvar`).
Antes de gravar, o CSV da v1.05 que estiver la' e' movido uma unica vez para `resultados_M15_v105_historico/`.

Uso: python port_retangulo_ema34_padrao.py [--sem-salvar]
"""
import argparse
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "combinacoes" / "y_tempos" / "retangulo" / "y4b"))
sys.path.insert(0, str(AQUI / "combinacoes" / "z4_ret2024"))

import dados as D  # noqa: E402
import port_ret_tf_v2 as P  # noqa: E402
import port_z4  # noqa: E402
import filtro_gap  # noqa: E402

NOME = P.NOME            # "WinRetanguloEma34"
TF_MIN = 15              # M15
AJUSTES = True           # RetTF (A, B, C da Y4b)
K_AMPLITUDE = 0.5        # f3: amplitude do pregao ate' a decisao >= K x ATR14 D1 (EA: FiltroAmplitudeATR)
SEM_POS = True           # tira os ticks do pos-pregao (>= 18:30), como o contrato real
HIST_V105 = AQUI / "resultados_M15_v105_historico"
_instalado = False


def filtro_f3(c):
    return c["faixa_dia_atrd"] >= K_AMPLITUDE


def roda(dias_lista=None, verbose=True, gap=True):
    """Roda o padrao v1.07 (M15, ajustes, f3 0,5, sem pos-pregao, NaoOperarGapATR 1,0). `dias_lista` None = pregoes de
    `dados.dias()`. gap=False reproduz a v1.06."""
    global _instalado
    if not _instalado:   # monkeypatch de port_z4 na classe Ea do port (uma vez so')
        port_z4.instala(P, P.dados, filtro_f3 if K_AMPLITUDE > 0 else None, SEM_POS)
        _instalado = True
    ea = P.roda(dias_lista=dias_lista, verbose=verbose, tf=TF_MIN, ajustes=AJUSTES)
    if gap:   # v1.07: tira as operacoes com ENTRADA em dia bloqueado (NaoOperarGapATR = 1,0; dias do WIN$N)
        n0 = len(ea.trades)
        ea.trades = filtro_gap.filtra(ea.trades)
        ea.n_gap = n0 - len(ea.trades)
    return ea


def guarda_v105():
    """Move resultados/WinRetanguloEma34.csv (v1.05) para resultados_M15_v105_historico/. So' uma vez."""
    src = AQUI / "resultados" / f"{NOME}.csv"
    dst = HIST_V105 / f"{NOME}.csv"
    if src.exists() and not dst.exists():
        HIST_V105.mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        print("v1.05 historico:", dst, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-salvar", action="store_true")
    a = ap.parse_args()
    ea = roda(verbose=False)
    if not a.sem_salvar:
        guarda_v105()
        print("->", D.salvar(NOME, ea.trades), flush=True)
    df, g = P.resumo(ea.trades)
    print(g.round(2).to_string(), flush=True)
    print("TOTAL", len(df), round(df.rs.sum(), 2), "c/ custo", round(df.rs.sum() - 2 * len(df), 2),
          "bloqueadas", P.Ea.n_bloq, "motivos", df.motivo.value_counts().to_dict(), "parou", ea.parou, flush=True)
    sal = D.CAPITAL + df.sort_values("saida").rs.cumsum()
    print("NaoOperarGapATR: removidas", getattr(ea, "n_gap", 0), "| saldo minimo sem elas", round(sal.min(), 2),
          "(> LIMITE_EQUITY", P.LIMITE_EQUITY, "->", "estado igual)" if sal.min() > P.LIMITE_EQUITY else "PAROU: refazer)", flush=True)
