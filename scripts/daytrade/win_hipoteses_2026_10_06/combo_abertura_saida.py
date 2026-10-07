"""Combina as duas candidatas da rodada de 2026-10-06 sobre a MELHOR ATUAL:
filtro de lado pela ABERTURA do mes (hip. A) + saida 'deixa correr' no lado a favor (hip. C).
Mes a mes contra o baseline. Pedido do dono, 2026-10-06."""
import importlib.util as u, inspect, textwrap
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
def load(n, p):
    s = u.spec_from_file_location(n, p); m = u.module_from_spec(s); s.loader.exec_module(m); return m
A = load("hipa", AQUI / "hip_a_ancora_mensal.py")
C = load("hipc", AQUI / "hip_c_saida_por_regime.py")
kit = C.kit

# copia do simula de C com bloqueio opcional do lado contra o regime (na barra do sinal)
src = textwrap.dedent(inspect.getsource(C.simula))
src = src.replace('periodos=(9, 21, 34, 100, 200)):', 'periodos=(9, 21, 34, 100, 200), bloq=False):')
alvo = "        if not pos and not pend and est[t] != 0 and tempo[t] < FIM:\n"
assert alvo in src
src = src.replace(alvo, "        if not pos and not pend and est[t] != 0 and tempo[t] < FIM and (not bloq or reg[t] in (est[t], 0, 2)):\n")
ns = dict(C.__dict__); exec(src, ns); simula = ns["simula"]

ABERT_MESANT = dict(nome="x", anc="abertura", regra="pos", k=0, D=5, prev=True)
ABERT_D0 = dict(nome="x", anc="abertura", regra="pos", k=0, D=0)


def rodar(m5, regime, favor, bloq):
    out = []
    for nome, seg, ini_op, ult in kit.segmentos(m5):
        if regime == "todos":
            reg_seg = np.full(len(seg), 2.0)
        elif regime == "vwap":
            reg_seg = None
        else:
            reg_seg = A.regime(seg, regime).astype(float)
        for mes in pd.period_range(ini_op, ult, freq="M"):
            a = max(ini_op, mes.start_time); z = min(mes.end_time, ult + pd.Timedelta(days=1))
            jan = seg[a:z]
            if not len(jan): continue
            reg = reg_seg
            if reg is None:
                anc = max(mes.start_time, seg.index[0])
                r = C.vwap_regime(seg[:z], anc); reg = np.concatenate([r, np.zeros(len(seg) - len(r))])
            tr, eq = simula(seg, a, z, reg, C.ORIG_C, favor, bloq=bloq)
            out.append(dict(janela=f"{mes} {a:%d}-{jan.index[-1]:%d}", trades=pd.DataFrame(tr, columns=kit.COLS),
                            eq=eq, mercado_pts=float(jan.c.iloc[-1] - jan.o.iloc[0])))
    return out


VARS = [
    ("ATUAL", "todos", "orig", False),
    ("A abertura+mes ant. (bloqueia)", ABERT_MESANT, "orig", True),
    ("A abertura D0 (bloqueia)", ABERT_D0, "orig", True),
    ("C VWAP, a favor sai c21", "vwap", "c21", False),
    ("C abertura+mes ant., a favor c21", ABERT_MESANT, "c21", False),
    ("COMBO abertura+mes ant. bloq + c21", ABERT_MESANT, "c21", True),
    ("COMBO abertura D0 bloq + c21", ABERT_D0, "c21", True),
    ("COMBO abertura+mes ant. bloq + 9x21", ABERT_MESANT, "9x21", True),
    ("controle: c21 em tudo", "todos", "c21", False),
]


def main():
    m5 = kit.carregar_m5()
    R, M = {}, {}
    for nome, reg, fav, bl in VARS:
        res = rodar(m5, reg, fav, bl)
        R[nome] = kit.resumo(res)
        M[nome] = {r["janela"]: round(float(r["eq"].iloc[-1] - kit.b.CAP0), 2) for r in res}
        print(nome, R[nome], flush=True)
    s = pd.DataFrame(R).T
    base = pd.Series(M["ATUAL"])
    mm = pd.DataFrame(M)
    s["meses melhores"] = [f"{(mm[c] > base + 0.01).sum()}/{len(base)}" for c in s.index]
    sem_set = [k for k in base.index if not k.startswith("2026-09")]
    s["melhores s/ set"] = [f"{(mm.loc[sem_set, c] > base[sem_set] + 0.01).sum()}/{len(sem_set)}" for c in s.index]
    s["soma s/ set"] = [round(mm.loc[sem_set, c].sum(), 2) for c in s.index]
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print("\n=== RESUMO ===\n" + s.to_string(), flush=True)
    print("\n=== MES A MES (liquido R$, cada janela comeca com R$1.000) ===\n" + mm.to_string(), flush=True)
    s.to_csv(AQUI / "combo_abertura_saida_resumo.csv", encoding="utf-8-sig")
    mm.to_csv(AQUI / "combo_abertura_saida_meses.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
