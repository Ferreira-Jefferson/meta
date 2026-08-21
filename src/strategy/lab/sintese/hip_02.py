"""sintese_02 -- Universo de iliquidez relativa ao grupo (sobrevivente C2,
familia `iliquidez`) + dimensionamento por orcamento de risco com stop ATR
enforced (sobrevivente C2, familia `risk_targeting`), no lugar do
igual-ponderado `sh = 1/top_n`.

Mecanismos combinados e POR QUE (razao escrita antes de medir)
----------------------------------------------------------------
1. `Hip06IliquidezRelativaAoGrupo` (`iliquidez/hip_06.py`) -- mesmo universo
   da `hip_01.py` desta pasta: os 33% de MENOR giro DENTRO do proprio terco
   de vol realizada.
2. `RiskCappedWithStop` (`risk_targeting/hip_05.py`) -- pesa cada entrada por
   `peso = min(2% / (3*ATR%), 40%)` e registra um stop ABSOLUTO no engine em
   `close[D] * (1 - 3*ATR%)`, fechando o ciclo entre "quanto risco eu quero
   correr" e "o que de fato me tira da posicao".

Estes dois mecanismos operam em eixos ORTOGONAIS ao par da `hip_01.py`: ali
o segundo mecanismo mudava QUAL papel ranqueia melhor (ranking); aqui o
universo (mecanismo 1, INTOCADO -- mesmo algoritmo, mesmo `iliquidez_06`)
continua decidido pelo momentum 12-1 original de `BuyTheDip`, e o que muda
e QUANTO alocar em cada papel escolhido (dimensionamento), nao quem e
escolhido. As duas sinteses juntas cobrem os tres eixos independentes que a
busca separou: universo, ranking, tamanho.

Razao a priori especifica: `iliquidez_06` compra `top_n=3` com peso IGUAL
apesar de o universo, por construcao, misturar os TRES tercos de
volatilidade realizada (o mecanismo so exige "menor giro DENTRO do proprio
terco" -- um papel de baixa vol tipo utility e um de alta vol tipo small
cap ciclica podem ambos aparecer no top-3 do mes). Peso igual trata um
papel de vol baixa e um de vol alta como o mesmo risco em reais, quando nao
sao. `RiskCappedWithStop` ja resolve exatamente esse problema (dimensionar
pelo ATR%, nao pela contagem de posicoes) para o universo AMPLO onde foi
medido (DSR 0,300, a mais baixa das 5 sobreviventes, mas ainda positiva).
A aposta a priori: aplicado ESPECIFICAMENTE ao universo mais concentrado e
mais heterogeneo em vol de `iliquidez_06` -- onde a mistura de tercos e
deliberada -- o dimensionamento por risco deveria ter mais o que fazer do
que no pool aberto onde a maioria dos papeis ja e razoavelmente homogenea
em liquidez. Isso deveria aparecer na cauda: `worst_dd` e `worst_12m`
melhores que `iliquidez_06` sozinho, ao preco de CAGR mediano provavelmente
menor (o stop ATR realiza perdas que o rebalance mensal de `iliquidez_06`
teria deixado a carteira absorver e reverter).

Isto NAO e uma sintese de corte de exposicao por regime (a familia
`dd_control` fechou 0 de 10 tentativas nesse eixo, ja documentado): o
mecanismo aqui reparte o MESMO capital entre as MESMAS posicoes por
contribuicao de risco relativa entre elas, com um stop explicito por
posicao -- nao existe leitura de regime de mercado, nao existe corte de
caixa por drawdown da carteira, nao existe redução de `top_n`.
"""
from __future__ import annotations

import pandas as pd

from strategy.lab.risk_targeting.hip_05 import RiskCappedWithStop
from strategy.lab.sintese._common import group_relative_illiquidity_mask
from swing_lab.measure import wide_pool

GROUP_VOL_WINDOW = 63
ADTV_WINDOW = 252
ADTV_FLOOR = 100_000.0
WITHIN_BUCKET_PCT = 0.33


class IliquidezGrupoComRiscoOrcado(RiskCappedWithStop):
    """RiskCappedWithStop (momentum 12-1 + peso por orcamento de risco +
    stop ATR) restrito ao universo de iliquidez-relativa-ao-grupo de
    `iliquidez_06`.
    """

    name = "sintese_02_iliquidez_grupo_risco_orcado"
    version = "1.0"
    # Promovida 2026-08-20 — unica sobrevivente do cofre selado (1998-2009)
    # entre 122 hipoteses medidas na busca de swing DD<=40%. Decisao do dono
    # do capital, tomada ANTES de walk-forward/C1/C3/C5 e do porte para
    # operacao ao vivo: competir no ranking automatico (ver
    # `strategy/discovery.py::_PROMOTED_LAB_MODULES`) nao substitui esse
    # escrutinio, so deixa o robo visivel enquanto ele acontece.
    #
    # APOSENTADA do podio em 2026-08-21 — nao por desempenho medido, e' a
    # decisao explicita do dono do capital de reduzir o podio a UM robo so
    # (`liqflop`, ex-`liquid_focus_loss_pause`), apos a investigacao de capital real
    # (R$100 + taxa fixa fracionaria) mostrar que esta classe (medida a
    # R$1.000, sem essa taxa) nunca foi validada no regime que o dono
    # realmente opera. Aposentar nao e apagar: continua resolvivel por chave.
    candidate = False
    universe_tickers = wide_pool()

    def __init__(
        self,
        group_vol_window: int = GROUP_VOL_WINDOW,
        adtv_window: int = ADTV_WINDOW,
        adtv_floor: float = ADTV_FLOOR,
        within_bucket_pct: float = WITHIN_BUCKET_PCT,
        **kwargs,
    ):
        # top_n=5 herdado do default de `RiskTargetingDip`: dimensionamento
        # so diz algo quando ha mais de uma posicao para comparar tamanho
        # entre si (mesma razao a priori documentada em `_common.py` da
        # familia risk_targeting). dip_pct/high_window seguem o congelado
        # `BuyTheDip`/campeao (2%, 40 dias).
        super().__init__(**kwargs)
        self.group_vol_window = group_vol_window
        self.adtv_window = adtv_window
        self.adtv_floor = adtv_floor
        self.within_bucket_pct = within_bucket_pct

    def initialize(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        # Cadeia completa: BuyTheDip (scores=momentum, dist_from_high, gates)
        # -> RiskTargetingDip (vol/atr_pct/worst_dd) -> RiskCappedWithStop
        # (self._close, para o stop absoluto). Nada disso e reescrito aqui.
        super().initialize(panels, ibov)

        eligible = group_relative_illiquidity_mask(
            panels,
            ibov,
            vol_window=self.group_vol_window,
            adtv_window=self.adtv_window,
            adtv_floor=self.adtv_floor,
            within_bucket_pct=self.within_bucket_pct,
        )

        for t in list(self._scores.keys()):
            if t not in eligible.columns:
                self._scores[t] = pd.Series(float("nan"), index=self._scores[t].index)
                continue
            mask = eligible[t].reindex(self._scores[t].index).fillna(False)
            self._scores[t] = self._scores[t].where(mask)


if __name__ == "__main__":
    import sys as _s

    _s.path.insert(0, "src")
    _s.path.insert(0, "scripts")
    from swing_lab.measure import screen

    r = screen(
        lambda: IliquidezGrupoComRiscoOrcado(),
        name="sintese_02_iliquidez_grupo_risco_orcado",
        family="sintese",
        note="iliquidez_06 (universo) + risk_targeting_05 (peso por risco + stop ATR)",
    )
    print(r)
