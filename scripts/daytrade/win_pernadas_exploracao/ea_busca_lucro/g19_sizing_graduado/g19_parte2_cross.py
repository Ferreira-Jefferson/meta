# -*- coding: utf-8 -*-
"""Geracao 19, PARTE 2 -- `WinBuscaLucroG19CrossWdoSizingGraduado`: contratos
DE VERDADE (1-N, capital R$1.000) graduados pela MAGNITUDE da anomalia
cruzada WIN x WDO (nao pela forca do rompimento ORB, que a Parte 1/G11 ja
mostrou ser incidental).

Protocolo (mesmo metodo CORRETO da Parte 1/G11, item 6.50 -- nunca
simulacao exclusiva por balde, nunca REJEITA um sinal por magnitude):

  1. PARIDADE: `magnitude_anomalo_cruzado` tem que bater byte a byte com
     `estado_anomalo_cruzado` (G4) nos MESMOS argumentos -- se nao bater,
     aborta antes de qualquer backtest.
  2. REF: roda 1x, contratos_por_balde=(1,1,1) (== G17 vencedor, flat 1
     contrato), coleta a magnitude de TODA anomalia bruta e da que virou
     CADA trade real.
  3. Cortes de tercil CAUSAIS (so' do IS) sobre a magnitude das entradas
     reais.
  4. Estratificacao POS-HOC dos mesmos trades da REF pelos 3 baldes --
     testa se magnitude da anomalia correlaciona com win%/resultado (ao
     contrario da forca do ORB, e' uma medida de CONVICCAO do proprio
     sinal, candidata mais promissora).
  5. Se houver correlacao REAL: GRADUADO via Kelly por balde (motor.tamanho)
     x FLAT pareado (mesma media de contratos) -- compara liquido, IC/win%,
     p_ruina, CONCENTRACAO (a pergunta extra desta Parte: os episodios de
     maior magnitude sao mais espalhados no tempo?).
  6. Se a correlacao for ~0: reporta honestamente, NAO forca estrategia de
     sizing.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g19_sizing_graduado/g19_parte2_cross.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g19_cross_base as b  # noqa: E402


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
    print(f"\n--- {rotulo} ---")
    print(f"  trades={c['n']}  liquido={b.br(c['liquido'])}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  veredito={c['veredito']}  "
          f"com_trade={c['com_trade']}/{c['pregoes']}")
    print(f"  IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"p_ruina(MC)={b.br(100*ruina['p_ruina'],1) if ruina['p_ruina']==ruina['p_ruina'] else '--'}%  "
          f"pior_seq={const.get('pior_seq_ops',0)} ({b.br(const.get('pior_seq_brl',0.0))})  "
          f"maxdd={b.br(const.get('maxdd_brl',0.0))}")
    print(f"  top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*top5,0) if top5==top5 else '--'}%  "
          f"censura_capital={cens['censura_capital']}  equity_min={b.br(cens['equity_min'])}  "
          f"desvio_pnl/trade={b.br(_desvio_pnl(trades),2)}")
    return dict(rotulo=rotulo, trades=trades, c=c, top5=top5, ruina=ruina, const=const,
                cens=cens, desvio=_desvio_pnl(trades))


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print(f"Geracao 19, PARTE 2 -- cruzado WIN x WDO sizing graduado por MAGNITUDE da anomalia, "
          f"capital R$ {b.br(b.CAPITAL,0)}, geometria G17 (alvo=4x/stop=150), {len(dias)} pregoes IS")
    print("=" * 150)

    # -- PASSO 1: paridade da funcao nova contra a G4 (confirma ANTES de rodar nada) --
    print("\n--- PASSO 1: paridade `magnitude_anomalo_cruzado` x `estado_anomalo_cruzado` (G4) ---")
    b.computa_estado_com_magnitude(dias, verifica_paridade=True)
    print("  PARIDADE OK -- anomalo/direcao batem byte a byte com a funcao original da G4.")

    # -- PASSO 2: REF (flat 1 contrato, == G17 vencedor) ----------------------
    res_ref, strat_ref = b.roda(dias, contratos_por_balde=(1, 1, 1), **b.GEOMETRIA_G17)
    r_ref = _resumo("PASSO 2: REF (flat, 1 contrato fixo == G17 vencedor)", res_ref, strat_ref, dias)

    trades_ref = list(res_ref.trades)
    mags_entrada = list(strat_ref.stats_magnitude_das_entradas)
    if len(trades_ref) != len(mags_entrada):
        print(f"\nAVISO: contagem trades ({len(trades_ref)}) != magnitudes registradas "
              f"({len(mags_entrada)}) -- instrumentacao dessincronizada. ABORTANDO.")
        return
    if any(m != m for m in mags_entrada):  # NaN check
        print("\nAVISO: alguma entrada real tem magnitude NaN -- bug na instrumentacao (toda entrada "
              "real exige anomalo=True, que por construcao da' magnitude definida). ABORTANDO.")
        return

    m_baixo, m_alto = b.quantis_magnitude(mags_entrada)
    print(f"\ncortes de tercil (causais, so' IS, sobre as {len(mags_entrada)} entradas REAIS): "
          f"m33={b.br(m_baixo,3)}  m67={b.br(m_alto,3)}  "
          f"(1,0 = exatamente no quantil 0,75; >1,0 = excedeu)")

    corr = b.correlacoes_pos_hoc(trades_ref, mags_entrada)
    print(f"corr(magnitude, venceu?) = {b.br(corr['corr_mag_ganho'],3)}")
    print(f"corr(magnitude, pnl R$)  = {b.br(corr['corr_mag_pnl'],3)}")

    baldes = b.baldes_pos_hoc(trades_ref, mags_entrada, m_baixo, m_alto)
    print("\n--- PASSO 4: estratificacao POS-HOC (mesmos trades da REF, item 6.50) ---")
    for nome in ("no_quantil", "moderado", "muito_acima"):
        r = baldes[nome]
        print(f"  {nome:<12} n={r['n']:>4}  dias_distintos={r['dias_distintos']:>3}  "
              f"win={b.br(100*r['win'],1) if r['n'] else '--':>6}%  "
              f"BEemp={b.br(100*r['be'],1) if r['be']==r['be'] else '--':>6}%  "
              f"IC95=[{b.br(100*r['lo'],1) if r['n'] else '--'};{b.br(100*r['hi'],1) if r['n'] else '--'}]  "
              f"liquido={b.br(r['liquido']):>10}")
    z = _z_duas_proporcoes(baldes["muito_acima"]["k"], baldes["muito_acima"]["n"],
                            baldes["no_quantil"]["k"], baldes["no_quantil"]["n"])
    print(f"  z(muito_acima vs no_quantil) = {b.br(z,2) if z==z else '--'}  "
          f"(|z|>=1,96 => distinguivel de ruido)  distinguivel? {z==z and abs(z)>=1.96}")

    corr_real = corr["corr_mag_pnl"] == corr["corr_mag_pnl"] and abs(corr["corr_mag_pnl"]) >= 0.15
    z_real = z == z and abs(z) >= 1.96
    print(f"\nCRITERIO desta geracao para 'correlacao real': |corr(magnitude,pnl)|>=0,15 OU "
          f"|z(muito_acima vs no_quantil)|>=1,96. Resultado: corr_real={corr_real}  z_real={z_real}")

    if not (corr_real or z_real):
        print("\n" + "=" * 150)
        print("VEREDITO PARTE 2: magnitude da anomalia NAO correlaciona com o resultado do trade "
              "(mesmo padrao qualitativo da forca do ORB na Parte 1) -- NAO sera' forcada nenhuma "
              "estrategia de sizing sobre um sinal sem diferenciacao real. Resultado honesto.")
        print("=" * 150)
        print("\nFIM PARTE 2 (encerrada no diagnostico). Ver g19_parte2_cross_stdout.log.")
        return

    # -- PASSO 5: so' roda se houver correlacao real --------------------------
    print("\n--- PASSO 5: correlacao REAL detectada -- construindo sizing Kelly por balde ---")
    ganhos_pts = [abs(t.exit_price - t.entry_price) for t in trades_ref if t.pnl_brl > 0]
    perdas_pts = [abs(t.exit_price - t.entry_price) for t in trades_ref if t.pnl_brl <= 0]
    gm = float(np.mean(ganhos_pts)) if ganhos_pts else 0.0
    lm = float(np.mean(perdas_pts)) if perdas_pts else 0.0

    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "rodada4" / "decisao"))
    import motor  # noqa: E402

    contratos_balde = []
    for nome in ("no_quantil", "moderado", "muito_acima"):
        rb = baldes[nome]
        p0 = rb["win"] if rb["win"] == rb["win"] else 0.0
        pe = motor.p_encolhido(rb["k"], rb["n"], p0) if rb["n"] else 0.0
        nc = motor.tamanho(pe, gm, lm, b.CAPITAL) if gm and lm else 0
        nc = max(1, nc)
        contratos_balde.append(nc)
        print(f"  balde={nome:<12} p_encolhido={b.br(100*pe,1)}%  contratos_kelly={nc}")
    contratos_por_balde = tuple(contratos_balde)
    n_flat = max(1, round(sum(contratos_balde) / 3))
    print(f"\ncontratos_por_balde (GRADUADO) = {contratos_por_balde}")
    print(f"n_flat pareado (media arredondada) = {n_flat}")

    res_grad, strat_grad = b.roda(dias, magnitude_cortes=(m_baixo, m_alto),
                                   contratos_por_balde=contratos_por_balde, **b.GEOMETRIA_G17)
    r_grad = _resumo(f"GRADUADO {contratos_por_balde}", res_grad, strat_grad, dias)
    res_flat, strat_flat = b.roda(dias, contratos_por_balde=(n_flat, n_flat, n_flat), **b.GEOMETRIA_G17)
    r_flat = _resumo(f"FLAT pareado ({n_flat},{n_flat},{n_flat})", res_flat, strat_flat, dias)

    print("\n" + "=" * 150)
    print("COMPARACAO FINAL -- FLAT pareado x GRADUADO (mesma exposicao MEDIA)")
    print("=" * 150)
    for r in (r_flat, r_grad):
        c = r["c"]
        print(f"  {r['rotulo']:<45} liquido={b.br(c['liquido']):>12}  win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
              f"p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
              f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
              f"top5/liq={b.br(100*r['top5'],0) if r['top5']==r['top5'] else '--':>5}%")

    print("\nFIM PARTE 2. Ver g19_parte2_cross_stdout.log para o relatorio completo.")


if __name__ == "__main__":
    main()
