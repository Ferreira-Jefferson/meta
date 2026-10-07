# -*- coding: utf-8 -*-
"""Geracao 19, PARTE 1 -- `WinBuscaLucroG19OrbSizingGraduado`: contratos DE
VERDADE (1-N, capital R$1.000) graduados pela forca do rompimento ORB.

Protocolo (herda o metodo CORRETO que a G11 so' descobriu depois -- nunca
simulacao exclusiva por balde, item 6.50):

  1. REF: roda 1x, contratos_por_balde=(1,1,1) (== G18 original, sizing
     flat de 1), coleta a forca de TODA borda bruta e da ordem que virou
     CADA trade real.
  2. Cortes de tercil CAUSAIS (so' do IS) sobre a forca das entradas reais.
  3. Estratificacao POS-HOC dos mesmos trades da REF pelos 3 baldes --
     reconfirma se a correlacao forca x resultado e' real ou ~0 (a R$1.000,
     mesma geometria que a G11 ja mediu ~0 a R$250).
  4. GRADUADO: roda 1x com contratos_por_balde ESCOLHIDO por Kelly
     fracionario por balde (`motor.tamanho`, usando o p_est de CADA balde,
     mesmo que a correlacao seja ~0 -- e' exatamente o ponto do teste: Kelly
     com p constante entre baldes prediz que o tamanho OTIMO e' o MESMO em
     todos, e qualquer graduacao artificial so' redistribui risco, nao
     esperanca).
  5. FLAT pareado: roda 1x com contratos_por_balde=(n,n,n), n = MEDIA
     arredondada dos contratos do passo 4 -- mesma exposicao MEDIA que o
     GRADUADO, para isolar o efeito de VARIAR o tamanho (vs so' aumentar a
     exposicao media).
  6. Compara liquido, win%, p_ruina (MC), pior sequencia, maxdd, desvio do
     P&L por trade entre FLAT e GRADUADO -- a predicao a verificar e'
     "esperanca ~igual, variancia/ruina podem mudar".

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g19_sizing_graduado/g19_parte1_orb.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g19_orb_base as b  # noqa: E402


def _z_duas_proporcoes(k1, n1, k2, n2) -> float:
    if n1 == 0 or n2 == 0:
        return float("nan")
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    denom = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if denom == 0:
        return float("nan")
    return (p1 - p2) / denom


def _desvio_pnl(trades) -> float:
    if not trades:
        return float("nan")
    return float(np.std([t.pnl_brl for t in trades]))


def _resumo(rotulo: str, res, strat, dias: list) -> dict:
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), horizonte_pregoes=44)
    const = b.constancia_motor(trades)
    cens = b.censura_separada(res, c)
    quantidades_pedidas = list(getattr(strat, "stats_quantidade_pedida", []))
    quantidades_reais = [t.quantity for t in sorted(trades, key=lambda t: t.entry_ts)]
    print(f"\n--- {rotulo} ---")
    print(f"  trades={c['n']}  liquido={b.br(c['liquido'])}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  veredito={c['veredito']}  "
          f"com_trade={c['com_trade']}/{c['pregoes']}")
    print(f"  p_ruina(MC)={b.br(100*ruina['p_ruina'],1) if ruina['p_ruina']==ruina['p_ruina'] else '--'}%  "
          f"pior_seq={const.get('pior_seq_ops',0)} ({b.br(const.get('pior_seq_brl',0.0))})  "
          f"maxdd={b.br(const.get('maxdd_brl',0.0))}  top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*top5,0) if top5==top5 else '--'}%")
    print(f"  censura_capital={cens['censura_capital']}  equity_min={b.br(cens['equity_min'])}  "
          f"ordens_recusadas_por_capital={cens['ordens_recusadas_por_capital']}")
    print(f"  desvio_pnl/trade={b.br(_desvio_pnl(trades),2)}  "
          f"contratos_pedidos(distribuicao)={sorted(set(quantidades_pedidas))}  "
          f"contratos_reais(distribuicao)={sorted(set(quantidades_reais))}")
    return dict(rotulo=rotulo, trades=trades, c=c, top5=top5, ruina=ruina, const=const,
                cens=cens, desvio=_desvio_pnl(trades), quantidades_reais=quantidades_reais)


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print(f"Geracao 19, PARTE 1 -- ORB sizing graduado por forca, capital R$ {b.br(b.CAPITAL,0)}, "
          f"geometria G18 (stop_max=140/alvo=3x), {len(dias)} pregoes IS (jan-jun/2026)")
    print("=" * 150)

    # -- PASSO 1: REF (flat 1 contrato, == G18 original) ----------------------
    res_ref, strat_ref = b.roda(dias, contratos_por_balde=(1, 1, 1), **b.GEOMETRIA_G18)
    r_ref = _resumo("PASSO 1: REF (flat, 1 contrato fixo == G18 original)", res_ref, strat_ref, dias)

    trades_ref = list(res_ref.trades)
    forcas_entrada = list(strat_ref.stats_forca_das_entradas)
    if len(trades_ref) != len(forcas_entrada):
        print("\nAVISO: contagem trades != forcas registradas -- instrumentacao dessincronizada. ABORTANDO.")
        return

    q_baixo, q_alto = b.quantis_forca(forcas_entrada)
    print(f"\ncortes de tercil (causais, so' IS, sobre as {len(forcas_entrada)} entradas REAIS): "
          f"p33={b.br(q_baixo,3)}  p67={b.br(q_alto,3)}")

    corr = b.correlacoes_pos_hoc(trades_ref, forcas_entrada)
    print(f"corr(forca, venceu?) = {b.br(corr['corr_forca_ganho'],3)}")
    print(f"corr(forca, pnl R$)  = {b.br(corr['corr_forca_pnl'],3)}")

    baldes = b.baldes_pos_hoc(trades_ref, forcas_entrada, q_baixo, q_alto)
    print("\n--- PASSO 3: estratificacao POS-HOC (mesmos trades da REF, item 6.50) ---")
    for nome in ("fraco", "medio", "forte"):
        r = baldes[nome]
        print(f"  {nome:<8} n={r['n']:>4}  win={b.br(100*r['win'],1) if r['n'] else '--':>6}%  "
              f"BEemp={b.br(100*r['be'],1) if r['be']==r['be'] else '--':>6}%  "
              f"IC95=[{b.br(100*r['lo'],1) if r['n'] else '--'};{b.br(100*r['hi'],1) if r['n'] else '--'}]  "
              f"liquido={b.br(r['liquido']):>10}")
    z = _z_duas_proporcoes(baldes["forte"]["k"], baldes["forte"]["n"],
                            baldes["fraco"]["k"], baldes["fraco"]["n"])
    print(f"  z(forte vs fraco) = {b.br(z,2) if z==z else '--'}  "
          f"(|z|>=1,96 => distinguivel de ruido)  "
          f"distinguivel? {z==z and abs(z)>=1.96}")

    # -- PASSO 4/5: sizing Kelly por balde x FLAT pareado ---------------------
    print("\n--- PASSO 4/5: sizing Kelly por balde (motor.tamanho) vs FLAT pareado (mesma media) ---")
    ganhos_pts = [abs(t.exit_price - t.entry_price) for t in trades_ref if t.pnl_brl > 0]
    perdas_pts = [abs(t.exit_price - t.entry_price) for t in trades_ref if t.pnl_brl <= 0]
    gm = float(np.mean(ganhos_pts)) if ganhos_pts else 0.0
    lm = float(np.mean(perdas_pts)) if perdas_pts else 0.0

    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "rodada4" / "decisao"))
    import motor  # noqa: E402

    contratos_balde = []
    for nome in ("fraco", "medio", "forte"):
        rb = baldes[nome]
        p0 = rb["win"] if rb["win"] == rb["win"] else 0.0
        pe = motor.p_encolhido(rb["k"], rb["n"], p0) if rb["n"] else 0.0
        nc = motor.tamanho(pe, gm, lm, b.CAPITAL) if gm and lm else 0
        nc = max(1, nc)
        contratos_balde.append(nc)
        print(f"  balde={nome:<8} p_encolhido={b.br(100*pe,1)}%  contratos_kelly={nc}")
    contratos_por_balde = tuple(contratos_balde)
    n_flat = max(1, round(sum(contratos_balde) / 3))
    print(f"\ncontratos_por_balde (GRADUADO) = {contratos_por_balde}")
    print(f"n_flat pareado (media arredondada) = {n_flat}")

    res_grad, strat_grad = b.roda(dias, forca_cortes=(q_baixo, q_alto),
                                   contratos_por_balde=contratos_por_balde, **b.GEOMETRIA_G18)
    r_grad = _resumo(f"GRADUADO {contratos_por_balde}", res_grad, strat_grad, dias)

    res_flat, strat_flat = b.roda(dias, contratos_por_balde=(n_flat, n_flat, n_flat), **b.GEOMETRIA_G18)
    r_flat = _resumo(f"FLAT pareado ({n_flat},{n_flat},{n_flat})", res_flat, strat_flat, dias)

    # -- comparacao final ------------------------------------------------------
    print("\n" + "=" * 150)
    print("COMPARACAO FINAL -- FLAT pareado x GRADUADO (mesma exposicao MEDIA)")
    print("=" * 150)
    for r in (r_flat, r_grad):
        c = r["c"]
        print(f"  {r['rotulo']:<45} liquido={b.br(c['liquido']):>12}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
              f"p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
              f"desvio_pnl/trade={b.br(r['desvio'],2):>8}  "
              f"pior_seq_brl={b.br(r['const'].get('pior_seq_brl',0.0)):>10}  "
              f"maxdd={b.br(r['const'].get('maxdd_brl',0.0)):>10}")

    print("\nPREDICAO (Kelly, p constante entre baldes): esperanca por trade deveria ser ~igual entre "
          "FLAT e GRADUADO (mesma media de contratos); variancia/ruina podem diferir.")
    liquido_flat = r_flat["c"]["liquido"]
    liquido_grad = r_grad["c"]["liquido"]
    diff_pct = (100 * (liquido_grad - liquido_flat) / abs(liquido_flat)) if liquido_flat else float("nan")
    print(f"diferenca de liquido GRADUADO vs FLAT: {b.br(diff_pct,1)}% "
          f"(liquido_flat={b.br(liquido_flat)}, liquido_graduado={b.br(liquido_grad)})")

    # -- PASSO 6: por que o Kelly do passo 4/5 deu (1,1,1) nos tres baldes --
    # achado MECANICO, nao so' estatistico: a escada de risco progressivo
    # do SISTEMA (`strategy.daytrade.base.ESCADA_RISCO_CONTRATO`, ordem do
    # dono 2026-09-18, liga por padrao em qualquer futuro com margem
    # configurada -- `config_for(enforce_capital_cap=True)` default) exige
    # caixa >= R$1.200 antes de autorizar um 2o contrato NESTA posicao,
    # nao so' R$750 que a margem crua x buffer autorizaria. Tentar FORCAR
    # quantity=2 fixo neste harness (testado e descartado) confirma isso na
    # pratica: a maioria das entradas e' RECUSADA POR CAPITAL (o 2o
    # "filho" da ordem dividida nao cabe no teto do momento), nao
    # encolhida -- so' preenche os 2 contratos nas poucas entradas em que o
    # caixa acumulado ja tinha cruzado R$1.200. Portanto "contratos de
    # verdade" (>1) so' existe, neste capital de teste e nesta geometria,
    # numa fracao pequena da janela -- o calculo abaixo usa a EQUITY REAL
    # da REF (1 contrato) para medir essa fracao, sem rodar outra simulacao
    # com quantidade fixa 2+ (que teria P&L diferente do que a REF mede).
    print("\n" + "=" * 150)
    print("PASSO 6: a ESCADA DE RISCO PROGRESSIVO (sistema, dono 2026-09-18) -- por que o Kelly nunca "
          "pediu >1 contrato, e quanto da janela teria caixa para um 2o contrato mesmo que pedisse")
    print("=" * 150)
    trades_ord = sorted(trades_ref, key=lambda t: t.entry_ts)
    equity_antes_do_trade = []
    acumulado = 0.0
    for t in trades_ord:
        equity_antes_do_trade.append(b.CAPITAL + acumulado)
        acumulado += t.pnl_brl
    equity_arr = np.asarray(equity_antes_do_trade)
    LIMIAR_2_CONTRATOS = 1200.0  # ESCADA_RISCO_CONTRATO[1]=0,25 -> margem(100)*buffer(2)*reserva(1,25)/0,25
    frac_libera_2o = float((equity_arr >= LIMIAR_2_CONTRATOS).mean())
    print(f"  degrau da escada para o 2o contrato: caixa >= R$ {b.br(LIMIAR_2_CONTRATOS,0)} "
          f"(ESCADA_RISCO_CONTRATO[1]=25% de risco/caixa-alvo)")
    print(f"  fracao das {len(trades_ord)} entradas REAIS da REF com equity-antes-do-trade >= "
          f"R$ {b.br(LIMIAR_2_CONTRATOS,0)}: {b.br(100*frac_libera_2o,1)}%")
    print(f"  equity minima/maxima no caminho: {b.br(equity_arr.min())} / {b.br(equity_arr.max())}")
    print("  CONCLUSAO MECANICA: mesmo IGNORANDO o achado de correlacao~0, o sistema (nao esta "
          "geracao) ja impede escalar alem de 1 contrato na maior parte da janela a R$1.000 nesta "
          "geometria -- 'contratos de verdade 1-4' do mandato so' fica disponivel, de fato, depois "
          "que o caixa acumula lucro suficiente, nao desde o primeiro trade.")

    print("\nFIM PARTE 1. Ver g19_parte1_orb_stdout.log para o relatorio completo.")


if __name__ == "__main__":
    main()
