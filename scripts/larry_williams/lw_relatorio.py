"""Escolha (SO' no IS), leitura unica do OOS, checagem de eixo morto e geracao do relatorio.

Entrada: `_resultados/<SETUP>/<ATIVO>.npz` (gerados por `lw_sweep.py`).
Saidas: RELATORIO.md, params_recomendados.json, universo_acoes.csv, ref_trades/*.csv.

Disciplina IS/OOS: toda a escolha (`escolhe_no_is`) le' SO' as fatias `[:, :, :, IS, :]`; o OOS
(`le_oos`) e' aberto UMA vez por (setup, classe), para a celula ja' escolhida.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import lw_dados as D  # noqa: E402
import lw_setups as S  # noqa: E402
import lw_sim as M  # noqa: E402
import lw_sweep as W  # noqa: E402
from backtest.intraday.report import LinhaResultado, num_br, tabela  # noqa: E402

C = {n: i for i, n in enumerate(W.COLS)}
IS, OOS = 0, 1
SLIP1 = 1

#: Criterios de elegibilidade da celula no IS (por classe).
MIN_TRADES_ATIVO = {"ACAO": 15, "ETF_BTC": 3, "WIN": 3, "WDO": 3}      # por ativo (acao) ou por semestre (futuro)
MIN_ATIVOS = {"ACAO": 12, "ETF_BTC": 2, "WIN": 3, "WDO": 3}            # ativos (ou semestres) qualificados
MIN_TRADES_TOTAL_IS = {"ACAO": 300, "ETF_BTC": 15, "WIN": 60, "WDO": 60}
MIN_SHARE_POSITIVO = 0.5
MIN_SHARE_VIZINHAS = 0.5
MIN_TRADES_OOS = {"ACAO": 300, "ETF_BTC": 15, "WIN": 40, "WDO": 40}


def carrega_unidades(setup: str, cl: str):
    uni = W.universo()[cl]
    outs, blks, nomes = [], [], []
    for a in uni:
        f = W.SAIDA_DIR / setup / f"{a}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        outs.append(z["out"])
        blks.append(z["blk"] if "blk" in z.files else None)
        nomes.append(a)
    if not outs:
        return None
    return np.stack(outs), blks, nomes


# ----------------------------------------------------------------------------
def pontuacao_is(cl: str, out: np.ndarray, blks):
    """(score, share_pos, n_qualif, n_total) por celula, usando SO' o IS a 1 tick.

    Acao/ETF: blocos = ATIVOS (mediana entre ativos de exp% por trade). Futuro: blocos =
    SEMESTRES do IS (mediana de R$/trade). Mediana, nao o melhor unico."""
    n_cel = out.shape[1]
    n_total = np.nansum(out[:, :, SLIP1, IS, C["n"]], axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if cl in ("WIN", "WDO"):
            blk = np.stack([b for b in blks if b is not None])[0]          # (cel, B, 2)
            n_b, v_b = blk[:, :, 0], blk[:, :, 1]
        else:
            n_b = out[:, :, SLIP1, IS, C["n"]].T                            # (cel, A)
            v_b = out[:, :, SLIP1, IS, C["exp_pct"]].T
        ok = n_b >= MIN_TRADES_ATIVO[cl]
        v = np.where(ok, v_b, np.nan)
        qual = ok.sum(axis=1)
        score = np.where(qual >= MIN_ATIVOS[cl], np.nanmedian(v, axis=1), np.nan)
        share = np.where(qual > 0, np.nansum(v > 0, axis=1) / np.maximum(qual, 1), np.nan)
    return score, share, qual, n_total


def vizinhas(defn, score: np.ndarray):
    """Para cada celula: (k positivas, m com dado) entre as vizinhas a UM eixo de distancia
    (mesmos demais eixos, qualquer outro valor do eixo). Metodo 'vizinhanca' do projeto."""
    shape = tuple(len(defn.eixos[n]) for n in defn.nomes_eixos)
    sc = score.reshape(shape)
    pos = (np.nan_to_num(sc, nan=-1.0) > 0).astype(int)
    val = np.isfinite(sc).astype(int)
    k = np.zeros(shape, dtype=int)
    m = np.zeros(shape, dtype=int)
    for ax in range(len(shape)):
        k += pos.sum(axis=ax, keepdims=True) - pos
        m += val.sum(axis=ax, keepdims=True) - val
    return k.reshape(-1), m.reshape(-1)


def escolhe_no_is(defn, cl: str, out: np.ndarray, blks, so_com_stop: bool = False) -> dict:
    """Escolhe a celula SO' com dados do IS. Retorna dict com a celula e o diagnostico.

    `so_com_stop=True` restringe a celulas com stop de protecao (descarta `stop=sem`): a escolha
    irrestrita tende a 'sem stop' (o IS premia o trade que nunca e' cortado), que e' risco aberto."""
    score, share, qual, n_tot = pontuacao_is(cl, out, blks)
    k, m = vizinhas(defn, score)
    frac_viz = np.where(m >= 3, k / np.maximum(m, 1), np.nan)
    base = np.isfinite(score) & (n_tot >= MIN_TRADES_TOTAL_IS[cl])
    if so_com_stop:
        base &= np.array([c['stop'][0] != 'sem' for c in defn.celulas()])
    passa = base & (score > 0) & (share >= MIN_SHARE_POSITIVO) & (frac_viz >= MIN_SHARE_VIZINHAS)
    ordem = np.argsort(-np.where(base, score, -np.inf))
    if passa.any():
        ci = int(np.flatnonzero(passa)[np.argmax(score[passa])])
        status = "APROVADA_NO_IS"
    elif base.any():
        ci = int(ordem[0])
        status = "REPROVADA_NO_IS"      # melhor celula existente, mas nao passa nos criterios
    else:
        ci, status = int(np.nanargmax(n_tot)), "SEM_DADOS_SUFICIENTES"
    topo = [int(x) for x in ordem[:5] if base[x]]
    return {"ci": ci, "cel": defn.celulas()[ci], "status": status, "score": float(score[ci]) if np.isfinite(score[ci]) else float("nan"),
            "share_pos": float(share[ci]) if np.isfinite(share[ci]) else float("nan"), "qualif": int(qual[ci]),
            "n_is": int(n_tot[ci]), "viz_k": int(k[ci]), "viz_m": int(m[ci]),
            "n_cel": int(out.shape[1]), "n_passam": int(passa.sum()), "n_base": int(base.sum()), "topo": topo,
            "score_arr": score, "viz_frac": frac_viz}


def eixos_mortos(defn, out: np.ndarray) -> dict[str, float]:
    """Item 6.25: fracao dos grupos (demais eixos fixos) em que mexer no eixo MUDA o resultado
    do IS (trades totais, liquido). 0,0 = eixo morto."""
    n = np.nansum(out[:, :, SLIP1, IS, C["n"]], axis=0)
    liq = np.nansum(out[:, :, SLIP1, IS, C["liquido"]], axis=0)
    shape = tuple(len(defn.eixos[x]) for x in defn.nomes_eixos)
    n, liq = n.reshape(shape), np.round(liq.reshape(shape), 2)
    res = {}
    for ax, nome in enumerate(defn.nomes_eixos):
        if shape[ax] == 1:
            res[nome] = float("nan")
            continue
        nm, lm = np.moveaxis(n, ax, 0), np.moveaxis(liq, ax, 0)
        difere = np.any(nm != nm[:1], axis=0) | np.any(lm != lm[:1], axis=0)
        res[nome] = float(difere.mean())
    return res


# ----------------------------------------------------------------------------
def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def agrega(cl: str, out: np.ndarray, ci: int, slip: int, jan: int) -> dict:
    """Agrega entre ativos a celula `ci` na janela `jan` (IS/OOS) a `slip`."""
    r = out[:, ci, slip, jan, :]
    n = r[:, C["n"]]
    ok = n > 0
    n_tot = float(np.nansum(n))
    win = r[:, C["win"]]
    n_win = np.nansum(np.where(ok, n * win / 100.0, 0.0))
    ganho = r[:, C["ganho_pct"]]
    perda = r[:, C["perda_pct"]]
    nw = np.where(ok, n * win / 100.0, 0.0)
    nl = np.where(ok, n - n * win / 100.0, 0.0)
    g_pool = float(np.nansum(nw * np.nan_to_num(ganho)) / max(np.nansum(nw), 1e-9))
    p_pool = float(np.nansum(nl * np.nan_to_num(perda)) / max(np.nansum(nl), 1e-9))
    be = 100.0 * p_pool / (g_pool + p_pool) if (g_pool + p_pool) > 0 else float("nan")
    ganho_brl = r[:, C["ganho_brl"]]
    perda_brl = r[:, C["perda_brl"]]
    g_b = float(np.nansum(nw * np.nan_to_num(ganho_brl)) / max(np.nansum(nw), 1e-9))
    p_b = float(np.nansum(nl * np.nan_to_num(perda_brl)) / max(np.nansum(nl), 1e-9))
    be_brl = 100.0 * p_b / (g_b + p_b) if (g_b + p_b) > 0 else float("nan")
    exp_pct = r[:, C["exp_pct"]][ok]
    lo, hi = wilson(n_win, n_tot)
    return {
        "n": int(n_tot), "ativos_com_trade": int(ok.sum()),
        "win": 100.0 * n_win / n_tot if n_tot else float("nan"), "win_ic": (lo, hi),
        "be_pct": be, "be_brl": be_brl,
        "exp_pct_mediana": float(np.nanmedian(exp_pct)) if len(exp_pct) else float("nan"),
        "share_pos": float(np.mean(exp_pct > 0)) if len(exp_pct) else float("nan"),
        "exp_brl": float(np.nansum(r[:, C["exp_brl"]] * n) / n_tot) if n_tot else float("nan"),
        "liquido_med": float(np.nanmedian(r[:, C["liquido"]])), "maxdd_med": float(np.nanmedian(r[:, C["maxdd_brl"]])),
        "n_g_med": float(np.nanmedian(r[:, C["n_g"]])), "cap_final_g_med": float(np.nanmedian(r[:, C["cap_final_g"]])),
        "pulados_med": float(np.nanmedian(r[:, C["pulados_g"]])), "cens_g": float(np.nanmean(r[:, C["cens_g"]])),
    }


def le_oos(cl: str, out: np.ndarray, ci: int) -> dict:
    """UNICA leitura do OOS por (setup, classe): a celula ja' escolhida no IS, slip 0/1/2."""
    return {s: agrega(cl, out, ci, si, OOS) for si, s in enumerate((0, 1, 2))}


def veredito(cl: str, status: str, a_oos: dict, a_is: dict) -> str:
    o = a_oos[1]
    if cl == "ETF_BTC":
        base = "AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin)"
        if o["n"] < MIN_TRADES_OOS[cl]:
            return base + f"; OOS com {o['n']} trades"
    if status == "SEM_DADOS_SUFICIENTES":
        return "SEM TRADES SUFICIENTES (inconclusivo)"
    if o["n"] < MIN_TRADES_OOS[cl]:
        return f"INCONCLUSIVO: OOS com {o['n']} trades (< {MIN_TRADES_OOS[cl]}) -> CENSURADA"
    be = o["be_pct"] if cl in ("ACAO", "ETF_BTC") else o["be_brl"]
    positivo_oos = (o["exp_pct_mediana"] > 0 if cl in ("ACAO", "ETF_BTC") else o["exp_brl"] > 0) and o["win"] > be
    sobrevive_2t = a_oos[2]["exp_brl"] > 0 if cl in ("WIN", "WDO") else a_oos[2]["exp_pct_mediana"] > 0
    ic_acima = o["win_ic"][0] > be
    if status != "APROVADA_NO_IS":
        return "NAO FUNCIONA: reprovada nos criterios do IS" + (
            " (OOS isolado positivo, mas a celula nao passou no IS: nao confiavel, so' investigar)" if positivo_oos else "")
    if not positivo_oos:
        return "NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS"
    if not sobrevive_2t:
        return "FRAGIL: positiva no OOS a 1 tick, morre a 2 ticks de slippage"
    if ic_acima:
        return "POSITIVA no OOS (IC95% do win% acima do breakeven; ver ressalva de multiplos testes)"
    return "POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven)"


# ----------------------------------------------------------------------------
def _fmt(v) -> str:
    if isinstance(v, float):
        return str(v).replace(".", ",")
    if isinstance(v, tuple):
        return "(" + "; ".join(_fmt(x) for x in v) + ")"
    return str(v)


def descreve_cel(cel: dict) -> str:
    partes = []
    for k, v in cel.items():
        if k == "tdw" and v == "todos":
            continue
        if k == "tend" and v == "NENHUM":
            continue
        if k == "stop":
            modo, fr = v
            partes.append("sem stop" if modo == "sem" else
                          ("stop=extremo de S" if modo == "abs" else f"stop={_fmt(fr)}xR1"))
        elif k == "saida":
            nome, arg = v
            partes.append(f"saida={nome}" + (f"({int(arg)}d)" if nome in ("BAILOUT", "TEMPO") else
                                             (f"({_fmt(arg)}R)" if nome == "RR" else "")))
        elif k == "tdw":
            partes.append(f"filtro dia: {v}")
        else:
            partes.append(f"{k.removeprefix('p_')}={_fmt(v)}")
    return ", ".join(partes)


def linha_tabela(rotulo: str, a: dict, cl: str, janela_dias: int) -> LinhaResultado:
    """Linha padrao de 12 colunas. Capital NOCIONAL (edge): as 3 colunas que dependem de capital
    ficam em branco (convencao do report.py); a leitura COM portao de caixa vai nos extras.
    Em classes de varios ativos: liquido/maxDD/trades = MEDIANA entre ativos."""
    n_med = a["n"] / max(a["ativos_com_trade"], 1)
    be = a["be_pct"] if cl in ("ACAO", "ETF_BTC") else a["be_brl"]
    return LinhaResultado(
        variante=rotulo, liquido_brl=a["liquido_med"], maxdd_brl=a["maxdd_med"], win_rate_pct=a["win"],
        trades=int(round(n_med)), pregoes=janela_dias,
        extras={"BE emp%": num_br(be, 1), "N total": str(a["n"]),
                "cap.final*": num_br(a["cap_final_g_med"], 0), "pulou*": num_br(a["pulados_med"], 0)},
        aviso="CENSURADA(cx)" if a["cens_g"] > 0.5 else "")


def rotulo_curto(setup: str, cl: str, tag: str) -> str:
    return f"{setup[:11]} {cl[:7]} {tag}"[:30]


def principal() -> None:
    defs = W.definicoes()
    uni = W.universo()
    acoes_inc, tab_acoes = D.universo_acoes()
    res: dict = {}
    mortos: dict = {}
    for setup, defn in defs.items():
        for cl in defn.classes:
            pacote = carrega_unidades(setup, cl)
            if pacote is None:
                continue
            out, blks, nomes = pacote
            esc = escolhe_no_is(defn, cl, out, blks)
            ci = esc["ci"]
            a_is = {s: agrega(cl, out, ci, si, IS) for si, s in enumerate((0, 1, 2))}
            a_oos = le_oos(cl, out, ci)
            res[(setup, cl)] = {"esc": esc, "is": a_is, "oos": a_oos, "nomes": nomes,
                                "veredito": veredito(cl, esc["status"], a_oos, a_is)}
            esc2 = escolhe_no_is(defn, cl, out, blks, so_com_stop=True)
            a_oos2 = le_oos(cl, out, esc2["ci"])
            res[(setup, cl)]["alt"] = {"esc": esc2, "oos": a_oos2,
                                       "veredito": veredito(cl, esc2["status"], a_oos2, None)}
            mortos[(setup, cl)] = eixos_mortos(defn, out)
    # --------------------------------------------------------------- relatorio
    jan_dias = {}
    for cl, nome in (("ACAO", "PETR4"), ("WIN", "WIN"), ("WDO", "WDO"), ("ETF_BTC", "BITH11")):
        at = D.carregar(nome)
        j = D.janelas(at)
        jan_dias[cl] = {k: v[1] - v[0] for k, v in j.items()}
    md = []
    md.append("# Larry Williams — relatório do motor de pesquisa (Python)\n")
    md.append("_Contrato: `ESPECIFICACAO.md`. Decisões: `DECISOES.md`. Parâmetros finais: `params_recomendados.json`._\n")
    md.append("## Como ler (números primeiro)\n")
    md.append("- **Edge** = capital nocional, todos os trades entram (a pergunta é \"a regra tem vantagem?\"). "
              "As colunas marcadas com `*` (`cap.final*`, `pulou*`) são a leitura **COM portão de caixa no capital mínimo real** "
              "(ação: preço×lote×2; WIN R$250; WDO R$375): mede se o dono sobreviveria operando 1 lote/contrato. "
              "**CENSURADA(cx)** = o portão barrou trades, o caixa zerou ou houve < 20 trades.\n")
    md.append("- **Sempre** win% ao lado do **breakeven empírico** `perda_média/(ganho_média+perda_média)` e do N. "
              "`R$/op > 0` e `win% > BE` são a mesma afirmação.\n")
    md.append("- **Slippage por entrada disparada**: escolha e tabela a **1 tick**; sensibilidade 0/1/2 ticks ao lado.\n")
    md.append("- Escolha da célula **só no IS**, por **mediana entre ativos** (ações/ETF) ou entre **semestres do IS** (WIN/WDO), "
              "com mínimo de trades, `share>0 ≥ 50%` e **vizinhança** (≥ 50% das vizinhas a um eixo de distância positivas). "
              "O OOS foi aberto **uma vez** por (setup, classe), na célula escolhida.\n")
    md.append("- **Aviso de múltiplos testes**: cada célula escolhida saiu de uma grade de centenas a milhares de células; "
              "o OOS é a única leitura honesta. Trades de ativos diferentes no mesmo dia são correlacionados — o IC do win% "
              "agregado entre ações é otimista.\n")
    # ---- ativos
    md.append("## Ativos que entraram e que saíram\n")
    n_inc = len(acoes_inc)
    md.append(f"**Ações/ETF B3 (data/raw, 157 arquivos): {n_inc} entraram, {157 - n_inc} saíram.** Corte: mediana do giro "
              f"financeiro diário (close×volume) ≥ R$ {D.GIRO_MIN_BRL/1e6:.0f} mi tanto no histórico inteiro quanto nos últimos 250 pregões; "
              f"≥ {D.MIN_BARRAS_IS} barras no IS (2010–2020) e ≥ {D.MIN_BARRAS_OOS} no OOS (2021–hoje); ≤ {100*D.MAX_FRACAO_VOLUME_ZERO:.0f}% de dias sem volume; "
              f"nenhum salto diário > {100*D.SALTO_MAX:.0f}% (suspeita de desdobramento não ajustado). BOVA11 incluído a pedido (lote 1).\n")
    md.append("Entraram: " + ", ".join(acoes_inc) + ".\n")
    saiu = [r for r in tab_acoes if not r["incluido"]]
    md.append("Saíram (motivo principal; lista completa com todos os motivos em `universo_acoes.csv`):\n")
    por_motivo: dict[str, list[str]] = {}
    for r in saiu:
        m = r["motivo"].split(";")[0].split(" ")[0:2]
        chave = ("giro < corte" if "giro" in r["motivo"].split(";")[0]
                 else "barras insuficientes (IS/OOS)" if "barras" in r["motivo"].split(";")[0]
                 else "dias sem volume" if "sem volume" in r["motivo"].split(";")[0] else "salto diário")
        por_motivo.setdefault(chave, []).append(r["simbolo"])
    for k, v in por_motivo.items():
        md.append(f"- **{k}** ({len(v)}): {', '.join(v)}")
    md.append("")
    md.append("**WIN e WDO**: `WIN@D`/`WDO@D` M1 (ajuste por diferença), 2021-10 → 2026-10; pregão regular 09:00–17:54 (corte único "
              "porque o CSV tem barras até 18:24–18:29 em parte dos pregões; ver DECISOES.md); pregões com < 300 barras descartados. "
              "IS 2021-10→2024-06, OOS 2024-07→hoje.\n")
    md.append("**Bitcoin (somente veículos listados na B3, M1 → diário em horário de Brasília, critério de `cripto_comum.py`: "
              "≥ 96 barras M1/pregão e giro mediano > R$ 1 mi/dia)**:\n")
    for s in D.VEICULOS_BTC:
        at, info = D.carregar_btc(s)
        md.append(f"- {s}: {'ENTROU' if at is not None else 'SAIU (' + info['motivo'] + ')'} — {info['pregoes']} pregões "
                  f"({info['inicio']}→{info['fim']}), mediana {info['barras_m1_mediana']:.0f} barras/pregão, giro mediano R$ {info['giro_mediano_brl']/1e6:.1f} mi.")
    md.append("\n_Limite duro_: o repositório guarda só ~100.000 barras M1 por ETF (≈ 1 ano). IS = primeiros 60% dos pregões, OOS = 40% finais: "
              "**amostra de poucas dezenas de trades por setup — qualquer veredito de bitcoin é INCONCLUSIVO.** BTC-USD cru não foi usado.\n")
    # ---- resultados por classe
    ordem_setups = list(defs)
    for cl, titulo in (("ACAO", "Ações B3 (diário)"), ("WIN", "WIN (mini-índice, M1)"), ("WDO", "WDO (mini-dólar, M1)"),
                       ("ETF_BTC", "ETFs de bitcoin na B3 (diário)")):
        md.append(f"\n## {titulo}\n")
        md.append("Linha IS = a escolhida; linha OOS = leitura única. `liquido`/`MaxDD`/`trades` = " +
                  ("mediana entre ativos" if cl in ("ACAO", "ETF_BTC") else "do ativo") +
                  f"; pregões = {jan_dias[cl]['IS']} (IS) / {jan_dias[cl]['OOS']} (OOS). Slippage 1 tick.\n")
        linhas = []
        for setup in ordem_setups:
            r = res.get((setup, cl))
            if not r:
                continue
            linhas.append(linha_tabela(rotulo_curto(setup, cl, "IS"), r["is"][1], cl, jan_dias[cl]["IS"]))
            linhas.append(linha_tabela(rotulo_curto(setup, cl, "OOS"), r["oos"][1], cl, jan_dias[cl]["OOS"]))
        md.append("```\n" + tabela(linhas, extras=("BE emp%", "N total", "cap.final*", "pulou*"), largura_extra=11) + "\n```\n")
        md.append("| setup | célula escolhida no IS (params; saída; stop; lados; filtros) | status IS | IS: score mediana | vizinhas + | OOS 0/1/2 ticks "
                  "(" + ("exp% mediana" if cl in ("ACAO", "ETF_BTC") else "R$/op") + ") | OOS win% [IC95%] vs BE | N OOS | veredito |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        for setup in ordem_setups:
            r = res.get((setup, cl))
            if not r:
                continue
            e, o = r["esc"], r["oos"]
            f = (lambda a: f"{a['exp_pct_mediana']:.3f}%".replace(".", ",")) if cl in ("ACAO", "ETF_BTC") else \
                (lambda a: num_br(a["exp_brl"], 2))
            be = o[1]["be_pct"] if cl in ("ACAO", "ETF_BTC") else o[1]["be_brl"]
            md.append(f"| {setup} | {descreve_cel(e['cel'])} | {e['status']} ({e['n_passam']}/{e['n_base']} células passam) | "
                      f"{num_br(e['score'], 3)} | {e['viz_k']}/{e['viz_m']} | {f(o[0])} / {f(o[1])} / {f(o[2])} | "
                      f"{num_br(o[1]['win'],1)}% [{num_br(o[1]['win_ic'][0],1)}; {num_br(o[1]['win_ic'][1],1)}] vs {num_br(be,1)}% | "
                      f"{o[1]['n']} | {r['veredito']} |")
        md.append("")
        md.append(f"**{titulo} — melhor célula COM stop de proteção** (a escolha irrestrita acima tende a `sem stop`, risco aberto; "
                  "aqui o stop é obrigatório. Mesmo critério de escolha no IS, OOS lido uma vez):" + chr(10))
        md.append("| setup | célula (com stop) | status IS | vizinhas + | OOS exp 1 tick | OOS win% vs BE | N OOS | veredito |")
        md.append("|---|---|---|---|---|---|---|---|")
        for setup in ordem_setups:
            r = res.get((setup, cl))
            if not r:
                continue
            e, o = r["alt"]["esc"], r["alt"]["oos"]
            ex = (f"{num_br(o[1]['exp_pct_mediana'], 3)}%" if cl in ("ACAO", "ETF_BTC") else f"R$ {num_br(o[1]['exp_brl'], 2)}")
            be = o[1]["be_pct"] if cl in ("ACAO", "ETF_BTC") else o[1]["be_brl"]
            md.append(f"| {setup} | {descreve_cel(e['cel'])} | {e['status']} | {e['viz_k']}/{e['viz_m']} | {ex} | "
                      f"{num_br(o[1]['win'], 1)}% vs {num_br(be, 1)}% | {o[1]['n']} | {r['alt']['veredito']} |")
        md.append("")
    # ---- eixos mortos
    md.append("\n## Eixos da grade que não mexem no resultado (item 6.25)\n")
    md.append("Fração dos grupos (demais eixos fixos) em que mudar o eixo altera trades/líquido do IS. **0,00 = eixo morto**; `—` = eixo com 1 valor.\n")
    md.append("| setup | classe | " + " | ".join(["eixo: fração"]) + " |")
    md.append("|---|---|---|")
    for (setup, cl), m in mortos.items():
        txt = "; ".join(f"{k.removeprefix('p_')}={'—' if v != v else f'{v:.2f}'}" for k, v in m.items())
        md.append(f"| {setup} | {cl} | {txt} |")
    # ---- salvar
    (AQUI / "RELATORIO_corpo.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    exporta_params(res, defs)
    exporta_ref_trades(res, defs)
    with open(AQUI / "universo_acoes.csv", "w", encoding="utf-8") as fh:
        fh.write("simbolo;incluido;giro_hist_mi;giro_250_mi;barras_is;barras_oos;salto_max;motivo\n")
        for r in tab_acoes:
            fh.write(f"{r['simbolo']};{int(r['incluido'])};{r['giro_hist_mi']:.2f};{r['giro_250_mi']:.2f};"
                     f"{r['barras_is']};{r['barras_oos']};{r['salto_max']:.3f};{r['motivo']}\n")
    print("ok: RELATORIO_corpo.md, params_recomendados.json, ref_trades/, universo_acoes.csv")


def params_ea(setup: str, cel: dict) -> dict:
    """Traduz a celula do motor para as chaves do EA (DECISOES_EA.md)."""
    saida, arg = cel.get("saida", ("ALVO_LIMITE_SMA3", 0))
    modo_stop, frac = cel["stop"]
    lados = cel.get("lados", "CV")     # TRES_BARRAS: o lado vem da tendencia
    out = {"setup": setup,
           "lado_compra": "C" in lados, "lado_venda": "V" in lados,
           "modo_saida": {"BAILOUT": "BAILOUT", "FECHAMENTO": "FECHAMENTO", "TEMPO": "TEMPO_N",
                          "REVERSAO": "REVERSAO", "ABERTURA_SEGUINTE": "ABERTURA_SEGUINTE",
                          "RR": "ALVO_RR", "OSC": "INDICADOR", "ALVO_LIMITE_SMA3": "ALVO_LIMITE_SMA3"}[saida],
           "stop_modo": {"frac": "FRACAO_R1", "abs": "EXTREMO_S", "sem": "SEM_STOP"}[modo_stop],
           "stop_frac": frac, "tendencia": cel.get("tend", "NENHUM")}
    if saida == "BAILOUT":
        out["bailout_apos_dias"] = int(arg)
    if saida == "TEMPO":
        out["saida_dias"] = int(arg)
    if saida == "RR":
        out["rr_alvo"] = float(arg)
    if cel.get("tdw", "todos") != "todos":
        dias = W.DIAS_TDW[cel["tdw"]]
        out["filtro_dias_compra"] = [d + 1 for d in dias]
        out["filtro_dias_venda"] = [d + 1 for d in dias]
    p = {k[2:]: v for k, v in cel.items() if k.startswith("p_")}
    if "k" in p:
        a, b = p.pop("k")
        out["kc"], out["kv"] = a, b
    if "gap_min" in p:
        out["gap_min"] = p["gap_min"]
    if "n" in p:
        out["n"] = p["n"]
    if "excl_out" in p:
        out["excluir_outside"] = p["excl_out"]
    if "zona" in p:
        out["zona"] = p["zona"]
    if "close_contra" in p:
        out["exige_close_oposto"] = p["close_contra"]
    if "modo" in p:
        out["modo_entrada"] = p["modo"]
    if "venda" in p:
        out["lado_venda"] = bool(p["venda"])
    if "espera" in p:
        out["espera"] = p["espera"]
    if "gatilho" in p:
        out["nivel_compra"], out["nivel_venda"] = p["gatilho"], 100.0 - p["gatilho"]
    if "compra_max" in p:
        out["nivel_compra"], out["nivel_venda"] = p["compra_max"], p["venda_min"]
    if "validade" in p:
        out["janela"] = p["validade"]
    if "dias" in p:
        out["dias_compra"] = list(p["dias"])
    if "meses" in p:
        out["filtro_meses_bloqueados"] = list(p["meses"])
    if "dia" in p:
        out["dias_compra"] = [p["dia"] + 1]
        out["dias_venda"] = [p["dia"] + 1]
    if "tf" in cel:
        out["timeframe"] = f"M{cel['tf']}"
        out["tendencia_3b"] = cel["tend"]
    if setup == "WR":
        out["periodo"] = p.get("n", 10)
    return out


def exporta_params(res: dict, defs: dict) -> None:
    saida = {"gerado_por": "lw_relatorio.py",
             "nota": ("Celulas escolhidas SO' no IS (mediana entre ativos/semestres + vizinhanca). `recomendado_para_ea`=true so' quando "
                      "aprovada no IS E positiva no OOS a 1 tick e a 2 ticks. Os demais ficam listados para reproducao, nao para operar. "
                      "dias da semana nos filtros: 1=seg ... 5=sex (convencao MQL5 day_of_week-0 domingo: 1=seg)."),
             "setups": {}}
    for (setup, cl), r in res.items():
        v = r["veredito"]
        rec = v.startswith("POSITIVA") and not v.startswith("POSITIVA FRACA")
        e = r["esc"]
        o = r["oos"]
        entrada = {"classe": cl, "recomendado_para_ea": rec, "veredito": v, "status_is": e["status"],
                   "params_ea": params_ea(setup, e["cel"]), "celula_motor": {k: (list(x) if isinstance(x, tuple) else x) for k, x in e["cel"].items()},
                   "is_score_mediana": e["score"], "is_n": e["n_is"], "vizinhas_positivas": f"{e['viz_k']}/{e['viz_m']}",
                   "oos_n": o[1]["n"], "oos_win_pct": o[1]["win"], "oos_breakeven_empirico_pct": o[1]["be_pct"] if cl in ("ACAO", "ETF_BTC") else o[1]["be_brl"],
                   "oos_exp_1tick": o[1]["exp_pct_mediana"] if cl in ("ACAO", "ETF_BTC") else o[1]["exp_brl"],
                   "oos_exp_2ticks": o[2]["exp_pct_mediana"] if cl in ("ACAO", "ETF_BTC") else o[2]["exp_brl"],
                   "slippage_ticks_assumido": 1, "candidata_fraca": v.startswith("POSITIVA FRACA"),
                   "alternativa_com_stop": {"veredito": r["alt"]["veredito"], "status_is": r["alt"]["esc"]["status"],
                                            "params_ea": params_ea(setup, r["alt"]["esc"]["cel"]),
                                            "oos_n": r["alt"]["oos"][1]["n"], "oos_win_pct": r["alt"]["oos"][1]["win"],
                                            "oos_exp_1tick": (r["alt"]["oos"][1]["exp_pct_mediana"] if cl in ("ACAO", "ETF_BTC") else r["alt"]["oos"][1]["exp_brl"])}}
        saida["setups"].setdefault(setup, {})[cl] = entrada
    (AQUI / "params_recomendados.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=float), encoding="utf-8")


def exporta_ref_trades(res: dict, defs: dict) -> None:
    """CSV de trades de referencia (formato do EA) para um ativo de cada classe, por setup,
    usando a celula escolhida da classe; janela = historico inteiro, slippage 0 (como o log do EA)."""
    pasta = AQUI / "ref_trades"
    pasta.mkdir(exist_ok=True)
    ativos = {"ACAO": "PETR4", "WIN": "WIN", "WDO": "WDO", "ETF_BTC": "BITH11"}
    for (setup, cl), r in res.items():
        at = D.carregar(ativos[cl])
        if at is None:
            continue
        cel = r["esc"]["cel"]
        tends = W.tendencias_do_ativo(at)
        if setup == "TRES_BARRAS":
            tr = M.gerar_trades_tres_barras(at, cel["tf"], cel["stop"][1], tends[cel["tend"]])
        else:
            defn = defs[setup]
            eixos_p = [n for n in defn.nomes_eixos if n.startswith("p_")]
            sin = defn.construtor(at, {n[2:]: cel[n] for n in eixos_p})
            cal = at.calendario()
            dias = W.DIAS_TDW[cel["tdw"]]
            sin = S.aplicar_filtros(sin, cal["dow"], cal["mes"], tends[cel["tend"]], dias_c=dias, dias_v=dias,
                                    usar_tendencia=cel["tend"] != "NENHUM")
            tr = M.gerar_trades(at, sin, W.monta_cfg(cel))
        M.exporta_trades_csv(at, tr, pasta / f"ref_trades_{at.nome}_{setup}.csv", slip_ticks=0.0)


if __name__ == "__main__":
    principal()
