"""Port do EA mt5/WinGapBarra1.mq5 (v1.00) para o replay tick a tick no padrao do Testador do MT5.

Regras do .mq5 reproduzidas (inputs padrao): M5; gap = open da 1a barra M5 (leilao) - close da ultima barra do pregao
anterior (call); se a barra 1 (09:00-09:05) fecha CONTRA o gap, limite no close dela, valida ate' 09:35; stop 1.200 pts
no servidor, sem alvo; zera a mercado 18:20 (17:50 no regime antigo: antes de 2024-03-11, no verao dos EUA); nao opera
a 1a sessao em/depois do vencimento; GapMinPts 5; 1 contrato; 1 operacao por dia.

Convencao do replay (a mesma dos outros ports, ver dados.py): bid = ask = last; limite que ja' esta' do lado errado do
livro (compra >= last, venda <= last) vai para a melhor oferta (last -/+ 1 tick), como o EA; enche ao TOCAR o last, no
preco do limite, a partir do tick seguinte ao do envio; o stop dispara no last que toca o nivel e sai no last do tick.

Variante `ref` (so' para o cruzamento com EA_referencia_trades.csv): o limite fica no close da barra 1 e enche ao toque
a partir do PROPRIO tick da decisao (como o simulador da pesquisa), sem o deslocamento para a melhor oferta.

Uso: python port_win_gap_barra1.py              -> 2026 (resultados/WinGapBarra1.csv) e 2022-2025
     python port_win_gap_barra1.py cruza        -> cruzamento com EA_referencia_trades.csv
"""
import sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados          # noqa: E402
import filtro_gap     # noqa: E402

NOME = "WinGapBarra1"
TICK = 5.0
P = dict(stop=1200.0, ttl_min=30, gap_min=5.0, abre_min=9 * 60, fim_min=565, flatten_min=18 * 60 + 20)


def nt(v):
    return float(np.floor(v / TICK + 0.5) * TICK)


def verao_eua(d: date) -> bool:
    def dom(ano, mes, dia):
        x = date(ano, mes, dia)
        return x + timedelta(days=(6 - x.weekday()) % 7)
    return dom(d.year, 3, 8) <= d < dom(d.year, 11, 1)


def fim_continuo(d: date) -> int:
    return 535 if (d < date(2024, 3, 11) and verao_eua(d)) else P["fim_min"]


def rolagem_entre(ant: date, hoje: date) -> bool:
    for ano in (ant.year, hoje.year):
        for mes in (2, 4, 6, 8, 10, 12):
            v = filtro_gap.venc(ano, mes)
            if ant < v <= hoje:
                return True
    return False


