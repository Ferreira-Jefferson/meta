"""AS ESPECIES -- populacoes que evoluem ISOLADAS, cada uma de uma premissa
diferente.

## Por que nao uma populacao so'

Pedido do dono (2026-09-18): *"nao vai testar apenas uma especie que surge a
partir de hipoteses e premissas diferentes, vai testar varias, e cada uma vai
evoluir como tiver que evoluir. Quanto mais variedade, maiores as chances de
chegar em uma que se destaque."*

E' tambem o que a computacao evolutiva chama de MODELO DE ILHAS, e existe por
uma razao mecanica, nao por gosto: numa populacao unica, o primeiro individuo
razoavel que aparece domina a reproducao e a busca converge para a vizinhanca
dele em poucas geracoes. Tudo que seria bom mas comeca ruim morre antes de
amadurecer. Ilhas separadas protegem linhagens que ainda nao valem nada -- que
e' precisamente a condicao de qualquer coisa genuinamente nova.

Aqui as ilhas nao diferem so' por sorteio: cada uma tem uma PREMISSA, e a
premissa entra de duas formas --

  * **o conjunto de features permitido**. Uma especie proibida de olhar o
    bloco destilado (0-16) so' pode descobrir coisa nova, porque nao tem
    acesso ao que ja' sabemos;
  * **os individuos SEMEADOS** na geracao zero. Um punhado de plantados numa
    populacao de dezenas nao domina nada (eles competem pelo mesmo fitness),
    mas dao a especie um ponto de partida na regiao da hipotese dela em vez
    de no meio do nada.

## As especies nao migram

Sem troca de individuos entre ilhas, de proposito -- "cada uma vai evoluir
como tiver que evoluir". Isso tem um preco estatistico que fica registrado:
sao 6 buscas INDEPENDENTES, entao o numero de tentativas efetivas e' 6x o de
uma busca so', e o melhor resultado entre as 6 e' mais provavelmente sorte do
que o melhor de uma. O relatorio final tem de comparar cada campeao contra a
janela cega, e nao so' o vencedor geral -- escolher a especie campea pelo
proprio numero que a elegeu seria a mesma armadilha de escolher a celula
depois de ver a grade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from strategy.daytrade.evo import features as F
from strategy.daytrade.evo.genoma import (
    Genoma, garante_nucleo, genoma_aleatorio, projeta_em, semear)

#: Indices do bloco DESTILADO (o que o projeto ja' mediu) e do bloco CRU
#: (sem hipotese associada). Ver a docstring de `features.py`.
DESTILADO = tuple(range(0, 17))
CRU = tuple(range(17, F.N_FEATURES))
TUDO = tuple(range(F.N_FEATURES))


def _i(nome: str) -> int:
    return F.NOMES.index(nome)


def _idx(*nomes: str) -> tuple[int, ...]:
    return tuple(F.NOMES.index(n) for n in nomes)


#: Quantos dos `N_ENCAIXES` encaixes ficam RESERVADOS ao nucleo da especie.
#: Dois de seis: a premissa fica garantida e sobram quatro encaixes livres
#: para a ilha descobrir o que quiser. Ver `MEDIDO` abaixo.
ENCAIXES_DE_NUCLEO = 2


@dataclass(frozen=True)
class Especie:
    """Uma ilha.

    A premissa entra por DUAS vias estruturais e uma sugestiva:

      * `permitidas` -- de quais features os encaixes podem sair (a ilha nao
        enxerga o resto do banco);
      * `nucleo` -- quais features a ilha e' OBRIGADA a usar, em pelo menos
        `ENCAIXES_DE_NUCLEO` dos seus encaixes;
      * `sementes` -- individuos plantados na geracao zero.

    MEDIDO em 2026-09-19, e e' a razao de `nucleo` existir: na rodada de 65
    geracoes as 7 especies cuja premissa era APENAS semente retiveram 1 das
    28 features semeadas; as 2 com premissa estrutural (`permitidas`)
    ficaram 100% dentro dela. Semente nao segura premissa -- representacao
    segura. Ver `genoma.garante_nucleo`."""

    nome: str
    premissa: str
    permitidas: tuple[int, ...]
    nucleo: tuple[int, ...] = field(default=())
    sementes: tuple[Genoma, ...] = field(default=())

    @property
    def min_nucleo(self) -> int:
        """Nao da' para exigir mais encaixes de nucleo do que o nucleo tem
        features distintas -- o `vwap` tem uma so'."""
        return min(ENCAIXES_DE_NUCLEO, len(self.nucleo))

    def projeta(self, g: Genoma) -> Genoma:
        """Puxa `g` para dentro desta especie. UNICO ponto por onde um genoma
        entra numa ilha -- sorteado, cruzado, mutado ou semeado."""
        return garante_nucleo(projeta_em(g, self.permitidas),
                              self.nucleo, self.min_nucleo)

    def aleatorio(self, rng) -> Genoma:
        return self.projeta(genoma_aleatorio(rng, self.permitidas))


