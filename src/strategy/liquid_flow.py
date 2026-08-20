"""LiquidFlowSleeve — universo liquido CONTINUO, com histerese de rank.

O problema que este arquivo resolve
-----------------------------------
`strategy/liquid_sleeve.py` refaz o universo a cada `refresh_months`. Isso deixa
duas coisas ruins no robo:

  1. **Um parametro que a evidencia nao escolhe.** `scripts/run_sleeve_tuning.py`
     varreu 12/24/36/60/120 meses nas cinco janelas de cinco anos: so o "pior
     CAGR" e monotono na cadencia (melhora quando afrouxa); o MaxDD e o pior
     retorno de 12 meses PIORAM em 120 meses (-45,8% e -35,1%). Nao existe
     cadencia que domine — escolher uma pelo capital seria exatamente o
     curve-fitting que invalidou a watchlist oficial deste projeto.

  2. **Uma data de ancoragem arbitraria.** As epocas caem no calendario (janeiro
     de cada N anos). Quem liga o robo em agosto opera ate 11 meses com um
     universo velho, e o resultado da janela passa a depender de quando ela
     comeca — que nao e uma propriedade do robo, e do teste.

A saida e nao ter cadencia. Aqui a liquidez e reavaliada em TODO fim de mes — o
mesmo dia em que o robo ja decide tudo — e a troca de universo e amortecida por
HISTERESE DE RANK, o mesmo mecanismo que a familia ja usa para nao rotacionar
posicao a cada oscilacao de momentum:

    entra   quem esta entre os `universe_n` mais liquidos
    fica    enquanto estiver entre os `exit_rank` mais liquidos
    sai     quando cai abaixo disso

Com `universe_n=20` e `exit_rank=30`, um papel oscilando entre a 19a e a 22a
posicao nao entra e sai do robo toda virada de mes. So sai quem afundou de
verdade na liquidez — que e o unico motivo pelo qual a regra existe.

Estabilidade do sleeve
----------------------
Um papel e atribuido a um sleeve quando ENTRA no universo e fica nele ate sair.
Nao da para usar o rodizio `[i::k]` de `liquid_sleeve.py` aqui: com o universo
mudando de composicao, a posicao de um papel na lista ordenada muda sozinha e
ele pularia de sleeve sem ter feito nada — o robo venderia e recompraria o mesmo
papel em contas diferentes. A atribuicao vai para o sleeve com MENOS membros
(empate: menor indice), o que mantem os cinco do mesmo tamanho e e determinista:
os cinco sleeves rodam o mesmo algoritmo sobre os mesmos dados e chegam
necessariamente a mesma divisao, sem precisar conversar entre si.

Esta classe nao e um robo (`candidate = False`). O robo e
`strategy/liquid_flow5.py`.
"""
from __future__ import annotations

import pandas as pd

from core.calendar import is_month_end
from strategy.liquid_sleeve import LiquidSleeve


class LiquidFlowSleeve(LiquidSleeve):
    """Sleeve cujo universo e reavaliado todo mes, com banda de rank 20/30."""

    name = "liquid_flow_sleeve"
    version = "1.0"
    candidate = False

    def __init__(self, exit_rank: int = 30, **kwargs):
        kwargs.setdefault("evict_on_refresh", False)
        super().__init__(**kwargs)
        self.exit_rank = exit_rank

    def _build_eligibility(self, panels, index: pd.DatetimeIndex) -> pd.DataFrame:
        turnover, history = {}, {}
        for t, df in panels.items():
            if t.startswith("^") or "volume" not in df.columns:
                continue
            tv = (df["close"] * df["volume"]).dropna()
            adtv_t = tv.rolling(self.liquidity_window, min_periods=self.liquidity_window // 2).median()
            turnover[t] = adtv_t.reindex(index).ffill()
            seen = pd.Series(range(1, len(df.index) + 1), index=df.index, dtype=float)
            history[t] = seen.reindex(index).ffill().fillna(0.0)
        if not turnover:
            return pd.DataFrame(index=index)

        adtv = pd.DataFrame(turnover, index=index)
        hist = pd.DataFrame(history, index=index)
        eligible = pd.DataFrame(False, index=index, columns=adtv.columns)
        cols = list(adtv.columns)
        col_pos = {t: i for i, t in enumerate(cols)}

        # Reavaliar so nos fins de mes: e quando `on_bar` decide qualquer coisa,
        # e recalcular o ranking nos outros ~20 pregoes do mes seria trabalho
        # jogado fora (e 20x mais lento) sem mudar uma unica ordem.
        month_end = is_month_end(index)
        checkpoints = [0] + [i for i in range(len(index)) if bool(month_end.iloc[i])]

        members: dict[str, int] = {}   # ticker -> sleeve
        prev = 0
        current: list[str] = []
        for pos in checkpoints:
            if pos > prev and current:
                idx = [col_pos[t] for t in current]
                eligible.iloc[prev:pos, idx] = True
            d = index[pos]
            row = adtv.loc[d]
            ok = row[(row > 0) & row.notna() & (hist.loc[d] >= self.min_history_days)]
            order = list(ok.sort_values(ascending=False).index)
            rank = {t: i + 1 for i, t in enumerate(order)}

            # 1. quem afundou abaixo da banda sai (e libera a vaga do sleeve)
            for t in [t for t in members if rank.get(t, 10**9) > self.exit_rank]:
                members.pop(t)
            # 2. as vagas restantes vao para os mais liquidos que ainda estao fora
            for t in order[: self.universe_n]:
                if len(members) >= self.universe_n:
                    break
                if t in members:
                    continue
                counts = [0] * self.sleeve_count
                for s in members.values():
                    counts[s] += 1
                members[t] = counts.index(min(counts))

            current = [t for t, s in members.items() if s == self.sleeve_index]
            prev = pos
        if current and prev < len(index):
            eligible.iloc[prev:, [col_pos[t] for t in current]] = True
        return eligible
