"""Catalogo marca de consumo -> empresa listada na B3.

E' o equivalente deste projeto ao Ticker Tags do Camilo (250 mil termos ->
8 mil tickers), so' que no Brasil ninguem construiu essa base pronta -- o
universo de consumo listado na B3 e' MUITO menor que o americano (dezenas
de marcas reconheciveis, nao milhares), entao uma tabela cadastrada a mao e'
o caminho certo aqui, nao uma NLP cara para um problema pequeno.

Cada entrada carrega `fonte_confianca` porque o dono de uma tese precisa
saber, antes de arriscar capital, se o vinculo marca->ticker e' fato
societario conhecido (ex.: Havaianas e' da Alpargatas) ou uma inferencia que
merece checar antes de operar (participacoes cruzadas, fusao recente,
marca que deixou de ser a maior fatia da receita). Nunca finja certeza
uniforme.

Cobertura e' PARCIAL de proposito -- e' ponto de partida, nao lista
fechada -- e o universo muda (fusao, IPO, recuperacao judicial, delisting).
Antes de abrir uma tese, confira o ticker no home broker: nao ha
verificacao automatica aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FonteConfianca(str, Enum):
    """Quao direto e' o vinculo entre a marca observada e o ticker."""

    #: A marca E' a empresa, ou e' o produto que domina a receita dela --
    #: mover a marca move a acao sem precisar de mais nenhuma suposicao.
    DIRETA = "direta"
    #: A marca pertence a uma holding com VARIAS marcas -- mover aquela
    #: marca especifica so' move a acao se ela pesar o suficiente na
    #: receita total. Verificar isso e' trabalho da fase EM_VERIFICACAO,
    #: nao deste catalogo.
    HOLDING_MULTIMARCA = "holding_multimarca"
    #: Vinculo societario mudou recentemente (fusao/aquisicao/cisao) ou e'
    #: menos conhecido -- conferir o ticker vigente antes de usar.
    A_CONFIRMAR = "a_confirmar"


@dataclass(frozen=True)
class BrandMapping:
    """Um vinculo marca -> ticker B3, com a categoria de consumo e o motivo
    de confianca. `__post_init__` recusa campos vazios: uma entrada sem
    ticker ou sem marca e' pior que ausente, porque parece cadastrada."""

    marca: str
    empresa: str
    ticker: str
    categoria: str
    fonte_confianca: FonteConfianca
    observacao: str = ""

    def __post_init__(self) -> None:
        for campo in ("marca", "empresa", "ticker", "categoria"):
            if not getattr(self, campo):
                raise ValueError(
                    f"BrandMapping: `{campo}` nao pode ser vazio -- entrada "
                    f"incompleta e' pior que ausente, porque parece cadastrada."
                )