#: Geometria de partida herdada do `wdo_orb` teto1/stop30/alvo1,5x, que e' a
#: unica geometria deste projeto com resultado positivo confirmado em janela
#: cega. Serve de ponto de partida para as especies que tem semente -- nao
#: como teto (o espaco continua inteiro disponivel), so' como lugar onde
#: comecar a procurar.
_GEO_ORB = {"theta": 0.35, "offset_ticks": 1, "ttl_min": 15, "stop_ticks": 30,
            "alvo_mult": 1.5, "max_ops_dia": 2, "hora_ini": 0.0,
            "hora_fim": 1.0, "corte_min": 60}

_GEO_CURTA = {"theta": 0.30, "offset_ticks": 2, "ttl_min": 8, "stop_ticks": 12,
              "alvo_mult": 1.5, "max_ops_dia": 4, "hora_ini": 0.0,
              "hora_fim": 1.0, "corte_min": 30}


ESPECIES: tuple[Especie, ...] = (
    Especie(
        nome="rompimento",
        premissa=(
            "A faixa dos primeiros minutos organiza o dia, e o preco a "
            "respeita ou a rompe. E' a premissa do `wdo_orb`, o unico "
            "candidato vivo do projeto -- entra aqui para a evolucao poder "
            "SUPERAR o que ja temos, e para que 'nao superou' seja um "
            "resultado legivel em vez de duvida."),
        permitidas=TUDO,
        nucleo=_idx("pos_faixa", "larg_faixa", "dentro_faixa", "rompeu_cima",
             "rompeu_baixo"),
        sementes=(
            semear(_GEO_ORB, [
                (_i("pos_faixa"), +1.0, -1.0, False),
                (_i("larg_faixa"), +0.3, +0.3, False),
                (_i("hora"), -0.2, -0.2, False),
            ]),
        ),
    ),
    Especie(
        nome="fade",
        premissa=(
            "Dia indeciso volta ao meio. E' a perna FORTE do `wdo_orb` no "
            "OOS (+R$34,50/op, win 67,86%, contra -R$11,38/op do rompimento) "
            "-- a unica coisa daquele robo que sobreviveu a janela cega, e "
            "que nunca foi isolada como robo proprio."),
        permitidas=TUDO,
        nucleo=_idx("pos_faixa", "dentro_faixa", "rompeu_cima", "rompeu_baixo"),
        sementes=(
            semear(_GEO_ORB, [
                (_i("pos_faixa"), -1.0, +1.0, False),
                (_i("rompeu_cima"), -0.5, +0.5, False),
                (_i("rompeu_baixo"), +0.5, -0.5, False),
            ]),
        ),
    ),
    Especie(
        nome="retangulo",
        premissa=(
            "Quando o preco se aperta numa faixa fina, as bordas dela valem "
            "mais que qualquer outra referencia. O detector do dono foi "
            "confirmado em OOS congelado (4/4) e virou robo no WIN; no WDO a "
            "logica e' portavel e nunca foi testada com a geometria certa."),
        permitidas=TUDO,
        nucleo=_idx("em_retangulo", "pos_retangulo"),
        sementes=(
            semear(_GEO_CURTA, [
                (_i("em_retangulo"), +0.5, +0.5, True),
                (_i("pos_retangulo"), -1.0, +1.0, False),
                (_i("amplit_rel"), -0.3, -0.3, False),
            ]),
        ),
    ),
    Especie(
        nome="fluxo",
        premissa=(
            "O que decide nao e' onde o preco esta', e' como ele chegou -- "
            "volume, aceleracao e a razao |deslocamento|/amplitude. A "
            "contracao de volatilidade por toxicidade foi MEDIDA e e' real; "
            "o que foi refutado e' vira-la em veto ou em ajuste de "
            "geometria. Como coordenada de uma politica, e' teste novo."),
        permitidas=TUDO,
        nucleo=_idx("vol_rel", "acel_vol", "drift_norm", "irreg_volume"),
        sementes=(
            semear(_GEO_CURTA, [
                (_i("drift_norm"), +1.0, -1.0, False),
                (_i("vol_rel"), +0.4, +0.4, False),
                (_i("acel_vol"), +0.4, +0.4, False),
            ]),
        ),
    ),
    Especie(
        nome="cega",
        premissa=(
            "Nenhuma premissa. Populacao sorteada sobre o banco INTEIRO, sem "
            "semente nenhuma. E' a especie que pode discordar de tudo que "
            "este projeto acredita, e a unica cujo resultado nao carrega "
            "vies de ponto de partida."),
        permitidas=TUDO,
    ),
    Especie(
        nome="crua",
        premissa=(
            "PROIBIDA de olhar o bloco destilado. So' ve geometria de barra, "
            "sequencias, distancia a extremos, irregularidade de fluxo, hora "
            "redonda e preco redondo -- coordenadas sobre as quais este repo "
            "nao tem nenhuma hipotese. Se algo sair daqui, e' necessariamente "
            "coisa que nao estavamos vendo, porque as features que usamos "
            "para ver estao fora do alcance dela."),
        permitidas=CRU,
    ),
    Especie(
        nome="extremos",
        premissa=(
            "O que ancora o dia nao e' a faixa de abertura, e' a maxima e a "
            "minima ja' feitas -- e ha' quanto tempo foram feitas. Mecanismo "
            "diferente do fade do `wdo_orb`: la' a referencia e' uma faixa "
            "congelada nos primeiros 15 minutos, aqui ela anda com o dia. A "
            "excursao parcial ja' foi refutada como GESTAO de posicao "
            "(5 desenhos, 0 passam); como coordenada de ENTRADA e' outra "
            "pergunta, nunca feita."),
        permitidas=TUDO,
        nucleo=_idx("dist_max_sessao", "dist_min_sessao", "idade_extremo"),
        sementes=(
            semear(_GEO_CURTA, [
                (_i("dist_max_sessao"), -1.0, +0.6, False),
                (_i("dist_min_sessao"), +0.6, -1.0, False),
                (_i("idade_extremo"), +0.4, +0.4, False),
            ]),
        ),
    ),
    Especie(
        nome="microestrutura",
        premissa=(
            "RESTRITA ao formato da barra e a grade de precos: corpo, "
            "sombras, distancia ao multiplo de 5 pontos, minuto da hora "
            "cheia. E' a aposta de que o que importa acontece em escala "
            "menor que qualquer indicador -- nivel redondo que segura, "
            "sombra que marca rejeicao, o minuto em que o fluxo institucional "
            "vira. Nenhuma dessas foi testada neste repo."),
        permitidas=(_i("corpo_rel"), _i("sombra_sup"), _i("sombra_inf"),
                    _i("preco_redondo"), _i("minuto_hora"), _i("ret_1"),
                    _i("seq_direcao"), _i("irreg_volume")),
    ),
    Especie(
        nome="relogio",
        premissa=(
            "A hora manda mais que o preco. Filtro de dia/horario ja' foi "
            "REFUTADO no WDO como veto (corta e piora o OOS), mas aquilo era "
            "um recorte imposto por fora; aqui a hora e' uma coordenada que "
            "a busca pondera junto das outras, e o teto/janela de operacao "
            "evoluem com ela. Refutacao de um veto nao e' refutacao de uma "
            "coordenada."),
        permitidas=TUDO,
        nucleo=_idx("hora", "minuto_hora", "dia_semana"),
        sementes=(
            semear(_GEO_CURTA, [
                (_i("hora"), +0.3, -0.7, False),
                (_i("dist_abert"), -0.8, +0.8, False),
                (_i("vol_rel"), +0.3, +0.3, False),
            ]),
        ),
    ),
    Especie(
        nome="vwap",
        premissa=(
            "A VWAP da sessao e' o preco justo do dia, e o desvio em relacao "
            "a ela e' o sinal. E' a referencia que mais aparece em mesa real "
            "e a unica das grandes que este projeto nunca testou como robo "
            "proprio."),
        permitidas=TUDO,
        nucleo=_idx("dist_vwap"),
        sementes=(
            semear(_GEO_ORB, [
                (_i("dist_vwap"), -1.0, +1.0, False),
                (_i("amplit_rel"), +0.3, +0.3, False),
                (_i("hora"), -0.3, -0.3, False),
            ]),
        ),
    ),
)

POR_NOME = {e.nome: e for e in ESPECIES}


def nomes() -> list[str]:
    return [e.nome for e in ESPECIES]


def resolve(pedidas: Sequence[str] | None) -> list[Especie]:
    if not pedidas:
        return list(ESPECIES)
    faltando = [n for n in pedidas if n not in POR_NOME]
    if faltando:
        raise SystemExit(
            f"especie desconhecida: {', '.join(faltando)}. "
            f"disponiveis: {', '.join(nomes())}")
    return [POR_NOME[n] for n in pedidas]
