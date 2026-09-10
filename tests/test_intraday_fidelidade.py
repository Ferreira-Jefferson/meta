"""FIDELIDADE DE EXECUCAO (`backtest/intraday/fidelidade.py`) -- a fila na
frente da nossa ordem-limite, dos dois lados, e o caminho que a leva sozinha
para dentro de toda run.

O que estes testes protegem e' o modo de falha que motivou o modulo, e ele
nao e' um bug de calculo: `IntradayBacktestConfig.queue_ahead_qty` existia
desde 2026-08-26, estava CERTO, e ficou UM MES no default 0,0 porque nenhum
chamador o passava. Um parametro de custo que depende de alguem lembrar de
passa-lo e' um parametro desligado (item 3.8 de LICOES_DE_PRODUCAO.md).

Por isso o teste central aqui nao e' "o numero X sai X": e' que `config_for`
aplique a calibracao SOZINHO, e que passar `0.0` explicito continue
reproduzindo o motor antigo -- as duas pontas do precedente do deslize do
alvo nativo.
"""
from __future__ import annotations

import dataclasses

import pytest

from backtest.intraday.fidelidade import (
    FIDELIDADE,
    FidelidadeExecucao,
    fidelidade_for,
    fidelidade_ou_none,
)
from backtest.intraday.profiles import config_for, profile_for
from backtest.intraday.report import cabecalho, linha, linha_de_resultado

#: Economia do WDO@ como o terminal a reporta na serie continua -- os mesmos
#: numeros que os outros testes de `config_for` usam. Nao ha' I/O nenhum
#: nestes testes; toda ordem de execucao entre eles e' irrelevante.
_WDO_ECON = dict(trade_tick_value=0.01, trade_tick_size=0.001)


def _config_wdo(**kwargs):
    return config_for(profile_for("WDO@"), initial_capital=375.0,
                      **_WDO_ECON, **kwargs)


# ---------- a tabela valida os proprios campos -----------------------------

def test_fila_negativa_e_recusada_mas_zero_e_legitimo():
    """Zero significa "book vazio na nossa frente" (o motor de ate
    2026-09-08) e e' uma premissa que alguem pode querer declarar. Negativo
    nao significa nada -- seria uma fila que ANDA sozinha antes de a ordem
    existir."""
    ok = FidelidadeExecucao(symbol="X", queue_ahead_qty=0.0,
                            exit_queue_ahead_qty=0.0, medido_em="2026-09-09",
                            n_entrada=1, n_entrada_fills=1,
                            n_saida=1, n_saida_fills=1)
    assert ok.queue_ahead_qty == 0.0

    with pytest.raises(ValueError, match="queue_ahead_qty"):
        dataclasses.replace(ok, queue_ahead_qty=-1.0)
    with pytest.raises(ValueError, match="exit_queue_ahead_qty"):
        dataclasses.replace(ok, exit_queue_ahead_qty=-1.0)


def test_procedencia_e_obrigatoria():
    """Fila sem data e sem estimador vira folclore em duas semanas: quem ler
    um backtest daqui a tres meses precisa poder perguntar ao codigo de
    quando e' o numero e com quantas ordens ele foi estimado."""
    base = FIDELIDADE["WDO@"]
    with pytest.raises(ValueError, match="medido_em"):
        dataclasses.replace(base, medido_em="   ")
    with pytest.raises(ValueError, match="estimador"):
        dataclasses.replace(base, estimador="")


def test_amostra_que_nao_fecha_e_recusada():
    """`n_*_fills` e' SUBCONJUNTO de `n_*` (quem preencheu esta' entre quem
    esperou). Mais preenchimentos do que ordens invalidaria a mediana de
    Kaplan-Meier, que depende de quantos ficaram em risco a cada evento."""
    base = FIDELIDADE["WDO@"]
    with pytest.raises(ValueError, match="preenchimentos"):
        dataclasses.replace(base, n_entrada_fills=base.n_entrada + 1)
    with pytest.raises(ValueError, match="preenchimentos"):
        dataclasses.replace(base, n_saida_fills=base.n_saida + 1)
    with pytest.raises(ValueError, match="n_saida"):
        dataclasses.replace(base, n_saida=-1)


