//+------------------------------------------------------------------+
//| WinSeletor/WinDeslocamentoMatinal.mqh
//| WinDeslocamentoMatinal v1.31: deslocamento da abertura as 10:30 (M1/D1), regra NaoOperarGapATR.
//|
//| Modulo do WinMaestro.mq5 v2.00, copiado de WinSeletor/WinDeslocamentoMatinal.mqh. A logica de
//| SINAL e' a mesma; so' a camada de execucao mudou (desenho v2.2 sec. 7, spec Apendice A):
//|  - o modulo escreve a INTENCAO: Decidir -> ENTRAR(limite, S pre-calculada no stop, B8);
//|    AjustarStop (no ENTRADA_EXECUTADA) -> MANTER(stop reancorado), SAIR se atravessado;
//|    TTL de 15 min -> NADA; g_ordem limpo so' no evento; VerificarStop saiu (a S no servidor
//|    e' o stop, B8, sec. 10);
//|  - posicao = ficha do robo (vista); o bloqueio "ja' existe posicao no simbolo" (L379) saiu;
//|  - teto de risco sobre DM_CAPITAL fixo (B9) no lugar de ACCOUNT_BALANCE;
//|  - zeragem e "pregao anterior" desligadas por flag (o maestro zera, spec 9.1);
//|  - o Deinit nao cancela a entrada (spec 10.4); estado persistido (Apendice A);
//|  - hora = v.agora (no lugar de TimeCurrent); decisao anterior a' partida = DECISAO PERDIDA.
//| Adaptacoes marcadas com "WinMaestro:" (as "WinSeletor:" sao da copia anterior).
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_DESLOCAMENTOMATINAL_MQH
#define WINMAESTRO_DESLOCAMENTOMATINAL_MQH

namespace WDM
{

// ---- inputs do EA original (mesmos nomes e padroes), preenchidos por Configura() ----
int MinutosDecisao = 90;
int JanelaDecisaoMin = 5;
double DeslocMinATR = 0.3;
double BandaATR = 0.05;
int PeriodoATR = 14;
int EntradaTTLMin = 15;
int MinutosZerar = 5;
int HoraFimPregao = 18;
int MinutoFimPregao = 25;
int FiltroMM = 0;
double RiscoMaxPct = 10.0;
const double Lote = 1.0;   // WinMaestro: lote fixo 1 (input removido, spec 1)
double NaoOperarGapATR = 1.0;

// WinMaestro: o maestro e' o unico dono das saidas por horario (spec 9.1); o codigo de zeragem abaixo fica desligado.
bool MaestroDonoHorario = true;

void Configura()
{
   MinutosDecisao = DM_MinutosDecisao;
   JanelaDecisaoMin = DM_JanelaDecisaoMin;
   DeslocMinATR = DM_DeslocMinATR;
   BandaATR = DM_BandaATR;
   PeriodoATR = DM_PeriodoATR;
   EntradaTTLMin = DM_EntradaTTLMin;
   MinutosZerar = DM_MinutosZerar;
   HoraFimPregao = DM_HoraFimPregao;
   MinutoFimPregao = DM_MinutoFimPregao;
   FiltroMM = DM_FiltroMM;
   RiscoMaxPct = DM_RiscoMaxPct;
   NaoOperarGapATR = DM_NaoOperarGapATR;
}

// ---------------------------- logica original ----------------------------
datetime g_dia            = 0;     // D1 do pregao corrente
bool     g_decidiu        = false; // ja' tomou a decisao do dia
ulong    g_ordem          = 0;     // limite de entrada pendente (WinMaestro: 1 = pedida ao maestro; 0 = nenhuma; limpo so' no evento)
long     g_id             = 0;     // WinMaestro: id_entrada da entrada pedida
datetime g_agora          = 0;     // WinMaestro: relogio da vista (v.agora), no lugar de TimeCurrent()
datetime Agora() { return g_agora; }
datetime g_ordemHora      = 0;
double   g_ordemPreco     = 0.0;
double   g_distStop       = 0.0;   // distancia limite->stop, para reancorar no preco executado
bool     g_stopAjustado   = false;
double   g_stopNivel      = 0.0;   // stop controlado pelo EA (ultimo negocio)
datetime g_ultimaM1       = 0;
int      g_hEma10         = INVALID_HANDLE;
int      g_hEma100        = INVALID_HANDLE;

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
   datetime agora = Agora();               // WinMaestro: era TimeCurrent()
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
   if(MinutosDecisao < 1 || DeslocMinATR <= 0 || PeriodoATR < 1 || EntradaTTLMin < 1)
   {
      Print("Parametros invalidos");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(FiltroMM < 0 || FiltroMM > 2) { Print("FiltroMM deve ser 0, 1 ou 2"); return INIT_PARAMETERS_INCORRECT; }
   if(FiltroMM >= 1) g_hEma100 = iMA(_Symbol, PERIOD_M5, 100, 0, MODE_EMA, PRICE_CLOSE);
   if(FiltroMM == 2) g_hEma10  = iMA(_Symbol, PERIOD_M5, 10, 0, MODE_EMA, PRICE_CLOSE);
   if((FiltroMM >= 1 && g_hEma100 == INVALID_HANDLE) || (FiltroMM == 2 && g_hEma10 == INVALID_HANDLE))
   {
      Print("Falha ao criar EMA");
      return INIT_FAILED;
   }
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
double NoTick(double preco)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0) return preco;
   return MathRound(preco / tick) * tick;
}

