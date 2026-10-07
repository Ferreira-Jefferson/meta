//+------------------------------------------------------------------+
//| Qullamaggie.mq5                                                  |
//| Expert Advisor das 3 configuracoes de Kristjan Kullamagi:        |
//|   1) Breakout  2) Episodic Pivot  3) Parabolic Short             |
//| Roda em grafico D1 (qualquer ativo B3: acao, ETF, indice, cripto)|
//|                                                                  |
//| Decide so' na ABERTURA de cada candle D1, com barras FECHADAS    |
//| (sem look-ahead). Toda a logica de sinal esta' em                |
//| QullamaggieLib.mqh (funcoes puras, espelho do qm_core.py).       |
//|                                                                  |
//| Aproximacao do original (que e' intradiario): o ORH vira ordem   |
//| buy-stop no rompimento da maxima da consolidacao, e a "minima do |
//| dia" vira a minima das ultimas InpStopBars barras.               |
//| Short so' roda se o simbolo permitir venda (aluguel de acoes).   |
//+------------------------------------------------------------------+
#property copyright "meta"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>
#include "QullamaggieLib.mqh"

//--- setups
input bool   InpBreakout      = true;    // Setup 1: Breakout
input bool   InpEpisodic      = false;   // Setup 2: Episodic Pivot
input bool   InpParabolic     = false;   // Setup 3: Parabolic Short (venda)
//--- universo
input double InpMinPrice      = 3.0;     // Preco minimo (R$)
input double InpMinDollarVol  = 5000000; // Volume financeiro medio 20d minimo (R$)
input double InpAdrMin        = 0.04;    // ADR20 minimo (0.04 = 4%)
//--- breakout
input int    InpPriorMoveBars = 63;      // Janela da alta previa (barras)
input double InpPriorMoveMin  = 0.30;    // Alta previa minima (30%)
input int    InpConsolBars    = 10;      // Barras da consolidacao
input double InpMaxDepth      = 0.35;    // Profundidade maxima da consolidacao
input double InpTightRatio    = 1.0;     // Range recente / range da consolidacao (<=)
input int    InpStopBars      = 2;       // Stop = minima das ultimas N barras
input double InpStopAdrMax    = 1.0;     // Stop nao mais largo que X*ADR
//--- gestao
input int    InpPartialDays   = 3;       // Realiza parcial apos N pregoes
input double InpPartialFrac   = 0.3333;  // Fracao vendida na parcial
input int    InpTrailMa       = 10;      // Trailing: 1o fechamento abaixo da SMA(N)
//--- EP
input double InpEpGap         = 0.10;    // Gap minimo
input int    InpEpNeglectBars = 63;      // Janela "dormente"
input double InpEpNeglectMax  = 0.20;    // Alta maxima na janela dormente
input double InpEpConfirm     = 0.0;     // Buy-stop em abertura*(1+x) (0 = a mercado)
input double InpEpStopAdr     = 1.0;     // Stop = abertura*(1 - x*ADR)
//--- parabolic
input int    InpParaUpDays    = 3;       // Altas seguidas
input int    InpParaWin       = 5;       // Janela da alta (barras)
input double InpParaMove      = 0.30;    // Alta minima na janela
input double InpParaConfirm   = 0.0;     // Sell-stop em abertura*(1-x)
input double InpParaStopAdr   = 1.0;     // Stop = entrada*(1 + x*ADR)
input int    InpParaTargetMa  = 10;      // Alvo: SMA(N)
input int    InpParaMaxHold   = 10;      // Maximo de pregoes
//--- conta
input double InpRiskPct       = 0.005;   // Risco por trade (% do patrimonio)
input double InpMaxPosPct     = 0.25;    // Teto por posicao (% do patrimonio)
input double InpLot           = 0;       // Lote (0 = passo do simbolo)
input long   InpMagic         = 770001;  // Magic
input bool   InpExportTrades  = true;    // Exporta negocios p/ CSV (paridade)

CTrade   trade;
QmCfg    g_cfg;
datetime g_lastBar = 0;
string   g_gvPartial;
double   g_lotStep, g_lotMin, g_tick;
int      g_digits;

