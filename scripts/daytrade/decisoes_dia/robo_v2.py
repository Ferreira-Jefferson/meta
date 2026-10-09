"""Robô v2 (ciclo 2 do CICLO.md). Pré-registrado pelo orquestrador; não ajustar olhando os dias novos.
v1 continua em robo.py (inalterado). Aqui:
  - monta_v2(): lista FAZER/VETO da v2 = v1 + ajustes aceitos dos agentes do ciclo 1;
  - roda_v2(dia, fz, nf, estrutural=False): estrutura v1 (padrão) ou variante descritiva v2-estrutural.
Ajustes: A1 (c1_2023_07_27; inclui a1b = F5 só se defendeu mínima), F2 alvo 1 ATR (c1_2023_12_18 #1),
veto #8 (vender no VWAP c/ média subindo), A2 (veto só no rompimento raso), N1 (não comprar spring raso),
A3/A4/A5 no FIM da lista de FAZER. NÃO entram: N5/N1/F3/F4 de c1_2025_01_20, A6, A5b, #6, neutras."""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import robo
from regras import c1_2023_07_27 as c1a, c1_2023_12_18 as c1b

F2_ORIG = "2025_06_04:F2 falha na maxima da 1a hora (venda)"


def monta_v2():
    fz, nf = robo.carrega_regras()
    assert any(n == F2_ORIG for n, _, _ in fz), "F2 original nao encontrada"
    fz, nf = c1a.monta(fz, nf, ["A1", "A2", "N1", "A3", "A4", "A5"])
    fz = [(n, c1b.f2_alvo_1atr, None) if n == F2_ORIG else (n, r, g) for n, r, g in fz]
    nf = nf + [("c1b:#8 vender_no_vwap_media_subindo", c1b.n_vender_no_vwap_com_media_subindo, None)]
    return fz, nf


def roda_v2(dia, fz, nf, estrutural=False):
    if not estrutural:
        return robo.roda_robo(dia, fz, nf)
    contra = []

    def decide(ctx):
        sins = []
        for n, r, g in fz:
            s = robo._chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins: return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v}, entrou=None, nota="")
        lados = {s["lado"] for _, s, _ in sins}
        livres = {l for l in lados if not vetos[l]}
        if len(lados) > 1 and len(livres) != 1:
            info["nota"] = "dois lados: nenhum ou ambos vetados"
            for n, s, g in sins:
                if vetos[s["lado"]]: contra.append(dict(t=ctx.t, regra=n, s=s, g=g, vetos=list(vetos[s["lado"]])))
            return None, info, None
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA] "
                contra.append(dict(t=ctx.t, regra=n, s=s, g=g, vetos=list(vetos[s["lado"]])))
                continue
            info["entrou"] = n
            return s, info, g
        return None, info, None
    trades, log = robo._roda(dia, decide)
    return trades, log, contra
