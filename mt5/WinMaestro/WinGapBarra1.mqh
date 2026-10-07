//+------------------------------------------------------------------+
//| WinMaestro/WinGapBarra1.mqh
//| WinGapBarra1 v1.01: gap do leilao contra o call + 1a barra M5 contra o gap (M5 fixo, sempre 1 contrato).
//|
//| Modulo do WinMaestro.mq5 v2.00, copiado de WinSeletor/WinGapBarra1.mqh. A logica de
//| SINAL e' a mesma; so' a camada de execucao mudou (desenho v2.2 sec. 7, spec Apendice A):
//|  - o modulo nao manda ordem: escreve a INTENCAO (ENTRAR / MANTER / NADA) e o maestro
//|    executa (a S nasce antes da E; alvo limite DAY; BE = mover a S);
//|  - AvaliaSinal -> ENTRAR(expira = g_exp); GerirPosicao -> MANTER(stop ou BE, alvo);
//|    depois de g_exp -> NADA; PendentesNossas/Zerar sairam (L1/L2 e zeragem pelo maestro);
//|  - posicao = ficha do robo (vista); hora = v.agora (no lugar de TimeCurrent);
//|  - fim do continuo pela grade (sem FimContinuoMin/RegimeAutomatico/ServerGMTOffsetH);
//|  - decisao anterior a' partida = DECISAO PERDIDA; estado persistido (Apendice A).
//| Adaptacoes marcadas com "WinMaestro:".
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_GAPBARRA1_MQH
#define WINMAESTRO_GAPBARRA1_MQH

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
int FlattenHora = 18;
int FlattenMinuto = 20;
bool EvitarVencimento = true;
// WinMaestro: o relogio do servidor e' Brasilia (AVISO no PRONTO se nao for, P22); input removido (spec 1).
const int ServerGMTOffsetH = 0;

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
   FlattenHora = GB_FlattenHora;
   FlattenMinuto = GB_FlattenMinuto;
   EvitarVencimento = GB_EvitarVencimento;
}

// ---------------------------- logica original ----------------------------
long     g_dkey      = -1;     // dia (data local BRT) em curso
bool     g_decidido  = false;  // sinal do dia ja' avaliado
bool     g_be_feito  = false;
datetime g_exp       = 0;      // validade da ordem de entrada (servidor)
datetime g_agora     = 0;      // WinMaestro: relogio da vista (v.agora)

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

// Minutos do fim do continuo na data, desde a abertura.
// WinMaestro: vem da grade embutida (F da data), no lugar de FimContinuoMin/RegimeAutomatico (spec 1, 9.1).
int FimContinuo(long key)
{
   return (int)((Mae_FDe((datetime)key) - (datetime)key) / 60) - (AberturaHora * 60 + AberturaMin);
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
int InitBase()
{
   if(StopPts <= 0.0 || TtlBarras < 1)
   {
      Print("ERRO: StopPts > 0 e TtlBarras >= 1.");
      return INIT_PARAMETERS_INCORRECT;
   }
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
// Posicao aberta: alvo (limite oposta, so' se ativado) e breakeven.
// WinMaestro: -> MANTER(stop, alvo). O stop e' o pedido (o SL anexado a' limite no original nao se move; o BE o move).
void GerirPosicao(const VistaRobo &v, Intencao &ped)
{
   double entr = Arredonda(v.preco);
   double st = (ped.tipo == INT_MANTER && ped.stop > 0.0) ? ped.stop : v.stop_pedido;
   double al = 0.0;
   double alvo = AlvoDist();
   if(alvo > 0.0)
      al = (v.lado > 0) ? Arredonda(entr + alvo) : Arredonda(entr - alvo);
   if(BeR > 0.0 && !g_be_feito)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double exc = (v.lado > 0) ? bid - entr : entr - ask;
      if(exc >= BeR * StopPts)
      {
         double novo = (v.lado > 0) ? entr + 5.0 : entr - 5.0;
         st = Arredonda(novo);
         g_be_feito = true;
      }
   }
   if(ped.tipo != INT_MANTER || !Mae_Igual(ped.stop, st) || !Mae_Igual(ped.alvo, al))
      Int_Manter(ped, st, al, g_be_feito ? "wgb1 break-even" : "wgb1 posicao");
}

//+------------------------------------------------------------------+
// Avalia o sinal do dia. Chamada no primeiro tick com barra 1 fechada.
void AvaliaSinal(datetime now, long key, Intencao &ped)
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
   // WinMaestro: momento da decisao = fechamento da barra 1; antes da partida = DECISAO PERDIDA.
   if(Ficha_DecisaoPerdida(R_GB, dia0 + abre + 300, "sinal do gap")) return;
   // WinMaestro: ENTRAR com a S no nivel do stop; validade SPECIFIED ate' g_exp se o simbolo aceita (decidido na partida), senao DAY.
   Int_Entrar(ped, Ficha_NovoId(R_GB), compra ? 1 : -1, preco, sl, exp, "wgb1 sinal do gap");
}

