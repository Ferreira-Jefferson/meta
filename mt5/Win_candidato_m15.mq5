//+------------------------------------------------------------------+
//| Win.mq5                                                          |
//| Expert Advisor para o MINI INDICE (WIN), grafico de 5 minutos.   |
//|                                                                  |
//| Direcao: WMA (Linear Weighted, a ROXA) e SMMA (Smoothed, a VERDE)|
//| de periodo 34 sobre o fechamento. Compra so' com a vela INTEIRA  |
//| (pavio incluido) ACIMA da roxa E a verde ABAIXO da roxa; venda   |
//| so' com a vela inteira ABAIXO da roxa E a verde ACIMA da roxa.   |
//| Decide so' no FECHAMENTO da vela e entra a mercado na abertura da|
//| seguinte.                                                        |
//|                                                                  |
//| Filtros de entrada (todos sobre a vela do sinal):                |
//|  - Idade: a vela do sinal e' no maximo a IdadeMax-esima vela     |
//|    seguida a fechar do mesmo lado da roxa (comeco da onda).      |
//|  - Distancia: a ponta do pavio mais proxima da roxa esta a pelo  |
//|    menos DistMinPontos dela (preco nao colado na roxa).          |
//|  - Gap: |roxa - verde| / ATR < GapMaxATR (medias nao esticadas).  |
//|  - Indecisao: nas ultimas JanelaToques velas fechadas, no maximo  |
//|    ToquesMax tocaram a roxa (vela nao inteira do lado do sinal). |
//|    Muito toque recente = mercado sem direcao, mais stops.        |
//|  - Horario: nao abre operacao nas horas de HorasSemEntrada (hora do  |
//|    servidor). Nos dados, 11h e as entradas depois das 15h perdiam |
//|    nos dois periodos testados.                                    |
//|  - Espaco: o extremo da vela do lado do preco esta a pelo menos  |
//|    ExtRoxaMinATR x ATR da roxa, e o fechamento a pelo menos      |
//|    DistVerdeMinATR x ATR da verde (onda com espaco para andar).  |
//|                                                                  |
//| CANDIDATO (Win_candidato_m15.mq5 = Win.mq5 v2.01 + 2 filtros     |
//| novos, ambos DESLIGADOS por padrao; com os padroes o EA e'       |
//| identico ao v2.01). Ainda NAO adotado:                           |
//|  - AlinharM15 (true liga): na abertura da M5 seguinte ao sinal,  |
//|    a ULTIMA barra M15 JA FECHADA (a de abertura <= abertura da   |
//|    M5 - 15 min; nunca a M15 em formacao) tem fechamento do mesmo |
//|    lado da roxa M15 (LWMA34 do close M15) que o sinal (acima na  |
//|    compra, abaixo na venda) E a SMMA34 M15 (verde) do lado oposto|
//|    da roxa M15. Comparacoes estritas.                            |
//|  - FaixaDiaMin (0 = desligado): pos = (fechamento da vela do     |
//|    sinal - minima do dia) / (maxima - minima do dia), com as     |
//|    velas M5 do MESMO dia ate' e incluindo a vela do sinal; na    |
//|    venda usa 1 - pos. So' entra se pos >= FaixaDiaMin.           |
//|  - DebugFiltros (true imprime): por sinal que passou os filtros  |
//|    do v2.01, uma linha com horario | M15 | roxa15 | verde15 |   |
//|    close15 | pos | max | min | veredito.                         |
//|                                                                  |
//| Saida: nao ha alvo nem trailing. O stop fica na roxa deslocado   |
//| KFechamentoATR x ATR para o lado do preco, e e' recolocado a cada|
//| fechamento de vela M5 (acompanha a roxa, sobe e desce). Se uma   |
//| vela M5 fecha ENTRE a roxa e a verde, a posicao e' encerrada a   |
//| mercado.                                                         |
//|                                                                  |
//| Saida por esticada: o "afastamento" e' (fechamento - roxa) no    |
//| sentido da operacao, em ATR, medido a cada fechamento de vela M5.|
//| Depois que ele passa de EsticadaArmaATR, a posicao e' encerrada a|
//| mercado quando o afastamento recua EsticadaRecuoATR em relacao ao|
//| maior afastamento ja' visto na operacao (preco foi longe demais  |
//| da roxa e esta voltando).                                        |
//|                                                                  |
//| Uma posicao por vez. Entradas ate' MinutosSemEntrada antes do fim|
//| do pregao; zera tudo a mercado MinutosZerar antes do fim.        |
//|                                                                  |
//| Origem dos parametros: simulacao M1 em WINV26 (set/2026 refino,  |
//| ago/2026 validacao). Custos (5 pts/op + 2 pts de slippage no     |
//| stop) valem so' naquela simulacao; aqui quem cobra e' a corretora|
//| ou o Testador.                                                   |
//+------------------------------------------------------------------+
#property copyright "win"
#property version   "2.02"
#property strict

