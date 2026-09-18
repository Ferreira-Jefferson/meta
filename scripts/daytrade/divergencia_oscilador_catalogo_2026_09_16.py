# -*- coding: utf-8 -*-
"""DIVERGÊNCIA oscilador × preço — a camada que REFUTA primeiro, sem custo.

Pedido do dono (2026-09-16), depois de confirmar que Elliott e Fibonacci já
foram medidos e refutados: a divergência nunca foi testada neste projeto.

## Por que este script não é um backtest

A divergência é uma afirmação sobre DIREÇÃO: "o preço fez topo mais alto, o
oscilador não acompanhou, logo o movimento está exaurido e vai virar". Se
essa afirmação for falsa, nenhuma geometria de alvo/stop a salva, e nenhum
modelo de fila ou de deslize muda o veredito — é o modo de morte
*cost-independent* que já matou Wyckoff/SMC e a cor do minuto do WDO.

Então a ordem é: primeiro perguntar se o sinal aponta para algum lado; só o
que sobreviver ganha o direito de virar robô com entrada limite, alvo maker
e fila calibrada (`feedback_teste_pequeno_valida_hipotese`).

## A métrica que decide: CORRIDA SIMÉTRICA

Para cada evento, a partir da abertura da barra SEGUINTE à confirmação:
o preço anda +A ticks a favor antes de −A ticks contra?

Simétrica de propósito. O nulo é **exatamente 50%**, sem depender de custo,
de payoff ou de breakeven empírico — qualquer edge direcional aparece como
afastamento de 50%, e a leitura não muda se amanhã a corretagem mudar.
Medida em três tamanhos (4/8/16 ticks) porque "exaustão" pode existir em
escala curta e sumir na longa.

## Os DOIS nulos, porque um só não basta

1. **50% teórico** da corrida simétrica (binomial, IC95 de Wilson sobre os
   eventos resolvidos).
2. **CONTROLE casado — o que de fato decide.** Mesma geometria de pivô, mesma
   convenção de lado, mesmo instante do dia; só a condição do oscilador
   INVERTIDA (topo mais alto COM oscilador mais alto = confirmação, não
   divergência). Se DIV e CONTROLE derem o mesmo número, o que está sendo
   medido é o pivô, não a divergência. Sem esse grupo, um viés intradiário do
   WDO (que existe: −442 pontos no intradiário contra +372 no overnight)
   seria lido como edge. Ver `metodo_nulo_signflip_custo_2026_08_26`.

Junto vai a linha `TODAS_BARRAS` (1 a cada 30 barras, lado short fixo): a
taxa incondicional da corrida no mesmo período, que ancora as outras três.

## Causalidade — onde a divergência costuma trapacear

Um pivô de topo em `i` só é conhecido `L` barras depois (precisa das barras à
DIREITA para ser pivô). Detector ingênuo carimba o evento em `i` e colhe o
movimento que já aconteceu — look-ahead puro, e é o erro clássico desta
família. Aqui o evento nasce na barra de CONFIRMAÇÃO `t = i + L`, e a
medição começa na abertura de `t+1` (regra do repo: decide no fechamento,
executa na abertura seguinte).

## O catálogo (8 unidades, nenhuma otimização)

2 símbolos (WDO@, WIN@) × 2 osciladores (IFR14, MACD 12/26) × 2 lookbacks
de pivô (L=3, L=5). Cada unidade mede 3 grupos:

| grupo | extremo do preço | oscilador | lado da medição |
|---|---|---|---|
| `REGULAR` | topo mais alto (fundo mais baixo) | NÃO acompanha | contra o movimento |
| `OCULTA` | topo mais baixo (fundo mais alto) | NÃO acompanha | a favor do movimento |
| `CONTROLE` | topo mais alto (fundo mais baixo) | ACOMPANHA | contra (mesma convenção do REGULAR) |

Os limiares (separação mínima/máxima entre pivôs, teto de 120 barras) são
ESCOLHAS declaradas, não calibrações — mesma disciplina do catálogo de
lateralização. Nada aqui é escolhido olhando resultado.

## Disciplina de janela

**Só IS** (< 2026-06-13). O OOS não é tocado: nenhuma hipótese desta rodada
ganhou ainda o direito de gastá-lo (`copa_oos_gasto_2026_08_26`).

## O que este script NÃO responde

- Executabilidade: fila, deslize, preenchimento. Se o sinal passar, a camada
  2 é um robô no desenho fechado (entrada `EnterLimit` com prazo, alvo em
  ordem-limite fatiada, stop a mercado) — e aí o custo decide de novo.
- Independência entre eventos: eventos do mesmo pregão se sobrepõem. Por
  isso vai também a linha `1/pregão` (só o primeiro evento de cada grupo em
  cada pregão), que é amostra menor mas independente.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/divergencia_oscilador_catalogo_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from core.indicators import ifr  # noqa: E402
from core.instruments import economics_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

SIMBOLOS = ("WDO@", "WIN@")
CORTE_OOS = pd.Timestamp("2026-06-13").date()
MIN_BARRAS_POR_PREGAO = 400
SAO_PAULO = "America/Sao_Paulo"

#: escolhas declaradas (não calibradas)
LOOKBACKS = (3, 5)
SEP_MIN_EXTRA = 1          # separação mínima entre pivôs = 2L + SEP_MIN_EXTRA
SEP_MAX = 60               # separação máxima entre os dois pivôs, em barras
TETO_BARRAS = 120          # teto da corrida (~2h); o fim do pregão também corta
CORRIDAS_TICKS = (4, 8, 16)
HORIZONTES = (10, 30, 60)  # barras à frente, para o deslocamento assinado
PASSO_BASELINE = 30        # 1 a cada N barras para a linha TODAS_BARRAS

GRUPOS = ("REGULAR", "OCULTA", "CONTROLE")
Z95 = 1.959963984540054


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int) -> tuple[float, float]:
    """IC95 de proporção (Wilson) — o normal quebra em n pequeno / p extremo."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = p + Z95 * Z95 / (2 * n)
    r = Z95 * np.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def z_vs_meio(k: int, n: int) -> float:
    """z da binomial contra p0 = 0,50 (o nulo exato da corrida simétrica)."""
    if n <= 0:
        return float("nan")
    return (k / n - 0.5) / np.sqrt(0.25 / n)


