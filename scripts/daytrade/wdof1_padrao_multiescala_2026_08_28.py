"""O padrao das 4 janelas em VARIAS ESCALAS -- 1, 2, 3 e 4 dias.
Extensao pedida pelo dono, 2026-08-28.

## A ideia

`wdof1_padrao_4_janelas_2026_08_28.py` mede o padrao dentro do pregao: 4
janelas (100%, 50%, 25% e 10% do tempo decorrido), cada uma virando ALTA
ou QUEDA, maioria manda, empate 2 a 2 nao opera.

O dono propos subir um nivel: a MESMA leitura, mas com a base esticada
para 2, 3 e 4 dias. "No dia deu AAAA; em dois dias AAAA tambem, entao
compra." A tendencia de um prazo passa a ser confirmada -- ou nao -- pela
do prazo acima.

    escala 1d : as 4 janelas medidas dentro do pregao de hoje
    escala 2d : as 4 janelas medidas sobre os ultimos 2 pregoes
    escala 3d : ... 3 pregoes
    escala 4d : ... 4 pregoes

Cada escala devolve seu proprio padrao de 4 letras e sua propria direcao.
O sinal forte e' quando elas CONCORDAM.

## Detalhe que muda o resultado: janela em BARRAS, nao em relogio

Dentro de um pregao, "ultimos 50% do tempo" e "ultimas 50% das barras" sao
a mesma coisa. Atravessando dias, nao sao: entre um pregao e o outro ha
~15 horas de mercado FECHADO, e uma janela por relogio jogaria metade do
seu tamanho nesse vazio -- mediria a madrugada. Aqui a contagem e' em
BARRAS NEGOCIADAS, o que preserva o comportamento intradiario e conserta o
multi-dia.

## O desfecho nunca atravessa a noite

O robo nunca carrega posicao de um dia para o outro. Entao o desfecho (para
onde o preco foi H barras a frente) so' conta quando as H barras cabem no
MESMO pregao. Instante perto do fechamento simplesmente nao entra.

## Baseline e nulo

Os mesmos dos arquivos anteriores, pelo mesmo motivo:
- baseline: apostar SEMPRE no mesmo lado. Num periodo de alta, "so'
  comprar" acerta muito sem saber de nada; o padrao tem de bater ISSO.
- nulo: DESLOCAMENTO CIRCULAR do sinal contra os desfechos, que preserva a
  autocorrelacao dos dois e destroi so' o alinhamento. Embaralhar daria um
  nulo estreito demais.

## Janela de dados

33 pregoes do contrato WDO em vigor naquela janela (2026-07-15 a
2026-08-28, ver `SYMBOL_LABEL`/`M1` abaixo) -- o que o terminal entrega
para o contrato. As 4 escalas exigem 3 pregoes de historico, entao
sobram ~30 utilizaveis. Nao e' teste cego: este intervalo cai depois do
corte OOS do perfil, que ja foi gasto em 2026-08-26 (ver a memoria
`copa-oos-gasto-2026-08-26`). Serve para EXPLORAR, nao para confirmar.

Uso: `python -u scripts/daytrade/wdof1_padrao_multiescala_2026_08_28.py`
"""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.report import num_br  # noqa: E402

#: Nome do arquivo deliberadamente SEM o codigo de vencimento do contrato --
#: o nome nao carrega a letra do mes pra nao parecer "o mes atual" quando
#: lido meses depois. O contrato real daquele pregao esta em `SYMBOL_REAL`
#: de `wdof1_tendencia_confirmacao_2026_08_28.py`, a fonte forense de verdade.
M1 = ROOT / "data" / "raw_intraday" / "wdo_fut_2026_08_28_M1.parquet"
#: Rótulo pros prints -- derivado do NOME DO ARQUIVO acima, nunca digitado
#: de novo: se um dia este script for reaproveitado para outro contrato
#: (outro `M1`), o rótulo impresso já vem certo sozinho.
SYMBOL_LABEL = M1.stem.removesuffix("_M1")
FRACOES = (1.00, 0.50, 0.25, 0.10)
ESCALAS = (1, 2, 3, 4)          # em pregoes
MIN_BARRAS_JANELA = 3
HORIZONTES = (5, 15, 30)
N_DESLOCAMENTOS = 400
SEMENTE = 20260828


@dataclass
class Instante:
    i: int
    sessao: object
    padrao: dict[int, str] = field(default_factory=dict)      # escala -> "AAAA"
    direcao: dict[int, int] = field(default_factory=dict)     # escala -> +1/-1 (sem 0)
    desfecho: dict[int, int] = field(default_factory=dict)    # horizonte -> +1/-1/0

    @property
    def concordam(self) -> int:
        """Quantas escalas apontam para o mesmo lado que a escala de 1 dia
        (contando ela). 0 quando a escala de 1 dia nao tem direcao."""
        base = self.direcao.get(1)
        if base is None:
            return 0
        return sum(1 for d in self.direcao.values() if d == base)


