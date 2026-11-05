"""LLM lendo o gráfico do WIN M5 e decidindo: pedido do dono em 2026-10-15, depois do mecanismo determinístico
"olhar para trás e repetir" ter sido refutado (olhar_para_tras.py).

A cada close de barra M5 (10:00..17:45), SEM posição, a LLM recebe o pregão até ali (OHLC, volume, MME9/21, VWAP,
ATR), o resumo do pregão anterior e os trades que ela já fez no dia com o resultado. Responde JSON:
comprar | vender | nada, stop e alvo em pontos. Sem data no prompt (o modelo não pode lembrar o mercado).
Execução idêntica ao resto do repo: entrada por limite no close (2 barras, 1 tick além), alvo por limite, stop a
mercado, zera no fim do pregão. 1 contrato, custo 10 pts.

Etapas (dono): 2 dias -> +4 -> +2, dos 10 dias reservados da fase 2 de olhar_para_tras.py, em ordem sorteada.
Régua escrita antes: avança se líquido acumulado > 0 E acima da mediana do nulo (mesmos trades, lado sorteado,
mesmo stop/alvo da LLM). Comparação lateral: o mecanismo determinístico literal (L30W30Am1) nos mesmos dias.

Respostas ficam em cache (llm_cache.jsonl): rodar de novo não paga de novo.
Uso: python llm_decide.py --etapa 1   (dias 1-2) | --etapa 2 (dias 1-6) | --etapa 3 (dias 1-8)
"""
import argparse
import hashlib
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import olhar_para_tras as opt  # noqa: E402

RAIZ = opt.RAIZ
MODELO = "deepseek/deepseek-v4.1-flash"
CACHE = AQUI / "llm_cache.jsonl"
FASE2 = ["2026-08-18", "2026-08-26", "2026-08-28", "2026-09-04", "2026-09-11", "2026-09-15", "2026-09-16",
         "2026-09-18", "2026-10-07", "2026-10-08"]
ETAPAS = {1: 2, 2: 6, 3: 8}
INICIO, N_NULO = "10:00", 2000
_lock = threading.Lock()
_uso = {"in": 0, "out": 0, "custo": 0.0, "chamadas": 0, "cache": 0}

SISTEMA = """Você é um operador de day trade do mini-índice WIN (B3), gráfico de 5 minutos. 1 ponto = R$0,20 por contrato; tick = 5 pontos; custo por operação ~10 pontos.
A cada vela fechada você decide se abre uma operação AGORA. Método: olhe as velas anteriores do dia e as suas operações anteriores; identifique o que teria dado lucro nesse trecho (que sinal, que direção, que saída) e decida se esse padrão está aparecendo de novo agora. Se não houver nada claro, "nada" é uma resposta normal.
Execução: a entrada é uma ordem limitada no fechamento desta vela, válida por 2 velas. O stop é a mercado; o alvo é limitado (ou sem alvo: a posição fica até o stop ou o fim do pregão).
Responda SÓ com JSON: {"acao": "comprar"|"vender"|"nada", "stop_pts": inteiro, "alvo_pts": inteiro ou null, "motivo": "até 20 palavras"}"""


def chave():
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if linha.startswith("OPENROUTER_API_KEY="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENROUTER_API_KEY não encontrada em .env")


def le_cache():
    c = {}
    if CACHE.exists():
        for l in CACHE.read_text(encoding="utf-8").splitlines():
            if l.strip():
                j = json.loads(l)
                c[j["k"]] = j["r"]
    return c


_CACHE = {}


def pergunta(user, key):
    k = hashlib.sha256((MODELO + SISTEMA + user).encode()).hexdigest()
    if k in _CACHE:
        with _lock:
            _uso["cache"] += 1
        return _CACHE[k]
    corpo = json.dumps({"model": MODELO, "temperature": 0, "max_tokens": 3000,
                        "response_format": {"type": "json_object"},
                        "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": user}],
                        "usage": {"include": True}}).encode()
    for tent in range(4):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=corpo, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.loads(r.read())
            txt = j["choices"][0]["message"]["content"]
            u = j.get("usage", {})
            with _lock:
                _uso["in"] += u.get("prompt_tokens", 0); _uso["out"] += u.get("completion_tokens", 0)
                _uso["custo"] += float(u.get("cost", 0) or 0); _uso["chamadas"] += 1
                _CACHE[k] = txt
                with CACHE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"k": k, "r": txt}, ensure_ascii=False) + "\n")
            return txt
        except Exception as e:  # noqa: BLE001
            if tent == 3:
                raise
            time.sleep(3 * (tent + 1))


