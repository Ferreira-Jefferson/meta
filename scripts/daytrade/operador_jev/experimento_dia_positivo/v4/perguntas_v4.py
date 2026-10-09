"""Perguntas e blocos de estado da v4 (ver ../perguntas_v4.md). Mercado (8) e finais (acao/stop/alvo/mao) = v3, sem mudar uma palavra.
Novidades: (a) bloco de estado CONTEXTO DO DIA E DE RISCO (etapa 2) e bloco TESE DA POSICAO (gestao), calculados pelo motor so com velas fechadas;
(b) `v4_direcao_comprovada` (noul, etapa 2): o Jev responde o portao, mas a TRAVA OFICIAL e deterministica (regras_v4.portao);
(c) gestao reescrita: `v4_g_acao` (manter por padrao) + `v4_motivo_de_sair` (R2G5-03, so registro)."""
from __future__ import annotations
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
for p in (str(EXP / "v3"), str(EXP), str(EXP.parent), str(AQUI)):
    if p not in sys.path:
        sys.path.insert(0, p)
import perguntas_v2 as pv  # noqa: E402
import perguntas_v3 as p3  # noqa: E402
import regras_v4 as rg  # noqa: E402

IDS_V3 = p3.IDS_V3
QUESTOES_MERCADO_V4 = p3.QUESTOES_MERCADO_V3

_Q_DIR = ("O dia já comprovou direção a favor da operação que você consideraria agora? Responda sim somente se (1) a eficiência direcional do dia (linha DERIVADOS) é "
          "pelo menos 0,20 E (2) o último fechamento está do lado da abertura da operação: compra só com o fechamento ACIMA da abertura do dia, venda só com o fechamento ABAIXO. "
          "Em dúvida, ou se o dia anda e devolve, responda não.")
QUESTOES_FINAIS_A4 = {**p3.QUESTOES_FINAIS_A3, "v4_direcao_comprovada": {"type": "noul", "instructions": _Q_DIR + pv.SUF}}

_Q_G = ("Há uma posição aberta. Leia o bloco TESE DA POSIÇÃO. A regra é 'manter' por padrão: oscilar entre o stop e o alvo, eficiência baixa do dia, mudança de opinião sobre o tipo de dia "
        "ou volume baixo NÃO são fatos novos e NÃO justificam sair. A tese só é invalidada se o preço FECHOU além do último swing contra a posição (compra: abaixo do último fundo de swing; "
        "venda: acima do último topo), como o bloco informa. 'manter': a tese não foi invalidada (ou há dúvida). 'stop_pivo': a tese foi invalidada e a posição ainda tem lucro aberto: "
        "mover o stop para o último pivô a favor. 'zerar': a tese foi invalidada e não há lucro a proteger. Na vela imediatamente após a entrada, 'zerar' só vale se a tese já foi invalidada.")
_Q_MOT = ("Desde a entrada, o que mudou no mercado? 'sem_fato_novo': nada de objetivo, o preço oscilou entre o stop e o alvo (troca de opinião sobre o tipo de dia não conta). "
          "'tese_invalidada': um fechamento M15 passou do último swing contra a posição. 'fim_do_pregao': o fim do pregão está a menos de 3 velas.")
QUESTOES_GESTAO_V4 = {
    "v4_g_acao": {"type": "choice", "instructions": _Q_G + pv.SUF,
                  "criteria": {"manter": "manter posição e stop como estão", "stop_pivo": "mover o stop para o último pivô a favor (só com tese invalidada e lucro aberto)",
                               "zerar": "zerar a posição (só com tese invalidada)"}},
    "v4_motivo_de_sair": {"type": "choice", "instructions": _Q_MOT + pv.SUF,
                          "criteria": {"sem_fato_novo": "nada objetivo mudou", "tese_invalidada": "fechamento além do último swing contra a posição", "fim_do_pregao": "fim do pregão próximo"}},
}


def texto_respostas(resp):
    return p3.texto_respostas(resp)


def _brl(x):
    return f"R$ {x:,.0f}".replace(",", ".")


