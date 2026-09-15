"""copa_win: ONDE moram os trades PERDEDORES?

Pergunta do dono (2026-09-14). Quebra a populacao de trades da config de
PRODUCAO (corte de achatamento de 2026-09-14, folga 5min) por hora de
ENTRADA, motivo de saida, lado e dia da semana -- e repete a quebra em IS e
OOS SEPARADOS, que e' a unica parte que decide se o padrao e' acionavel.

Por que o IS/OOS separado importa mais que o ranking: o projeto ja achou
concentracao de perda por dia/hora DUAS vezes e refutou agir sobre ela nas
duas (`wdo_win_filtro_dia_horario_refutado_2026_09_04` -- cortar o pior
dia/hora PIOROU o OOS; `wdo_orb_perfil_operacao_sem_preditor_2026_09_14` --
0 de 15 variaveis separavam vencedor de perdedor no momento do SINAL). Um
balde ruim no IS que nao e' ruim no OOS e' ruido de amostra com cara de
padrao.

Reaproveita o carregador e o construtor de config de
`copawin_encerrar_mais_cedo_2026_09_14.py` -- nada e' redigitado aqui.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL
FOLGA_PRODUCAO = 5


def br(x, casas=2):
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _quebra(nome, trades, chave):
    """n / perdedores / win% / soma R$ / R$ por trade, por balde."""
    baldes = defaultdict(list)
    for t in trades:
        baldes[chave(t)].append(t)
    total_liq = sum(t.pnl_brl for t in trades)
    perdas_tot = sum(t.pnl_brl for t in trades if t.pnl_brl < 0)
    print(f"\n--- {nome} (n={len(trades)}, liquido R$ {br(total_liq)}, "
          f"soma das PERDAS R$ {br(perdas_tot)}) ---")
    hdr = (f"{'balde':<14}{'n':>6}{'perd':>6}{'win%':>8}{'soma R$':>13}"
           f"{'R$/trade':>11}{'perdas R$':>13}{'% das perdas':>14}")
    print(hdr); print("-" * len(hdr))
    for k in sorted(baldes):
        ts = baldes[k]
        perd = [t for t in ts if t.pnl_brl < 0]
        soma = sum(t.pnl_brl for t in ts)
        sperd = sum(t.pnl_brl for t in perd)
        print(f"{str(k):<14}{len(ts):>6}{len(perd):>6}"
              f"{br(100*(len(ts)-len(perd))/len(ts),1):>7}%"
              f"{br(soma):>13}{br(soma/len(ts)):>11}{br(sperd):>13}"
              f"{br(100*sperd/perdas_tot,1):>13}%")


def _ordinal_no_pregao(trades):
    """`id(trade) -> 1, 2, 3...` pela ordem de ENTRADA dentro do proprio pregao.

    Pergunta do dono: o stop tende a cair na 1a, 2a, 3a operacao do dia? A
    ordem e' por `entry_ts` e reinicia a cada pregao -- nao e' o numero de
    rodada do robo (`trade_seq`), que atravessa a sessao."""
    from collections import defaultdict
    por_dia = defaultdict(list)
    for t in trades:
        por_dia[t.entry_ts.date()].append(t)
    ordem = {}
    for dia, ts in por_dia.items():
        for i, t in enumerate(sorted(ts, key=lambda x: x.entry_ts), start=1):
            ordem[id(t)] = i
    return ordem


def _motivo_por_ordinal(trades, ordem, teto=6):
    """Composicao de MOTIVO DE SAIDA dentro de cada ordinal -- a pergunta
    condicional 'dado que e' a N-esima operacao do dia, qual a chance de
    ela morrer no stop?'"""
    from collections import defaultdict
    baldes = defaultdict(list)
    for t in trades:
        k = ordem[id(t)]
        baldes[min(k, teto)].append(t)
    motivos = sorted({t.exit_reason.value for t in trades})
    hdr = f"{'ordem':<9}{'n':>6}" + "".join(f"{m[:11]:>13}" for m in motivos) + f"{'R$/trade':>11}"
    print("\n--- MOTIVO DE SAIDA por ORDEM DA OPERACAO NO PREGAO (% da linha) ---")
    print(hdr); print("-" * len(hdr))
    for k in sorted(baldes):
        ts = baldes[k]
        rot = f"{k}a" if k < teto else f"{teto}a+"
        linha = f"{rot:<9}{len(ts):>6}"
        for m in motivos:
            q = sum(1 for t in ts if t.exit_reason.value == m)
            linha += f"{br(100*q/len(ts),1)+'%':>13}"
        linha += f"{br(sum(t.pnl_brl for t in ts)/len(ts)):>11}"
        print(linha)
    # e a leitura inversa: dos STOPS, quantos caem em cada ordinal
    stops = [t for t in trades if t.exit_reason.value == "stop"]
    print(f"\n  dos {len(stops)} STOPS, onde caem:")
    dist = defaultdict(int)
    for t in stops:
        dist[min(ordem[id(t)], teto)] += 1
    for k in sorted(dist):
        rot = f"{k}a" if k < teto else f"{teto}a+"
        print(f"    {rot:<5} {dist[k]:>4} stops ({br(100*dist[k]/len(stops),1)}%)")


def _hora_brt(t):
    return f"{(t.entry_ts.tz_convert('America/Sao_Paulo')).hour:02d}h"


def _dia_semana(t):
    return ["seg", "ter", "qua", "qui", "sex", "sab", "dom"][t.entry_ts.dayofweek]


def main():
    df, dias = _base._df()
    import pandas as pd
    corte_oos = pd.Timestamp("2026-06-13").date()   # mesmo corte do script base
    janelas = [
        ("IS (<2026-06-13)", [d for d in dias if d < corte_oos]),
        ("OOS (>=2026-06-13)", [d for d in dias if d >= corte_oos]),
        ("HISTORICO COMPLETO", dias),
    ]
    print("=" * 100)
    print("copa_win -- ONDE moram os trades PERDEDORES (config de producao, folga 5min)")
    print("=" * 100)
    print(f"{len(dias)} pregoes: {dias[0]} a {dias[-1]}")

    for nome, dias_janela in janelas:
        res, _ = _base._roda_janela(CAPITAL, FOLGA_PRODUCAO, dias_janela)
        trades = list(res.trades)
        print("\n" + "=" * 100)
        print(f"JANELA: {nome}  ({len(dias_janela)} pregoes)")
        print("=" * 100)
        _quebra("por HORA DE ENTRADA (BRT)", trades, _hora_brt)
        _quebra("por MOTIVO DE SAIDA", trades, lambda t: t.exit_reason.value)
        _quebra("por LADO", trades, lambda t: t.side)
        _quebra("por DIA DA SEMANA", trades, _dia_semana)
        ordem = _ordinal_no_pregao(trades)
        _quebra("por ORDEM DA OPERACAO NO PREGAO", trades,
                lambda t, o=ordem: f"{min(o[id(t)],6)}a" + ("+" if o[id(t)] >= 6 else ""))
        _motivo_por_ordinal(trades, ordem)

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
