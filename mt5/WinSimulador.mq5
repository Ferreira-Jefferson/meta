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
//| v1.02 (2026-10-08):                                              |
//|  - compra saia a PRECO 0: clique no fim do pregao + atraso caia  |
//|    no 1o tick do dia seguinte (leilao, bid/ask = 0). A ordem so' |
//|    sai com compra e venda validas no livro, e e' cancelada se    |
//|    ficar mais de 60 s sem mercado.                               |
//|  - campos voltam a aceitar digitacao (alem do - / +); campo      |
//|    apagado ou invalido volta ao valor vigente.                   |
//|  - WIN$/WIN$N/WIN$D nao tem bid/ask nos ticks (medido: 0 em      |
//|    86.934 de 86.934 no Rico-DEMO): testar no contrato (WINV26).  |
//|  - stop/alvo executados pelo Testador com livro defasado sao     |
//|    corrigidos para o preco justo (deposito da diferenca).        |
//|  - input Roteiro: cliques automaticos para teste sem visual.     |
//|  - stop/alvo em pontos de RESULTADO com sinal (stop -300; passou |
//|    da entrada = +50, trava lucro; alvo +200 ou -50), nos campos  |
//|    e nos rotulos das linhas do grafico.                          |
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
#property version   "1.02"

#include <Trade\Trade.mqh>

input double Lote               = 1;      // Contratos por clique (ajustavel no grafico)
input double StopPts            = 0;      // Stop inicial: perda em pontos a partir do preco medio (0 = sem stop)
input double AlvoPts            = 0;      // Alvo inicial: lucro em pontos a partir do preco medio (0 = sem alvo)
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
input string Roteiro            = "";     // Teste automatico: "HH:MM COMPRA,HH:MM ZERAR" (vazio = desligado)

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
// Stop e alvo = RESULTADO em pontos a partir do preco medio, com sinal:
// stop -300 = sai com 300 de perda; stop +50 = passou da entrada e trava 50 de lucro.
// alvo +200 = sai com 200 de lucro; alvo -50 = sai reduzindo a perda.
double   g_stop         = 0;
double   g_alvo         = 0;
bool     g_stop_on      = false;  // false = sem stop
bool     g_alvo_on      = false;  // false = sem alvo

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
bool     g_ajuste_manual = false; // ultimo stop/alvo veio do - / + com posicao aberta
string   g_ult_modif    = "";     // ultimo sl/tp que a corretora recusou (evita repetir a cada tick)
double   g_pos_sl       = 0;      // stop/alvo da posicao no ultimo tick
double   g_pos_tp       = 0;

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

// Na abertura (leilao) os ticks reais da B3 vem sem compra/venda no livro
// (bid/ask = 0 ou cruzados) e o Testador executaria a mercado a preco 0.
bool LivroValido(const MqlTick &tk) { return tk.bid > 0 && tk.ask > 0 && tk.ask >= tk.bid; }

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
   // No Testador visual o texto digitado NAO chega ao EA (medido: so' cliques de botao
   // chegam; teclas, nem com OnChartEvent). La' o campo so' exibe e vale o - / +.
   ObjectSetInteger(0, nome, OBJPROP_READONLY, g_tester);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);

   CriaBotao(btMais, "+", x + 68, y, clrDimGray, 22, 20);
}

// So' reescreve o campo quando o texto difere do valor vigente: assim um valor
// digitado valido nao e' tocado, e um campo apagado/invalido volta ao vigente.
// Digitacao: o texto do campo so' e' lido depois de ficar PARADO (1 s se valido,
// 4 s se vazio/invalido). Antes disso o EA nao toca no campo - ler a cada tick
// aplicava numero pela metade e devolvia o valor antigo a um campo apagado.
string g_campo_nome[3] = {ED_L, ED_S, ED_A};
string g_campo_txt[3];            // ultimo texto visto em cada campo
uint   g_campo_ms[3];             // GetTickCount() (relogio real) da ultima mudanca; 0 = escrito pelo EA

void MostraCampo(int i, string texto)
{
   if(ObjectGetString(0, g_campo_nome[i], OBJPROP_TEXT) != texto)
      ObjectSetString(0, g_campo_nome[i], OBJPROP_TEXT, texto);
   g_campo_txt[i] = texto;
   g_campo_ms[i]  = 0;
}

