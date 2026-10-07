//+------------------------------------------------------------------+
//| QullamaggieLib.mqh                                               |
//| Funcoes PURAS (sem ordem, sem estado, sem I/O) das 3 configuracoes|
//| de Kristjan Kullamagi (Qullamaggie): Breakout, Episodic Pivot e  |
//| Parabolic Short, em barras DIARIAS.                              |
//|                                                                  |
//| Espelho 1:1 de scripts/qullamaggie/qm_core.py - a matematica e'  |
//| a mesma, e qm_parity.py confere as duas contra o testador.       |
//|                                                                  |
//| Convencao de indice: arrays NAO-serie, [0] = barra mais antiga,  |
//| [i] = ultima barra FECHADA. Toda funcao usa so' barras <= i.     |
//+------------------------------------------------------------------+
#property strict

struct QmCfg
  {
   // universo
   double min_price;
   double min_dvol;
   double adr_min;
   // breakout
   int    pm_window;
   double pm_min;
   int    consol_bars;
   double max_depth;
   double tight_ratio;
   int    stop_bars;
   double stop_adr_max;
   // gestao
   int    partial_days;
   double partial_frac;
   int    trail_ma;
   // EP
   double ep_gap;
   int    ep_neglect_bars;
   double ep_neglect_max;
   double ep_confirm;
   double ep_stop_adr;
   // parabolic short
   int    para_up_days;
   int    para_win;
   double para_move;
   double para_confirm;
   double para_stop_adr;
   int    para_target_ma;
   int    para_max_hold;
   // conta
   double risk_pct;
   double max_pos_pct;
  };

//--- indicadores ----------------------------------------------------
double QmSma(const double &x[], const int i, const int n)
  {
   if(i - n + 1 < 0) return EMPTY_VALUE;
   double s = 0;
   for(int k = i - n + 1; k <= i; k++) s += x[k];
   return s / n;
  }

double QmMaxRange(const double &x[], const int i, const int n)
  {
   double m = x[i];
   for(int k = i - n + 1; k < i; k++) if(x[k] > m) m = x[k];
   return m;
  }

double QmMinRange(const double &x[], const int i, const int n)
  {
   double m = x[i];
   for(int k = i - n + 1; k < i; k++) if(x[k] < m) m = x[k];
   return m;
  }

//--- ADR% = media(h/l) - 1 em n barras (formula do TC2000 dele)
double QmAdr(const double &h[], const double &l[], const int i, const int n)
  {
   if(i - n + 1 < 0) return EMPTY_VALUE;
   double s = 0;
   for(int k = i - n + 1; k <= i; k++) s += h[k] / l[k];
   return s / n - 1.0;
  }

//--- media de close*volume em n barras (liquidez em R$)
double QmDollarVol(const double &c[], const double &v[], const int i, const int n)
  {
   if(i - n + 1 < 0) return EMPTY_VALUE;
   double s = 0;
   for(int k = i - n + 1; k <= i; k++) s += c[k] * v[k];
   return s / n;
  }

//--- maior alta "minima -> maxima posterior" na janela de `window` barras ate i
double QmPriorMoveUp(const double &h[], const double &l[], const int i, const int window)
  {
   if(i - window + 1 < 0) return EMPTY_VALUE;
   double runmin = l[i - window + 1], best = 0;
   for(int k = i - window + 1; k <= i; k++)
     {
      if(l[k] < runmin) runmin = l[k];
      double r = h[k] / runmin;
      if(k == i - window + 1 || r > best) best = r;
     }
   return best - 1.0;
  }

//--- universo: preco, liquidez e ADR minimos
bool QmUniverseOk(const double &h[], const double &l[], const double &c[], const double &v[],
                  const int i, const QmCfg &g)
  {
   if(i < 25) return false;
   double adr = QmAdr(h, l, i, 20), dv = QmDollarVol(c, v, i, 20);
   if(adr == EMPTY_VALUE || dv == EMPTY_VALUE) return false;
   return c[i] >= g.min_price && dv >= g.min_dvol && adr >= g.adr_min;
  }

