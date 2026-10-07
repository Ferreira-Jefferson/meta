"""Frente B: junta filtro_res.pkl + saida_res.pkl em resultado.md, resultado.csv e trades/*.csv. Uso: python relatorio.py"""
import pickle
from functools import lru_cache
import numpy as np
import pandas as pd
from comum import *
import saida as S
S._ticks = lru_cache(maxsize=None)(S._ticks.__wrapped__)

F = pickle.load(open(AQ / "filtro_res.pkl", "rb")); R = pickle.load(open(AQ / "saida_res.pkl", "rb"))
e = F["e"]; P = F["P"]; res = F["res"]
mes = e.mes.to_numpy(); est = e.estrategia.to_numpy(); rs = e.rs.to_numpy(); saida = e.t_saida_ms.to_numpy()
rng = np.random.default_rng(23)
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out"]
r_idx = R["r_idx"]; t_idx = R["t_idx"]

# ------------------------------------------------------------------ versoes: (rs bruto por evento, mantidos)
ALL = np.ones(len(e), bool)
v_ret = rs.copy(); v_ret[r_idx] = R["base_r"]                       # RetEma34 re-simulado (1,1): comparador do resize
fin = R["res"]["nota"]["final"]; v_resize = rs.copy(); v_resize[r_idx] = fin + CUSTO     # resize pela nota (modelo 'nota')
VERS = {
    "sem filtro (original)": (rs, ALL),
    "filtro tabela (WF)": (rs, res["tabela"]["keep"]),
    "filtro logistica (WF) = sem filtro": (rs, res["logit"]["keep"]),
    "filtro nota (WF) = sem filtro": (rs, res["nota"]["keep"]),
    "RetEma34 re-simulado (1,1)": (v_ret, ALL),
    "RetEma34 resize pela nota (WF)": (v_resize, ALL),
}

def tabela_mensal(rsv, keep, subset, custo):
    out = []
    for m in range(1, 11):
        k = keep & subset & (mes == m)
        out.append((rsv[k] - custo * k[k].sum() / max(k[k].sum(), 1)).sum() if False else rsv[k].sum() - custo * k.sum())
    return out

def linha(rsv, keep, subset):
    k = keep & subset
    liq0 = rsv[k].sum(); liq2 = rsv[k].sum() - CUSTO * k.sum()
    _, smin, q = equity(rsv[k] - CUSTO, saida[k])
    return liq0, liq2, int(k.sum()), smin, q

CARTM = np.isin(est, CART)
md = []
def P_(s=""): md.append(s)

# ------------------------------------------------------------------ resultado.csv
rows = []
for nome, (rsv, keep) in VERS.items():
    for s in CART + ["Win_c1", "CARTEIRA(5)"]:
        sub = CARTM if s == "CARTEIRA(5)" else (est == s)
        liq0, liq2, n, smin, q = linha(rsv, keep, sub)
        rows.append(dict(versao=nome, escopo=s, liquido_sem_custo=round(liq0, 1), liquido_R2=round(liq2, 1), trades=n, saldo_min_R1000=round(smin, 1), quebrou=q))
pd.DataFrame(rows).to_csv(AQ / "resultado.csv", index=False)

# ------------------------------------------------------------------ forcado: fracao fixa a partir do mes 4 (sem escolha)
forc = {}
grupos = [idx for _, idx in pd.DataFrame(dict(m=mes, s=est)).groupby(["m", "s"]).indices.items()]
rsl = rs - CUSTO
for k in ("tabela", "logit", "nota"):
    for f in (0.2, 0.4):
        keep = np.ones(len(e), bool)
        for m in range(MES_MIN_FILTRO, 11):
            past = (mes >= 2) & (mes < m) & ~np.isnan(P[k]) & (est != "Win_c1")
            thr = np.quantile(P[k][past], f)
            mm = mes == m
            keep[mm] = P[k][mm] >= thr
        liq = rsl[keep & CARTM].sum()
        sr = np.array([rsl[sorteio(grupos, keep, rng) & CARTM].sum() for _ in range(200)])
        forc[(k, f)] = (liq, (keep & CARTM).sum(), np.median(sr), np.percentile(sr, 95), (sr < liq).mean() * 100)

