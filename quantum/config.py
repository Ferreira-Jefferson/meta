"""Configuração do Quantum: caminhos, períodos congelados e premissas de backtest.

Tudo que muda a conclusão de um estudo mora aqui, num lugar só, para que a
linha de resultado possa dizer sob quais premissas ela foi medida.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DADOS = Path(os.environ.get("QUANTUM_DADOS", RAIZ / "dados"))
# Organização da base (pedido do dono, 2026-10-12: "mantenha toda base de
# arquivos salvas e bem organizadas"). Ver dados/README.md.
BRUTOS = DADOS / "brutos"        # arquivo original de cada fonte, nunca editado
ESTUDOS = DADOS / "estudos"      # cada rodada de estudos exportada (csv/json)
MANIFESTO = DADOS / "manifesto.csv"  # url, data de coleta, tamanho e sha256 de cada bruto
BANCO = DADOS / "quantum.sqlite"     # tabelas tratadas (reconstruível a partir de brutos/)

# Primeiro ano de DFP/ITR baixado da CVM. O ITR em dados abertos começa em 2011;
# com LTM exigindo 4 trimestres, o primeiro painel completo sai em meados de 2012.
ANO_INICIAL_CVM = 2011
INICIO_PRECOS = "2010-01-01"


# ── Períodos congelados (pedido do dono, 2026-10-12: "use IS e OOS pra não tirar
# conclusões enviesadas") ────────────────────────────────────────────────────
# Os limites foram fixados ANTES de qualquer backtest rodar. Mudar depois de ver
# resultado transforma a separação em ajuste, e o OOS deixa de confirmar nada.
#
#   IS     — único período usado para ESCOLHER (estratégia, N, frequência).
#   OOS    — confirma a escolha feita no IS; nunca decide nada.
#   VIRGEM — trancado. Só é revelado por ação explícita, que fica registrada.
#            Depois de revelado, ele vira OOS comum: não existe "segunda virgindade".
@dataclass(frozen=True)
class Periodo:
    nome: str
    inicio: date
    fim: date
    papel: str


PERIODOS = (
    Periodo("IS", date(2013, 1, 1), date(2020, 12, 31), "escolha"),
    Periodo("OOS", date(2021, 1, 1), date(2024, 12, 31), "confirmação"),
    Periodo("VIRGEM", date(2025, 1, 1), date(2099, 12, 31), "trancado"),
)
PERIODO = {p.nome: p for p in PERIODOS}


# ── Premissas padrão de backtest ───────────────────────────────────────────
@dataclass(frozen=True)
class Premissas:
    liquidez_min: float = 500_000.0   # R$/dia, média de 21 pregões (filtro do vídeo)
    custo_lado: float = 0.0010        # 0,10% por lado sobre o giro (emolumentos + spread)
    execucao_defasagem: int = 1       # decide no fechamento D, executa no fechamento D+1
    n_sorteios_nulo: int = 200        # carteiras aleatórias para o nulo


PREMISSAS = Premissas()

# Grade padrão dos estudos (a mesma do vídeo).
GRADE_N = (5, 10, 15, 20, 30)
GRADE_MESES = (3, 6, 12)

# Critério de escolha da célula, declarado antes de olhar: maior Sharpe
# (excesso sobre o CDI) NO IS. O OOS só confirma.
CRITERIO_ESCOLHA = "sharpe"

# Nível do Benjamini-Hochberg sobre todos os testes de uma rodada de estudos.
FDR_Q = 0.10

# Atualização automática enquanto o servidor estiver no ar (hora local).
HORA_ATUALIZACAO = int(os.environ.get("QUANTUM_HORA_ATUALIZACAO", "20"))

# ── Documentos do RI (documentos.py) ──────────────────────────────────────
# Leitura de PDF só para a LISTA CURTA (vigiadas + topo das estratégias), para não
# gastar tempo nem crédito com o mercado inteiro.
LISTA_CURTA_MAX = 30
LISTA_CURTA_N_POR_ESTRATEGIA = 10   # quando a estratégia ainda não tem estudo
DOCS_MAX_POR_RODADA = 300
# Haiku: reserva PAGA, desligada por padrão (liga com QUANTUM_HAIKU=1). Tetos diários
# rígidos: ao atingir qualquer um, os documentos ficam "aguardando orçamento".
HAIKU_MAX_DOCS_DIA = int(os.environ.get("QUANTUM_HAIKU_DOCS_DIA", "40"))
HAIKU_MAX_USD_DIA = float(os.environ.get("QUANTUM_HAIKU_USD_DIA", "0.50"))
HAIKU_MAX_CHARS = 24_000            # ~6 mil tokens de entrada por documento, no máximo

# balancos.com.br é PAGO (cobra por consulta). Só liga se as três variáveis
# existirem no ambiente; nunca guarde credencial no repositório.
BALANCOS_VARS = ("BALANCOS_TOKEN", "BALANCOS_LOGIN", "BALANCOS_SENHA")


def garantir_pastas() -> None:
    for p in (DADOS, BRUTOS, ESTUDOS):
        p.mkdir(parents=True, exist_ok=True)
