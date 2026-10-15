"""Painel web do Quantum — FastAPI + Jinja2 + HTMX + Plotly (sem SPA).

Rodar:  .\\.venv\\Scripts\\python.exe -m quantum servir   →  http://127.0.0.1:8100
"""
from __future__ import annotations

import csv
import json
import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import armazem, config, estudos, metricas, pipeline
from ..backtest import rodar
from ..base import base_atual
from ..estrategias import ESTRATEGIAS, INDICADORES

AQUI = Path(__file__).parent
app = FastAPI(title="Quantum")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
tpl = Jinja2Templates(directory=AQUI / "templates")


# ── formatação BR ──────────────────────────────────────────────────────────
def _vazio(x) -> bool:
    if isinstance(x, bool) or not isinstance(x, (int, float, np.integer, np.floating)):
        return True  # None, Undefined do Jinja, texto
    return math.isnan(x) or math.isinf(x)


def f_pct(x, casas=1):
    return "—" if _vazio(x) else f"{x * 100:,.{casas}f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def f_num(x, casas=2):
    return "—" if _vazio(x) else f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def f_brl(x):
    if _vazio(x):
        return "—"
    a = abs(x)
    for lim, suf in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if a >= lim:
            return "R$ " + f_num(x / lim, 1) + suf
    return "R$ " + f_num(x, 0)


def f_bytes(x):
    x = float(x or 0)
    for suf in ("B", "KB", "MB", "GB"):
        if x < 1024:
            return f"{x:.0f} {suf}" if suf == "B" else f_num(x, 1) + f" {suf}"
        x /= 1024
    return f_num(x, 1) + " TB"


tpl.env.filters.update(pct=f_pct, num=f_num, brl=f_brl, bytes=f_bytes)
tpl.env.globals.update(PERIODOS=config.PERIODOS, INDICADORES=INDICADORES, ESTRATEGIAS=ESTRATEGIAS)


def _v(nome: str) -> str:
    p = AQUI / "static" / nome
    return str(int(p.stat().st_mtime)) if p.exists() else "0"


tpl.env.globals["v"] = _v


def render(req: Request, _tpl: str, pagina: str = "", **ctx):
    return tpl.TemplateResponse(req, _tpl, {"pagina": pagina, **ctx})


def _json_seguro(o):
    return json.loads(json.dumps(o, default=lambda x: None if _vazio(x) else str(x)).replace("NaN", "null"))


def _base_ou_none():
    try:
        b = base_atual()
        return b if len(b.datas) else None
    except Exception:
        return None


def _virgem_revelado() -> bool:
    with armazem.conexao() as con:
        return armazem.periodo_revelado(con, "VIRGEM")


def _fim_permitido(b) -> pd.Timestamp:
    """Sem revelar o VIRGEM, nada roda depois do fim do OOS."""
    if _virgem_revelado():
        return b.datas[-1]
    return min(pd.Timestamp(config.PERIODO["OOS"].fim), b.datas[-1])


# ── Painel ─────────────────────────────────────────────────────────────────
def _status() -> dict:
    with armazem.conexao() as con:
        q = lambda s: con.execute(s).fetchone()[0]
        st = {
            "empresas": q("SELECT COUNT(*) FROM empresas"),
            "tickers": q("SELECT COUNT(*) FROM tickers"),
            "demonstracoes": q("SELECT COUNT(*) FROM demonstracoes"),
            "documentos": q("SELECT COUNT(*) FROM documentos"),
            "tickers_preco": q("SELECT COUNT(DISTINCT ticker) FROM precos"),
            "ultimo_preco": q("SELECT MAX(data) FROM precos"),
            "ultimo_balanco": q("SELECT MAX(dt_receb) FROM demonstracoes"),
        }
        st["execucoes"] = armazem.ler(con, "SELECT * FROM execucoes ORDER BY id DESC LIMIT 12").fillna("").to_dict("records")
    st["em_curso"] = pipeline.tarefas_em_curso()
    return st


