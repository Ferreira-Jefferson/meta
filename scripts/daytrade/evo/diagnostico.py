"""VIGIA da rodada em curso -- procura o que invalidaria o treinamento.

Existe porque uma rodada de 9,5h so' entrega resultado no fim, e ate' aqui
TRES defeitos so' apareceram quando ja' havia horas gastas: o fitness rotulado
com unidade errada, a premissa evaporando por falta de restricao estrutural, e
o piso de amostra por bloco virando penhasco de 940 pontos. Nenhum dos tres
faria o processo quebrar -- todos produziriam numeros perfeitamente formatados
e sem sentido.

Por isso o vigia nao pergunta "esta' rodando?" (isso o log responde), e sim
"o que esta' rodando ainda mede alguma coisa?". Cada checagem abaixo e' um
modo de falha que ja' aconteceu ou que a busca encontraria sozinha:

  * POPULACAO CONGELADA -- fitness identico por varias geracoes seguidas. Com
    elitismo e populacao pequena, uma ilha pode virar clone do mesmo
    ancestral; as geracoes seguintes rodam, custam tempo e nao procuram nada.
  * FAIXA UNICA -- 100% da populacao morta ou 100% sem amostra. Ai' o torneio
    compara empates e a selecao vira sorteio, que e' o oposto de evoluir.
  * MENSURAVEL ENCOLHENDO -- a fracao da populacao com amostra caindo ao longo
    das geracoes. E' a assinatura da busca fugindo de operar, que e' o otimo
    degenerado deste desenho (quem nao opera nao morre).
  * PREMISSA VAZANDO -- campeao sem o minimo de encaixes no nucleo da especie.
    Invariante estrutural; se falhar, a ilha deixou de ser o que dizia ser.
  * CONVERGENCIA ENTRE ILHAS -- campeoes de ilhas diferentes olhando as mesmas
    features. Dez ilhas iguais nao sao dez buscas: pagam o custo estatistico
    de dez tentativas e entregam a diversidade de uma.

Uso:
    python scripts/daytrade/evo/diagnostico.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
for _p in (RAIZ / "src", RAIZ / "scripts" / "daytrade"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from evo.especies import POR_NOME  # noqa: E402
from strategy.daytrade.evo import features as F  # noqa: E402
from strategy.daytrade.evo.genoma import (  # noqa: E402
    PESO_MINIMO_NUCLEO, Genoma)

PASTA = RAIZ / "scratch" / "evo_wdo_2026_09_18"
LOG = RAIZ / "scratch" / "evo_treino_v2.log"

#: Geracoes iguais seguidas a partir das quais a ilha esta' parada de fato.
#: 5 e' folgado de proposito: com blocos que deslocam, repetir 2 ou 3 e'
#: normal (o mesmo elite reavaliado na mesma particao).
CONGELADA = 5

#: Piso de amostra na janela cega -- `avaliacao.min_trades(20)`.
PISO_CEGO = 8


def _frac(hist: list[dict], chave: str, ini: int, fim: int) -> float:
    corte = hist[ini:fim]
    if not corte:
        return float("nan")
    return sum(h.get(chave, 0) / (h.get("pop") or 1) for h in corte) / len(corte)


def _alertas(d: dict) -> list[str]:
    fora = []
    usos: Counter = Counter()
    for ilha in d["ilhas"]:
        nome, hist = ilha["nome"], ilha["historico"]
        esp = POR_NOME.get(nome)

        # -- populacao congelada -------------------------------------------
        fits = [round(h["melhor"], 6) for h in hist]
        seq = 1
        for a, b in zip(fits, fits[1:]):
            seq = seq + 1 if a == b else 1
        if seq >= CONGELADA:
            fora.append(f"{nome}: campeao identico ha {seq} geracoes "
                        f"(fitness {fits[-1]:+.2f}) -- populacao pode ter "
                        f"virado clone")

        ult = hist[-1]
        pop = ult.get("pop") or 1
        # -- faixa unica ---------------------------------------------------
        for faixa in ("morto", "sem_amostra"):
            if ult.get(faixa, 0) == pop:
                fora.append(f"{nome}: 100% da populacao em '{faixa}' na "
                            f"g{ult['geracao']} -- sem gradiente de selecao")
        if ult.get("medido", 0) == 0 and len(hist) >= 8:
            fora.append(f"{nome}: nenhum individuo mensuravel na "
                        f"g{ult['geracao']}")

        # -- mensuravel encolhendo ------------------------------------------
        if len(hist) >= 10:
            meio = len(hist) // 2
            a, b = _frac(hist, "medido", 0, meio), _frac(hist, "medido", meio,
                                                         len(hist))
            if b < a - 0.10:
                fora.append(f"{nome}: fracao mensuravel CAINDO "
                            f"({100*a:.0f}% -> {100*b:.0f}%) -- busca pode "
                            f"estar fugindo de operar")

        # -- premissa vazando ------------------------------------------------
        # Decodifica do GENOMA, nunca do resumo do painel: o resumo
        # omite encaixe inerte (|peso| < 0,05), entao uma feature presente
        # com peso zero sumiria da lista e viraria alerta falso -- foi
        # exatamente o que aconteceu na primeira execucao deste vigia.
        cru = ilha["melhor"].get("cru")
        idxs = [e.idx for e in Genoma(cru=tuple(cru)).encaixes] if cru else []
        if esp:
            usos[nome] = 0
            for i in idxs:
                usos[F.NOMES[i]] += 1
            if esp.nucleo and cru:
                ativos = [e for e in Genoma(cru=tuple(cru)).encaixes
                          if e.idx in esp.nucleo
                          and (e.porta or max(abs(e.a), abs(e.b))
                               >= PESO_MINIMO_NUCLEO)]
                if len(ativos) < esp.min_nucleo:
                    fora.append(
                        f"{nome}: campeao com {len(ativos)} encaixes de nucleo "
                        f"ATIVOS, minimo {esp.min_nucleo} -- PREMISSA VAZOU")
            if set(idxs) - set(esp.permitidas):
                fora.append(f"{nome}: campeao olha feature fora das "
                            f"permitidas -- restricao vazou")

    # -- convergencia entre ilhas --------------------------------------------
    por_feature: Counter = Counter()
    for ilha in d["ilhas"]:
        vistos = set()
        for e in ilha["melhor"].get("encaixes") or []:
            m = re.match(r"(?:porta: )?(\w+)", e)
            if m:
                vistos.add(m.group(1))
        por_feature.update(vistos)
    n_ilhas = len(d["ilhas"])
    for feat, k in por_feature.items():
        if k >= max(6, int(0.7 * n_ilhas)):
            fora.append(f"convergencia: {k}/{n_ilhas} ilhas usam '{feat}' -- "
                        f"as ilhas estao virando a mesma busca")
    return fora


def main() -> None:
    if not PASTA.joinpath("progresso.json").exists():
        print("sem progresso.json -- a rodada ainda nao escreveu nada")
        return
    d = json.loads((PASTA / "progresso.json").read_text(encoding="utf-8"))
    parado = (time.time() - (PASTA / "progresso.json").stat().st_mtime) / 60
    g, gs = d["geracao"], d["geracoes"]
    dt = d.get("segundos_geracao", 0)
    print(f"geracao {g}/{gs}  |  {dt:.0f}s/geracao  |  "
          f"faltam ~{(gs - g) * dt / 3600:.1f}h  |  "
          f"ultima escrita ha {parado:.1f} min")
    if parado > 3 * max(dt, 60) / 60:
        print(f"  !! LOG PARADO ha {parado:.0f} min -- esperado ~{dt/60:.0f} min")

    print(f"\n{'ilha':<15}{'morto':>7}{'s/amo':>7}{'medido':>8}"
          f"{'  medido inicio->agora':>24}{'  cega +/com amostra':>21}")
    print("-" * 84)
    for ilha in sorted(d["ilhas"], key=lambda x: x["nome"]):
        h = ilha["historico"]
        u = h[-1]
        pop = u.get("pop") or 1
        meio = max(1, len(h) // 2)
        a, b = _frac(h, "medido", 0, meio), _frac(h, "medido", meio, len(h))
        amo = [x for x in h if not x.get("cego_morreu")
               and (x.get("cego_n_trades") or 0) >= PISO_CEGO]
        pos = sum(1 for x in amo if x.get("cego_r_por_op", 0) > 0)
        print(f"{ilha['nome']:<15}{u.get('morto',0):>7}{u.get('sem_amostra',0):>7}"
              f"{u.get('medido',0):>8}{100*a:>12.0f}% ->{100*b:>5.0f}%"
              f"{pos:>13}/{len(amo)}")

    alertas = _alertas(d)
    print()
    if alertas:
        print(f"!! {len(alertas)} ALERTA(S):")
        for x in alertas:
            print(f"   - {x}")
    else:
        print("nenhum alerta: nada indica que o treinamento esteja invalidado")


if __name__ == "__main__":
    main()
