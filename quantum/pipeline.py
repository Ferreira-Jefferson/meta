"""Orquestração: atualizar cada fonte (sozinha ou todas) e recalcular os estudos.

Cada fonte é uma etapa independente, chamada pelo painel de Fontes ("baixar
novos arquivos desta fonte") ou pela atualização completa. Toda etapa:
  1. baixa o que é novo para `dados/brutos/<fonte>/` (registrado no manifesto)
  2. recarrega as tabelas tratadas dela no SQLite
  3. grava início/fim/status em `execucoes` (o painel mostra)
"""
from __future__ import annotations

import os
import threading
import traceback
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from . import armazem, config
from .fontes import bcb, cvm, yahoo


@dataclass(frozen=True)
class Fonte:
    chave: str
    nome: str
    descricao: str
    site: str
    pasta: str           # dentro de brutos/
    gratuita: bool = True


FONTES = {f.chave: f for f in (
    Fonte("cvm_cadastro", "CVM · Cadastro", "Companhias abertas: razão social, setor, situação.",
          "https://dados.cvm.gov.br/dataset/cia_aberta-cad", "cvm/cad"),
    Fonte("cvm_fca", "CVM · FCA", "Tickers de cada companhia (inclusive deslistados) e site de RI.",
          "https://dados.cvm.gov.br/dataset/cia_aberta-doc-fca", "cvm/fca"),
    Fonte("cvm_dfp", "CVM · DFP", "Demonstrações anuais com data de entrega.",
          "https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp", "cvm/dfp"),
    Fonte("cvm_itr", "CVM · ITR", "Demonstrações trimestrais com data de entrega.",
          "https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr", "cvm/itr"),
    Fonte("cvm_ipe", "CVM · IPE (RI)", "Fatos relevantes, releases, apresentações e avisos de proventos publicados pelo RI.",
          "https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe", "cvm/ipe"),
    Fonte("cvm_docs", "RI · PDFs da lista curta", "PDFs dos documentos do RI (proventos, releases, fatos relevantes) das empresas da lista curta, "
          "lidos por regras grátis; Haiku só de reserva, com teto diário.", "https://www.rad.cvm.gov.br", "cvm_docs"),
    Fonte("yahoo", "Yahoo Finance", "Preços diários, proventos e desdobramentos (yfinance) + Ibovespa.",
          "https://finance.yahoo.com", "yahoo/precos"),
    Fonte("bcb", "Banco Central · SGS", "CDI diário (série 12) para o benchmark de renda fixa.",
          "https://www3.bcb.gov.br/sgspub", "bcb/cdi"),
    Fonte("balancos", "Balanços.com.br", "PAGA, por consulta. Cobre sobretudo S.A. fechadas; para listadas a CVM já é a fonte original. "
          "Só liga com BALANCOS_TOKEN/LOGIN/SENHA no ambiente.", "https://balancos.com.br", "balancos", gratuita=False),
)}


def _anos() -> range:
    return range(config.ANO_INICIAL_CVM, date.today().year + 1)


def _etapa(nome: str, fn: Callable[[Callable], str], progresso=print) -> str:
    with armazem.conexao() as con:
        id_ = armazem.log_inicio(con, nome)
    try:
        msg = fn(progresso)
        status = "ok"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        status = "erro"
    with armazem.conexao() as con:
        armazem.log_fim(con, id_, status, msg)
    progresso(f"[{nome}] {status}: {msg.splitlines()[0] if msg else ''}")
    return status


# ── Etapas por fonte ───────────────────────────────────────────────────────
def _cadastro(progresso) -> str:
    emp = cvm.ler_cadastro()
    with armazem.conexao() as con:
        sites = armazem.ler(con, "SELECT cnpj, site_ri FROM empresas")
        emp = emp.merge(sites, on="cnpj", how="left")
        con.execute("DELETE FROM empresas")
        armazem.upsert(con, "empresas", emp)
    return f"{len(emp)} companhias"


def _fca(progresso) -> str:
    tickers, sites = cvm.ler_fca(_anos())
    with armazem.conexao() as con:
        con.execute("DELETE FROM tickers")
        armazem.upsert(con, "tickers", tickers)
        con.executemany("UPDATE empresas SET site_ri=? WHERE cnpj=?",
                        [(s, c) for c, s in zip(sites.cnpj, sites.site_ri) if isinstance(s, str)])
    return f"{len(tickers)} tickers, {sites.site_ri.notna().sum()} sites de RI"