# ------------------------------------------------------------------ markdown
P_("# Frente B - Nota / probabilidade de acerto")
P_("")
P_("Veredito: a nota das outras estrategias nao preve o acerto da entrada (AUC fora da amostra 0,47-0,50), nenhum filtro walk-forward bate o sorteio, e a unica celula acima do p95 (alvo mais largo no RetEma34 pela nota) e' uma entre ~115 olhadas, em cima de uma re-simulacao que nao reproduz o original. Nao ha ganho a incorporar.")
P_("")
P_("## Como foi feito")
P_("- Unidade: cada ENTRADA das 6 estrategias (`eventos.parquet`, 1.608). Acerto = `rs > 0` na saida original. Mes = mes da entrada.")
P_("- Walk-forward mensal expansivo: o mes m usa modelo e limiar treinados so' com os meses < m. **Janeiro nao tem passado e opera sem filtro. O filtro so' pode agir a partir de abril** (o limiar precisa de previsoes fora da amostra de pelo menos fev e mar); jan-mar operam sem filtro.")
P_("- Limiar: fracao a pular f em {0, 10, 20, 30, 40, 50}% escolhida pelo maior liquido R$2 do passado, medido nas previsoes fora da amostra de fev..m-1 (nao na amostra de treino). Empate vai para f menor.")
P_("- Features (so' dados fechados antes da entrada, sem Win_c1, sem WdoRetangulo): n de outras a favor, n contra, forca da propria, taxa de acerto da estrategia no treino, e a ORDEM DE CHEGADA (ideia 5: 2a a favor no lucro / 2a a favor no prejuizo). Win_c1 fica fora do treino e da escolha do limiar (e' gemea do Win) mas recebe o filtro.")
P_("- 3 modelos: (i) tabela por n de outras a favor com Laplace (k+1)/(n+2); (ii) logistica L2 com 6 features; (iii) nota = media dos voto x forca das 3 outras, calibrada por Platt.")
P_("- Controle: sorteio de 200 mantendo o MESMO numero de entradas por (mes, estrategia). Placebo: 200 execucoes de todo o walk-forward com os rotulos de acerto embaralhados dentro do mes.")
P_("- Capital R$1.000 corrido por ordem de saida, 1 contrato; quebra = saldo <= 0 (nenhuma versao quebrou). R$/ponto = 0,20.")
P_("- **Celulas olhadas: ~115** (filtro 3 modelos x 6 fracoes = 18; resize RetEma34 9 celulas x 3 modelos = 27; ideia 6 = 9; overlay de stop 4 x 3 modelos = 12; tabela descritiva de chegada 4 classes x 6 estrategias x 2 metades = 48; AUC por estrategia e fracoes forcadas nao contadas). A escolha das celulas e' sempre no passado; o que se olha depois e' o resultado.")
P_("")
P_("## AUC e calibracao fora da amostra (meses 2-10, sem Win_c1)")
P_("| modelo | AUC geral | " + " | ".join(s.replace("WinDeslocamentoMatinal", "Desloc").replace("WinRetanguloEma34", "RetEma34").replace("WinCincoMedias", "Cinco") for s in CART) + " |")
P_("|---|---|" + "---|" * len(CART))
for k in ("tabela", "logit", "nota"):
    a = F["aucs"][k]
    P_(f"| {k} | {a['geral']:.3f} | " + " | ".join(f"{a[s]:.3f}" for s in CART) + " |")
P_("")
P_("Calibracao por quintil de probabilidade prevista (prevista / acerto realizado / n):")
for k in ("tabela", "logit", "nota"):
    c = F["calib"][k]
    P_(f"- {k}: " + "; ".join(f"Q{int(i)+1} {r.prevista:.2f}/{r.realizada:.2f}/{int(r.n)}" for i, r in c.iterrows()))
P_("")
P_("Leitura: AUC ~0,5 e quintis sem ordem. As probabilidades previstas variam de 0,35 a 0,52, mas o acerto realizado nao acompanha (a logistica chega a ter o quintil mais baixo acertando 49% e o mais alto 42%). Nao ha informacao nas outras estrategias para dizer se esta entrada acerta.")
P_("")
P_("## Entra ou nao: walk-forward contra sorteio e placebo (carteira = 5 estrategias sem Win_c1, R$2/op)")
P_("| modelo | fracoes escolhidas por mes (abr..out) | liquido R$2 | entradas | sorteio p50 / p5-p95 | percentil no sorteio | placebo p50 / p95 | percentil no placebo |")
P_("|---|---|---|---|---|---|---|---|")
base = F["base"]["CART"]
P_(f"| sem filtro | - | {base[1]:.0f} | {base[2]} | - | - | - | - |")
for k in ("tabela", "logit", "nota"):
    r = res[k]; sr = r["sorteio_cart"]; pl = r["placebo"]
    fr = " ".join(f"{f:.1f}" for m, f, t in r["info"][3:])
    P_(f"| {k} | {fr} | {r['met']['CART'][1]:.0f} | {r['met']['CART'][2]} | {np.median(sr):.0f} / {np.percentile(sr,5):.0f}-{np.percentile(sr,95):.0f} | {r['pct_cart']:.0f} | {np.median(pl):.0f} / {np.percentile(pl,95):.0f} | {r['pct_placebo']:.0f} |")
