//+------------------------------------------------------------------+
//| WinSimulador.mq5                                                 |
//| Simulador de operacao MANUAL para o Testador de Estrategia em    |
//| modo visual: botoes COMPRA / VENDA / ZERAR no grafico, com       |
//| atraso de envio e deslize de preco sorteados para chegar perto   |
//| da execucao real.                                                |
//|                                                                  |
//| v1.00 (2026-10-07).                                              |
//| v1.01 (2026-10-07):                                              |
//|  - stop/alvo ficavam ZERADOS e o preco saia "@ 0": em ativo de   |
//|    bolsa a ordem e' so' COLOCADA no envio e executa no tick      |
//|    seguinte, entao a posicao ainda nao existia quando o EA ia    |
//|    por o stop. Agora preco, stop/alvo e deslize sao tratados     |
//|    quando o NEGOCIO acontece (OnTradeTransaction), e o stop/alvo |
//|    e' conferido de novo a cada tick ate' pegar.                  |
//|  - lote/stop/alvo ajustados por botoes - / + (o campo de texto   |
//|    perdia o valor no grafico do Testador ao clicar no vizinho);  |
//|    stop/alvo novos valem na hora para a posicao aberta.          |
//|                                                                  |
//| COMO USAR                                                        |
//|  Testador -> Expert: WinSimulador, simbolo WIN$N, modelagem      |
//|  "Cada tick baseado em ticks reais", Visualizacao LIGADA.        |
//|  Clique nos botoes do grafico visual. Lote/stop/alvo sao         |
//|  ajustados nos botoes - / + a qualquer momento.                  |
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
#property version   "1.01"

#include <Trade\Trade.mqh>

input double Lote               = 1;      // Contratos por clique (ajustavel no grafico)
input double StopPts            = 300;    // Stop em pontos a partir do preco medio (0 = sem stop)
input double AlvoPts            = 0;      // Alvo em pontos a partir do preco medio (0 = sem alvo)
input double PassoPts           = 50;     // Quanto cada clique em - / + muda o stop/alvo (pontos)
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
#define BT_LM  "SIM_BT_LOTE_MENOS"
#define BT_LP  "SIM_BT_LOTE_MAIS"
#define BT_SM  "SIM_BT_STOP_MENOS"
#define BT_SP  "SIM_BT_STOP_MAIS"
#define BT_AM  "SIM_BT_ALVO_MENOS"
#define BT_AP  "SIM_BT_ALVO_MAIS"

CTrade   trade;
bool     g_tester       = false;

// Valores vigentes de lote/stop/alvo. Ficam no EA, nao no texto do campo:
// no grafico do Testador o OBJ_EDIT perdia o valor ao clicar no campo vizinho.
double   g_lote         = 0;
double   g_stop         = 0;
double   g_alvo         = 0;

int      g_pend         = 0;      // ordem em transito: 1 compra, -1 venda, 2 zerar, 0 nenhuma
long     g_pend_req_msc = 0;      // instante do clique (ms do tick)
long     g_pend_exe_msc = 0;      // instante em que a ordem "chega" (ms do tick)
double   g_pend_ref     = 0;      // preco na tela no clique
int      g_pend_atraso  = 0;

// Ordem ja' enviada, esperando o negocio (em bolsa ela executa no tick seguinte)
int      g_env_acao     = 0;
double   g_env_ref      = 0;
int      g_env_atraso   = 0;
bool     g_reancorar    = false;  // conferir stop/alvo da posicao no proximo tick
string   g_ult_modif    = "";     // ultimo sl/tp que a corretora recusou (evita repetir a cada tick)

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

string NomeAcao(int acao) { return acao == 1 ? "COMPRA" : (acao == -1 ? "VENDA" : "ZERAR"); }

//+------------------------------------------------------------------+
void CriaBotao(string nome, string texto, int x, int y, color fundo, int w = 90, int h = 32)
{
   ObjectCreate(0, nome, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, nome, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nome, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nome, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, nome, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, nome, OBJPROP_YSIZE, h);
   ObjectSetString (0, nome, OBJPROP_TEXT, texto);
   ObjectSetString (0, nome, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, nome, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, clrWhite);
   ObjectSetInteger(0, nome, OBJPROP_BGCOLOR, fundo);
   ObjectSetInteger(0, nome, OBJPROP_STATE, false);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
}

