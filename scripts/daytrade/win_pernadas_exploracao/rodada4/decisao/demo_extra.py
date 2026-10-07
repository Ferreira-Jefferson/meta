"""Tabelas de regras praticas: ruina vs capital (formula x Monte Carlo), encolhimento de p,
n para confirmar vantagem, e stop/alvo por horario (relogio real de 2026)."""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import motor as m

T0, S0 = 75.0, 150.0
g, l = m.ganho_perda(T0, S0)
nulo, be = m.nulo_p(T0, S0), m.breakeven_p(g, l)
print(f"geometria alvo {T0:.0f}/stop {S0:.0f}: ganho liq {g} pts (R${g*.2:.2f}), perda liq {l} pts (R${l*.2:.2f}), nulo {nulo:.3f}, breakeven c/ custo {be:.3f}, payoff {m.payoff(g,l):.2f}")

print("\n== Ruina (1 contrato fixo), formula de Lundberg x Monte Carlo 250 ops; ruina = caixa<R$100")
print("capital | p=nulo+0pp | +2,4pp(=BE) | +4pp | +8pp | +15pp")
for cap in (250, 300, 400, 500, 750, 1000, 2500):
    linha = []
    for dl in (0.0, 0.016, 0.04, 0.08, 0.15):
        p = nulo + dl
        res = np.array([g * .2, -l * .2]); pr = np.array([p, 1 - p])
        f = m.ruina_formula(res, pr, cap)
        mc = m.ruina_mc(res, pr, cap, 250, 3000)["p_ruina"]
        linha.append(f"{f*100:5.1f}%/{mc*100:5.1f}%")
    print(cap, "|", " | ".join(linha))
print("(formula infinito-horizonte / MC 250 ops)")

print("\n== Capital minimo p/ 1 contrato com ruina(250 ops)<=5%, por vantagem")
for dl in (0.04, 0.08, 0.15):
    p = nulo + dl; res = np.array([g * .2, -l * .2]); pr = np.array([p, 1 - p])
    for cap in range(250, 20001, 50):
        if m.ruina_mc(res, pr, cap, 250, 2000, seed=3)["p_ruina"] <= 0.05:
            print(f"  +{dl*100:.0f}pp: R${cap}"); break
    else:
        print(f"  +{dl*100:.0f}pp: > R$20000")

print("\n== Encolhimento: acerto observado -> p usado (base=nulo 66,7%, n0=100)")
for obs, n in [(0.82, 10), (0.82, 30), (0.82, 100), (0.82, 178), (0.82, 500), (0.707, 100), (0.707, 500)]:
    k = round(obs * n)
    pe = m.p_encolhido(k, n, nulo, 100)
    print(f"  obs {obs:.1%} em n={n}: p_encolhido {pe:.3f}  (edge liq {m.esperanca(pe, g, l):+.1f} pts) ; lim.inf(1dp) {m.p_limite_inferior(k, n, nulo, 100):.3f}; tamanho(R$1000)={m.tamanho(pe, g, l, 1000)}")

print("\n== n necessario para o acerto observado excluir a base (1 lado 5%) e para provar vantagem LIQUIDA de custo")
for dl in (0.04, 0.08, 0.15):
    print(f"  vantagem +{dl*100:.0f}pp sobre o nulo: n={m.n_para_confirmar(nulo, dl)} (vs nulo); vs breakeven c/ custo ({(nulo+dl-be)*100:.1f}pp): n={m.n_para_confirmar(be, nulo + dl - be) if nulo+dl>be else 'inf'}")

print("\n== Combinacao de sinais fracos (cada um sozinho 70% vs base 66,7%)")
for k in (1, 2, 3):
    for rho in (0.0, 0.5, 0.8):
        print(f"  {k} sinais, rho {rho}: p={m.combina_sinais(nulo,[0.70]*k,rho):.3f}", end=";")
    print()

idx = {(kk.split('|')[0] == '1', int(kk.split('|')[1])): v for kk, v in json.load(open(Path(__file__).parent / 'indice_vol.json')).items()}
print("\n== Relogio -> stop/alvo (base 150/75) e peso do custo (7 pts) no alvo; regime DST-EUA (mar-out) e inverno")
print("bloco | idx DST | stop/alvo | custo%alvo | idx inv | stop/alvo | perda R$ (1ctt, DST)")
for b in range(540, 1080, 30):
    iv_d, iv_i = idx.get((True, b)), idx.get((False, b))
    if iv_d is None: continue
    s, a = m.stop_alvo_por_vol(iv_d, S0); s2, a2 = m.stop_alvo_por_vol(iv_i, S0)
    print(f"{b//60:02d}:{b%60:02d} | {iv_d:.2f} | {s:.0f}/{a:.0f} | {(m.CUSTO_PTS+ (1-m.nulo_p(a,s))*m.DESLIZE_STOP_PTS)/a*100:.1f}% | {iv_i:.2f} | {s2:.0f}/{a2:.0f} | {(s+7)*.2:.1f}")