// ATR diario: media simples do True Range das PeriodoATR ultimas velas D1 fechadas.
double AtrDiario()
{
   MqlRates d[];
   ArraySetAsSeries(d, true);
   int n = PeriodoATR + 1;
   if(CopyRates(_Symbol, PERIOD_D1, 1, n, d) < n) return 0.0;
   double soma = 0.0;
   for(int i = 0; i < PeriodoATR; i++)
   {
      double tr = MathMax(d[i].high - d[i].low,
                  MathMax(MathAbs(d[i].high - d[i + 1].close), MathAbs(d[i].low - d[i + 1].close)));
      soma += tr;
   }
   return soma / PeriodoATR;
}

// Fim da sessao de negociacao de hoje (horario do servidor).
datetime FimSessao(datetime agora)
{
   MqlDateTime t;
   TimeToStruct(agora, t);
   datetime inicioDia = agora - (t.hour * 3600 + t.min * 60 + t.sec);
   datetime de, ate, fim = 0;
   for(uint s = 0; s < 10; s++)
   {
      if(!SymbolInfoSessionTrade(_Symbol, (ENUM_DAY_OF_WEEK)t.day_of_week, s, de, ate)) break;
      if(ate > fim) fim = ate;
   }
   if(fim > 0 && fim < 86400) return inicioDia + fim;
   return inicioDia + HoraFimPregao * 3600 + MinutoFimPregao * 60;
}

// WinMaestro: a posicao do robo e' a ficha dele (preco da ficha, lado, stop pedido; sem TP).
bool MinhaPosicao(double &preco, long &tipo, double &sl, double &tp, ulong &ticket)
{
   if(!Ficha_Tem(R_DM)) return false;
   preco  = Ficha_Preco(R_DM);
   tipo   = Ficha_Lado(R_DM) > 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   sl     = Ficha_Stop(R_DM);
   tp     = 0.0;
   ticket = Ficha_Id(R_DM);
   return true;
}

// WinMaestro: a entrada pedida ainda nao teve desfecho (g_ordem e' limpo so' nos eventos do maestro).
bool OrdemPendenteViva()
{
   return g_ordem != 0;
}