// Campo so' de exibicao, com botoes - / + dos lados
void CriaCampo(string nome, string rotulo, string nomeRotulo, string btMenos, string btMais, int x, int y)
{
   ObjectCreate(0, nomeRotulo, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_YDISTANCE, y + 18);
   ObjectSetString (0, nomeRotulo, OBJPROP_TEXT, rotulo);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_COLOR, clrSilver);
   ObjectSetInteger(0, nomeRotulo, OBJPROP_SELECTABLE, false);

   CriaBotao(btMenos, "-", x, y, clrDimGray, 22, 20);

   ObjectCreate(0, nome, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, nome, OBJPROP_CORNER, CORNER_LEFT_LOWER);
   ObjectSetInteger(0, nome, OBJPROP_XDISTANCE, x + 22);
   ObjectSetInteger(0, nome, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, nome, OBJPROP_XSIZE, 46);
   ObjectSetInteger(0, nome, OBJPROP_YSIZE, 20);
   ObjectSetInteger(0, nome, OBJPROP_ALIGN, ALIGN_CENTER);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, nome, OBJPROP_BGCOLOR, clrWhite);
   ObjectSetInteger(0, nome, OBJPROP_READONLY, true);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);

   CriaBotao(btMais, "+", x + 68, y, clrDimGray, 22, 20);
}

void MostraCampos()
{
   ObjectSetString(0, ED_L, OBJPROP_TEXT, DoubleToString(g_lote, 0));
   ObjectSetString(0, ED_S, OBJPROP_TEXT, g_stop > 0 ? DoubleToString(g_stop, 0) : "sem");
   ObjectSetString(0, ED_A, OBJPROP_TEXT, g_alvo > 0 ? DoubleToString(g_alvo, 0) : "sem");
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
   CriaCampo(ED_L, "lote",      LB_L, BT_LM, BT_LP, 10,  90);
   CriaCampo(ED_S, "stop pts",  LB_S, BT_SM, BT_SP, 105, 90);
   CriaCampo(ED_A, "alvo pts",  LB_A, BT_AM, BT_AP, 200, 90);

   g_lote = NormVolume(Lote);
   g_stop = MathMax(0, StopPts);
   g_alvo = MathMax(0, AlvoPts);
   MostraCampos();
   ChartRedraw();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_tester)   // no Testador as setas dos negocios ficam no grafico para revisar o teste
   {
      ObjectsDeleteAll(0, "SIM_BT");
      ObjectsDeleteAll(0, "SIM_ED_");
      ObjectsDeleteAll(0, "SIM_LB_");
      ObjectsDeleteAll(0, "SIM_HL_");
   }
   else ObjectsDeleteAll(0, "SIM_");
   Comment("");
}

//+------------------------------------------------------------------+
bool Clicou(string nome)
{
   if(!ObjectGetInteger(0, nome, OBJPROP_STATE)) return false;
   ObjectSetInteger(0, nome, OBJPROP_STATE, false);
   return true;
}

void LeAjustes()
{
   double passoLote = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(passoLote <= 0) passoLote = 1;
   bool mudouLote = false, mudouNiveis = false;
   if(Clicou(BT_LM)) { g_lote = NormVolume(g_lote - passoLote); mudouLote = true; }
   if(Clicou(BT_LP)) { g_lote = NormVolume(g_lote + passoLote); mudouLote = true; }
   if(Clicou(BT_SM)) { g_stop = MathMax(0, g_stop - PassoPts);  mudouNiveis = true; }
   if(Clicou(BT_SP)) { g_stop += PassoPts;                      mudouNiveis = true; }
   if(Clicou(BT_AM)) { g_alvo = MathMax(0, g_alvo - PassoPts);  mudouNiveis = true; }
   if(Clicou(BT_AP)) { g_alvo += PassoPts;                      mudouNiveis = true; }
   if(!mudouLote && !mudouNiveis) return;
   MostraCampos();
   ChartRedraw();
   if(mudouNiveis) g_reancorar = true;
}

void LeBotoes(const MqlTick &tk)
{
   int acao = 0;
   if(Clicou(BTN_C)) acao = 1;
   if(Clicou(BTN_V)) acao = (acao == 0 ? -1 : acao);
   if(Clicou(BTN_Z)) acao = (acao == 0 ? 2 : acao);
   if(acao == 0) return;
   ChartRedraw();

   if(g_pend != 0 || g_env_acao != 0)
   {
      g_ultimo = "ordem anterior ainda em transito - clique ignorado";
      return;
   }
   g_pend_atraso  = g_tester ? SorteiaAtraso() : 0;
   g_pend         = acao;
   g_pend_req_msc = tk.time_msc;
   g_pend_exe_msc = tk.time_msc + g_pend_atraso;
   g_pend_ref     = (acao == 1 ? tk.ask : (acao == -1 ? tk.bid : 0));
   if(acao == 2 && PositionSelect(_Symbol))   // zerar comprado vende no bid, vendido compra no ask
      g_pend_ref = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? tk.bid : tk.ask);
   if(g_pend_atraso == 0) Envia();
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