P_("")
P_("A logistica e a nota nunca encontraram, no passado, um limiar que ganhasse do 'nao filtrar': operam sem filtro o ano todo (resultado = sem filtro; o sorteio e o placebo degeneram nesse valor). So' a tabela filtrou (f>0 em abr, jul, ago) e perdeu R$3.487 contra nao filtrar, no percentil 16 do sorteio.")
P_("")
P_("Controle adicional, fracao FIXA a partir de abril (sem escolha de limiar) - liquido R$2 da carteira, entradas, sorteio p50/p95, percentil:")
for (k, f), (liq, n, p50, p95, pc) in forc.items():
    P_(f"- {k}, pular {int(f*100)}%: {liq:.0f}, {n} entradas, sorteio {p50:.0f}/{p95:.0f}, percentil {pc:.0f}  (sem filtro: {base[1]:.0f})")
P_("")
P_("## Tabela mensal da carteira (5 estrategias, entrada no mes)")
P_("| versao | custo | " + " | ".join(MESES) + " | total | trades | saldo min | quebrou |")
P_("|---|---|" + "---|" * 10 + "---|---|---|---|")
for nome, (rsv, keep) in VERS.items():
    if "= sem filtro" in nome:
        continue
    for c, nc in ((0.0, "sem"), (CUSTO, "R$2")):
        mm = tabela_mensal(rsv, keep, CARTM, c)
        liq0, liq2, n, smin, q = linha(rsv, keep, CARTM)
        P_(f"| {nome} | {nc} | " + " | ".join(f"{x:.0f}" for x in mm) + f" | {sum(mm):.0f} | {n} | {smin:.0f} | {'SIM' if q else 'nao'} |")
P_("")
P_("Totais por estrategia (sem custo / R$2), sem filtro e com o filtro da tabela:")
P_("| estrategia | sem filtro | filtro tabela | trades sem -> com |")
P_("|---|---|---|---|")
for s in ESTR:
    a = linha(rs, ALL, est == s); b = linha(rs, res["tabela"]["keep"], est == s)
    P_(f"| {s} | {a[0]:.0f} / {a[1]:.0f} | {b[0]:.0f} / {b[1]:.0f} | {a[2]} -> {b[2]} |")
P_("")
P_("## Tamanho de alvo e stop pela nota (re-simulacao nos ticks, mesma entrada)")
P_("RetEma34 tem stop (0,45L) e alvo (0,90L) proprios, fixos. A re-simulacao com `saida.py` em (1,1) NAO reproduz o CSV original: so' 69% dos trades saem iguais e o bruto sobe de R$2.307 para R$3.010 (liquido R$2: 841 -> 1.544), porque o EA aproxima o alvo com o tempo (AproximarAlvo) e a re-simulacao usa alvo fixo. Por isso o comparador do resize e' a re-simulacao (1,1), nao o CSV. De passagem, isso sugere que a aproximacao do alvo custa dinheiro, mas e' achado lateral, nao testado aqui.")
P_("Grade (9 celulas): alvo x{1; 1,25; 1,5} nas entradas de nota alta (>= mediana das previsoes passadas) e stop x{1; 0,75; 0,5} nas de nota baixa; a celula do mes m e' a melhor no passado.")
P_("| score usado | base re-sim R$2 | walk-forward R$2 | celulas escolhidas abr..out (alvo x, stop x) | sorteio de score p50 / p95 | percentil |")
P_("|---|---|---|---|---|---|")
for k in ("logit", "nota", "tabela"):
    r = R["res"][k]
    cs = " ".join(f"{v[0][0]:g}/{v[0][1]:g}" for m, v in r["esc"].items())
    P_(f"| {k} | 1544 | {r['final'].sum():.0f} | {cs} | {np.median(r['ctrl']):.0f} / {np.percentile(r['ctrl'],95):.0f} | {r['pct']:.0f} |")
