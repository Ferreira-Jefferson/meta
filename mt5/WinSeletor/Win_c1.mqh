//+------------------------------------------------------------------+
//| WinSeletor/Win_c1.mqh
//| Win_c1 v2.07: roxa/verde 34 em H1, filtro H3, break-even 15 min, regra NaoOperarGapATR.
//|
//| Modulo do WinSeletor.mq5. A logica e' a de mt5/Win_c1.mq5 copiada SEM
//| alteracao de regra: so' mudaram escopo (tudo dentro do namespace
//| WC1, para os nomes de variavel/funcao nao colidirem com os outros 4
//| robos), os inputs viram variaveis de mesmo nome preenchidas por
//| Configura() a partir dos inputs C1_* do EA, e os eventos
//| OnInit/OnTick/OnDeinit viram Init/Tick/Deinit. Adaptacoes de
//| seletor estao marcadas com "WinSeletor:" no codigo.
//| Gerado por scripts de build a partir do EA original; nao editar a
//| logica aqui sem editar o EA original (e vice-versa).
//+------------------------------------------------------------------+
#ifndef WINSELETOR_WINC1_MQH
#define WINSELETOR_WINC1_MQH

namespace WC1
{

// ---- inputs do EA original (mesmos nomes e padroes), preenchidos por Configura() ----
int Periodo = 34;
double KFechamentoATR = 0.6;
int PeriodoATR = 14;
int IdadeMax = 9;
double DistMinPontos = 15.0;
double GapMaxATR = 3.0;
double ExtRoxaMinATR = 1.4;
double DistVerdeMinATR = 1.2;
double EsticadaArmaATR = 2.5;
double EsticadaRecuoATR = 0.75;
int AlinharM15 = 1;
bool DebugFiltros = false;
int JanelaToques = 20;
int ToquesMax = 14;
string HorasSemEntrada = "11,15,16,17";
int HoraFimPregao = 18;
int MinutoFimPregao = 0;
int MinutosSemEntrada = 30;
int MinutosZerar = 10;
double Lote = 1.0;
ulong MagicNumber = 80080002;
int BreakEvenMinutos = 15;
double BreakEvenColchaoPts = 7.0;
double NaoOperarGapATR = 1.0;

// WinSeletor: true = robo so' GERE o que ja' existe (saidas, stop, break-even, zeragem, validade das ordens);
// nao arma entrada nova. Usado enquanto uma troca de robo espera a posicao fechar.
bool SoGerir = false;

void Configura()
{
   Periodo = C1_Periodo;
   KFechamentoATR = C1_KFechamentoATR;
   PeriodoATR = C1_PeriodoATR;
   IdadeMax = C1_IdadeMax;
   DistMinPontos = C1_DistMinPontos;
   GapMaxATR = C1_GapMaxATR;
   ExtRoxaMinATR = C1_ExtRoxaMinATR;
   DistVerdeMinATR = C1_DistVerdeMinATR;
   EsticadaArmaATR = C1_EsticadaArmaATR;
   EsticadaRecuoATR = C1_EsticadaRecuoATR;
   AlinharM15 = C1_AlinharM15;
   DebugFiltros = C1_DebugFiltros;
   JanelaToques = C1_JanelaToques;
   ToquesMax = C1_ToquesMax;
   HorasSemEntrada = C1_HorasSemEntrada;
   HoraFimPregao = C1_HoraFimPregao;
   MinutoFimPregao = C1_MinutoFimPregao;
   MinutosSemEntrada = C1_MinutosSemEntrada;
   MinutosZerar = C1_MinutosZerar;
   Lote = C1_Lote;
   MagicNumber = C1_MagicNumber;
   BreakEvenMinutos = C1_BreakEvenMinutos;
   BreakEvenColchaoPts = C1_BreakEvenColchaoPts;
   NaoOperarGapATR = C1_NaoOperarGapATR;
}

void DefineSoGerir(const bool v) { SoGerir = v; }

// WinSeletor: ha posicao ou ordem pendente deste robo (magic proprio, simbolo do grafico)?
bool Tem() { return WinTemPosOuOrdens(MagicNumber); }

// ---------------------------- logica original ----------------------------
// Tempos graficos FIXOS no codigo (sem input, para o Testador nao trocar): o EA calcula tudo em H1, com o filtro
// superior em H3, qualquer que seja o tempo do grafico em que for colocado.
const ENUM_TIMEFRAMES TempoGrafico = PERIOD_H1;
const ENUM_TIMEFRAMES TempoFiltro  = PERIOD_H3;
CTrade trade;

int      g_h_smma = INVALID_HANDLE;
int      g_h_wma = INVALID_HANDLE;
int      g_h_smma15 = INVALID_HANDLE;  // SMMA34 (verde) do H3
int      g_h_wma15 = INVALID_HANDLE;   // LWMA34 (roxa) do H3
datetime g_ultima_barra = 0;
datetime g_ultima_m1 = 0;       // ultima barra M1 ja' checada pelo break-even
bool     g_hora_bloqueada[24];  // horas (do servidor) sem entrada nova

// estado da saida por esticada (da posicao aberta)
ulong    g_ticket_pos = 0;
bool     g_esticada_armada = false;
double   g_pico_afastamento = -1.0e9;

//+------------------------------------------------------------------+
//| REGRA NaoOperarGapATR (Z8, 2026-10-06) -- BLOCO IDENTICO nos 5   |
//| EAs do WIN (Win, Win_c1, WinCincoMedias, WinDeslocamentoMatinal, |
//| WinRetanguloEma34). Copiado de proposito, sem include: mudar aqui|
//| = mudar nos 5. Referencia Python: comparativo_win_2026/          |
//| filtro_gap.py (mesma definicao de combinacoes/z7_dias_extremos/  |
//| z7.py).                                                          |
//|  - Dia BLOQUEADO: |abertura do pregao - fechamento do pregao     |
//|    anterior| >= NaoOperarGapATR x ATR14 D1. Nao abre posicao nova|
//|    no dia; saidas seguem normais.                                |
//|  - Diarias montadas das velas M1 com abertura <= 18:25 (abertura |
//|    = 1a M1 do dia, maxima, minima, ultimo fechamento).           |
//|  - ATR14 D1 = media SIMPLES do True Range dos 14 pregoes         |
//|    ANTERIORES (nada do dia corrente).                            |
//|  - Simbolo CONTINUO (nome com '$' ou '@': WIN$N, WIN@, WIN$): no |
//|    dia do vencimento (4a-feira mais proxima do dia 15 dos meses  |
//|    pares; sem pregao nele, o 1o pregao ate' 3 dias depois) a     |
//|    serie troca de contrato: o gap NAO bloqueia e o True Range    |
//|    desse dia vale so' a amplitude (ignora o salto). Num contrato |
//|    especifico (WINV26...) nao ha salto: sem exclusao, TR completo|
//|  - Decide no 1o tick do pregao (com a 1a vela M1 do dia ja'      |
//|    formada) e guarda o resultado ate' o dia virar.               |
//+------------------------------------------------------------------+
long g_gap_dia_avaliado = -1;    // dia (TimeCurrent / 86400) ja' avaliado
bool g_gap_bloqueado    = false; // resultado do dia avaliado

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime GapVencimentoWIN(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime t15 = StructToTime(d);
   TimeToStruct(t15, d);
   int dif = 3 - d.day_of_week;           // 3 = quarta
   if(dif > 3) dif -= 7;
   if(dif < -3) dif += 7;
   return t15 + dif * 86400;
}

// Serie continua (troca de contrato no vencimento): nome com '$' ou '@'.
bool GapSimboloContinuo()
{
   return StringFind(_Symbol, "$") >= 0 || StringFind(_Symbol, "@") >= 0;
}

// `dia` (00:00) e' o 1o pregao em/apos um vencimento, ate' 3 dias depois; `dia_ant` = pregao anterior.
bool GapDiaDeRolagem(datetime dia, datetime dia_ant)
{
   MqlDateTime d; TimeToStruct(dia, d);
   int ano = d.year, mes = d.mon;
   for(int k = 0; k < 2; k++)             // vencimento deste mes e do mes anterior
   {
      if(mes % 2 == 0)
      {
         datetime v = GapVencimentoWIN(ano, mes);
         if(v > dia_ant && v <= dia && dia - v < 4 * 86400) return true;
      }
      mes--; if(mes == 0) { mes = 12; ano--; }
   }
   return false;
}

// true = hoje NAO abre posicao nova. Avalia uma vez por dia; chame em todo tick (o 1o tick do pregao decide).
bool GapDiaBloqueado()
{
   if(NaoOperarGapATR <= 0.0) return false;
   datetime agora = TimeCurrent();
   long dia_n = (long)(agora / 86400);
   if(dia_n == g_gap_dia_avaliado) return g_gap_bloqueado;
   datetime dia0 = (datetime)(dia_n * 86400);
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, dia0 - 45 * 86400, agora, r);
   if(n < 1 || r[n - 1].time < dia0) return false;   // ainda sem vela M1 de hoje: decide no proximo tick
   datetime dd[];
   double   dO[], dH[], dL[], dC[];
   int nd = 0;
   for(int i = 0; i < n; i++)
   {
      MqlDateTime t; TimeToStruct(r[i].time, t);
      if(t.hour * 60 + t.min > 18 * 60 + 25) continue;          // so' velas M1 com abertura <= 18:25
      datetime d = (datetime)((long)(r[i].time / 86400) * 86400);
      if(nd == 0 || d != dd[nd - 1])
      {
         nd++;
         ArrayResize(dd, nd); ArrayResize(dO, nd); ArrayResize(dH, nd); ArrayResize(dL, nd); ArrayResize(dC, nd);
         dd[nd - 1] = d; dO[nd - 1] = r[i].open; dH[nd - 1] = r[i].high; dL[nd - 1] = r[i].low;
      }
      if(r[i].high > dH[nd - 1]) dH[nd - 1] = r[i].high;
      if(r[i].low  < dL[nd - 1]) dL[nd - 1] = r[i].low;
      dC[nd - 1] = r[i].close;
   }
   g_gap_dia_avaliado = dia_n;
   g_gap_bloqueado = false;
   if(nd < 16 || dd[nd - 1] != dia0)
   {
      PrintFormat("NaoOperarGapATR: %s sem historico para o ATR14 D1 (%d pregoes M1 lidos, preciso de 15 + hoje) -- dia liberado",
                  TimeToString(dia0, TIME_DATE), nd);
      return false;
   }
   bool continuo = GapSimboloContinuo();
   double soma = 0.0;
   for(int k = nd - 15; k <= nd - 2; k++)                        // 14 pregoes anteriores a hoje
   {
      double amp = dH[k] - dL[k];
      double tr = MathMax(amp, MathMax(MathAbs(dH[k] - dC[k - 1]), MathAbs(dL[k] - dC[k - 1])));
      if(continuo && GapDiaDeRolagem(dd[k], dd[k - 1])) tr = amp;  // salto da troca de contrato nao e' volatilidade
      soma += tr;
   }
   double atr = soma / 14.0;
   double gap = dO[nd - 1] - dC[nd - 2];
   if(atr <= 0.0) return false;
   if(MathAbs(gap) < NaoOperarGapATR * atr) return false;
   if(continuo && GapDiaDeRolagem(dd[nd - 1], dd[nd - 2]))
   {
      PrintFormat("NaoOperarGapATR: %s gap %.0f pts = %.2f ATR, mas e' dia de vencimento numa serie continua (%s): troca de contrato, dia liberado",
                  TimeToString(dia0, TIME_DATE), gap, MathAbs(gap) / atr, _Symbol);
      return false;
   }
   g_gap_bloqueado = true;
   PrintFormat("Dia bloqueado: gap %.0f pts = %.2f ATR (abertura %.0f, fechamento anterior %.0f, ATR14 D1 %.1f, limite %.2f ATR) -- sem entrada nova hoje",
               gap, MathAbs(gap) / atr, dO[nd - 1], dC[nd - 2], atr, NaoOperarGapATR);
   return true;
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
int InitBase()
{
   // WinSeletor: aviso de periodo do grafico removido (o modulo calcula em H1 com filtro H3, qualquer grafico serve).
   if(Periodo < 2 || PeriodoATR < 1 || KFechamentoATR < 0.0)
   {
      Print("ERRO: parametros invalidos (Periodo >= 2, PeriodoATR >= 1, KFechamentoATR >= 0).");
      return INIT_PARAMETERS_INCORRECT;
   }

   ArrayInitialize(g_hora_bloqueada, false);
   string horas[];
   // O Testador, em otimizacao, nao repassa parametros de texto aos agentes e entrega "(null)": nesse caso vale o padrao.
   string horas_txt = HorasSemEntrada;
   if(horas_txt == "(null)") horas_txt = "11,15,16,17";
   int n_horas = StringSplit(horas_txt, ',', horas);
   for(int i = 0; i < n_horas; i++)
   {
      StringTrimLeft(horas[i]); StringTrimRight(horas[i]);
      if(horas[i] == "") continue;
      int h = (int)StringToInteger(horas[i]);
      if(h < 0 || h > 23 || (h == 0 && horas[i] != "0"))
      {
         PrintFormat("ERRO: HorasSemEntrada invalida ('%s'): use horas de 0 a 23 separadas por virgula.", horas_txt);
         return INIT_PARAMETERS_INCORRECT;
      }
      g_hora_bloqueada[h] = true;
   }

   g_h_smma = iMA(_Symbol, TempoGrafico, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
   g_h_wma = iMA(_Symbol, TempoGrafico, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
   if(g_h_smma == INVALID_HANDLE || g_h_wma == INVALID_HANDLE)
      return INIT_FAILED;

   // handles do H3 so' sao criados quando precisam ser lidos (filtro ligado ou debug)
   if(AlinharM15 != 0 || DebugFiltros)
   {
      g_h_smma15 = iMA(_Symbol, TempoFiltro, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
      g_h_wma15 = iMA(_Symbol, TempoFiltro, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
      if(g_h_smma15 == INVALID_HANDLE || g_h_wma15 == INVALID_HANDLE)
         return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   return INIT_SUCCEEDED;
}

void DeinitBase(const int reason)
{
   IndicatorRelease(g_h_smma);
   IndicatorRelease(g_h_wma);
   if(g_h_smma15 != INVALID_HANDLE) IndicatorRelease(g_h_smma15);
   if(g_h_wma15 != INVALID_HANDLE) IndicatorRelease(g_h_wma15);
}

//+------------------------------------------------------------------+
// WinSeletor: OnTester e diagnostico de pico de equidade do Win_c1.mq5 nao foram portados (nao negociam).

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
   if(CopyClose(_Symbol, TempoGrafico, 1, 1, c) != 1) return false;
   wma = w[0]; smma = s[0]; close1 = c[0];
   return true;
}

// ATR: media simples do True Range das PeriodoATR ultimas velas fechadas
bool LeATR(double &atr, int shift = 1)
{
   int n = PeriodoATR + 1;  // +1: o True Range da vela mais antiga precisa do fechamento anterior
   double hi[], lo[], cl[];
   ArraySetAsSeries(hi, true); ArraySetAsSeries(lo, true); ArraySetAsSeries(cl, true);
   if(CopyHigh(_Symbol, TempoGrafico, shift, n, hi) != n) return false;
   if(CopyLow(_Symbol, TempoGrafico, shift, n, lo) != n) return false;
   if(CopyClose(_Symbol, TempoGrafico, shift, n, cl) != n) return false;
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
   if(CopyClose(_Symbol, TempoGrafico, shift, 1, c) != 1) return false;
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
   if(CopyHigh(_Symbol, TempoGrafico, 1, 1, hi) != 1) return 0;
   if(CopyLow(_Symbol, TempoGrafico, 1, 1, lo) != 1) return 0;
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
   if(CopyClose(_Symbol, TempoGrafico, 1, n, c) != n) return n;
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
   if(CopyHigh(_Symbol, TempoGrafico, 1, janela, hi) != janela) return janela;
   if(CopyLow(_Symbol, TempoGrafico, 1, janela, lo) != janela) return janela;
   int toques = 0;
   for(int i = 0; i < janela; i++)
      if(sinal > 0 ? lo[i] <= w[i] : hi[i] >= w[i]) toques++;
   return toques;
}

// Filtros de entrada sobre a vela do sinal
bool FiltrosAprovam(int sinal, double wma, double smma, double close1, double atr)
{
   double hi[1], lo[1];
   if(CopyHigh(_Symbol, TempoGrafico, 1, 1, hi) != 1) return false;
   if(CopyLow(_Symbol, TempoGrafico, 1, 1, lo) != 1) return false;

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
// Filtro superior (H3) alinhado, lido na abertura da H1 `t_entrada` (abertura da H1 seguinte ao sinal).
// A barra H3 usada e' a ultima JA FECHADA nesse instante: a de abertura <= t_entrada - 3h.
//   H1 abre 12:00 -> alvo 09:00 -> barra H3 09:00 (fechou 12:00)       [recem-fechada: usa]
//   H1 abre 13:00 -> alvo 10:00 -> barra H3 09:00 (fechou 12:00)       [H3 de 12:00 em formacao: nao usa]
//   H1 abre 10:00 -> alvo 07:00 -> sem barra nesse horario: a ultima anterior (pregao da vespera)
// iBarShift(exact=false) devolve a barra que CONTEM o instante alvo (ou a ultima antes dele); a checagem
// t15 + PeriodSeconds(TempoFiltro) <= t_entrada garante que ela ja' fechou (nunca usa barra em formacao).
bool LeM15(datetime t_entrada, double &wma15, double &smma15, double &close15)
{
   int sh = iBarShift(_Symbol, TempoFiltro, t_entrada - PeriodSeconds(TempoFiltro), false);
   if(sh < 0) return false;
   datetime t15 = iTime(_Symbol, TempoFiltro, sh);
   if(t15 == 0 || t15 + PeriodSeconds(TempoFiltro) > t_entrada) return false;
   double w[1], s[1], c[1];
   if(CopyBuffer(g_h_wma15, 0, sh, 1, w) != 1) return false;    // -1 = indicador ainda nao calculado
   if(CopyBuffer(g_h_smma15, 0, sh, 1, s) != 1) return false;
   if(CopyClose(_Symbol, TempoFiltro, sh, 1, c) != 1) return false;
   if(w[0] == EMPTY_VALUE || s[0] == EMPTY_VALUE) return false;
   wma15 = w[0]; smma15 = s[0]; close15 = c[0];
   return true;
}

// Filtro superior (H3). Roda so' na vela nova com sinal que ja' passou os demais filtros.
bool FiltrosNovosAprovam(int sinal, datetime t_entrada)
{
   if(AlinharM15 == 0 && !DebugFiltros) return true;

   double w15 = 0, s15 = 0, c15 = 0;
   bool m15_lido = LeM15(t_entrada, w15, s15, c15);
   bool m15_ok = m15_lido
              && (sinal > 0 ? (c15 > w15 && s15 < w15) : (c15 < w15 && s15 > w15));
   bool aprova = AlinharM15 == 0 || m15_ok;

   if(DebugFiltros)
      PrintFormat("FILTROS %s | %s | H3=%s | roxa15=%s | verde15=%s | close15=%s | %s",
                  TimeToString(t_entrada, TIME_DATE | TIME_MINUTES), sinal > 0 ? "COMPRA" : "VENDA",
                  m15_lido ? (m15_ok ? "sim" : "nao") : "sem_dado",
                  m15_lido ? StringFormat("%.1f", w15) : "-", m15_lido ? StringFormat("%.1f", s15) : "-",
                  m15_lido ? StringFormat("%.0f", c15) : "-",
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

// A cada fechamento de vela H1 com posicao aberta: encerra se a vela fechou entre
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
         int desde = iBarShift(_Symbol, TempoGrafico, (datetime)PositionGetInteger(POSITION_TIME));
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

//+------------------------------------------------------------------+
// Break-even a mercado (v2.05). Roda no PRIMEIRO tick de cada barra M1 (equivale a checar na abertura do minuto,
// como o simulador M1) e so' com posicao selecionada. Prazo = abertura da H1 de entrada + BreakEvenMinutos:
// a decisao usa so' o preco atual (bid na compra / ask na venda = preco de saida), sem olhar a frente. Sem estado
// alem da ultima M1 checada: reiniciar o EA no meio da posicao nao perde nada.
void VerificaBreakEven()
{
   if(BreakEvenMinutos <= 0) return;
   datetime m1 = iTime(_Symbol, PERIOD_M1, 0);
   if(m1 == g_ultima_m1) return;
   g_ultima_m1 = m1;
   if(!CotacaoValida()) return;

   datetime t_ent = iTime(_Symbol, TempoGrafico, iBarShift(_Symbol, TempoGrafico, (datetime)PositionGetInteger(POSITION_TIME)));
   if(m1 < t_ent + BreakEvenMinutos * 60) return;

   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double saida = compra ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double fl = (compra ? 1.0 : -1.0) * (saida - PositionGetDouble(POSITION_PRICE_OPEN));  // pontos a favor
   if(fl > BreakEvenColchaoPts) return;
   PrintFormat("Break-even: %s %.0f pts a favor <= %.1f (M1 %s) -> fecha a mercado", compra ? "compra" : "venda", fl,
               BreakEvenColchaoPts, TimeToString(m1, TIME_DATE | TIME_MINUTES));
   if(!trade.PositionClose(_Symbol))
      PrintFormat("ERRO fechar break-even: retcode=%u (%s) -- tenta de novo na proxima M1", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void Tick()
{
   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)
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

   datetime barra = iTime(_Symbol, TempoGrafico, 0);
   bool nova_barra = (barra != g_ultima_barra);
   g_ultima_barra = barra;

   if(tem_pos)
   {
      if(nova_barra) AtualizaPosicao();                       // stop/canal/esticada primeiro, como no simulador
      if(BreakEvenMinutos > 0 && SelecionaPosicao()) VerificaBreakEven();
      return;
   }
   if(!nova_barra) return;
   if(SoGerir) return;   // WinSeletor: troca pendente / robo nao selecionado: so' gere posicao, nao abre nova

   // Sinal da vela fechada de OUTRO dia (primeira barra do pregao) e' sinal velho: nao opera.
   if((long)(iTime(_Symbol, TempoGrafico, 1) / 86400) != (long)(barra / 86400)) return;

   int sinal = Sinal();
   if(sinal == 0) return;
   if(agora >= fim - MinutosSemEntrada) return;
   if(g_hora_bloqueada[MinutoDoDia(barra) / 60]) return;  // hora da vela que abriu: igual ao backtest
   if(PositionSelect(_Symbol)) return;  // posicao de outro robo/magic no simbolo: nao mexe

   double wma, smma, close1, atr;
   if(!LeMedias(wma, smma, close1) || !LeATR(atr)) return;
   if(!FiltrosAprovam(sinal, wma, smma, close1, atr)) return;
   if(!FiltrosNovosAprovam(sinal, barra)) return;

   if(GapDiaBloqueado()) { PrintFormat("Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)", sinal > 0 ? "COMPRA" : "VENDA"); return; }
   Entra(sinal, wma, atr);
}

// ---------------------------- fim da logica original ----------------------------

// WinSeletor: volta TODO o estado global do modulo ao valor inicial (o modulo pode ser religado
// na mesma execucao quando o dono troca de robo e depois volta a este).
void Reseta()
{
   g_h_smma = INVALID_HANDLE; g_h_wma = INVALID_HANDLE; g_h_smma15 = INVALID_HANDLE; g_h_wma15 = INVALID_HANDLE;
   g_ultima_barra = 0; g_ultima_m1 = 0;
   ArrayInitialize(g_hora_bloqueada, false);
   g_ticket_pos = 0; g_esticada_armada = false; g_pico_afastamento = -1.0e9;
   g_gap_dia_avaliado = -1; g_gap_bloqueado = false;
}

int Init()
{
   Reseta();
   Configura();
   int r = InitBase();
   if(r != INIT_SUCCEEDED) return r;

   return INIT_SUCCEEDED;
}

void Deinit(const int reason)
{

   DeinitBase(reason);
}

} // namespace WC1

#endif
