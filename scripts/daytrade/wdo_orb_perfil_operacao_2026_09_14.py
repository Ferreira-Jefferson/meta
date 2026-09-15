"""TESTE (2026-09-14) -- o que as operacoes PERDEDORAS tem em comum?

Pergunta do dono: "nao olhar apenas para o dia, mas para cada uma das
operacoes -- o que as perdedoras tinham em comum que nao tem quando ela da'
win?"

## Por que este desenho e' diferente do que acabou de falhar

A hipotese da agitacao (H2, refutada hoje) comparou MEDIAS de dois grupos
partidos pela mediana da propria amostra, em 4 variaveis correlacionadas
entre si, sobre 28 operacoes. Parecia 4 evidencias; era uma so', vista de 4
angulos, e inverteu de sinal nas duas janelas independentes.

Aqui o desenho e' o oposto em tres pontos:

1. **A descoberta acontece no IS (72 pregoes), nao nas 4 semanas.** A janela
   grande e' quem propoe; as 4 semanas viram observacao.
2. **Toda variavel testada e' declarada ANTES**, e o preco de testar muitas
   e' pago: correcao de Benjamini-Hochberg sobre o conjunto inteiro. Testar
   20 variaveis a 5% produz 1 "achado" por puro acaso -- sem a correcao, o
   relatorio viraria uma maquina de fabricar padrao.
3. **Nada e' achado ate' repetir no OOS_LIMPO**, com a MESMA direcao. O IS
   so' gera candidatos.

## Anti-look-ahead: so' entra o que era conhecido no momento do SINAL

Toda variavel abaixo e' calculada com dado ANTERIOR ao instante em que a
ordem foi armada. MFE/MAE ficam de fora dos preditores de proposito -- eles
so' existem depois que a operacao terminou, entao "o perdedor andou menos a
favor" e' uma descricao do resultado, nunca um sinal de entrada. Eles
aparecem no relatorio apenas na secao descritiva, separados.

`atraso_fill_min` e' a unica variavel posterior ao sinal, e entra porque e'
anterior ao RESULTADO: no instante em que a ordem preenche, o robo ja' sabe
quanto esperou, e poderia (em tese) desistir. Fica marcada como tal.

## As variaveis (18)

    tempo        minutos_desde_abertura, hora_sinal, dia_semana
    faixa        faixa_ticks, faixa_rel_amplitude15, stop_ticks
    rompimento   dist_rompimento_ticks, tentativa_no_dia, tipo, side
    fluxo        vol_5min, vol_15min, aceleracao_vol, nticks_5min
    movimento    amplitude_5min, amplitude_15min, retorno_5min_ticks,
                 alinhamento_ticks (retorno recente NO SENTIDO da operacao),
                 atraso_fill_min

Uso: `python -u scripts/daytrade/wdo_orb_perfil_operacao_2026_09_14.py`
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    excursao, monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)

SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(8, (os.cpu_count() or 4))

#: numericas testadas. `tipo`/`side`/`dia_semana` sao categoricas e vao numa
#: tabela propria (proporcao de vitoria por nivel).
NUMERICAS = [
    "minutos_desde_abertura", "faixa_ticks", "faixa_rel_amplitude15",
    "stop_ticks", "dist_rompimento_ticks", "tentativa_no_dia",
    "vol_5min", "vol_15min", "aceleracao_vol", "nticks_5min",
    "amplitude_5min", "amplitude_15min", "retorno_5min_ticks",
    "alinhamento_ticks", "atraso_fill_min",
]
CATEGORICAS = ["tipo", "side", "dia_semana"]
DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


# ---------------------------------------------------------------------------
# estatistica na mao (sem scipy -- dependencia nova precisa de justificativa)
# ---------------------------------------------------------------------------

def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """U de Mann-Whitney com aproximacao normal e correcao de empates.
    Devolve `(z, p)` bicaudal. Nao-parametrico de proposito: as distribuicoes
    aqui sao assimetricas e com cauda (um alvo cheio vale 4 cortes de
    relogio), entao comparar MEDIAS daria peso demais a cauda."""
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    juntos = [(v, 0) for v in a] + [(v, 1) for v in b]
    juntos.sort(key=lambda x: x[0])
    ranks = [0.0] * len(juntos)
    i = 0
    empates = []
    while i < len(juntos):
        j = i
        while j + 1 < len(juntos) and juntos[j + 1][0] == juntos[i][0]:
            j += 1
        rank_medio = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[k] = rank_medio
        if j > i:
            empates.append(j - i + 1)
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, juntos) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    corr = sum(t ** 3 - t for t in empates)
    var = (n1 * n2 / 12.0) * ((n + 1) - corr / float(n * (n - 1)))
    if var <= 0:
        return float("nan"), float("nan")
    z = (u1 - mu) / math.sqrt(var)
    p = 2 * (1 - _phi(abs(z)))
    return z, p


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def benjamini_hochberg(ps: list[float], alpha: float = 0.05) -> list[bool]:
    """Quais p-valores sobrevivem controlando a taxa de falsa descoberta.
    Sem isto, testar 15 variaveis a 5% entrega ~1 achado falso por rodada --
    e o achado falso e' indistinguivel do verdadeiro no relatorio."""
    indexados = sorted((p, i) for i, p in enumerate(ps) if not math.isnan(p))
    m = len(indexados)
    passou = [False] * len(ps)
    maior_k = -1
    for k, (p, _) in enumerate(indexados, start=1):
        if p <= alpha * k / m:
            maior_k = k
    for k, (_, i) in enumerate(indexados, start=1):
        if k <= maior_k:
            passou[i] = True
    return passou