//+------------------------------------------------------------------+
void BuildCfg()
  {
   g_cfg.min_price = InpMinPrice;       g_cfg.min_dvol = InpMinDollarVol;  g_cfg.adr_min = InpAdrMin;
   g_cfg.pm_window = InpPriorMoveBars;  g_cfg.pm_min = InpPriorMoveMin;
   g_cfg.consol_bars = InpConsolBars;   g_cfg.max_depth = InpMaxDepth;
   g_cfg.tight_ratio = InpTightRatio;   g_cfg.stop_bars = InpStopBars;     g_cfg.stop_adr_max = InpStopAdrMax;
   g_cfg.partial_days = InpPartialDays; g_cfg.partial_frac = InpPartialFrac; g_cfg.trail_ma = InpTrailMa;
   g_cfg.ep_gap = InpEpGap;             g_cfg.ep_neglect_bars = InpEpNeglectBars;
   g_cfg.ep_neglect_max = InpEpNeglectMax; g_cfg.ep_confirm = InpEpConfirm; g_cfg.ep_stop_adr = InpEpStopAdr;
   g_cfg.para_up_days = InpParaUpDays;  g_cfg.para_win = InpParaWin;       g_cfg.para_move = InpParaMove;
   g_cfg.para_confirm = InpParaConfirm; g_cfg.para_stop_adr = InpParaStopAdr;
   g_cfg.para_target_ma = InpParaTargetMa; g_cfg.para_max_hold = InpParaMaxHold;
   g_cfg.risk_pct = InpRiskPct;         g_cfg.max_pos_pct = InpMaxPosPct;
  }

//--- carrega N barras D1 fechadas em arrays nao-serie ([n-1] = ultima fechada)
bool LoadBars(const int n, double &o[], double &h[], double &l[], double &c[], double &v[])
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   if(CopyRates(_Symbol, PERIOD_D1, 1, n, r) != n) return false;
   ArrayResize(o, n); ArrayResize(h, n); ArrayResize(l, n); ArrayResize(c, n); ArrayResize(v, n);
   for(int k = 0; k < n; k++)
     {
      o[k] = r[k].open; h[k] = r[k].high; l[k] = r[k].low; c[k] = r[k].close;
      v[k] = r[k].real_volume > 0 ? (double)r[k].real_volume : (double)r[k].tick_volume;
     }
   return true;
  }

double RoundTick(const double p, const bool up)
  {
   double t = p / g_tick;
   t = up ? MathCeil(t - 1e-9) : MathFloor(t + 1e-9);
   return NormalizeDouble(t * g_tick, g_digits);
  }