def bloco_dia(ctx, dia, k, trades, caixa_ini=rg.CAIXA_INI_DIA):
    """Bloco CONTEXTO DO DIA E DE RISCO (etapa 2, sem posicao). Fatos calculados pelo motor com velas <= k. Nao decide nada: so informa."""
    saldo = sum(t["brl"] for t in trades)
    caixa = caixa_ini + saldo
    er, desl = rg.er_dia(dia, k)
    lim = caixa * rg.RISCO_MAX_PCT / 100
    L = ["CONTEXTO DO DIA E DE RISCO (calculado pelo motor com as velas fechadas):",
         f"  Caixa: {_brl(caixa)} (R$ 2.000 no início do dia {saldo:+.0f} de resultado do dia) | limite de risco por operação: {rg.RISCO_MAX_PCT:.0f}% do caixa = {_brl(lim)} de perda no stop "
         f"(acima disso a mão cai para 1 contrato; com 1 contrato ainda acima, a operação não é feita)",
         f"  Operações fechadas hoje: {len(trades)} (máximo {rg.MAX_OPS_DIA} por dia) | saldo do dia {_brl(saldo)}"]
    if trades:
        u = trades[-1]
        extra = (f" | após operação perdedora só se reentra com a direção comprovada e pelo menos {rg.MIN_VELAS_REENTRADA} velas de espera") if u["brl"] < 0 else ""
        L.append(f"  Última saída: {u['motivo'].split(' (gap')[0]} há {k - u['k_sai']} vela(s) M15, resultado {u['brl']:+.0f} R${extra}")
    else:
        L.append("  Última saída: nenhuma (esta seria a primeira operação do dia)")
    lado = "ACIMA da abertura (só compra é a favor)" if desl > 0 else ("ABAIXO da abertura (só venda é a favor)" if desl < 0 else "na abertura (nenhum lado é a favor)")
    L.append(f"  Direção do dia: eficiência direcional {er:.2f} (a regra do motor só aceita entrada com eficiência >= {rg.LIMIAR_ER:.2f}) | o último fechamento está {lado}, {desl:+.0f} pts")
    for nome, dirn in (("comprar", 1), ("vender", -1)):
        preco, ops = rg.stop_opcoes(ctx, dia, k, dirn)
        partes = []
        for o in ("0.5atr", "1atr", "1.5atr", "pivo"):
            s = ops.get(o)
            if s is None:
                partes.append(f"{o}: indisponível")
                continue
            p = rg.perda_stop_brl(preco, s, 1)
            partes.append(f"{o}: {abs(preco - s):.0f} pts = {_brl(p)} ({100 * p / caixa:.1f}% do caixa)")
        L.append(f"  Perda no stop com 1 contrato ({nome}, entrada {preco:.0f}): " + " | ".join(partes) + "  (2 contratos = o dobro)")
    return "\n".join(L)


def bloco_tese(ctx, dia, k, pos):
    """Bloco TESE DA POSICAO (gestao). Fatos do motor: ultimo swing contra a posicao e se algum fechamento passou dele."""
    inval, info = rg.tese_invalidada(ctx, dia, k, pos)
    nome = "fundo" if pos["dir"] > 0 else "topo"
    sw = info["swing_agora"]
    sw0 = info["swing_na_entrada"]
    sw_txt = "nenhum" if sw is None else "%.0f (último fechamento %+.0f pts dele)" % (sw, info["fecha_atual"] - sw)
    sw0_txt = "nenhum" if sw0 is None else "%.0f" % sw0
    L = ["TESE DA POSIÇÃO (calculado pelo motor com as velas fechadas):",
         f"  Último {nome} de swing M15 de hoje (confirmado): {sw_txt}",
         f"  {nome.capitalize()} de swing que valia na entrada: {sw0_txt}",
         f"  Algum fechamento M15 desde a entrada passou além desse nível: {'sim' if info['quebra_desde_entrada'] else 'não'} | "
         f"o fechamento atual está além do último {nome}: {'sim' if info['quebra_agora'] else 'não'}",
         f"  Tese invalidada (fechamento além do swing contra a posição): {'SIM' if inval else 'NÃO'}"]
    return "\n".join(L), inval, info
