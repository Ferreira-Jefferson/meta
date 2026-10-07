"""Gera CONGELADAS.md (SHA-256 dos scripts e dos dados de entrada + regras + protocolo do VAL). Rodar ANTES do VAL."""
import hashlib
from pathlib import Path
import pandas as pd

AQ = Path(__file__).resolve().parent
C = AQ.parents[1]; B = C.parent; V0 = AQ.parent / "v0"
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
arq = {"v1_regras.py (as 13 regras)": AQ / "v1_regras.py", "v1_val.py (execucao do VAL)": AQ / "v1_val.py",
       "v1_2026.py (etapa 2026)": AQ / "v1_2026.py", "v1_niveis_val.py": AQ / "v1_niveis_val.py",
       "a_consenso/consenso_filtro.py": C / "a_consenso/consenso_filtro.py", "a_consenso/consenso_gatilho.py": C / "a_consenso/consenso_gatilho.py",
       "b_nota/comum.py": C / "b_nota/comum.py", "e_saida_virada/virada.py": C / "e_saida_virada/virada.py",
       "f0_fundacao/saida.py": C / "f0_fundacao/saida.py", "port_win.py (importado por consenso_gatilho)": B / "port_win.py",
       "port_retangulo_ema34.py (niveis do C12)": B / "port_retangulo_ema34.py", "dados.py": B / "dados.py",
       "v0/dados_val.py": V0 / "dados_val.py", "v0/votos_val.parquet": V0 / "votos_val.parquet",
       "v0/eventos_val.parquet": V0 / "eventos_val.parquet", "v1/retema34_niveis_val.csv": AQ / "retema34_niveis_val.csv",
       "v1/filtro_2026.csv": AQ / "filtro_2026.csv"}
for r in ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]:
    arq[f"v0/resultados/{r}.csv"] = V0 / "resultados" / f"{r}.csv"
hs = "\n".join(f"| `{k}` | `{h(v)}` |" for k, v in arq.items())
f = pd.read_csv(AQ / "filtro_2026.csv")


def tab(df):
    return "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False))