//--- 1) BREAKOUT: avaliado no FECHAMENTO da barra i; a ordem buy-stop vale em i+1.
//    Devolve o gatilho (maxima da consolidacao) e o stop (minima das ultimas stop_bars).
bool QmBreakoutSetup(const double &h[], const double &l[], const double &c[], const double &v[],
                     const int i, const QmCfg &g, double &trigger, double &stop)
  {
   const int C = g.consol_bars, half = C / 2;
   if(C < 6 || i < MathMax(g.pm_window, MathMax(C, 25)) + 5) return false;
   if(!QmUniverseOk(h, l, c, v, i, g)) return false;
   if(QmPriorMoveUp(h, l, i, g.pm_window) < g.pm_min) return false;
   double hh = QmMaxRange(h, i, C), ll = QmMinRange(l, i, C);
   if((hh - ll) / hh > g.max_depth) return false;
   // minimas ascendentes: metade recente nao rompe a minima da primeira metade
   double ll_recent = QmMinRange(l, i, half);
   double ll_first  = QmMinRange(l, i - half, C - half);
   if(ll_recent < ll_first) return false;
   // range apertando: media (h-l)/c das ultimas 5 barras <= ratio * media da consolidacao
   double r5 = 0, rC = 0;
   for(int k = i - 4; k <= i; k++) r5 += (h[k] - l[k]) / c[k];
   for(int k = i - C + 1; k <= i; k++) rC += (h[k] - l[k]) / c[k];
   if(r5 / 5.0 > g.tight_ratio * rC / C) return false;
   // surfando a 10/20 SMA, com a 20 subindo
   double s10 = QmSma(c, i, 10), s20 = QmSma(c, i, 20), s20l = QmSma(c, i - 5, 20);
   if(!(c[i] > s10 && c[i] > s20 && s10 >= s20 && s20 > s20l)) return false;
   trigger = hh;
   stop = QmMinRange(l, i, g.stop_bars);
   double width = (trigger - stop) / trigger;
   if(!(width > 0 && width <= g.stop_adr_max * QmAdr(h, l, i, 20))) return false;
   return true;
  }

//--- 2) EPISODIC PIVOT: decidido na ABERTURA de hoje (open_today); i = ultima barra fechada.
//    O volume dos primeiros 15 min nao existe em candle diario e nao e' filtrado.
bool QmEpSetup(const double &h[], const double &l[], const double &c[], const double &v[],
               const int i, const double open_today, const QmCfg &g,
               double &level, double &stop)
  {
   if(i < g.ep_neglect_bars + 1) return false;
   if(!QmUniverseOk(h, l, c, v, i, g)) return false;
   if(open_today / c[i] - 1.0 < g.ep_gap) return false;
   if(c[i] / c[i - g.ep_neglect_bars] - 1.0 > g.ep_neglect_max) return false;   // ficou "dormente"
   level = open_today * (1.0 + g.ep_confirm);
   stop  = open_today * (1.0 - g.ep_stop_adr * QmAdr(h, l, i, 20));
   return true;
  }

//--- 3) PARABOLIC SHORT: decidido na abertura de hoje
bool QmParaSetup(const double &h[], const double &l[], const double &c[], const double &v[],
                 const int i, const double open_today, const QmCfg &g,
                 double &level, double &stop)
  {
   if(i < MathMax(g.para_up_days, g.para_win) + 21) return false;
   if(!QmUniverseOk(h, l, c, v, i, g)) return false;
   for(int k = 0; k < g.para_up_days; k++)
      if(!(c[i - k] > c[i - k - 1])) return false;                              // altas seguidas
   if(c[i] / c[i - g.para_win] - 1.0 < g.para_move) return false;              // parabolico
   level = open_today * (1.0 - g.para_confirm);
   stop  = level * (1.0 + g.para_stop_adr * QmAdr(h, l, i, 20));
   return true;
  }

//--- gestao ---------------------------------------------------------
//    Fechamento abaixo da SMA(trail_ma) na barra i => sai na abertura de i+1
bool QmTrailExit(const double &c[], const int i, const int trail_ma)
  {
   double ma = QmSma(c, i, trail_ma);
   return ma != EMPTY_VALUE && c[i] < ma;
  }

//    Parabolic short: alvo dinamico = SMA(para_target_ma) do ultimo fechamento
double QmParaTarget(const double &c[], const int i, const int ma)
  {
   return QmSma(c, i, ma);
  }

//    Quantas barras desde a barra de entrada (0 = dia da entrada)
bool QmPartialDue(const int held, const int partial_days, const bool already_done)
  {
   return held == partial_days && !already_done;
  }

//--- dimensionamento: risco fixo / distancia ate o stop, teto por posicao, em lotes
double QmPositionSize(const double equity, const double entry, const double stop,
                      const QmCfg &g, const double lot_step, const double lot_min,
                      const double free_cash)
  {
   double dist = MathAbs(entry - stop);
   if(dist <= 0 || entry <= 0) return 0;
   double notional = MathMin(equity * g.risk_pct * entry / dist, equity * g.max_pos_pct);
   notional = MathMin(notional, free_cash);
   double shares = MathFloor(notional / entry / lot_step) * lot_step;
   return shares >= lot_min ? shares : 0;
  }

//    Quanto vender na parcial (arredonda para baixo no lote; 0 = nao faz a parcial)
double QmPartialVolume(const double volume, const double frac, const double lot_step)
  {
   double v = MathFloor(volume * frac / lot_step) * lot_step;
   return (v >= lot_step && v < volume) ? v : 0;
  }
//+------------------------------------------------------------------+