// WinMaestro: cancelar = intencao NADA (o maestro cancela a E e a S dela depois); a E so' e' esquecida no evento.
void CancelarEntrada(Intencao &ped, string motivo)
{
   if(!OrdemPendenteViva()) return;
   if(ped.tipo == INT_ENTRAR && ped.id_entrada == g_id)
   {
      Int_Nada(ped, "wdm cancela: " + motivo);
      PrintFormat("Entrada cancelada (%s)", motivo);
   }
}

void NovoDia(Intencao &ped, datetime dia)
{
   CancelarEntrada(ped, "novo pregao");
   g_dia          = dia;
   g_decidiu      = false;
   g_ordem        = 0;
   g_ordemHora    = 0;
   g_ordemPreco   = 0.0;
   g_distStop     = 0.0;
   g_stopAjustado = false;
   g_stopNivel    = 0.0;
   g_id           = 0;
}

// EMA da ultima vela M5 FECHADA (indice 1). Na decisao das 10:30 e' a vela 10:25,
// cujo fechamento e' o mesmo `ultimo` da M1 de 10:29.
double EmaFechada(int h)
{
   double v[];
   if(h == INVALID_HANDLE || CopyBuffer(h, 0, 1, 1, v) < 1) return 0.0;
   return v[0];
}

// Filtro de media (FiltroMM): o preco tem de estar do lado da operacao em relacao as EMAs.
bool FiltroMMPassa(int sinal, double preco)
{
   if(FiltroMM == 0) return true;
   double e100 = EmaFechada(g_hEma100);
   if(e100 <= 0) { Print("EMA100 indisponivel: dia em branco"); return false; }
   bool ok = sinal * (preco - e100) > 0;
   double e10 = 0.0;
   if(FiltroMM == 2)
   {
      e10 = EmaFechada(g_hEma10);
      if(e10 <= 0) { Print("EMA10 indisponivel: dia em branco"); return false; }
      ok = ok && sinal * (preco - e10) > 0;
   }
   PrintFormat("FiltroMM=%d: preco=%.0f EMA100=%.0f EMA10=%.0f -> %s",
               FiltroMM, preco, e100, e10, ok ? "passa" : "bloqueia");
   return ok;
}