cols = f[["id", "robo", "regra", "liq2_sem_wdo", "liq2_original", "delta_sem_wdo", "criterio", "segue"]].fillna("-")
txt = f"""# V1 — candidatas CONGELADAS (escrito em 2026-10-06 ANTES de rodar o VAL)

## Etapa 1 (2026) — reprodução com o WdoRetangulo e filtro do pré-registro
Reprodução COM o WdoRetangulo contra o CSV da frente (linhas idênticas por entrada/saída/lado/rs ÷ linhas do CSV): **13/13 candidatas reproduzem 100%** (C1 146/146, C2 292/292, C3 35/35, C4 56/56, C5-C7 181/181, C8-C9 308/308, C10-C11 65/65, C12 733/733, C13 426/426; mesmo número de operações).
O `WdoRetangulo.csv` foi apagado de `resultados/` (exclusão do dono); para o E (que lê as posições de todos os votantes) ele foi reconstruído das próprias operações em `f0_fundacao/eventos.parquet` (`v1/_base_com_wdo/`), só para a prova de reprodução.

Filtro (líquido com R$2/op, janela 2026; variante: Δ > 0 contra o próprio original; nova: > R$841):

| id | robô | regra | líq. sem Wdo | líq. original | Δ | critério | segue |
|---|---|---|---|---|---|---|---|
{tab(cols)}

**Seguem para o VAL (10):** C1, C4, C5, C7, C8, C9, C10, C11, C12, C13. **Caem em 2026 sem o WdoRetangulo (3):** C2 (Δ −258), C3 (Δ −883), C6 (Δ −90).
Observação declarada: sem o WdoRetangulo a "outra família" dos robôs de tendência é só o WinRetanguloEma34, então **C5 (V2b) e C7 (V1b) viram a MESMA regra** (mesmas 181 operações, mesmo Δ). Os dois entram no VAL e no Holm como candidatas separadas, como o pré-registro lista; o resultado dos dois é idêntico por construção. C8–C11 (V3, outro membro da própria família) não dependem do WdoRetangulo e ficam iguais ao original das frentes.

## Regras congeladas (as 13 funções estão em `v1_regras.py`; cada uma é a regra da frente, sem mexer em parâmetro nem grade)
| id | robô | regra da frente |
|---|---|---|
| C1 | Win_c1 | B, filtro "entra ou não" pela tabela de frequência (fav 0–3), limiar walk-forward, MES_MIN_FILTRO=4 |
| C2 | WinCincoMedias | A1, filtro de consenso, variante comum ao conjunto (9 variantes, melhor do passado, padrão `maj`) |
| C3 | WinDeslocamentoMatinal | A1, escolha individual |
| C4 | WinDeslocamentoMatinal | A1, variante comum |
| C5 | Win | E V2b (qualquer um da outra família contra, só no lucro) |
| C6 | Win | E V1a |
| C7 | Win | E V1b |
| C8 | WinCincoMedias | E V3b |
| C9 | WinCincoMedias | E V3a |
| C10 | WinDeslocamentoMatinal | E V3a |
| C11 | WinDeslocamentoMatinal | E V3b |
| C12 | WinRetanguloEma34 | B resize pela nota (modelo `nota`, grade 3x3 de alvo/stop, mediana do passado) |
| C13 | ConsensoGatilho | A2 gatilho (≥3 votos, ≥1 de cada família; stop e alvo em múltiplos de ATR M5 {{1,2,3}} x {{1,2,3}}, célula do passado) |

Votantes sem o WdoRetangulo: Win, WinCincoMedias, WinDeslocamentoMatinal (T) e WinRetanguloEma34 (R). C13 passa a exigir 3 dos 4 (≥1 T, e o WinRetanguloEma34 obrigatório).

## Execução no VAL (2024-07-01 → 2025-09-30), fixada antes
- Walk-forward: mesmo laço das frentes, com o mês sendo a chave sequencial ano*12+mês; o passado é expansivo e inclui 2024-01..06. Janela aplicada: 2024-07..2025-09 (15 meses). C12: modelo `nota` treinado nos meses anteriores; com <20 eventos de RetEma34 no passado fora da amostra ele fica na célula (1,1), como na frente.
- Operações: as do robô com **entrada** na janela. Meses/trimestres das tabelas pela data de **saída**. Trimestres: 2024T3, 2024T4, 2025T1, 2025T2, 2025T3 (5).
- Δ = Σ(rs − R$2) da candidata − Σ(rs − R$2) do original do mesmo robô na janela, **sem truncar na quebra** (os robôs operam sem parar por saldo). Para as saídas (E) o número de operações não muda, então Δ com custo = Δ sem custo.
- Capital R$1.000 corrido por ordem de saída, a partir de 2024-07-01. Quebra = saldo ≤ 0 em algum ponto (data marcada, a curva segue). Maior queda = máx(pico − saldo), com pico inicial R$1.000. Fator de recuperação = líquido com custo ÷ maior queda. Fator de lucro = Σganhos ÷ Σperdas (líquido de custo). Payoff = ganho médio ÷ perda média (líquido de custo). Acerto = % de operações com líquido > 0.
- **Teste, unilateral, 2.000 sorteios, semente 20261006**, p = (1 + nº de sorteios com Δ_sorteio ≥ Δ_real) ÷ 2001:
  - filtros (C1, C4): sorteio mantém ao acaso, entre as entradas do original na janela, o MESMO número de operações que a candidata manteve (mesma fração cortada);
  - saídas (C5, C7–C11): `virada.sorteio_instante` — permuta, entre as operações disparadas, o instante da saída (mesmo nº de saídas antecipadas, mesma distribuição de tempo desde a entrada; nas (b) só vale se estiver no lucro);
  - resize (C12): a regra da frente — o escore da nota é trocado por uniforme sorteado e a mesma escolha walk-forward é refeita (célula escolhida no passado com o escore sorteado); Δ contra o original;
  - nova (C13): sorteio de lado nos MESMOS gatilhos (mesmo horário), com a mesma célula de stop/alvo do mês da candidata; compara o líquido com custo da candidata com o do sorteio.
- Holm sobre o conjunto que chegou ao VAL (10 candidatas), α = 0,05. (O pré-registro dizia 13; a lista que segue é a regra dada pelo pedido. O Holm com m = 13 também é reportado, sem mudar a classificação principal.)
- Classificação, exatamente pelo pré-registro. Variante: APROVADA = Δ>0 e p Holm<0,05; PROMISSORA = Δ>0, fator de recuperação maior que o do original e p bruto<0,10, sem passar no Holm; REFUTADA = o resto. Nova (C13): APROVADA se líquido com custo > o do pior original no VAL (menor líquido com custo entre os 5 robôs), sem quebra, fator de lucro ≥ 1,2, ≥3 de 5 trimestres positivos, p bruto ≤ 0,05 (percentil ≥95) **e** p Holm<0,05; senão REFUTADA. (Leitura estrita; a leitura só com p bruto ≤0,05 também é reportada.)

## SHA-256 (conferidos no momento do congelamento)
| arquivo | sha256 |
|---|---|
{hs}
"""
(AQ / "CONGELADAS.md").write_text(txt, encoding="utf-8")
print("ok", len(txt))
