//+------------------------------------------------------------------+
//| WinSeletor/WinGapBarra1.mqh
//| WinGapBarra1 v1.01: gap do leilao contra o call + 1a barra M5 contra o gap (M5 fixo, sempre 1 contrato).
//|
//| Modulo do WinSeletor.mq5. A logica e' a de mt5/WinGapBarra1.mq5 copiada SEM
//| alteracao de regra: so' mudaram escopo (tudo dentro do namespace
//| WGB1, para os nomes de variavel/funcao nao colidirem com os outros 4
//| robos), os inputs viram variaveis de mesmo nome preenchidas por
//| Configura() a partir dos inputs GB_* do EA, e os eventos
//| OnInit/OnTick/OnDeinit viram Init/Tick/Deinit. Adaptacoes de
//| seletor estao marcadas com "WinSeletor:" no codigo.
//| Gerado por scripts de build a partir do EA original; nao editar a
//| logica aqui sem editar o EA original (e vice-versa).
//+------------------------------------------------------------------+
#ifndef WINSELETOR_GAPBARRA1_MQH
#define WINSELETOR_GAPBARRA1_MQH

namespace WGB1
{

// ---- inputs do EA original (mesmos nomes e padroes), preenchidos por Configura() ----
double StopPts = 1200;
double AlvoPts = 0;
double AlvoR = 0;
double BeR = 0;
int RecuoPts = 0;
int TtlBarras = 6;
int GapMinPts = 5;
int AberturaHora = 9;
int AberturaMin = 0;
int FimContinuoMin = 565;
int FlattenHora = 18;
int FlattenMinuto = 20;
bool EvitarVencimento = true;
int ServerGMTOffsetH = 0;
bool RegimeAutomatico = true;
ulong MagicNumber = 80080601;

// WinSeletor: true = robo so' GERE o que ja' existe (saidas, stop, break-even, zeragem, validade das ordens);
// nao arma entrada nova. Usado enquanto uma troca de robo espera a posicao fechar.
bool SoGerir = false;

void Configura()
{
   StopPts = GB_StopPts;
   AlvoPts = GB_AlvoPts;
   AlvoR = GB_AlvoR;
   BeR = GB_BeR;
   RecuoPts = GB_RecuoPts;
   TtlBarras = GB_TtlBarras;
   GapMinPts = GB_GapMinPts;
   AberturaHora = GB_AberturaHora;
   AberturaMin = GB_AberturaMin;
   FimContinuoMin = GB_FimContinuoMin;
   FlattenHora = GB_FlattenHora;
   FlattenMinuto = GB_FlattenMinuto;
   EvitarVencimento = GB_EvitarVencimento;
   ServerGMTOffsetH = GB_ServerGMTOffsetH;
   RegimeAutomatico = GB_RegimeAutomatico;
   MagicNumber = GB_MagicNumber;
}

void DefineSoGerir(const bool v) { SoGerir = v; }

// WinSeletor: ha posicao ou ordem pendente deste robo (magic proprio, simbolo do grafico)?
bool Tem() { return WinTemPosOuOrdens(MagicNumber); }

// ---------------------------- logica original ----------------------------
CTrade   trade;

long     g_dkey      = -1;     // dia (data local BRT) em curso
bool     g_decidido  = false;  // sinal do dia ja' avaliado
bool     g_be_feito  = false;
datetime g_exp       = 0;      // validade da ordem de entrada (servidor)

const string COM_ENT  = "wgb1 E";
const string COM_ALVO = "wgb1 A";

//+------------------------------------------------------------------+
// Segundos do dia no relogio de Brasilia.
int LocalSec(datetime srv)
{
   return (int)((((long)srv + (long)ServerGMTOffsetH * 3600) % 86400 + 86400) % 86400);
}
// Data (meia-noite) no relogio de Brasilia, como "chave de dia".
long DateKey(datetime srv)
{
   return (((long)srv + (long)ServerGMTOffsetH * 3600) / 86400) * 86400;
}
// Meia-noite local da chave convertida para o relogio do servidor.
datetime DiaSrv(long key)
{
   return (datetime)(key - (long)ServerGMTOffsetH * 3600);
}

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime VencimentoWIN(int ano, int mes)
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

// Primeiro domingo a partir do dia 'dia' do mes (ano, mes).
datetime DomingoDoMes(int ano, int mes, int dia)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = dia;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   return t + ((7 - d.day_of_week) % 7) * 86400;
}

// Verao dos EUA: 2o domingo de marco ate' 1o domingo de novembro.
bool VeraoEUA(long key)
{
   MqlDateTime d; TimeToStruct((datetime)key, d);
   datetime ini = DomingoDoMes(d.year, 3, 8);
   datetime fim = DomingoDoMes(d.year, 11, 1);
   return (datetime)key >= ini && (datetime)key < fim;
}

// Minutos do fim do continuo na data (regime da grade B3).
int FimContinuo(long key)
{
   int fim = FimContinuoMin;
   if(RegimeAutomatico && key < (long)D'2024.03.11' && VeraoEUA(key) && fim > 535) fim = 535;
   return fim;
}

