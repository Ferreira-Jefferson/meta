"""Sessao com `zerar` por ORDEM LIMITADA (variante de execucao da v3). Isto e custo de execucao, nao ajuste de estrategia.

`zerar` (decisao da gestao no fechamento da vela k): em vez de sair a mercado na abertura da k+1, coloca uma ordem-limite de saida no ultimo
fechamento (arredondado para o lado passivo: venda -> tick acima; compra -> tick abaixo), valida por 2 velas (k+1 e k+2). Enche pela mesma regra
do motor (passou FILL_PTS alem do preco no M1). Se nao encher, a posicao continua com o stop original (e o trailing/stop_pivo seguem valendo).
No mesmo M1, stop vence (conservador, como no motor). Um novo `zerar` com saida pendente e ignorado."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from motor import Sessao, arredonda, _hm, TICK
from decisoes import _tick_baixo, _tick_alto

VALIDADE_SAIDA = 2


class SessaoL(Sessao):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.exit_pend = None
        self.zerar_pedidos = 0

    def aplicar(self, dec, k):
        if dec.get("acao") == "zerar":
            d = self.dia
            t_dec = _hm(d.m15_t[k] + np.timedelta64(15, "m"))
            if not self.pos:
                self.eventos.append(dict(t=t_dec, tipo="rejeitada", texto="decisao zerar rejeitada: nao ha posicao"))
                return ["REJEITADA zerar: nao ha posicao"]
            if self.exit_pend:
                return ["zerar ignorado: saida limitada ja pendente"]
            last = float(d.m15[k, 3])
            px = float(_tick_alto(last) if self.pos["dir"] > 0 else _tick_baixo(last))
            self.exit_pend = dict(preco=px, last_k=k + VALIDADE_SAIDA, k_dec=k)
            self.zerar_pedidos += 1
            self.eventos.append(dict(t=t_dec, tipo="zerar_limite", texto=f"zerar LIMITADO: saida limite {px:.0f} valida {VALIDADE_SAIDA} velas"))
            return []
        return super().aplicar(dec, k)

    def simular_barra(self, k):
        if self.exit_pend and k > self.exit_pend["last_k"]:
            self.eventos.append(dict(t=_hm(self.dia.m15_t[k]), tipo="expirada", texto="saida limitada expirou sem encher (stop segue)"))
            self.exit_pend = None
        super().simular_barra(k)

    def _m1(self, i, k):
        super()._m1(i, k)
        if self.exit_pend and self.pos and not self.encerrada and i < self.dia.flat_i:
            p, e = self.pos, self.exit_pend
            _, h, l, _ = self.dia.m1[i]
            if k > e["k_dec"] and ((h >= e["preco"] + self.fill) if p["dir"] > 0 else (l <= e["preco"] - self.fill)):
                self._sai(i, k, e["preco"], "zerar (limite)")

    def _sai(self, i, k, preco, motivo):
        self.exit_pend = None
        return super()._sai(i, k, preco, motivo)
