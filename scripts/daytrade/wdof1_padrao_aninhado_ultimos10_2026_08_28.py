"""Padrao ANINHADO dentro dos ultimos 10% do pregao -- pedido do dono,
2026-08-28. Foco EXCLUSIVO em AAAA.

## A ideia

Dia inteiro, multi-dia e semana foram refutados; momento curto (10/5/2/1
barras fixas) nao achou edge no dia mais dificil. O dono propos outra
coisa: talvez a QUANTIDADE de historico usada para detectar o padrao seja
o que importa -- nem o pregao inteiro (dilui), nem so' 1 barra (ruido
puro). Pegar os ULTIMOS 10% do pregao (a mesma janela `t4` de sempre) e,
DENTRO dela, rodar de novo a mesma analise de 4 janelas (100%/50%/25%/10%
-- agora fracoes DESSA janela menor, nao do pregao inteiro).

Isto e' literalmente recursivo: `_letras(fech, i, base)` (de
`wdof1_padrao_multiescala_2026_08_28.py`) ja e' generica em `base` --
antes `base` era o inicio do PREGAO; aqui e' o inicio dos ultimos 10% do
pregao. So' isso muda.

**Foco exclusivo em AAAA** (pedido explicito do dono): nao no "3 de 4" nem
no espelho QQQQ -- so' quando as 4 sub-janelas, TODAS dentro dos ultimos
10% do dia, concordam em ALTA.

## As duas comparacoes que respondem "quantidade importa?"

1. **bruto vs aninhado.** `t4` sozinho (so' compara o preco de agora com o
   inicio dos ultimos 10%, 1 numero) contra AAAA aninhado (exige que as 4
   sub-janelas DENTRO desse mesmo pedaco concordem). Se aninhado nao bate
   o bruto, exigir mais confirmacao dentro da mesma janela nao ajudou.
2. **estratificado por TAMANHO da janela.** Os ultimos 10% de um pregao
   sao poucas barras as 10h e muitas as 16h -- e' a propria "quantidade"
   que o dono quer testar. Terços por quantidade de barras disponiveis na
   janela aninhada: se o efeito so' aparece quando ha' MAIS barras (ou so'
   quando ha' MENOS), isso e' a resposta direta a pergunta.

## Desfecho e disciplina

Horizonte fixo em 30 barras (convencao ja' estabelecida), nunca atravessa
a noite. Rodado nos 33 pregoes inteiros -- nao em 1 dia escolhido a dedo
--, e fecha com a dispersao PREGAO a PREGAO do proprio sinal AAAA, porque
foi exatamente essa tabela que revelou, na rodada de dia inteiro, que 1
pregao sozinho enganava.

Uso: `python -u scripts/daytrade/wdof1_padrao_aninhado_ultimos10_2026_08_28.py`
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402
from wdof1_padrao_multiescala_2026_08_28 import (  # noqa: E402
    M1,
    MIN_BARRAS_JANELA,
    _letras,
)
from wdof1_padrao_semana_2026_08_28 import HORIZONTE  # noqa: E402

FRACAO_EXTERNA = 0.10   # "os ultimos 10% do pregao" -- a mesma janela t4 de sempre
N_DESLOCAMENTOS = 400
SEMENTE = 20260828


def null_de_selecao(mask: np.ndarray, movs: np.ndarray
                     ) -> tuple[float, int, float, float, float]:
    """Nulo por deslocamento circular da SELECAO (nao da aposta).

    As linhas "bruto=ALTA"/"aninhado=AAAA" ja' sao filtradas para so'
    conter apostas de COMPRA -- o vetor de sinal e' uma lista constante de
    1s. Girar uma constante no tempo devolve a MESMA constante: o nulo de
    `com_nulo` (que gira o SINAL) fica degenerado e da' p=1,000 sempre,
    nao porque o resultado seja ruim, mas porque o teste esta' errado
    para este caso -- bug meu, pego antes de reportar.

    Aqui gira-se a MASCARA de selecao (quais instantes o padrao escolheu)
    contra a serie INTEIRA de desfechos. Isso testa a pergunta certa:
    "um recorte do MESMO TAMANHO, em instantes deslocados no tempo (nao
    escolhidos pelo padrao), acerta tanto quanto?" -- preserva a
    autocorrelacao de ambos os lados e destroi so' o alinhamento entre
    selecao e desfecho, mesmo espirito do deslocamento usado nos scripts
    anteriores."""
    real = 100.0 * float((movs[mask] == 1).mean()) if mask.any() else 0.0
    rng = random.Random(SEMENTE)
    n = len(movs)
    nulos = []
    for _ in range(N_DESLOCAMENTOS):
        k = rng.randrange(1, n)
        m2 = np.roll(mask, k)
        if m2.any():
            nulos.append(100.0 * float((movs[m2] == 1).mean()))
    nulos.sort()
    p = (sum(1 for x in nulos if x >= real) + 1) / (len(nulos) + 1)
    p05, p95 = nulos[int(0.05 * len(nulos))], nulos[int(0.95 * len(nulos))]
    return real, int(mask.sum()), p05, p95, p


@dataclass
class Instante:
    i: int
    sessao: object
    qtd_janela: int          # barras dentro dos ultimos 10% do dia, ate `i`
    bruto: int                # +1/-1 -- so' compara agora contra o inicio da janela
    padrao_aninhado: str | None
    desfecho: int              # sempre +1/-1


def montar(df: pd.DataFrame) -> tuple[list[Instante], int]:
    fech = df["close"].to_numpy(dtype=float)
    idx = pd.DatetimeIndex(df.index).tz_convert("America/Sao_Paulo")
    sessoes = idx.date

    inicios: list[int] = []
    for k, s in enumerate(sessoes):
        if k == 0 or s != sessoes[k - 1]:
            inicios.append(k)
    n_sessoes = len(inicios)
    fim_da_sessao = {}
    for n, ini in enumerate(inicios):
        fim_da_sessao[n] = (inicios[n + 1] - 1) if n + 1 < n_sessoes else len(fech) - 1
    sessao_da_barra = np.empty(len(fech), dtype=int)
    for n, ini in enumerate(inicios):
        sessao_da_barra[ini:fim_da_sessao[n] + 1] = n

    instantes: list[Instante] = []
    for i in range(len(fech)):
        n = int(sessao_da_barra[i])
        dia_start = inicios[n]
        decorrido_dia = i - dia_start
        base10 = i - int(round(decorrido_dia * FRACAO_EXTERNA))
        if i - base10 < MIN_BARRAS_JANELA:
            continue                    # quantidade insuficiente nos ultimos 10% do dia
        if fech[i] == fech[base10]:
            continue                    # janela bruta sem direcao
        bruto = 1 if fech[i] > fech[base10] else -1
        padrao_aninhado = _letras(fech, i, base10)

        limite = fim_da_sessao[n]
        if i + HORIZONTE > limite:
            continue                    # o desfecho NUNCA atravessa a noite
        delta_out = fech[i + HORIZONTE] - fech[i]
        if delta_out == 0:
            continue
        instantes.append(Instante(
            i=i, sessao=sessoes[i], qtd_janela=i - base10, bruto=bruto,
            padrao_aninhado=padrao_aninhado,
            desfecho=1 if delta_out > 0 else -1,
        ))
    return instantes, n_sessoes


def main() -> None:
    if not M1.exists():
        raise SystemExit(f"[aninhado] falta {M1} -- rode o cache do M1 primeiro.")
    df = pd.read_parquet(M1)
    instantes, n_sessoes = montar(df)

    print("=" * 108)
    print("PADRAO ANINHADO dentro dos ULTIMOS 10% do pregao -- foco em AAAA")
    print("=" * 108)
    print("Fora: os ultimos 10% do pregao inteiro (a janela t4 de sempre).")
    print("Dentro: a MESMA analise de 4 janelas (100/50/25/10%), agora fracao DESSA janela.")
    print(f"{n_sessoes} pregoes | {len(instantes):,} instantes com quantidade suficiente "
          f"nos ultimos 10% | desfecho fixo em {HORIZONTE} barras")

    aaaa = [i for i in instantes if i.padrao_aninhado == "AAAA"]
    bruto_alta = [i for i in instantes if i.bruto == 1]
    print(f"\nbruto=ALTA (sem refinar): {len(bruto_alta):,}  |  "
          f"aninhado=AAAA (refinado): {len(aaaa):,}")

    print("\n--- bruto vs aninhado -- 'quantidade extra de confirmacao' ajuda? ---")
    print("(nulo por deslocamento da SELECAO, nao do sinal -- ver docstring de "
          "`null_de_selecao`)")
    movs_todos = np.array([i.desfecho for i in instantes])
    mask_bruto = np.array([i.bruto == 1 for i in instantes])
    mask_aaaa = np.array([i.padrao_aninhado == "AAAA" for i in instantes])

    cab = (f"{'':<38} {'n':>6} {'acerto':>8} {'lado fixo':>10} "
           f"{'acaso 5-95%':>18} {'p':>7}  veredito")
    print(cab)
    print("-" * len(cab))
    lado_fixo = 100 * float((movs_todos == 1).mean())
    for rotulo, mask in (("t4 bruto = ALTA (sem refinar)", mask_bruto),
                        ("aninhado = AAAA (refinado, so' este)", mask_aaaa)):
        real, n, p05, p95, p = null_de_selecao(mask, movs_todos)
        marca = "ACIMA do acaso" if p <= 0.05 else "dentro do acaso"
        if real <= lado_fixo:
            marca += " / pior que apostar sempre em ALTA"
        print(f"{rotulo:<38} {n:>6,} {num_br(real, 1) + '%':>8} "
              f"{num_br(lado_fixo, 1) + '%':>10} "
              f"{'[' + num_br(p05, 1) + ' , ' + num_br(p95, 1) + ']':>18} "
              f"{num_br(p, 3):>7}  {marca}")

    print("\n--- AAAA estratificado por TAMANHO da janela (a 'quantidade' em si) ---")
    if len(aaaa) >= 9:
        qtds = np.array([i.qtd_janela for i in aaaa])
        cortes = np.quantile(qtds, [1 / 3, 2 / 3])
        baixo = [i for i in aaaa if i.qtd_janela <= cortes[0]]
        medio = [i for i in aaaa if cortes[0] < i.qtd_janela <= cortes[1]]
        alto = [i for i in aaaa if i.qtd_janela > cortes[1]]
        print(f"cortes (terços): <= {num_br(cortes[0], 0)} barras | "
              f"<= {num_br(cortes[1], 0)} barras | acima")
        for rotulo, sub in (("pouca quantidade", baixo), ("media quantidade", medio),
                            ("muita quantidade", alto)):
            if not sub:
                continue
            acc = 100 * sum(1 for i in sub if i.desfecho == 1) / len(sub)
            qmin = min(i.qtd_janela for i in sub)
            qmax = max(i.qtd_janela for i in sub)
            print(f"  {rotulo:<18} n={len(sub):>5,}  janela [{qmin}-{qmax}] barras  "
                  f"acerto={num_br(acc, 1)}%")
    else:
        print("(poucas ocorrencias de AAAA para estratificar por quantidade)")

    print("\n--- AAAA, pregao a pregao (so' sessoes com n >= 5) -- a dispersao real ---")
    por_dia: dict[object, list[Instante]] = {}
    for inst in aaaa:
        por_dia.setdefault(inst.sessao, []).append(inst)
    linhas = []
    for dia, sub in sorted(por_dia.items()):
        if len(sub) < 5:
            continue
        acc = 100 * sum(1 for i in sub if i.desfecho == 1) / len(sub)
        linhas.append((dia, len(sub), acc))
    print(f"{'pregao':>12} {'n':>5} {'acerto':>8}")
    print("-" * 28)
    for dia, n, acc in linhas:
        print(f"{str(dia):>12} {n:>5} {num_br(acc, 1) + '%':>8}")
    if linhas:
        valores = sorted(a for _, _, a in linhas)
        print(f"\n{len(linhas)} pregoes com AAAA suficiente | mediana "
              f"{num_br(valores[len(valores) // 2], 1)}%  |  pior "
              f"{num_br(valores[0], 1)}%  |  melhor {num_br(valores[-1], 1)}%")


if __name__ == "__main__":
    main()