bool HavePosition(ENUM_POSITION_TYPE &type, double &vol, double &price, datetime &when, double &sl)
  {
   for(int k = PositionsTotal() - 1; k >= 0; k--)
     {
      ulong tk = PositionGetTicket(k);
      if(tk == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      type  = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      vol   = PositionGetDouble(POSITION_VOLUME);
      price = PositionGetDouble(POSITION_PRICE_OPEN);
      when  = (datetime)PositionGetInteger(POSITION_TIME);
      sl    = PositionGetDouble(POSITION_SL);
      return true;
     }
   return false;
  }

void CancelPendings()
  {
   for(int k = OrdersTotal() - 1; k >= 0; k--)
     {
      ulong tk = OrderGetTicket(k);
      if(tk == 0 || OrderGetString(ORDER_SYMBOL) != _Symbol ||
         OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      trade.OrderDelete(tk);
     }
  }

bool CanShort()
  {
   long m = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   return m == SYMBOL_TRADE_MODE_FULL || m == SYMBOL_TRADE_MODE_SHORTONLY;
  }

//--- coloca ordem de entrada: a mercado se o preco ja passou do gatilho (gap), senao stop
void PlaceEntry(const bool isBuy, const double level, const double stop, const string tag)
  {
   double entry = isBuy ? RoundTick(level, true) : RoundTick(level, false);
   double sl    = isBuy ? RoundTick(stop, false) : RoundTick(stop, true);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double vol = QmPositionSize(equity, entry, sl, g_cfg, g_lotStep, g_lotMin,
                               AccountInfoDouble(ACCOUNT_MARGIN_FREE));
   if(vol <= 0) return;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   datetime exp = 0;
   if(isBuy)
     {
      if(ask >= entry) trade.Buy(vol, _Symbol, 0, sl, 0, tag);
      else trade.BuyStop(vol, entry, _Symbol, sl, 0, ORDER_TIME_DAY, exp, tag);
     }
   else
     {
      if(bid <= entry) trade.Sell(vol, _Symbol, 0, sl, 0, tag);
      else trade.SellStop(vol, entry, _Symbol, sl, 0, ORDER_TIME_DAY, exp, tag);
     }
  }

//--- gestao da posicao aberta, executada na abertura (decisao no fechamento anterior)
void ManagePosition(const ENUM_POSITION_TYPE type, const double vol, const double price,
                    const datetime when, const double sl,
                    const double &c[], const double &h[], const double &l[], const int i,
                    const double openToday)
  {
   int held = iBarShift(_Symbol, PERIOD_D1, when, false);   // 0 = dia da entrada
   bool done = GlobalVariableCheck(g_gvPartial);
   if(type == POSITION_TYPE_BUY)
     {
      if(held >= InpPartialDays && QmTrailExit(c, i, InpTrailMa))
        { trade.PositionClose(_Symbol); return; }
      if(QmPartialDue(held, InpPartialDays, done))
        {
         double pv = QmPartialVolume(vol, InpPartialFrac, g_lotStep);
         if(pv > 0) trade.PositionClosePartial(_Symbol, pv);
         GlobalVariableSet(g_gvPartial, 1);
         double be = RoundTick(price, true);
         if(be > sl) trade.PositionModify(_Symbol, be, 0);     // stop no zero a zero
        }
     }
   else
     {
      double tgt = QmParaTarget(c, i, InpParaTargetMa);
      if(tgt != EMPTY_VALUE && openToday <= tgt) { trade.PositionClose(_Symbol); return; }
      if(held >= InpParaMaxHold) { trade.PositionClose(_Symbol); return; }
      if(tgt != EMPTY_VALUE) trade.PositionModify(_Symbol, sl, RoundTick(tgt, true));
     }
  }

//--- rotina da abertura de cada D1
void OnNewDay()
  {
   const int N = 300;
   double o[], h[], l[], c[], v[];
   if(!LoadBars(N, o, h, l, c, v)) return;
   const int i = N - 1;
   const double openToday = iOpen(_Symbol, PERIOD_D1, 0);
   CancelPendings();

   ENUM_POSITION_TYPE type; double vol, price, sl; datetime when;
   if(HavePosition(type, vol, price, when, sl))
     {
      ManagePosition(type, vol, price, when, sl, c, h, l, i, openToday);
      // saiu a mercado nesta abertura? libera nova entrada no mesmo pregao
      if(HavePosition(type, vol, price, when, sl)) return;
     }
   GlobalVariableDel(g_gvPartial);

   double level, stop;
   if(InpBreakout && QmBreakoutSetup(h, l, c, v, i, g_cfg, level, stop))
     { PlaceEntry(true, level, stop, "QM-BO"); return; }
   if(InpEpisodic && QmEpSetup(h, l, c, v, i, openToday, g_cfg, level, stop))
     { PlaceEntry(true, level, stop, "QM-EP"); return; }
   if(InpParabolic && CanShort() && QmParaSetup(h, l, c, v, i, openToday, g_cfg, level, stop))
      PlaceEntry(false, level, stop, "QM-PS");
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   BuildCfg();
   if(Period() != PERIOD_D1) { Print("Qullamaggie: use o grafico D1."); return INIT_FAILED; }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(50);
   g_tick  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   g_digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   g_lotStep = InpLot > 0 ? InpLot : SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   g_lotMin  = MathMax(g_lotStep, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));
   g_gvPartial = StringFormat("QM_P_%I64d_%s", InpMagic, _Symbol);
   if(!MQLInfoInteger(MQL_TESTER)) GlobalVariableDel(g_gvPartial);
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   datetime bar = iTime(_Symbol, PERIOD_D1, 0);
   if(bar == g_lastBar) return;
   g_lastBar = bar;
   OnNewDay();
  }

//--- exporta os negocios (entrada/saida) p/ conferir contra o simulador Python
void OnDeinit(const int reason)
  {
   if(!InpExportTrades) return;
   if(!HistorySelect(0, TimeCurrent())) return;
   int fh = FileOpen("qm_trades_" + _Symbol + ".csv", FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ';');
   if(fh == INVALID_HANDLE) return;
   FileWrite(fh, "time", "type", "entry", "price", "volume", "profit", "comment");
   for(int k = 0; k < HistoryDealsTotal(); k++)
     {
      ulong tk = HistoryDealGetTicket(k);
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol ||
         HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      FileWrite(fh, TimeToString((datetime)HistoryDealGetInteger(tk, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                (long)HistoryDealGetInteger(tk, DEAL_TYPE), (long)HistoryDealGetInteger(tk, DEAL_ENTRY),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_PRICE), g_digits),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_VOLUME), 2),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_PROFIT), 2),
                HistoryDealGetString(tk, DEAL_COMMENT));
     }
   FileClose(fh);
  }
//+------------------------------------------------------------------+
