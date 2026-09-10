"""RE-DERIVA do terminal MT5 a FIDELIDADE DE EXECUCAO do WDO F1 -- quanta
FILA existe na frente da nossa ordem-limite, dos dois lados -- e mede o custo
NOVO que apareceu quando a fatia de saida perdeu o prazo.

SOMENTE LEITURA. Nao manda ordem, nao toca `db/live.sqlite`, nao inicia nem
mata processo nenhum. Pode rodar com o robo operando.

## Por que este script existe (e nao so' a tabela)

Os numeros que ele produz alimentam `backtest.intraday.fidelidade.
FIDELIDADE`, que `profiles.config_for` le' sozinho. A tabela e' a FONTE DA
VERDADE; este script e' o que permite REFRESCA-LA em vez de deixa-la
envelhecer. A amostra de 2026-09-09 tem n=67 na entrada e n=25 na saida --
esta ultima e' pouca, e cada pregao real novo quase dobra ela.

Rodar isto num pregao novo e reeditar UMA linha de `fidelidade.py` e' o ciclo
inteiro de manutencao do modelo.

## O metodo

`history_orders_get` da' o instante em que a ordem-limite ENTROU no book
(`time_setup_msc`), o instante em que ela preencheu ou foi cancelada
(`time_done_msc`) e o estado final. `copy_ticks_range` da' todo negocio do
dia. Q_frente de uma ordem = volume negociado EXATAMENTE NO PRECO DELA entre
os dois instantes.

Ordem que preencheu: a fila valia aquilo (EVENTO). Ordem que morreu sem
preencher: a fila valia MAIS que aquilo -- observacao CENSURADA a direita,
que entra na conta em vez de ser descartada. Dai **Kaplan-Meier**: usar so'
as que preencheram e' vies de sobrevivencia puro (ordem que preenche e' ordem
que GANHOU a fila) e ele so' anda para um lado, subestimando Q. Em 2026-09-09
a diferenca foi de 21% (entrada) e 24% (saida).

Ordem que preencheu em menos de `ESPERA_MINIMA_S` = 0,5s e' descartada: ja'
estava agressiva ao postar e nunca entrou em fila nenhuma. Mante-la como
"evento em v=0" derrubaria a mediana por um motivo que nao e' fila.

Discriminador ENTRADA x SAIDA: o MT5 so' carimba `position_id` em ordem que
EXECUTOU, entao a limite de saida cancelada sai com `position_id = 0`, igual
a uma de entrada -- e sao justamente essas as de fila grande. O script
reconstroi os intervalos de posicao ABERTA a partir dos deals e classifica
como SAIDA toda limite postada dentro de um intervalo, no lado OPOSTO ao da
posicao.

## O refinamento MEDIDO e REFUTADO (secao "agressor", roda sempre)

Hipotese razoavel: uma limite de VENDA parada na oferta so' e' executada por
quem COMPRA agredindo, entao so' o volume do agressor contrario deveria comer
a nossa fila -- e o motor, que desconta o volume INTEIRO da barra, estaria
errado. Medido em 2026-09-09: no dia inteiro o volume se divide 50,1% /
50,1%, mas NO NIVEL DA NOSSA PROPRIA ORDEM 99,3% dele e' do lado que executa
contra nos. Obvio depois de ver: a nossa limite esta' na melhor oferta, entao
negocio naquele preco e', por definicao, alguem agredindo a nossa ponta.

A secao continua rodando (e nao virou comentario) porque o numero e' de UM
pregao: se um dia ela imprimir 60% em vez de 99%, a conclusao muda.

## Os DOIS REGIMES de saida -- leia antes de juntar pregoes

Ate 2026-09-09 a fatia de alvo tinha PRAZO (`exit_ttl_bars`, ~22s): a ordem
que nao preenchia era CANCELADA, e foi isso que produziu 17 censuradas em 25.
A partir de 2026-09-09 a producao roda SEM PRAZO (`wdo_grid_reload_maker.
EXIT_TTL_BARS_SEM_PRAZO`, ordem do dono): a limite fica no livro ate' o
mercado pagar o alvo, e sobram tres saidas -- alvo como limite, stop, ou
achatamento no fim do pregao.

A censura muda de NATUREZA: no regime sem prazo a maioria das observacoes
vira EVENTO, e as poucas que sobram censuradas sao censuradas no fim do
pregao, com volume acumulado alto. Kaplan-Meier lida com os dois casos sem
mudanca -- o estimador continua o mesmo. Mas a TAXA DE CENSURA por pregao e'
impressa exatamente para quem le' perceber de que regime aquele dia veio, e
o script AVISA quando a janela mistura pregoes com taxas muito diferentes.
Juntar regimes numa curva so' sem perceber produziria uma mediana que nao
descreve nem um nem outro.

## As tres metricas NOVAS (o custo que substituiu a derrapagem do prazo)

Sem prazo, o robo deixa de pagar a saida a mercado do estouro -- e passa a
pagar outra coisa. Ninguem mediu ainda o que:

  1. **Saidas por ACHATAMENTO de fim de pregao** -- quantas e quanto custaram
     (R$ e ticks contra o preco de entrada). Caminho novo, custo desconhecido.
  2. **TEMPO DE POSICAO ABERTA** (mediana/p75/p90/maximo). Este e' o custo
     novo de verdade: o motor NAO piramida (`motor_nao_piramida_2026_08_26`),
     entao enquanto a limite espera, o robo nao abre outra posicao. Sem prazo
     ele troca derrapagem por CAIXA PARADO, e caixa parado precisa de numero.
  3. **Posicoes que o pregao inteiro nao pagou** -- quantas chegaram ao
     achatamento sem o alvo nunca ter preenchido, como fracao do total.

AS DUAS PRIMEIRAS NAO TEM VALOR DE REFERENCIA AINDA. O pregao de 2026-09-09
rodou COM prazo; o primeiro pregao SEM prazo e' que vai gerar a linha de base
delas. Ate' la', o que este script imprime nessas duas secoes e' o "antes" --
util para comparar, nao para julgar.

## Uso

    .\\.venv\\Scripts\\python.exe scripts/daytrade/wdof1_calibra_fila_real_2026_09_09.py
    .\\.venv\\Scripts\\python.exe scripts/daytrade/wdof1_calibra_fila_real_2026_09_09.py \\
        --de 2026-09-09 --ate 2026-09-11 --simbolo WDOV26

`--ate` e' EXCLUSIVO. O simbolo e' o CONTRATO REAL com vencimento (`WDOV26`),
nao a serie continua (`WDO@`): o historico de ordens/deals so' existe no
contrato negociado. O `--magic` isola o robo -- ordem manual do dono no mesmo
terminal nao pode entrar na amostra, porque ela nao passou pela mesma fila
nem pela mesma regra.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.profiles import profile_for  # noqa: E402
from core.b3_session import utc_to_server_wall_clock  # noqa: E402
from core.instruments import economics_for  # noqa: E402

#: Robo `wdo_grid_reload_maker` (WDO F1) em producao. O magic e' o que separa
#: as ordens DELE de qualquer outra coisa no mesmo terminal.
MAGIC_WDO_F1 = 862399285
SIMBOLO_PADRAO = "WDOV26"
#: Serie CONTINUA correspondente -- so' para ler a economia declarada
#: (valor do ponto, tick) de `core.instruments`, que e' por instrumento.
CONTINUA = "WDO@"

#: Janela que produziu a calibracao vigente em `backtest.intraday.
#: fidelidade.FIDELIDADE["WDO@"]` -- e' o DEFAULT do script exatamente para
#: que rodar sem argumento nenhum REPRODUZA a tabela (438/489, n=67 e n=25).
#: Um script de calibracao cujo default nao reproduz o numero em vigor e' um
#: script que ninguem consegue usar para conferir se a tabela ainda vale.
#:
#: Sao dois pregoes (2026-09-08 e 2026-09-09) e a assimetria e' real: o lado
#: da SAIDA so' tem observacao de 09-09 (a fatia de alvo como ordem-limite
#: nasceu em 08-09 e nao gerou ordem qualificada naquele dia), enquanto o
#: lado da ENTRADA aproveita os dois. Restringir a janela a 09-09 daria
#: n=40 e mediana 508 na entrada, com a saida intacta.
JANELA_DA_CALIBRACAO = ("2026-09-07", "2026-09-10")

#: Ordem que preencheu em menos disto ja' estava agressiva ao postar: a
#: corretora executou na hora, ela nunca entrou em fila. Entra como "evento
#: em v=0" e derrubaria a mediana por um motivo que nao e' fila.
ESPERA_MINIMA_S = 0.5

#: Diferenca de taxa de censura entre pregoes acima da qual o script avisa
#: que a janela provavelmente mistura o regime COM prazo e o SEM prazo (ver
#: a secao "os dois regimes" na docstring). Nao e' teste estatistico -- e'
#: um limiar para chamar atencao do leitor.
SALTO_DE_CENSURA_SUSPEITO = 0.30


# --------------------------------------------------------------------------
# Kaplan-Meier
# --------------------------------------------------------------------------

def kaplan_meier(volumes: np.ndarray, eventos: np.ndarray) -> list[tuple[float, float]]:
    """Curva S(v) = probabilidade de a fila AINDA NAO ter chegado na gente
    depois de `v` contratos negociados no nosso nivel.

    `eventos[i]` True = a ordem i preencheu com `volumes[i]` negociado no
    nivel (a fila valia aquilo). False = ela morreu antes (a fila valia
    MAIS que aquilo -- censurada a direita, e o peso dela vai para o
    denominador "em risco" de todos os eventos anteriores, que e' exatamente
    o que a mediana ingenua joga fora).

    Devolve a curva como degraus `(v, S(v))`, comecando em `(0, 1)`."""
    curva = [(0.0, 1.0)]
    sobrevivencia = 1.0
    for v in np.sort(np.unique(volumes[eventos])):
        em_risco = int((volumes >= v).sum())
        if em_risco == 0:
            continue
        mortes = int(((volumes == v) & eventos).sum())
        sobrevivencia *= 1 - mortes / em_risco
        curva.append((float(v), sobrevivencia))
    return curva


def quantil_km(curva: list[tuple[float, float]], fracao: float) -> float | None:
    """Menor `v` em que a curva ja' desceu a `1 - fracao` (mediana =
    `fracao=0.5`). `None` quando a curva NUNCA chega la' -- o que acontece
    quando a censura e' pesada demais para a amostra decidir, e devolver o
    ultimo `v` observado ali seria inventar um numero para baixo."""
    alvo = 1.0 - fracao
    return next((v for v, s in curva if s <= alvo + 1e-12), None)


def imprime_lado(rotulo: str, df: pd.DataFrame, n_descartadas: int) -> float | None:
    """Imprime a curva de Kaplan-Meier de UM lado e devolve a mediana."""
    print(f"\n{'=' * 74}")
    print(f"{rotulo}")
    print("=" * 74)
    if df.empty:
        print("  n=0 -- nenhuma ordem deste lado esperou em fila na janela.")
        return None

    volumes = df["vol_nivel"].to_numpy(dtype=float)
    eventos = df["preencheu"].to_numpy(dtype=bool)
    n, n_fill = len(df), int(eventos.sum())
    censura = 1.0 - n_fill / n
    print(f"  ordens que ESPERARAM (>={ESPERA_MINIMA_S}s): {n}   "
          f"(descartadas por preencher na hora: {n_descartadas})")
    print(f"  preencheram: {n_fill}   censuradas: {n - n_fill}   "
          f"taxa de censura: {censura:.1%}")

    print(f"\n  {'v (vol no nivel)':>18} | {'em risco':>8} | {'fills':>5} | {'S(v)':>6}")
    print("  " + "-" * 46)
    for v, s in kaplan_meier(volumes, eventos)[1:]:
        em_risco = int((volumes >= v).sum())
        mortes = int(((volumes == v) & eventos).sum())
        print(f"  {v:18.0f} | {em_risco:8d} | {mortes:5d} | {s:6.3f}")

    curva = kaplan_meier(volumes, eventos)
    q1 = quantil_km(curva, 0.25)
    mediana = quantil_km(curva, 0.50)
    ingenua = float(np.median(volumes[eventos])) if n_fill else float("nan")
    print(f"\n  Q1 (25% ja' preencheram) : {q1}")
    print(f"  MEDIANA Kaplan-Meier     : {mediana}   <- o numero da tabela")
    print(f"  mediana INGENUA (so' fills): {ingenua:.0f}"
          f"   <- enviesada para BAIXO, nao use")
    print(f"  S(v) final: {curva[-1][1]:.3f}  "
          f"(fracao que nunca preencheu na janela observada)")
    return mediana


# --------------------------------------------------------------------------
# Leitura do terminal (somente leitura)
# --------------------------------------------------------------------------

def le_terminal(simbolo: str, de: dt.datetime, ate: dt.datetime):
    """Ordens, deals e ticks do periodo. Fecha o terminal ao sair -- nenhuma
    outra chamada MT5 e' feita neste script."""
    import MetaTrader5 as mt5  # importado aqui: o resto do script e' testavel sem terminal

    if not mt5.initialize():
        raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()} -- "
                         f"o terminal precisa estar ABERTO e logado.")
    try:
        ordens = [o for o in (mt5.history_orders_get(de, ate) or ()) if o.symbol == simbolo]
        deals = [d for d in (mt5.history_deals_get(de, ate) or ()) if d.symbol == simbolo]
        ticks = mt5.copy_ticks_range(simbolo, de, ate, mt5.COPY_TICKS_ALL)
        consts = {
            "LIMITES": (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT),
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
            "FILLED": mt5.ORDER_STATE_FILLED,
            "DEAL_BUY": mt5.DEAL_TYPE_BUY,
            "F_LAST": mt5.TICK_FLAG_LAST,
            "F_BUY": mt5.TICK_FLAG_BUY,
            "F_SELL": mt5.TICK_FLAG_SELL,
            "REASON_SL": mt5.DEAL_REASON_SL,
            "REASON_TP": mt5.DEAL_REASON_TP,
        }
    finally:
        mt5.shutdown()
    if ticks is None or len(ticks) == 0:
        raise SystemExit(f"copy_ticks_range devolveu 0 negocios para {simbolo} "
                         f"em {de:%Y-%m-%d}..{ate:%Y-%m-%d} -- simbolo errado, "
                         f"ou o terminal nao tem o historico de tick baixado.")
    return ordens, deals, ticks, consts