// Ancora stop/alvo no preco medio da posicao. Chamado a cada tick enquanto
// g_reancorar estiver ligado: depois de cada execucao e quando stop/alvo mudam.
void AjustaNiveis()
{
   if(!PositionSelect(_Symbol)) return;          // posicao ainda nao existe ou ja' zerou
   g_reancorar = false;
   double pm   = PositionGetDouble(POSITION_PRICE_OPEN);
   bool   comp = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   double sl = 0, tp = 0;
   if(g_stop > 0) sl = NormPreco(comp ? pm - g_stop : pm + g_stop);
   if(g_alvo > 0) tp = NormPreco(comp ? pm + g_alvo : pm - g_alvo);
   double meioTick = (TickSize() > 0 ? TickSize() : _Point) / 2;
   if(MathAbs(sl - PositionGetDouble(POSITION_SL)) < meioTick &&
      MathAbs(tp - PositionGetDouble(POSITION_TP)) < meioTick) return;   // nada a mudar
   if(!trade.PositionModify(_Symbol, sl, tp))
   {
      string msg = StringFormat("stop %s / alvo %s recusado: %s", DoubleToString(sl, _Digits),
                                DoubleToString(tp, _Digits), trade.ResultRetcodeDescription());
      if(msg != g_ult_modif) { g_ultimo = g_ultimo + "  | " + msg; Print("[SIM] ", msg); }
      g_ult_modif = msg;
   }
   else g_ult_modif = "";
}

// Envia a ordem depois do atraso. O preco, o stop/alvo e o deslize sao tratados
// em OnTradeTransaction, quando o negocio de fato acontece.
void Envia()
{
   int acao = g_pend;
   g_pend = 0;
   bool ok;

   if(acao == 2)
   {
      if(!PositionSelect(_Symbol)) { g_ultimo = "ZERAR: sem posicao"; return; }
      ok = trade.PositionClose(_Symbol);
   }
   else
      ok = (acao == 1 ? trade.Buy(g_lote, _Symbol) : trade.Sell(g_lote, _Symbol));

   if(!ok)
   {
      g_ultimo = NomeAcao(acao) + " recusada: " + trade.ResultRetcodeDescription();
      return;
   }
   g_env_acao   = acao;
   g_env_ref    = g_pend_ref;
   g_env_atraso = g_pend_atraso;
   g_ultimo     = StringFormat(">>> %s enviada, aguardando execucao...", NomeAcao(acao));
}

//+------------------------------------------------------------------+
// Marcas no grafico: seta em cada negocio + linhas de entrada/stop/alvo
void MarcaNegocio(ulong deal, string tag, double preco)
{
   bool     compra = (HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_BUY);
   datetime t      = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
   color    c      = (tag == "STOP" ? clrRed : (tag == "ALVO" ? clrLime : (compra ? clrDodgerBlue : clrOrangeRed)));
   string   n      = "SIM_MK_" + (string)deal;

   ObjectCreate(0, n, compra ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, t, preco);
   ObjectSetInteger(0, n, OBJPROP_COLOR, c);
   ObjectSetInteger(0, n, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);

   ObjectCreate(0, n + "_T", OBJ_TEXT, 0, t, preco);
   ObjectSetString (0, n + "_T", OBJPROP_TEXT, " " + tag + " " + DoubleToString(preco, _Digits));
   ObjectSetInteger(0, n + "_T", OBJPROP_ANCHOR, compra ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, n + "_T", OBJPROP_COLOR, c);
   ObjectSetInteger(0, n + "_T", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, n + "_T", OBJPROP_SELECTABLE, false);
}

