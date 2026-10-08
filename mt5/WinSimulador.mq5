//+------------------------------------------------------------------+
//| WinSimulador.mq5                                                 |
//| Simulador de operacao MANUAL para o Testador de Estrategia em    |
//| modo visual: botoes COMPRA / VENDA / ZERAR no grafico, com       |
//| atraso de envio e deslize de preco sorteados para chegar perto   |
//| da execucao real.                                                |
//|                                                                  |
//| v1.00 (2026-10-07).                                              |
//|                                                                  |
//| COMO USAR                                                        |
//|  Testador -> Expert: WinSimulador, simbolo WIN$N, modelagem      |
//|  "Cada tick baseado em ticks reais", Visualizacao LIGADA.        |
//|  Clique nos botoes do grafico visual. Lote/stop/alvo podem ser   |
//|  editados nos campos do grafico a qualquer momento.              |
//|                                                                  |
//| O QUE E' SIMULADO (so' dentro do Testador; em conta real/demo o  |
//| mercado ja' faz isso sozinho e o EA so' manda a ordem)           |
//|  - ATRASO: entre o clique e a execucao passa um tempo sorteado   |
//|    (AtrasoMinMs..AtrasoMaxMs; com chance ProbPico, um pico de    |
//|    PicoMinMs..PicoMaxMs). A ordem sai no preco do mercado DEPOIS |
//|    do atraso, medido no relogio em ms dos ticks reais - entao o  |
//|    preco anda contra ou a favor naturalmente.                    |
//|  - DESLIZE: com chance ProbDeslize* (padrao 1 em 3) a execucao   |
//|    sai 1..DeslizeMaxTicks ticks PIOR (1 tick e' o mais comum).   |
//|    O Testador nao deixa executar fora do preco do tick, entao o  |
//|    deslize e' cobrado como SAQUE do saldo (TesterWithdrawal) no  |
//|    instante da execucao: o saldo e a curva ficam com o custo,    |
//|    e o relatorio mostra os saques separados das operacoes.       |
//|  - STOP e ALVO ficam no servidor (sl/tp da posicao): saem sem    |
//|    atraso, mas cada um pode deslizar com a sua probabilidade.    |
//|    Alvo como tp nativo desliza de verdade na B3 (WDO medido:     |
//|    10 de 11 sairam 1 tick pior).                                 |
//|                                                                  |
//| Conta NETTING (Rico/Clear): VENDA com posicao comprada reduz ou  |
//| vira a mao, como no pregao real.                                 |
//+------------------------------------------------------------------+
#property copyright "WinSimulador"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input double Lote               = 1;      // Contratos por clique (editavel no grafico)
input double StopPts            = 300;    // Stop em pontos a partir do preco medio (0 = sem stop)
input double AlvoPts            = 0;      // Alvo em pontos a partir do preco medio (0 = sem alvo)
input int    AtrasoMinMs        = 50;     // Atraso normal minimo entre clique e execucao (ms)
input int    AtrasoMaxMs        = 300;    // Atraso normal maximo (ms)
input double ProbPico           = 0.05;   // Chance de um pico de atraso (rede/corretora lenta)
input int    PicoMinMs          = 500;    // Pico minimo (ms)
input int    PicoMaxMs          = 1500;   // Pico maximo (ms)
input double ProbDeslizeMercado = 0.3333; // Chance de deslize na COMPRA/VENDA/ZERAR (1 em 3)
input double ProbDeslizeStop    = 0.3333; // Chance de deslize quando o STOP executa
input double ProbDeslizeAlvo    = 0.3333; // Chance de deslize quando o ALVO executa
input int    DeslizeMaxTicks    = 3;      // Deslize maximo em ticks (sorteio favorece 1 tick)
input int    Semente            = 0;      // Semente do sorteio (0 = diferente a cada teste)
input ulong  MagicNumber        = 80100701; // Codigo que identifica as ordens deste EA