# ---------------------------------------------------------------------------
# coleta -- um pregao, a celula de PRODUCAO, com as 18 variaveis
# ---------------------------------------------------------------------------

def _janela_antes(bars: pd.DataFrame, ts, minutos: int) -> pd.DataFrame:
    return bars.loc[ts - pd.Timedelta(minutes=minutos):ts]


def variaveis_no_sinal(bars: pd.DataFrame, ordem: dict, abertura) -> dict:
    ts = ordem["sinal_ts"]
    v = {}
    for minutos in (5, 15):
        jan = _janela_antes(bars, ts, minutos)
        v[f"vol_{minutos}min"] = float(jan["volume"].sum()) if not jan.empty else float("nan")
        v[f"nticks_{minutos}min"] = int(len(jan))
        v[f"amplitude_{minutos}min"] = (float((jan["close"].max() - jan["close"].min()) / TICK_SIZE)
                                        if not jan.empty else float("nan"))
        if minutos == 5 and not jan.empty:
            v["retorno_5min_ticks"] = float(
                (jan["close"].iloc[-1] - jan["close"].iloc[0]) / TICK_SIZE)
    # aceleracao: o fluxo dos ultimos 5 min contra o ritmo dos 15
    v["aceleracao_vol"] = (v["vol_5min"] / (v["vol_15min"] / 3.0)
                           if v.get("vol_15min") else float("nan"))
    v["faixa_ticks"] = ordem["faixa_ticks"]
    v["stop_ticks"] = ordem["stop_ticks"]
    v["faixa_rel_amplitude15"] = (ordem["faixa_ticks"] / v["amplitude_15min"]
                                  if v.get("amplitude_15min") else float("nan"))
    # o quanto o preco esticou ALEM da faixa antes de a ordem ser armada
    if ordem["side"] == "long" and ordem["faixa_hi"] is not None:
        bruto = (ordem["preco_sinal"] - ordem["faixa_hi"]) / TICK_SIZE
    elif ordem["faixa_lo"] is not None:
        bruto = (ordem["faixa_lo"] - ordem["preco_sinal"]) / TICK_SIZE
    else:
        bruto = float("nan")
    # no FADE o rompimento e' do lado contrario ao da operacao, entao o sinal
    # do calculo acima se inverte -- `abs` deixa a variavel com o MESMO
    # significado nos dois casos: distancia percorrida alem da borda.
    v["dist_rompimento_ticks"] = abs(bruto) if not pd.isna(bruto) else float("nan")
    v["minutos_desde_abertura"] = (ts - abertura).total_seconds() / 60.0
    ts_brt = pd.Timestamp(ts).tz_convert("America/Sao_Paulo")
    v["hora_sinal"] = ts_brt.hour
    v["dia_semana"] = DIAS_PT[ts_brt.weekday()]
    return v


def roda_pregao(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    strat = WdoOrbInstrumentado()          # producao: T2.0, com fade
    cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
    res = run_intraday_backtest(bars, strat, cfg)
    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    abertura = bars.index.min()
    linhas = []
    for t in sorted(res.trades, key=lambda x: x.entry_ts):
        ordem, tentativa = None, 0
        for k, o in enumerate(ordens, start=1):
            if o["sinal_ts"] <= t.entry_ts:
                ordem, tentativa = o, k
            else:
                break
        if ordem is None:
            continue
        pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                      else (t.entry_price - t.exit_price)) / TICK_SIZE)
        razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                 else str(t.exit_reason))
        exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
        v = variaveis_no_sinal(bars, ordem, abertura)
        sinal_lado = 1.0 if t.side == "long" else -1.0
        linhas.append({
            "data": dia,
            "tipo": ordem["tipo"], "side": t.side,
            "tentativa_no_dia": tentativa,
            "atraso_fill_min": (t.entry_ts - ordem["sinal_ts"]).total_seconds() / 60.0,
            "alinhamento_ticks": sinal_lado * v.get("retorno_5min_ticks", float("nan")),
            "pnl_brl": round(t.pnl_brl, 2),
            "venceu": int(t.pnl_brl > 0),
            "saida_efetiva": classifica_saida(razao, pnl_ticks, ordem["alvo_ticks"]),
            "mfe_ticks": round(exc["mfe_ticks"], 1),
            "mae_ticks": round(exc["mae_ticks"], 1),
            **v,
        })
    return linhas


# ---------------------------------------------------------------------------