def hora_servidor(msc: int) -> dt.datetime:
    """`time_msc` do MT5 -> relogio de parede do SERVIDOR (Brasilia).

    O campo parece epoch UTC mas e' o relogio local do servidor codificado
    como se fosse UTC -- medido e documentado em `core.b3_session`. Usar
    `fromtimestamp` local aqui erraria 3h e jogaria toda saida por
    achatamento para fora da janela de fim de pregao."""
    return dt.datetime.fromtimestamp(msc / 1000, tz=dt.timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--simbolo", default=SIMBOLO_PADRAO,
                   help=f"contrato REAL com vencimento (default {SIMBOLO_PADRAO})")
    p.add_argument("--magic", type=int, default=MAGIC_WDO_F1)
    p.add_argument("--de", default=JANELA_DA_CALIBRACAO[0],
                   help="AAAA-MM-DD (inclusivo)")
    p.add_argument("--ate", default=None,
                   help="AAAA-MM-DD (EXCLUSIVO; default = a janela da "
                        "calibracao vigente, ou --de + 1 dia se voce passar --de)")
    args = p.parse_args()

    de = dt.datetime.strptime(args.de, "%Y-%m-%d")
    if args.ate:
        ate = dt.datetime.strptime(args.ate, "%Y-%m-%d")
    elif args.de == JANELA_DA_CALIBRACAO[0]:
        ate = dt.datetime.strptime(JANELA_DA_CALIBRACAO[1], "%Y-%m-%d")
    else:
        ate = de + dt.timedelta(days=1)

    econ = economics_for(CONTINUA)
    print(f"WDO F1 -- fidelidade de execucao medida do terminal (somente leitura)")
    print(f"simbolo={args.simbolo}  magic={args.magic}  "
          f"janela=[{de:%Y-%m-%d}, {ate:%Y-%m-%d})")
    print(f"economia declarada ({CONTINUA}): 1 ponto = R${econ.point_value_brl:.2f}, "
          f"tick = {econ.price_tick_size} pt = R${econ.tick_value_brl:.2f}")

    ordens, deals, ticks, K = le_terminal(args.simbolo, de, ate)

    # ---- fita de negocios -------------------------------------------------
    td = pd.DataFrame(ticks).sort_values("time_msc")
    neg = td[(td["flags"] & K["F_LAST"]) != 0]
    ts_a = neg["time_msc"].to_numpy()
    px_a = neg["last"].to_numpy()
    vol_a = (neg["volume_real"] if "volume_real" in neg else neg["volume"]).to_numpy(dtype=float)
    eh_buy = (neg["flags"].to_numpy() & K["F_BUY"]) != 0
    eh_sell = (neg["flags"].to_numpy() & K["F_SELL"]) != 0

    # ---- intervalos de posicao ABERTA ------------------------------------
    # O MT5 so' carimba `position_id` em ordem que EXECUTOU; a limite de saida
    # cancelada sai com 0, igual a uma de entrada. Reconstruir os intervalos
    # a partir dos DEALS e o unico jeito de classificar as canceladas -- e sao
    # elas as de fila grande.
    por_pos: dict[int, list] = {}
    for d in deals:
        # Agrupa TODO deal do simbolo, inclusive os de magic 0 (fechamento
        # manual do dono na mesma posicao): o filtro por magic vai no DEAL DE
        # ENTRADA logo abaixo, que e' quem diz de quem e' a posicao. Filtrar
        # aqui perderia a perna de saida manual e a posicao ficaria "aberta"
        # para sempre, engolindo toda limite postada depois dela.
        por_pos.setdefault(d.position_id, []).append(d)
    posicoes = []
    for pid, ds in por_pos.items():
        ent = [x for x in ds if x.entry == 0]
        sai = [x for x in ds if x.entry == 1]
        if not ent or not sai:
            continue
        if ent[0].magic != args.magic:
            continue
        posicoes.append({
            "pid": pid,
            "t_abre": ent[0].time_msc, "t_fecha": sai[-1].time_msc,
            "lado": "long" if ent[0].type == K["DEAL_BUY"] else "short",
            "preco_entrada": float(ent[0].price), "preco_saida": float(sai[-1].price),
            "volume": float(ent[0].volume),
            "reason_saida": int(sai[-1].reason), "order_saida": int(sai[-1].order),
            "lucro": float(sum(x.profit for x in sai)),
        })
    posicoes.sort(key=lambda r: r["t_abre"])

    def contexto_em(t: int):
        for pos in posicoes:
            if pos["t_abre"] <= t <= pos["t_fecha"]:
                return pos
        return None

    # ---- classifica cada ordem-limite ------------------------------------
    linhas_ent, linhas_sai, descarte_ent, descarte_sai = [], [], 0, 0
    for o in ordens:
        if o.type not in K["LIMITES"] or o.magic != args.magic:
            continue
        t0, t1 = o.time_setup_msc, o.time_done_msc
        if not t1 or t1 <= t0:
            continue
        janela = (ts_a >= t0) & (ts_a < t1) & np.isclose(px_a, o.price_open)
        # A nossa e' limite de VENDA -> so' agressor COMPRADOR executa contra
        # nos (e vice-versa) -- ver a secao do refinamento refutado.
        contra = eh_buy if o.type == K["SELL_LIMIT"] else eh_sell
        registro = {
            "dia": hora_servidor(t0).date(),
            "hora": hora_servidor(t0).time(),
            "preco": float(o.price_open),
            "espera_s": (t1 - t0) / 1000.0,
            "vol_nivel": float(vol_a[janela].sum()),
            "vol_contra": float(vol_a[janela & contra].sum()),
            "preencheu": o.state == K["FILLED"],
        }
        pos = contexto_em(t0)
        fecha_posicao = pos is not None and (
            (pos["lado"] == "long" and o.type == K["SELL_LIMIT"])
            or (pos["lado"] == "short" and o.type == K["BUY_LIMIT"]))
        alvo = linhas_sai if fecha_posicao else linhas_ent
        if registro["espera_s"] < ESPERA_MINIMA_S and registro["preencheu"]:
            if fecha_posicao:
                descarte_sai += 1
            else:
                descarte_ent += 1
            continue
        alvo.append(registro)

    df_ent = pd.DataFrame(linhas_ent)
    df_sai = pd.DataFrame(linhas_sai)
    if not df_ent.empty:
        df_ent = df_ent[df_ent["espera_s"] >= ESPERA_MINIMA_S]
    if not df_sai.empty:
        df_sai = df_sai[df_sai["espera_s"] >= ESPERA_MINIMA_S]

    med_ent = imprime_lado("LADO DA ENTRADA  (`queue_ahead_qty`)", df_ent, descarte_ent)
    med_sai = imprime_lado("LADO DA SAIDA    (`exit_queue_ahead_qty`)", df_sai, descarte_sai)

    # ---- regime: taxa de censura POR PREGAO ------------------------------
    print(f"\n{'=' * 74}")
    print("REGIME DE SAIDA -- taxa de censura por pregao")
    print("=" * 74)
    print("  COM prazo (ate 2026-09-09): a limite nao preenchida e' CANCELADA,")
    print("  e a censura e' alta (17/25 = 68% em 2026-09-09). SEM prazo")
    print("  (`EXIT_TTL_BARS_SEM_PRAZO`, producao desde 2026-09-09): a ordem")
    print("  fica ate' preencher/stop/achatamento, a maioria vira EVENTO e o")
    print("  que sobra censurado e' censurado no FIM do pregao, com volume")
    print("  acumulado alto. Kaplan-Meier serve nos dois -- o que nao serve e'")
    print("  juntar os dois numa curva so' sem saber.\n")
    taxas: dict[dt.date, float] = {}
    if not df_sai.empty:
        print(f"  {'pregao':<12} {'n':>4} {'fills':>6} {'censura':>9}")
        for dia, sub in df_sai.groupby("dia"):
            taxa = 1.0 - sub["preencheu"].mean()
            taxas[dia] = float(taxa)
            print(f"  {str(dia):<12} {len(sub):4d} {int(sub['preencheu'].sum()):6d} "
                  f"{taxa:8.1%}")
        if len(taxas) > 1 and (max(taxas.values()) - min(taxas.values())) > SALTO_DE_CENSURA_SUSPEITO:
            print(f"\n  AVISO: a taxa de censura varia "
                  f"{max(taxas.values()) - min(taxas.values()):.0%} entre os pregoes "
                  f"desta janela.\n  Isso e' a assinatura de REGIMES DIFERENTES "
                  f"(com prazo x sem prazo) misturados na\n  mesma curva. A mediana "
                  f"acima nao descreve nenhum dos dois -- rode um pregao\n  por vez, "
                  f"ou justifique por escrito por que juntar.")
    else:
        print("  (sem ordens de saida na janela)")

    # ---- refinamento REFUTADO: so' o agressor contrario consome a fila? ---
    print(f"\n{'=' * 74}")
    print("REFINAMENTO REFUTADO -- o agressor contrario e' quase todo o volume")
    print("=" * 74)
    total = vol_a.sum()
    print(f"  no DIA inteiro: volume={total:,.0f}   "
          f"agressor compra {vol_a[eh_buy].sum() / total:.1%}   "
          f"agressor venda {vol_a[eh_sell].sum() / total:.1%}")
    for rot, sub in (("ENTRADA", df_ent), ("SAIDA", df_sai)):
        if sub.empty or sub["vol_nivel"].sum() == 0:
            print(f"  no NIVEL das nossas ordens ({rot}): n=0")
            continue
        frac = sub["vol_contra"].sum() / sub["vol_nivel"].sum()
        print(f"  no NIVEL das nossas ordens ({rot}): {frac:.1%} do volume e' do "
              f"lado que executa CONTRA nos")
    print("  Em 2026-09-09 deu 99,3%: a nossa limite esta' na melhor oferta, entao")
    print("  negocio naquele preco e' por definicao alguem agredindo a NOSSA ponta.")
    print("  O motor ja' esta' certo ao descontar o volume INTEIRO da barra --")
    print("  nao ha' correcao a fazer. (Se um dia isto imprimir 60%, a conclusao")
    print("  muda e a refutacao cai.)")

    # ---- as tres metricas do regime SEM PRAZO -----------------------------
    print(f"\n{'=' * 74}")
    print("REGIME SEM PRAZO -- o custo que substituiu a derrapagem do estouro")
    print("=" * 74)
    print("  SEM LINHA DE BASE AINDA: 2026-09-09 rodou COM prazo. O que sai")
    print("  abaixo e' o 'antes' -- serve para comparar, nao para julgar.\n")
    if not posicoes:
        print("  (nenhuma posicao fechada do robo na janela)")
        return

    ordens_por_ticket = {o.ticket: o for o in ordens}
    corte_por_dia: dict[dt.date, dt.time] = {}
    fim_utc = profile_for(CONTINUA).session_end_time

    achatamentos, duracoes, sem_alvo = [], [], 0
    for pos in posicoes:
        abre, fecha = hora_servidor(pos["t_abre"]), hora_servidor(pos["t_fecha"])
        duracoes.append((fecha - abre).total_seconds())
        dia = fecha.date()
        if dia not in corte_por_dia:
            # `session_end_time` do perfil e' UTC; o relogio do MT5 e' de
            # Brasilia. Converter pelo FUSO (nunca por um escalar de 3h) e'
            # a mesma regra de `core.b3_session`.
            corte_por_dia[dia] = utc_to_server_wall_clock(
                dt.datetime.combine(dia, fim_utc, tzinfo=dt.timezone.utc)).time()
        corte = corte_por_dia[dia]
        ordem = ordens_por_ticket.get(pos["order_saida"])
        saiu_por_limite = ordem is not None and ordem.type in K["LIMITES"]
        saiu_por_sl = pos["reason_saida"] == K["REASON_SL"]
        saiu_por_tp = pos["reason_saida"] == K["REASON_TP"]
        # Achatamento = saida A MERCADO, sem stop e sem alvo nativo, no fim do
        # pregao. E' o unico caminho que sobra quando a limite de alvo nunca
        # foi paga e o dia acabou.
        eh_achatamento = (not saiu_por_limite and not saiu_por_sl
                          and not saiu_por_tp and fecha.time() >= corte)
        if eh_achatamento:
            sinal = 1.0 if pos["lado"] == "long" else -1.0
            pontos = sinal * (pos["preco_saida"] - pos["preco_entrada"])
            achatamentos.append({
                "hora": fecha.time(),
                "ticks": pontos / econ.price_tick_size,
                "brl": pontos * econ.point_value_brl * pos["volume"],
            })
            sem_alvo += 1

    # 1. achatamento
    print(f"  [1] SAIDAS POR ACHATAMENTO DE FIM DE PREGAO: {len(achatamentos)} "
          f"de {len(posicoes)} posicoes")
    if achatamentos:
        da = pd.DataFrame(achatamentos)
        print(f"      resultado total : R$ {da['brl'].sum():,.2f}   "
              f"por saida: R$ {da['brl'].mean():,.2f}")
        print(f"      contra a entrada: mediana {da['ticks'].median():+.1f} ticks   "
              f"pior {da['ticks'].min():+.1f}   melhor {da['ticks'].max():+.1f}")
        print(f"      horarios: {', '.join(str(h) for h in da['hora'])}")
    else:
        print("      nenhuma -- todo o pregao fechou por alvo ou stop.")

    # 2. tempo de posicao aberta
    s = pd.Series(duracoes)
    print(f"\n  [2] TEMPO DE POSICAO ABERTA (n={len(s)} posicoes fechadas)")
    print(f"      mediana {s.median():8.1f}s   p75 {s.quantile(.75):8.1f}s   "
          f"p90 {s.quantile(.90):8.1f}s   max {s.max():8.1f}s")
    print(f"      O motor NAO piramida: enquanto a limite espera, o robo nao abre")
    print(f"      outra posicao. Sem prazo, isto e' o CAIXA PARADO que substituiu a")
    print(f"      derrapagem do estouro -- e' o numero a vigiar quando o regime virar.")

    # 3. posicoes que o pregao nao pagou
    frac = sem_alvo / len(posicoes)
    print(f"\n  [3] POSICOES QUE O PREGAO INTEIRO NAO PAGOU: {sem_alvo} de "
          f"{len(posicoes)} ({frac:.1%})")
    print(f"      Chegaram ao achatamento sem o alvo nunca ter preenchido.")

    # ---- o que fazer com o resultado -------------------------------------
    print(f"\n{'=' * 74}")
    print("PARA ATUALIZAR A CALIBRACAO")
    print("=" * 74)
    print(f"  Edite `src/backtest/intraday/fidelidade.py`, entrada {CONTINUA!r}:")
    print(f"      queue_ahead_qty      = {med_ent}")
    print(f"      exit_queue_ahead_qty = {med_sai}")
    print(f"      medido_em            = '{de:%Y-%m-%d}'"
          + ("" if ate - de <= dt.timedelta(days=1) else f" .. '{ate:%Y-%m-%d}'"))
    print(f"      n_entrada={len(df_ent)}  n_entrada_fills="
          f"{int(df_ent['preencheu'].sum()) if not df_ent.empty else 0}")
    print(f"      n_saida={len(df_sai)}  n_saida_fills="
          f"{int(df_sai['preencheu'].sum()) if not df_sai.empty else 0}")
    print("  `profiles.config_for` le' DALI sozinho -- backtest, sombra e producao")
    print("  herdam juntos, sem nenhum script precisar passar o numero a mao.")


if __name__ == "__main__":
    main()