P_("")
P_("Leitura: com a logistica e a tabela a regra nao supera o sorteio (percentil 56 e 86); com a nota chega a +R$227 sobre a base e percentil 95 do sorteio. E' 1 de 3 modelos, a diferenca vem sempre de alargar o alvo (stop mais curto perde em toda celula: todas as celulas com stop x0,75 ou x0,5 ficam abaixo da base), e a melhoria de alvo mais largo existe tambem fora da nota. Nao e' evidencia de que a NOTA ajude; e' evidencia de que, na re-simulacao sem a aproximacao do alvo, alvo maior rende um pouco mais em 2026.")
P_("")
P_("Estrategias de tendencia (Win, Win_c1, Cinco, Desloc) tem saida dinamica (canal, esticada, stop que persegue a media, zera 18:20): nao da' para alargar alvo/stop sem reescrever a estrategia. Teste possivel: stop-teto extra de s x ATR M5 nas entradas de nota baixa (sai no teto se ele disparar antes da saida original; dispara antes em 22-62% das entradas conforme s):")
P_("| score | base R$2 (4 estrategias, sem Win_c1) | walk-forward | percentil no sorteio |")
P_("|---|---|---|---|")
for k in ("logit", "nota", "tabela"):
    o = R["ores"][k]; sel = (e.iloc[t_idx].estrategia != "Win_c1").to_numpy()
    P_(f"| {k} | {R['osims'][None][sel].sum():.0f} | {o['final'][sel].sum():.0f} | {o['pct']:.0f} |")
P_("Nenhum ganho: o teto de stop so' tira operacoes que depois recuperariam, o mesmo achado de 'stop curto' ja' refutado em outras frentes.")
P_("")
P_("## Ideia 5 - ordem de chegada")
d5 = F["d5"]
P_("Classe da entrada pela posicao da OUTRA familia (tendencia x retangulo) aberta no instante: 1a (nenhuma), 2a a favor no lucro, 2a a favor no prejuizo, contra. Contagem total: " + str(e.cheg.value_counts().sort_index().to_dict()) + " (0=1a, 1=lucro, 2=prejuizo, 3=contra). R$/op bruto por metade (jan-mai | jun-out), n entre parenteses; descritivo, nao escolhe nada:")
P_("| estrategia | 1a | 2a lucro | 2a prejuizo | contra |")
P_("|---|---|---|---|---|")
for s in CART + ["Win_c1"]:
    cel = []
    for c in ["1a", "2a_lucro", "2a_prej", "contra"]:
        x = d5[(d5.estrategia == s) & (d5.classe == c)].sort_values("metade")
        cel.append(" | ".join([]) or " ; ".join(f"{('%.0f' % r.rs_op) if r.n else '-'} ({int(r.n)})" for r in x.itertuples()))
    P_(f"| {s} | " + " | ".join(cel) + " |")