def _demonstracoes(progresso) -> str:
    # DFP e ITR andam juntos: o LTM de um ITR precisa da DFP do ano anterior.
    dem = cvm.ler_demonstracoes(_anos(), progresso)
    with armazem.conexao() as con:
        con.execute("DELETE FROM demonstracoes")
        armazem.upsert(con, "demonstracoes", dem)
    return f"{len(dem)} documentos (empresa × data de referência)"


def _ipe(progresso) -> str:
    with armazem.conexao() as con:
        cnpjs = set(armazem.ler(con, "SELECT DISTINCT cnpj FROM tickers").cnpj)
        docs = cvm.ler_ipe(_anos(), cnpjs)
        armazem.upsert(con, "documentos", docs)
    return f"{len(docs)} documentos de RI"


def _yahoo(progresso) -> str:
    with armazem.conexao() as con:
        tk = armazem.ler(con, "SELECT ticker, fim_negociacao FROM tickers")
    # Inclui quem já deixou de negociar: o Yahoo às vezes ainda tem a série.
    lista = sorted(set(tk.ticker)) + ["^BVSP"]
    dados = yahoo.baixar_lote(lista, progresso=progresso)
    with armazem.conexao() as con:
        for t, df in dados.items():
            con.execute("DELETE FROM precos WHERE ticker=?", (t,))
            armazem.upsert(con, "precos", yahoo.para_tabela(t, df))
    return f"{len(dados)}/{len(lista)} tickers com preço"


def _bcb(progresso) -> str:
    cdi = bcb.baixar_cdi()
    with armazem.conexao() as con:
        con.execute("DELETE FROM indices WHERE serie='CDI'")
        armazem.upsert(con, "indices", cdi)
    return f"CDI até {cdi.data.iloc[-1]}"


def _balancos(progresso) -> str:
    faltando = [v for v in config.BALANCOS_VARS if not os.environ.get(v)]
    if faltando:
        return "desligada: credenciais ausentes (" + ", ".join(faltando) + ")"
    return "credenciais presentes; consultas são feitas por empresa na página da análise"


def _documentos(progresso) -> str:
    from . import documentos
    from .base import Base
    return documentos.processar(Base(), progresso=progresso)


ETAPAS: dict[str, Callable] = {
    "cvm_docs": _documentos,
    "cvm_cadastro": _cadastro,
    "cvm_fca": _fca,
    "cvm_dfp": _demonstracoes,
    "cvm_itr": _demonstracoes,
    "cvm_ipe": _ipe,
    "yahoo": _yahoo,
    "bcb": _bcb,
    "balancos": _balancos,
}
ORDEM = ("cvm_cadastro", "cvm_fca", "cvm_dfp", "cvm_ipe", "bcb", "yahoo")


def atualizar_fonte(chave: str, progresso=print) -> str:
    return _etapa(f"fonte:{chave}", ETAPAS[chave], progresso)


def atualizar_tudo(estudar: bool = True, progresso=print) -> None:
    for chave in ORDEM:
        atualizar_fonte(chave, progresso)
    if estudar:
        from . import estudos
        _etapa("estudos", lambda p: "rodada " + estudos.rodada(progresso=p), progresso)
    # Documentos por último: a lista curta depende do ranking e dos vereditos.
    atualizar_fonte("cvm_docs", progresso)


# ── Execução em segundo plano (servidor) ───────────────────────────────────
_trava = threading.Lock()
_em_curso: dict[str, str] = {}


def em_segundo_plano(nome: str, fn: Callable[[], None]) -> bool:
    """Dispara `fn` numa thread; recusa se a mesma tarefa já estiver rodando."""
    with _trava:
        if nome in _em_curso:
            return False
        _em_curso[nome] = pd.Timestamp.now().isoformat(timespec="seconds")

    def corpo():
        try:
            fn()
        finally:
            with _trava:
                _em_curso.pop(nome, None)

    threading.Thread(target=corpo, daemon=True, name=f"quantum-{nome}").start()
    return True


def tarefas_em_curso() -> dict[str, str]:
    with _trava:
        return dict(_em_curso)