void Linha(string nome, double preco, color c, ENUM_LINE_STYLE estilo, string rotulo, datetime agora)
{
   if(preco <= 0) { ObjectDelete(0, nome); ObjectDelete(0, nome + "_T"); return; }
   if(ObjectFind(0, nome) < 0)
   {
      ObjectCreate(0, nome, OBJ_HLINE, 0, 0, preco);
      ObjectSetInteger(0, nome, OBJPROP_COLOR, c);
      ObjectSetInteger(0, nome, OBJPROP_STYLE, estilo);
      ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, nome, OBJPROP_BACK, true);
      ObjectCreate(0, nome + "_T", OBJ_TEXT, 0, agora, preco);
      ObjectSetInteger(0, nome + "_T", OBJPROP_ANCHOR, ANCHOR_RIGHT_LOWER);
      ObjectSetInteger(0, nome + "_T", OBJPROP_COLOR, c);
      ObjectSetInteger(0, nome + "_T", OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, nome + "_T", OBJPROP_SELECTABLE, false);
   }
   ObjectSetDouble (0, nome, OBJPROP_PRICE, preco);
   ObjectMove      (0, nome + "_T", 0, agora, preco);   // rotulo acompanha a ultima barra
   ObjectSetString (0, nome + "_T", OBJPROP_TEXT, rotulo + " " + DoubleToString(preco, _Digits));
}

void DesenhaNiveis(datetime agora)
{
   double pm = 0, sl = 0, tp = 0;
   if(PositionSelect(_Symbol))
   {
      pm = PositionGetDouble(POSITION_PRICE_OPEN);
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
   }
   Linha("SIM_HL_ENTRADA", pm, clrSilver,    STYLE_DASH,  "ENTRADA", agora);
   Linha("SIM_HL_STOP",    sl, clrRed,       STYLE_SOLID, "STOP",    agora);
   Linha("SIM_HL_ALVO",    tp, clrLime,      STYLE_SOLID, "ALVO",    agora);
}

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &t,
                        const MqlTradeRequest &req,
                        const MqlTradeResult &res)
{
   if(t.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(t.deal)) return;
   if(HistoryDealGetString(t.deal, DEAL_SYMBOL) != _Symbol) return;

   long   motivo = HistoryDealGetInteger(t.deal, DEAL_REASON);
   double vol    = HistoryDealGetDouble(t.deal, DEAL_VOLUME);
   double preco  = HistoryDealGetDouble(t.deal, DEAL_PRICE);
   string tag;
   double prob;

   if(motivo == DEAL_REASON_SL)      { tag = "STOP"; prob = ProbDeslizeStop; }
   else if(motivo == DEAL_REASON_TP) { tag = "ALVO"; prob = ProbDeslizeAlvo; }
   else if(g_env_acao != 0 && (ulong)HistoryDealGetInteger(t.deal, DEAL_MAGIC) == MagicNumber)
   {
      int acao = g_env_acao;
      g_env_acao = 0;
      tag  = NomeAcao(acao);
      prob = ProbDeslizeMercado;
      g_n_exec++;
      string mov = "";
      if(g_env_ref > 0)
      {
         bool compra = (HistoryDealGetInteger(t.deal, DEAL_TYPE) == DEAL_TYPE_BUY);
         double d = (compra ? preco - g_env_ref : g_env_ref - preco);  // >0 = pior
         mov = StringFormat(", tela %s, atraso custou %+.0f pts", DoubleToString(g_env_ref, _Digits), -d);
      }
      g_ultimo = StringFormat("%s %.0f @ %s (atraso %d ms%s)", tag, vol,
                              DoubleToString(preco, _Digits), g_env_atraso, mov);
      MarcaNegocio(t.deal, tag, preco);
      if(acao != 2) g_reancorar = true;
      if(g_tester)
      {
         int desl = SorteiaDeslize(prob);
         if(desl > 0) CobraDeslize(desl, vol, tag);
      }
      return;
   }
   else return;

   g_n_exec++;
   g_ultimo = StringFormat("%s executado %.0f @ %s", tag, vol, DoubleToString(preco, _Digits));
   MarcaNegocio(t.deal, tag, preco);
   if(g_tester)
   {
      int desl = SorteiaDeslize(prob);
      if(desl > 0) CobraDeslize(desl, vol, tag);
   }
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
      transito = StringFormat("\n>>> ENVIANDO %s ... (%d ms)", NomeAcao(g_pend),
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
   LeAjustes();
   LeBotoes(tk);
   if(g_pend != 0 && tk.time_msc >= g_pend_exe_msc) Envia();
   if(g_reancorar) AjustaNiveis();
   DesenhaNiveis(tk.time);
   Painel(tk);
}
//+------------------------------------------------------------------+