def test_censuradas_sao_exatamente_a_diferenca():
    """As censuradas (esperaram e NAO preencheram) sao a razao de o estimador
    ser Kaplan-Meier e nao uma mediana simples -- estimar fila so' com quem
    preencheu e' vies de sobrevivencia, e ele so' anda para um lado.

    O INVARIANTE aqui e' aritmetico (`censuradas == n - fills`), nao um numero
    da calibracao do dia: a taxa de censura muda de regime para regime, e e'
    exatamente essa mudanca que `test_a_calibracao_vigente_declara_a_propria_
    procedencia` documenta."""
    for fid in FIDELIDADE.values():
        assert fid.censuradas_entrada == fid.n_entrada - fid.n_entrada_fills
        assert fid.censuradas_saida == fid.n_saida - fid.n_saida_fills
        assert fid.censuradas_entrada >= 0 and fid.censuradas_saida >= 0


def test_a_calibracao_vigente_declara_a_propria_procedencia():
    """PINO DELIBERADO dos numeros em vigor. Nao e' redundancia com o teste
    central (que checa o CAMINHO, `config_for` -> tabela): e' o alarme de que
    a fonte da verdade mudou sem ninguem declarar, num numero que ja se
    mostrou capaz de inverter o SINAL de um resultado.

    Trocar estes valores e' uma linha, e e' para ser deliberado: a tabela
    passou de 438/489 (pregao de 2026-09-09, COM prazo na fatia de saida,
    68% de censura -- o numero saia de um estimador) para 329/494
    (2026-09-10, SEM prazo, do jeito que a producao opera, 18% de censura).
    A saida CONFIRMA (489 -> 494, 1% em regimes diferentes); a entrada cai de
    438 para 329 com a amostra encolhendo de n=67 para n=11, porque o pregao
    de 10/09 durou 41 minutos. Regimes de censura diferentes nao se somam
    numa estimativa so' -- por isso a substituicao, e nao a media."""
    wdo = FIDELIDADE["WDO@"]
    assert (wdo.queue_ahead_qty, wdo.exit_queue_ahead_qty) == (329.0, 494.0)
    assert wdo.medido_em == "2026-09-10"
    assert (wdo.n_entrada, wdo.n_saida) == (11, 11)
    # 18% de censura dos dois lados -- o que torna a mediana observada
    # confiavel o bastante para o Kaplan-Meier coincidir com a ingenua.
    assert wdo.censuradas_entrada == wdo.censuradas_saida == 2


def test_toda_entrada_da_tabela_declara_o_proprio_simbolo():
    """A chave do dicionario e o campo `symbol` sao duas fontes para o mesmo
    dado -- e um numero declarado em dois lugares e' um numero que vai
    divergir (primeira frase de `backtest.intraday.profiles`)."""
    for symbol, fid in FIDELIDADE.items():
        assert fid.symbol == symbol


def test_todo_simbolo_calibrado_tem_perfil_para_operar():
    """Calibrar a fila de um simbolo que nenhum perfil consegue montar seria
    numero medido que nunca chega a run nenhuma."""
    for symbol in FIDELIDADE:
        assert profile_for(symbol) is not None


# ---------- acesso: KeyError, nunca default silencioso ---------------------

def test_fidelidade_de_simbolo_desconhecido_levanta():
    """Um default aqui emprestaria a fila de um mini-dolar (329/494
    CONTRATOS) para uma acao de centavos, e o numero entraria no motor com
    cara de medicao."""
    with pytest.raises(KeyError, match="sem fidelidade de execucao"):
        fidelidade_for("NAO_EXISTE")