void MostraCampos()
{
   MostraCampo(0, DoubleToString(g_lote, 0));
   MostraCampo(1, TxtStop());
   MostraCampo(2, TxtAlvo());
}

// Campo = DISTANCIA em pontos da entrada (vazio = desligado). Negativa so' com
// posicao aberta: stop -50 = 50 pts alem da entrada (trava lucro); alvo -50 = sai
// antes da entrada (reduz a perda).
string TxtStop() { return !g_stop_on ? "" : DoubleToString(-g_stop, 0); }
string TxtAlvo() { return !g_alvo_on ? "" : DoubleToString(g_alvo, 0); }

// ms que o texto do campo esta' parado; -1 = acabou de mudar (registra no Diario)
int CampoParado(int i)
{
   string t = ObjectGetString(0, g_campo_nome[i], OBJPROP_TEXT);
   if(t != g_campo_txt[i])
   {
      PrintFormat("[SIM] campo %s: '%s' -> '%s'", g_campo_nome[i], g_campo_txt[i], t);
      g_campo_txt[i] = t;
      g_campo_ms[i]  = GetTickCount();
      return -1;
   }
   if(g_campo_ms[i] == 0) return 1000000;
   return (int)(GetTickCount() - g_campo_ms[i]);
}

string Pts(double v) { return MathAbs(v) < 0.5 ? "0" : StringFormat("%+.0f", v); }