def _ultima_rodada(rodada: str = "") -> tuple[str | None, list[dict]]:
    with armazem.conexao() as con:
        r = rodada or con.execute("SELECT MAX(rodada) FROM estudos WHERE tipo='protocolo'").fetchone()[0]
        if not r:
            return None, []
        df = armazem.ler(con, "SELECT id, estrategia, resultado FROM estudos WHERE rodada=? AND tipo='protocolo'", (r,))
    linhas = []
    for _, x in df.iterrows():
        e = json.loads(x.resultado)
        e["id"] = int(x.id)
        linhas.append(e)
    ordem = {"confirmada": 0, "promissora, sem significância": 1, "não confirmada": 2}
    linhas.sort(key=lambda e: (ordem.get(e.get("veredito"), 3),
                               -(e["periodos"].get("OOS", {}).get("resumo", {}).get("sharpe") or -9)))
    return r, linhas


@app.get("/", response_class=HTMLResponse)
def painel(req: Request):
    rodada, linhas = _ultima_rodada()
    return render(req, "painel.html", "painel", st=_status(), rodada=rodada, linhas=linhas,
                  virgem=_virgem_revelado())


@app.get("/parcial/status", response_class=HTMLResponse)
def parcial_status(req: Request):
    return render(req, "parciais/status.html", st=_status())


@app.post("/atualizar", response_class=HTMLResponse)
def atualizar(req: Request, estudar: str = Form("1")):
    pipeline.em_segundo_plano("atualizacao_completa", lambda: pipeline.atualizar_tudo(estudar=estudar == "1"))
    return render(req, "parciais/status.html", st=_status())


# ── Empresas ───────────────────────────────────────────────────────────────
def _tabela_empresas(b) -> pd.DataFrame:
    p = b.painel(b.datas[-1]).copy()
    emp = b.empresas.reset_index()[["cnpj", "nome", "nome_comercial", "setor", "site_ri"]].fillna("")
    return p.merge(emp, on="cnpj", how="left").fillna({"nome": "", "nome_comercial": "", "setor": "", "site_ri": ""})


@app.get("/empresas", response_class=HTMLResponse)
def empresas(req: Request):
    b = _base_ou_none()
    setores = sorted(b.empresas.setor.dropna().unique()) if b else []
    return render(req, "empresas.html", "empresas", setores=setores, sem_dados=b is None)


COLS_EMPRESAS = ("mcap", "liquidez", "pl_ind", "pvp", "ev_ebit", "roe", "roic", "margem_liquida",
                 "dy", "dy_med_3a", "mom_12_1", "vol_1a")


@app.get("/parcial/empresas", response_class=HTMLResponse)
def parcial_empresas(req: Request, q: str = "", setor: str = "", ordem: str = "liquidez",
                     desc: int = 1, liq_min: float = 0):
    b = _base_ou_none()
    if b is None:
        return HTMLResponse("<p class='vazio'>Sem dados. Rode a atualização no Painel.</p>")
    df = _tabela_empresas(b)
    if q:
        m = df.ticker.str.contains(q.upper(), na=False) | df.nome.fillna("").str.contains(q, case=False) \
            | df.nome_comercial.fillna("").str.contains(q, case=False)
        df = df[m]
    if setor:
        df = df[df.setor == setor]
    if liq_min:
        df = df[df.liquidez >= liq_min]
    if ordem in df:
        df = df.sort_values(ordem, ascending=not desc, na_position="last")
    return render(req, "parciais/empresas_linhas.html", linhas=df.head(400).to_dict("records"),
                  total=len(df), data=b.datas[-1].date(), cols=COLS_EMPRESAS, ordem=ordem, desc=desc)