def le_decisao(txt):
    try:
        s = txt[txt.index("{"): txt.rindex("}") + 1]
        j = json.loads(s)
        acao = str(j.get("acao", "nada")).lower()
        lado = 1 if acao.startswith("compr") else -1 if acao.startswith("vend") else 0
        stop = float(j.get("stop_pts") or 0)
        alvo = j.get("alvo_pts")
        alvo = None if alvo in (None, "", 0) else float(alvo)
        if lado and stop <= 0:
            lado = 0
        return lado, stop, alvo, str(j.get("motivo", ""))[:120]
    except Exception:  # noqa: BLE001
        return 0, 0.0, None, "resposta inválida"


def simula(D, t, lado, stop_pts, alvo_pts):
    """Mesmo motor de olhar_para_tras.trades_do_dia, com stop/alvo em pontos. -> (entrada, saída, pts) ou None."""
    o, h, l, c = D["open"], D["high"], D["low"], D["close"]
    n, s, lim, F = len(c), lado, c[t], opt.FURA
    stop0 = opt.rnd(lim - s * stop_pts)
    for v in range(t + 1, min(t + 1 + opt.VALIDADE, n)):
        if (l[v] <= stop0 if s == 1 else h[v] >= stop0) or (l[v] <= lim - F if s == 1 else h[v] >= lim + F):
            u, px = v, (min(o[v], lim) if s == 1 else max(o[v], lim))
            break
    else:
        return None
    stop = opt.rnd(px - s * stop_pts)
    alvo = None if alvo_pts is None else opt.rnd(px + s * alvo_pts)
    saida, vs = c[-1], n - 1
    for v in range(u, n):
        ot = px if v == u else o[v]
        if (l[v] <= stop) if s == 1 else (h[v] >= stop):
            saida, vs = (min(ot, stop) if s == 1 else max(ot, stop)), v
            break
        if alvo is not None and v > u and ((h[v] >= alvo + F) if s == 1 else (l[v] <= alvo - F)):
            saida, vs = (max(o[v], alvo) if s == 1 else min(o[v], alvo)), v
            break
    return u, vs, s * (saida - px) - opt.CUSTO


def tabela_velas(D, ate):
    f = lambda x: f"{x:.0f}"
    linhas = ["hora;abert;max;min;fech;vol;mme9;mme21;vwap;atr14"]
    for i in range(ate + 1):
        linhas.append(";".join([D["hora"][i], f(D["open"][i]), f(D["high"][i]), f(D["low"][i]), f(D["close"][i]),
                                f"{D['vol'][i]:.0f}", f(D["e9"][i]), f(D["e21"][i]), f(D["vwap"][i]),
                                f(D["atr"][i])]))
    return "\n".join(linhas)