#define BTN_C  "SIM_BTN_COMPRA"
#define BTN_V  "SIM_BTN_VENDA"
#define BTN_Z  "SIM_BTN_ZERAR"
#define ED_L   "SIM_ED_LOTE"
#define ED_S   "SIM_ED_STOP"
#define ED_A   "SIM_ED_ALVO"
#define LB_L   "SIM_LB_LOTE"
#define LB_S   "SIM_LB_STOP"
#define LB_A   "SIM_LB_ALVO"

CTrade   trade;
bool     g_tester       = false;

int      g_pend         = 0;      // ordem em transito: 1 compra, -1 venda, 2 zerar, 0 nenhuma
long     g_pend_req_msc = 0;      // instante do clique (ms do tick)
long     g_pend_exe_msc = 0;      // instante em que a ordem "chega" (ms do tick)
double   g_pend_ref     = 0;      // preco na tela no clique
int      g_pend_atraso  = 0;

double   g_custo_desl   = 0;      // R$ cobrados de deslize
int      g_n_desl       = 0;
int      g_n_exec       = 0;
string   g_ultimo       = "";

//+------------------------------------------------------------------+
double Rand01() { return MathRand() / 32768.0; }

int RandInt(int a, int b)
{
   if(b <= a) return a;
   return a + (int)MathFloor(Rand01() * (b - a + 1));
}

int SorteiaAtraso()
{
   if(Rand01() < ProbPico) return RandInt(PicoMinMs, PicoMaxMs);
   return RandInt(AtrasoMinMs, AtrasoMaxMs);
}

// 0 = sem deslize; senao 1..DeslizeMaxTicks, com u^2 puxando para 1 tick
int SorteiaDeslize(double prob)
{
   if(DeslizeMaxTicks <= 0 || Rand01() >= prob) return 0;
   double u = Rand01();
   return 1 + (int)MathFloor(u * u * DeslizeMaxTicks);
}

double TickSize() { return SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE); }

double NormPreco(double p)
{
   double tk = TickSize();
   if(tk <= 0) return p;
   return NormalizeDouble(MathRound(p / tk) * tk, _Digits);
}

double NormVolume(double v)
{
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(st > 0) v = MathFloor(v / st + 1e-9) * st;
   if(v < mn) v = mn;
   if(mx > 0 && v > mx) v = mx;
   return v;
}

double LeCampo(string nome, double padrao)
{
   string s = ObjectGetString(0, nome, OBJPROP_TEXT);
   StringReplace(s, ",", ".");
   double v = StringToDouble(s);
   if(v < 0 || (v == 0 && StringFind(s, "0") < 0)) return padrao;
   return v;
}

//+------------------------------------------------------------------+
void CriaBotao(string nome, string texto, int x, int y, color fundo)
{
   ObjectCreate(0, nome, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, nome, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nome, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nome, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, nome, OBJPROP_XSIZE, 90);
   ObjectSetInteger(0, nome, OBJPROP_YSIZE, 32);
   ObjectSetString (0, nome, OBJPROP_TEXT, texto);
   ObjectSetString (0, nome, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, nome, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, clrWhite);
   ObjectSetInteger(0, nome, OBJPROP_BGCOLOR, fundo);
   ObjectSetInteger(0, nome, OBJPROP_STATE, false);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
}

void CriaCampo(string nome, string rotulo, string nomeRotulo, string valor, int x, int y)
{
   ObjectCreate(0, nomeRotulo, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_YDISTANCE, y + 18);
   ObjectSetString (0, nomeRotulo, OBJPROP_TEXT, rotulo);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_COLOR, clrSilver);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_SELECTABLE, false);

   ObjectCreate(0, nome, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, nome, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nome, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nome, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, nome, OBJPROP_XSIZE, 90);
   ObjectSetInteger(0, nome, OBJPROP_YSIZE, 20);
   ObjectSetString (0, nome, OBJPROP_TEXT, valor);
   ObjectSetInteger(0, nome, OBJPROP_ALIGN, ALIGN_CENTER);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, nome, OBJPROP_BGCOLOR, clrWhite);
   ObjectSetInteger(0, nome, OBJPROP_READONLY, false);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
}