#: Catalogo BRASIL -- marcas de consumo reconheciveis mapeadas para o
#: ticker B3 da controladora. Curado a mao (2026-09-27); revisar
#: periodicamente contra fusao/cisao/recuperacao judicial. NAO e' lista
#: fechada -- adicione entradas conforme novas teses aparecerem.
CATALOGO_BRASIL: tuple[BrandMapping, ...] = (
    BrandMapping("Havaianas", "Alpargatas", "ALPA4", "vestuario/calcados", FonteConfianca.DIRETA),
    BrandMapping("Osklen", "Alpargatas", "ALPA4", "vestuario/calcados", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Farm", "Grupo Soma", "SOMA3", "vestuario/moda", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Animale", "Grupo Soma", "SOMA3", "vestuario/moda", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Hering", "Grupo Soma", "SOMA3", "vestuario/moda", FonteConfianca.HOLDING_MULTIMARCA, "Cia Hering (ex-HGTX3) incorporada ao Grupo Soma -- confirmar ticker vigente."),
    BrandMapping("Arezzo", "Arezzo&Co", "ARZZ3", "vestuario/calcados", FonteConfianca.A_CONFIRMAR, "Fusao Arezzo&Co x Grupo Soma anunciada em 2024/2025 -- confirmar se o ticker ARZZ3 segue vigente ou virou SOMA3."),
    BrandMapping("Renner", "Lojas Renner", "LREN3", "varejo/vestuario", FonteConfianca.DIRETA),
    BrandMapping("C&A", "C&A Modas", "CEAB3", "varejo/vestuario", FonteConfianca.DIRETA),
    BrandMapping("Riachuelo", "Guararapes Confeccoes", "GUAR3", "varejo/vestuario", FonteConfianca.DIRETA),
    BrandMapping("Vivara", "Vivara Participacoes", "VIVA3", "joalheria", FonteConfianca.DIRETA),
    BrandMapping("Centauro", "Grupo SBF", "SBFG3", "varejo/artigos esportivos", FonteConfianca.DIRETA),
    BrandMapping("Petz", "Petz", "PETZ3", "varejo/pet", FonteConfianca.DIRETA),
    BrandMapping("Smart Fit", "Smart Fit Escola de Ginastica e Danca", "SMFT3", "servicos/academia", FonteConfianca.DIRETA),
    BrandMapping("Enjoei", "Enjoei", "ENJU3", "marketplace/moda usada", FonteConfianca.DIRETA),
    BrandMapping("Magazine Luiza", "Magazine Luiza", "MGLU3", "varejo/e-commerce", FonteConfianca.DIRETA),
    BrandMapping("Casas Bahia", "Grupo Casas Bahia", "BHIA3", "varejo/eletro", FonteConfianca.DIRETA, "Ex-Via (VIIA3); confirmar ticker apos reestruturacao."),
    BrandMapping("Assai", "Assai Atacadista", "ASAI3", "varejo/atacarejo", FonteConfianca.DIRETA),
    BrandMapping("Pao de Acucar", "Grupo Pao de Acucar (GPA)", "PCAR3", "varejo/supermercado", FonteConfianca.DIRETA),
    BrandMapping("Carrefour", "Atacadao/Carrefour Brasil", "CRFB3", "varejo/supermercado", FonteConfianca.DIRETA),
    BrandMapping("Skol", "Ambev", "ABEV3", "bebidas", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Brahma", "Ambev", "ABEV3", "bebidas", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Guarana Antarctica", "Ambev", "ABEV3", "bebidas", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Sadia", "BRF", "BRFS3", "alimentos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Perdigao", "BRF", "BRFS3", "alimentos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Seara", "JBS", "JBSS3", "alimentos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Piraque", "M. Dias Branco", "MDIA3", "alimentos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Adria", "M. Dias Branco", "MDIA3", "alimentos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Natura", "Natura &Co", "NTCO3", "cosmeticos", FonteConfianca.DIRETA),
    BrandMapping("Avon", "Natura &Co", "NTCO3", "cosmeticos", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Drogasil", "Raia Drogasil (RD)", "RADL3", "farmacia/varejo", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Droga Raia", "Raia Drogasil (RD)", "RADL3", "farmacia/varejo", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Pague Menos", "Pague Menos", "PGMN3", "farmacia/varejo", FonteConfianca.DIRETA),
    BrandMapping("Engov", "Hypera Pharma", "HYPE3", "farmaceutico OTC", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Estomazil", "Hypera Pharma", "HYPE3", "farmaceutico OTC", FonteConfianca.HOLDING_MULTIMARCA),
    BrandMapping("Localiza", "Localiza", "RENT3", "locacao de veiculos", FonteConfianca.DIRETA),
    BrandMapping("Movida", "Movida Participacoes", "MOVI3", "locacao de veiculos", FonteConfianca.DIRETA),
    BrandMapping("Azul", "Azul", "AZUL4", "aviacao", FonteConfianca.DIRETA),
    BrandMapping("Gol", "Gol Linhas Aereas", "GOLL4", "aviacao", FonteConfianca.DIRETA),
    BrandMapping("CVC", "CVC Brasil", "CVCB3", "turismo/agencia", FonteConfianca.DIRETA),
    BrandMapping("Hapvida", "Hapvida NotreDame Intermedica", "HAPV3", "saude/plano", FonteConfianca.DIRETA),
    BrandMapping("Fleury", "Grupo Fleury", "FLRY3", "saude/diagnostico", FonteConfianca.DIRETA),
    BrandMapping("Meliuz", "Meliuz", "CASH3", "fintech/cashback", FonteConfianca.DIRETA),
)


def buscar_por_marca(marca: str) -> tuple[BrandMapping, ...]:
    """Vinculos cujo campo `marca` bate (case-insensitive, exato) com
    `marca`. Retorna tupla vazia para marca desconhecida -- nunca lanca,
    porque "nao esta no catalogo ainda" e' esperado, nao erro; use
    `buscar_por_ticker`/percorrer `CATALOGO_BRASIL` para descobrir o que ja
    existe antes de assumir que falta."""
    alvo = marca.strip().casefold()
    return tuple(m for m in CATALOGO_BRASIL if m.marca.casefold() == alvo)


def buscar_por_ticker(ticker: str) -> tuple[BrandMapping, ...]:
    """Todas as marcas cadastradas sob um `ticker` (uma holding
    multimarca aparece varias vezes)."""
    alvo = ticker.strip().upper()
    return tuple(m for m in CATALOGO_BRASIL if m.ticker.upper() == alvo)
