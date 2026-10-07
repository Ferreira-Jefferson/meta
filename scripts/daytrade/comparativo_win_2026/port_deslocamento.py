"""Port do WinDeslocamentoMatinal.mq5 (v1.30) para replay tick a tick no padrao do Testador do MT5.

Regras do .mq5 reproduzidas (inputs padrao):
  - OnTick em cada tick; decisao so' na virada de vela M1 (1o tick do minuto) quando a vela em formacao abriu
    >= MinutosDecisao (90) min depois da 1a vela M1 do dia; se > 90+5 min, dia em branco. Usa so' M1 FECHADAS.
  - ATR = media simples do True Range das 14 D1 fechadas (CopyRates D1 shift 1, n=15), D1 montada das M1.
  - sinal: desloc >= 0,3 ATR e nenhuma M1 fechada abaixo de abertura - 0,05 ATR (compra); espelho na venda.
  - limite no ultimo fechamento (NoTick); se limite >= ask (compra) / <= bid (venda), vai para a melhor oferta
    (bid=ask=last do tick da decisao: last - 5 / last + 5). Prazo 15 min (TimeCurrent em segundos): cancela no 1o
    tick com agora - hora_ordem >= 900 s; o fill do proprio tick vem ANTES do OnTick, entao o tick conta.
  - distancia do stop = max(lado*(limite-linha), tick), apertada pelo teto RiscoMaxPct=10% do SALDO corrente
    (R$1.000 + resultado de cada operacao fechada): teto = floor(saldo*0,10/(0,20*Lote)/5)*5, minimo 2 ticks.
  - fill da limite (Testador): enche ao TOCAR o last (compra: last <= limite), no PRECO DO LIMITE, a partir do tick
    seguinte ao do envio.
  - MQL_TESTER: o PositionModify (SL no servidor) NAO e' feito; o stop e' so' o do EA: nivel = NoTick(preco_exec -/+
    distancia), criado no OnTick do tick do fill (AjustarStop), checado pelo last desde esse mesmo tick
    (VerificarStop roda logo apos AjustarStop); dispara com last <= nivel (compra) e fecha a mercado no last do tick.
  - zera a mercado (last do tick) no 1o tick com agora >= fim_sessao - 5 min (sessao 18:25 -> 18:20); cancela a pendente.
    Se o dia acabar sem tick >= 18:20, a posicao carrega e e' zerada no 1o tick do pregao seguinte ('overnight').
  - 1 operacao por dia, 1 posicao. Saldo <= 0: para de operar (registra a data).
Nao reproduzido: FiltroMM (padrao 0), margem/saldo insuficiente para o lote, fila, custos.

Uso: python port_deslocamento.py            -> rodada final 2026 (resultados/WinDeslocamentoMatinal.csv)
     python port_deslocamento.py valida     -> compara com o replay antigo na janela do WINV26
"""
import sys
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados

NOME = "WinDeslocamentoMatinal"
TICK = 5.0
P = dict(minutos_decisao=90, janela=5, desloc=0.3, banda=0.05, per_atr=14, ttl_min=15, zerar_min=5,
         fim_min=18 * 60 + 25, risco_pct=10.0, lote=1.0, vponto=1.0 / 5.0)


def nt(v):
    return float(np.floor(v / TICK + 0.5) * TICK)       # MathRound (meio para longe do zero; precos > 0)


def d1_de(m1):
    g = m1.groupby(m1.index.date)
    return pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})


def atr_d1(d1, dia, n):
    h = d1[d1.index < dia].tail(n + 1)
    if len(h) < n + 1:
        return 0.0
    hi, lo, cl = h.high.to_numpy(), h.low.to_numpy(), h.close.to_numpy()
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    return float(tr.sum() / n)