//+------------------------------------------------------------------+
// Decisao das 10:30. Retorna sem fazer nada se ainda nao e' hora.
void Decidir(Intencao &ped, datetime agora)
{
   MqlRates m[];
   ArraySetAsSeries(m, false);
   int n = CopyRates(_Symbol, PERIOD_M1, g_dia, agora, m);
   if(n < 2) return;
   int fechadas = n - 1;                       // a ultima esta em formacao
   datetime primeira = m[0].time;
   double minutos = (double)(m[n - 1].time - primeira) / 60.0;  // abertura da vela em formacao
   if(minutos < MinutosDecisao) return;
   g_decidiu = true;
   if(minutos > MinutosDecisao + JanelaDecisaoMin)
   {
      PrintFormat("Decisao atrasada (%.0f min de pregao): dia em branco", minutos);
      return;
   }

   double atr = AtrDiario();
   if(atr <= 0) { Print("Sem ATR diario: dia em branco"); return; }

   double abertura = m[0].open;
   double banda    = BandaATR * atr;
   double ultimo   = m[fechadas - 1].close;
   double minC = DBL_MAX, maxC = -DBL_MAX;
   for(int i = 0; i < fechadas; i++)
   {
      minC = MathMin(minC, m[i].close);
      maxC = MathMax(maxC, m[i].close);
   }
   double desloc = ultimo - abertura;

   int    sinal = 0;
   double linha = 0.0;
   if(desloc >= DeslocMinATR * atr && minC >= abertura - banda)       { sinal =  1; linha = abertura - banda; }
   else if(-desloc >= DeslocMinATR * atr && maxC <= abertura + banda) { sinal = -1; linha = abertura + banda; }

   PrintFormat("Decisao: abertura=%.0f ultimo=%.0f desloc=%.2f ATR (ATR=%.0f) limpo_compra=%s limpo_venda=%s -> %s",
               abertura, ultimo, desloc / atr, atr,
               minC >= abertura - banda ? "sim" : "nao", maxC <= abertura + banda ? "sim" : "nao",
               sinal > 0 ? "COMPRA" : (sinal < 0 ? "VENDA" : "sem sinal"));
   if(sinal == 0) return;
   if(!FiltroMMPassa(sinal, ultimo)) return;
   // WinMaestro: o bloqueio "ja' existe posicao no simbolo" saiu (cada robo tem a sua ficha, spec 3.3).
   if(GapDiaBloqueado()) { PrintFormat("Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)", sinal > 0 ? "COMPRA" : "VENDA"); return; }

   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double limite = NoTick(ultimo);
   // Limite que ja' cruzou o livro viraria agressao: vai para a melhor oferta do proprio lado.
   if(sinal > 0 && ask > 0 && limite >= ask) limite = NoTick(bid > 0 ? MathMin(bid, ask - tick) : ask - tick);
   if(sinal < 0 && bid > 0 && limite <= bid) limite = NoTick(ask > 0 ? MathMax(ask, bid + tick) : bid + tick);

   g_distStop = MathMax(sinal * (limite - linha), tick);
   // Teto de risco: se o stop da linha custa mais que RiscoMaxPct% do saldo, aperta ate' o teto.
   if(RiscoMaxPct > 0)
   {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double vPonto = (tv > 0 && tick > 0) ? tv / tick : 0.2;   // R$ por ponto por contrato (WIN: 0,20)
      double saldo  = DM_CAPITAL;   // WinMaestro: teto sobre DM_CAPITAL fixo (B9), nao ACCOUNT_BALANCE
      double tetoRs = RiscoMaxPct / 100.0 * saldo;
      double tetoPts = MathFloor(tetoRs / (vPonto * Lote) / tick) * tick;
      tetoPts = MathMax(tetoPts, 2 * tick);
      if(g_distStop > tetoPts)
      {
         PrintFormat("Teto de risco: saldo=%.2f teto=R$%.2f -> stop apertado de %.0f para %.0f pts",
                     saldo, tetoRs, g_distStop, tetoPts);
         g_distStop = tetoPts;
      }
   }
   double stop = NoTick(limite - sinal * g_distStop);

   // WinMaestro: momento = abertura da M1 da decisao; antes da partida = DECISAO PERDIDA.
   if(Ficha_DecisaoPerdida(R_DM, m[n - 1].time, sinal > 0 ? "entrada COMPRA" : "entrada VENDA")) return;
   // WinMaestro: ENTRAR DAY com a S pre-calculada no stop (B8, spec 5.3).
   g_id = Ficha_NovoId(R_DM);
   Int_Entrar(ped, g_id, sinal, limite, stop, 0, sinal > 0 ? "desloc_matinal_compra" : "desloc_matinal_venda");
   g_ordem      = 1;
   g_ordemHora  = agora;
   g_ordemPreco = limite;
   PrintFormat("Limite %s %.0f pedida, stop %.0f (%.0f pts)",
               sinal > 0 ? "COMPRA" : "VENDA", limite, stop, g_distStop);
}