#include <Trade\Trade.mqh>

input int    Periodo             = 34;     // Periodo da WMA (roxa) e da SMMA (verde)
input double KFechamentoATR      = 0.6;    // Stop na roxa deslocado K x ATR para o lado do preco
input int    PeriodoATR          = 14;     // Periodo do ATR (media simples do True Range, M5)
input int    IdadeMax            = 9;      // So' entra ate' a N-esima vela seguida do mesmo lado da roxa (0 = sem filtro)
input double DistMinPontos       = 15.0;   // Ponta do pavio a no minimo N pontos da roxa
input double GapMaxATR           = 3.0;    // So' entra se |roxa-verde| / ATR < N (0 = sem filtro)
input double ExtRoxaMinATR       = 1.4;    // Extremo da vela (maxima na compra, minima na venda) a no minimo N x ATR da roxa (0 = sem filtro)
input double DistVerdeMinATR     = 1.2;    // Fechamento a no minimo N x ATR da verde, no sentido da operacao (0 = sem filtro)
input double EsticadaArmaATR      = 2.5;    // Arma a saida por esticada quando o afastamento da roxa passa de N x ATR (0 = sem esta saida)
input double EsticadaRecuoATR    = 0.75;   // Armada, sai quando o afastamento recua N x ATR do maior afastamento da operacao
input bool   AlinharM15          = false;  // CANDIDATO: exige M15 alinhado (ultima M15 fechada: close do lado do sinal da roxa M15 e verde M15 do lado oposto)
input double FaixaDiaMin         = 0.0;    // CANDIDATO: so' entra se a posicao do fechamento na faixa do dia (0 a 1, invertida na venda) >= N (0 = desligado)
input bool   DebugFiltros        = false;  // CANDIDATO: imprime no Diario os valores dos 2 filtros novos a cada sinal que passou os filtros do v2.01
input int    JanelaToques        = 20;    // Janela, em velas M5 fechadas, para contar os toques na roxa (0 = sem filtro)
input int    ToquesMax           = 14;     // Maximo de velas da janela que tocaram a roxa para poder entrar
input string HorasSemEntrada     = "11,15,16,17"; // Horas cheias do servidor (0-23, separadas por virgula) em que NAO abre operacao; vazio = sem filtro
input int    HoraFimPregao       = 18;     // Hora do fim do pregao (horario do servidor do MT5)
input int    MinutoFimPregao     = 0;      // Minuto do fim do pregao
input int    MinutosSemEntrada   = 30;     // Para de abrir operacao tantos minutos antes do fim
input int    MinutosZerar        = 10;     // Fecha a posicao a mercado tantos minutos antes do fim
input double Lote                = 1.0;    // Contratos por operacao
input double CapitalDigitado     = 1000.0; // Seu capital em R$ no momento em que liga o robo (NAO usa o saldo do MT5: ele nao e' confiavel na Rico)
input double MargemPorContrato   = 100.0;  // Margem exigida por contrato de WIN, em R$ -- o robo so' abre operacao enquanto o capital cobrir isso
input ulong  MagicNumber         = 80080001; // Codigo que identifica as ordens deste robo

CTrade trade;