// Le o campo: -1 = vazio/invalido (o campo volta ao vigente), 0 = "sem", 1 = numero.
// comSinal diz se foi digitado + ou - na frente.
int LeCampo(string nome, double &v, bool &comSinal)
{
   string s = ObjectGetString(0, nome, OBJPROP_TEXT);
   StringTrimLeft(s);
   StringTrimRight(s);
   StringReplace(s, ",", ".");
   comSinal = false;
   if(s == "sem" || StringLen(s) == 0) return 0;
   double sinal = 1;
   for(int i = 0; i < StringLen(s); i++)
   {
      ushort c = StringGetCharacter(s, i);
      if((c < '0' || c > '9') && c != '.') return -1;
   }
   v = sinal * StringToDouble(s);
   return 1;
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
   CriaCampo(ED_S, "stop pts", LB_S, BT_SM, BT_SP, 105, 90);
   CriaCampo(ED_A, "alvo pts", LB_A, BT_AM, BT_AP, 200, 90);

   g_lote = NormVolume(Lote);
   g_stop_on = (StopPts > 0);
   g_stop    = -MathAbs(StopPts);
   g_alvo_on = (AlvoPts > 0);
   g_alvo    = MathAbs(AlvoPts);
   MostraCampos();
   Roteiro_Carrega();
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
   // + aumenta a distancia da entrada (vazio -> PassoPts); - diminui. Sem posicao,
   // chegando a 0 desliga (campo vazio); com posicao aberta passa de zero (stop alem
   // da entrada trava lucro; alvo antes da entrada reduz a perda).
   bool posicionado = PositionSelect(_Symbol);
   if(Clicou(BT_SP)) { if(g_stop_on) g_stop -= PassoPts; else { g_stop = -PassoPts; g_stop_on = true; } mudouNiveis = true; }
   if(Clicou(BT_SM) && g_stop_on) { g_stop += PassoPts; if(!posicionado && g_stop >= -0.5) g_stop_on = false; mudouNiveis = true; }
   if(Clicou(BT_AP)) { if(g_alvo_on) g_alvo += PassoPts; else { g_alvo = PassoPts; g_alvo_on = true; } mudouNiveis = true; }
   if(Clicou(BT_AM) && g_alvo_on) { g_alvo -= PassoPts; if(!posicionado && g_alvo <= 0.5) g_alvo_on = false; mudouNiveis = true; }
   if(mudouNiveis && posicionado) g_ajuste_manual = true;
   // zerado, distancia 0 ou negativa nao vale (seria alem da proxima entrada): desliga
   if(!posicionado && g_pend == 0 && g_env_acao == 0)
   {
      if(g_stop_on && g_stop >= -0.5) { g_stop_on = false; mudouNiveis = true; }
      if(g_alvo_on && g_alvo <= 0.5)  { g_alvo_on = false; mudouNiveis = true; }
   }

   if(mudouLote || mudouNiveis) MostraCampos();

   // valores digitados (so' fora do Testador): distancia em pontos; vazio desliga.
   // Numero do tamanho de um PRECO (ex. 182900) vira pontos a partir da entrada.
   for(int i = 0; i < 3; i++)
   {
      int parado = CampoParado(i);
      if(parado < 1000 || g_campo_ms[i] == 0) continue;   // digitando, ou texto e' do proprio EA
      double v = 0;
      bool sn = false;
      int r = LeCampo(g_campo_nome[i], v, sn);
      bool ok = false;
      if(i == 0)
      {
         if(r == 1 && v > 0) { ok = true; if(MathAbs(NormVolume(v) - g_lote) > 1e-9) { g_lote = NormVolume(v); mudouLote = true; } }
      }
      else if(r == 0)
      {
         ok = true;
         if(i == 1 && g_stop_on) { g_stop_on = false; mudouNiveis = true; }
         if(i == 2 && g_alvo_on) { g_alvo_on = false; mudouNiveis = true; }
      }
      else if(r == 1)
      {
         double ref = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
         if(ref > 0 && v > ref / 2)                   // digitou um preco
         {
            if(PositionSelect(_Symbol))
            {
               double dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
               v  = (NormPreco(v) - PositionGetDouble(POSITION_PRICE_OPEN)) * dir;
               sn = true;
               ok = true;
            }
            else g_ultimo = "sem posicao aberta: digite stop/alvo em PONTOS (o preco depende da entrada)";
         }
         else { ok = true; if(i == 1) v = -v; }     // distancia: stop fica abaixo da entrada
         bool liga = MathAbs(v) > 0.5;
         if(ok && i == 1 && (g_stop_on != liga || MathAbs(v - g_stop) > 1e-9)) { g_stop = v; g_stop_on = liga; mudouNiveis = true; }
         if(ok && i == 2 && (g_alvo_on != liga || MathAbs(v - g_alvo) > 1e-9)) { g_alvo = v; g_alvo_on = liga; mudouNiveis = true; }
      }
      if(ok || parado >= 4000)                       // valido: formata; invalido parado 4 s: volta ao vigente
         MostraCampo(i, i == 0 ? DoubleToString(g_lote, 0) : (i == 1 ? TxtStop() : TxtAlvo()));
   }

   if(mudouLote || mudouNiveis) ChartRedraw();
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
   if(g_pend_atraso == 0 && LivroValido(tk)) Envia();
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
   if(g_stop_on) sl = NormPreco(comp ? pm + g_stop : pm - g_stop);
   if(g_alvo_on) tp = NormPreco(comp ? pm + g_alvo : pm - g_alvo);
   double meioTick = (TickSize() > 0 ? TickSize() : _Point) / 2;
   if(MathAbs(sl - PositionGetDouble(POSITION_SL)) < meioTick &&
      MathAbs(tp - PositionGetDouble(POSITION_TP)) < meioTick) return;   // nada a mudar
   if(!trade.PositionModify(_Symbol, sl, tp))
   {
      string msg = StringFormat("stop %s / alvo %s recusado: %s", DoubleToString(sl, _Digits),
                                DoubleToString(tp, _Digits), trade.ResultRetcodeDescription());
      if(msg != g_ult_modif) { g_ultimo = g_ultimo + "  | " + msg; Print("[SIM] ", msg); }
      g_ult_modif = msg;
      if(g_ajuste_manual)   // ex.: stop alem do preco atual. Os campos voltam ao que vale.
      {
         double dir = comp ? 1 : -1, slv = PositionGetDouble(POSITION_SL), tpv = PositionGetDouble(POSITION_TP);
         g_stop_on = (slv > 0); if(g_stop_on) g_stop = (slv - pm) * dir;
         g_alvo_on = (tpv > 0); if(g_alvo_on) g_alvo = (tpv - pm) * dir;
         MostraCampos();
      }
   }
   else { g_ult_modif = ""; LogPosicao("stop/alvo ajustado"); }
   g_ajuste_manual = false;
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

void Linha(string nome, double preco, color c, ENUM_LINE_STYLE estilo, string rotulo, datetime agora,
           bool arrastavel = false)
{
   if(preco <= 0) { ObjectDelete(0, nome); ObjectDelete(0, nome + "_T"); return; }
   if(ObjectFind(0, nome) < 0)
   {
      ObjectCreate(0, nome, OBJ_HLINE, 0, 0, preco);
      ObjectSetInteger(0, nome, OBJPROP_COLOR, c);
      ObjectSetInteger(0, nome, OBJPROP_STYLE, estilo);
      ObjectSetInteger(0, nome, OBJPROP_WIDTH, arrastavel ? 2 : 1);
      ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, arrastavel);
      ObjectSetInteger(0, nome, OBJPROP_SELECTED, arrastavel);   // ja' selecionada: arrasta sem duplo clique
      ObjectSetInteger(0, nome, OBJPROP_BACK, false);
      ObjectCreate(0, nome + "_T", OBJ_TEXT, 0, agora, preco);
      ObjectSetInteger(0, nome + "_T", OBJPROP_ANCHOR, ANCHOR_RIGHT_LOWER);
      ObjectSetInteger(0, nome + "_T", OBJPROP_COLOR, c);
      ObjectSetInteger(0, nome + "_T", OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, nome + "_T", OBJPROP_SELECTABLE, false);
   }
   ObjectSetDouble (0, nome, OBJPROP_PRICE, preco);
   ObjectMove      (0, nome + "_T", 0, agora, preco);   // rotulo acompanha a ultima barra
   ObjectSetString (0, nome + "_T", OBJPROP_TEXT, rotulo);
}