// Depois do preenchimento: stop reancorado ao preco executado (mesma distancia).
void AjustarStop(Intencao &ped)
{
   double preco, sl, tp; long tipo; ulong ticket;
   if(g_stopAjustado || !MinhaPosicao(preco, tipo, sl, tp, ticket)) return;
   g_stopAjustado = true;
   g_ordem = 0;
   if(g_distStop <= 0) return;
   g_stopNivel = NoTick(tipo == POSITION_TYPE_BUY ? preco - g_distStop : preco + g_distStop);
   PrintFormat("Executado a %.0f, stop em %.0f (bid=%.0f ask=%.0f last=%.0f)", preco, g_stopNivel,
               SymbolInfoDouble(_Symbol, SYMBOL_BID), SymbolInfoDouble(_Symbol, SYMBOL_ASK), SymbolInfoDouble(_Symbol, SYMBOL_LAST));
   // WinMaestro: o stop e' a S no servidor no proprio g_stopNivel (B8), movida no preenchimento: MANTER(stop reancorado).
   Int_Manter(ped, g_stopNivel, 0.0, "wdm stop reancorado no preco executado");
   // WinMaestro: nivel ja' atravessado pelo preco (fonte de preco do avulso, piso spec 5.3): SAIR.
   double ult = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
   if(ult <= 0) ult = SymbolInfoDouble(_Symbol, tipo == POSITION_TYPE_BUY ? SYMBOL_BID : SYMBOL_ASK);
   double piso = Ficha_PisoStop();
   if(ult > 0 && (tipo == POSITION_TYPE_BUY ? ult <= g_stopNivel + piso : ult >= g_stopNivel - piso))
   {
      Int_Sair(ped, "wdm stop (nivel ja' atravessado no preenchimento)");
      PrintFormat("Stop (last=%.0f, nivel=%.0f)", ult, g_stopNivel);
   }
}

// WinMaestro: VerificarStop saiu (desenho sec. 10): o stop e' a S no servidor (B8).
// B-10 (v2.01): mas o "nivel atravessado" e' reavaliado a CADA tick, nao so' no preenchimento: se um SAIR expirou
// (SAIDA_EXPIRADA) e o last continua alem de g_stopNivel (com o piso), o DM pede SAIR de novo.
void StopAtravessado(Intencao &ped)
{
   double preco, sl, tp; long tipo; ulong ticket;
   if(!g_stopAjustado || g_stopNivel <= 0 || ped.tipo == INT_SAIR || !MinhaPosicao(preco, tipo, sl, tp, ticket)) return;
   double ult = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
   if(ult <= 0) ult = SymbolInfoDouble(_Symbol, tipo == POSITION_TYPE_BUY ? SYMBOL_BID : SYMBOL_ASK);
   double piso = Ficha_PisoStop();
   if(ult > 0 && (tipo == POSITION_TYPE_BUY ? ult <= g_stopNivel + piso : ult >= g_stopNivel - piso))
   {
      Int_Sair(ped, "wdm stop (nivel atravessado)");
      PrintFormat("Stop (last=%.0f, nivel=%.0f)", ult, g_stopNivel);
   }
}

void Zerar(Intencao &ped, string motivo)
{
   if(MaestroDonoHorario) return;   // WinMaestro: zeragem pelo maestro (spec 9.1)
   double preco, sl, tp; long tipo; ulong ticket;
   if(!MinhaPosicao(preco, tipo, sl, tp, ticket)) return;
   Int_Sair(ped, "wdm zerar: " + motivo);
   PrintFormat("Zerado (%s)", motivo);
}

//+------------------------------------------------------------------+
void Tick(const VistaRobo &v, Intencao &ped)
{
   g_agora = v.agora;   // WinMaestro: o relogio da vista
   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)
   datetime agora = Agora();
   datetime dia   = iTime(_Symbol, PERIOD_D1, 0);
   if(dia == 0) return;
   if(dia != g_dia)
   {
      Zerar(ped, "posicao de pregao anterior");   // nunca carrega overnight (WinMaestro: pelo maestro, spec 9.3; desligado por flag)
      NovoDia(ped, dia);
   }

   AjustarStop(ped);
   StopAtravessado(ped);   // B-10

   // Prazo da limite de entrada.
   if(OrdemPendenteViva() && agora - g_ordemHora >= EntradaTTLMin * 60)
      CancelarEntrada(ped, "prazo");

   // Fim do pregao: cancela pendente e zera. WinMaestro: o maestro cancela e zera (spec 9.1); o retorno fica.
   if(agora >= FimSessao(agora) - MinutosZerar * 60)
   {
      if(!MaestroDonoHorario)
      {
         CancelarEntrada(ped, "fim do pregao");
         Zerar(ped, "fim do pregao");
      }
      return;
   }

   // Decisao so' na virada de vela M1.
   datetime m1 = iTime(_Symbol, PERIOD_M1, 0);
   if(m1 == g_ultimaM1) return;
   g_ultimaM1 = m1;
   if(!g_decidiu) Decidir(ped, agora);
}