# ── Análise de uma empresa ─────────────────────────────────────────────────
@app.get("/empresa/{ticker}", response_class=HTMLResponse)
def empresa(req: Request, ticker: str):
    b = _base_ou_none()
    if b is None:
        return RedirectResponse("/")
    ticker = ticker.upper()
    cnpj = b.ticker_cnpj.get(ticker)
    if cnpj is None:
        return render(req, "vazio.html", "empresas", msg=f"Ticker {ticker} não encontrado na base.")
    info = b.empresas.loc[cnpj].fillna("").to_dict() if cnpj in b.empresas.index else {}
    p = b.painel(b.datas[-1])
    linha = p[p.cnpj == cnpj].to_dict("records")
    linha = linha[0] if linha else {}
    # posição em cada estratégia hoje
    ranks = []
    for e in ESTRATEGIAS.values():
        r = e.ranquear(p, config.PREMISSAS.liquidez_min).reset_index(drop=True)
        pos = r.index[r.cnpj == cnpj]
        ranks.append({"chave": e.chave, "nome": e.nome, "pos": int(pos[0]) + 1 if len(pos) else None,
                      "total": len(r), "nota": float(r.nota.iloc[pos[0]]) if len(pos) else None})
    with armazem.conexao() as con:
        docs = armazem.ler(con, "SELECT * FROM documentos WHERE cnpj=? ORDER BY data_entrega DESC LIMIT 200", (cnpj,))
    outros = b.tickers[b.tickers.cnpj == cnpj].ticker.tolist()
    return render(req, "empresa.html", "empresas", ticker=ticker, cnpj=cnpj, info=info, ind=linha,
                  ranks=ranks, docs=docs.to_dict("records"), outros=outros,
                  categorias=sorted(docs.categoria.dropna().unique()),
                  balancos_ligado=all(os.environ.get(v) for v in config.BALANCOS_VARS))


@app.get("/api/empresa/{ticker}")
def api_empresa(ticker: str):
    b = base_atual()
    ticker = ticker.upper()
    cnpj = b.ticker_cnpj.get(ticker)
    px = b.adj[ticker].dropna() if ticker in b.adj else pd.Series(dtype=float)
    ib = b.ibov.reindex(px.index).ffill()
    sem = pd.DataFrame({"acao": px / px.iloc[0], "ibov": ib / ib.iloc[0]}).resample("W-FRI").last() if len(px) else pd.DataFrame()
    dem = b.dem[b.dem.cnpj == cnpj].sort_values("dt_refer")
    divs = b.div[ticker][b.div[ticker] > 0] if ticker in b.div else pd.Series(dtype=float)
    div_ano = divs.groupby(divs.index.year).sum()
    # múltiplos ao longo do tempo, só desta empresa (regras idênticas às do painel)
    mh = b.multiplos_historicos(cnpj, ticker) if cnpj else pd.DataFrame()
    fin = bool(b.empresas.financeira.get(cnpj, 0)) if cnpj else False
    if fin and len(mh):
        mh["ev_ebit"] = None
    hist = mh.to_dict("records")
    return JSONResponse(_json_seguro({
        "preco": {"datas": [d.strftime("%Y-%m-%d") for d in sem.index],
                  "acao": sem.get("acao", pd.Series()).round(4).tolist(),
                  "ibov": sem.get("ibov", pd.Series()).round(4).tolist()},
        "fund": {"datas": dem.dt_refer.dt.strftime("%Y-%m-%d").tolist(),
                 **{c: dem[c].tolist() for c in ("receita", "ebit", "lucro_contr", "fco", "pl_contr", "divida", "caixa")}},
        "divs": {"anos": [int(a) for a in div_ano.index], "valor": div_ano.round(4).tolist()},
        "multiplos": hist,
    }))


# ── Estratégias ────────────────────────────────────────────────────────────
@app.get("/estrategias", response_class=HTMLResponse)
def estrategias(req: Request, n: int = 15):
    b = _base_ou_none()
    cart = {}
    if b is not None:
        p = b.painel(b.datas[-1])
        for e in ESTRATEGIAS.values():
            cart[e.chave] = e.ranquear(p, config.PREMISSAS.liquidez_min).head(n).to_dict("records")
    rodada, linhas = _ultima_rodada()
    vered = {l["estrategia"]: l for l in linhas}
    return render(req, "estrategias.html", "estrategias", cart=cart, n=n, vered=vered,
                  data=b.datas[-1].date() if b is not None else None)


# ── Estudos ────────────────────────────────────────────────────────────────
@app.get("/estudos", response_class=HTMLResponse)
def estudos_pg(req: Request, rodada: str = ""):
    with armazem.conexao() as con:
        rodadas = armazem.ler(con, "SELECT rodada, COUNT(*) n, MIN(criado_em) criado FROM estudos "
                                   "WHERE tipo='protocolo' GROUP BY rodada ORDER BY rodada DESC")
    rodada, linhas = _ultima_rodada(rodada)
    return render(req, "estudos.html", "estudos", rodadas=rodadas.to_dict("records"), rodada=rodada,
                  linhas=linhas, virgem=_virgem_revelado(), em_curso=pipeline.tarefas_em_curso(),
                  q=config.FDR_Q, sorteios=config.PREMISSAS.n_sorteios_nulo)


