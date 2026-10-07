"""Z8: aplica a regra NaoOperarGapATR nos 5 EAs do WIN (bloco_gap.mqh.txt identico em todos).

Cada troca e' de texto exato e tem de acontecer UMA vez (assert). Preserva CRLF/LF de cada arquivo.
Roda uma vez so': se o EA ja' tem NaoOperarGapATR, nao mexe.
"""
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MT5 = AQUI.parents[4] / "mt5"
BLOCO = (AQUI / "bloco_gap.mqh.txt").read_text(encoding="ascii")
INPUT = "input double NaoOperarGapATR     = 1.0;  // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)"
CHAMADA = "   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)\n"


def cabecalho(versao, robo_delta, bak):
    import textwrap
    pars = [
        f"v{versao} (2026-10-06, frente Z8): REGRA NaoOperarGapATR -- nao abre posicao nova no dia em que "
        "|abertura - fechamento do pregao anterior| >= NaoOperarGapATR (1,0) x ATR14 D1 (media simples do True Range "
        "dos 14 pregoes anteriores). Input novo no FIM da lista; 0 desliga. As saidas seguem normais. Definicao "
        "completa (velas ate' 18:25, dia de vencimento numa serie continua) no bloco \"REGRA NaoOperarGapATR\", "
        "identico nos 5 EAs do WIN. Decide no 1o tick do pregao e escreve no Diario \"Dia bloqueado: gap X pts = Y ATR\".",
        "Por que (Z7, regra G1 k=1,0 pre-registrada, 5 robos somados, 2022-01 a 2026-10-05, custo R$2/op): bloqueia "
        "so' 10 dias em ~5 anos -- eleicoes de 2022 (03/10 e 31/10), Ucrania (24/02/2022), crash global de "
        "05/08/2024, tarifas (04/04/2025), 05/10/2026 (gap de +9,2% depois do 1o turno) e mais 4 --; +R$1.749 na "
        "soma (base +R$21.414), melhora 4 de 5 anos (2023 nao teve dia bloqueado), p99,8 contra bloquear o mesmo "
        "numero de dias ao acaso.",
        "FRAGILIDADE: o ganho vem quase todo do WinCincoMedias (+1.796), e o de 2026 depende de 05/10 (+542; sem "
        "ele 2026 = -247 e a regra cai para 3 de 5 anos). 5 regras testadas na Z7, sem correcao de multiplicidade.",
        f"Neste robo (Z7, total 2022-2026 com custo): {robo_delta}. Versao anterior em {bak}.",
    ]
    w = 66
    linhas = []
    for i, par in enumerate(pars):
        if i: linhas.append("")
        linhas += textwrap.wrap(par, w)
    sep = "//+" + "-" * (w + 2) + "+"
    corpo = "\n".join(f"//| {l:<{w}} |" for l in linhas)
    return f"{sep}\n{corpo}\n{sep}\n"