// Linha de stop/alvo arrastada com o mouse: o preco da linha difere do que o EA
// desenhou por ultimo. Vira o novo resultado em pontos e reposiciona a ordem.
double g_desenho_sl = 0, g_desenho_tp = 0;

bool LeArrasto(string nome, double &desenhado, double pm, double dir, double &alvoPts, bool &ligado)
{
   if(ObjectFind(0, nome) < 0 || desenhado <= 0) return false;
   double p = NormPreco(ObjectGetDouble(0, nome, OBJPROP_PRICE));
   double meioTick = (TickSize() > 0 ? TickSize() : _Point) / 2;
   if(MathAbs(p - desenhado) < meioTick) return false;
   alvoPts  = (p - pm) * dir;
   ligado   = true;
   desenhado = p;
   PrintFormat("[SIM] %s arrastado para %s (%s pts)", nome == "SIM_HL_STOP" ? "STOP" : "ALVO",
               DoubleToString(p, _Digits), Pts(alvoPts));
   return true;
}

// Rotulos em pontos de RESULTADO a partir da entrada: STOP -300 / +50, ALVO +200 / -50
void DesenhaNiveis(const MqlTick &tk)
{
   double pm = 0, sl = 0, tp = 0;
   string rEnt = "", rStop = "", rAlvo = "";
   if(PositionSelect(_Symbol))
   {
      bool   comp = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
      double dir  = comp ? 1 : -1;
      pm = PositionGetDouble(POSITION_PRICE_OPEN);
      bool arrastou = LeArrasto("SIM_HL_STOP", g_desenho_sl, pm, dir, g_stop, g_stop_on);
      arrastou = LeArrasto("SIM_HL_ALVO", g_desenho_tp, pm, dir, g_alvo, g_alvo_on) || arrastou;
      if(arrastou)
      {
         MostraCampos();
         AjustaNiveis();          // manda o novo stop/alvo agora
      }
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
      if(arrastou && PositionSelect(_Symbol))
      {
         sl = PositionGetDouble(POSITION_SL);   // recusado pela corretora: a linha volta ao nivel vigente
         tp = PositionGetDouble(POSITION_TP);
         g_stop_on = (sl > 0);
         if(g_stop_on) g_stop = (sl - pm) * dir;
         g_alvo_on = (tp > 0);
         if(g_alvo_on) g_alvo = (tp - pm) * dir;
         MostraCampos();
      }
      double saida = comp ? tk.bid : tk.ask;   // preco em que zeraria agora
      rEnt  = StringFormat("ENTRADA %s   agora %s", DoubleToString(pm, _Digits),
                           saida > 0 ? Pts((saida - pm) * dir) : "-");
      rStop = StringFormat("STOP %s pts   (%s)", Pts((sl - pm) * dir), DoubleToString(sl, _Digits));
      rAlvo = StringFormat("ALVO %s pts   (%s)", Pts((tp - pm) * dir), DoubleToString(tp, _Digits));
   }
   Linha("SIM_HL_ENTRADA", pm, clrSilver,    STYLE_DASH,  rEnt,  tk.time);
   Linha("SIM_HL_STOP",    sl, clrRed,       STYLE_SOLID, rStop, tk.time, true);
   Linha("SIM_HL_ALVO",    tp, clrLime,      STYLE_SOLID, rAlvo, tk.time, true);
   g_desenho_sl = sl;
   g_desenho_tp = tp;
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
      Print("[SIM] ", g_ultimo);
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

   // O Testador dispara stop/alvo pelo ULTIMO negocio mas executa pelo bid/ask, e nos
   // ticks historicos da B3 o livro fica defasado em movimento rapido (medido WINV26
   // 01/09 11:00:04: ultimo varreu 182280->182245 com o ask parado em 182375; alvo de
   // venda em 182260 saiu a 182375). Preco justo = o nivel; no stop, o ultimo se o
   // mercado pulou alem dele. So' corrige quando o Testador foi PIOR que o justo.
   double nivel = (motivo == DEAL_REASON_SL ? g_pos_sl : g_pos_tp);
   if(g_tester && nivel > 0)
   {
      bool fechaComprado = (HistoryDealGetInteger(t.deal, DEAL_TYPE) == DEAL_TYPE_SELL);
      double justo = nivel;
      MqlTick k;
      if(motivo == DEAL_REASON_SL && SymbolInfoTick(_Symbol, k) && k.last > 0)
         justo = fechaComprado ? MathMin(nivel, k.last) : MathMax(nivel, k.last);
      double pts = fechaComprado ? justo - preco : preco - justo;   // >0 = Testador pior
      double tkSize = TickSize();
      if(pts > 0 && tkSize > 0)
      {
         double rs = pts / tkSize * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) * vol;
         TesterDeposit(rs);
         g_ultimo += StringFormat("  | livro defasado: corrigido p/ %s (+R$%.2f)", DoubleToString(justo, _Digits), rs);
         PrintFormat("[SIM] %s: Testador executou a %s com livro defasado; preco justo %s, devolvido +R$%.2f",
                     tag, DoubleToString(preco, _Digits), DoubleToString(justo, _Digits), rs);
         preco = justo;
      }
   }
   MarcaNegocio(t.deal, tag, preco);
   Print("[SIM] ", g_ultimo);
   if(g_tester)
   {
      int desl = SorteiaDeslize(prob);
      if(desl > 0) CobraDeslize(desl, vol, tag);
   }
}