//+------------------------------------------------------------------+
void Tick(const VistaRobo &v, Intencao &ped)
{
   g_agora = v.agora;
   datetime now = g_agora;                                // WinMaestro: era TimeCurrent()
   long key = DateKey(now);
   if(key != g_dkey)
   {
      g_dkey = key; g_decidido = false; g_be_feito = false; g_exp = 0;
   }
   int sec = LocalSec(now);

   bool tem = v.tem;                                      // WinMaestro: a ficha do robo

   // Fim do dia: WinMaestro: a zeragem e' do maestro (I3 no horario do robo, limitado ao corte); o modulo so' para.
   if(sec >= FlattenSec(key)) return;

   // Validade da entrada: depois de g_exp -> NADA (o maestro cancela a E; backup da validade SPECIFIED).
   if(g_exp > 0 && now >= g_exp && ped.tipo == INT_ENTRAR) Int_Nada(ped, "wgb1 validade da entrada");

   if(tem)
   {
      GerirPosicao(v, ped);
      return;
   }
   // Sem posicao: alvo orfao -> L2 do maestro (WinMaestro).

   if(g_decidido) return;
   if(sec < AberturaHora * 3600 + AberturaMin * 60 + 300) return;   // a barra 1 fecha as 09:05
   AvaliaSinal(now, key, ped);
}

// ---------------------------- fim da logica original ----------------------------

// WinMaestro: volta TODO o estado global do modulo ao valor inicial (P17).
void Reseta()
{
   g_dkey = -1; g_decidido = false; g_be_feito = false; g_exp = 0; g_agora = 0;
}

// WinMaestro: estado persistido (Apendice A): g_decidido, g_exp, g_be_feito, data.
void Exporta()
{
   Mem_SetI("GB.dkey", g_dkey);
   Mem_SetB("GB.decidido", g_decidido);
   Mem_SetB("GB.be_feito", g_be_feito);
   Mem_SetI("GB.exp", (long)g_exp);
}

void Importa()
{
   if(!Car_Tem("GB.dkey")) return;
   g_dkey = Car_GetI("GB.dkey", -1);
   g_decidido = Car_GetB("GB.decidido", false);
   g_be_feito = Car_GetB("GB.be_feito", false);
   g_exp = (datetime)Car_GetI("GB.exp", 0);
}

// WinMaestro: avisos do maestro. Resposta: nao rearmar (g_decidido ja' impede outra entrada no dia).
void Evento(const SEvento &e, const VistaRobo &v, Intencao &ped) { }

// WinMaestro: stop pela regra do robo para a ficha atual: preco da ficha -/+ StopPts (0 sem ficha).
double StopRegra(const int lado)
{
   if(!Ficha_Tem(R_GB) || Ficha_Lado(R_GB) != lado) return 0.0;
   return Arredonda(Ficha_Preco(R_GB) - lado * StopPts);
}

// WinMaestro: horario proprio de zeragem (o maestro limita ao corte).
int MinutoZerarRobo(const datetime dia) { return FlattenHora * 60 + FlattenMinuto; }

int Init(const VistaRobo &v)
{
   Reseta();
   Configura();
   int r = InitBase();
   if(r != INIT_SUCCEEDED) return r;
   Importa();
   g_agora = v.agora;
   return INIT_SUCCEEDED;
}

void Deinit(const int reason) { }

} // namespace WGB1

#endif