@app.post("/estudos/rodar", response_class=HTMLResponse)
def estudos_rodar(req: Request):
    ok = pipeline.em_segundo_plano("estudos", lambda: pipeline._etapa(
        "estudos", lambda p: "rodada " + estudos.rodada(progresso=p)))
    msg = "Rodada iniciada em segundo plano. Leva alguns minutos; a página mostra o resultado quando terminar." \
        if ok else "Já existe uma rodada em andamento."
    return HTMLResponse(f"<p class='aviso'>{msg}</p>")


@app.get("/estudo/{id_}", response_class=HTMLResponse)
def estudo(req: Request, id_: int):
    with armazem.conexao() as con:
        x = con.execute("SELECT rodada, resultado, params FROM estudos WHERE id=?", (id_,)).fetchone()
    if not x:
        return render(req, "vazio.html", "estudos", msg="Estudo não encontrado.")
    e = json.loads(x[1])
    return render(req, "estudo.html", "estudos", e=e, rodada=x[0], params=json.loads(x[2]), id_=id_,
                  e_json=json.dumps(_json_seguro(e), ensure_ascii=False))


@app.post("/virgem/revelar", response_class=HTMLResponse)
def virgem_revelar(req: Request, motivo: str = Form(...), confirmo: str = Form("")):
    if confirmo.strip().upper() != "REVELAR" or len(motivo.strip()) < 10:
        return HTMLResponse("<p class='aviso'>Digite REVELAR e um motivo (10+ caracteres).</p>")
    estudos.revelar_virgem(motivo.strip())
    return HTMLResponse("<p class='aviso'>Período VIRGEM revelado e registrado. A próxima rodada de estudos o inclui.</p>")


# ── Backtest livre ─────────────────────────────────────────────────────────
@app.get("/backtest", response_class=HTMLResponse)
def backtest_pg(req: Request):
    b = _base_ou_none()
    fim = _fim_permitido(b).date() if b is not None else None
    return render(req, "backtest.html", "backtest", fim_max=fim, virgem=_virgem_revelado(),
                  premissas=config.PREMISSAS, sem_dados=b is None)


@app.post("/backtest", response_class=HTMLResponse)
def backtest_rodar(req: Request, estrategia: str = Form(...), n: int = Form(10), meses: int = Form(3),
                   periodo: str = Form("IS"), liquidez_min: float = Form(config.PREMISSAS.liquidez_min),
                   custo_lado: float = Form(config.PREMISSAS.custo_lado * 100)):
    b = base_atual()
    if periodo == "VIRGEM" and not _virgem_revelado():
        return HTMLResponse("<p class='aviso'>O período VIRGEM está trancado. Revele-o em Estudos primeiro.</p>")
    per = config.PERIODO[periodo] if periodo in config.PERIODO else None
    ini = pd.Timestamp(per.inicio) if per else pd.Timestamp(config.PERIODO["IS"].inicio)
    fim = min(pd.Timestamp(per.fim), b.datas[-1]) if per else _fim_permitido(b)
    t0 = time.time()
    est = ESTRATEGIAS[estrategia]
    r = rodar(b, est, n, meses, ini, fim, liquidez_min=liquidez_min, custo_lado=custo_lado / 100)
    m = metricas.calcular(r.serie, b.ibov, b.cdi, r.operacoes, r.giro)
    serie = estudos._serie_json(r, b)
    dd = (r.serie / r.serie.cummax() - 1).resample("W-FRI").min()
    cart = r.carteiras.copy()
    cart["data_decisao"] = cart.data_decisao.dt.strftime("%Y-%m-%d")
    ops = r.operacoes.copy()
    por_data = []
    for d, g in cart.groupby("data_decisao"):
        rr = ops[ops.entrada == pd.Timestamp(g.data_execucao.iloc[0])].set_index("ticker").retorno
        por_data.append({"data": d, "acoes": [{"ticker": t, "ret": rr.get(t)} for t in g.ticker]})
    graf = {"serie": serie, "dd": {"datas": [x.strftime("%Y-%m-%d") for x in dd.index], "v": dd.round(4).tolist()},
            "anual": m["rentabilidade"]["anual"]}
    return render(req, "parciais/backtest_resultado.html", m=m, est=est, params=r.params, periodo=periodo,
                  carteiras=por_data[::-1], graf=json.dumps(_json_seguro(graf)), segundos=time.time() - t0)