//+------------------------------------------------------------------+
// Roteiro: cliques automaticos para testar o EA sem visualizacao.
// Formato "HH:MM ACAO,HH:MM ACAO", ACAO = COMPRA | VENDA | ZERAR | STOP=n | ALVO=n.
// Cada passo roda uma vez por dia, pelo mesmo caminho do clique na tela.
string   g_rot_hora[];
string   g_rot_acao[];
int      g_rot_dia = -1;
bool     g_rot_feito[];

void Roteiro_Carrega()
{
   string passos[];
   int n = StringSplit(Roteiro, ',', passos);
   ArrayResize(g_rot_hora, 0);
   ArrayResize(g_rot_acao, 0);
   for(int i = 0; i < n; i++)
   {
      string p = passos[i];
      StringTrimLeft(p);
      StringTrimRight(p);
      int sp = StringFind(p, " ");
      if(sp < 0) continue;
      int k = ArraySize(g_rot_hora);
      ArrayResize(g_rot_hora, k + 1);
      ArrayResize(g_rot_acao, k + 1);
      g_rot_hora[k] = StringSubstr(p, 0, sp);
      g_rot_acao[k] = StringSubstr(p, sp + 1);
   }
   ArrayResize(g_rot_feito, ArraySize(g_rot_hora));
}

// Digita no campo como se ja' estivesse parado ha' tempo (o teste sem visual roda
// mais rapido que o relogio real)
void Roteiro_Digita(int i, string texto)
{
   ObjectSetString(0, g_campo_nome[i], OBJPROP_TEXT, texto);
   g_campo_txt[i] = texto;
   g_campo_ms[i]  = GetTickCount() - 5000;
}

