"""Ficha da tese de arbitragem social -- o objeto que percorre as fases do
metodo Camilo/Williams, de deteccao ate fechamento. Puro dado + regra de
transicao; persistencia mora em `store.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Lente(str, Enum):
    """De qual paradigma de assimetria de informacao a tese nasceu. As duas
    lentes principais compartilham a mesma maquina de estados (`Fase`) e o
    mesmo criterio de saida (paridade de informacao) -- o que muda e' o
    INSUMO da deteccao, nao o funil depois dela:

      * `CONSUMO` -- metodo Camilo. Mudanca real de comportamento de
        consumo observada ANTES do mercado (prateleira vazia, video viral,
        fila). Usa `brand_map.py` para achar o ticker.
      * `POSICIONAMENTO` -- logica de Larry Williams (recorde de 11.376% em
        1987, Robbins World Cup), NAO os indicadores dele (nao e' %R nem
        WillCo AD isolados -- ver adiante onde o %R entra, so' como
        confirmacao). Williams nunca operou um sinal so': ele exigia
        CONFLUENCIA de quatro condicoes ao mesmo tempo, e descartava 90% das
        vezes em que so' uma ou duas batiam. As quatro (cada uma vira uma
        `Evidencia` desta tese -- ver o campo `fonte` de cada uma):

          1. **Smart money via COT.** O CFTC publica semanalmente quem esta
             posicionado: `commercials` (quem lida com a mercadoria fisica --
             hedge, nao especulacao, compram pesado quando o preco esta
             baixo pela logica do PROPRIO negocio) contra `speculators`
             (fundos/varejo, em regra chegam por ULTIMO no movimento).
             Williams nao olhava o nivel absoluto da posicao comercial --
             olhava o PERCENTIL dela dentro da propria janela de 3 anos: a
             pergunta e' "o dinheiro grande esta anormalmente comprado ou
             vendido CONTRA O PROPRIO HISTORICO recente", nao contra um
             numero fixo. No Brasil o analogo e' a "posicao em aberto por
             tipo de investidor" que a B3 publica para futuros (WDO, WIN,
             DI, indice) -- fonte de dado ainda NAO integrada neste modulo
             (fase 3 do faseamento, ver `social_arbitrage/__init__.py`).
          2. **Calendario -- TDW (Trading Day of the Week).** Nao e' so'
             sazonalidade de mes/safra: Williams descobriu que dia da SEMANA
             importa, porque dinheiro institucional opera em rotina semanal
             fixa (fechamento, vencimento, rebalanceamento). E' derivavel do
             proprio calendario da barra, sem dado externo.
          3. **Gatilho de entrada -- o padrao "Oops!"** (a transcricao chama
             de "UPS", e' o mesmo "Oops!" que Williams descreve nos livros):
             abertura em gap PARA BAIXO da minima do dia anterior; o preco
             reverte e recupera aquela minima; o cruzamento de VOLTA acima
             dela e' o gatilho de compra, stop logo abaixo da minima da
             manha. Logica: panico de abertura faz gente vender por medo: se
             o mercado absorve essa venda e recupera o nivel anterior, o
             panico era infundado, e Williams compra o que o resto largou
             por nervosismo. Padrao puramente OHLCV -- portavel para
             `strategy/` se algum dia virar candidato sistematico, mas
             NUNCA teste isso isolado: some ao 6.25 (eixo morto) da memoria
             do projeto -- e' so' 1 das 4 condicoes.
          4. **%R como termometro, nao gatilho.** Confirma que o preco
             estava "exaurido" (sobrevendido) nas ultimas 14 sessoes antes
             do Oops disparar -- filtro de confirmacao, nunca sinal
             independente.

        Por ora a tese POSICIONAMENTO e' cadastrada com a leitura ja feita
        manualmente pelo dono (as 4 condicoes registradas como evidencias),
        do mesmo jeito que uma tese CONSUMO detectada a mao -- nenhuma das
        quatro fontes esta automatizada neste modulo ainda.
      * `OUTRA` -- qualquer lente futura que nao se encaixe nas duas acima.
    """

    CONSUMO = "consumo"
    POSICIONAMENTO = "posicionamento"
    OUTRA = "outra"


class Fase(str, Enum):
    """Estados da tese, na ordem em que o metodo Camilo percorre.

    Transicoes permitidas (aplicadas por `Thesis.transicionar`):
      DETECTADA -> EM_VERIFICACAO | REJEITADA
      EM_VERIFICACAO -> APROVADA | REJEITADA
      APROVADA -> ABERTA
      ABERTA -> FECHADA
    Nenhuma fase volta para tras -- uma tese rejeitada nao reabre; se a
    observacao continua valendo, cadastre uma tese NOVA com a evidencia
    atualizada, para nao apagar o motivo da rejeicao original.
    """

    DETECTADA = "detectada"
    EM_VERIFICACAO = "em_verificacao"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
    ABERTA = "aberta"
    FECHADA = "fechada"


#: Transicoes validas: fase atual -> conjunto de fases destino permitidas.
_TRANSICOES_VALIDAS: dict[Fase, frozenset[Fase]] = {
    Fase.DETECTADA: frozenset({Fase.EM_VERIFICACAO, Fase.REJEITADA}),
    Fase.EM_VERIFICACAO: frozenset({Fase.APROVADA, Fase.REJEITADA}),
    Fase.APROVADA: frozenset({Fase.ABERTA}),
    Fase.ABERTA: frozenset({Fase.FECHADA}),
    Fase.REJEITADA: frozenset(),
    Fase.FECHADA: frozenset(),
}


@dataclass(frozen=True)
class Evidencia:
    """Um item de verificacao de campo ou social acumulado durante
    `Fase.EM_VERIFICACAO` -- e' o que diferencia uma tese investigada de um
    palpite. `fonte` e' livre (ex.: "ligacao com gerente de loja X",
    "menções X/Twitter", "Google Trends"), mas e' obrigatoria: evidencia sem
    fonte nao pode ser reavaliada depois."""

    texto: str
    fonte: str
    registrado_em: datetime

    def __post_init__(self) -> None:
        if not self.texto.strip():
            raise ValueError("Evidencia: `texto` nao pode ser vazio.")
        if not self.fonte.strip():
            raise ValueError("Evidencia: `fonte` nao pode ser vazia.")


@dataclass
class Thesis:
    """Tese de uma marca/ticker, do desequilibrio de informacao ate o
    fechamento. Campos de execucao (`preco_entrada`, `quantidade`, ...) sao
    preenchidos manualmente pelo dono DEPOIS de operar pelo canal que ja usa
    (MT5/home broker) -- este objeto e' o registro da decisao, nunca o
    caminho de ordem.

    `tamanho_alvo_pct` nao tem default: e' fracao do capital (0 a 1) que o
    dono pretende alocar SE aprovar, e exigir o numero explicito forca a
    decisao de tamanho a acontecer na aprovacao, nao a virar um default
    silencioso. O proprio Camilo concentra 20-40% por convicção com
    volatilidade ~5x o mercado (auditoria academica, ver `CLAUDE.md`) -- isto
    e' contexto para o dono decidir, nao um teto imposto por este codigo.

    O jeito RECOMENDADO de chegar nesse numero e' `sizing.tamanho_meio_kelly`
    (Kelly fracionario a partir de probabilidade de acerto e payoff
    estimados), nao digitar um percentual de cabeca -- mas o campo aceita
    qualquer valor em (0, 1] porque o dono pode ter motivo para divergir do
    que o Kelly sugere, e essa decisao e' sempre dele, nunca imposta pelo
    dataclass.
    """

    id: int | None
    marca: str
    ticker: str
    fase: Fase
    lente: Lente
    fonte_deteccao: str
    descricao: str
    criterio_saida: str
    tamanho_alvo_pct: float
    criado_em: datetime
    evidencias: list[Evidencia] = field(default_factory=list)
    motivo_rejeicao: str | None = None
    preco_entrada: float | None = None
    quantidade: float | None = None
    preco_saida: float | None = None
    resultado_brl: float | None = None
    atualizado_em: datetime | None = None
    # Preenchidos SO' quando `tamanho_alvo_pct` veio de `sizing.tamanho_meio_kelly`
    # (via `--prob-acerto`/`--payoff` na CLI) -- `None` quando o dono digitou o
    # percentual direto. Existem para fechar o loop que `calibragem.py` mede:
    # a probabilidade/payoff ESTIMADOS na hora da aprovacao contra o resultado
    # REALIZADO depois de FECHADA. Sem guardar a estimativa original, calibrar
    # o proprio julgamento do dono seria impossivel -- so' o resultado fica,
    # nao a previsao que o gerou.
    prob_acerto_estimada: float | None = None
    payoff_estimado: float | None = None

    def __post_init__(self) -> None:
        if not self.marca.strip():
            raise ValueError("Thesis: `marca` nao pode ser vazia.")
        if not self.ticker.strip():
            raise ValueError("Thesis: `ticker` nao pode ser vazio.")
        if not self.descricao.strip():
            raise ValueError("Thesis: `descricao` nao pode ser vazia -- o que foi observado tem de ficar escrito.")
        if not self.criterio_saida.strip():
            raise ValueError(
                "Thesis: `criterio_saida` nao pode ser vazio -- o metodo Camilo "
                "sai na PARIDADE de informacao, nao num preco-alvo; declare aqui "
                "o que vai indicar que a informacao virou publica."
            )
        if not 0.0 < self.tamanho_alvo_pct <= 1.0:
            raise ValueError(
                f"Thesis: `tamanho_alvo_pct` tem de estar em (0, 1], recebeu "
                f"{self.tamanho_alvo_pct!r} -- e' fracao do capital, nao percentual (use 0.30 para 30%)."
            )

    def transicionar(self, nova_fase: Fase, *, quando: datetime) -> None:
        """Move a tese para `nova_fase`, ou lanca `ValueError` se a
        transicao nao esta em `_TRANSICOES_VALIDAS` -- nunca pula fase
        (ex.: DETECTADA direto para ABERTA) nem volta fase."""
        permitidas = _TRANSICOES_VALIDAS[self.fase]
        if nova_fase not in permitidas:
            raise ValueError(
                f"Thesis {self.id!r} ({self.marca}): transicao {self.fase.value} -> "
                f"{nova_fase.value} nao e' permitida. De {self.fase.value} so' se vai "
                f"para {sorted(f.value for f in permitidas)!r}."
            )
        self.fase = nova_fase
        self.atualizado_em = quando

    def adicionar_evidencia(self, evidencia: Evidencia) -> None:
        if self.fase not in (Fase.DETECTADA, Fase.EM_VERIFICACAO):
            raise ValueError(
                f"Thesis {self.id!r} ({self.marca}): evidencia so' se acumula em "
                f"DETECTADA/EM_VERIFICACAO, fase atual e' {self.fase.value}."
            )
        self.evidencias.append(evidencia)