def test_a_porta_tolerante_devolve_none_em_vez_de_levantar():
    """As duas portas existem para consumidores diferentes: `fidelidade_for`
    e' "qual e' a fidelidade MEDIDA deste simbolo?" (e para quem nao tem, a
    resposta honesta e' 'nao existe'); `fidelidade_ou_none` e' "ESTE simbolo
    tem calibracao?", a pergunta de quem monta config para PMAM3, WIN@ e
    WDO@ pelo mesmo caminho e nao pode quebrar em dois deles."""
    assert fidelidade_ou_none("WDO@") is FIDELIDADE["WDO@"]
    assert fidelidade_ou_none("PMAM3") is None
    assert fidelidade_ou_none("WIN@") is None


def test_mensagem_de_erro_ensina_a_desligar_de_proposito():
    """Quem quer rodar SEM fila (o motor antigo) tem de saber como pedir
    isso em voz alta -- senao a saida do erro e' 'inventa uma entrada na
    tabela', que e' o oposto do ponto."""
    with pytest.raises(KeyError) as exc:
        fidelidade_for("PMAM3")
    assert "queue_ahead_qty=0.0" in str(exc.value)


# ---------- config_for aplica sozinho -------------------------------------

def test_config_for_aplica_a_calibracao_do_wdo_sozinho():
    """O TESTE CENTRAL. Falha no codigo antigo: `config_for` tinha os dois
    parametros com default 0,0 e ninguem os passava -- o backtest enchia
    toda ordem-limite no primeiro toque do nivel. Simulando o pregao real de
    2026-09-09 assim, o motor devolvia +R$3,82 por operacao num dia que deu
    -R$3,00: erro de SINAL, nao de magnitude."""
    wdo = FIDELIDADE["WDO@"]
    config = _config_wdo()
    # A identidade com a TABELA e' o invariante -- os valores em si sao
    # pinados em `test_a_calibracao_vigente_declara_a_propria_procedencia`.
    # Repeti-los aqui faria uma recalibracao legitima quebrar dois testes
    # pelo mesmo motivo, escondendo qual deles e' o alarme de verdade.
    assert config.queue_ahead_qty == wdo.queue_ahead_qty
    assert config.exit_queue_ahead_qty == wdo.exit_queue_ahead_qty
    assert config.queue_ahead_qty > 0.0 and config.exit_queue_ahead_qty > 0.0


