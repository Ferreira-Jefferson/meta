"""Gera relatorios_rodada3/replica_dia.md a partir de resultado.pkl."""
import pickle, numpy as np
R = pickle.load(open("resultado.pkl", "rb"))
real, boot, nul, nb = R["real"], R["boot"], R["nul"], R["nulo_p"]
MES = ["2026-%02d" % m for m in range(1, 9)]
CAB = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago"]
OUT = "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/relatorios_rodada3/replica_dia.md"
L = []


def f(x, k="p", d=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)): return "-"
    if k == "p": return ("%.1f" % (100 * x)).replace(".", ",") + "%"
    if k == "i": return "%d" % round(x)
    if k == "h":
        m = int(round(x)); return "%02d:%02d" % (m // 60, m % 60)
    return (("%." + str(d) + "f") % x).replace(".", ",")


def ic(key, k="p", d=2, nome="JanAug"):
    lo, hi = boot[nome][key]
    return "[%s ; %s]" % (f(lo, k, d), f(hi, k, d))


def tab(titulo, linhas, ic_key=None):
    """linhas: (rotulo, fn(nome)->str)."""
    L.append("| " + titulo + " | " + " | ".join(CAB) + " | jan-ago | IC95 jan-ago | set (ref.) |")
    L.append("|---|" + "---:|" * 11)
    for lab, fn, ickey, k, d in linhas:
        cels = [fn(m) for m in MES] + [fn("JanAug"), (ic(ickey, k, d) if ickey else "-"), fn("2026-09")]
        L.append("| " + lab + " | " + " | ".join(cels) + " |")
    L.append("")


def r(key, k="p", d=2): return lambda m: f(real[m].get(key), k, d)
def nl(kind, key, k="p", d=2): return lambda m: f(nb[kind][m][key][0], k, d)


def nl_ic(kind, key, k="p", d=2):
    return lambda m: "%s (%s-%s)" % (f(nb[kind][m][key][0], k, d), f(nb[kind][m][key][1], k, d), f(nb[kind][m][key][2], k, d))


def reg(titulo, linhas):
    L.append("| " + titulo + " | inverno EUA (2/jan-6/mar, 43 dias) | verao EUA (9/mar-ago, 121 dias) | jan-ago |")
    L.append("|---|---:|---:|---:|")
    for lab, key, k, d in linhas:
        L.append("| %s | %s | %s | %s |" % (lab, f(real["inv"].get(key), k, d), f(real["ver"].get(key), k, d), f(real["JanAug"].get(key), k, d)))
    L.append("")


V = {  # veredito por regra
 "R01": ("replicou", "ligada 13,2% x desligada 4,7% (2,8x); set 20,0% x 4,6% (4,3x). Razao >= 2x em 7 de 8 meses; jan quase sem efeito (8,4% x 6,3%). O nulo por blocos de 30 min da o mesmo (13,2% x 4,7%): e relogio de volatilidade, igual em set."),
 "R02": ("replicou (mais fraco no inverno)", "62,2% das pernadas em 21,1% do tempo (set 73,4%); lift 2,9x. Mensal 39 / 53 / 52 / 64 / 68 / 73 / 84 / 84%: so a partir de jun chega a 73%. O nulo por blocos da 62,6%: relogio."),
 "R03": ("replicou", "3,4% tarde x 10,3% antes das 13h (set 3,1% x 14,2%). Todos os meses: tarde 1,4-5,8% x manha 8,4-14,8%. Nulo por blocos 3,3%: relogio."),
 "R04": ("falhou", "tarde 64,6% x manha 67,2% (set 75,4%). Nulo por blocos 66,8% (tarde) / 65,9% (manha). A tarde nao destoa do acaso em jan-ago; set foi o mes de pico (n=61)."),
 "R05": ("falhou", "contra o consenso 50,0% (48/96) x 85,7% em set; meses 21 / 50 / 69 / 60 / 55 / 42 / 20 / 79%. Inverte de mes para mes; a mediana do restante do dia muda de sinal."),
 "R06": ("falhou", "dentro da janela 49,9% x fora 49,2% (set 73,1% x 51,9%). Jan 37,5% (continuacao), set e o pico."),
 "R07": ("falhou", "dentro 47,5% x fora 49,0% (set 65,9%)."),
 "R08": ("falhou", "dentro 48,4% x fora 47,5% (set 61,3%)."),
 "R09": ("parcial", "fecha 73,0% (set 85,7%) e em todos os meses >= 63%, mas a mesma distancia percorrida no sentido OPOSTO acontece em 70,6% dos dias: o excesso sobre o acaso e +2 pp (em set era +38 pp: 86% x 48%). E fato do tamanho do range, nao do gap."),
 "R10": ("falhou", "dia termina contra o gap em 53,4% (IC 45,7-60,7%), set 71,4%. Meses 48 / 47 / 45 / 80 / 47 / 52 / 32 / 76%."),
 "R11": ("replicou (= nulo)", "92,1% dos dias (set 95,2%); todos os meses 86-100%. Mas o nulo com horario (blocos de 30 min: 90,9%; blocos sorteados de outros dias: 91,2%) da o mesmo: nao e estrutura, e a pernada de H1 de 750 pts ser grande para o range do dia. 'Ambos os extremos' 27,4% = nulo (26,4%); os 52% de set foram excecao."),
 "R12": ("parcial", "mediana jan-ago: maxima 10:44, minima 11:04 (set 10:28 / 10:29). Mensal da maxima: 12:39 / 11:50 / 11:43 / 10:38 / 09:28 / 10:32 / 10:26 / 10:27. So de abr em diante fica em ~10:30; jan-mar e em torno de 11:45-12:40. O nulo de relogio (blocos de outros dias) da 10:52 / 11:11: o horario segue o relogio de volatilidade, que muda com o mes."),
 "R20": ("replicou", "corr. 0,19-0,67 por mes (set 0,28) x nulo +-0,07; todos os meses acima do p95. Tirando o regime do mes: 0,36 jan-ago; tirando o regime do dia: 0,23 (ainda positivo em todos os meses). Mais forte em jan (0,67) e no inverno (0,53 x 0,26 no verao, regime do mes removido)."),
 "R21": ("replicou", ":00 = 1,37x (set 1,51x), todos os meses 1,20-1,60 x nulo 1,00 (p95 ~1,06); :30 = 1,18x (set 1,27x), meses 1,06-1,28 (mar 1,06 fica na borda do nulo). O :00 e mais fraco em jan-mar (1,20-1,25) e mais forte em abr-ago (1,35-1,60)."),
 "R22": ("replicou (mais fraco)", "VR5 0,81 (set 0,69; IC 0,76-0,87) x nulo 1,00 (0,96-1,04). 7 de 8 meses abaixo do p5 do nulo; mai 1,01 e o unico que nao. Fraco em abr-jun (0,85-1,01)."),
 "R23": ("parcial", "tarde/manha: velocidade 2,6x (IC 2,1-3,0; set 4,5x), correcoes por pernada 1,4x (set 1,8x), por 1.000 pts 1,6x (set 2,5x), tamanho 0,88x. Mesmo sentido, magnitude menor que '4x e 3x'. O nulo por blocos (relogio) da 2,4x / 1,5x / 1,7x: e relogio."),
 "R24": ("replicou, com ressalva de horario", "razao de amplitude 10:30: 1,16 jan-ago (set 1,28). Mar-ago 1,13-1,27 e o 1o entre 67 cortes em 5 de 6 meses (mai: 2o); jan e fev NAO tem degrau as 10:30 (0,96 / 0,98) e sim as 11:30 (1,26 / 1,55, 1o corte). O degrau acompanha a abertura de NY: 10:30 BRT so quando os EUA estao no horario de verao (inicio 8/mar/2026)."),
}


def main():
    L.append("# Replicacao jan-ago/2026: regras de dia do WIN (R01-R12, R20-R24)\n")
    L.append("Base: WIN@D M1 (ajuste por diferenca, hora de Brasilia), somente 2026. 164 pregoes em jan-ago (+21 em set como referencia). O fechamento anterior de 02/01 vem de 30/12/2025; nenhum outro dado de 2025 foi usado. Definicoes e limiares congelados de `REGRAS.md`; nada foi otimizado. Nenhum lucro de estrategia foi calculado.\n")
    L.append("## Veredito\n")
    L.append("| Regra | O que diz | jan-ago/26 | set/26 | base / acaso | Veredito |")
    L.append("|---|---|---|---|---|---|")
    jr = real["JanAug"]; sp = real["2026-09"]
    linhas = [
     ("R01", "hora<11 liga a pernada (250->750)", f(jr["r01_on_pct"]) + " x " + f(jr["r01_off_pct"]), f(sp["r01_on_pct"]) + " x " + f(sp["r01_off_pct"]), "desligada " + f(jr["r01_off_pct"]) + "; nulo " + f(nb["bloco"]["JanAug"]["r01_on_pct"][0]) + " x " + f(nb["bloco"]["JanAug"]["r01_off_pct"][0])),
     ("R02", "<11h captura as pernadas", f(jr["r02_cap"]) + " em " + f(jr["r02_tempo"]) + " do tempo", f(sp["r02_cap"]), "proporcional " + f(jr["r02_tempo"])),
     ("R03", ">=13h quase nao nasce pernada", f(jr["r03_tarde_pct"]) + " x " + f(jr["r03_ate13_pct"]), f(sp["r03_tarde_pct"]) + " x " + f(sp["r03_ate13_pct"]), "ligada " + f(jr["r03_ate13_pct"])),
     ("R04", ">=13h recuo 500 vira 750", f(jr["r04_tarde_pct"]), f(sp["r04_tarde_pct"]), "nulo " + f(nb["bloco"]["JanAug"]["r04_tarde_pct"][0]) + "; manha " + f(jr["r04_manha_pct"])),
     ("R05", "consenso 10:30: resto contra", f(jr["r05_pct"]) + " (%d/%d)" % (jr["r05_k"], jr["r05_n"]), f(sp["r05_pct"]), "50%"),
     ("R06", "10:30-12:30, >500 do fech. ant. volta", f(jr["r06_in_pct"]), f(sp["r06_in_pct"]), "fora " + f(jr["r06_out_pct"])),
     ("R07", "idem, da abertura", f(jr["r07_in_pct"]), f(sp["r07_in_pct"]), "fora " + f(jr["r07_out_pct"])),
     ("R08", "idem, do VWAP", f(jr["r08_in_pct"]), f(sp["r08_in_pct"]), "fora " + f(jr["r08_out_pct"])),
     ("R09", "gap fecha no dia", f(jr["r09_pct"]), f(sp["r09_pct"]), "excursao simetrica " + f(jr["r09_mirror"])),
     ("R10", "dia termina contra o gap", f(jr["r10_pct"]), f(sp["r10_pct"]), "50%"),
     ("R11", ">=1 extremo nas 2 1as pernadas H1", f(jr["r11_any"]), f(sp["r11_any"]), "nulo " + f(nb["xdia"]["JanAug"]["r11_any"][0])),
     ("R12", "max/min do dia ate ~10:30 (mediana)", f(jr["r12_max"], "h") + " / " + f(jr["r12_min"], "h"), f(sp["r12_max"], "h") + " / " + f(sp["r12_min"], "h"), "nulo " + f(nb["xdia"]["JanAug"]["r12_max"][0], "h") + " / " + f(nb["xdia"]["JanAug"]["r12_min"][0], "h")),
     ("R20", "ondas de volatilidade (corr. 15 min)", f(jr["r20_corr"], "n", 2) + " (sem regime do mes " + f(jr["r20_corr_mes"], "n", 2) + ")", f(sp["r20_corr"], "n", 2), "0,00 +-0,07/mes"),
     ("R21", "minuto :00 / :30", f(jr["r21_m00"], "n", 2) + "x / " + f(jr["r21_m30"], "n", 2) + "x", f(sp["r21_m00"], "n", 2) + "x / " + f(sp["r21_m30"], "n", 2) + "x", "1,00x"),
     ("R22", "VR5 das 9-10h", f(jr["r22_vr5"], "n", 2), f(sp["r22_vr5"], "n", 2), "1,00 (0,96-1,04)"),
     ("R23", "tarde: x mais lenta / x mais correcoes", f(jr["r23_vel_razao"], "n", 1) + "x / " + f(jr["r23_corr_razao"], "n", 1) + "x", f(sp["r23_vel_razao"], "n", 1) + "x / " + f(sp["r23_corr_razao"], "n", 1) + "x", "nulo " + f(nb["bloco"]["JanAug"]["r23_vel_razao"][0], "n", 1) + "x / " + f(nb["bloco"]["JanAug"]["r23_corr_razao"][0], "n", 1) + "x"),
     ("R24", "degrau 10:30 (amplitude 15/15 min)", f(jr["r24_amp_1030"], "n", 2) + "x", f(sp["r24_amp_1030"], "n", 2) + "x", "outros cortes " + f(jr["r24_amp_ctrl_med"], "n", 2) + "x"),
    ]
    for rid, que, a, b, c in linhas:
        L.append("| %s | %s | %s | %s | %s | **%s** |" % (rid, que, a, b, c, V[rid][0]))
    L.append("")
    L.append("Resumo: replicaram R01, R02, R03, R11 (igual ao nulo), R20, R21, R22 (mais fraca), R24 (com ressalva de horario). Parciais: R09, R12, R23. Falharam: R04, R05, R06, R07, R08, R10. As regras de DIRECAO (R05-R10) e a virada da tarde (R04) sao justamente as que falharam; as que se mantiveram sao as de relogio de volatilidade (quando e quanto o preco anda), nao de para onde.\n")

    L.append("## Leitura de conjunto\n")
    L.append("- **Relogio x direcao.** Tudo o que replica descreve QUANDO e QUANTO o preco anda (R01-R03, R20-R24, e R11/R12 por consequencia). O nulo com horario (blocos de 30 min embaralhados, ou blocos sorteados de outros dias) reproduz R01, R02, R03, R11, R12 e R23 praticamente igual ao real: nesses casos o numero real nao tem excesso sobre um passeio aleatorio com a mesma volatilidade por horario. Em set a mesma comparacao dava excesso (R11 'ambos': 52% x nulo 27%); em jan-ago o excesso some (27% x 27%).")
    L.append("- **Direcao nao replica.** R04, R05, R06-R08, R10 ficam em ~50% (R04 em ~65% = nulo). Em set essas regras estavam em 60-86%: set foi um mes atipico de reversao da manha (R05 12/14, R06 73%), e jan-ago inverte de mes para mes sem padrao.")
    L.append("- **Horario de NY depende do DST americano.** O WIN opera 09:00-18:24 o ano todo, mas a abertura de NY cai as 10:30 BRT so quando os EUA estao no horario de verao (de 8/mar em diante); antes disso cai as 11:30. R24 mostra: jan-fev sem degrau as 10:30 (0,96 / 0,98) e degrau as 11:30 (1,26 / 1,55, primeiro entre 67 cortes), mar-ago degrau as 10:30. Qualquer regra amarrada ao 'marco das 10:30' (R05, R06-R08, R24, a janela 10:30-12:30) esta desalinhada em jan-6/mar. Nao troquei a definicao (replicacao): as tabelas de regime abaixo mostram a divisao.")
    L.append("- **Nivel de volatilidade.** Range diario medio: jan 3.116, fev 3.455, mar 4.183, abr 2.901, mai 2.895, jun 2.874, jul 2.750, ago 3.139, set 3.514. As regras de relogio enfraquecem com a volatilidade alta e dispersa (jan-mar: R02 39-53%, R12 as 11:40-12:40 na maxima, R22 0,76-0,83 ainda abaixo de 1) e se firmam de abr em diante (R02 64-84%, R12 ~10:30).")
    L.append("- **Janela de teste.** Por serem 8 meses de ~20 dias, cada percentual mensal tem erro padrao de 5-15 pp; o IC por bootstrap de dias esta ao lado de cada total.\n")

    # ------------------------------------------------ tabelas
    L.append("## Tabelas por regra (n e % por mes)\n")
    L.append("### Regras de pernada: R01, R02, R03 (tipo 'balanco', M5, X=250)\n")
    L.append("Definicao usada: zigzag de 100 pts no caminho M5; evento = o preco ja andou 250 do ultimo pivo (1x por pivo); y=1 se chega a 750 do pivo antes de recuar 100 do extremo (`kit_pernadas.eventos_balanco` + `rotular`, a mesma de `chave.md`). Hora do evento = abertura da vela M5 onde o avanco ocorre. Os eventos de um mesmo dia se sobrepoem; o IC e por bootstrap de dias.\n")
    tab("R01", [
        ("P(750) hora<11 (ligada)", r("r01_on_pct", "p", 1), "r01_on_pct", "p", 1),
        ("n eventos ligada", r("r01_on_n", "i"), None, "i", 0),
        ("P(750) hora>=11 (desligada)", r("r01_off_pct", "p", 1), "r01_off_pct", "p", 1),
        ("n eventos desligada", r("r01_off_n", "i"), None, "i", 0),
        ("nulo 30 min, ligada (p5-p95)", nl_ic("bloco", "r01_on_pct", "p", 1), None, "p", 0),
        ("nulo 30 min, desligada (p5-p95)", nl_ic("bloco", "r01_off_pct", "p", 1), None, "p", 0),
    ])
    tab("R02", [
        ("pernadas capturadas com <11h", r("r02_cap", "p", 1), "r02_cap", "p", 1),
        ("tempo ligado (fracao dos minutos)", r("r02_tempo", "p", 1), None, "p", 0),
        ("n pernadas (eventos que chegam a 750)", r("r02_nper", "i"), None, "i", 0),
        ("nulo 30 min, capturadas (p5-p95)", nl_ic("bloco", "r02_cap", "p", 1), None, "p", 0),
    ])
    tab("R03", [
        ("P(750) hora>=13", r("r03_tarde_pct", "p", 1), "r03_tarde_pct", "p", 1),
        ("n eventos >=13h", r("r03_tarde_n", "i"), None, "i", 0),
        ("P(750) hora<13 (ligada)", r("r03_ate13_pct", "p", 1), "r03_ate13_pct", "p", 1),
        ("nulo 30 min, >=13h (p5-p95)", nl_ic("bloco", "r03_tarde_pct", "p", 1), None, "p", 0),
    ])
    L.append("### R04: recuo de 500 do extremo, depois das 13h\n")
    L.append("Definicao usada (`transicoes/an.py`): zigzag de 750 no caminho M1 de 4 pontos por vela; evento = recuo de 500 do maximo (minimo) corrente da perna, 1x por extremo, so com alta acumulada >= 750; y=1 se o recuo chega a 750 antes de novo extremo. Eventos sem desfecho (fim do dia) descartados. 'Manha' = antes das 13h.\n")
    tab("R04", [
        ("P(vira 750) tarde (>=13h)", r("r04_tarde_pct", "p", 1), "r04_tarde_pct", "p", 1),
        ("n eventos tarde", r("r04_tarde_n", "i"), None, "i", 0),
        ("P(vira 750) manha (<13h)", r("r04_manha_pct", "p", 1), "r04_manha_pct", "p", 1),
        ("n eventos manha", r("r04_manha_n", "i"), None, "i", 0),
        ("nulo 30 min, tarde (p5-p95)", nl_ic("bloco", "r04_tarde_pct", "p", 1), None, "p", 0),
        ("nulo 30 min, manha (p5-p95)", nl_ic("bloco", "r04_manha_pct", "p", 1), None, "p", 0),
    ])
    L.append("### R05: consenso das 3 leituras as 10:30 (`a2.py`)\n")
    L.append("Consenso = retorno desde a abertura, preco - VWAP (ponderada por close x volume) e preco - fechamento anterior com o mesmo sinal as 10:30; 'contra' = o fechamento do dia fica do lado oposto do preco das 10:30. Base: 50% (binomial). O nulo por blocos de 30 min nao se aplica: preserva o preco as 10:30 e o fechamento.\n")
    tab("R05", [
        ("dias contra o consenso", r("r05_pct", "p", 1), "r05_pct", "p", 1),
        ("n dias com consenso", r("r05_n", "i"), None, "i", 0),
        ("dias contra o consenso (k)", r("r05_k", "i"), None, "i", 0),
        ("mediana do restante a favor do consenso, pts", r("r05_med_pts", "n", 0), "r05_med_pts", "n", 0),
        ("extra: so retorno desde a abertura, contra", r("r05dir_pct", "p", 1), "r05dir_pct", "p", 1),
    ])
    L.append("### R06-R08: desvio >500 pts, janela 10:30-12:30, horizonte 60 min (`a4.py`)\n")
    L.append("Grade a cada 15 min de 09:30 a 16:00; desvio dv = preco - VWAP (tipico x volume acumulada), do = preco - abertura, dp = preco - fechamento anterior; 'contra' = o retorno dos 60 min seguintes tem sinal oposto ao do desvio. Janela = tempos de 10:30 a 12:15 (a 12:30 e 'depois'); fora = antes de 10:30 + de 12:30 em diante. Amostras sobrepostas dentro do dia (IC por dias). Base: 50% / 'fora da janela'.\n")
    for rid, nm in (("r06", "R06 (fech. anterior)"), ("r07", "R07 (abertura)"), ("r08", "R08 (VWAP)")):
        tab(nm, [
            ("contra, dentro 10:30-12:30", r(rid + "_in_pct", "p", 1), rid + "_in_pct", "p", 1),
            ("n dentro", r(rid + "_in_n", "i"), None, "i", 0),
            ("contra, fora da janela", r(rid + "_out_pct", "p", 1), rid + "_out_pct", "p", 1),
            ("n fora", r(rid + "_out_n", "i"), None, "i", 0),
        ])
    L.append("### R09, R10: gap\n")
    L.append("Gap = abertura do dia - fechamento anterior (qualquer valor diferente de zero; n = dias com gap). R09: o dia toca o fechamento anterior. Base para R09 (nova, `-` no original): o preco percorre a mesma distancia |gap| no sentido OPOSTO ao gap a partir da abertura ('excursao simetrica'). R10: fechamento do dia - abertura contra o sinal do gap (leitura mais proxima do relatorio: 'dia termina na direcao do gap', direcao do dia = abertura->fechamento); a coluna alternativa mede o fechamento contra o fechamento anterior.\n")
    tab("R09 / R10", [
        ("R09 gap fecha no dia", r("r09_pct", "p", 1), "r09_pct", "p", 1),
        ("base: excursao simetrica", r("r09_mirror", "p", 1), "r09_mirror", "p", 1),
        ("n dias com gap", r("gap_n", "i"), None, "i", 0),
        ("R10 dia termina contra o gap (fech. - abertura)", r("r10_pct", "p", 1), "r10_pct", "p", 1),
        ("R10 alt.: fechamento do lado oposto do fech. anterior", r("r10_alt_pct", "p", 1), "r10_alt_pct", "p", 1),
    ])
    L.append("### R11, R12: extremos do dia\n")
    L.append("R11 (`sequencia.md`): zigzag de 750 sobre o caminho H1; extremo do dia (max ou min) cai ate o fim da 2a pernada (se ha menos de 2 pernadas, conta como sim). Nulos: (a) blocos de 30 min embaralhados e (b) cada bloco de 30 min do dia sorteado de outro dia (preserva o relogio de volatilidade, destroi a estrutura do dia). 300 simulacoes cada. R12: horario da vela M1 da maxima/minima do dia (1a ocorrencia), mediana dos dias.\n")
    tab("R11 / R12", [
        ("R11 >=1 extremo nas 2 1as pernadas H1", r("r11_any", "p", 1), "r11_any", "p", 1),
        ("R11 ambos os extremos", r("r11_both", "p", 1), "r11_both", "p", 1),
        ("n dias", r("r11_n", "i"), None, "i", 0),
        ("nulo blocos 30 min, >=1 extremo (p5-p95)", nl_ic("bloco", "r11_any", "p", 1), None, "p", 0),
        ("nulo dias sorteados, >=1 extremo (p5-p95)", nl_ic("xdia", "r11_any", "p", 1), None, "p", 0),
        ("nulo dias sorteados, ambos (p5-p95)", nl_ic("xdia", "r11_both", "p", 1), None, "p", 0),
        ("R12 mediana horario da maxima", r("r12_max", "h"), "r12_max", "h", 0),
        ("R12 mediana horario da minima", r("r12_min", "h"), "r12_min", "h", 0),
        ("nulo dias sorteados, maxima", nl_ic("xdia", "r12_max", "h"), None, "h", 0),
        ("nulo dias sorteados, minima", nl_ic("xdia", "r12_min", "h"), None, "h", 0),
    ])
    L.append("### R20: ondas de volatilidade\n")
    L.append("Faixa (max-min) de blocos de 15 min (37 por dia, 09:00-18:15), em log, menos a media do mesmo horario; correlacao entre bloco e o seguinte no mesmo dia. A media do horario e tirada dentro de cada coluna (mes) e, em jan-ago, sobre os 164 dias; a linha 'sem regime do mes' tira a media de cada mes, a linha 'sem regime do dia' tira tambem a media de cada dia. Nulo: permutar os dias dentro de cada horario (300 sorteios), p5-p95.\n")
    tab("R20", [
        ("corr. bloco t x t+1", r("r20_corr", "n", 2), "r20_corr", "n", 2),
        ("sem regime do mes", r("r20_corr_mes", "n", 2), "r20_corr_mes", "n", 2),
        ("sem regime do dia", r("r20_corr_semdia", "n", 2), "r20_corr_semdia", "n", 2),
        ("nulo (p5 ; p95)", lambda m: "%s ; %s" % (f(nul[m]["r20"][1], "n", 2), f(nul[m]["r20"][2], "n", 2)), None, "n", 2),
        ("range diario medio, pts", r("amp_dia", "n", 0), None, "n", 0),
    ])
    L.append("### R21: minuto cheio\n")
    L.append("Faixa M1 / media da faixa da hora, 10h-17h sem 10:30-10:32; media sobre as horas-dia. Nulo: permutar os minutos dentro de cada hora-dia (200 sorteios), p5-p95.\n")
    tab("R21", [
        (":00", r("r21_m00", "n", 2), "r21_m00", "n", 2),
        ("nulo :00 (p5 ; p95)", lambda m: "%s ; %s" % (f(nul[m]["r21_00"][1], "n", 2), f(nul[m]["r21_00"][2], "n", 2)), None, "n", 2),
        (":30", r("r21_m30", "n", 2), "r21_m30", "n", 2),
        ("nulo :30 (p5 ; p95)", lambda m: "%s ; %s" % (f(nul[m]["r21_30"][1], "n", 2), f(nul[m]["r21_30"][2], "n", 2)), None, "n", 2),
        ("minutos sem destaque (media)", r("r21_outros", "n", 2), None, "n", 2),
    ])
    L.append("### R22: razao de variancia em 5 min, 09:00-10:00\n")
    L.append("VR5 = var(retorno de 5 min, janelas sobrepostas) / (5 x var(retorno de 1 min)), so velas consecutivas dentro de 09:00-10:00, pooled nos dias. Nulo (do relatorio original): permutar os retornos de 1 min dentro de cada dia (100 sorteios), p5-p95.\n")
    tab("R22", [
        ("VR5 9-10h", r("r22_vr5", "n", 2), "r22_vr5", "n", 2),
        ("nulo (p5 ; p95)", lambda m: "%s ; %s" % (f(nul[m]["r22"][1], "n", 2), f(nul[m]["r22"][2], "n", 2)), None, "n", 2),
    ])
    L.append("### R23: tarde x manha\n")
    L.append("Pernadas de zigzag 750 em M5 (todas, inclusive a 1a do dia e a aberta no fim, como no original). Manha = inicio antes de 12:00; tarde = inicio a partir de 13:00 (a faixa 12-13h fica fora). Velocidade = tamanho / duracao (duracao = fim - inicio, minimo 5 min = uma vela M5). Correcao = recuo >= 5 pts seguido de novo extremo dentro da pernada. Razoes tarde/manha: velocidade invertida (manha/tarde = 'x mais lenta').\n")
    tab("R23", [
        ("n pernadas manha", r("r23_n_m", "i"), None, "i", 0),
        ("n pernadas tarde", r("r23_n_t", "i"), None, "i", 0),
        ("tamanho mediano manha, pts", r("r23_size_m", "n", 0), "r23_size_m", "n", 0),
        ("tamanho mediano tarde, pts", r("r23_size_t", "n", 0), "r23_size_t", "n", 0),
        ("velocidade mediana manha, pts/min", r("r23_vel_m", "n", 1), "r23_vel_m", "n", 1),
        ("velocidade mediana tarde, pts/min", r("r23_vel_t", "n", 1), "r23_vel_t", "n", 1),
        ("manha/tarde: velocidade (x mais lenta)", r("r23_vel_razao", "n", 1), "r23_vel_razao", "n", 1),
        ("nulo 30 min (p5-p95)", nl_ic("bloco", "r23_vel_razao", "n", 1), None, "n", 1),
        ("correcoes por pernada manha / tarde", lambda m: "%s / %s" % (f(real[m]["r23_corr_m"], "n", 1), f(real[m]["r23_corr_t"], "n", 1)), None, "n", 1),
        ("tarde/manha: correcoes por pernada", r("r23_corr_razao", "n", 1), "r23_corr_razao", "n", 1),
        ("nulo 30 min (p5-p95)", nl_ic("bloco", "r23_corr_razao", "n", 1), None, "n", 1),
        ("tarde/manha: correcoes por 1.000 pts", r("r23_corr1000_razao", "n", 1), "r23_corr1000_razao", "n", 1),
        ("tarde/manha: tamanho", r("r23_size_razao", "n", 2), "r23_size_razao", "n", 2),
    ])
    L.append("### R24: degrau das 10:30\n")
    L.append("Razao entre a media por minuto dos 15 min depois do corte e dos 15 antes, mediana dos dias; controle = os outros 66 cortes de 5 em 5 min das 10:30 as 16:00. 'posto' = posicao do corte entre os 67 (1 = o maior). Volume = coluna VOL do M1.\n")
    tab("R24", [
        ("amplitude 10:30", r("r24_amp_1030", "n", 2), "r24_amp_1030", "n", 2),
        ("posto 10:30 (de 67)", r("r24_amp_rank1030", "i"), None, "i", 0),
        ("amplitude 11:30", r("r24_amp_1130", "n", 2), "r24_amp_1130", "n", 2),
        ("posto 11:30 (de 67)", r("r24_amp_rank1130", "i"), None, "i", 0),
        ("amplitude, mediana dos outros cortes", r("r24_amp_ctrl_med", "n", 2), None, "n", 2),
        ("volume 10:30", r("r24_vol_1030", "n", 2), "r24_vol_1030", "n", 2),
        ("posto volume 10:30", r("r24_vol_rank1030", "i"), None, "i", 0),
        ("volume 11:30", r("r24_vol_1130", "n", 2), "r24_vol_1130", "n", 2),
        ("posto volume 11:30", r("r24_vol_rank1130", "i"), None, "i", 0),
    ])

    L.append("## Divisao por regime do horario de NY\n")
    L.append("Inverno dos EUA: 2/jan a 6/mar (43 pregoes), abertura de NY as 11:30 BRT. Verao dos EUA: 9/mar a ago (121 pregoes), abertura as 10:30 BRT. Definicoes inalteradas (10:30).\n")
    reg("regra", [
        ("R01 ligada", "r01_on_pct", "p", 1), ("R01 desligada", "r01_off_pct", "p", 1), ("R02 captura", "r02_cap", "p", 1),
        ("R03 >=13h", "r03_tarde_pct", "p", 1), ("R04 tarde", "r04_tarde_pct", "p", 1), ("R05 contra consenso", "r05_pct", "p", 1),
        ("R06 janela", "r06_in_pct", "p", 1), ("R07 janela", "r07_in_pct", "p", 1), ("R08 janela", "r08_in_pct", "p", 1),
        ("R09 gap fecha", "r09_pct", "p", 1), ("R10 contra o gap", "r10_pct", "p", 1), ("R11 >=1 extremo", "r11_any", "p", 1),
        ("R12 max (mediana)", "r12_max", "h", 0), ("R12 min (mediana)", "r12_min", "h", 0), ("R20 corr.", "r20_corr", "n", 2),
        ("R21 :00", "r21_m00", "n", 2), ("R21 :30", "r21_m30", "n", 2), ("R22 VR5", "r22_vr5", "n", 2),
        ("R23 velocidade manha/tarde", "r23_vel_razao", "n", 1), ("R24 amplitude 10:30", "r24_amp_1030", "n", 2),
        ("R24 amplitude 11:30", "r24_amp_1130", "n", 2)])

    L.append("## Veredito e leitura por regra\n")
    for rid in ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R20", "R21", "R22", "R23", "R24"]:
        L.append("- **%s: %s.** %s" % (rid, V[rid][0], V[rid][1]))
    L.append("")
    L.append("## Escolhas de definicao (onde o texto original era ambiguo)\n")
    L.append("- Dias parciais excluidos: 18/02 (abertura 13:00, quarta de cinzas) e 31/07 (abertura 12:34). Os demais 164 pregoes de jan-ago tem 09:00-18:24 (a vela das 09:00 as vezes so tem dado a partir de 09:02-09:04).")
    L.append("- R01-R03: familia 'balanco' (a que gerou 20% x 5% e 73% em `chave.md`), nao a 'extremo'. 'Hora' = abertura da vela M5 do evento. 'Tempo ligado' = fracao das velas M1 antes das 11:00.")
    L.append("- R04: caminho M1 de 4 pontos por vela e eventos de `transicoes/an.py` (tipo 'extremo', X=500, D=750). A tarde e >= 13:00 e a manha < 13:00.")
    L.append("- R05: VWAP ponderada por close x volume e T=10:30 como no `a2.py`; R06-R08 usam VWAP de preco tipico, como no `a4.py`. 'Dentro da janela' = instantes 10:30, 10:45, ..., 12:15.")
    L.append("- R10: 'termina contra o gap' = fechamento menor (maior) que a abertura quando houve gap de alta (baixa). A leitura contra o fechamento anterior aparece como alternativa.")
    L.append("- R11: se o dia tem menos de 2 pernadas H1 de 750, considera-se que os extremos estao nas 'duas primeiras' (todo o dia). Aconteceu em poucos dias e favorece o sim igualmente no nulo.")
    L.append("- R12: horario por vela M1 (abertura da vela), 1a ocorrencia do extremo.")
    L.append("- R20: 37 blocos por dia; media do horario tirada dentro do conjunto de dias analisado (mes ou jan-ago).")
    L.append("- R23: duracao minima 5 min; 'tarde' >= 13:00 (REGRAS.md), 'manha' < 12:00 (relatorio de set).")
    L.append("- Serie: WIN@D com ajuste por diferenca; setembro aqui sai dela e nao do WINV26 do original (R09 deu 18/21 em vez de 17/20 porque 01/09 tem gap contra 31/08; demais numeros de set batem com os originais: R01 20,0%, R02 73,4%, R03 3,1%, R05 12/14 com mediana -1.093, R06 73,1%, R07 65,9%, R08 61,3%, R11 95,2%, R12 10:28/10:29, R21 1,51x/1,27x, R22 0,69, R24 1,28x).")
    L.append("- Nulos: R01-R04 e R23 usam embaralhar velas M1 dentro de blocos de 30 min de cada pregao (300 sorteios; gaps entre velas ficam na posicao). R05, R06-R10: binomial/base real, porque o embaralho de blocos preserva os precos em :00 e :30, abertura e fechamento. R11/R12 recebem tambem o nulo de blocos sorteados de outros dias (300 sorteios), que preserva o relogio de volatilidade e destroi a estrutura do dia.")
    L.append("- Codigo: `lib.py`, `stats.py`, `run.py`, `relatorio.py` nesta pasta (rodada3/replica_dia); resultado bruto em `resultado.pkl`.")
    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print("ok", OUT)


main()