def _letras(fech: np.ndarray, i: int, base: int) -> str | None:
    """As 4 letras da escala cuja janela mais longa comeca em `base`."""
    decorrido = i - base
    letras = []
    for fracao in FRACOES:
        j = i - int(round(decorrido * fracao))
        if i - j < MIN_BARRAS_JANELA or j < 0:
            return None
        delta = fech[i] - fech[j]
        if delta == 0:
            return None
        letras.append("A" if delta > 0 else "Q")
    return "".join(letras)


def direcao_do_padrao(padrao: str) -> int | None:
    altas = padrao.count("A")
    if altas == 2:
        return None                 # empate 2 a 2: nao opera
    return 1 if altas > 2 else -1


def montar(df: pd.DataFrame) -> list[Instante]:
    fech = df["close"].to_numpy(dtype=float)
    sessoes = pd.DatetimeIndex(df.index).tz_convert("America/Sao_Paulo").date
    # indice da PRIMEIRA barra de cada pregao, na ordem
    inicios: list[int] = []
    for k, s in enumerate(sessoes):
        if k == 0 or s != sessoes[k - 1]:
            inicios.append(k)
    fim_da_sessao = {}
    for n, ini in enumerate(inicios):
        fim_da_sessao[n] = (inicios[n + 1] - 1) if n + 1 < len(inicios) else len(fech) - 1
    sessao_da_barra = np.empty(len(fech), dtype=int)
    for n, ini in enumerate(inicios):
        sessao_da_barra[ini:fim_da_sessao[n] + 1] = n

    instantes: list[Instante] = []
    for i in range(len(fech)):
        n = int(sessao_da_barra[i])
        inst = Instante(i=i, sessao=sessoes[i])
        for escala in ESCALAS:
            if n - (escala - 1) < 0:
                continue            # nao ha historico suficiente
            base = inicios[n - (escala - 1)]
            letras = _letras(fech, i, base)
            if letras is None:
                continue
            inst.padrao[escala] = letras
            d = direcao_do_padrao(letras)
            if d is not None:
                inst.direcao[escala] = d
        if 1 not in inst.padrao:
            continue                # sem a leitura do dia nao ha decisao
        limite = fim_da_sessao[n]
        for h in HORIZONTES:
            if i + h > limite:
                continue            # o desfecho NUNCA atravessa a noite
            delta = fech[i + h] - fech[i]
            inst.desfecho[h] = 0 if delta == 0 else (1 if delta > 0 else -1)
        if inst.desfecho:
            instantes.append(inst)
    return instantes


# ---------------------------------------------------------------------------

def taxa(sinais: np.ndarray, movs: np.ndarray) -> tuple[float, int]:
    valido = (sinais != 0) & (movs != 0)
    if not valido.any():
        return 0.0, 0
    return 100.0 * float((sinais[valido] == movs[valido]).mean()), int(valido.sum())


def com_nulo(sinais: np.ndarray, movs: np.ndarray) -> tuple[float, int, float, float, float]:
    real, n = taxa(sinais, movs)
    rng = random.Random(SEMENTE)
    nulos = sorted(taxa(np.roll(sinais, rng.randrange(1, len(sinais))), movs)[0]
                   for _ in range(N_DESLOCAMENTOS))
    p = (sum(1 for x in nulos if x >= real) + 1) / (len(nulos) + 1)
    return real, n, nulos[int(0.05 * len(nulos))], nulos[int(0.95 * len(nulos))], p


def linha(rotulo: str, sinais, movs, largura: int = 34) -> None:
    real, n, p05, p95, p = com_nulo(np.array(sinais), np.array(movs))
    fixo_alta = 100.0 * sum(1 for m in movs if m > 0) / max(1, sum(1 for m in movs if m != 0))
    melhor_fixo = max(fixo_alta, 100 - fixo_alta)
    marca = "ACIMA do acaso" if p <= 0.05 else "dentro do acaso"
    if real <= melhor_fixo:
        marca += " / pior que lado fixo"
    print(f"{rotulo:<{largura}} {n:>6,} {num_br(real, 1) + '%':>8} "
          f"{num_br(melhor_fixo, 1) + '%':>10} "
          f"{'[' + num_br(p05, 1) + ' , ' + num_br(p95, 1) + ']':>18} "
          f"{num_br(p, 3):>7}  {marca}")


def cabecalho(titulo: str, largura: int = 34) -> None:
    print(f"\n{titulo}")
    print(f"{'':<{largura}} {'n':>6} {'acerto':>8} {'lado fixo':>10} "
          f"{'acaso 5-95%':>18} {'p':>7}  veredito")
    print("-" * (largura + 55))