EAS = {
    "Win.mq5": dict(
        versao="2.06", bak="Win_v2_05.mq5.bak", delta="+R$107 (2024 +259, 2026 -152)",
        trocas=[
            ('#property version   "2.05"\n#property description "Win v2.05: calcula em H1 com filtro superior H3 (fixos no codigo)"',
             '#property version   "2.06"\n#property description "Win v2.06: H1 com filtro H3 + NaoOperarGapATR (sem entrada em dia de gap >= 1 ATR14 D1)"'),
            ("input ulong  MagicNumber         = 80080001; // Codigo que identifica as ordens deste robo\n",
             "input ulong  MagicNumber         = 80080001; // Codigo que identifica as ordens deste robo\n" + INPUT + "\n"),
            ("   Entra(sinal, wma, atr);\n}",
             "   if(GapDiaBloqueado()) { PrintFormat(\"Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)\", sinal > 0 ? \"COMPRA\" : \"VENDA\"); return; }\n"
             "   Entra(sinal, wma, atr);\n}"),
        ]),
    "Win_c1.mq5": dict(
        versao="2.07", bak="Win_c1_v2_06.mq5.bak", delta="-R$145 (2024 +7, 2026 -152)",
        trocas=[
            ('#property version   "2.06"\n#property description "Win_c1 v2.06: Win com break-even a mercado (15 min, colchao 7 pts); calcula em H1 com filtro H3"',
             '#property version   "2.07"\n#property description "Win_c1 v2.07: Win com break-even a mercado (15 min, colchao 7 pts); H1 com filtro H3 + NaoOperarGapATR"'),
            ("input double BreakEvenColchaoPts = 7.0;    // Break-even: fecha a mercado se o resultado flutuante for <= N pontos a favor (7 = custo 5 + slippage 2)\n",
             "input double BreakEvenColchaoPts = 7.0;    // Break-even: fecha a mercado se o resultado flutuante for <= N pontos a favor (7 = custo 5 + slippage 2)\n" + INPUT + "\n"),
            ("   Entra(sinal, wma, atr);\n}",
             "   if(GapDiaBloqueado()) { PrintFormat(\"Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)\", sinal > 0 ? \"COMPRA\" : \"VENDA\"); return; }\n"
             "   Entra(sinal, wma, atr);\n}"),
        ]),
    "WinCincoMedias.mq5": dict(
        versao="2.05", bak="WinCincoMedias_v2_04.mq5.bak", delta="+R$1.796 (2022 +1.249, 2024 +202, 2025 +202, 2026 +143)",
        trocas=[
            ('#property version   "2.04"', '#property version   "2.05"'),
            ("input double SupertrendMult     = 3.0;    // Multiplicador do ATR do Supertrend H4\n",
             "input double SupertrendMult     = 3.0;    // Multiplicador do ATR do Supertrend H4\n" + INPUT + "\n"),
            ("   Entra(est1, reg == est1);\n}",
             "   if(GapDiaBloqueado()) { PrintFormat(\"Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)\", est1 > 0 ? \"COMPRA\" : \"VENDA\"); return; }\n"
             "   Entra(est1, reg == est1);\n}"),
        ]),
    "WinDeslocamentoMatinal.mq5": dict(
        versao="1.31", bak="WinDeslocamentoMatinal_v1_30.mq5.bak", delta="-R$125 (2022 -490, 2025 -51, 2026 +416)",
        trocas=[
            ('#property version   "1.30"', '#property version   "1.31"'),
            ("input ulong  MagicNumber       = 80080101; // Codigo que identifica as ordens deste robo\n",
             "input ulong  MagicNumber       = 80080101; // Codigo que identifica as ordens deste robo\n" + INPUT + "\n"),
            ("   if(PositionSelect(_Symbol)) { Print(\"Ja' existe posicao no simbolo: nao entra\"); return; }\n",
             "   if(PositionSelect(_Symbol)) { Print(\"Ja' existe posicao no simbolo: nao entra\"); return; }\n"
             "   if(GapDiaBloqueado()) { PrintFormat(\"Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)\", sinal > 0 ? \"COMPRA\" : \"VENDA\"); return; }\n"),
        ]),
    "WinRetanguloEma34.mq5": dict(
        versao="1.07", bak="WinRetanguloEma34_v1_06.mq5.bak", delta="+R$116 (2022 +124, 2025 -48, 2026 +40)",
        trocas=[
            ('#property version   "1.06"', '#property version   "1.07"'),
            ("input double FiltroAmplitudeATR  = 0.5;  // v1.06 (f3): so' arma se a amplitude do pregao ate' a decisao >= isto x ATR14 D1 (0 = desligado)\n",
             "input double FiltroAmplitudeATR  = 0.5;  // v1.06 (f3): so' arma se a amplitude do pregao ate' a decisao >= isto x ATR14 D1 (0 = desligado)\n" + INPUT + "\n"),
            ("   if(!FiltroAmplitudeLibera(ts)) return;\n",
             "   // v1.07 (Z8): dia bloqueado pelo gap nao arma (nao muda estado nenhum).\n"
             "   if(GapDiaBloqueado()) { PrintFormat(\"%s entrada %s nao armada: dia bloqueado pelo gap (NaoOperarGapATR)\", TimeToString(ts), lado == RET_LONG ? \"COMPRA\" : \"VENDA\"); return; }\n"
             "   if(!FiltroAmplitudeLibera(ts)) return;\n"),
        ]),
}

ANCORA_ONINIT = "//+------------------------------------------------------------------+\nint OnInit()"
ANCORA_ONTICK = "void OnTick()\n{\n"

for nome, cfg in EAS.items():
    f = MT5 / nome
    raw = f.read_bytes().decode("ascii")
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    if "NaoOperarGapATR" in s:
        print(nome, "ja' tem a regra: nao mexe"); continue
    trocas = list(cfg["trocas"]) + [
        (ANCORA_ONINIT, BLOCO + "\n" + ANCORA_ONINIT),
        (ANCORA_ONTICK, ANCORA_ONTICK + CHAMADA),
        ("#property copyright", cabecalho(cfg["versao"], cfg["delta"], cfg["bak"]) + "#property copyright"),
    ]
    for a, b in trocas:
        c = s.count(a)
        assert c == 1, (nome, a[:60], c)
        s = s.replace(a, b)
    if crlf:
        s = s.replace("\n", "\r\n")
    f.write_bytes(s.encode("ascii"))
    print(nome, "->", cfg["versao"], "CRLF" if crlf else "LF")