def rodar(lista_dias, m1, get_ticks, variante="ea", saldo0=1000.0, stop=None, lado_forcado=None, alvo_mult=None,
          barra_min=5):
    # barra_min: duracao (min) da barra de sinal a partir das 09:00; 5 = a M5 do EA (pesquisa de tempo grafico)
    stop_pts = P["stop"] if stop is None else stop
    por_dia = {d: g for d, g in m1.groupby(m1.index.date)}
    todos = sorted(por_dia)
    # call de cada pregao: close da ultima M1 com abertura <= 18:24
    call = {}
    for d, g in por_dia.items():
        x = g[g.index.time <= pd.Timestamp("18:24").time()]
        if len(x):
            call[d] = float(x.close.iloc[-1])
    trades, saldo, quebrou = [], saldo0, None
    diag = dict(dias=0, sem_barra1=0, sem_anterior=0, vencimento=0, gap_pequeno=0, sem_sinal=0, sinais=0,
                nao_encheu=0, stop=0, flatten=0, sem_tick_flatten=0)
    for dia in lista_dias:
        diag["dias"] += 1
        b = por_dia.get(dia)
        if b is None or len(b) == 0:
            continue
        ini = int(pd.Timestamp(dia).value // 10**6)
        h = b.index.hour * 60 + b.index.minute
        b0 = b[(h >= P["abre_min"]) & (h < P["abre_min"] + barra_min)]
        if len(b0) == 0 or h[0] >= P["abre_min"] + barra_min:
            diag["sem_barra1"] += 1
            continue
        i_ant = todos.index(dia) - 1
        if i_ant < 0 or dia - todos[i_ant] > timedelta(days=5) or todos[i_ant] not in call:
            diag["sem_anterior"] += 1
            continue
        ant = todos[i_ant]
        if rolagem_entre(ant, dia):
            diag["vencimento"] += 1
            continue
        abre, fecha = float(b0.open.iloc[0]), float(b0.close.iloc[-1])
        gap = abre - call[ant]
        if abs(gap) < max(P["gap_min"], 0.0) or gap == 0:
            diag["gap_pequeno"] += 1
            continue
        corpo = fecha - abre
        if corpo == 0 or (corpo > 0) == (gap > 0):
            diag["sem_sinal"] += 1
            continue
        s = 1 if corpo > 0 else -1
        if lado_forcado is not None:                              # so' para nulo de direcao aleatoria (pesquisa)
            s = lado_forcado
        t, last = get_ticks(dia)
        if len(t) == 0:
            continue
        t_dec = ini + (P["abre_min"] + barra_min) * 60000
        t_exp = ini + (P["abre_min"] + P["ttl_min"] + barra_min - 5) * 60000   # validade conta do fecho da barra
        t_fl = ini + (min(P["flatten_min"], P["abre_min"] + fim_continuo(dia) - 5)) * 60000
        i0 = int(np.searchsorted(t, t_dec))
        if i0 >= len(t) or t[i0] >= t_exp:
            diag["sem_barra1"] += 1
            continue
        iz = int(np.searchsorted(t, t_fl))
        diag["sinais"] += 1
        limite = nt(fecha)
        ult = float(last[i0])                                     # bid = ask = last
        if variante == "ea":
            if s > 0 and limite >= ult:
                limite = nt(ult - TICK)
            if s < 0 and limite <= ult:
                limite = nt(ult + TICK)
            ini_fill = i0 + 1
        else:                                                     # "ref": enche ao toque ja' no tick da decisao
            ini_fill = i0
        fim_fill = min(int(np.searchsorted(t, t_exp)), iz, len(t))
        seg = last[ini_fill:fim_fill]
        c = (seg <= limite) if s > 0 else (seg >= limite)
        if len(seg) == 0 or not c.any():
            diag["nao_encheu"] += 1
            continue
        j = ini_fill + int(np.argmax(c))
        stop_px = nt(limite - s * stop_pts)
        fim = iz if iz < len(t) else len(t)
        seg = last[j:fim]
        c = (seg <= stop_px) if s > 0 else (seg >= stop_px)
        ia = None
        if alvo_mult is not None:                                 # alvo a mercado: sai no last do 1o tick que toca entrada +/- k*stop
            alvo_px = nt(limite + s * alvo_mult * stop_pts)
            ca = (seg >= alvo_px) if s > 0 else (seg <= alvo_px)
            if len(seg) and ca.any():
                ia = j + int(np.argmax(ca))
        ist = (j + int(np.argmax(c))) if (len(seg) and c.any()) else None
        if ia is not None and (ist is None or ia < ist):
            k = ia; motivo = "alvo"; diag["alvo"] = diag.get("alvo", 0) + 1
        elif ist is not None:
            k = ist; motivo = "stop"; diag["stop"] += 1
        elif iz < len(t):
            k = iz; motivo = "flatten"; diag["flatten"] += 1
        else:
            k = len(t) - 1; motivo = "flatten"; diag["sem_tick_flatten"] += 1
        tr = dados.trade(NOME, t[j], t[k], s, 1, limite, float(last[k]), motivo)
        trades.append(tr)
        saldo += tr["rs"]
        # 1 contrato fixo (Lotes=1): o saldo nao muda o que o EA faz; a quebra e' lida no resumo, por cenario de custo
    return trades, saldo, quebrou, diag


def m1_total():
    return filtro_gap.m1_continuo()


def ticks_fn(m1):
    por_dia = {d: g for d, g in m1.groupby(m1.index.date)}

    def gt(d):
        if d >= date(2026, 1, 1):
            t, p, v, r = dados.ticks(d)
            return t, p
        t, p, v = dados._sinteticos(por_dia[d])
        return t, p
    return gt


def final():
    m1 = m1_total()
    gt = ticks_fn(m1)
    todos = sorted(set(m1.index.date))
    d26 = [d for d in todos if date(2026, 1, 1) <= d <= date(2026, 10, 5)]
    tr, saldo, q, dg = rodar(d26, m1, gt)
    out = dados.salvar(NOME, tr)
    print("2026:", len(tr), "trades; total", round(sum(x["rs"] for x in tr), 2), "diag", dg, "quebrou", q, out, flush=True)
    tr2, dg2 = [], {}
    for ano in (2022, 2023, 2024, 2025):          # cada ano recomeca com R$1.000 (a quebra do ano nao contamina o seguinte)
        d_ano = [d for d in todos if date(ano, 1, 1) <= d <= min(date(ano, 12, 31), date(2025, 9, 30))]
        t_, _, q_, dg_ = rodar(d_ano, m1, gt)
        tr2 += t_
        dg2[ano] = dg_
    o = AQUI / "resultados_anos_gap_barra1"
    o.mkdir(exist_ok=True)
    pd.DataFrame(tr2, columns=dados.COLUNAS).to_csv(o / "WinGapBarra1_2022_2025.csv", index=False)
    print("2022-2025:", len(tr2), "trades; diag", dg2, flush=True)


if __name__ == "__main__":
    final()