//+------------------------------------------------------------------+
int OnInit()
{
   g_tester = (bool)MQLInfoInteger(MQL_TESTER);
   MathSrand(Semente > 0 ? Semente : (int)(GetTickCount() ^ (uint)TimeLocal()));
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(0);

   CriaBotao(BTN_C, "COMPRA", 10,  50, clrSeaGreen);
   CriaBotao(BTN_V, "VENDA",  105, 50, clrFireBrick);
   CriaBotao(BTN_Z, "ZERAR",  200, 50, clrDimGray);
   CriaCampo(ED_L, "lote",      LB_L, DoubleToString(Lote, 0),    10,  90);
   CriaCampo(ED_S, "stop pts",  LB_S, DoubleToString(StopPts, 0), 105, 90);
   CriaCampo(ED_A, "alvo pts",  LB_A, DoubleToString(AlvoPts, 0), 200, 90);
   ChartRedraw();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "SIM_");
   Comment("");
}

//+------------------------------------------------------------------+
bool Clicou(string nome)
{
   if(!ObjectGetInteger(0, nome, OBJPROP_STATE)) return false;
   ObjectSetInteger(0, nome, OBJPROP_STATE, false);
   return true;
}

void LeBotoes(const MqlTick &tk)
{
   int acao = 0;
   if(Clicou(BTN_C)) acao = 1;
   if(Clicou(BTN_V)) acao = (acao == 0 ? -1 : acao);
   if(Clicou(BTN_Z)) acao = (acao == 0 ? 2 : acao);
   if(acao == 0) return;
   ChartRedraw();

   if(g_pend != 0)
   {
      g_ultimo = "ordem anterior ainda em transito - clique ignorado";
      return;
   }
   g_pend_atraso  = g_tester ? SorteiaAtraso() : 0;
   g_pend         = acao;
   g_pend_req_msc = tk.time_msc;
   g_pend_exe_msc = tk.time_msc + g_pend_atraso;
   g_pend_ref     = (acao == 1 ? tk.ask : (acao == -1 ? tk.bid : 0));
   if(g_pend_atraso == 0) Executa(tk);
}

// Cobra o deslize como saque do saldo do Testador
void CobraDeslize(int ticks, double vol, string oque)
{
   double custo = ticks * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) * vol;
   if(g_tester) TesterWithdrawal(custo);
   g_custo_desl += custo;
   g_n_desl++;
   g_ultimo = g_ultimo + StringFormat("  | DESLIZE %d tick(s) = -R$%.2f", ticks, custo);
   PrintFormat("[SIM] %s deslizou %d tick(s): -R$%.2f", oque, ticks, custo);
}

// Re-ancora stop/alvo no preco medio da posicao depois de cada execucao
void AjustaNiveis()
{
   if(!PositionSelect(_Symbol)) return;
   double stop = LeCampo(ED_S, StopPts);
   double alvo = LeCampo(ED_A, AlvoPts);
   double pm   = PositionGetDouble(POSITION_PRICE_OPEN);
   bool   comp = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   double sl = 0, tp = 0;
   if(stop > 0) sl = NormPreco(comp ? pm - stop : pm + stop);
   if(alvo > 0) tp = NormPreco(comp ? pm + alvo : pm - alvo);
   if(!trade.PositionModify(_Symbol, sl, tp))
      g_ultimo = g_ultimo + "  | stop/alvo recusado: " + trade.ResultRetcodeDescription();
}

double PrecoDoNegocio()
{
   ulong d = trade.ResultDeal();
   if(d > 0 && HistoryDealSelect(d)) return HistoryDealGetDouble(d, DEAL_PRICE);
   return trade.ResultPrice();
}