def rodar(lista_dias, m1, get_ticks, saldo0=1000.0, risco_pct=None, params=None, log=print):
    p = {**P, **(params or {})}
    if risco_pct is not None:
        p["risco_pct"] = risco_pct
    d1 = d1_de(m1)
    saldo, trades, quebrou, aberta = saldo0, [], None, None
    diag = dict(sinais=0, nao_encheu=0, sem_sinal=0, atrasada=0, sem_atr=0, sem_decisao=0, overnight=0, teto_apertou=0)
    por_dia = {d: g for d, g in m1.groupby(m1.index.date)}

    def fecha(pos, k, t, last, motivo):
        nonlocal saldo
        tr = dados.trade(NOME, pos["te"], t[k], pos["s"], p["lote"], pos["pe"], float(last[k]), motivo)
        trades.append(tr)
        saldo += tr["rs"]
        return tr

    for dia in lista_dias:
        t, last = get_ticks(dia)
        if len(t) == 0:
            continue
        if aberta is not None:                       # Zerar("posicao de pregao anterior") no 1o tick do dia
            diag["overnight"] += 1
            fecha(aberta, 0, t, last, "overnight")
            aberta = None
        if quebrou is not None:
            continue
        if saldo <= 0:
            quebrou = str(dia)
            log(f"{dia}: saldo {saldo:.2f} <= 0 -> para de operar", flush=True)
            continue
        b = por_dia.get(dia)
        if b is None or len(b) < 2:
            diag["sem_decisao"] += 1
            continue
        ini = int(pd.Timestamp(dia).value // 10**6)
        t_zera = ini + (p["fim_min"] - p["zerar_min"]) * 60000
        iz = int(np.searchsorted(t, t_zera))
        iz = iz if iz < len(t) else None
        tb = b.index.values.astype("datetime64[ms]").astype(np.int64)
        i0 = int(np.searchsorted(t, tb[0] + p["minutos_decisao"] * 60000))
        if i0 >= len(t) or (iz is not None and i0 >= iz):
            diag["sem_decisao"] += 1
            continue
        minuto0 = t[i0] // 60000 * 60000                  # abertura da vela M1 em formacao
        if (minuto0 - tb[0]) / 60000 > p["minutos_decisao"] + p["janela"]:
            diag["atrasada"] += 1
            continue
        atr = atr_d1(d1, dia, p["per_atr"])
        if atr <= 0:
            diag["sem_atr"] += 1
            continue
        nf = int(np.searchsorted(tb, minuto0))            # barras fechadas = tb < minuto da vela em formacao
        if nf < 1:
            diag["sem_decisao"] += 1
            continue
        cl = b.close.to_numpy()[:nf]
        ab, banda, ultimo = float(b.open.iloc[0]), p["banda"] * atr, float(cl[-1])
        desloc = ultimo - ab
        if desloc >= p["desloc"] * atr and cl.min() >= ab - banda:
            s, linha = 1, ab - banda
        elif -desloc >= p["desloc"] * atr and cl.max() <= ab + banda:
            s, linha = -1, ab + banda
        else:
            diag["sem_sinal"] += 1
            continue
        diag["sinais"] += 1
        bidask = float(last[i0])                          # bid = ask = last
        limite = nt(ultimo)
        if s > 0 and limite >= bidask:
            limite = nt(min(bidask, bidask - TICK))
        if s < 0 and limite <= bidask:
            limite = nt(max(bidask, bidask + TICK))
        dist = max(s * (limite - linha), TICK)
        if p["risco_pct"] > 0:
            teto_rs = p["risco_pct"] / 100.0 * saldo
            teto = float(np.floor(teto_rs / (p["vponto"] * p["lote"]) / TICK) * TICK)
            teto = max(teto, 2 * TICK)
            if dist > teto:
                diag["teto_apertou"] += 1
                dist = teto
        # prazo: 1o tick com segundos >= segundos da decisao + ttl
        sec = t // 1000
        ic = int(np.searchsorted(sec, sec[i0] + p["ttl_min"] * 60))
        lim_i = min(ic, iz if iz is not None else len(t) - 1, len(t) - 1)
        seg = last[i0 + 1:lim_i + 1]
        c = (seg <= limite) if s > 0 else (seg >= limite)
        if len(seg) == 0 or not c.any():
            diag["nao_encheu"] += 1
            continue
        j = i0 + 1 + int(np.argmax(c))
        pos = dict(s=s, pe=limite, te=int(t[j]))
        stop = nt(limite - s * dist)
        fim = iz if iz is not None else len(t)
        seg = last[j:fim]
        c = (seg <= stop) if s > 0 else (seg >= stop)
        if len(seg) and c.any():
            k = j + int(np.argmax(c))
            fecha(pos, k, t, last, "stop")
        elif iz is not None:
            fecha(pos, iz, t, last, "zera")
        else:
            aberta = pos
        if saldo <= 0 and quebrou is None:
            quebrou = str(dia)
            log(f"{dia}: saldo {saldo:.2f} <= 0 apos a operacao -> para de operar", flush=True)
    return trades, saldo, quebrou, diag


def final():
    dias = dados.dias()
    m1 = dados.m1()

    def gt(d):
        t, p, v, r = dados.ticks(d)
        return t, p
    print(f"{len(dias)} pregoes, saldo inicial R$1.000", flush=True)
    trades, saldo, quebrou, diag = rodar(dias, m1, gt)
    out = dados.salvar(NOME, trades)
    df = pd.DataFrame(trades)
    print("diag:", diag, "| quebrou:", quebrou, "| saldo final:", round(saldo, 2), flush=True)
    if len(df):
        df["mes"] = df.saida.str[:7]
        print(df.groupby("mes").rs.agg(trades="count", liquido="sum").round(2).to_string(), flush=True)
        print("total", len(df), "trades, R$", round(df.rs.sum(), 2), flush=True)
    print(out, flush=True)


def valida():
    """Janela WINV26 (2026-08-13 -> 09-30): port (ticks WINV26, last>0) vs replay antigo (fill 'tocar', lat 0)."""
    sys.path.insert(0, str(dados.ROOT / "scripts" / "daytrade"))
    import win_deslocamento_replay_ticks as vel
    ini, fim = date(2026, 8, 13), date(2026, 9, 30)
    ant = vel.replay(ini, fim, 0.0, "fixa", {"fill": "tocar"}, "WINV26")
    print("antigo:", ant["resumo"], ant["diag"], ant["avisos"], flush=True)
    A = pd.DataFrame(ant["trades"])
    m1 = vel.carregar_m1("WINV26", ini, fim, [])
    m1 = m1[["open", "high", "low", "close"]]
    dias = sorted(d for d in set(m1.index.date) if ini <= d <= fim)

    def gt(d):
        x = pd.read_pickle(vel.CACHE / "WINV26" / f"{d}.pkl")
        x = x[x["last"] > 0]
        return x.time_msc.to_numpy(), x["last"].to_numpy(float)
    res = {}
    for nome, kw in (("port sem teto (isola execucao)", dict(risco_pct=0.0)), ("port com teto 10%/saldo", dict())):
        tr, saldo, q, dg = rodar(dias, m1, gt, **kw, log=lambda *a, **k: None)
        B = pd.DataFrame(tr)
        print(f"\n== {nome}: {len(B)} trades, R$ {B.rs.sum():.2f}, diag {dg}", flush=True)
        res[nome] = B
    B = res["port sem teto (isola execucao)"]
    B["dia"] = B.entrada.str[:10]
    m = A[["dia", "te", "tx", "d", "pe", "px", "mot", "rs"]].merge(
        B[["dia", "entrada", "saida", "lado", "preco_entrada", "preco_saida", "motivo", "rs"]], on="dia", how="outer", suffixes=("_ant", "_port"))
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(m.to_string(), flush=True)
    print("antigo total", A.rs.sum().round(2), "| port sem teto", B.rs.sum().round(2), "| com teto", res["port com teto 10%/saldo"].rs.sum().round(2))


if __name__ == "__main__":
    valida() if len(sys.argv) > 1 and sys.argv[1] == "valida" else final()
