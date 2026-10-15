"""Extração de dados dos documentos do RI: primeiro de graça (regras), Haiku só de reserva.

Pedido do dono (2026-10-12): "obter os dados dos documentos de maneira gratuita, sem
precisar usar LLM; se não for possível, use o Haiku, só para uma lista das melhores
empresas, para não queimar o limite de crédito".

Fluxo por documento (só empresas da LISTA CURTA, só categorias úteis):
  1. baixa o PDF do RAD/CVM → `brutos/cvm_docs/<cnpj>/<protocolo>.pdf` (manifesto)
  2. extrai o texto com pypdf (local, grátis) → `derivados/textos/<protocolo>.txt`
  3. REGRAS (regex + palavras-chave), por tipo:
       proventos  → tipo (JCP/dividendo), R$/ação, data-com, data ex, pagamento
       release    → receita, EBITDA, lucro, dívida líquida (+ unidade)
       fato relev.→ tópicos (recompra, aquisição, emissão, guidance...)
  4. se as regras não acharam o mínimo E o Haiku está LIGADO E há orçamento do dia:
       manda só as páginas mais relevantes (por palavra-chave), nunca o PDF inteiro,
       e grava quantos tokens e quanto custou. Documento já processado nunca é
       reenviado (o protocolo é a chave).

O Haiku nasce DESLIGADO. Liga com QUANTUM_HAIKU=1 + credencial da Anthropic no
ambiente (ANTHROPIC_API_KEY ou perfil `ant auth login`). Teto diário em config.
"""
from __future__ import annotations

import io
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import armazem, config
from .estrategias import ESTRATEGIAS
from .fontes import arquivo