# ── Fatores ────────────────────────────────────────────────────────────────
@app.get("/fatores", response_class=HTMLResponse)
def fatores_pg(req: Request):
    return render(req, "fatores.html", "fatores", virgem=_virgem_revelado())


@app.post("/fatores", response_class=HTMLResponse)
def fatores_rodar(req: Request, coluna: str = Form(...), direcao: str = Form("maior"),
                  periodo: str = Form("IS"), meses: int = Form(3)):
    if periodo == "VIRGEM" and not _virgem_revelado():
        return HTMLResponse("<p class='aviso'>O período VIRGEM está trancado.</p>")
    b = base_atual()
    res = estudos.estudo_fator(b, coluna, direcao == "maior", periodo, 5, meses)
    return render(req, "parciais/fator_resultado.html", res=res, graf=json.dumps(_json_seguro(res)),
                  nome=INDICADORES.get(coluna, (coluna,))[0], direcao=direcao)


# ── Fontes (gerenciamento) ─────────────────────────────────────────────────
def _manifesto() -> pd.DataFrame:
    if not config.MANIFESTO.exists():
        return pd.DataFrame(columns=["caminho", "fonte", "url", "coletado_em", "bytes", "sha256", "grupo", "nome"])
    df = pd.read_csv(config.MANIFESTO, dtype=str)
    partes = df.caminho.str.split("/")
    df["grupo"] = partes.str[2]
    df["nome"] = partes.str[-1]
    df["bytes"] = pd.to_numeric(df.bytes)
    return df


def _pasta_fonte(f) -> tuple[str, str]:
    fonte, _, grupo = f.pasta.partition("/")
    return fonte, grupo


@app.get("/fontes", response_class=HTMLResponse)
def fontes_pg(req: Request):
    man = _manifesto()
    with armazem.conexao() as con:
        ex = armazem.ler(con, "SELECT etapa, MAX(fim) fim, status, mensagem FROM execucoes "
                              "WHERE etapa LIKE 'fonte:%' GROUP BY etapa").fillna("")
    ult = {r.etapa.split(":", 1)[1]: r for r in ex.itertuples()}
    cards = []
    for f in pipeline.FONTES.values():
        fonte, grupo = _pasta_fonte(f)
        m = man[(man.fonte == fonte) & ((man.grupo == grupo) if grupo else True)]
        e = ult.get(f.chave)
        cards.append({"f": f, "arquivos": len(m), "bytes": int(m.bytes.sum()) if len(m) else 0,
                      "ultima_coleta": m.coletado_em.max() if len(m) else None,
                      "ultima_exec": e.fim if e else None, "status": e.status if e else None,
                      "mensagem": (e.mensagem or "").splitlines()[0] if e and e.mensagem else ""})
    grupos = sorted(man.grupo.dropna().unique())
    return render(req, "fontes.html", "fontes", cards=cards, grupos=grupos,
                  em_curso=pipeline.tarefas_em_curso(), total=len(man), total_bytes=int(man.bytes.sum()) if len(man) else 0)


@app.post("/fontes/{chave}/atualizar", response_class=HTMLResponse)
def fonte_atualizar(req: Request, chave: str):
    if chave not in pipeline.ETAPAS:
        return HTMLResponse("<span class='aviso'>fonte desconhecida</span>")
    ok = pipeline.em_segundo_plano(f"fonte:{chave}", lambda: pipeline.atualizar_fonte(chave))
    txt = "baixando em segundo plano…" if ok else "já em andamento"
    return HTMLResponse(f"<span class='aviso' hx-get='/parcial/fonte/{chave}' hx-trigger='load delay:5s' "
                        f"hx-swap='outerHTML'>{txt}</span>")