def tabela_numericas(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df.venceu == 1]
    p = df[df.venceu == 0]
    linhas, ps = [], []
    for var in NUMERICAS:
        a = [x for x in g[var].tolist() if not pd.isna(x)]
        b = [x for x in p[var].tolist() if not pd.isna(x)]
        z, pv = mann_whitney_u(a, b)
        linhas.append({
            "variavel": var,
            "venceu_mediana": round(pd.Series(a).median(), 2) if a else float("nan"),
            "perdeu_mediana": round(pd.Series(b).median(), 2) if b else float("nan"),
            "dif_pct": (round(100.0 * (pd.Series(a).median() - pd.Series(b).median())
                              / abs(pd.Series(b).median()), 1)
                        if b and pd.Series(b).median() != 0 else float("nan")),
            "z": round(z, 2), "p": round(pv, 4),
        })
        ps.append(pv)
    passou = benjamini_hochberg(ps)
    for linha, ok in zip(linhas, passou):
        linha["sobrevive_BH"] = "SIM" if ok else "nao"
    return pd.DataFrame(linhas).sort_values("p")


def tabela_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for var in CATEGORICAS:
        for nivel, sub in df.groupby(var):
            linhas.append({
                "variavel": var, "nivel": nivel, "n": len(sub),
                "win_pct": round(100.0 * sub.venceu.mean(), 1),
                "rs_por_op": round(sub.pnl_brl.mean(), 2),
                "liquido": round(sub.pnl_brl.sum(), 2),
            })
    return pd.DataFrame(linhas)


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
        print(f"[janela] {rotulo}: {len(dias)} pregoes", flush=True)
    print(f"\n[perfil] {len(todos)} pregoes, {MAX_WORKERS} processos\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "50_perfil_operacoes.csv", index=False, encoding="utf-8")
    print(f"\n[perfil] {len(df)} operacoes -> 50_perfil_operacoes.csv")

    is_ = df[df.janela == "IS"]
    oos = df[df.janela == "OOS_LIMPO"]
    desc = df[df.janela == "DESCOBERTA"]

    print("\n" + "=" * 118)
    print(f"IS -- DESCOBERTA DE CANDIDATOS  ({len(is_)} operacoes: "
          f"{int(is_.venceu.sum())} venceram, {int((1-is_.venceu).sum())} perderam)")
    print("=" * 118)
    t_is = tabela_numericas(is_)
    print(t_is.to_string(index=False))
    t_is.to_csv(SAIDA / "51_perfil_is.csv", index=False, encoding="utf-8")

    candidatas = t_is[t_is.sobrevive_BH == "SIM"]["variavel"].tolist()
    brutas = t_is[(t_is.p < 0.05)]["variavel"].tolist()
    print(f"\n  sobrevivem a Benjamini-Hochberg no IS: "
          f"{candidatas if candidatas else 'NENHUMA'}")
    print(f"  (p<0,05 sem correcao, so' para registro: {brutas if brutas else 'nenhuma'})")

    print("\n" + "=" * 118)
    print(f"OOS_LIMPO -- VALIDACAO  ({len(oos)} operacoes)")
    print("=" * 118)
    t_oos = tabela_numericas(oos)
    print(t_oos.to_string(index=False))
    t_oos.to_csv(SAIDA / "52_perfil_oos.csv", index=False, encoding="utf-8")

    print("\n--- veredito por variavel: a direcao do IS se repete no OOS? ---")
    ver = []
    for var in NUMERICAS:
        a = t_is[t_is.variavel == var].iloc[0]
        b = t_oos[t_oos.variavel == var].iloc[0]
        dir_is = a.venceu_mediana - a.perdeu_mediana
        dir_oos = b.venceu_mediana - b.perdeu_mediana
        mesma = (dir_is > 0) == (dir_oos > 0)
        ver.append({"variavel": var,
                    "IS_dif": round(dir_is, 2), "IS_p": a.p, "IS_BH": a.sobrevive_BH,
                    "OOS_dif": round(dir_oos, 2), "OOS_p": b.p,
                    "mesma_direcao": "SIM" if mesma else "INVERTE",
                    "veredito": ("CONFIRMADA" if (a.sobrevive_BH == "SIM" and mesma
                                                   and b.p < 0.05)
                                 else "candidata IS, nao confirma" if a.sobrevive_BH == "SIM"
                                 else "-")})
    df_ver = pd.DataFrame(ver).sort_values("IS_p")
    print(df_ver.to_string(index=False))
    df_ver.to_csv(SAIDA / "53_perfil_veredito.csv", index=False, encoding="utf-8")

    print("\n--- categoricas (IS | OOS | DESCOBERTA) ---")
    for nome, sub in [("IS", is_), ("OOS_LIMPO", oos), ("DESCOBERTA", desc)]:
        tc = tabela_categoricas(sub)
        tc.insert(0, "janela", nome)
        print(tc.to_string(index=False))
        print()
        tc.to_csv(SAIDA / f"54_categoricas_{nome}.csv", index=False, encoding="utf-8")

    print("--- DESCRITIVO (nao e' preditor: so' existe depois do resultado) ---")
    desc_mm = df.groupby(["janela", "venceu"])[["mfe_ticks", "mae_ticks"]].median().round(1)
    print(desc_mm.to_string())

    print(f"\n[perfil] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