UA = {"User-Agent": "quantum-research/0.1 (uso pessoal; dados publicos CVM)"}
MODELO_HAIKU = "claude-haiku-4-5"
PRECO_IN, PRECO_OUT = 1.00 / 1e6, 5.00 / 1e6        # US$ por token (tabela 2026-09)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS extracoes (
    protocolo TEXT PRIMARY KEY, cnpj TEXT, data_entrega TEXT, tipo_doc TEXT,
    metodo TEXT, status TEXT, campos TEXT, evidencias TEXT, paginas INTEGER,
    tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, custo_usd REAL DEFAULT 0,
    criado_em TEXT
);
CREATE TABLE IF NOT EXISTS vigiadas (cnpj TEXT PRIMARY KEY, adicionado_em TEXT);
"""


def _con():
    con = armazem.conectar()
    con.executescript(SCHEMA_SQL)
    return con


# ── Qual documento é de qual tipo ──────────────────────────────────────────
def tipo_do_documento(categoria: str, tipo: str, especie: str, assunto: str) -> str | None:
    a = f"{tipo or ''} {especie or ''} {assunto or ''}".lower()
    if categoria in ("Relatório Proventos",) or (
            categoria in ("Aviso aos Acionistas", "Fato Relevante", "Comunicado ao Mercado")
            and re.search(r"dividend|juros sobre (o )?capital|jcp|proventos|remunera[çc][ãa]o aos acionistas", a)):
        return "proventos"
    if categoria == "Dados Econômico-Financeiros" and re.search(r"press|release|resultado", a):
        return "release"
    if categoria == "Fato Relevante":
        return "fato_relevante"
    return None


# ── Lista curta ────────────────────────────────────────────────────────────
def lista_curta(base, maximo: int | None = None) -> list[dict]:
    """Empresas que merecem leitura de documento: vigiadas primeiro, depois o topo
    de cada estratégia de hoje, das mais bem avaliadas no estudo para as piores."""
    maximo = maximo or config.LISTA_CURTA_MAX
    with _con() as con:
        vig = [r[0] for r in con.execute("SELECT cnpj FROM vigiadas ORDER BY adicionado_em")]
        r = con.execute("SELECT MAX(rodada) FROM estudos WHERE tipo='protocolo'").fetchone()[0]
        vered = {}
        if r:
            for est, res in con.execute("SELECT estrategia, resultado FROM estudos WHERE rodada=?", (r,)):
                e = json.loads(res)
                vered[est] = (e.get("veredito"), e["escolha"]["n"])
    ordem = {"confirmada": 0, "promissora, sem significância": 1}
    chaves = sorted(ESTRATEGIAS, key=lambda k: ordem.get(vered.get(k, (None,))[0], 2))
    p = base.painel(base.datas[-1])
    saida, vistos = [], set()
    for c in vig:
        if c not in vistos:
            t = p[p.cnpj == c].ticker
            saida.append({"cnpj": c, "ticker": t.iloc[0] if len(t) else None, "motivo": "vigiada"})
            vistos.add(c)
    for k in chaves:
        n = vered.get(k, (None, config.LISTA_CURTA_N_POR_ESTRATEGIA))[1]
        rank = ESTRATEGIAS[k].ranquear(p, config.PREMISSAS.liquidez_min).head(n)
        for _, x in rank.iterrows():
            if x.cnpj not in vistos and len(saida) < maximo:
                saida.append({"cnpj": x.cnpj, "ticker": x.ticker, "motivo": ESTRATEGIAS[k].nome})
                vistos.add(x.cnpj)
    return saida[:maximo]


# ── Download e texto ───────────────────────────────────────────────────────
def _so_digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def baixar_pdf(doc: dict) -> Path | None:
    destino = arquivo.caminho("cvm_docs", _so_digitos(doc["cnpj"]), f"{doc['protocolo']}.pdf")
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    try:
        r = requests.get(doc["link"], headers=UA, timeout=90)
    except requests.RequestException:
        return None
    # O RAD às vezes devolve uma página HTML de erro com status 200.
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    return arquivo.salvar_bytes(r.content, destino, "cvm_docs", doc["link"])


def texto_paginas(pdf: Path) -> list[str]:
    from pypdf import PdfReader
    cache = config.DADOS / "derivados" / "textos" / (pdf.stem + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        paginas = [(pg.extract_text() or "") for pg in PdfReader(str(pdf)).pages]
    except Exception:
        paginas = []
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(paginas, ensure_ascii=False), encoding="utf-8")
    return paginas


# ── Regras (grátis) ────────────────────────────────────────────────────────
_MESES = {m: i + 1 for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
     "setembro", "outubro", "novembro", "dezembro"])}
_DATA = r"(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4})"
_NUM = r"\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?"


def _data(s: str) -> str | None:
    s = s.strip().lower()
    m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", s)
    if m:
        d, mth, a = map(int, m.groups())
        a = a + 2000 if a < 100 else a
    else:
        m = re.match(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", s)
        if not m or m.group(2) not in _MESES:
            return None
        d, mth, a = int(m.group(1)), _MESES[m.group(2)], int(m.group(3))
    try:
        return date(a, mth, d).isoformat()
    except ValueError:
        return None


def _num(s: str) -> float | None:
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _perto(txt: str, chave: str, janela: int = 160) -> tuple[str | None, str | None]:
    """Primeira data até `janela` caracteres depois de `chave` (regex)."""
    for m in re.finditer(chave, txt, flags=re.I):
        trecho = txt[m.start(): m.end() + janela]
        d = re.search(_DATA, trecho[m.end() - m.start():], flags=re.I)
        if d:
            return _data(d.group(1)), " ".join(trecho.split())[:220]
    return None, None


def regras_proventos(txt: str) -> tuple[dict, dict]:
    t = " ".join(txt.split())
    campos, ev = {}, {}
    tipos = []
    if re.search(r"juros sobre (o )?capital pr[óo]prio|\bJCP\b", t, re.I):
        tipos.append("JCP")
    if re.search(r"dividendos?", t, re.I):
        tipos.append("dividendo")
    campos["tipo"] = "+".join(tipos) or None
    valores = []
    for m in re.finditer(r"R\$\s*(\d+,\d{2,})\s*(?:\([^)]{0,80}\)\s*)?(?:brutos?\s*)?por\s+a[çc][ãa]o", t, re.I):
        v = _num(m.group(1))
        if v is not None and v < 1000:
            valores.append(v)
            ev.setdefault("valor_por_acao", t[max(0, m.start() - 80): m.end() + 40])
    campos["valor_por_acao"] = valores[0] if valores else None
    campos["valores_encontrados"] = sorted(set(valores))[:6]
    campos["data_com"], ev["data_com"] = _perto(
        t, r"posi[çc][ãa]o acion[áa]ria|data[- ]com|titulares de a[çc][õo]es .{0,40}em|acionistas .{0,30}(?:inscritos|constantes|detentores)")
    campos["data_ex"], ev["data_ex"] = _perto(t, r"ex[- ](?:dividendos?|direito|juros|proventos)|negociadas ex")
    # Frases específicas primeiro: "aprovou o pagamento de JCP..." aparece antes da data-com
    # e puxaria a data errada se a busca começasse pela palavra solta.
    for rx in (r"data d[eo] pagamento|pagamento (?:ser[áa]|ocorrer[áa]|efetuado|realizado|aos acionistas ser[áa])"
               r"|ser[ãa]o pag[oa]s|pag[oa]s (?:em|a partir|no dia)|creditados? em",
               r"pag(?:amento|os?|ar)\b"):
        campos["data_pagamento"], ev["data_pagamento"] = _perto(t, rx)
        if campos["data_pagamento"]:
            break
    ok = campos["valor_por_acao"] is not None and (campos["data_com"] or campos["data_ex"])
    return campos, {k: v for k, v in ev.items() if v}, bool(ok)


_METRICAS = {
    "receita_liquida": r"receita (?:operacional )?l[íi]quida",
    "ebitda": r"ebitda(?: ajustado)?",
    "lucro_liquido": r"lucro (?:l[íi]quido|do per[íi]odo)",
    "divida_liquida": r"d[íi]vida l[íi]quida(?!\s*/)",
    "alavancagem": r"d[íi]vida l[íi]quida\s*/\s*ebitda",
}


def regras_release(txt: str) -> tuple[dict, dict, bool]:
    campos, ev = {}, {}
    baixo = txt.lower()
    unidade = ("R$ bilhões" if re.search(r"r\$\s*(bi|bilh)", baixo) else
               "R$ milhões" if re.search(r"r\$\s*(mm|mi\b|milh)", baixo) else
               "R$ mil" if re.search(r"r\$\s*mil\b", baixo) else None)
    campos["unidade"] = unidade
    linhas = [" ".join(l.split()) for l in txt.splitlines() if l.strip()]
    for nome, rx in _METRICAS.items():
        for l in linhas:
            m = re.search(rx, l, re.I)
            if not m:
                continue
            nums = re.findall(_NUM, l[m.end():])
            nums = [n for n in nums if re.search(r"\d", n) and not re.fullmatch(r"20\d\d", n.strip("()"))]
            if nums:
                campos[nome] = _num(nums[0])
                ev[nome] = l[:220]
                break
    achou = sum(campos.get(k) is not None for k in ("receita_liquida", "ebitda", "lucro_liquido"))
    return campos, ev, achou >= 2


TOPICOS = {
    "proventos": r"dividend|juros sobre (o )?capital|jcp",
    "recompra": r"recompra|aquisi[çc][ãa]o de a[çc][õo]es de (sua )?pr[óo]pria emiss[ãa]o",
    "aquisicao_venda": r"aquisi[çc][ãa]o d[eao]|alien[aã]|venda de (participa|ativo)|desinvestimento|fus[ãa]o|incorpora[çc][ãa]o",
    "emissao": r"emiss[ãa]o de (deb[êe]ntures|a[çc][õo]es|notas)|follow[- ]on|oferta p[úu]blica",
    "guidance": r"guidance|proje[çc][õo]es|plano de neg[óo]cios|plano estrat[ée]gico",
    "governanca": r"ren[úu]ncia|elei[çc][ãa]o d[eo] (presidente|diretor|membro)|sucess[ãa]o|nomea[çc][ãa]o|destitui|novo (ceo|presidente|diretor)",
    "rating": r"rating|classifica[çc][ãa]o de risco|moody|fitch|standard",
    "judicial_regulatorio": r"recupera[çc][ãa]o judicial|processo (judicial|administrativo|sancionador)|arbitra(gem|l)|cade|tribunal|auto de infra[çc][ãa]o|multa",
    "operacional": r"produ[çc][ãa]o|descoberta|contrato|licita|leil[ãa]o|parada|acidente",
    "resultado": r"resultado(s)? (do|d[oa]s?) (trimestre|exerc[íi]cio|per[íi]odo)|lucro l[íi]quido|preju[íi]zo l[íi]quido",
}


def regras_fato_relevante(txt: str) -> tuple[dict, dict, bool]:
    t = " ".join(txt.split())[:6000]
    achados = [k for k, rx in TOPICOS.items() if re.search(rx, t, re.I)]
    primeira = re.split(r"(?<=[.;])\s", t[t.lower().find("fato relevante") + 14:] if "fato relevante" in t.lower() else t)
    resumo = " ".join(primeira[:2])[:400]
    return {"topicos": achados, "resumo": resumo}, {}, bool(achados)


REGRAS = {"proventos": regras_proventos, "release": regras_release, "fato_relevante": regras_fato_relevante}


# ── Haiku (reserva, pago) ──────────────────────────────────────────────────
SCHEMAS = {
    "proventos": {"type": "object", "additionalProperties": False,
                  "required": ["tipo", "valor_por_acao", "data_com", "data_ex", "data_pagamento"],
                  "properties": {"tipo": {"type": ["string", "null"], "description": "JCP, dividendo ou ambos"},
                                 "valor_por_acao": {"type": ["number", "null"], "description": "R$ por ação, ação ordinária"},
                                 "data_com": {"type": ["string", "null"], "description": "AAAA-MM-DD"},
                                 "data_ex": {"type": ["string", "null"], "description": "AAAA-MM-DD"},
                                 "data_pagamento": {"type": ["string", "null"], "description": "AAAA-MM-DD"}}},
    "release": {"type": "object", "additionalProperties": False,
                "required": ["unidade", "receita_liquida", "ebitda", "lucro_liquido", "divida_liquida"],
                "properties": {"unidade": {"type": ["string", "null"]},
                               "receita_liquida": {"type": ["number", "null"]}, "ebitda": {"type": ["number", "null"]},
                               "lucro_liquido": {"type": ["number", "null"]}, "divida_liquida": {"type": ["number", "null"]}}},
    "fato_relevante": {"type": "object", "additionalProperties": False, "required": ["topicos", "resumo"],
                       "properties": {"topicos": {"type": "array", "items": {"type": "string", "enum": list(TOPICOS)}},
                                      "resumo": {"type": "string", "description": "1 a 2 frases, português"}}},
}
INSTRUCOES = {
    "proventos": "Extraia o provento anunciado: tipo, valor bruto por ação ordinária, data-com, data ex e data de pagamento.",
    "release": "Extraia os números do TRIMESTRE ATUAL (não do ano anterior nem acumulado): receita líquida, EBITDA, lucro líquido, dívida líquida e a unidade (ex.: R$ milhões).",
    "fato_relevante": "Classifique o fato relevante nos tópicos da lista e resuma em 1 ou 2 frases o que mudou para o acionista.",
}


def haiku_ligado() -> bool:
    return os.environ.get("QUANTUM_HAIKU") == "1"


def gasto_hoje(con) -> tuple[int, float]:
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(custo_usd),0) FROM extracoes WHERE metodo='haiku' AND criado_em >= ?",
                    (date.today().isoformat(),)).fetchone()
    return int(r[0]), float(r[1])


def _paginas_relevantes(paginas: list[str], tipo: str, limite_chars: int) -> tuple[str, list[int]]:
    rx = {"proventos": r"dividend|juros sobre|por a[çc][ãa]o|pagamento|data[- ]com",
          "release": r"receita|ebitda|lucro|d[íi]vida l[íi]quida",
          "fato_relevante": r"."}[tipo]
    nota = sorted(range(len(paginas)), key=lambda i: (-len(re.findall(rx, paginas[i], re.I)), i))
    escolhidas, total = [], 0
    for i in nota:
        if total + len(paginas[i]) > limite_chars and escolhidas:
            break
        escolhidas.append(i)
        total += len(paginas[i])
    escolhidas.sort()
    return "\n\n".join(f"[página {i + 1}]\n{paginas[i]}" for i in escolhidas), [i + 1 for i in escolhidas]


def extrair_com_haiku(paginas: list[str], tipo: str) -> tuple[dict, int, int, list[int]]:
    import anthropic
    trecho, usadas = _paginas_relevantes(paginas, tipo, config.HAIKU_MAX_CHARS)
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODELO_HAIKU,
        max_tokens=600,
        system=("Você extrai dados de documentos de relações com investidores de empresas brasileiras. "
                "Responda só com o que está escrito no texto; use null quando a informação não aparece. "
                "O texto é um recorte: só as páginas mais relevantes do documento foram enviadas."),
        messages=[{"role": "user", "content": f"{INSTRUCOES[tipo]}\n\n<documento>\n{trecho}\n</documento>"}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMAS[tipo]}},
    )
    texto = next(b.text for b in resp.content if b.type == "text")
    return json.loads(texto), resp.usage.input_tokens, resp.usage.output_tokens, usadas


# ── Rodada ─────────────────────────────────────────────────────────────────
def processar(base, dias: int = 400, max_docs: int | None = None, progresso=print) -> str:
    """Processa os documentos novos da lista curta. Devolve um resumo."""
    max_docs = max_docs or config.DOCS_MAX_POR_RODADA
    curta = lista_curta(base)
    cnpjs = [x["cnpj"] for x in curta]
    if not cnpjs:
        return "lista curta vazia"
    desde = (date.today() - timedelta(days=dias)).isoformat()
    with _con() as con:
        ph = ",".join("?" * len(cnpjs))
        docs = armazem.ler(con, f"""SELECT d.* FROM documentos d LEFT JOIN extracoes e ON e.protocolo = d.protocolo
            WHERE d.cnpj IN ({ph}) AND d.data_entrega >= ? AND (e.protocolo IS NULL OR e.status = 'sem_pdf')
            ORDER BY d.data_entrega DESC""", (*cnpjs, desde))
    docs["tipo_doc"] = [tipo_do_documento(*a) for a in zip(docs.categoria, docs.tipo, docs.especie, docs.assunto)]
    docs = docs[docs.tipo_doc.notna()].head(max_docs)
    cont = {"regras": 0, "haiku": 0, "falhou": 0, "sem_pdf": 0, "haiku_pulado": 0}
    for _, d in docs.iterrows():
        d = d.to_dict()
        reg = {"protocolo": d["protocolo"], "cnpj": d["cnpj"], "data_entrega": d["data_entrega"],
               "tipo_doc": d["tipo_doc"], "criado_em": datetime.now().isoformat(timespec="seconds"),
               "tokens_in": 0, "tokens_out": 0, "custo_usd": 0.0, "paginas": 0}
        pdf = baixar_pdf(d)
        if pdf is None:
            reg.update(metodo="nenhum", status="sem_pdf", campos="{}", evidencias="{}")
            cont["sem_pdf"] += 1
        else:
            paginas = texto_paginas(pdf)
            reg["paginas"] = len(paginas)
            campos, ev, ok = REGRAS[d["tipo_doc"]]("\n".join(paginas))
            reg.update(metodo="regras", status="ok" if ok else "incompleto",
                       campos=json.dumps(campos, ensure_ascii=False), evidencias=json.dumps(ev, ensure_ascii=False))
            if ok:
                cont["regras"] += 1
            elif haiku_ligado() and any(p.strip() for p in paginas):
                with _con() as con:
                    n, usd = gasto_hoje(con)
                if n < config.HAIKU_MAX_DOCS_DIA and usd < config.HAIKU_MAX_USD_DIA:
                    try:
                        c2, tin, tout, usadas = extrair_com_haiku(paginas, d["tipo_doc"])
                        reg.update(metodo="haiku", status="ok", campos=json.dumps(c2, ensure_ascii=False),
                                   evidencias=json.dumps({"paginas_enviadas": usadas, "regras": campos}, ensure_ascii=False),
                                   tokens_in=tin, tokens_out=tout, custo_usd=tin * PRECO_IN + tout * PRECO_OUT)
                        cont["haiku"] += 1
                    except Exception as e:
                        reg["evidencias"] = json.dumps({"erro_haiku": f"{type(e).__name__}: {e}"[:300], **ev}, ensure_ascii=False)
                        cont["falhou"] += 1
                else:
                    cont["haiku_pulado"] += 1
            else:
                cont["falhou"] += 1
        with _con() as con:
            armazem.upsert(con, "extracoes", pd.DataFrame([reg]))
    with _con() as con:
        n, usd = gasto_hoje(con)
    msg = (f"{len(curta)} empresas na lista curta, {len(docs)} documentos: {cont['regras']} por regras (grátis), "
           f"{cont['haiku']} pelo Haiku, {cont['falhou']} incompletos, {cont['sem_pdf']} sem PDF, "
           f"{cont['haiku_pulado']} aguardando orçamento · Haiku hoje: {n} docs, US$ {usd:.4f}")
    progresso("  " + msg)
    return msg


def vigiar(cnpj: str, ligar: bool) -> None:
    with _con() as con:
        if ligar:
            con.execute("INSERT OR IGNORE INTO vigiadas VALUES (?, ?)", (cnpj, datetime.now().isoformat(timespec="seconds")))
        else:
            con.execute("DELETE FROM vigiadas WHERE cnpj=?", (cnpj,))