def main() -> None:
    if not M1.exists():
        raise SystemExit(f"[multiescala] falta {M1} -- rode o cache do M1 primeiro.")
    df = pd.read_parquet(M1)
    instantes = montar(df)
    sessoes = sorted({i.sessao for i in instantes})

    print("=" * 108)
    print(f"PADRAO das 4 janelas em MULTIPLAS ESCALAS -- {SYMBOL_LABEL} M1")
    print("=" * 108)
    print(f"{len(df):,} barras | {len(sessoes)} pregoes com decisao "
          f"({sessoes[0]} a {sessoes[-1]}) | {len(instantes):,} instantes")
    print("Escalas: 1d (dentro do pregao), 2d, 3d, 4d -- mesma leitura, base maior.")
    print("Janelas contadas em BARRAS NEGOCIADAS (relogio jogaria metade da janela")
    print("no mercado fechado). Desfecho nunca atravessa a noite.")
    print("ATENCAO: intervalo posterior ao corte OOS ja gasto -- exploracao, nao teste cego.")

    for h in HORIZONTES:
        cabecalho(f"### desfecho em {h} barras a frente")
        movs_all, sin_all = [], []
        for inst in instantes:
            if h in inst.desfecho and 1 in inst.direcao:
                movs_all.append(inst.desfecho[h])
                sin_all.append(inst.direcao[1])
        linha("so' a escala de 1 dia (baseline)", sin_all, movs_all)

        for k in (2, 3, 4):
            sin, mov = [], []
            for inst in instantes:
                if h not in inst.desfecho or 1 not in inst.direcao:
                    continue
                mov.append(inst.desfecho[h])
                sin.append(inst.direcao[1] if inst.concordam >= k else 0)
            linha(f"1d + pelo menos {k - 1} escala(s) junto", sin, mov)

        sin, mov = [], []
        for inst in instantes:
            if h not in inst.desfecho or 1 not in inst.direcao:
                continue
            mov.append(inst.desfecho[h])
            mesmo = (inst.padrao.get(2) == inst.padrao.get(1))
            sin.append(inst.direcao[1] if mesmo else 0)
        linha("1d e 2d com o MESMO padrao exato", sin, mov)

    # --- os tres padroes que o dono elegeu, agora com 30 pregoes ------------
    print("\n" + "=" * 108)
    print("Os padroes da escala de 1 dia, sobre todos os pregoes (desfecho 5 barras)")
    print("=" * 108)
    h = 5
    por_padrao: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for inst in instantes:
        if h in inst.desfecho and 1 in inst.direcao:
            por_padrao[inst.padrao[1]].append((inst.direcao[1], inst.desfecho[h]))
    contagem = Counter({p: len(v) for p, v in por_padrao.items()})
    print(f"{'padrao':>8} {'aposta':>8} {'n':>7} {'acerto':>8}   (so padroes com n >= 50)")
    print("-" * 60)
    for padrao, _n in contagem.most_common():
        pares = por_padrao[padrao]
        if len(pares) < 50:
            continue
        val = [(s, m) for s, m in pares if m != 0]
        acc = 100.0 * sum(1 for s, m in val if s == m) / len(val) if val else 0.0
        aposta = "compra" if direcao_do_padrao(padrao) == 1 else "venda"
        print(f"{padrao:>8} {aposta:>8} {len(val):>7,} {num_br(acc, 1) + '%':>8}")
    ignorados = sum(n for p, n in contagem.items() if n < 50)
    print(f"\n({ignorados:,} instantes em padroes com n < 50, nao mostrados)")

    # --- por que UM pregao nao provava nada ---------------------------------
    print("\n" + "=" * 108)
    print("Acerto PREGAO A PREGAO (desfecho 15 barras) -- a dispersao e' a licao")
    print("=" * 108)
    por_dia: dict[object, list[tuple[int, int]]] = defaultdict(list)
    for inst in instantes:
        if 15 in inst.desfecho and inst.desfecho[15] != 0 and 1 in inst.direcao:
            por_dia[inst.sessao].append((inst.direcao[1], inst.desfecho[15]))
    taxas = []
    for dia, pares in por_dia.items():
        if len(pares) < 50:
            continue
        taxas.append((100.0 * sum(1 for s, m in pares if s == m) / len(pares), dia, len(pares)))
    taxas.sort(reverse=True)
    print(f"{len(taxas)} pregoes com pelo menos 50 decisoes resolvidas\n")
    print(f"{'posicao':>8} {'pregao':>12} {'n':>6} {'acerto':>8}")
    print("-" * 40)
    for pos, (acc, dia, n) in enumerate(taxas, 1):
        if pos <= 3 or pos > len(taxas) - 3 or str(dia) == "2026-08-28":
            marca = "  <- o dia que medimos primeiro" if str(dia) == "2026-08-28" else ""
            print(f"{pos:>8} {str(dia):>12} {n:>6,} {num_br(acc, 1) + '%':>8}{marca}")
        elif pos == 4:
            print(f"{'...':>8}")
    valores = [t[0] for t in taxas]
    print(f"\nmediana {num_br(sorted(valores)[len(valores) // 2], 1)}%  |  "
          f"pior {num_br(min(valores), 1)}%  |  melhor {num_br(max(valores), 1)}%")
    print("Escolher UM pregao e concluir dele e' escolher uma posicao nesta lista.")


if __name__ == "__main__":
    main()