void Executa(const MqlTick &tk)
{
   int acao = g_pend;
   g_pend = 0;
   double vol;
   string tag;
   bool ok;

   if(acao == 2)
   {
      if(!PositionSelect(_Symbol)) { g_ultimo = "ZERAR: sem posicao"; return; }
      vol = PositionGetDouble(POSITION_VOLUME);
      tag = "ZERAR";
      ok  = trade.PositionClose(_Symbol);
   }
   else
   {
      vol = NormVolume(LeCampo(ED_L, Lote));
      tag = (acao == 1 ? "COMPRA" : "VENDA");
      ok  = (acao == 1 ? trade.Buy(vol, _Symbol) : trade.Sell(vol, _Symbol));
   }
   if(!ok)
   {
      g_ultimo = tag + " recusada: " + trade.ResultRetcodeDescription();
      return;
   }
   g_n_exec++;

   double preco = PrecoDoNegocio();
   string mov = "";
   if(g_pend_ref > 0)
   {
      double d = (acao == 1 ? preco - g_pend_ref : g_pend_ref - preco);  // >0 = pior
      mov = StringFormat(", tela %s, atraso custou %+.0f pts", DoubleToString(g_pend_ref, _Digits), -d);
   }
   g_ultimo = StringFormat("%s %.0f @ %s (atraso %d ms%s)", tag, vol,
                           DoubleToString(preco, _Digits), g_pend_atraso, mov);

   if(acao != 2) AjustaNiveis();

   int desl = g_tester ? SorteiaDeslize(ProbDeslizeMercado) : 0;
   if(desl > 0) CobraDeslize(desl, vol, tag);
}

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &t,
                        const MqlTradeRequest &req,
                        const MqlTradeResult &res)
{
   if(!g_tester || t.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(t.deal)) return;
   if(HistoryDealGetString(t.deal, DEAL_SYMBOL) != _Symbol) return;

   long   motivo = HistoryDealGetInteger(t.deal, DEAL_REASON);
   double vol    = HistoryDealGetDouble(t.deal, DEAL_VOLUME);
   double preco  = HistoryDealGetDouble(t.deal, DEAL_PRICE);
   string tag;
   double prob;
   if(motivo == DEAL_REASON_SL)      { tag = "STOP"; prob = ProbDeslizeStop; }
   else if(motivo == DEAL_REASON_TP) { tag = "ALVO"; prob = ProbDeslizeAlvo; }
   else return;

   g_n_exec++;
   g_ultimo = StringFormat("%s executado %.0f @ %s", tag, vol, DoubleToString(preco, _Digits));
   int desl = SorteiaDeslize(prob);
   if(desl > 0) CobraDeslize(desl, vol, tag);
}

//+------------------------------------------------------------------+
void Painel(const MqlTick &tk)
{
   string pos = "ZERADO";
   double flut = 0;
   if(PositionSelect(_Symbol))
   {
      bool comp = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
      flut = PositionGetDouble(POSITION_PROFIT);
      pos = StringFormat("%s %.0f @ %s   stop %s   alvo %s",
                         comp ? "COMPRADO" : "VENDIDO",
                         PositionGetDouble(POSITION_VOLUME),
                         DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), _Digits),
                         DoubleToString(PositionGetDouble(POSITION_SL), _Digits),
                         DoubleToString(PositionGetDouble(POSITION_TP), _Digits));
   }
   string transito = "";
   if(g_pend != 0)
      transito = StringFormat("\n>>> ENVIANDO %s ... (%d ms)", g_pend == 1 ? "COMPRA" : (g_pend == -1 ? "VENDA" : "ZERAR"),
                              (int)(tk.time_msc - g_pend_req_msc));
   Comment(StringFormat(
      "WinSimulador%s\n"
      "%s   |   flutuante R$ %.2f\n"
      "saldo R$ %.2f   |   deslizes %d de %d execucoes = -R$ %.2f\n"
      "ultima: %s%s",
      g_tester ? "  (atraso e deslize simulados)" : "  (conta real/demo: sem simulacao)",
      pos, flut,
      AccountInfoDouble(ACCOUNT_BALANCE), g_n_desl, g_n_exec, g_custo_desl,
      g_ultimo, transito));
}

void OnTick()
{
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk)) return;
   LeBotoes(tk);
   if(g_pend != 0 && tk.time_msc >= g_pend_exe_msc) Executa(tk);
   Painel(tk);
}
//+------------------------------------------------------------------+
