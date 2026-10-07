"""Simulacao de cenarios sinteticos do ciclo de vida da tese -- percorre o
fluxo inteiro (deteccao -> evidencia -> verificacao -> aprovacao/rejeicao ->
abertura -> fechamento) e confere que os numeros saem certos em cada passo.
Roda contra um banco TEMPORARIO (apagado no fim, nunca `db/
social_arbitrage.sqlite`) -- e' um passeio legivel para revisar o encanamento
antes de operar com tese real, nao um substituto dos testes em
`tests/test_social_arbitrage*.py` (que ja cobrem os mesmos caminhos como
asserts silenciosos).

Cada cenario imprime a PROPRIA linha assim que termina (nunca espera os
outros -- mesma regra de `AGENTS.md` para varredura), com PASSOU/FALHOU. Uma
falha lanca a excecao original (nao mascara com um "resumo" no fim) para o
traceback apontar exatamente a linha errada.

Uso:
    python scripts/social_arbitrage_dry_run.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_arbitrage.calibragem import calibrar  # noqa: E402
from social_arbitrage.sizing import max_unidades_pelo_pior_caso, tamanho_meio_kelly  # noqa: E402
from social_arbitrage.store import SocialArbitrageStore  # noqa: E402
from social_arbitrage.thesis import Evidencia, Fase, Lente  # noqa: E402


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def cenario_consumo_aprovada_com_lucro(store: SocialArbitrageStore) -> None:
    tamanho = tamanho_meio_kelly(0.65, 1.2)
    tese = store.criar_tese(
        marca="Havaianas", ticker="ALPA4", lente=Lente.CONSUMO,
        fonte_deteccao="video viral TikTok", descricao="esgotado em 3 lojas do bairro X",
        criterio_saida="quando a imprensa financeira citar o produto",
        tamanho_alvo_pct=tamanho, quando=_agora(),
        prob_acerto_estimada=0.65, payoff_estimado=1.2,
    )
    store.adicionar_evidencia(tese.id, Evidencia(texto="gerente confirmou ruptura de estoque ha 2 semanas", fonte="ligacao loja X", registrado_em=_agora()))
    store.transicionar(tese.id, Fase.EM_VERIFICACAO, quando=_agora())
    store.transicionar(tese.id, Fase.APROVADA, quando=_agora())
    store.registrar_abertura(tese.id, preco_entrada=4.20, quantidade=1000, quando=_agora())
    fechada = store.registrar_fechamento(tese.id, preco_saida=6.30, quando=_agora())
    assert fechada.fase == Fase.FECHADA
    assert abs(fechada.resultado_brl - 2100.0) < 0.01, fechada.resultado_brl
    assert fechada.prob_acerto_estimada == 0.65


def cenario_posicionamento_rejeitada_na_verificacao(store: SocialArbitrageStore) -> None:
    tese = store.criar_tese(
        marca="WDO@ concentracao institucional", ticker="WDO@", lente=Lente.POSICIONAMENTO,
        fonte_deteccao="leitura de posicionamento por tipo de investidor (B3)",
        descricao="institucional no percentil 8% da janela de 3 anos",
        criterio_saida="quando o percentil voltar a media",
        tamanho_alvo_pct=0.15, quando=_agora(),
    )
    store.adicionar_evidencia(tese.id, Evidencia(texto="TDW nao favoravel esta semana", fonte="calendario", registrado_em=_agora()))
    store.transicionar(tese.id, Fase.EM_VERIFICACAO, quando=_agora())
    rejeitada = store.transicionar(tese.id, Fase.REJEITADA, quando=_agora(), motivo_rejeicao="so' 1 das 4 condicoes de confluencia bateu")
    assert rejeitada.fase == Fase.REJEITADA
    assert rejeitada.motivo_rejeicao is not None
    try:
        store.transicionar(tese.id, Fase.EM_VERIFICACAO, quando=_agora())
    except ValueError:
        pass
    else:
        raise AssertionError("REJEITADA deveria ser terminal -- transicao para EM_VERIFICACAO nao podia ter sido aceita.")


def cenario_kelly_sem_edge_nao_cadastra(store: SocialArbitrageStore) -> None:
    tamanho = tamanho_meio_kelly(0.30, 1.0)  # 30% de acerto, payoff 1:1 -- edge negativa
    assert tamanho == 0.0, "Kelly deveria indicar fracao 0 (sem edge) para prob_acerto=0.30, payoff=1.0."


def cenario_teto_pior_caso_limita_unidades(store: SocialArbitrageStore) -> None:
    # capital 30.000, pior perda ja vista por unidade 4.000, multiplicador 1.5
    # exigencia por unidade = 6.000 -> 30.000 // 6.000 = 5
    max_unidades = max_unidades_pelo_pior_caso(30_000.0, 4_000.0, multiplicador=1.5)
    assert max_unidades == 5


def cenario_calibragem_reflete_teses_fechadas(store: SocialArbitrageStore) -> None:
    tese_perdedora = store.criar_tese(
        marca="Teste calibragem", ticker="TSTE4", lente=Lente.CONSUMO,
        fonte_deteccao="cenario sintetico", descricao="d", criterio_saida="s",
        tamanho_alvo_pct=0.05, quando=_agora(),
    )
    store.transicionar(tese_perdedora.id, Fase.EM_VERIFICACAO, quando=_agora())
    store.transicionar(tese_perdedora.id, Fase.APROVADA, quando=_agora())
    store.registrar_abertura(tese_perdedora.id, preco_entrada=10.0, quantidade=100, quando=_agora())
    store.registrar_fechamento(tese_perdedora.id, preco_saida=9.0, quando=_agora())

    linhas = calibrar(store.listar())
    total = next(l for l in linhas if l.grupo == "TOTAL")
    # inclui tambem a tese lucrativa do primeiro cenario (mesmo banco) -- 2 fechadas no total
    assert total.n >= 1
    assert any(l.grupo == "consumo" for l in linhas)


CENARIOS = (
    cenario_consumo_aprovada_com_lucro,
    cenario_posicionamento_rejeitada_na_verificacao,
    cenario_kelly_sem_edge_nao_cadastra,
    cenario_teto_pior_caso_limita_unidades,
    cenario_calibragem_reflete_teses_fechadas,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="social_arbitrage_dry_run_") as tmp_dir:
        store = SocialArbitrageStore(db_path=Path(tmp_dir) / "dry_run.sqlite")
        falhas = 0
        for cenario in CENARIOS:
            try:
                cenario(store)
            except Exception:
                falhas += 1
                print(f"FALHOU: {cenario.__name__}", flush=True)
                raise
            print(f"PASSOU: {cenario.__name__}", flush=True)
        print(f"\n{len(CENARIOS)} cenarios, {len(CENARIOS) - falhas} passaram.")


if __name__ == "__main__":
    main()
