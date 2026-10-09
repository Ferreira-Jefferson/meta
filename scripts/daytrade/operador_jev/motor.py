"""Motor de execucao deterministico: a LLM decide, o motor executa. Simulacao em M1 dentro de cada vela M15.

Regras (padrao do projeto):
- entrada e alvo SEMPRE ordem limitada; so o stop e o 'zerar' saem a mercado.
- limite de compra enche se a minima de um M1 de vela SEGUINTE a decisao for <= preco - FILL_PTS (venda: espelho).
- stop a mercado no nivel; se o M1 abre alem do stop, sai na abertura. Alvo enche se passar FILL_PTS alem.
- stop e alvo no mesmo M1 -> stop (conservador). No M1 do preenchimento o alvo nao conta; o stop conta.
- custo: CUSTO_PTS por contrato por operacao (ida+volta). R$ = pts * 0,20 * contratos.
- 1 posicao por vez, max 2 contratos, zera no fim do pregao (flat_i).
- decisao tomada no fechamento da vela k so age a partir do 1o M1 da vela k+1 (sem look-ahead).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

FILL_PTS = 10.0
CUSTO_PTS = 10.0
VALOR_PT = 0.20
MAX_CONTRATOS = 2
TICK = 5.0


def _hm(t):
    return str(np.datetime64(t, "m"))[11:16]


def arredonda(p):
    return round(float(p) / TICK) * TICK


class Sessao:
    def __init__(self, dia, fill_pts=FILL_PTS, custo_pts=CUSTO_PTS):
        self.dia = dia
        self.fill = fill_pts
        self.custo = custo_pts
        self.pos = None
        self.pend = None
        self.zerar_prox = False
        self.eventos: list[dict] = []     # eventos estruturados
        self.trades: list[dict] = []
        self.ordens: list[dict] = []      # ciclo de vida de cada ordem (para o visualizador)
        self.pts = 0.0                    # pts-contrato liquidos
        self.brl = 0.0
        self.encerrada = False

    # ---------- estado visivel ao operador ----------
    def estado(self):
        return dict(pos=self.pos, pend=self.pend, pts=self.pts, brl=self.brl, ntrades=len(self.trades))

    def _ev(self, i, tipo, texto, **kw):
        t = _hm(self.dia.m1_t[i]) if i is not None else ""
        e = dict(t=t, tipo=tipo, texto=texto, **kw)
        self.eventos.append(e)
        return e

    def textos_eventos(self):
        return [f"{e['t']} {e['texto']}" for e in self.eventos]

    # ---------- decisoes (tomadas no fechamento da vela k) ----------
    def aplicar(self, dec: dict, k: int):
        """Valida e aplica a decisao. Retorna lista de mensagens (aceitas/rejeitadas)."""
        msgs = []
        d = self.dia
        t_dec = _hm(d.m15_t[k] + np.timedelta64(15, "m"))
        last = float(d.m15[k, 3])
        acao = dec.get("acao", "ficar_fora")

        def rej(motivo):
            msgs.append(f"REJEITADA {acao}: {motivo}")
            self.eventos.append(dict(t=t_dec, tipo="rejeitada", texto=f"decisao {acao} rejeitada: {motivo}"))

        if acao in ("manter",):
            return msgs
        if acao == "ficar_fora":
            if self.pend:
                self._cancela(k, t_dec, "ficar_fora (cancela ordem pendente)")
            return msgs
        if acao == "cancelar_ordem":
            if not self.pend:
                rej("nao ha ordem pendente")
            else:
                self._cancela(k, t_dec, "cancelada pelo operador")
            return msgs
        if acao == "zerar":
            if not self.pos:
                rej("nao ha posicao")
            else:
                self.zerar_prox = True
                self.eventos.append(dict(t=t_dec, tipo="zerar_pedido", texto="zerar: sai a mercado na abertura da proxima vela M1"))
            return msgs
        if acao == "mover_stop":
            if not self.pos:
                rej("nao ha posicao")
                return msgs
            novo = dec.get("novo_stop")
            if novo is None:
                rej("novo_stop ausente")
                return msgs
            novo = arredonda(novo)
            p = self.pos
            if p["dir"] > 0 and not (p["stop"] < novo < last):
                rej(f"stop de compra deve subir (atual {p['stop']:.0f}) e ficar abaixo do ultimo fechamento {last:.0f}")
                return msgs
            if p["dir"] < 0 and not (last < novo < p["stop"]):
                rej(f"stop de venda deve descer (atual {p['stop']:.0f}) e ficar acima do ultimo fechamento {last:.0f}")
                return msgs
            p["stop"] = novo
            p["stops"].append(dict(k=k + 1, valor=novo))
            self.eventos.append(dict(t=t_dec, tipo="stop_mov", texto=f"stop movido para {novo:.0f}"))
            return msgs
        if acao in ("comprar_limite", "vender_limite"):
            if self.pos:
                rej("ja ha posicao (1 por vez)")
                return msgs
            dirn = 1 if acao == "comprar_limite" else -1
            try:
                preco = arredonda(dec["preco"])
                stop = arredonda(dec["stop"])
            except Exception:
                rej("preco/stop ausentes")
                return msgs
            alvo = dec.get("alvo")
            alvo = arredonda(alvo) if alvo else None
            n = int(dec.get("contratos") or 1)
            n = max(1, min(MAX_CONTRATOS, n))
            val = int(dec.get("validade_velas") or 1)
            val = max(1, min(4, val))
            if dirn > 0 and preco > last:
                rej(f"compra limite {preco:.0f} acima do ultimo fechamento {last:.0f} seria ordem a mercado")
                return msgs
            if dirn < 0 and preco < last:
                rej(f"venda limite {preco:.0f} abaixo do ultimo fechamento {last:.0f} seria ordem a mercado")
                return msgs
            if (stop - preco) * dirn >= 0:
                rej("stop do lado errado do preco")
                return msgs
            if alvo is not None and (alvo - preco) * dirn <= 0:
                rej("alvo do lado errado do preco")
                return msgs
            if self.pend:
                self._cancela(k, t_dec, "substituida por nova ordem")
            self.pend = dict(lado="compra" if dirn > 0 else "venda", dir=dirn, preco=preco, stop=stop, alvo=alvo, n=n,
                             k_dec=k, last_k=k + val, validade=val, trail=bool(dec.get("trail")))
            self.ordens.append(dict(lado=self.pend["lado"], preco=preco, stop=stop, alvo=alvo, n=n, k_dec=k,
                                    validade=val, t=t_dec, estado="pendente", k_fim=None, fill=None, exit=None,
                                    stops=[], pts=None, brl=None, trail=bool(dec.get("trail"))))
            self.eventos.append(dict(t=t_dec, tipo="ordem", texto=f"ordem {self.pend['lado']} limite {preco:.0f} x{n} stop {stop:.0f} alvo {alvo if alvo else '-'} validade {val} vela(s)"))
            return msgs
        rej("acao desconhecida")
        return msgs

    def _cancela(self, k, t, motivo):
        o = self.ordens[-1]
        o["estado"] = "cancelada"
        o["k_fim"] = k
        self.eventos.append(dict(t=t, tipo="cancelada", texto=f"ordem cancelada ({motivo})"))
        self.pend = None

    # ---------- simulacao ----------
    def simular_barra(self, k: int):
        d = self.dia
        if self.pend and k > self.pend["last_k"]:
            o = self.ordens[-1]
            o["estado"] = "expirada"
            o["k_fim"] = self.pend["last_k"]
            self.eventos.append(dict(t=_hm(d.m15_t[k]), tipo="expirada", texto="ordem expirou sem preencher"))
            self.pend = None
        for i in range(int(d.m1_ini[k]), int(d.m1_fim[k])):
            if self.encerrada:
                return
            self._m1(i, k)

    def _m1(self, i, k):
        d = self.dia
        o, h, l, c = d.m1[i]
        if i > d.flat_i:
            self.encerrada = True
            return
        if self.zerar_prox and self.pos:
            self._sai(i, k, o, "zerar (mercado)")
            self.zerar_prox = False
        if self.pos:
            self._checa_saida(i, k, o, h, l)
        elif self.pend and i < d.flat_i:
            p = self.pend
            cruzou = (l <= p["preco"] - self.fill) if p["dir"] > 0 else (h >= p["preco"] + self.fill)
            if cruzou:
                self.pos = dict(lado=p["lado"], dir=p["dir"], n=p["n"], preco=p["preco"], stop=p["stop"], alvo=p["alvo"],
                                k_ent=k, i_ent=i, stops=[dict(k=k, valor=p["stop"])], trail=p.get("trail", False))
                od = self.ordens[-1]
                od["estado"] = "preenchida"
                od["k_fim"] = k
                od["fill"] = dict(k=k, t=_hm(d.m1_t[i]), preco=p["preco"])
                od["stops"] = self.pos["stops"]
                self.pend = None
                self.eventos.append(dict(t=_hm(d.m1_t[i]), tipo="fill", texto=f"{p['lado']} preenchida a {p['preco']:.0f} x{p['n']}"))
                # no M1 do preenchimento so o stop conta (conservador)
                if (self.pos["dir"] > 0 and l <= self.pos["stop"]) or (self.pos["dir"] < 0 and h >= self.pos["stop"]):
                    self._sai(i, k, self.pos["stop"], "stop")
        if i == d.flat_i:
            if self.pos:
                self._sai(i, k, c, "fim do pregao (zerar)")
            if self.pend:
                self._cancela(k, _hm(d.m1_t[i]), "fim do pregao")
            self.encerrada = True

    def _checa_saida(self, i, k, o, h, l):
        p = self.pos
        if p["dir"] > 0:
            if o <= p["stop"]:
                return self._sai(i, k, o, "stop (gap na abertura)")
            if l <= p["stop"]:
                return self._sai(i, k, p["stop"], "stop")
            if p["alvo"] and h >= p["alvo"] + self.fill:
                return self._sai(i, k, p["alvo"], "alvo")
        else:
            if o >= p["stop"]:
                return self._sai(i, k, o, "stop (gap na abertura)")
            if h >= p["stop"]:
                return self._sai(i, k, p["stop"], "stop")
            if p["alvo"] and l <= p["alvo"] - self.fill:
                return self._sai(i, k, p["alvo"], "alvo")

    def _sai(self, i, k, preco, motivo):
        p = self.pos
        bruto = (preco - p["preco"]) * p["dir"]
        liq = bruto - self.custo
        brl = liq * p["n"] * VALOR_PT
        d = self.dia
        t = _hm(d.m1_t[i])
        self.pts += liq * p["n"]
        self.brl += brl
        tr = dict(lado=p["lado"], n=p["n"], t_ent=_hm(d.m1_t[p["i_ent"]]), preco_ent=p["preco"], t_sai=t,
                  preco_sai=float(preco), motivo=motivo, pts_bruto=bruto, pts_liq=liq, brl=brl,
                  stop_ini=p["stops"][0]["valor"], alvo=p["alvo"], k_ent=p["k_ent"], k_sai=k)
        self.trades.append(tr)
        od = self.ordens[-1]
        od["exit"] = dict(k=k, t=t, preco=float(preco), motivo=motivo)
        od["pts"] = liq
        od["brl"] = brl
        self.eventos.append(dict(t=t, tipo="saida", texto=f"saida {motivo} a {preco:.0f}: {bruto:+.0f} pts bruto, {liq:+.0f} pts liquido/contrato, R$ {brl:+.2f}"))
        self.pos = None


def decisao_padrao(acao="ficar_fora", **kw):
    return dict(acao=acao, **kw)


def run_dia(mk, dia, decidir, hora_ini="09:15", hora_fim="17:30", on_ponto=None):
    """Roda um dia. decidir(pacote_fn, k, sessao) -> dict de decisao (ou levanta Abortar).

    on_ponto(ponto) recebe cada ponto de decisao (para log). Retorna Sessao e lista de pontos.
    """
    from mercado import montar_pacote
    s = Sessao(dia)
    pontos = []
    decisoes_txt = []
    n = len(dia.m15_t)
    abortado = False
    for k in range(n):
        s.simular_barra(k)
        if s.encerrada:
            break
        t_fech = _hm(dia.m15_t[k] + np.timedelta64(15, "m"))
        # nao decide depois do limite (nem depois do flat)
        fim_ok = t_fech <= hora_fim
        if not (hora_ini <= t_fech and fim_ok) or abortado:
            continue
        if int(dia.m1_fim[k]) > dia.flat_i + 1 or k == n - 1:
            continue
        pacote_fn = lambda k=k: montar_pacote(mk, dia, k, s.estado(), s.textos_eventos(), decisoes_txt)
        try:
            dec, meta = decidir(pacote_fn, k, s)
        except Abortar as e:
            abortado = True
            dec, meta = decisao_padrao("ficar_fora"), dict(falha=str(e), abortado=True)
        n_ev = len(s.eventos)
        msgs = s.aplicar(dec, k)
        pt = dict(k=k, t=t_fech, decisao=dec, meta=meta, msgs=msgs, eventos_aplicacao=s.eventos[n_ev:],
                  pos_antes=bool(s.pos), pend_depois=bool(s.pend))
        pontos.append(pt)
        r = (dec.get("raciocinio") or "")[:160].replace("\n", " ")
        par = ""
        if dec.get("acao") in ("comprar_limite", "vender_limite"):
            par = f" {dec.get('preco')} stop {dec.get('stop')} alvo {dec.get('alvo')}"
        decisoes_txt.append(f"{t_fech} {dec.get('acao')}{par} (conf {dec.get('confianca')}): {r}")
        if on_ponto:
            on_ponto(pt)
    return s, pontos


class Abortar(Exception):
    pass