def macd_linha(close: pd.Series, rapida: int = 12, lenta: int = 26) -> pd.Series:
    """Linha MACD (EMA rápida − EMA lenta). Inline aqui de propósito: só sobe
    para `core/indicators.py` se a hipótese sobreviver — indicador que nasce
    no núcleo por causa de um teste que morreu é peso morto."""
    ema_r = close.ewm(span=rapida, adjust=False, min_periods=rapida).mean()
    ema_l = close.ewm(span=lenta, adjust=False, min_periods=lenta).mean()
    return ema_r - ema_l


def pivos(valores: np.ndarray, L: int, topo: bool) -> np.ndarray:
    """Índices dos pivôs. Pivô de topo em `i` = `valores[i]` é o máximo ESTRITO
    da janela `[i-L, i+L]`. Estrito para não gerar dois pivôs empatados."""
    n = len(valores)
    out: list[int] = []
    for i in range(L, n - L):
        jan = valores[i - L : i + L + 1]
        v = valores[i]
        if np.isnan(v) or np.isnan(jan).any():
            continue
        esq, dir_ = jan[:L], jan[L + 1 :]
        if topo:
            if (esq < v).all() and (dir_ < v).all():
                out.append(i)
        else:
            if (esq > v).all() and (dir_ > v).all():
                out.append(i)
    return np.asarray(out, dtype=int)


def corrida(h: np.ndarray, l: np.ndarray, entrada: float, i0: int, i_fim: int,
            alcance: float, lado: int) -> int:
    """+1 alvo primeiro, −1 stop primeiro, 0 ambos na MESMA barra (indefinido —
    M1 não resolve a ordem dentro da barra, e inventar a ordem é exatamente o
    tipo de otimismo que o motor já pagou caro), 2 não resolveu no prazo."""
    alvo = entrada + lado * alcance
    stop = entrada - lado * alcance
    for k in range(i0, i_fim + 1):
        if lado > 0:
            bateu_alvo, bateu_stop = h[k] >= alvo, l[k] <= stop
        else:
            bateu_alvo, bateu_stop = l[k] <= alvo, h[k] >= stop
        if bateu_alvo and bateu_stop:
            return 0
        if bateu_alvo:
            return 1
        if bateu_stop:
            return -1
    return 2


