"""Stop da v4.1. Duas peças que a operação chama:

  inicial(s, D) -> preço do stop ao armar a entrada (s = sinal, D = pregão)
  mover(stop, t, p, D) -> stop que vale a partir da barra t+1, decidido com a barra t fechada
                          (p = posição aberta: lado, px, R, ext, t_ent)

Outras regras de stop (trailing etc.) são só outras funções com a mesma assinatura.
"""
MME_APERTO, COLCHAO_ATR, FOLGA_MIN_ATR = 38, 0.2, 0.25


def melhor(a, b, lado):
    """O stop mais a favor da posição (mais alto na compra, mais baixo na venda)."""
    return max(a, b) if lado == 1 else min(a, b)


def inicial_v41(s, D):
    """No pivô; se a MME38 do M15 está entre o pivô e a entrada (a mais de 0,25 ATR da entrada), sobe para
    0,2 ATR além dela. Exige a coluna 'mme38' no pregão."""
    t = s.t0 - 1
    lado, atr, ent, n = s.lado, D["atr"][t], D["close"][t], D["mme38"][t]
    if n == n and (ent - n) * lado > FOLGA_MIN_ATR * atr:
        return melhor(s.stop, n - lado * COLCHAO_ATR * atr, lado)
    return s.stop


def estrutura(stop, t, p, D):
    """Sobe (desce na venda) para cada novo fundo (topo) confirmado na barra t."""
    piv = D["pivos"].get(t)
    if piv is not None and piv[0] == ("F" if p.lado == 1 else "T"):
        return melhor(stop, piv[2], p.lado)
    return stop
