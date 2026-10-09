"""Motor e candidatas D1..D16 do ciclo 4 (ver ciclo4/PREREGISTRO.md). Base = v3 (cfg3.monta(["C8","C7","C6","C4"])).
Nada existente e editado: as funcoes dos agentes sao importadas; so o MOTOR e estendido aqui:
  - `empate` (FAZER nos dois lados): None = nao entra (v3) | 'desloc' (D3) | 'vwap_maioria' (D4)
  - cadeia `post` pára se uma transformacao cancela a entrada (s=None)  [no v3 `post` e vazio: sem efeito]
Sem nenhuma candidata o resultado e IDENTICO ao v3 (verificado em ciclo4/p_confere.py)."""
import sys, json
from pathlib import Path
import numpy as np

C4 = Path(__file__).resolve().parent
RAIZ = C4.parent
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import base, robo, robo_v3, cfg3, av, an
from regras import (c3_grupo_2024_04_26 as g0426, c3_2024_04_26 as a0426, c3_grupo_2022_12_12 as g1212, c3_2022_12_12 as a1212,
                    c3_grupo_2022_08_18 as g0818, c3_2022_09_21 as a0921, c3_grupo_2024_09_05 as g0905, c3_2024_09_05 as a0905,
                    c3_2024_10_25 as a1025, c3_grupo_2022_04_13 as g0413, c3_2022_04_13 as a0413, c3_2022_05_17 as a0517,
                    c3_2025_06_20 as a0620)

V3 = list(robo_v3.IDS)


class Cfg4(cfg3.Cfg):
    def __init__(self, c):
        super().__init__(c.fz, c.nf, c.prio, c.post)
        self.empate = None


# ------------------------------------------------------------------ motor
def _emp_desloc(ctx, sins):
    h = ctx.hoje; d = float(h.close.iloc[-1] - h.open.iloc[0])
    if abs(d) >= ctx.atr15: return "compra" if d > 0 else "venda"
    return None


EMPATE = {"desloc": _emp_desloc, "vwap_maioria": g0905.desempate_vwap_e_maioria}


def roda(dia, cfg):
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post
    emp = EMPATE.get(cfg.empate) if cfg.empate else None

    def decide(ctx):
        for n, r, g in prio:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and not robo._agressiva(s, ctx):
                return s, dict(fazer=[(n, s["lado"])], vetos={}, entrou=n, nota="prioritaria"), g
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
        if len({s["lado"] for _, s, _ in sins}) > 1:
            lado = emp(ctx, sins) if emp else None
            if lado is None:
                info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
            sins = [x for x in sins if x[1]["lado"] == lado]
            info["nota"] = f"empate -> {lado} "
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA por {len(vetos[s['lado']])}] "
                return None, info, None
            info["entrou"] = n
            for f in post:
                s, g = f(n, s, g, ctx)
                if s is None: break
            return s, info, g
        return None, info, None

    return robo._roda(dia, decide)


def resultado_dia(dia, cfg):
    tr, log = roda(dia, cfg)
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                trades=[dict(fonte=x.fonte, lado=x.lado, contratos=x.contratos, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()),
                             sai=str(x.t_sai.time()), preco=x.preco, preco_sai=x.preco_sai, stop=x.stop_ini, alvo=x.alvo,
                             motivo=x.motivo, pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in ok])


# ------------------------------------------------------------------ candidatas
def _ap_motor(modo):
    def ap(cfg): cfg.empate = modo
    return ap


def _de_ajustes(chave):
    """aplica uma entrada de AJUSTES (add_fazer/add_prio/add_veto) de c3_2024_04_26 / c3_grupo_2024_04_26."""
    def ap(cfg):
        aj = {**g0426.AJUSTES, **a0426.AJUSTES}[chave]
        cfg.fz = cfg.fz + list(aj.get("add_fazer", [])); cfg.nf = cfg.nf + list(aj.get("add_veto", []))
        cfg.prio = cfg.prio + list(aj.get("add_prio", []))
    return ap


def _ap_g7a(cfg): g1212.AP["G7a"](cfg)


def _ap_post(f):
    def ap(cfg): cfg.post = cfg.post + [f]
    return ap


# id -> (descricao, ap, grupo_exclusivo, tardia). `tardia` = aplicada depois das demais (embrulha TODA a lista de FAZER).
CAND = {
    "D1":  ("F1 prioritaria: retomada da abertura a favor do gap", _de_ajustes("A_F1"), None, False),
    "D2":  ("G4 flip apos stop da gap_fade", _de_ajustes("G4"), None, False),
    "D3":  ("conflito de lados -> lado do deslocamento (E1)", _ap_motor("desloc"), "conflito", False),
    "D4":  ("conflito de lados -> so se VWAP e maioria concordam (G3d)", _ap_motor("vwap_maioria"), "conflito", False),
    "D5":  ("H4: A2 condicional estreito (ef<0,12, faixa 2h<=2 ATR15)", g0818._nf(g0818.n_vende_faixa_estreita, "c3:H4"), None, False),
    "D6":  ("N5: nao vender minima nova com volume >= 2,5x", g0818._nf(a0921.n5_vender_minima_nova_com_volume_extremo, "c3b:N5"), None, False),
    "D7":  ("S2: nao repetir o lado apos 2 stops nele", g1212.AP["S2"], None, False),
    "D8":  ("N2: nao comprar com gap de alta ja devolvido", a1212.AP["D1_N2"], None, False),
    "D9":  ("N1: nao comprar apos 1a vela de queda forte", a1212.AP["D1_N1"], None, False),
    "D10": ("G7a: a favor de vela de expansao, sem alvo, trailing", _ap_g7a, None, False),
    "D11": ("BN3: apos vitoria matinal em rotacao nao opera mais", g0905.REG["BN3"][2], None, True),
    "D12": ("AN1: descarta FAZER com alvo < 0,5x stop", g0905.REG["AN1"][2], None, True),
    "D13": ("N1: nao vender terco inferior da faixa em rotacao", g0413.CAND["G3n_venda_ef0.1_f0.3"], None, False),
    "D14": ("N1: nao comprar recuo em rotacao comprimida", g0413.CAND["G4v_cont_ef0.08_amp0.35"], None, False),
    "D15": ("F1: fade cedo do gap com rejeicao", a0517.CAND["b_F1_gap_cedo"], None, False),
    "D16": ("G1: alvo x2 se a favor da perna (0,3/0,3/2,0)", _ap_post(a0620._g1(0.3, 0.3, 2.0)), None, False),
}
ORDEM = list(CAND.keys())


def monta(ids):
    cfg = Cfg4(cfg3.monta(V3))
    ids = [i for i in ORDEM if i in ids]
    for i in ids:
        if not CAND[i][3]: CAND[i][1](cfg)
    for i in ids:
        if CAND[i][3]: CAND[i][1](cfg)
    return cfg


def chave(ids): return tuple(i for i in ORDEM if i in ids)


# ------------------------------------------------------------------ dias
def dias70():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    for c in ("ciclo1", "ciclo2", "ciclo3"):
        out += [(x["dia"], "c" + c[-1]) for x in du[c]["dias"]]
    assert len(out) == 70
    return out