int      g_h_smma = INVALID_HANDLE;
int      g_h_wma = INVALID_HANDLE;
int      g_h_smma15 = INVALID_HANDLE;  // SMMA34 (verde) do M15
int      g_h_wma15 = INVALID_HANDLE;   // LWMA34 (roxa) do M15
datetime g_ultima_barra = 0;
datetime g_inicio_capital = 0;  // lucro/prejuizo do robo conta a partir daqui
bool     g_hora_bloqueada[24];  // horas (do servidor) sem entrada nova

// estado da saida por esticada (da posicao aberta)
ulong    g_ticket_pos = 0;
bool     g_esticada_armada = false;
double   g_pico_afastamento = -1.0e9;

//+------------------------------------------------------------------+
int OnInit()
{
   if(Period() != PERIOD_M5)
      Print("AVISO: a estrategia foi desenhada para o grafico de 5 minutos (M5).");
   if(Periodo < 2 || PeriodoATR < 1 || KFechamentoATR < 0.0)
   {
      Print("ERRO: parametros invalidos (Periodo >= 2, PeriodoATR >= 1, KFechamentoATR >= 0).");
      return INIT_PARAMETERS_INCORRECT;
   }

   ArrayInitialize(g_hora_bloqueada, false);
   string horas[];
   int n_horas = StringSplit(HorasSemEntrada, ',', horas);
   for(int i = 0; i < n_horas; i++)
   {
      StringTrimLeft(horas[i]); StringTrimRight(horas[i]);
      if(horas[i] == "") continue;
      int h = (int)StringToInteger(horas[i]);
      if(h < 0 || h > 23 || (h == 0 && horas[i] != "0"))
      {
         PrintFormat("ERRO: HorasSemEntrada invalida ('%s'): use horas de 0 a 23 separadas por virgula.", HorasSemEntrada);
         return INIT_PARAMETERS_INCORRECT;
      }
      g_hora_bloqueada[h] = true;
   }

   g_h_smma = iMA(_Symbol, PERIOD_M5, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
   g_h_wma = iMA(_Symbol, PERIOD_M5, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
   if(g_h_smma == INVALID_HANDLE || g_h_wma == INVALID_HANDLE)
      return INIT_FAILED;

   if(FaixaDiaMin < 0.0 || FaixaDiaMin > 1.0)
   {
      Print("ERRO: FaixaDiaMin deve estar entre 0 e 1 (0 = desligado).");
      return INIT_PARAMETERS_INCORRECT;
   }
   // handles do M15 so' sao criados quando precisam ser lidos (filtro ligado ou debug)
   if(AlinharM15 || DebugFiltros)
   {
      g_h_smma15 = iMA(_Symbol, PERIOD_M15, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
      g_h_wma15 = iMA(_Symbol, PERIOD_M15, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
      if(g_h_smma15 == INVALID_HANDLE || g_h_wma15 == INVALID_HANDLE)
         return INIT_FAILED;
   }

   g_inicio_capital = TimeCurrent();
   trade.SetExpertMagicNumber(MagicNumber);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(g_h_smma);
   IndicatorRelease(g_h_wma);
   if(g_h_smma15 != INVALID_HANDLE) IndicatorRelease(g_h_smma15);
   if(g_h_wma15 != INVALID_HANDLE) IndicatorRelease(g_h_wma15);
}

//+------------------------------------------------------------------+
double Arredonda(double preco)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return NormalizeDouble(MathRound(preco / tick) * tick, _Digits);
}

int MinutoDoDia(datetime t)
{
   MqlDateTime d;
   TimeToStruct(t, d);
   return d.hour * 60 + d.min;
}

bool SelecionaPosicao()
{
   if(!PositionSelect(_Symbol)) return false;
   return PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber;
}

//+------------------------------------------------------------------+
// Roxa, verde e fechamento da ultima vela FECHADA (indice 1)
bool LeMedias(double &wma, double &smma, double &close1)
{
   double w[1], s[1], c[1];
   if(CopyBuffer(g_h_wma, 0, 1, 1, w) != 1) return false;
   if(CopyBuffer(g_h_smma, 0, 1, 1, s) != 1) return false;
   if(CopyClose(_Symbol, PERIOD_M5, 1, 1, c) != 1) return false;
   wma = w[0]; smma = s[0]; close1 = c[0];
   return true;
}

// ATR: media simples do True Range das PeriodoATR ultimas velas fechadas
bool LeATR(double &atr, int shift = 1)
{
   int n = PeriodoATR + 1;  // +1: o True Range da vela mais antiga precisa do fechamento anterior
   double hi[], lo[], cl[];
   ArraySetAsSeries(hi, true); ArraySetAsSeries(lo, true); ArraySetAsSeries(cl, true);
   if(CopyHigh(_Symbol, PERIOD_M5, shift, n, hi) != n) return false;
   if(CopyLow(_Symbol, PERIOD_M5, shift, n, lo) != n) return false;
   if(CopyClose(_Symbol, PERIOD_M5, shift, n, cl) != n) return false;
   double soma = 0.0;
   for(int i = 0; i < PeriodoATR; i++)
      soma += MathMax(hi[i] - lo[i], MathMax(MathAbs(hi[i] - cl[i + 1]), MathAbs(lo[i] - cl[i + 1])));
   atr = soma / PeriodoATR;
   return atr > 0.0;
}

// Afastamento do fechamento da vela fechada `shift` em relacao a roxa, no sentido da
// operacao, em ATR. Atualiza o pico e arma a saida por esticada.
bool AcumulaAfastamento(bool compra, int shift, double &afast)
{
   double w[1], c[1], atr;
   if(CopyBuffer(g_h_wma, 0, shift, 1, w) != 1) return false;
   if(CopyClose(_Symbol, PERIOD_M5, shift, 1, c) != 1) return false;
   if(!LeATR(atr, shift)) return false;
   afast = (compra ? 1.0 : -1.0) * (c[0] - w[0]) / atr;
   if(afast >= EsticadaArmaATR) g_esticada_armada = true;
   g_pico_afastamento = MathMax(g_pico_afastamento, afast);
   return true;
}

// +1 compra, -1 venda, 0 nada -- usando a vela FECHADA no indice 1
int Sinal()
{
   double smma[1], wma[1], hi[1], lo[1];
   if(CopyBuffer(g_h_smma, 0, 1, 1, smma) != 1) return 0;
   if(CopyBuffer(g_h_wma, 0, 1, 1, wma) != 1) return 0;
   if(CopyHigh(_Symbol, PERIOD_M5, 1, 1, hi) != 1) return 0;
   if(CopyLow(_Symbol, PERIOD_M5, 1, 1, lo) != 1) return 0;
   // vela INTEIRA (pavio incluido) fora da roxa e verde do lado oposto da roxa
   if(lo[0] > wma[0] && smma[0] < wma[0]) return 1;
   if(hi[0] < wma[0] && smma[0] > wma[0]) return -1;
   return 0;
}

// Quantas velas fechadas seguidas (contando a do sinal) terminaram do lado do sinal da roxa
int IdadeDaOnda(int sinal)
{
   int n = IdadeMax + 1;  // basta saber se passa de IdadeMax
   double w[], c[];
   ArraySetAsSeries(w, true); ArraySetAsSeries(c, true);
   if(CopyBuffer(g_h_wma, 0, 1, n, w) != n) return n;
   if(CopyClose(_Symbol, PERIOD_M5, 1, n, c) != n) return n;
   int idade = 0;
   for(int i = 0; i < n; i++)
   {
      int lado = c[i] > w[i] ? 1 : (c[i] < w[i] ? -1 : 0);
      if(lado != sinal) break;
      idade++;
   }
   return idade;
}

// Quantas das ultimas `janela` velas fechadas NAO ficaram inteiras do lado do sinal da roxa
int ToquesNaRoxa(int sinal, int janela)
{
   double w[], hi[], lo[];
   ArraySetAsSeries(w, true); ArraySetAsSeries(hi, true); ArraySetAsSeries(lo, true);
   if(CopyBuffer(g_h_wma, 0, 1, janela, w) != janela) return janela;
   if(CopyHigh(_Symbol, PERIOD_M5, 1, janela, hi) != janela) return janela;
   if(CopyLow(_Symbol, PERIOD_M5, 1, janela, lo) != janela) return janela;
   int toques = 0;
   for(int i = 0; i < janela; i++)
      if(sinal > 0 ? lo[i] <= w[i] : hi[i] >= w[i]) toques++;
   return toques;
}

// Filtros de entrada sobre a vela do sinal
bool FiltrosAprovam(int sinal, double wma, double smma, double close1, double atr)
{
   double hi[1], lo[1];
   if(CopyHigh(_Symbol, PERIOD_M5, 1, 1, hi) != 1) return false;
   if(CopyLow(_Symbol, PERIOD_M5, 1, 1, lo) != 1) return false;

   if(IdadeMax > 0 && IdadeDaOnda(sinal) > IdadeMax) return false;

   if(JanelaToques > 0 && ToquesNaRoxa(sinal, JanelaToques) > ToquesMax) return false;

   double dist = sinal > 0 ? lo[0] - wma : wma - hi[0];  // ponta do pavio mais proxima da roxa
   if(dist < DistMinPontos) return false;

   if(GapMaxATR > 0.0 && MathAbs(wma - smma) / atr >= GapMaxATR) return false;

   double ext = sinal > 0 ? hi[0] - wma : wma - lo[0];  // extremo da vela ate' a roxa
   if(ExtRoxaMinATR > 0.0 && ext / atr < ExtRoxaMinATR) return false;

   if(DistVerdeMinATR > 0.0 && sinal * (close1 - smma) / atr < DistVerdeMinATR) return false;
   return true;
}

//+------------------------------------------------------------------+
// M15 alinhado, lido na abertura da M5 `t_entrada` (abertura da M5 seguinte ao sinal).
// A barra M15 usada e' a ultima JA FECHADA nesse instante: a de abertura <= t_entrada - 15min.
//   M5 abre 10:05 -> alvo 09:50 -> barra M15 09:45 (fechou 10:00)       [M15 de 10:00 em formacao: nao usa]
//   M5 abre 10:15 -> alvo 10:00 -> barra M15 10:00 (fechou 10:15)       [recem-fechada: usa]
// iBarShift(exact=false) devolve a barra que CONTEM o instante alvo; a checagem
// t15 + 15min <= t_entrada garante que ela ja' fechou (nunca usa barra em formacao).
bool LeM15(datetime t_entrada, double &wma15, double &smma15, double &close15)
{
   int sh = iBarShift(_Symbol, PERIOD_M15, t_entrada - 15 * 60, false);
   if(sh < 0) return false;
   datetime t15 = iTime(_Symbol, PERIOD_M15, sh);
   if(t15 == 0 || t15 + 15 * 60 > t_entrada) return false;
   double w[1], s[1], c[1];
   if(CopyBuffer(g_h_wma15, 0, sh, 1, w) != 1) return false;    // -1 = indicador ainda nao calculado
   if(CopyBuffer(g_h_smma15, 0, sh, 1, s) != 1) return false;
   if(CopyClose(_Symbol, PERIOD_M15, sh, 1, c) != 1) return false;
   if(w[0] == EMPTY_VALUE || s[0] == EMPTY_VALUE) return false;
   wma15 = w[0]; smma15 = s[0]; close15 = c[0];
   return true;
}

// Maxima e minima do dia (M5 do MESMO dia do servidor, da primeira vela do dia ate' a vela do sinal, inclusive)
bool LeFaixaDia(double &maxd, double &mind)
{
   datetime t_sinal = iTime(_Symbol, PERIOD_M5, 1);
   datetime t_dia = t_sinal - (datetime)(t_sinal % 86400);
   double hi[], lo[];
   int nh = CopyHigh(_Symbol, PERIOD_M5, t_dia, t_sinal, hi);
   int nl = CopyLow(_Symbol, PERIOD_M5, t_dia, t_sinal, lo);
   if(nh < 1 || nl < 1 || nh != nl) return false;
   maxd = hi[ArrayMaximum(hi)];
   mind = lo[ArrayMinimum(lo)];
   return true;
}

// Filtros novos (candidato). Roda so' na vela nova com sinal que ja' passou os filtros do v2.01.
bool FiltrosNovosAprovam(int sinal, double close1, datetime t_entrada)
{
   if(!AlinharM15 && FaixaDiaMin <= 0.0 && !DebugFiltros) return true;

   // --- M15 alinhado
   double w15 = 0, s15 = 0, c15 = 0;
   bool m15_lido = (AlinharM15 || DebugFiltros) && LeM15(t_entrada, w15, s15, c15);
   bool m15_ok = m15_lido
              && (sinal > 0 ? (c15 > w15 && s15 < w15) : (c15 < w15 && s15 > w15));

   // --- posicao na faixa do dia
   double mx = 0, mn = 0, pos = 0;
   bool faixa_lida = (FaixaDiaMin > 0.0 || DebugFiltros) && LeFaixaDia(mx, mn) && mx > mn;
   if(faixa_lida)
   {
      pos = (close1 - mn) / (mx - mn);
      if(sinal < 0) pos = 1.0 - pos;
   }
   bool faixa_ok = faixa_lida && pos >= FaixaDiaMin;

   bool aprova = (!AlinharM15 || m15_ok) && (FaixaDiaMin <= 0.0 || faixa_ok);

   if(DebugFiltros)
      PrintFormat("FILTROS %s | %s | M15=%s | roxa15=%s | verde15=%s | close15=%s | pos=%s | max=%s | min=%s | %s",
                  TimeToString(t_entrada, TIME_DATE | TIME_MINUTES), sinal > 0 ? "COMPRA" : "VENDA",
                  m15_lido ? (m15_ok ? "sim" : "nao") : "sem_dado",
                  m15_lido ? StringFormat("%.1f", w15) : "-", m15_lido ? StringFormat("%.1f", s15) : "-",
                  m15_lido ? StringFormat("%.0f", c15) : "-",
                  faixa_lida ? StringFormat("%.3f", pos) : "sem_dado",
                  faixa_lida ? StringFormat("%.0f", mx) : "-", faixa_lida ? StringFormat("%.0f", mn) : "-",
                  aprova ? "APROVA" : "REJEITA");
   return aprova;
}

//+------------------------------------------------------------------+
// Cotacao valida: simbolos sem livro (ex.: WIN$ continuo no testador) vem com bid/ask = 0 e abririam posicao a preco 0.
bool CotacaoValida()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   return bid > 0.0 && ask > 0.0 && ask >= bid;
}

void Entra(int sinal, double wma, double atr)
{
   if(!CotacaoValida())
   {
      PrintFormat("Entrada ignorada: %s sem cotacao (bid/ask) valida -- use o contrato real (ex.: WINV26), nao a serie continua", _Symbol);
      return;
   }
   double preco = sinal > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double sl = Arredonda(wma + sinal * KFechamentoATR * atr);

   // Preco ja' dentro da faixa do stop (perto demais da roxa): o stop ficaria do lado errado do preco.
   if(sinal > 0 ? sl > preco - tick : sl < preco + tick)
   {
      PrintFormat("Entrada ignorada: stop %.0f nao fica abaixo/acima do preco %.0f", sl, preco);
      return;
   }

   bool ok = sinal > 0 ? trade.Buy(Lote,  _Symbol, 0.0, sl, 0.0, "win")
                       : trade.Sell(Lote, _Symbol, 0.0, sl, 0.0, "win");
   if(!ok)
      PrintFormat("ERRO entrada: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

// A cada fechamento de vela M5 com posicao aberta: encerra se a vela fechou entre
// a roxa e a verde; senao recoloca o stop na roxa +/- K x ATR. O estado e' recalculado
// do zero a cada vela, entao um reinicio do EA no meio da posicao nao perde nada.
void AtualizaPosicao()
{
   double wma, smma, close1, atr;
   if(!LeMedias(wma, smma, close1) || !LeATR(atr)) return;

   if(close1 > MathMin(wma, smma) && close1 < MathMax(wma, smma))
   {
      if(!trade.PositionClose(_Symbol))
         PrintFormat("ERRO fechar no canal: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }

   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   if(!CotacaoValida()) return;  // sem cotacao nao ha' como decidir o stop: tenta na proxima vela

   if(EsticadaArmaATR > 0.0)
   {
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      if(ticket != g_ticket_pos)
      {
         // posicao nova (ou EA reiniciado no meio dela): reconstroi o pico das velas desde a entrada
         g_ticket_pos = ticket;
         g_esticada_armada = false;
         g_pico_afastamento = -1.0e9;
         double ignora;
         int desde = iBarShift(_Symbol, PERIOD_M5, (datetime)PositionGetInteger(POSITION_TIME));
         for(int sh = desde; sh >= 2; sh--)
            AcumulaAfastamento(compra, sh, ignora);
      }
      double afast;
      if(AcumulaAfastamento(compra, 1, afast) && g_esticada_armada && afast <= g_pico_afastamento - EsticadaRecuoATR)
      {
         if(!trade.PositionClose(_Symbol))
            PrintFormat("ERRO fechar por esticada: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
         return;
      }
   }

   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double novo = Arredonda(wma + (compra ? 1.0 : -1.0) * KFechamentoATR * atr);
   double preco = compra ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // O preco ja' passou do novo stop: ele nao pode ser colocado, sai a mercado.
   if(compra ? novo > preco - tick : novo < preco + tick)
   {
      if(!trade.PositionClose(_Symbol))
         PrintFormat("ERRO fechar stop alcancado: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }

   double sl = PositionGetDouble(POSITION_SL);
   if(MathAbs(novo - sl) > tick / 2.0 && !trade.PositionModify(_Symbol, novo, 0.0))
      PrintFormat("ERRO mover stop: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

// capital digitado + resultado realizado deste robo desde que foi ligado
double CapitalAtual()
{
   double total = CapitalDigitado;
   if(!HistorySelect(g_inicio_capital, TimeCurrent() + 60)) return total;
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong tk = HistoryDealGetTicket(k);
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != (long)MagicNumber) continue;
      total += HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_COMMISSION)
             + HistoryDealGetDouble(tk, DEAL_SWAP) + HistoryDealGetDouble(tk, DEAL_FEE);
   }
   return total;
}

//+------------------------------------------------------------------+
void OnTick()
{
   int fim = HoraFimPregao * 60 + MinutoFimPregao;
   int agora = MinutoDoDia(TimeCurrent());

   bool tem_pos = SelecionaPosicao();

   if(tem_pos)
   {
      // posicao de OUTRO dia (EA ficou sem tick no fim do pregao) tambem zera
      bool de_outro_dia = (long)(TimeCurrent() / 86400) != (long)(PositionGetInteger(POSITION_TIME) / 86400);
      if(agora >= fim - MinutosZerar || de_outro_dia)
      {
         if(!trade.PositionClose(_Symbol))
            PrintFormat("ERRO zerar: retcode=%u (%s) -- tenta de novo no proximo tick", trade.ResultRetcode(), trade.ResultRetcodeDescription());
         return;
      }
   }

   datetime barra = iTime(_Symbol, PERIOD_M5, 0);
   if(barra == g_ultima_barra) return;
   g_ultima_barra = barra;

   if(tem_pos)
   {
      AtualizaPosicao();
      return;
   }

   // Sinal da vela fechada de OUTRO dia (primeira barra do pregao) e' sinal velho: nao opera.
   if((long)(iTime(_Symbol, PERIOD_M5, 1) / 86400) != (long)(barra / 86400)) return;

   int sinal = Sinal();
   if(sinal == 0) return;
   if(agora >= fim - MinutosSemEntrada) return;
   if(g_hora_bloqueada[MinutoDoDia(barra) / 60]) return;  // hora da vela que abriu: igual ao backtest
   if(PositionSelect(_Symbol)) return;  // posicao de outro robo/magic no simbolo: nao mexe

   double wma, smma, close1, atr;
   if(!LeMedias(wma, smma, close1) || !LeATR(atr)) return;
   if(!FiltrosAprovam(sinal, wma, smma, close1, atr)) return;
   if(!FiltrosNovosAprovam(sinal, close1, barra)) return;

   double capital = CapitalAtual(), margem = MargemPorContrato * Lote;
   if(capital < margem)
   {
      PrintFormat("SEM MARGEM: capital R$ %.2f < margem R$ %.2f -- nao abre operacao", capital, margem);
      return;
   }
   Entra(sinal, wma, atr);
}
//+------------------------------------------------------------------+