void DeinitBase(const int reason)
{
   // WinMaestro: o Deinit nao cancela nada (spec 10.4): toda E ja' tem a sua S.
   if(g_hEma10 != INVALID_HANDLE) IndicatorRelease(g_hEma10);
   if(g_hEma100 != INVALID_HANDLE) IndicatorRelease(g_hEma100);
}

// ---------------------------- fim da logica original ----------------------------

// WinMaestro: volta TODO o estado global do modulo ao valor inicial (P17).
void Reseta()
{
   g_dia = 0; g_decidiu = false; g_ordem = 0; g_ordemHora = 0; g_ordemPreco = 0.0; g_distStop = 0.0;
   g_stopAjustado = false; g_stopNivel = 0.0; g_ultimaM1 = 0;
   g_hEma10 = INVALID_HANDLE; g_hEma100 = INVALID_HANDLE;
   g_gap_dia_avaliado = -1; g_gap_bloqueado = false;
   g_id = 0; g_agora = 0;
}

// WinMaestro: g_distStop da decisao das 10:30 refeita das barras M1 do dia (recuperacao sem memoria, Apendice A).
// Mesma conta de Decidir() ate' a distancia; o ajuste da limite ao livro no instante da decisao nao e'
// reproduzivel (usa o ultimo fechamento). 0 = sem decisao reconstruivel ou de lado diferente da ficha.
double DistStopDaDecisao(const int lado_ficha)
{
   datetime d0 = iTime(_Symbol, PERIOD_D1, 0);
   if(d0 == 0) return 0.0;
   MqlRates m[];
   ArraySetAsSeries(m, false);
   int n = CopyRates(_Symbol, PERIOD_M1, d0, Agora(), m);
   if(n < 2) return 0.0;
   int k = -1;
   for(int j = 1; j < n; j++)
      if((double)(m[j].time - m[0].time) / 60.0 >= MinutosDecisao) { k = j; break; }
   if(k < 1) return 0.0;
   int fechadas = k;
   double atr = AtrDiario();
   if(atr <= 0) return 0.0;
   double abertura = m[0].open;
   double banda    = BandaATR * atr;
   double ultimo   = m[fechadas - 1].close;
   double minC = DBL_MAX, maxC = -DBL_MAX;
   for(int j = 0; j < fechadas; j++) { minC = MathMin(minC, m[j].close); maxC = MathMax(maxC, m[j].close); }
   double desloc = ultimo - abertura;
   int    sinal = 0;
   double linha = 0.0;
   if(desloc >= DeslocMinATR * atr && minC >= abertura - banda)       { sinal =  1; linha = abertura - banda; }
   else if(-desloc >= DeslocMinATR * atr && maxC <= abertura + banda) { sinal = -1; linha = abertura + banda; }
   if(sinal == 0 || sinal != lado_ficha) return 0.0;
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double limite = NoTick(ultimo);
   double dist = MathMax(sinal * (limite - linha), tick);
   if(RiscoMaxPct > 0)
   {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double vPonto = (tv > 0 && tick > 0) ? tv / tick : 0.2;
      double tetoPts = MathFloor(RiscoMaxPct / 100.0 * DM_CAPITAL / (vPonto * Lote) / tick) * tick;
      tetoPts = MathMax(tetoPts, 2 * tick);
      if(dist > tetoPts) dist = tetoPts;
   }
   return dist;
}

// WinMaestro: estado persistido (Apendice A).
void Exporta()
{
   Mem_SetD("DM.stopNivel", g_stopNivel);
   Mem_SetD("DM.distStop", g_distStop);
   Mem_SetB("DM.stopAjustado", g_stopAjustado);
   Mem_SetB("DM.decidiu", g_decidiu);
   Mem_SetI("DM.dia", (long)g_dia);
   Mem_SetI("DM.ordemHora", (long)g_ordemHora);
   Mem_SetD("DM.ordemPreco", g_ordemPreco);
   Mem_SetI("DM.ordem", (long)g_ordem);
   Mem_SetI("DM.id", g_id);
}

