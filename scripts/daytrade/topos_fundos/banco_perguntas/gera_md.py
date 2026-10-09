import numpy as np, pandas as pd, catalogo as K, soma
T = pd.read_pickle("resultado.pkl"); Z = soma.Z

def esc(s): return str(s).replace("|", "/")
# ---- catalogo
L = ["# Catálogo de perguntas (WIN M15) — novas (N01–N50) e existentes medidas (C, T, D, Q)", "",
     "Resposta esperada = a que, segundo a literatura/o arquivo, favorece a COMPRA (venda = espelho: preços invertidos). Só velas fechadas até a vela da pergunta; ATR diário até D-1. "
     "'sem lado' = pergunta que descreve o regime e não a direção (no alvo simétrico não pode separar nada; serve só como modificador).", "",
     "| # | origem | pergunta | família | régua (WIN M15) | tipo | esperada (compra) | fonte / justificativa | peso IS | classe |", "|---|---|---|---|---|---|---|---|---|---|"]
for r in K.R:
    t = T.loc[r["id"]]
    L.append(f"| {r['id']} | {r['origem']} | {esc(r['texto'])}{'' if r['lado'] else ' (sem lado)'} | {esc(r['fam'])} | {esc(r['regua'])} | {r['tipo']} | {r['esperada']} | {esc(r['fonte'])} | {t.peso:+.3f} | {t.classe} |")
L += ["", "## Perguntas do arquivo PERGUNTAS_DE_OPERACAO.md sem régua de preço/volume (marcadas 'sem dado' ou sem resposta objetiva)", "",
      "| # | motivo |", "|---|---|",
      "| Q20, Q22, Q29, Q30, Q36, Q37, Q47–Q53 | introspecção do operador / hábito / emoção: sem dado |",
      "| Q41 | calendário de eventos e notícias: sem dado (substituto medido: Q19, vela/volume anormais) |",
      "| Q44 | dias parecidos com hoje: é um método (vizinhança), não uma pergunta de resposta única |",
      "| Q21 | diário × M1: coberta por N19/N20/N21 |", "| Q17, Q35 | força da perna: coberta por N46 |",
      "| Q15 | referências do dia/semana/mês: cobertas por C2, N16, N17, N48 |", "| Q25, Q28 | oscilador extremo / divergência: D6, N41, N42 |",
      "| Q31, Q38 | figura/falha de rompimento: N10, N35, T2 (figuras já refutadas no projeto) |", "| Q34 | padrão de vela: refutado no projeto, não remedido |",
      "| Q43 | leilões: já removidos da base |", "| Q39/Q40/D9/D10 | horário: Q39, D9 (sem lado), e o bloco 0 por hora |",
      "| D1 | = T1; D2–D5 = C1–C4; D6/D7 = D6, D7; D8 (posição aberta) e D9 são regras de execução; D10 = Q39 / hora; D12 = T2; D13 = D13 |"]
open("catalogo_perguntas.md", "w", encoding="utf-8").write("\n".join(L) + "\n")

# ---- medicao
ordem = {"BOA": 0, "FRACA": 1, "INSTÁVEL": 2, "INERTE": 3, "SEM AMOSTRA": 4}
X = T.copy(); X["o"] = X.classe.map(ordem); X["a"] = -X.lift_OOS.abs().fillna(0); X = X.sort_values(["o", "a"])
M = ["# Medição no mercado (alvo: +1 ATR M15 antes de −1 ATR, até o fim do pregão; compra e venda juntas)", "",
     "IS 2022-01→2025-09 (pesos) · OOS 2025-10→2026-10-05 · virgem 2021-10→12. Base = 50,0% por construção (compra e venda do mesmo instante somam 1). Lift em pontos percentuais. "
     "p = embaralhamento de DIAS (2.000×) · BH q=0,10 sobre as 81 perguntas.", "",
     "| # | origem | pergunta | freq OOS % | acerto OOS % | lift IS pp | lift OOS pp | lift virgem pp | peso | p IS | p OOS | classe |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for i, t in X.iterrows():
    M.append(f"| {i} | {t.origem} | {esc(t.texto)}{'' if t.lado else ' (sem lado)'} | {100*t.freq_OOS:.1f} | {100*t.acerto_OOS:.1f} | {100*t.lift_IS:+.2f} | {100*t.lift_OOS:+.2f} | {100*t.lift_virgem:+.2f} | {t.peso:+.3f} | {t.p_IS:.3f} | {t.p_OOS:.3f} | {t.classe} |")
open("medicao_perguntas.md", "w", encoding="utf-8").write("\n".join(M) + "\n")

# ---- 10 melhores (nao redundantes)
c = T[(T.lado) & (T.classe.isin(["FRACA", "BOA"])) & (np.sign(T.lift_IS) == np.sign(T.lift_OOS))].copy()
c["chave"] = np.minimum(c.lift_IS.abs(), c.lift_OOS.abs())
c = c.sort_values("chave", ascending=False)
ids = list(c.index); z = Z["OOS"]; E = z["elig"]
Mx = {i: (z[i] == soma.EXP[i])[E].reshape(-1).astype(float) for i in ids}
sel = []
for i in ids:
    if all(abs(np.corrcoef(Mx[i], Mx[j])[0, 1]) < 0.5 for j in sel): sel.append(i)
    if len(sel) == 10: break
top = T.loc[sel, ["texto", "tipo", "esperada", "lift_IS", "lift_OOS", "lift_virgem", "peso", "p_OOS", "classe"]]
top.to_pickle("top10.pkl")
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
print(top.assign(lift_IS=100*top.lift_IS, lift_OOS=100*top.lift_OOS, lift_virgem=100*top.lift_virgem).round(3).to_string())
print(T.classe.value_counts())
print(T[T.origem == "nova"].classe.value_counts(), T[T.origem == "existente"].classe.value_counts())
