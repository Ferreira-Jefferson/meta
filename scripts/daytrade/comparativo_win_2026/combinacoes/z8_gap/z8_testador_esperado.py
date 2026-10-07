"""Z8: numero esperado no Testador (WINV26, ticks reais, R$1.000, 1 contrato, sem custo) com a regra NaoOperarGapATR.

Dados = o que o Testador carrega para o contrato WINV26: M1 do WINV26 (z_padrao/m1_WINV26.parquet + 05/10 em
z8_gap/m1_WINV26_ate_0510.parquet) e ticks reais do WINV26 (data/cache_win_ticks/WINV26 ate' 01/10; 02/10 e 05/10 em
z8_gap/ticks_WINV26), so' ticks com last > 0 e antes das 18:30 (shim da Z1, estendido).
Dias bloqueados = filtro_gap.bloqueados(k=1,0) sobre o M1 do WINV26 com continuo=False (contrato especifico: sem
exclusao de rolagem; e' o que o EA faz num simbolo sem '$'/'@').

Uso: python z8_testador_esperado.py <Win|Win_c1|WinCincoMedias|WinDeslocamentoMatinal|WinRetanguloEma34> <ini> <fim>
Imprime as operacoes SEM a regra e COM a regra, e grava esperado_testador/<robo>_z8_<ini>_<fim>_WINV26.csv (com a regra).
"""
import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]                      # comparativo_win_2026/
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(AQUI.parent / "z_padrao"))
import dados as D0  # noqa: E402
import filtro_gap  # noqa: E402

CACHE = ROOT / "data" / "cache_win_ticks" / "WINV26"
EXTRA = AQUI / "ticks_WINV26"
OUT = BASE / "esperado_testador"


def shim():
    m = pd.read_parquet(AQUI / "m1_WINV26_ate_0510.parquet")
    S = types.ModuleType("dados")
    for k in ("TICK", "RS_PONTO", "COLUNAS", "trade", "salvar", "ts", "ms", "CAPITAL", "ROOT", "DADOS", "INICIO", "FIM"):
        setattr(S, k, getattr(D0, k))
    S.m1 = lambda: m
    S.dias = lambda: sorted(set(m.index.date))

    def ticks(dia):
        f = CACHE / f"{dia}.pkl"
        x = pd.read_pickle(f if f.exists() else EXTRA / f"{dia}.pkl")
        x = x[(x["last"] > 0) & ((x.time_msc // 60000) % 1440 < 18 * 60 + 30)]
        return x.time_msc.to_numpy(np.int64), x["last"].to_numpy(float), x.volume.to_numpy(np.int64), True
    S.ticks = ticks
    return S


def roda(robo, ini, fim, S):
    dias = [d for d in S.dias() if ini <= d <= fim]
    bloq = {d for d in filtro_gap.bloqueados(1.0, m1=S.m1(), continuo=False) if ini <= d <= fim}
    if robo in ("Win", "Win_c1"):
        import port_win_padrao as PP
        p = PP.PARAMS_C1 if robo == "Win_c1" else PP.PARAMS
        sem = PP.P.rodar(robo, p, ini, fim, salvar=False, verbose=False)
        com = filtro_gap.filtra(sem, bloq)
    elif robo == "WinCincoMedias":
        import port_cinco_medias_padrao as PP
        P = PP.prepara()
        sem = PP.simular(P, ini, fim, verbose=False)
        com = filtro_gap.filtra(sem, bloq)
    elif robo == "WinRetanguloEma34":
        import port_retangulo_ema34_padrao as PP
        sem = PP.roda(dias_lista=dias, verbose=False, gap=False).trades
        com = filtro_gap.filtra(sem, bloq)
    elif robo == "WinDeslocamentoMatinal":
        import port_deslocamento_padrao as PD

        def gt(d):
            t, p, v, r = S.ticks(d)
            return t, p
        PD.instala(set())
        sem = PD.P.rodar(dias, S.m1(), gt, log=lambda *a, **k: None)[0]
        PD.instala(bloq)                       # roda de novo com o dia bloqueado (o teto usa o saldo)
        com = PD.P.rodar(dias, S.m1(), gt, log=lambda *a, **k: None)[0]
    return dias, bloq, pd.DataFrame(sem, columns=S.COLUNAS), pd.DataFrame(com, columns=S.COLUNAS)


if __name__ == "__main__":
    robo, ini, fim = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
    S = shim()
    sys.modules["dados"] = S
    dias, bloq, sem, com = roda(robo, ini, fim, S)
    G = filtro_gap.diarias(S.m1(), continuo=False)
    g = G.loc[[d for d in dias if d in G.index], ["gap_s", "atr", "gap_atr"]]
    print(f"== {robo} WINV26 {ini}..{fim}: {len(dias)} pregoes; maior gap {g.gap_atr.max():.2f} ATR em {g.gap_atr.idxmax()}; "
          f"bloqueados: {[str(d) for d in sorted(bloq)]}", flush=True)
    for d in sorted(bloq):
        print(f"   {d}: gap {G.loc[d, 'gap_s']:+.0f} pts = {G.loc[d, 'gap_atr']:.2f} ATR (ATR14 D1 {G.loc[d, 'atr']:.1f})", flush=True)
    cols = ["entrada", "lado", "saida", "preco_entrada", "preco_saida", "motivo", "rs"]
    for rot, df in (("SEM a regra", sem), ("COM a regra (EA novo)", com)):
        print(f"-- {rot}: {len(df)} ops, liquido sem custo R$ {df.rs.sum():.2f}", flush=True)
        if len(df):
            print(df[cols].to_string(index=False), flush=True)
    OUT.mkdir(exist_ok=True)
    f = OUT / f"{robo}_z8_{ini:%m%d}_{fim:%m%d}_esperado_testador_WINV26.csv"
    com.to_csv(f, index=False)
    print("->", f, flush=True)