def eventos_do_pregao(g: pd.DataFrame, osc: pd.Series, L: int) -> list[dict]:
    """Todos os eventos de UM pregão. `t` é a barra de CONFIRMAÇÃO (i+L); a
    medição começa na abertura de t+1."""
    high = g["high"].to_numpy(float)
    low = g["low"].to_numpy(float)
    o = osc.to_numpy(float)
    n = len(g)
    sep_min = 2 * L + SEP_MIN_EXTRA
    eventos: list[dict] = []

    for topo in (True, False):
        piv = pivos(high if topo else low, L, topo)
        for pos in range(1, len(piv)):
            i, j = int(piv[pos]), int(piv[pos - 1])
            if not (sep_min <= i - j <= SEP_MAX):
                continue
            t = i + L                      # barra de confirmação
            if t + 1 >= n:
                continue
            if np.isnan(o[i]) or np.isnan(o[j]):
                continue
            if topo:
                # "estende" = topo mais ALTO; oscilador acompanha se também subiu
                estende, osc_acompanha = high[i] > high[j], o[i] > o[j]
                recua = high[i] < high[j]
                lado = -1                  # topo -> convenção short
            else:
                # "estende" = fundo mais BAIXO; oscilador acompanha se também caiu
                estende, osc_acompanha = low[i] < low[j], o[i] < o[j]
                recua = low[i] > low[j]
                lado = +1                  # fundo -> convenção long

            if estende and not osc_acompanha:
                grupo = "REGULAR"
            elif estende and osc_acompanha:
                grupo = "CONTROLE"
            elif recua and osc_acompanha:
                grupo = "OCULTA"
                lado = -lado               # oculta é continuação: lado invertido
            else:
                continue
            eventos.append(dict(grupo=grupo, t=t, lado=lado, topo=topo))
    return eventos


def mede_eventos(g: pd.DataFrame, eventos: list[dict], tick: float, dia) -> list[dict]:
    o_ = g["open"].to_numpy(float)
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    n = len(g)
    linhas = []
    for ev in eventos:
        t, lado = ev["t"], ev["lado"]
        i0 = t + 1
        entrada = o_[i0]
        i_fim = min(n - 1, i0 + TETO_BARRAS - 1)
        reg = dict(grupo=ev["grupo"], dia=dia, t=t, lado=lado)
        for A in CORRIDAS_TICKS:
            reg[f"corrida_{A}"] = corrida(h, l, entrada, i0, i_fim, A * tick, lado)
        for H in HORIZONTES:
            k = min(n - 1, i0 + H - 1)
            reg[f"desl_{H}"] = lado * (c[k] - entrada) / tick
        linhas.append(reg)
    return linhas