def roda_dia(D, key, log):
    ini = int(np.searchsorted(D["hora"], INICIO))
    t, trades = ini, []
    while t < D["corte"]:
        hist = "nenhuma" if not trades else "\n".join(
            f"{x['hora']} {'compra' if x['lado'] == 1 else 'venda'} stop {x['stop']:.0f} alvo {x['alvo']} -> "
            f"{x['pts']:+.0f} pts ({x['saida_hora']})" for x in trades)
        user = (f"Pregão anterior: máx {D['ant'][0]:.0f}, mín {D['ant'][1]:.0f}, fech {D['ant'][2]:.0f}.\n"
                f"Velas M5 de hoje até agora (a última acabou de fechar):\n{tabela_velas(D, t)}\n\n"
                f"Suas operações de hoje: {hist}\n\nDecida agora.")
        lado, stop, alvo, motivo = le_decisao(pergunta(user, key))
        if lado:
            r = simula(D, t, lado, stop, alvo)
            if r is None:
                log.append(f"{D['dia']} {D['hora'][t]} {'C' if lado == 1 else 'V'} s{stop:.0f} a{alvo} não encheu")
                t += opt.VALIDADE + 1
                continue
            u, vs, pts = r
            trades.append(dict(dia=D["dia"], hora=D["hora"][t], t=t, lado=lado, stop=stop, alvo=alvo, pts=pts,
                               saida_hora=D["hora"][vs], motivo=motivo))
            log.append(f"{D['dia']} {D['hora'][t]} {'C' if lado == 1 else 'V'} s{stop:.0f} a{alvo} -> {pts:+.0f} | {motivo}")
            t = vs + 1
        else:
            t += 1
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapa", type=int, default=1)
    args = ap.parse_args()
    global _CACHE
    _CACHE = le_cache()
    key = chave()
    ordem = [str(d) for d in np.random.default_rng(opt.SEMENTE + 1).permutation(FASE2)]
    dias_txt = ordem[:ETAPAS[args.etapa]]
    print(f"modelo {MODELO} | etapa {args.etapa}: {' '.join(d[5:] for d in dias_txt)} | ordem completa: "
          f"{' '.join(d[5:] for d in ordem)}", flush=True)

    b = opt.carrega()
    b["vol"] = b.real_volume
    diario = b.groupby("dia").agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    dias = []
    for d in dias_txt:
        ts = pd.Timestamp(d)
        D = opt.prepara_dia(b, ts)
        D["vol"] = b[b.dia == ts].vol.to_numpy(float)
        ant = diario[diario.index < ts].iloc[-1]
        D["ant"] = (ant.high, ant.low, ant.close)
        dias.append(D)

    res, logs = {}, {}
    with ThreadPoolExecutor(max_workers=len(dias)) as ex:
        futs = {ex.submit(roda_dia, D, key, logs.setdefault(D["dia"], [])): D["dia"] for D in dias}
        for f in as_completed(futs):
            d = futs[f]
            res[d] = f.result()
            print(f"{d}: {len(res[d])} trades, {sum(x['pts'] for x in res[d]) * opt.PT_BRL:+.0f} R$", flush=True)

    tr = pd.DataFrame([x for d in dias_txt for x in res[d]])
    for d in dias_txt:
        print("\n".join(logs[d]))
    # nulo: mesmos momentos, mesmo stop/alvo, lado sorteado
    rng = np.random.default_rng(opt.SEMENTE)
    Dpor = {D["dia"]: D for D in dias}
    nulo = np.zeros(N_NULO)
    if len(tr):
        alt = {}
        for i, x in tr.iterrows():
            for s in (1, -1):
                r = simula(Dpor[x.dia], x.t, s, x.stop, x.alvo)
                alt[(i, s)] = 0.0 if r is None else r[2]
        lados = rng.choice([1, -1], size=(N_NULO, len(tr)))
        nulo = np.array([sum(alt[(i, s)] for i, s in zip(tr.index, row)) for row in lados])
    real = tr.pts.sum() if len(tr) else 0.0
    p = (1 + (nulo >= real).sum()) / (1 + N_NULO)
    det = opt.roda(dias, (6, 6, "A", 1))

    linhas = [opt.linha_padrao(f"LLM {MODELO.split('/')[1]}", tr if len(tr) else pd.DataFrame({"pts": [], "dia": []}),
                               dias, {"nulo med R$": opt.num_br(np.median(nulo) * opt.PT_BRL, 0),
                                      "nulo p90 R$": opt.num_br(np.quantile(nulo, .9) * opt.PT_BRL, 0),
                                      "p nulo": opt.num_br(p, 3)}),
              opt.linha_padrao("determ. L30W30Am1", det, dias, {})]
    print(f"\n=== etapa {args.etapa}: {len(dias)} pregões, 1 contrato, capital R$250 ===")
    print(opt.tabela(linhas, ("nulo med R$", "nulo p90 R$", "p nulo"), 13))
    if len(tr):
        por = tr.groupby("dia").pts.sum() * opt.PT_BRL
        print("por dia R$: " + " ".join(f"{d[5:]}:{v:+.0f}" for d, v in por.items()))
        print(f"acerto compra {((tr.lado == 1) & (tr.pts > 0)).sum()}/{(tr.lado == 1).sum()}, "
              f"venda {((tr.lado == -1) & (tr.pts > 0)).sum()}/{(tr.lado == -1).sum()}; "
              f"stop mediano {tr.stop.median():.0f}, sem alvo {tr.alvo.isna().mean():.0%}")
    avanca = real > 0 and real > np.median(nulo)
    print(f"régua: líquido>0 e > mediana do nulo -> {'AVANÇA' if avanca else 'PARA'}")
    print(f"uso: {_uso['chamadas']} chamadas pagas ({_uso['cache']} do cache), {_uso['in']} tok in, {_uso['out']} tok out,"
          f" US$ {_uso['custo']:.4f}")


if __name__ == "__main__":
    main()