void Roteiro_Executa(const MqlTick &tk)
{
   if(ArraySize(g_rot_hora) == 0) return;
   MqlDateTime d;
   TimeToStruct(tk.time, d);
   if(d.day_of_year != g_rot_dia) { g_rot_dia = d.day_of_year; ArrayInitialize(g_rot_feito, false); }
   string agora = StringFormat("%02d:%02d", d.hour, d.min);
   for(int i = 0; i < ArraySize(g_rot_hora); i++)
   {
      if(g_rot_feito[i] || agora < g_rot_hora[i]) continue;
      g_rot_feito[i] = true;
      string a = g_rot_acao[i];
      PrintFormat("[ROTEIRO] %s %s (bid %s ask %s)", agora, a,
                  DoubleToString(tk.bid, _Digits), DoubleToString(tk.ask, _Digits));
      if(a == "COMPRA")      ObjectSetInteger(0, BTN_C, OBJPROP_STATE, true);
      else if(a == "VENDA")  ObjectSetInteger(0, BTN_V, OBJPROP_STATE, true);
      else if(a == "ZERAR")  ObjectSetInteger(0, BTN_Z, OBJPROP_STATE, true);
      else if(StringFind(a, "STOP=") == 0) Roteiro_Digita(1, StringSubstr(a, 5));
      else if(StringFind(a, "ALVO=") == 0) Roteiro_Digita(2, StringSubstr(a, 5));
      // MOVE_STOP=+50 / MOVE_ALVO=-30: move a linha como o mouse faria (pontos de resultado)
      else if((StringFind(a, "MOVE_STOP=") == 0 || StringFind(a, "MOVE_ALVO=") == 0) && PositionSelect(_Symbol))
      {
         double dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
         double p   = PositionGetDouble(POSITION_PRICE_OPEN) + dir * StringToDouble(StringSubstr(a, 10));
         ObjectSetDouble(0, StringFind(a, "MOVE_STOP=") == 0 ? "SIM_HL_STOP" : "SIM_HL_ALVO", OBJPROP_PRICE, p);
      }
   }
}

void LogPosicao(string quando)
{
   if(!PositionSelect(_Symbol)) { PrintFormat("[SIM] %s: ZERADO", quando); return; }
   PrintFormat("[SIM] %s: %s %.0f @ %s stop %s alvo %s", quando,
               PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "COMPRADO" : "VENDIDO",
               PositionGetDouble(POSITION_VOLUME),
               DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), _Digits),
               DoubleToString(PositionGetDouble(POSITION_SL), _Digits),
               DoubleToString(PositionGetDouble(POSITION_TP), _Digits));
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
      g_pos_sl = PositionGetDouble(POSITION_SL);   // guardados para corrigir a execucao do stop/alvo
      g_pos_tp = PositionGetDouble(POSITION_TP);
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
   if(!LivroValido(tk) && tk.last > 0)
      transito += "\nAVISO: este tick nao tem compra/venda no livro (bid/ask = 0) - o Testador nao consegue executar."
                  "\nWIN$/WIN$N/WIN$D nao trazem bid/ask nos ticks: teste no contrato (ex. WINV26).";
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
   Roteiro_Executa(tk);
   LeAjustes();
   LeBotoes(tk);
   if(g_pend != 0 && tk.time_msc >= g_pend_exe_msc)
   {
      if(tk.time_msc - g_pend_exe_msc > 60000)
      {
         // o clique ficou sem mercado (fim de pregao, leilao): no pregao real a
         // ordem nao atravessaria a noite esperando
         g_ultimo = NomeAcao(g_pend) + StringFormat(" cancelada: 60 s sem compra/venda no livro (bid %s / ask %s / ultimo %s)",
                    DoubleToString(tk.bid, _Digits), DoubleToString(tk.ask, _Digits), DoubleToString(tk.last, _Digits));
         Print("[SIM] ", g_ultimo);
         g_pend   = 0;
      }
      else if(LivroValido(tk)) Envia();
      // senao: espera o proximo tick com compra e venda no livro
   }
   if(g_reancorar) AjustaNiveis();
   DesenhaNiveis(tk);
   Painel(tk);
}
//+------------------------------------------------------------------+