def test_valor_explicito_vence_a_calibracao():
    """Reproduzir o motor antigo (a linha "sem fila" de uma comparacao) tem
    de continuar possivel, e explicitamente -- mesma regra de
    `target_slippage_ticks=0.0`."""
    antigo = _config_wdo(queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    assert antigo.queue_ahead_qty == 0.0
    assert antigo.exit_queue_ahead_qty == 0.0

    # E sensibilidade: a amostra tem n=11 de cada lado, entao variar o numero
    # e' uso previsto, nao gambiarra.
    sens = _config_wdo(exit_queue_ahead_qty=600.0)
    assert sens.exit_queue_ahead_qty == 600.0
    assert sens.queue_ahead_qty == FIDELIDADE["WDO@"].queue_ahead_qty, \
        "um lado explicito nao apaga o outro"


def test_simbolo_sem_medicao_fica_sem_fila_nunca_herda_a_do_wdo():
    """Uma acao de centavos nao pode receber 329 CONTRATOS de fila por
    default. Sem pregao real medido, o honesto e' 0,0 -- que e' o motor
    otimista de sempre, mas declarado, nao emprestado."""
    acao = config_for(profile_for("PMAM3"), trade_tick_value=0.01,
                      trade_tick_size=0.01, preco_atual=1.0)
    assert acao.queue_ahead_qty == 0.0
    assert acao.exit_queue_ahead_qty == 0.0


def test_perfil_montado_a_mao_nao_recebe_fila_de_ninguem():
    """`SymbolProfile` nao carrega o proprio simbolo -- quem carrega e' a
    chave da tabela. Um perfil sintetico (teste, script de laboratorio) nao
    esta' em tabela nenhuma e tem de cair no ramo 'sem calibracao', nunca
    num simbolo parecido."""
    sintetico = dataclasses.replace(profile_for("WDO@"))
    config = config_for(sintetico, initial_capital=375.0, **_WDO_ECON)
    assert config.queue_ahead_qty == 0.0
    assert config.exit_queue_ahead_qty == 0.0


# ---------- o carimbo na tabela padrao ------------------------------------

class _ResultadoFake:
    """O minimo que `linha_de_resultado` le' de um `IntradayBacktestResult`.
    Montar o de verdade exigiria rodar um backtest, que nao e' o que este
    arquivo testa."""

    def __init__(self, fila_entrada=0.0, fila_saida=0.0, calibrada=None):
        self.trades = []
        self.equity_curve = None
        self.metrics = {"max_drawdown": 0.0}
        self.wiped_out_at = None
        self.sessoes_puladas_por_capital = []
        self.deslize_alvo_ticks = 0.0
        self.fila_entrada_qty = fila_entrada
        self.fila_saida_qty = fila_saida
        self.fila_calibrada = calibrada


def test_carimbo_da_fila_aparece_na_linha_e_nao_vira_coluna():
    """PREMISSA DE PREENCHIMENTO tem de ser visivel: duas linhas com o mesmo
    `liquido R$` e filas diferentes nao sao comparaveis, e ate' 2026-09-09
    elas sairiam IDENTICAS na tabela.

    Sai no `aviso`, nunca como coluna -- a base sao 12 colunas fixas, e uma
    coluna que nao existe em toda rodada quebraria a comparacao entre
    tabelas."""
    item = linha_de_resultado("x", _ResultadoFake(438.0, 489.0, calibrada=True),
                              initial_capital=375.0)
    assert "fila 438/489" in item.aviso
    assert "fila 438/489" in linha(item)
    assert "fila" not in cabecalho(), "premissa nao vira coluna da base"


def test_run_sem_fila_nao_ganha_carimbo_e_resultado_antigo_nao_explode():
    """O carimbo e' sobre o que ESTA sendo assumido. Uma run sem fila (motor
    antigo, ou comparacao deliberada) nao pode carregar rotulo que sugira o
    contrario -- e um `IntradayBacktestResult` velho, sem os campos, tem de
    continuar passando pela tabela."""
    assert linha_de_resultado("x", _ResultadoFake(), initial_capital=375.0).aviso == ""

    class _ResultadoAntigo:
        trades = []
        equity_curve = None
        metrics = {"max_drawdown": 0.0}

    assert linha_de_resultado("x", _ResultadoAntigo(), initial_capital=375.0).aviso == ""


def test_carimbo_sai_mesmo_com_um_lado_so_ligado():
    """A afericao de 2026-09-09 rodou uma celula com Q_entrada=0 e
    Q_saida=400 (o chute anterior a calibracao). Uma linha assim tem premissa
    diferente da linha sem fila nenhuma e nao pode sair igual a ela."""
    item = linha_de_resultado("x", _ResultadoFake(0.0, 400.0),
                              initial_capital=375.0)
    assert "fila 0/400" in item.aviso


def test_simbolo_sem_calibracao_diz_isso_na_linha_em_vez_de_sumir():
    """O TERCEIRO estado, e o que mais importa. Uma linha SEM carimbo nenhum
    e' indistinguivel de uma linha que ninguem sabe se esta certa -- foi
    exatamente assim que `queue_ahead_qty` passou um mes no default 0,0 sem
    ninguem notar. Gremah roda em acao B3 e CopaWin em WIN@: nenhum dos dois
    foi medido, e a tabela deles tem de dizer isso em voz alta."""
    item = linha_de_resultado("x", _ResultadoFake(0.0, 0.0, calibrada=False),
                              initial_capital=375.0)
    assert "fila NAO CALIBRADA" in item.aviso
    assert "fila NAO CALIBRADA" in linha(item)


def test_zero_deliberado_e_zero_por_ausencia_de_medicao_nao_saem_iguais():
    """Os dois sao `queue_ahead_qty=0.0` no motor e produzem o MESMO
    resultado numerico -- e significam coisas opostas. Um e' premissa
    declarada (reproduzir o motor de ate 2026-09-08 num simbolo medido); o
    outro e' 'ninguem mediu este simbolo'. Confundi-los na leitura e' o bug
    que este modulo inteiro existe para consertar."""
    deliberado = linha_de_resultado("x", _ResultadoFake(0.0, 0.0, calibrada=True),
                                    initial_capital=375.0).aviso
    sem_medicao = linha_de_resultado("x", _ResultadoFake(0.0, 0.0, calibrada=False),
                                     initial_capital=375.0).aviso
    assert deliberado == "fila 0/0"
    assert sem_medicao == "fila NAO CALIBRADA"
    assert deliberado != sem_medicao


def test_fila_chutada_em_simbolo_nao_medido_nao_passa_por_calibracao():
    """Sensibilidade num simbolo sem medicao e' legitima (e prevista), mas a
    linha nao pode sair parecendo calibrada: o numero ali e' escolha do
    chamador, nao medicao."""
    item = linha_de_resultado("x", _ResultadoFake(100.0, 200.0, calibrada=False),
                              initial_capital=375.0)
    assert "fila 100/200 (nao calibrada)" in item.aviso


def test_config_for_marca_a_procedencia_da_fila_no_modelo_de_custo():
    """O carimbo da tabela nao pode depender de cada script lembrar de
    passar a procedencia -- ela viaja sozinha de `config_for` ate' o
    resultado, pelo modelo de custo (que ja e' o carregador das premissas de
    execucao da run)."""
    assert _config_wdo().costs.fidelidade_calibrada is True
    acao = config_for(profile_for("PMAM3"), trade_tick_value=0.01,
                      trade_tick_size=0.01, preco_atual=1.0)
    assert acao.costs.fidelidade_calibrada is False
    win = config_for(profile_for("WIN@"), trade_tick_value=0.2,
                     trade_tick_size=1.0, initial_capital=200.0)
    assert win.costs.fidelidade_calibrada is False, "WIN@ nunca foi medido"


def test_backtest_de_acao_de_ponta_a_ponta_nao_quebra_e_sai_marcado():
    """O caminho EM RISCO da mudanca: so' o WDO@ tem calibracao, e um
    `fidelidade_for` estrito no meio de `config_for` quebraria todo backtest
    de acao (Gremah, PMAM3 e as outras nove) e do WIN@ (CopaWin). Roda o
    motor inteiro num simbolo sem medicao e confere as duas pontas -- nao
    levanta, e a linha sai dizendo que ninguem mediu."""
    import pandas as pd

    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.gremah import Gremah

    idx = pd.date_range("2026-03-02 13:00", periods=180, freq="min", tz="UTC")
    preco = 4.50
    bars = pd.DataFrame({"open": preco, "high": preco + 0.02, "low": preco - 0.02,
                         "close": preco, "volume": 5000.0}, index=idx)
    config = config_for(profile_for("PMAM3"), trade_tick_value=0.01,
                        trade_tick_size=0.01, preco_atual=preco)
    result = run_intraday_backtest(bars, Gremah(symbol="PMAM3"), config)

    assert result.fila_entrada_qty == 0.0
    assert result.fila_calibrada is False
    item = linha_de_resultado("PMAM3", result, initial_capital=config.initial_capital)
    assert "fila NAO CALIBRADA" in item.aviso
