"""A REGUA da Copa BTG Trader — escrita ANTES de qualquer sinal existir.

Ordem deliberada, e e' o ponto inteiro do modulo: primeiro se define como o
resultado sera' julgado, depois se inventa a estrategia. O caminho inverso
(inventar, medir, e so' entao escolher a metrica que ela ganha) e' a forma
mais comum de se enganar sozinho num projeto de trading, e este repo ja tem
precedente de estrategia descartada por nao confirmar (CMIN3, BBDC3, EQTL3,
EUCA4 — ver `backtest/intraday/profiles.py::OOS_CUTOFF`).

Funcao pura sobre `list[IntradayTrade]`: sem I/O, sem banco, sem MT5. O que
entra e' o que `run_intraday_backtest` devolve; o que sai sao numeros.

## A unidade e' o BLOCO, nao a curva

A competicao nao mede curva acumulada — mede FASE, e cada fase e' um punhado
de pregoes seguidos:

| fase (2026) | pregoes |
|---|---|
| Classificatoria 1 (14–17/09) | 4 |
| Classificatoria 2 (21–24/09) | 4 |
| Repescagem (28–30/09) | 3 |
| Semifinal (13–16/10) | 4 |
| Final presencial (29/10) | 2 baterias de 45 min |

Por isso o julgamento out-of-sample e' feito em blocos de `PREGOES_POR_FASE`
pregoes consecutivos, nunca numa curva de 50 pregoes: uma curva esconde que
o resultado inteiro veio de dois dias bons; doze blocos, nao. Um robo que
lucra no acumulado mas perde em 7 dos 12 blocos NAO serve para esta
competicao — ele precisaria ter sorte de cair numa janela boa.

## `score_copa` e' RELATORIO, nunca criterio

O ranking oficial soma os liquidos diarios DESCARTANDO o pior dia. Explorar
isso (torrar risco no dia que ja esta perdido, porque ele "nao conta") foi
descartado pelo dono explicitamente: a funcao objetivo e' lucro total,
convencional. `score_copa` existe so' para reportar onde a estrategia
ficaria no ranking — nenhuma selecao de parametro pode ler este numero.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backtest.intraday.machine import IntradayTrade

#: Pregoes de uma fase classificatoria/semifinal da Copa — a unidade de
#: julgamento (ver docstring). A repescagem tem 3; `blocos_de_fase` aceita
#: qualquer tamanho, este e' so' o default.
PREGOES_POR_FASE = 4

#: Minutos de UMA bateria da final presencial. 40 e' o tempo de PROJETO
#: (decisao do dono 2026-08-25: "nosso tempo maximo nao deve ser 45, mas sim
#: 40"); 45 e' o tempo real anunciado, usado como CONFIRMACAO de que o robo
#: nao devolve ganho depois do minuto 40. Os dois sempre reportados juntos.
MINUTOS_BATERIA = (40, 45)


def _sem_tz(ts) -> pd.Timestamp:
    """Timestamp SEM fuso, preservando o instante como ele esta guardado.

    Toda serie deste modulo e' tz-naive de proposito, pela mesma convencao
    que `backtest/intraday/engine.py` ja usa ao agrupar sessoes
    (`bars.index.date`, que le a data no fuso em que a barra foi salva, UTC).
    Misturar tz-aware e tz-naive na mesma comparacao levanta `TypeError` no
    pandas — arrancar o fuso UMA vez, na fronteira, evita isso em todo o
    resto do modulo.

    Seguro para a B3: o pregao vai de 12:00 a 21:30 UTC, nunca cruza a
    meia-noite UTC, entao a data UTC e a data do pregao sao sempre a mesma."""
    ts = pd.Timestamp(ts)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _data_do_trade(trade: IntradayTrade) -> pd.Timestamp:
    """O pregao de um trade e' o do FECHAMENTO, nao o da abertura: e' quando
    o P&L vira resultado realizado. Day trade nunca cruza a virada (o motor
    achata na ultima barra), entao os dois coincidem sempre — a escolha so'
    importa para nao depender disso por acidente."""
    return _sem_tz(trade.exit_ts).normalize()


def resultados_diarios(trades: list[IntradayTrade]) -> pd.Series:
    """P&L LIQUIDO por pregao, em reais, indexado por data crescente.

    Pregao sem nenhum trade simplesmente nao aparece — nao e' zero: a serie
    descreve os dias em que o robo operou, e quem precisa da grade completa
    de pregoes (para contar dia parado) reindexa com o calendario do dado.
    Serie vazia (nenhum trade) volta vazia, nao levanta."""
    if not trades:
        return pd.Series(dtype="float64", name="liquido_brl")
    df = pd.DataFrame({
        "data": [_data_do_trade(t) for t in trades],
        "pnl": [t.pnl_brl for t in trades],
    })
    serie = df.groupby("data")["pnl"].sum().sort_index()
    serie.name = "liquido_brl"
    return serie


@dataclass(frozen=True)
class BlocoFase:
    """Um bloco de `pregoes` pregoes CONSECUTIVOS da serie diaria — o analogo
    de uma fase da competicao."""

    inicio: pd.Timestamp
    fim: pd.Timestamp
    pregoes: int
    liquido_brl: float
    #: Pior pregao do bloco (pode ser positivo, se todos foram positivos).
    pior_dia_brl: float
    #: Melhor pregao do bloco — junto com `pior_dia_brl` responde "o bloco
    #: inteiro depende de um dia so'?" sem precisar da serie crua.
    melhor_dia_brl: float
    dias_positivos: int

    @property
    def positivo(self) -> bool:
        return self.liquido_brl > 0

    @property
    def score_copa_brl(self) -> float:
        """Liquido do bloco DESCARTANDO o pior pregao — a regra de ranking da
        Copa. RELATORIO apenas: nenhuma selecao de parametro le isto (ver a
        docstring do modulo)."""
        return self.liquido_brl - self.pior_dia_brl


def blocos_de_fase(diarios: pd.Series, pregoes: int = PREGOES_POR_FASE) -> list[BlocoFase]:
    """Fatia a serie diaria em blocos NAO SOBREPOSTOS de `pregoes` pregoes,
    do mais antigo para o mais novo.

    Sobra que nao completa um bloco e' DESCARTADA — um bloco de 2 pregoes nao
    e' comparavel a um de 4, e mante-lo na amostra deixaria o resultado do
    portao depender de onde o dado por acaso terminou. Quem precisa saber
    quanto sobrou compara `len(diarios)` com `len(blocos) * pregoes`.

    Blocos sao contados sobre os pregoes COM TRADE (a serie que
    `resultados_diarios` devolve), nao sobre o calendario: um dia em que o
    robo nao operou nao gasta uma vaga da fase — na competicao ele existiria,
    mas com resultado zero, e zero nao muda soma nem pior-dia negativo."""
    if pregoes <= 0:
        raise ValueError(f"blocos_de_fase: `pregoes` tem de ser >= 1, veio {pregoes!r}")
    serie = diarios.sort_index()
    blocos: list[BlocoFase] = []
    for inicio in range(0, len(serie) - pregoes + 1, pregoes):
        pedaco = serie.iloc[inicio:inicio + pregoes]
        blocos.append(BlocoFase(
            inicio=pd.Timestamp(pedaco.index[0]),
            fim=pd.Timestamp(pedaco.index[-1]),
            pregoes=len(pedaco),
            liquido_brl=float(pedaco.sum()),
            pior_dia_brl=float(pedaco.min()),
            melhor_dia_brl=float(pedaco.max()),
            dias_positivos=int((pedaco > 0).sum()),
        ))
    return blocos


@dataclass(frozen=True)
class ResumoBlocos:
    """O que o portao de aceitacao (G1–G4 do plano) precisa saber, calculado
    uma vez em cima da lista de blocos."""

    n_blocos: int
    positivos: int
    liquido_mediano_brl: float
    pior_bloco_brl: float
    melhor_bloco_brl: float
    #: Mediana dos blocos VENCEDORES — a referencia de G3 ("nenhum bloco
    #: perde mais do que um bloco tipico ganha").
    mediana_dos_vencedores_brl: float
    pior_pregao_brl: float
    #: Mediana dos pregoes POSITIVOS — a referencia de G4.
    mediana_dos_pregoes_positivos_brl: float

    @property
    def fracao_positiva(self) -> float:
        return self.positivos / self.n_blocos if self.n_blocos else 0.0


def resumir_blocos(blocos: list[BlocoFase], diarios: pd.Series) -> ResumoBlocos:
    """`blocos` vazio devolve um resumo todo zerado — e' o caso "a estrategia
    nao produziu nem uma fase inteira de dado", que o portao reprova por
    `n_blocos` insuficiente, nao por excecao aqui."""
    if not blocos:
        return ResumoBlocos(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    liquidos = pd.Series([b.liquido_brl for b in blocos])
    vencedores = liquidos[liquidos > 0]
    positivos_diarios = diarios[diarios > 0] if len(diarios) else pd.Series(dtype="float64")
    return ResumoBlocos(
        n_blocos=len(blocos),
        positivos=int((liquidos > 0).sum()),
        liquido_mediano_brl=float(liquidos.median()),
        pior_bloco_brl=float(liquidos.min()),
        melhor_bloco_brl=float(liquidos.max()),
        mediana_dos_vencedores_brl=float(vencedores.median()) if len(vencedores) else 0.0,
        pior_pregao_brl=float(diarios.min()) if len(diarios) else 0.0,
        mediana_dos_pregoes_positivos_brl=(
            float(positivos_diarios.median()) if len(positivos_diarios) else 0.0
        ),
    )


def janelas_sprint(
    trades: list[IntradayTrade],
    minutos: int,
    passo_minutos: int = 5,
) -> pd.DataFrame:
    """P&L de TODA janela deslizante de `minutos` dentro de cada pregao — a
    simulacao da bateria da final presencial.

    Um trade conta na janela so' se ABRIU e FECHOU dentro dela. E' a regra da
    bateria de verdade: o competidor chega zerado, tem `minutos` de relogio e
    e' achatado no fim; o que ficou aberto quando o apito toca nao virou
    resultado dele. Contar por `exit_ts` sozinho daria a uma janela o lucro
    de um trade montado antes de ela comecar.

    `passo_minutos` e' a resolucao da varredura (5 = uma janela a cada 5
    minutos de pregao). Nao e' aproximacao do resultado: cada janela avaliada
    e' exata; o passo so' decide QUANTAS janelas se olha. Existe porque o
    horario das baterias nao e' publico — nao ha uma janela "certa" para
    medir, entao se mede todas e se reporta a distribuicao, incluindo a PIOR
    (a final de 2025 foi ganha com uma bateria forte e uma quase zerada:
    +R$1.099 e -R$14,20).

    Colunas: `data`, `inicio`, `fim`, `liquido_brl`, `trades`. DataFrame
    vazio (com as colunas) se nao houver trade nenhum."""
    colunas = ["data", "inicio", "fim", "liquido_brl", "trades"]
    if not trades or minutos <= 0:
        return pd.DataFrame(columns=colunas)

    df = pd.DataFrame({
        "entrada": [_sem_tz(t.entry_ts) for t in trades],
        "saida": [_sem_tz(t.exit_ts) for t in trades],
        "pnl": [t.pnl_brl for t in trades],
    })
    df["data"] = df["saida"].dt.normalize()
    largura = pd.Timedelta(minutes=minutos)
    passo = pd.Timedelta(minutes=max(1, passo_minutos))

    linhas: list[dict] = []
    for data, grupo in df.groupby("data"):
        primeiro = grupo["entrada"].min()
        ultimo = grupo["saida"].max()
        if ultimo <= primeiro:
            ultimo = primeiro
        inicio = primeiro
        entradas = grupo["entrada"].to_numpy()
        saidas = grupo["saida"].to_numpy()
        pnls = grupo["pnl"].to_numpy()
        while inicio <= ultimo:
            fim = inicio + largura
            dentro = (entradas >= inicio.to_datetime64()) & (saidas <= fim.to_datetime64())
            linhas.append({
                "data": data, "inicio": inicio, "fim": fim,
                "liquido_brl": float(pnls[dentro].sum()),
                "trades": int(dentro.sum()),
            })
            inicio = inicio + passo
    return pd.DataFrame(linhas, columns=colunas)


def resumo_sprint(janelas: pd.DataFrame) -> dict:
    """Distribuicao das janelas de bateria, em uma linha de relatorio.

    `pior` tem o MESMO peso da mediana na leitura (decisao registrada no
    plano): a final e' ganha com uma bateria forte e uma nao-desastrosa, nao
    com duas medianas."""
    if janelas.empty:
        return {"janelas": 0, "pior": 0.0, "p25": 0.0, "mediana": 0.0,
                "p75": 0.0, "melhor": 0.0, "positivas_pct": 0.0}
    v = janelas["liquido_brl"]
    return {
        "janelas": int(len(v)),
        "pior": float(v.min()),
        "p25": float(v.quantile(0.25)),
        "mediana": float(v.median()),
        "p75": float(v.quantile(0.75)),
        "melhor": float(v.max()),
        "positivas_pct": float(100.0 * (v > 0).mean()),
    }
