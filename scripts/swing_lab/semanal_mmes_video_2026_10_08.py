"""Medicao do setup semanal do video "Se eu tivesse so R$1.000" (Bull/Value Trader).

O QUE O VIDEO PROPOE (so a parte de B3 -- EUA/BDRs fora por decisao do dono):
  * grafico SEMANAL, tres MMEs: 9, 21, 50;
  * so opera ativo com as tres medias apontando para cima;
  * universo = ativos que mais subiram em 12 meses (a "grade" do Profit);
  * compra no recuo perto das medias, gatilho Inside Bar / Dave Landry /
    rompimento da maxima, stop abaixo da minima do candle-sinal;
  * saida por alvo de 3x o risco OU por Stop ATR (sai so quando FECHA abaixo).

COMO ESTE SCRIPT MEDE (premissas declaradas -- o video nao fixa nenhuma delas):
  * SINAL so no candle semanal FECHADO (sexta). Nada do candle em formacao.
  * EXECUCAO no diario da semana seguinte: ordem stop de compra 1 centavo
    acima da maxima do candle-sinal, valida so naquela semana. Gap acima do
    gatilho preenche na abertura. (Tipo de ordem ainda em aberto -- o dono vai
    decidir depois; o video usa rompimento, entao a medicao segue o video.)
  * Stop inicial 1 centavo abaixo da minima do candle-sinal, checado todo dia.
    Dia em que stop e alvo/entrada coexistem = conta o pior caso (stop).
  * "Apontando para cima" = cada MME maior que ela mesma na semana anterior.
  * "Perto das medias" = minima do candle-sinal <= MME9 * (1 + TOL_RECUO) e
    fechamento acima da MME50.
  * Stop ATR (estilo Profit): linha = fechamento - k*ATR(n), so sobe; sai na
    abertura seguinte quando o fechamento SEMANAL fica abaixo da linha anterior.
    O video nao da n nem k -- testamos dois pares.
  * Custo: 0,06%/perna (corretagem+emolumentos) + 0,15%/perna de deslize, os
    defaults de `core.config.CostModel`. A corretagem FIXA do fracionario na
    Rico (R$1,90/ordem) nao entra aqui: ela depende do capital e esta medicao
    e por trade, em %. Entra na simulacao de carteira com R$1.000.
  * Uma posicao por ativo por vez. Retorno composto = 100% do capital do
    ativo em cada trade, em sequencia (nao e a carteira do dono).

VIES CONHECIDO: o universo e a grade do video de 2024 -- acoes que sobreviveram
e eram liquidas em 2024. Quem faliu/saiu da bolsa antes nao esta aqui, o que
favorece estrategia comprada de tendencia. Ler os numeros com esse desconto.

Uso: .venv/Scripts/python.exe scripts/swing_lab/semanal_mmes_video_2026_10_08.py [--prt CAMINHO] [--sem-download]
Saida: scripts/swing_lab/semanal_mmes_video/medicoes.json (+ HTML gerado a parte).
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from market_data.download import (  # noqa: E402
    download_one, merge_preserving_history, parquet_path, save_parquet,
)
from market_data.loader import load_one  # noqa: E402

PRT_PADRAO = Path.home() / "Downloads" / "Nova grade de cotações.prt"
SAIDA = ROOT / "scripts" / "swing_lab" / "semanal_mmes_video"
INICIO = "2010-01-01"

GRUPOS_FORA = ("ndices, ETFs", "BDRs")  # indices/ETFs/futuros e BDRs: nao sao acoes B3

# A grade e de 2024. Codigos que mudaram depois (conferido no yfinance em
# 2026-10-08: todos os novos trazem o historico inteiro, desde 2010 quando a
# empresa ja era listada). Fusao em que dois codigos viraram um (SOMA3+ARZZ3 ->
# AZZA3; MRFG3+BRFS3 -> MBRF3; ENAT3+RRRP3 -> BRAV3) entra uma vez so.
# JBSS3 virou BDR (JBSS32) e fica de fora pela regra "so acoes B3".
RENOMEADOS = {
    "EMBR3": "EMBJ3", "CCRO3": "MOTV3", "ELET3": "AXIA3", "NTCO3": "NATU3", "MRFG3": "MBRF3",
    "ARZZ3": "AZZA3", "TRPL4": "ISAE4", "PETZ3": "AUAU3", "ENAT3": "BRAV3", "CPLE6": "CPLE3",
    "GUAR3": "RIAA3",
}
TICKER_GRADE = {v: k for k, v in RENOMEADOS.items()}

# Final 31-35 e 39 = BDR. A regra do dono e "so acoes B3".
BDR = re.compile(r"[A-Z0-9]{4}3[1-59]")

# A grade do video escolhe UMA classe por empresa e e de 2024, entao deixa de
# fora acao liquida (PETR3, ITUB3, BBDC3, ITSA4...) e empresa que listou ou
# ganhou liquidez depois. O universo e completado com o que a Rico lista no
# MT5 acima deste piso. MEDIANA do financeiro diario, nao media: um negocio
# em bloco faz a media mentir (VSPT3 aparecia com R$6,8 bi/dia).
LIQ_MIN_MT5 = 5e6
UNIVERSO_CACHE = SAIDA / "universo_mt5.json"
# Setor de quem entra pelo MT5, no vocabulario da grade (o MT5 nao traz setor).
# Ticker que nao estiver aqui aparece como "Sem classificação" -- e o sinal
# para acrescentar a linha.
SETOR_EXTRA = {
    "PETR3": "Petr, Gás e Bio", "PASS3": "Petr, Gás e Bio", "OPCT3": "Petr, Gás e Bio",
    "ITSA4": "Financeiro", "ITUB3": "Financeiro", "BBDC3": "Financeiro", "PINE4": "Financeiro",
    "ALOS3": "Financeiro", "SANB3": "Financeiro", "SANB4": "Financeiro", "BBSE3": "Financeiro",
    "SAUD3": "Saúde",
    "POMO3": "Bens Industriais", "POMO4": "Bens Industriais", "PRNR3": "Bens Industriais", "AZEV3": "Bens Industriais",
    "AZEV4": "Bens Industriais",
    "KLBN4": "Materiais Básicos", "KLBN3": "Materiais Básicos", "USIM3": "Materiais Básicos", "GGBR3": "Materiais Básicos",
    "SAPR4": "Saneamento", "SAPR3": "Saneamento",
    "DESK3": "Telecomunicação",
    "TFCO4": "Consumo Cíclico", "VTRU3": "Consumo Cíclico", "CYRE4": "Consumo Cíclico", "RENT4": "Consumo Cíclico",
    "RIAA3": "Consumo Cíclico",
}

TOL_RECUO = 0.02
CUSTO_PERNA = 0.0006 + 0.0015
TICK = 0.01
VARIANTES = {
    "atr14x2": ("atr", 14, 2.0),
    "atr21x3": ("atr", 21, 3.0),
    "alvo3R": ("alvo", 3.0, None),
}
SETUPS = ("inside_bar", "dave_landry", "recuo_media")
CORTE_ISOS = pd.Timestamp("2020-01-01")


# ---------------------------------------------------------------- universo --
def ler_grade_setores(prt: Path) -> list[tuple[str, str]]:
    """(setor, ticker) da grade 'Setores' do workspace do Profit.

    O .prt e um zip; a grade de setores mora num .cg cujas strings sao
    UTF-16LE com prefixo de tamanho. Ticker vem como 'PETR4_B_0' (B = Bovespa).
    O cabecalho de setor e a string sem o sufixo _X_0.
    """
    with zipfile.ZipFile(prt) as z:
        for nome in z.namelist():
            if not nome.endswith(".cg"):
                continue
            b = z.read(nome)
            if "Setor Financeiro".encode("utf-16-le") not in b:
                continue
            out: list[tuple[str, str]] = []
            setor = None
            for m in re.finditer(rb"(?:[\x20-\x7e\xc0-\xff]\x00){3,}", b):
                s = m.group().decode("utf-16-le")
                achados = re.findall(r"([A-Z0-9]{4,7})_([A-Z])_0", s)
                if achados:
                    for tk, mercado in achados:
                        if mercado == "B" and setor is not None:
                            out.append((setor, tk))
                    continue
                # cabecalho: o 1o caractere as vezes cola no byte de tamanho
                setor = s
            vistos, final = set(), []
            for st, tk in out:
                tk = RENOMEADOS.get(tk, tk)
                # BDR escondido em setor (INBR32, ROXO34, XPBR31, AURA33 estavam no Financeiro/Materiais)
                if any(g in st for g in GRUPOS_FORA) or tk in vistos or BDR.fullmatch(tk):
                    continue
                vistos.add(tk)
                final.append((_limpa_setor(st), tk))
            return final
    raise RuntimeError(f"grade de setores nao achada em {prt}")


def universo_mt5() -> dict[str, dict]:
    """Acoes (ON/PN/units) que a corretora lista no MT5, com a mediana do
    financeiro diario dos ultimos 63 pregoes. Grava cache: sem o terminal
    aberto, a rodada usa o ultimo universo lido em vez de cair."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        mt5 = None
    if mt5 is not None and mt5.initialize():
        out: dict[str, dict] = {}
        for s in mt5.symbols_get():
            if "A VISTA" not in s.path or "Deprecated" in s.path:
                continue
            desc = s.description or ""
            acao = re.fullmatch(r"[A-Z0-9]{4}[3-6]", s.name)
            unit = re.fullmatch(r"[A-Z0-9]{4}11", s.name) and "UNT" in desc  # 11 sem UNT = FII/ETF; a Rico cola o UNT no nome ("SANTANDER BRUNT")
            if not (acao or unit) or BDR.fullmatch(s.name):
                continue
            r = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_D1, 0, 63)
            if r is None or len(r) < 40:
                continue
            out[s.name] = {"fin_med": float(np.median(r["close"] * r["real_volume"])), "desc": desc.strip()}
        corretora = mt5.account_info().company if mt5.account_info() else "?"
        mt5.shutdown()
        UNIVERSO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        UNIVERSO_CACHE.write_text(json.dumps({"lido": pd.Timestamp.now().strftime("%Y-%m-%d"), "corretora": corretora,
                                              "ativos": out}, ensure_ascii=False), encoding="utf-8")
        print(f"universo MT5 ({corretora}): {len(out)} acoes/units com cotacao", flush=True)
        return out
    if UNIVERSO_CACHE.exists():
        c = json.loads(UNIVERSO_CACHE.read_text(encoding="utf-8"))
        print(f"MT5 indisponivel -- usando universo em cache de {c['lido']}", flush=True)
        return c["ativos"]
    raise RuntimeError("MT5 indisponivel e sem cache de universo: abra o terminal da corretora e rode de novo")