// Segundo do dia (BRT) a partir do qual zera: min(Flatten configurado, fim do continuo - 5 min).
int FlattenSec(long key)
{
   int cfg = FlattenHora * 3600 + FlattenMinuto * 60;
   int lim = AberturaHora * 3600 + AberturaMin * 60 + (FimContinuo(key) - 5) * 60;
   return MathMin(cfg, lim);
}

//+------------------------------------------------------------------+
double Arredonda(double preco)
{
   double tk = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tk <= 0.0) tk = 5.0;
   return NormalizeDouble(MathRound(preco / tk) * tk, _Digits);
}

double TickSize()
{
   double tk = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return tk > 0.0 ? tk : 5.0;
}

double AlvoDist()
{
   if(AlvoPts > 0.0) return AlvoPts;
   if(AlvoR > 0.0)   return AlvoR * StopPts;
   return 0.0;
}

//+------------------------------------------------------------------+
bool PosicaoNossa(ulong &ticket, ENUM_POSITION_TYPE &tipo, double &preco, double &vol)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      ticket = tk;
      tipo   = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      preco  = PositionGetDouble(POSITION_PRICE_OPEN);
      vol    = PositionGetDouble(POSITION_VOLUME);
      return true;
   }
   return false;
}

// Conta ordens pendentes nossas com o comentario dado ("" = todas); apaga se apagar = true.
int PendentesNossas(const string com, bool apagar)
{
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
      if(com != "" && OrderGetString(ORDER_COMMENT) != com) continue;
      n++;
      if(apagar) trade.OrderDelete(tk);
   }
   return n;
}