bool Importa()
{
   if(!Car_Tem("DM.dia")) return false;
   g_stopNivel = Car_GetD("DM.stopNivel", 0.0);
   g_distStop = Car_GetD("DM.distStop", 0.0);
   g_stopAjustado = Car_GetB("DM.stopAjustado", false);
   g_decidiu = Car_GetB("DM.decidiu", false);
   g_dia = (datetime)Car_GetI("DM.dia", 0);
   g_ordemHora = (datetime)Car_GetI("DM.ordemHora", 0);
   g_ordemPreco = Car_GetD("DM.ordemPreco", 0.0);
   g_ordem = (ulong)Car_GetI("DM.ordem", 0);
   g_id = Car_GetI("DM.id", 0);
   return true;
}

// WinMaestro: avisos do maestro. ENTRADA_EXECUTADA -> AjustarStop (MANTER no stop reancorado). Cancelada,
// recusada ou perdida -> a entrada deixa de ser rastreada (g_ordem = 0); nao rearma (g_decidiu segue true).
void Evento(const SEvento &e, const VistaRobo &v, Intencao &ped)
{
   if(e.ev == EV_ENTRADA_EXECUTADA) { AjustarStop(ped); return; }
   if((e.ev == EV_ENTRADA_CANCELADA || e.ev == EV_ENTRADA_RECUSADA || e.ev == EV_ENTRADA_PERDIDA) && e.id_entrada == g_id) g_ordem = 0;
}

// WinMaestro: stop pela regra do robo: preco da ficha -/+ g_distStop (refeito das barras sem memoria).
double StopRegra(const int lado)
{
   if(!Ficha_Tem(R_DM) || Ficha_Lado(R_DM) != lado) return 0.0;
   double dist = (g_distStop > 0) ? g_distStop : DistStopDaDecisao(lado);
   if(dist <= 0) return 0.0;
   return NoTick(Ficha_Preco(R_DM) - lado * dist);
}

// WinMaestro: horario proprio de zeragem = fim do continuo da grade - MinutosZerar (o maestro limita ao corte).
// B-13 (v2.01): o fim vem da MESMA FimSessao do Tick (sessao do simbolo; sem ela, os inputs HoraFimPregao/MinutoFimPregao),
// como o C1 respeita os seus inputs; antes vinha da grade do maestro e ignorava os inputs do DM.
int MinutoZerarRobo(const datetime dia) { return (int)((FimSessao(dia + 12 * 3600) - dia) / 60) - MinutosZerar; }

int Init(const VistaRobo &v)
{
   Reseta();
   Configura();
   int r = InitBase();
   if(r != INIT_SUCCEEDED) return r;
   g_agora = v.agora;
   if(Importa()) return INIT_SUCCEEDED;
   // WinMaestro: sem memoria, com ficha DESTE robo aberta HOJE: o pregao de hoje ja' conta como iniciado e a
   // decisao como tomada; o stop e' refeito das barras (a S no servidor ja' protege).
   datetime d0 = iTime(_Symbol, PERIOD_D1, 0);
   if(d0 != 0 && Ficha_Tem(R_DM) && Ficha_Hora(R_DM) >= d0)
   {
      g_dia = d0;
      g_decidiu = true;
      g_stopAjustado = true;
      g_distStop = DistStopDaDecisao(Ficha_Lado(R_DM));
      if(g_distStop > 0) g_stopNivel = NoTick(Ficha_Preco(R_DM) - Ficha_Lado(R_DM) * g_distStop);
   }
   return INIT_SUCCEEDED;
}

void Deinit(const int reason)
{
   DeinitBase(reason);
}

} // namespace WDM

#endif