def _limpa_setor(s: str) -> str:
    s = s.strip().rstrip("/")
    for k, v in {"Setor de ": "", "Setor ": "", "etor de ": "", "etor ": ""}.items():
        if s.startswith(k):
            s = s[len(k):]
    return s[:1].upper() + s[1:]


# ------------------------------------------------------------------- dados --
def garantir_dados(tickers: list[str], baixar: bool) -> dict[str, str]:
    """Baixa/atualiza o diario de cada ticker (yfinance, .SA). Retorna falhas.
    Com `baixar=False` so baixa quem ainda nao tem parquet (ticker novo no universo)."""
    falhas: dict[str, str] = {}
    for i, tk in enumerate(tickers, 1):
        y = f"{tk}.SA"
        if baixar or not parquet_path(y).exists():
            try:
                novo = download_one(y, start=INICIO)
                novo, _ = merge_preserving_history(y, novo)
                save_parquet(y, novo)
            except Exception as e:  # sem dado = ticker saiu da bolsa/mudou de codigo
                falhas[tk] = str(e)[:80]
        print(f"  dados {i}/{len(tickers)} {tk}{'  FALHOU' if tk in falhas else ''}", flush=True)
    return falhas


def semanal(d: pd.DataFrame) -> pd.DataFrame:
    w = d.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min",
                                 "close": "last", "volume": "sum"}).dropna(subset=["close"])
    return w


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(w: pd.DataFrame, n: int) -> pd.Series:
    pc = w["close"].shift()
    tr = pd.concat([w["high"] - w["low"], (w["high"] - pc).abs(), (w["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ----------------------------------------------------------------- simulacao --
@dataclass
class Trade:
    setup: str
    variante: str
    semana_sinal: str
    entrada_data: str
    entrada: float
    stop: float
    risco_pct: float
    saida_data: str
    saida: float
    motivo: str
    ret: float          # liquido de custo
    r_mult: float
    dias: int
    ambiguo: bool       # dia da entrada tocou o stop sem dar para saber a ordem


def sinais(w: pd.DataFrame) -> pd.DataFrame:
    e9, e21, e50 = ema(w["close"], 9), ema(w["close"], 21), ema(w["close"], 50)
    sobe = (e9 > e9.shift()) & (e21 > e21.shift()) & (e50 > e50.shift())
    perto = (w["low"] <= e9 * (1 + TOL_RECUO)) & (w["close"] > e50)
    base = sobe & perto
    base &= pd.Series(np.arange(len(w)) >= 50, index=w.index)  # MME50 aquecida
    ib = (w["high"] <= w["high"].shift()) & (w["low"] >= w["low"].shift())
    dl = w["low"] < np.minimum(w["low"].shift(), w["low"].shift(2))
    return pd.DataFrame({"inside_bar": base & ib, "dave_landry": base & dl, "recuo_media": base,
                         "e9": e9, "e21": e21, "e50": e50, "sobe": sobe}, index=w.index)


def semana_de(idx: pd.DatetimeIndex) -> np.ndarray:
    """Sexta-feira da semana de cada pregao (rotulo do resample W-FRI)."""
    return (idx + pd.to_timedelta((4 - idx.weekday) % 7, unit="D")).values


def simular(d: pd.DataFrame, w: pd.DataFrame, sig: pd.DataFrame, setup: str, variante: str) -> list[Trade]:
    tipo, p1, p2 = VARIANTES[variante]
    atr_w = atr(w, int(p1)).to_numpy() if tipo == "atr" else None
    O, H, L, C = (d[c].to_numpy() for c in ("open", "high", "low", "close"))
    sem_dia = semana_de(d.index)
    sem_w = w.index.values
    pos_w = {s: i for i, s in enumerate(sem_w)}
    wc, wh, wl = w["close"].to_numpy(), w["high"].to_numpy(), w["low"].to_numpy()
    flag = sig[setup].to_numpy()
    # primeiro pregao de cada semana
    ini_sem = {s: i for i, s in reversed(list(enumerate(sem_dia)))}
    n = len(d)
    trades: list[Trade] = []
    livre = np.datetime64("NaT")
    for j in range(len(sem_w) - 1):
        if not flag[j] or (not np.isnat(livre) and sem_w[j] < livre):
            continue
        gatilho, stop = wh[j] + TICK, wl[j] - TICK
        prox = sem_w[j + 1]
        i = ini_sem.get(prox)
        if i is None:
            continue
        ent = None
        while i < n and sem_dia[i] == prox:
            if H[i] >= gatilho:
                ent = i
                break
            i += 1
        if ent is None:
            continue
        ent_px = max(O[ent], gatilho)
        risco = (ent_px - stop) / ent_px
        if risco <= 0:
            continue
        alvo = ent_px + p1 * (ent_px - stop) if tipo == "alvo" else None
        linha = None
        sai, sai_px, motivo, ambiguo = None, None, None, False
        sair_na_abertura = False
        for k in range(ent, n):
            if sair_na_abertura:
                sai, sai_px, motivo = k, O[k], "stop_atr"
                break
            if k == ent:
                # Dia da entrada: no diario nao se sabe se a minima veio antes ou
                # depois do gatilho. Abriu acima do gatilho -> compra primeiro,
                # minima depois, stop vale. Senao e ambiguo: so conta o stop se
                # o dia FECHOU abaixo dele (ai certamente passou por ele comprado).
                if L[k] <= stop:
                    if O[k] >= gatilho or C[k] <= stop:
                        sai, sai_px, motivo = k, stop, "stop"
                        ambiguo = O[k] < gatilho
                        break
                    ambiguo = True
                if alvo is not None and C[k] >= alvo:
                    sai, sai_px, motivo = k, alvo, "alvo"
                    break
            else:
                if O[k] <= stop:
                    sai, sai_px, motivo = k, O[k], "stop"
                    break
                if L[k] <= stop:
                    sai, sai_px, motivo = k, stop, "stop"
                    break
                if alvo is not None and O[k] >= alvo:
                    sai, sai_px, motivo = k, O[k], "alvo"
                    break
                if alvo is not None and H[k] >= alvo:
                    sai, sai_px, motivo = k, alvo, "alvo"
                    break
            if atr_w is not None and (k + 1 == n or sem_dia[k + 1] != sem_dia[k]):
                jw = pos_w.get(sem_dia[k])
                if jw is not None:  # semana fechada (a em formacao nao esta em w)
                    nova = wc[jw] - p2 * atr_w[jw]
                    if linha is not None and wc[jw] < linha:
                        sair_na_abertura = True
                    linha = nova if linha is None else max(linha, nova)
        if sai is None:  # aberto ate hoje: marca no ultimo fechamento
            sai, sai_px, motivo = n - 1, C[-1], "aberto"
        bruto = sai_px / ent_px - 1
        liq = (1 + bruto) * (1 - CUSTO_PERNA) / (1 + CUSTO_PERNA) - 1
        trades.append(Trade(setup, variante, str(sem_w[j])[:10], str(d.index[ent].date()),
                            round(float(ent_px), 2), round(float(stop), 2), round(float(risco), 4),
                            str(d.index[sai].date()), round(float(sai_px), 2), motivo,
                            round(float(liq), 5), round(float(liq / risco), 3),
                            int((d.index[sai] - d.index[ent]).days), ambiguo))
        livre = sem_dia[sai]
    return trades


def resumo(ts: list[dict]) -> dict:
    fechados = [t for t in ts if t["motivo"] != "aberto"]
    n = len(fechados)
    if n == 0:
        return {"n": 0}
    r = np.array([t["ret"] for t in fechados])
    g, p = r[r > 0], r[r <= 0]
    ganho = float(g.mean()) if len(g) else 0.0
    perda = float(-p.mean()) if len(p) else 0.0
    be = perda / (ganho + perda) if ganho + perda > 0 else None
    eq = np.cumprod(1 + r)
    dd = float((eq / np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:] - 1).min())
    return {"n": n, "win": float((r > 0).mean()), "be": be, "ganho_med": ganho, "perda_med": perda,
            "exp": float(r.mean()), "r_med": float(np.mean([t["r_mult"] for t in fechados])),
            "risco_med": float(np.mean([t["risco_pct"] for t in fechados])),
            "composto": float(eq[-1] - 1), "dd": dd,
            "dias_med": float(np.median([t["dias"] for t in fechados])),
            "ambiguos": int(sum(t["ambiguo"] for t in fechados)),
            "abertos": len(ts) - n}


def medir_ativo(setor: str, tk: str) -> dict:
    bruto = load_one(f"{tk}.SA")[["open", "high", "low", "close", "adj_close", "volume"]].dropna()
    bruto = bruto[bruto["close"] > 0]
    # Serie ajustada por proventos (retorno total): sem isso o stop leva gap de
    # data-ex que o acionista recebe em dinheiro, e o "comprar e segurar" fica
    # subestimado. O preco exibido na grade continua sendo o de tela.
    f = bruto["adj_close"] / bruto["close"]
    d = bruto[["open", "high", "low", "close"]].mul(f, axis=0)
    d["volume"] = bruto["volume"]
    hoje = d.index[-1]
    w = semanal(d)
    if w.index[-1] > hoje:  # semana em formacao nao gera sinal
        w = w.iloc[:-1]
    sig = sinais(w)
    c = d["close"]

    def ret(dias: int) -> float | None:
        ref = c[c.index <= hoje - pd.Timedelta(days=dias)]
        return float(c.iloc[-1] / ref.iloc[-1] - 1) if len(ref) else None

    seq = 0
    for v in sig["sobe"].iloc[::-1]:
        if not v:
            break
        seq += 1
    ult = sig.iloc[-1]
    vol_fin = float((bruto["close"] * bruto["volume"]).iloc[-63:].mean())

    def medias(serie_c: pd.Series) -> dict:
        """Estado das MMEs 9/21/50 no ultimo candle FECHADO da serie."""
        out = {}
        for n in (9, 21, 50):
            e = ema(serie_c, n)
            out[f"acima{n}"] = bool(serie_c.iloc[-1] > e.iloc[-1])
            out[f"sobe{n}"] = bool(e.iloc[-1] > e.iloc[-2])
            out[f"dist{n}"] = float(serie_c.iloc[-1] / e.iloc[-1] - 1)
            out[f"_e{n}"] = float(e.iloc[-1])
        out["alinhada"] = out["_e9"] > out["_e21"] > out["_e50"]
        return {k: v for k, v in out.items() if not k.startswith("_")}

    max52 = float(c.iloc[-252:].max())
    foto = {
        "setor": setor, "ticker": tk, "preco": float(bruto["close"].iloc[-1]), "data": hoje.strftime("%Y-%m-%d"),
        "ticker_grade": TICKER_GRADE.get(tk, tk),
        "r1s": ret(7), "r1m": ret(30), "r3m": ret(91), "r6m": ret(182), "r12m": ret(365), "r24m": ret(730),
        "rano": float(c.iloc[-1] / c[c.index.year < hoje.year].iloc[-1] - 1) if (c.index.year < hoje.year).any() else None,
        "dist_max52": float(c.iloc[-1] / max52 - 1),
        "mm": {"W": medias(w["close"]), "D": medias(c)},
        "sobe_agora": bool(ult["sobe"]), "semanas_subindo": seq,
        "pct_52s_subindo": float(sig["sobe"].iloc[-52:].mean()),
        "dist_e9": float(w["close"].iloc[-1] / ult["e9"] - 1),
        "alinhada": bool(ult["e9"] > ult["e21"] > ult["e50"]),
        "setup_agora": [s for s in SETUPS if bool(sig[s].iloc[-1])],
        "vol_fin_3m": vol_fin, "inicio": d.index[0].strftime("%Y-%m-%d"),
        "bh": float(c.iloc[-1] / c.iloc[0] - 1),
    }
    trades: list[dict] = []
    for st in SETUPS:
        for v in VARIANTES:
            trades += [t.__dict__ for t in simular(d, w, sig, st, v)]
    # retorno 52s semanal por semana, para o filtro de ranking feito fora
    r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return {"foto": foto, "trades": trades, "r52": {k.strftime("%Y-%m-%d"): round(float(v), 4) for k, v in r52.items()}}


def _unidade(setor: str, tk: str) -> tuple[str, dict | None, str]:
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            res = medir_ativo(setor, tk)
        return tk, res, ""
    except Exception as e:
        return tk, None, f"{type(e).__name__}: {e}"[:120]


# ------------------------------------------------------------------- main --
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prt", type=Path, default=PRT_PADRAO)
    ap.add_argument("--sem-download", action="store_true")
    a = ap.parse_args()

    grade = ler_grade_setores(a.prt)
    mt5u = universo_mt5()
    na_grade = {t for _, t in grade}
    fora_corretora = {t: "a corretora não lista no MT5" for _, t in grade if t not in mt5u}
    extras = sorted(t for t, v in mt5u.items() if v["fin_med"] >= LIQ_MIN_MT5 and t not in na_grade)
    universo = [(s, t) for s, t in grade if t in mt5u] + [(SETOR_EXTRA.get(t, "Sem classificação"), t) for t in extras]
    origem = {t: "grade" for _, t in grade} | {t: "mt5" for t in extras}
    print(f"universo: {len(grade)} da grade ({len(fora_corretora)} fora da corretora) + {len(extras)} do MT5 "
          f">= R${LIQ_MIN_MT5 / 1e6:.0f} mi/dia: {' '.join(extras)}", flush=True)
    falhas = garantir_dados([t for _, t in universo], baixar=not a.sem_download)

    resultados: dict[str, dict] = {}
    erros: dict[str, str] = dict(falhas) | fora_corretora
    # 2 processos: a maquina tem 3,9 GB e o terminal do MT5 aberto -- com
    # um processo por nucleo ela entra em troca de disco e a rodada para.
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(_unidade, s, t): t for s, t in universo if t not in falhas}
        for f in as_completed(futs):
            tk, res, err = f.result()
            if res is None:
                erros[tk] = err
                print(f"  {tk:7s} ERRO {err}", flush=True)
                continue
            resultados[tk] = res
            ib = resumo([t for t in res["trades"] if t["setup"] == "recuo_media" and t["variante"] == "atr14x2"])
            print(f"  {tk:7s} 12m {res['foto']['r12m'] or 0:+7.1%}  recuo/atr14x2 n={ib.get('n', 0):3d} "
                  f"win={ib.get('win', 0):5.1%} exp={ib.get('exp', 0):+6.2%}", flush=True)

    # ranking de 12m NA SEMANA DO SINAL (sem olhar o futuro): percentil entre os ativos com dado
    r52 = pd.DataFrame({tk: pd.Series(r["r52"]) for tk, r in resultados.items()})
    pct = r52.rank(axis=1, pct=True)
    for tk, r in resultados.items():
        for t in r["trades"]:
            v = pct.at[t["semana_sinal"], tk] if t["semana_sinal"] in pct.index else np.nan
            t["pct12m"] = None if pd.isna(v) else round(float(v), 3)

    todos = [t | {"ticker": tk} for tk, r in resultados.items() for t in r["trades"]]
    agregados = {}
    for st in SETUPS:
        for v in VARIANTES:
            base = [t for t in todos if t["setup"] == st and t["variante"] == v]
            agregados[f"{st}|{v}"] = {
                "todos": resumo(base),
                "top30": resumo([t for t in base if (t["pct12m"] or 0) >= 0.70]),
                "resto": resumo([t for t in base if t["pct12m"] is not None and t["pct12m"] < 0.70]),
                "ate2019": resumo([t for t in base if pd.Timestamp(t["entrada_data"]) < CORTE_ISOS]),
                "2020+": resumo([t for t in base if pd.Timestamp(t["entrada_data"]) >= CORTE_ISOS]),
            }

    ativos = []
    for tk, r in resultados.items():
        por = {f"{st}|{v}": resumo([t for t in r["trades"] if t["setup"] == st and t["variante"] == v])
               for st in SETUPS for v in VARIANTES}
        ativos.append(r["foto"] | {"medidas": por, "origem": origem[tk],
                                   "fin_med_mt5": mt5u.get(tk, {}).get("fin_med")})
    # ranking de 12m HOJE, entre os ativos da grade (o que a coluna "12 meses" do Profit mostra)
    r12 = pd.Series({a["ticker"]: a["r12m"] for a in ativos}).dropna().rank(pct=True)
    for a in ativos:
        a["pct12m_agora"] = float(r12[a["ticker"]]) if a["ticker"] in r12 else None

    SAIDA.mkdir(parents=True, exist_ok=True)
    out = {
        "gerado": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "premissas": {"tol_recuo": TOL_RECUO, "custo_perna": CUSTO_PERNA, "variantes": VARIANTES,
                      "setups": SETUPS, "inicio": INICIO, "corte": "2020-01-01", "top": 0.70, "liq_min_mt5": LIQ_MIN_MT5},
        "erros": erros, "ativos": ativos, "agregados": agregados, "trades": todos,
    }
    (SAIDA / "medicoes.json").write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nok: {len(ativos)} ativos medidos, {len(erros)} sem dado -> {SAIDA / 'medicoes.json'}", flush=True)
    for k, ag in agregados.items():
        a_ = ag["todos"]
        if a_.get("n"):
            print(f"{k:28s} n={a_['n']:5d} win={a_['win']:5.1%} be={a_['be']:5.1%} exp={a_['exp']:+6.2%} "
                  f"R={a_['r_med']:+5.2f}  | top30 exp={ag['top30'].get('exp', 0):+6.2%} n={ag['top30'].get('n', 0)}",
                  flush=True)


if __name__ == "__main__":
    main()