P_("")
P_("Leitura: nenhuma classe mantem o mesmo sinal nas duas metades em mais de uma estrategia; os numeros grandes (ex.: +168 no WdoRet 2a no lucro, +225 no Desloc) sao n de 1 a 10. Como feature da logistica (cheg_lucro, cheg_prej) o AUC fora da amostra continuou em 0,479.")
P_("")
P_("## Ideia 6 - stop e alvo pela volatilidade esperada do horario (RetEma34)")
P_("Volatilidade esperada = mediana da amplitude (max-min das M1) da janela de 30 min do horario da entrada nos pregoes ANTERIORES (>= 10 pregoes de historico; antes disso razao 1), dividida pela mediana de todas as janelas 09-17h anteriores, limitada a [0,5; 2]. Stop e alvo multiplicados por razao^gs e razao^ga, (gs, ga) em {0; 0,5; 1}^2 = 9 celulas, a do mes m escolhida no passado (base = (0,0) = re-simulacao).")
rv = R["vsims"]
P_("R$2 de cada celula fixa no ano todo (so' orientacao, olha o futuro): " + ", ".join(f"({c[0]:g},{c[1]:g}) {v.sum():.0f}" for c, v in rv.items()))
P_(f"Walk-forward: base {rv[(0.0,0.0)].sum():.0f} -> {R['fv'].sum():.0f}; celulas escolhidas abr..out: {R['escv']}; razao embaralhada entre trades do mesmo mes (30 sorteios) p50 {np.median(R['ctrlv']):.0f}, p95 {np.percentile(R['ctrlv'],95):.0f}, percentil {(R['ctrlv'] < R['fv'].sum()).mean()*100:.0f}.")
P_("Correlacao da razao com o tamanho do movimento original |pontos|: 0,14 (fraca). A celula (0,5; 0) (so stop escalado) foi a escolhida quase todo mes e ganha no ano fixo (+778), mas esse ganho esta em jan-mar, que o walk-forward nao usa: de abril a outubro ela da -652 contra -497 da base. Sem ganho.")
P_("")
P_("## Melhor versao walk-forward e arquivos")
P_("Melhor por liquido, escolhida DEPOIS de ver o resultado (portanto otimista): RetEma34 com resize pela nota (score 'nota'): carteira R$2 " + f"{linha(v_resize, ALL, CARTM)[1]:.0f}" + " contra " + f"{linha(rs, ALL, CARTM)[1]:.0f}" + " sem filtro, mas contra " + f"{linha(v_ret, ALL, CARTM)[1]:.0f}" + " com o RetEma34 re-simulado (1,1); a diferenca entre esses dois e' efeito da re-simulacao, nao da nota. Nenhuma versao quebrou com R$1.000.")
P_("- `resultado.csv`: liquido sem custo e R$2, trades, saldo minimo e quebra por versao e escopo.")
P_("- `trades/`: no formato de `resultados/*.csv` - `*_filtro_tabela.csv` (entradas mantidas pelo filtro walk-forward da tabela; unico filtro que agiu) e `WinRetanguloEma34_resize_nota.csv` (saidas re-simuladas com o alvo/stop da celula escolhida; meses jan-mar em (1,1)).")
P_("- Codigo: `comum.py`, `run_filtro.py`, `run_saida.py`, `extrai_retema34.py`, `relatorio.py`.")
(AQ / "resultado.md").write_text("\n".join(md) + "\n", encoding="utf-8")

# ------------------------------------------------------------------ trades/
(AQ / "trades").mkdir(exist_ok=True)
cols = ["estrategia", "entrada", "saida", "lado", "qtd", "preco_entrada", "preco_saida", "motivo", "pontos", "rs"]
keep_t = res["tabela"]["keep"]
for s in ESTR:
    x = e[(est == s) & keep_t].copy(); x["qtd"] = 1.0
    x[cols].to_csv(AQ / "trades" / f"{s}_filtro_tabela.csv", index=False)

er = e.iloc[r_idx].reset_index(drop=True)
niv = pd.read_csv(AQ / "retema34_niveis.csv").set_index("t_ent")
st0 = niv.loc[er.t_entrada_ms, "stop_pts"].to_numpy(); al0 = niv.loc[er.t_entrada_ms, "alvo0_pts"].to_numpy()
sc = P["nota"][r_idx]; mm = mes[r_idx]
smul = np.ones(len(er)); amul = np.ones(len(er))
for m, (cel, thr) in R["res"]["nota"]["esc"].items():
    ma, ms = cel
    high = np.where(np.isnan(sc), True, sc >= thr)
    sel = mm == m
    amul[sel & high] = ma; smul[sel & ~high] = ms
T = lambda x: np.maximum(np.round(x / 5.0) * 5.0, 5.0)
o = S.simula_saida_lote(er.t_entrada_ms.to_numpy(), er.lado.to_numpy(), er.preco_entrada.to_numpy(), T(st0 * smul), T(al0 * amul), hora_zera="17:00", alvo_limite=True)
out = pd.DataFrame(dict(estrategia="WinRetanguloEma34", entrada=er.entrada, saida=pd.to_datetime(o.t_saida_ms.to_numpy(), unit="ms"), lado=er.lado,
                        qtd=1.0, preco_entrada=er.preco_entrada, preco_saida=o.preco_saida.to_numpy(), motivo=o.motivo.to_numpy(), pontos=o.pontos.to_numpy()))
out["rs"] = out.pontos * RS_PT
chk = out.rs.sum() - CUSTO * len(out)
print("confere resize: trades.csv R$2 =", round(chk, 1), "| pickle =", round(fin.sum(), 1), flush=True)
out[cols].to_csv(AQ / "trades" / "WinRetanguloEma34_resize_nota.csv", index=False)
print((AQ / "resultado.md").read_text(encoding="utf-8")[:200], flush=True)