@app.get("/parcial/fonte/{chave}", response_class=HTMLResponse)
def parcial_fonte(chave: str):
    if f"fonte:{chave}" in pipeline.tarefas_em_curso():
        return HTMLResponse(f"<span class='aviso' hx-get='/parcial/fonte/{chave}' hx-trigger='load delay:5s' "
                            f"hx-swap='outerHTML'>baixando…</span>")
    with armazem.conexao() as con:
        r = con.execute("SELECT status, mensagem, fim FROM execucoes WHERE etapa=? ORDER BY id DESC LIMIT 1",
                        (f"fonte:{chave}",)).fetchone()
    if not r:
        return HTMLResponse("<span>—</span>")
    cls = "ok" if r[0] == "ok" else "erro"
    return HTMLResponse(f"<span class='{cls}'>{r[0]} · {r[2]} · {(r[1] or '').splitlines()[0]}</span>")


@app.get("/parcial/arquivos", response_class=HTMLResponse)
def parcial_arquivos(req: Request, fonte: str = "", grupo: str = "", q: str = "", desde: str = "",
                     ordem: str = "caminho", pagina: int = 1):
    man = _manifesto()
    if fonte:
        f = pipeline.FONTES.get(fonte)
        if f:
            fo, gr = _pasta_fonte(f)
            man = man[(man.fonte == fo) & ((man.grupo == gr) if gr else True)]
    if grupo:
        man = man[man.grupo == grupo]
    if q:
        man = man[man.nome.str.contains(q, case=False, na=False)]
    if desde:
        man = man[man.coletado_em >= desde]
    asc = ordem != "coletado_em" and ordem != "bytes"
    man = man.sort_values(ordem if ordem in man else "caminho", ascending=asc)
    por = 100
    total = len(man)
    pag = man.iloc[(pagina - 1) * por: pagina * por]
    return render(req, "parciais/arquivos.html", linhas=pag.to_dict("records"), total=total,
                  total_bytes=int(man.bytes.sum()) if total else 0, pagina=pagina,
                  paginas=max(1, -(-total // por)))


# ── Atualização automática diária enquanto o servidor estiver no ar ────────
def _agendador():
    while True:
        try:
            agora = datetime.now()
            if agora.hour >= config.HORA_ATUALIZACAO and agora.weekday() < 5:
                with armazem.conexao() as con:
                    r = con.execute("SELECT MAX(inicio) FROM execucoes WHERE etapa='fonte:yahoo'").fetchone()[0]
                if not r or r[:10] < agora.strftime("%Y-%m-%d"):
                    pipeline.em_segundo_plano("atualizacao_completa", lambda: pipeline.atualizar_tudo(estudar=True))
        except Exception:
            pass
        time.sleep(600)


@app.on_event("startup")
def _inicio():
    if os.environ.get("QUANTUM_AUTO", "1") == "1":
        threading.Thread(target=_agendador, daemon=True, name="quantum-agendador").start()


# ── Documentos do RI (extração grátis por regras; Haiku de reserva) ────────
from .. import documentos as docs_mod  # noqa: E402


@app.get("/documentos", response_class=HTMLResponse)
def documentos_pg(req: Request):
    b = _base_ou_none()
    curta = docs_mod.lista_curta(b) if b is not None else []
    con = docs_mod._con()
    try:
        n, usd = docs_mod.gasto_hoje(con)
        stats = armazem.ler(con, "SELECT metodo, status, COUNT(*) n, SUM(custo_usd) custo FROM extracoes GROUP BY metodo, status")
        total_usd = con.execute("SELECT COALESCE(SUM(custo_usd),0) FROM extracoes").fetchone()[0]
    finally:
        con.close()
    nomes = b.empresas.nome_comercial.fillna(b.empresas.nome).to_dict() if b is not None else {}
    for x in curta:
        x["nome"] = nomes.get(x["cnpj"], "")
    return render(req, "documentos.html", "documentos", curta=curta, stats=stats.fillna(0).to_dict("records"),
                  haiku=docs_mod.haiku_ligado(), n_hoje=n, usd_hoje=usd, total_usd=total_usd,
                  tetos=(config.HAIKU_MAX_DOCS_DIA, config.HAIKU_MAX_USD_DIA),
                  em_curso=pipeline.tarefas_em_curso())


@app.get("/parcial/extracoes", response_class=HTMLResponse)
def parcial_extracoes(req: Request, q: str = "", tipo: str = "", metodo: str = "", status: str = "", cnpj: str = ""):
    con = docs_mod._con()
    try:
        df = armazem.ler(con, """SELECT e.*, d.assunto, d.link, d.categoria FROM extracoes e
                                 JOIN documentos d ON d.protocolo = e.protocolo ORDER BY e.data_entrega DESC""")
    finally:
        con.close()
    b = _base_ou_none()
    if b is not None:
        tk = b.tickers.drop_duplicates("cnpj").set_index("cnpj").ticker
        df["ticker"] = df.cnpj.map(tk)
    else:
        df["ticker"] = ""
    for col, val in (("tipo_doc", tipo), ("metodo", metodo), ("status", status), ("cnpj", cnpj)):
        if val:
            df = df[df[col] == val]
    if q:
        df = df[df.ticker.fillna("").str.contains(q.upper()) | df.assunto.fillna("").str.contains(q, case=False)]
    linhas = []
    for r in df.head(300).fillna("").to_dict("records"):
        r["campos"] = json.loads(r["campos"] or "{}")
        linhas.append(r)
    return render(req, "parciais/extracoes.html", linhas=linhas, total=len(df))


@app.post("/documentos/processar", response_class=HTMLResponse)
def documentos_processar(req: Request):
    ok = pipeline.em_segundo_plano("fonte:cvm_docs", lambda: pipeline.atualizar_fonte("cvm_docs"))
    return HTMLResponse("<span class='aviso'>" + ("processando em segundo plano…" if ok else "já em andamento") + "</span>")


@app.post("/vigiar/{ticker}", response_class=HTMLResponse)
def vigiar(ticker: str, ligar: int = Form(1)):
    b = base_atual()
    cnpj = b.ticker_cnpj.get(ticker.upper())
    if cnpj is None:
        return HTMLResponse("<span class='erro'>ticker desconhecido</span>")
    docs_mod.vigiar(cnpj, bool(ligar))
    return HTMLResponse(f"<span class='ok'>{'na lista curta (vigiada)' if ligar else 'removida das vigiadas'}</span>")


# ── Busca de combinações (busca.py) ─────────────────────────────────────────
import subprocess  # noqa: E402
import sys  # noqa: E402

_busca_proc: dict = {}


@app.get("/busca", response_class=HTMLResponse)
def busca_pg(req: Request):
    with armazem.conexao() as con:
        x = con.execute("SELECT id, rodada, resultado FROM estudos WHERE tipo='busca' ORDER BY id DESC LIMIT 1").fetchone()
    res = json.loads(x[2]) if x else None
    b = _base_ou_none()
    if res and b is not None:
        nomes = b.empresas.nome_comercial.fillna(b.empresas.nome)
        for f in res["finalistas"]:
            for c in f["carteira_hoje"]:
                c["empresa"] = str(nomes.get(c["cnpj"], ""))[:28]
    rodando = _busca_proc.get("p") is not None and _busca_proc["p"].poll() is None
    with armazem.conexao() as con:
        v = con.execute("SELECT rodada, resultado FROM estudos WHERE tipo='virgem' ORDER BY id DESC LIMIT 1").fetchone()
    virgem = json.loads(v[1]) if v else None
    return render(req, "busca.html", "busca", res=res, rodada=x[1] if x else None, rodando=rodando,
                  virgem=virgem, virgem_rodada=v[0] if v else None,
                  virgem_json=json.dumps(_json_seguro(virgem["serie"])) if virgem else "null",
                  res_json=json.dumps(_json_seguro(res), ensure_ascii=False) if res else "null")


@app.post("/busca/rodar", response_class=HTMLResponse)
def busca_rodar(req: Request):
    if _busca_proc.get("p") is not None and _busca_proc["p"].poll() is None:
        return HTMLResponse("<span class='aviso'>busca já em andamento</span>")
    log = config.DADOS / "busca_ultima.log"
    _busca_proc["p"] = subprocess.Popen([sys.executable, "-m", "quantum.busca"], cwd=str(config.RAIZ.parent),
                                        stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    return HTMLResponse("<span class='aviso'>busca iniciada (~10 min). Recarregue a página ao fim; log em quantum/dados/busca_ultima.log</span>")
