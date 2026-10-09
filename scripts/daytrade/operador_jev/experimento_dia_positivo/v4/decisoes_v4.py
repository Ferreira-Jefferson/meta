"""Decisoes v4 = decisoes v3 (decisoes.decisao_entrada / decisao_gestao) + as 4 regras deterministicas de regras_v4. Funcoes puras (sem rede)."""
from __future__ import annotations
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
for p in (str(EXP.parent), str(AQUI)):
    if p not in sys.path:
        sys.path.insert(0, p)
from decisoes import decisao_entrada, decisao_gestao  # noqa: E402
import regras_v4 as rg  # noqa: E402

CFG_V4 = dict(portao=True, reentrada=True, risco=True, guarda_gestao=True, limiar_er=rg.LIMIAR_ER)


def decisao_entrada_v4(rm, ctx, dia, k, limiar, trades, cfg=CFG_V4):
    """(dec, info). `trades` = operacoes fechadas hoje. Aplica, nesta ordem: portao -> reentrada/maximo -> risco. Cada bloqueio fica em info['bloq']."""
    dec, info = decisao_entrada(rm, ctx, dia, k, limiar, "argmax")
    er, desl = rg.er_dia(dia, k)
    info.update(er=er, desl=desl, caixa=rg.CAIXA_INI_DIA + sum(t["brl"] for t in trades), bloq=[])
    if dec["acao"] not in ("comprar_limite", "vender_limite"):
        return dec, info
    dirn = 1 if dec["acao"] == "comprar_limite" else -1
    info["portao_ok"], mot = rg.portao(er, desl, dirn, cfg["limiar_er"])
    bloq = []
    if cfg["portao"] and not info["portao_ok"]:
        bloq.append(mot)
    if cfg["reentrada"]:
        ok, mot = rg.reentrada(trades, k)
        if not ok:
            bloq.append(mot)
    n = dec["contratos"]
    if cfg["risco"] and not bloq:
        n2, mot, perdas = rg.risco(dec["preco"], dec["stop"], n, info["caixa"])
        info["perda_stop_brl"] = perdas[0]
        if n2 == 0:
            bloq.append(mot)
        elif n2 != n:
            info["mao_reduzida"] = mot
            dec = dict(dec, contratos=n2, raciocinio=dec["raciocinio"] + f" | {mot}")
            info["mao"] = n2
    if bloq:
        info["bloq"] = bloq
        info["acao_jev"] = dec["acao"]
        return dict(acao="ficar_fora", confianca=dec.get("confianca", 0), respostas=[], raciocinio="v4 bloqueou: " + " ; ".join(bloq)), info
    return dec, info


def decisao_gestao_v4(rgest, ctx, dia, k, pos, cfg=CFG_V4):
    """rgest = respostas da gestao ({'g_acao': {'c','p'}, ...}) ou None. Com guarda: zerar/stop_pivo so com a tese invalidada (calculo do motor)."""
    inval, info_t = rg.tese_invalidada(ctx, dia, k, pos)
    raw = ((rgest or {}).get("g_acao") or {}).get("c", "manter")
    esc = raw
    bloq = False
    if cfg["guarda_gestao"] and esc in ("zerar", "stop_pivo") and not inval:
        esc, bloq = "manter", True
        rg2 = dict(rgest, g_acao=dict(rgest["g_acao"], c="manter"))
    else:
        rg2 = rgest
    dec, info = decisao_gestao(rg2, ctx, dia, k, pos)
    info.update(esc_jev=raw, guarda_bloqueou=bloq, tese_invalidada=inval, tese=info_t)
    return dec, info