//+------------------------------------------------------------------+
int InitBase()
{
   // WinSeletor: aviso de periodo do grafico removido (o modulo le M5 sozinho, qualquer grafico serve).
   if(StopPts <= 0.0 || TtlBarras < 1)
   {
      Print("ERRO: StopPts > 0 e TtlBarras >= 1.");
      return INIT_PARAMETERS_INCORRECT;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFilling(ORDER_FILLING_RETURN);
   trade.SetDeviationInPoints(0);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void Zerar()
{
   ulong tk; ENUM_POSITION_TYPE tp; double pr, vol;
   if(PosicaoNossa(tk, tp, pr, vol))
   {
      if(!trade.PositionClose(tk))
         PrintFormat("Zerar: falhou (%d %s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
   PendentesNossas("", true);
}

// Posicao aberta: alvo (limite oposta, so' se ativado) e breakeven.
void GerirPosicao(ulong tk, ENUM_POSITION_TYPE tp, double entrada, double vol)
{
   double entr = Arredonda(entrada);
   double alvo = AlvoDist();
   if(alvo > 0.0 && PendentesNossas(COM_ALVO, false) == 0)
   {
      if(tp == POSITION_TYPE_BUY)
         trade.SellLimit(vol, Arredonda(entr + alvo), _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, COM_ALVO);
      else
         trade.BuyLimit(vol, Arredonda(entr - alvo), _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, COM_ALVO);
   }
   if(BeR > 0.0 && !g_be_feito)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double exc = (tp == POSITION_TYPE_BUY) ? bid - entr : entr - ask;
      if(exc >= BeR * StopPts)
      {
         double novo = (tp == POSITION_TYPE_BUY) ? entr + 5.0 : entr - 5.0;
         if(trade.PositionModify(tk, Arredonda(novo), 0.0)) g_be_feito = true;
      }
   }
}

//+------------------------------------------------------------------+
// Avalia o sinal do dia. Chamada no primeiro tick com barra 1 fechada.
void AvaliaSinal(datetime now, long key)
{
   int abre = AberturaHora * 3600 + AberturaMin * 60;
   datetime dia0 = DiaSrv(key);

   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M5, dia0, now, r);
   if(n < 2) return;                                   // barra 1 ainda nao fechou: espera o proximo tick
   g_decidido = true;                                   // a partir daqui o dia esta' decidido, com ou sem sinal

   if(r[0].time != dia0 + abre)
   {
      PrintFormat("Sem sinal: 1a barra do dia abre %s, nao %02d:%02d.", TimeToString(r[0].time, TIME_DATE | TIME_MINUTES), AberturaHora, AberturaMin);
      return;
   }
   // Ordem so' vale ate' a validade; tick tardio (EA ligado depois) nao opera.
   datetime exp = dia0 + abre + TtlBarras * 300;
   if(now >= exp) { Print("Sem sinal: janela de entrada ja' encerrada."); return; }

   // Ultima barra M5 do pregao anterior (carrega o call).
   MqlRates p[];
   int np = CopyRates(_Symbol, PERIOD_M5, dia0 - 7 * 86400, dia0 - 1, p);
   if(np < 1) { Print("Sem sinal: nao ha' barra do pregao anterior."); return; }
   long key_ant = DateKey(p[np - 1].time);
   if((key - key_ant) / 86400 > 5) { Print("Sem sinal: pregao anterior a mais de 5 dias."); return; }

   if(EvitarVencimento)
   {
      MqlDateTime a, h; TimeToStruct((datetime)key_ant, a); TimeToStruct((datetime)key, h);
      int ano = a.year, mes = a.mon;
      while(ano < h.year || (ano == h.year && mes <= h.mon))
      {
         if(mes % 2 == 0)
         {
            datetime v = VencimentoWIN(ano, mes);
            if((long)v > key_ant && (long)v <= key)
            {
               PrintFormat("Sem sinal: %s e' a 1a sessao depois do vencimento (%s); troca de contrato.",
                           TimeToString((datetime)key, TIME_DATE), TimeToString(v, TIME_DATE));
               return;
            }
         }
         mes++; if(mes > 12) { mes = 1; ano++; }
      }
   }

   double leilao = r[0].open;
   double call   = p[np - 1].close;
   double gap    = leilao - call;
   if(MathAbs(gap) < (double)GapMinPts || gap == 0.0) return;
   double corpo = r[0].close - r[0].open;
   if(corpo == 0.0) return;

   bool compra;
   if(gap > 0.0 && corpo < 0.0)      compra = false;
   else if(gap < 0.0 && corpo > 0.0) compra = true;
   else return;                                         // barra a favor do gap: sem sinal

   const double vol = 1.0;                                // sempre 1 contrato (ordem do dono, 2026-10-06)

   double tk = TickSize();
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double preco = Arredonda(compra ? r[0].close - RecuoPts : r[0].close + RecuoPts);
   // Limite so' e' aceito do lado de dentro do livro; se o mercado ja' passou do preco, fica na melhor oferta (nunca a mercado).
   if(compra && ask > 0.0 && preco >= ask) preco = Arredonda(ask - tk);
   if(!compra && bid > 0.0 && preco <= bid) preco = Arredonda(bid + tk);

   double sl = compra ? preco - StopPts : preco + StopPts;
   sl = Arredonda(sl);

   PrintFormat("Sinal %s: leilao %.0f, call %.0f, gap %.0f pts; barra 1 %.0f -> %.0f; limite %.0f, stop %.0f, %.0f contrato(s), validade %s.",
               compra ? "COMPRA" : "VENDA", leilao, call, gap, r[0].open, r[0].close, preco, sl, vol, TimeToString(exp, TIME_MINUTES));

   g_exp = exp;
   bool ok;
   if(compra) ok = trade.BuyLimit(vol, preco, _Symbol, sl, 0.0, ORDER_TIME_SPECIFIED, exp, COM_ENT);
   else       ok = trade.SellLimit(vol, preco, _Symbol, sl, 0.0, ORDER_TIME_SPECIFIED, exp, COM_ENT);
   if(!ok)
   {
      PrintFormat("Ordem com validade rejeitada (%d %s); tentando validade do dia (o EA cancela em %s).",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription(), TimeToString(exp, TIME_MINUTES));
      if(compra) ok = trade.BuyLimit(vol, preco, _Symbol, sl, 0.0, ORDER_TIME_DAY, 0, COM_ENT);
      else       ok = trade.SellLimit(vol, preco, _Symbol, sl, 0.0, ORDER_TIME_DAY, 0, COM_ENT);
      if(!ok) PrintFormat("Ordem rejeitada: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
void Tick()
{
   datetime now = TimeCurrent();
   long key = DateKey(now);
   if(key != g_dkey)
   {
      g_dkey = key; g_decidido = false; g_be_feito = false; g_exp = 0;
   }
   int sec = LocalSec(now);

   ulong tk; ENUM_POSITION_TYPE tp; double pr, vol;
   bool tem = PosicaoNossa(tk, tp, pr, vol);

   // Fim do dia: zera a mercado e apaga o que sobrou. Nunca dentro do call.
   if(sec >= FlattenSec(key))
   {
      if(tem || PendentesNossas("", false) > 0) Zerar();
      return;
   }

   // Validade da entrada (backup para o caso de a corretora ignorar o prazo).
   if(g_exp > 0 && now >= g_exp) PendentesNossas(COM_ENT, true);

   if(tem)
   {
      GerirPosicao(tk, tp, pr, vol);
      return;
   }
   // Sem posicao: alvo orfao nao fica no livro.
   if(PendentesNossas(COM_ALVO, false) > 0) PendentesNossas(COM_ALVO, true);

   if(g_decidido) return;
   if(sec < AberturaHora * 3600 + AberturaMin * 60 + 300) return;   // a barra 1 fecha as 09:05
   if(SoGerir) return;   // WinSeletor: troca pendente / robo nao selecionado: nao avalia sinal novo
   AvaliaSinal(now, key);
}

void DeinitBase(const int reason) { }


// ---------------------------- fim da logica original ----------------------------

// WinSeletor: volta TODO o estado global do modulo ao valor inicial (o modulo pode ser religado
// na mesma execucao quando o dono troca de robo e depois volta a este).
void Reseta()
{
   g_dkey = -1; g_decidido = false; g_be_feito = false; g_exp = 0;
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

} // namespace WGB1

#endif