def _unidade(args) -> tuple[str, str]:
    simbolo, nome_osc, L = args
    buf = StringIO()
    with redirect_stdout(buf):
        tick = economics_for(simbolo).price_tick_size
        df = load_m1(simbolo)
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        df = df.copy()
        df.index = idx.tz_convert(SAO_PAULO)

        linhas: list[dict] = []
        base: list[dict] = []
        pregoes = 0
        for dia, g in df.groupby(df.index.normalize()):
            if dia.date() >= CORTE_OOS or len(g) < MIN_BARRAS_POR_PREGAO:
                continue
            pregoes += 1
            osc = (ifr(g["close"], window=14) if nome_osc == "IFR14"
                   else macd_linha(g["close"]))
            linhas.extend(mede_eventos(g, eventos_do_pregao(g, osc, L), tick, dia.date()))
            evs_base = [dict(grupo="TODAS_BARRAS", t=t, lado=-1, topo=True)
                        for t in range(3 * L, len(g) - 2, PASSO_BASELINE)]
            base.extend(mede_eventos(g, evs_base, tick, dia.date()))

        ev = pd.DataFrame(linhas)
        bs = pd.DataFrame(base)
        todos = pd.concat([ev, bs], ignore_index=True) if len(bs) else ev

        titulo = f"{simbolo} · {nome_osc} · L={L}"
        print("=" * 112)
        print(f"{titulo}   ({pregoes} pregões IS, tick {br(tick, 2)} pt)")
        print("=" * 112)
        if todos.empty:
            print("  sem eventos.")
            return titulo, buf.getvalue()

        print("\n  CORRIDA SIMÉTRICA — anda +A ticks a favor antes de −A contra (nulo EXATO = 50,00%)\n")
        cab = f"  {'grupo':<14}{'n':>7}" + "".join(
            f"{f'±{A}t win%':>11}{'IC95':>18}{'z':>8}{'n.res':>8}" for A in CORRIDAS_TICKS)
        print(cab)
        print("  " + "-" * (len(cab) - 2))
        for grupo in (*GRUPOS, "TODAS_BARRAS"):
            sub = todos[todos["grupo"] == grupo]
            if sub.empty:
                continue
            campos = [f"  {grupo:<14}{len(sub):>7}"]
            for A in CORRIDAS_TICKS:
                r = sub[f"corrida_{A}"]
                k, p = int((r == 1).sum()), int((r == -1).sum())
                nres = k + p
                lo, hi = ic95(k, nres)
                txt_p = (br(100 * k / nres, 2) + "%") if nres else "—"
                txt_ic = ("[" + br(100 * lo, 2) + ";" + br(100 * hi, 2) + "]") if nres else "—"
                campos.append(f"{txt_p:>11}{txt_ic:>18}{br(z_vs_meio(k, nres), 2):>8}{nres:>8}")
            print("".join(campos))

        print("\n  DESLOCAMENTO ASSINADO (ticks a favor do lado do sinal) — mediana [média ± IC95]\n")
        cab2 = f"  {'grupo':<14}{'n':>7}" + "".join(f"{f'H={H}b':>30}" for H in HORIZONTES)
        print(cab2)
        print("  " + "-" * (len(cab2) - 2))
        for grupo in (*GRUPOS, "TODAS_BARRAS"):
            sub = todos[todos["grupo"] == grupo]
            if sub.empty:
                continue
            campos = [f"  {grupo:<14}{len(sub):>7}"]
            for H in HORIZONTES:
                x = sub[f"desl_{H}"].to_numpy(float)
                med, mu = float(np.median(x)), float(np.mean(x))
                e = Z95 * float(np.std(x, ddof=1)) / np.sqrt(len(x)) if len(x) > 1 else float("nan")
                campos.append(f"{br(med, 2) + '  [' + br(mu, 2) + ' ± ' + br(e, 2) + ']':>30}")
            print("".join(campos))

        print("\n  INDEPENDÊNCIA — só o PRIMEIRO evento de cada grupo em cada pregão (corrida ±8t)\n")
        print(f"  {'grupo':<14}{'n':>7}{'win%':>11}{'IC95':>20}{'z':>8}")
        for grupo in GRUPOS:
            sub = todos[todos["grupo"] == grupo].sort_values("t").groupby("dia").head(1)
            if sub.empty:
                continue
            r = sub["corrida_8"]
            k, p = int((r == 1).sum()), int((r == -1).sum())
            if not (k + p):
                continue
            lo, hi = ic95(k, k + p)
            print(f"  {grupo:<14}{len(sub):>7}{br(100 * k / (k + p), 2) + '%':>11}"
                  f"{('[' + br(100 * lo, 2) + ';' + br(100 * hi, 2) + ']'):>20}"
                  f"{br(z_vs_meio(k, k + p), 2):>8}")

        n_tot = len(todos)
        nao_res = ", ".join(
            f"±{A}t {br(100 * int((todos[f'corrida_{A}'] == 2).sum()) / n_tot, 1)}%" for A in CORRIDAS_TICKS)
        indef = ", ".join(
            f"±{A}t {br(100 * int((todos[f'corrida_{A}'] == 0).sum()) / n_tot, 1)}%" for A in CORRIDAS_TICKS)
        print(f"\n  não resolvidas no prazo ({TETO_BARRAS}b / fim de pregão): {nao_res}")
        print(f"  indefinidas (alvo e stop na MESMA barra M1): {indef}")
    return titulo, buf.getvalue()


def main() -> None:
    unidades = [(s, osc, L) for s in SIMBOLOS for osc in ("IFR14", "MACD") for L in LOOKBACKS]
    print(f"DIVERGÊNCIA oscilador × preço — catálogo cost-independent, "
          f"{len(unidades)} unidades, só IS (< {CORTE_OOS})")
    print("Corrida SIMÉTRICA: nulo exato 50%. Controle casado = mesmo pivô, oscilador CONCORDANDO.\n")
    with ProcessPoolExecutor(max_workers=min(8, len(unidades))) as pool:
        futuros = {pool.submit(_unidade, u): u for u in unidades}
        for fut in as_completed(futuros):
            _, saida = fut.result()
            print(saida, flush=True)


if __name__ == "__main__":
    main()
