//+------------------------------------------------------------------+
//| LarryWilliams.mq5                                                |
//| Setups de Larry Williams (scripts/larry_williams/ESPECIFICACAO.md)|
//|                                                                  |
//| Um unico EA, um bool por setup. Sinais SOMENTE com barras D1     |
//| fechadas (shift>=1) + abertura do dia corrente (sem look-ahead). |
//| UMA posicao por vez por magic/simbolo.                           |
//|                                                                  |
//| PRIORIDADE (varios setups ligados): VB > OOPS > SMASH > HSMASH   |
//| > OUTSIDE > GSV > WR > UO > TDM > TDW. O primeiro que gerar sinal|
//| no dia vale; os demais nao sao avaliados naquele dia.            |
//| TRES_BARRAS (intradiario, so' ordens LIMITE) roda em paralelo,   |
//| mas ainda sujeito a regra de uma posicao por vez.                |
//|                                                                  |
//| DESVIO DECLARADO do desenho "fechado" do repo: VB/OOPS/SMASH/    |
//| HSMASH entram por ordem STOP (viram mercado ao disparar) e o     |
//| stop de protecao e' nativo. OUTSIDE/WR/UO/TDM/TDW entram na      |
//| abertura (a mercado, fiel ao livro) ou por LIMITE no fechamento  |
//| de S. Isto reproduz Larry fielmente, a pedido do dono; so'       |
//| TRES_BARRAS e' 100% limite.                                      |
//|                                                                  |
//| [INTERP] marca decisoes de interpretacao (ver DECISOES.md).      |
//| Horarios sao do SERVIDOR do MT5. Sem portao de capital/margem.   |
//| Log: Print + CSV LW_trades_<simbolo>_<setup>.csv                 |
//|      (data;lado;entrada;saida;motivo;pnl_pts)                    |
//+------------------------------------------------------------------+
#property copyright "larry_williams"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

CTrade trade;

//--- enums
enum ENUM_MODO_SAIDA
{
   SAIDA_BAILOUT,            // Primeira abertura lucrativa (apos BailoutAposDias)
   SAIDA_FECHAMENTO,         // Fecha no fim do pregao do dia da entrada
   SAIDA_TEMPO_N,            // Fecha no fim do pregao do N-esimo dia (0 = dia da entrada)
   SAIDA_REVERSAO,           // Sai quando surge sinal oposto (so' vale se o setup o gera)
   SAIDA_ABERTURA_SEGUINTE,  // Fecha na abertura do dia seguinte (Oops: "1,5 dia")
   SAIDA_ALVO_RR,            // Alvo nativo = RRAlvo x distancia do stop (SMASH)
   SAIDA_INDICADOR           // Saida do proprio indicador (UO, WR); outros setups: BAILOUT
};
enum ENUM_STOP_MODO { STOP_FRAC_R1, STOP_ATR };
enum ENUM_TEND { TEND_NENHUM, TEND_SWING, TEND_SMA };
enum ENUM_ENTRADA_ABERTURA { ENTRADA_MERCADO_ABERTURA, ENTRADA_LIMITE_FECHAMENTO_S };

//--- inputs: escolha de setup
input bool   UsarVB            = true;   // VB: Volatility Breakout (buy/sell stop a partir da abertura)
input bool   UsarOops          = false;  // OOPS: gap alem da max/min de ontem, entra na volta
input bool   UsarSmash         = false;  // SMASH: naked close, rompe a max/min do dia do setup
input bool   UsarHiddenSmash   = false;  // HSMASH: hidden smash day
input bool   UsarOutside       = false;  // OUTSIDE: outside day com fechamento fora
input bool   UsarGSV           = false;  // GSV: Greatest Swing Value
input bool   UsarWR            = false;  // WR: Williams %R
input bool   UsarUO            = false;  // UO: Ultimate Oscillator (divergencia)
input bool   UsarTDM           = false;  // TDM: dia de pregao do mes
input bool   UsarTDW           = false;  // TDW: dia da semana (setup proprio)
input bool   UsarTresBarras    = false;  // TRES_BARRAS: intradiario, entrada e alvo LIMITE
input bool   PermiteCompra     = true;   // Liga o lado comprado
input bool   PermiteVenda      = true;   // Liga o lado vendido

//--- inputs: saida e stop (valores do livro/especificacao por ora -- trocar aqui pelos recomendados)
input ENUM_MODO_SAIDA ModoSaida = SAIDA_BAILOUT; // Modo de saida (vale para todos os setups diarios)
input int    SaidaDias         = 3;      // N dias, no modo SAIDA_TEMPO_N
input int    BailoutAposDias   = 0;      // Bailout: esperar N dias antes de aceitar (livro: 0 a 2)
input double RRAlvo            = 2.0;    // Alvo/stop, no modo SAIDA_ALVO_RR
input ENUM_STOP_MODO StopModo  = STOP_FRAC_R1; // Base do stop: range de ontem (R1) ou ATR
input double StopFrac          = 0.5;    // Stop = StopFrac x (R1 ou ATR) [INTERP: US$ do livro -> fracao]; 0 = sem stop
input int    AtrPeriodo        = 14;     // Periodo do ATR (StopModo = STOP_ATR)

//--- inputs: parametros por setup
input double VB_Kc             = 0.5;    // VB: compra em abertura + Kc x R1
input double VB_Kv             = 0.5;    // VB: venda em abertura - Kv x R1
input double Oops_GapMin       = 0.0;    // OOPS: gap minimo, fracao de R1 (0 = qualquer gap)
input bool   Oops_CompraApos17 = false;  // OOPS: comprar so' depois do 17o pregao do mes (livro)
input int    Smash_N           = 1;      // SMASH: fecha abaixo da minima dos N dias anteriores (livro 3-8)
input bool   Smash_ExcluirOutside = false; // SMASH: ignora se o dia do setup e' outside bar
input bool   Smash_StopExtremo = true;   // SMASH/HSMASH: stop no extremo oposto do dia do setup [SEC]; false = StopFrac
input double HS_Zona           = 0.25;   // HSMASH: fechamento nos 25% extremos do range
input bool   HS_ExigeCloseOposto = false; // HSMASH: "melhores" (fecha abaixo/acima da abertura)
input ENUM_ENTRADA_ABERTURA EntradaNaAbertura = ENTRADA_MERCADO_ABERTURA; // OUTSIDE/WR/UO/TDM/TDW: mercado na abertura ou LIMITE em C(S)
input bool   Outside_LadoVenda = false;  // OUTSIDE: liga o lado venda [INTERP; livro silencioso]
input bool   Outside_EvitaQuinta = true; // OUTSIDE: nao entra na quinta (livro)
input int    GSV_N             = 4;      // GSV: media dos ultimos N dias (livro: 4)
input double GSV_Kc            = 0.8;    // GSV: compra em abertura + Kc x media
input double GSV_Kv            = 1.2;    // GSV: venda em abertura - Kv x media
input int    WR_Periodo        = 10;     // WR: periodo do %R (livro 10; 14 variacao)
input int    WR_Espera         = 5;      // WR: pregoes de espera apos tocar 100/0
input double WR_NivelCompra    = 95.0;   // WR: compra quando %R volta abaixo disto (85-95)
input double WR_NivelVenda     = 5.0;    // WR: venda quando %R volta acima disto (5-15)
input int    WR_Janela         = 30;     // WR: ate' quantos pregoes atras buscar o toque
input int    UO_P1             = 7;      // UO: periodo curto
input int    UO_P2             = 14;     // UO: periodo medio
input int    UO_P3             = 28;     // UO: periodo longo
input double UO_NivelCompra    = 30.0;   // UO: 1a minima da divergencia altista abaixo disto
input double UO_NivelVenda     = 50.0;   // UO: 1o topo da divergencia baixista acima disto (artigo 1985; moderno 70)
input int    UO_Janela         = 40;     // UO: distancia maxima entre os dois pivos, em pregoes
input string TDM_DiasCompra    = "1";    // TDM: dias de pregao do mes p/ comprar (csv; livro: 1)
input string TDM_DiasVenda     = "";     // TDM: dias de pregao do mes p/ vender (csv; vazio = nenhum)
input string TDW_DiasCompra    = "1";    // TDW: dias da semana p/ comprar (1=seg..5=sex, ex "15")
input string TDW_DiasVenda     = "";     // TDW: dias da semana p/ vender
input ENUM_TIMEFRAMES TB_Timeframe = PERIOD_M5; // TRES_BARRAS: timeframe (M5/M15)
input double TB_StopFrac       = 0.5;    // TRES_BARRAS: stop = fracao x R1 diario
input int    TB_HoraUltimaEntrada = 17;  // TRES_BARRAS: hora (servidor) a partir da qual nao arma entrada
input int    TB_MinUltimaEntrada  = 0;   // TRES_BARRAS: minuto da hora acima

//--- inputs: filtros
input ENUM_TEND Tend_Geral     = TEND_NENHUM; // Filtro de tendencia em todos os setups diarios
input ENUM_TEND Tend_WR        = TEND_SWING;  // Filtro de tendencia do WR (obrigatorio no livro)
input ENUM_TEND Tend_3B        = TEND_SWING;  // Filtro de tendencia do TRES_BARRAS
input int    Tend_SMA_N        = 50;     // Periodo da SMA quando o filtro e' TEND_SMA
input string FiltroDiasCompra  = "12345"; // Dias da semana permitidos p/ comprar (1=seg..5=sex)
input string FiltroDiasVenda   = "12345"; // Dias da semana permitidos p/ vender
input string FiltroMeses       = "1,2,3,4,5,6,7,8,9,10,11,12"; // Meses permitidos (csv)

//--- inputs: execucao
input double Lote              = 1.0;    // Volume por operacao (normalizado a volume_min/step)
input int    HoraAbertura      = 9;      // Hora (servidor) da abertura do pregao
input int    MinAbertura       = 0;      // Minuto da abertura
input int    DelayAbertura     = 1;      // Minutos apos a abertura para armar ordens do dia
input int    HoraFim           = 17;     // Hora (servidor) do fim do pregao (cancela pendentes / fecha)
input int    MinFim            = 50;     // Minuto do fim
input int    DesvioPontos      = 50;     // Desvio maximo (pontos) das ordens a mercado
input ulong  MagicNumber       = 20261004; // Identifica as ordens deste EA
input bool   LogComum          = true;   // CSV na pasta Common\Files (facil de achar no Testador); false = MQL5\Files

//--- estruturas
struct Plano
{
   bool            ativo;
   int             lado;      // +1 compra, -1 venda
   ENUM_ORDER_TYPE tipo;      // BUY/SELL (mercado), BUY_STOP/SELL_STOP, BUY_LIMIT/SELL_LIMIT
   double          preco;     // nivel da ordem pendente (0 p/ mercado)
   double          dist_sl;   // distancia do stop ate' o preco de entrada (0 = sem)
   double          dist_tp;   // distancia do alvo nativo (0 = sem)
   string          setup;
};

//--- estado
MqlRates g_r[];                 // D1, serie: [0]=hoje, [1]=ontem (S)
datetime g_dia = 0;
bool     g_aberto_proc = false;
string   g_setup_dia = "";
bool     g_dia_ok[8], g_dia_ok_v[8];   // filtros por dia da semana (0=dom..6=sab)
bool     g_mes_ok[13];
bool     g_tdw_c[8], g_tdw_v[8];
int      g_tdm_c[], g_tdm_v[];

// posicao e log
bool     g_em_pos = false;
ulong    g_pos_id = 0;
double   g_entrada = 0.0;
datetime g_entrada_t = 0;
int      g_lado_pos = 0;
string   g_setup_pos = "";
string   g_motivo = "";
bool     g_passou50 = false;
ulong    g_ticket_alvo = 0;
datetime g_ult_barra_tb = 0;

//+------------------------------------------------------------------+
// utilitarios
//+------------------------------------------------------------------+
double TickSz()
{
   double t = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return (t > 0.0) ? t : _Point;
}

double NormPreco(const double p)
{
   double t = TickSz();
   return NormalizeDouble(MathRound(p / t) * t, _Digits);
}

double NormLote(const double v)
{
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(st <= 0.0) st = mn;
   double r = MathFloor(v / st + 1e-9) * st;
   if(r < mn) r = mn;
   if(mx > 0.0 && r > mx) r = mx;
   return NormalizeDouble(r, 8);
}

int MinDoDia(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return d.hour * 60 + d.min;
}

bool AposHora(const int h, const int m) { return MinDoDia(TimeCurrent()) >= h * 60 + m; }

int DiaSemana(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return d.day_of_week;
}

int MesDe(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return d.mon;
}

// "1,15,22" -> {1,15,22}
void ParseListaInt(const string s, int &out[])
{
   ArrayResize(out, 0);
   string partes[];
   int n = StringSplit(s, ',', partes);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(partes[i]); StringTrimRight(partes[i]);
      if(partes[i] == "") continue;
      int k = ArraySize(out);
      ArrayResize(out, k + 1);
      out[k] = (int)StringToInteger(partes[i]);
   }
}

bool ContemInt(const int &arr[], const int v)
{
   for(int i = 0; i < ArraySize(arr); i++)
      if(arr[i] == v) return true;
   return false;
}

// mascara "135" -> dias 1,3,5 verdadeiros (1=seg..5=sex)
void ParseMascaraDias(const string s, bool &m[])
{
   for(int i = 0; i < 8; i++) m[i] = false;
   for(int i = 0; i < StringLen(s); i++)
   {
      int d = (int)(StringGetCharacter(s, i) - '0');
      if(d >= 0 && d <= 6) m[d] = true;
   }
}

//+------------------------------------------------------------------+
// filtros
//+------------------------------------------------------------------+
bool FiltroDiaSemana(const int lado, const datetime t)
{
   int d = DiaSemana(t);
   return (lado > 0) ? g_dia_ok[d] : g_dia_ok_v[d];
}

bool FiltroMes(const datetime t) { return g_mes_ok[MesDe(t)]; }

// dia de pregao do mes (1 = primeiro) da barra g_r[i], contando barras D1 do mesmo mes
int DiaDePregaoDoMes(const int i)
{
   int mes = MesDe(g_r[i].time);
   int ano; { MqlDateTime d; TimeToStruct(g_r[i].time, d); ano = d.year; }
   int n = 0;
   for(int k = i; k < ArraySize(g_r); k++)
   {
      MqlDateTime d; TimeToStruct(g_r[k].time, d);
      if(d.mon != mes || d.year != ano) break;
      n++;
   }
   return n;
}

//+------------------------------------------------------------------+
// indicadores (todos sobre barras fechadas: shift >= 1)
//+------------------------------------------------------------------+
double CalcATR(const int n)
{
   int bars = ArraySize(g_r);
   if(bars < n + 2) return 0.0;
   double s = 0.0;
   for(int i = 1; i <= n; i++)
   {
      double tr = MathMax(g_r[i].high, g_r[i + 1].close) - MathMin(g_r[i].low, g_r[i + 1].close);
      s += tr;
   }
   return s / n;
}

// pivo curto de 3 barras: x[i] estritamente menor (fundo) ou maior (topo) que as duas vizinhas.
// Simetrico, vale em serie ou cronologico. O chamador garante i-1 e i+1 ja' fechados.
bool PivoCurto(const double &x[], const int i, const bool fundo)
{
   if(i < 1 || i + 1 >= ArraySize(x)) return false;
   if(fundo) return (x[i] < x[i - 1] && x[i] < x[i + 1]);
   return (x[i] > x[i - 1] && x[i] > x[i + 1]);
}

// %R de Larry: 100 = fechou na minima do periodo (sobrevendido), 0 = na maxima
double WilliamsR(const int shift, const int n)
{
   if(shift + n > ArraySize(g_r)) return -1.0;
   double hh = -DBL_MAX, ll = DBL_MAX;
   for(int i = shift; i < shift + n; i++)
   {
      hh = MathMax(hh, g_r[i].high);
      ll = MathMin(ll, g_r[i].low);
   }
   if(hh - ll <= 0.0) return 50.0;
   return 100.0 * (hh - g_r[shift].close) / (hh - ll);
}

double UltimateOscillator(const int shift)
{
   int ps[3]; ps[0] = UO_P1; ps[1] = UO_P2; ps[2] = UO_P3;
   if(shift + UO_P3 + 1 > ArraySize(g_r)) return -1.0;
   double a[3];
   for(int q = 0; q < 3; q++)
   {
      double bp = 0.0, tr = 0.0;
      for(int i = shift; i < shift + ps[q]; i++)
      {
         double pc = g_r[i + 1].close;
         bp += g_r[i].close - MathMin(g_r[i].low, pc);
         tr += MathMax(g_r[i].high, pc) - MathMin(g_r[i].low, pc);
      }
      a[q] = (tr > 0.0) ? bp / tr : 0.0;
   }
   return 100.0 * (4.0 * a[0] + 2.0 * a[1] + a[2]) / 7.0;
}

// +1 alta, -1 baixa, 0 indefinida. Swing: o ultimo rompimento (para cima do ultimo
// short-term high x para baixo do ultimo short-term low) mais recente decide. Inside days ignorados.
int TendenciaSwing()
{
   int n = MathMin(ArraySize(g_r) - 1, 150);
   if(n < 6) return 0;
   double H[], L[];
   ArrayResize(H, n); ArrayResize(L, n);
   int m = 0;
   for(int i = n; i >= 1; i--)   // da mais antiga para a mais recente fechada
   {
      if(m > 0 && g_r[i].high <= H[m - 1] && g_r[i].low >= L[m - 1]) continue; // inside day
      H[m] = g_r[i].high; L[m] = g_r[i].low; m++;
   }
   ArrayResize(H, m); ArrayResize(L, m);
   double sth = 0.0, stl = 0.0;
   bool temH = false, temL = false;
   int lastUp = -1, lastDn = -1;
   for(int t = 1; t < m; t++)
   {
      int k = t - 1;                 // pivo em k confirmado pela barra t (ja' fechada)
      if(k >= 1)
      {
         if(PivoCurto(L, k, true))  { stl = L[k]; temL = true; }
         if(PivoCurto(H, k, false)) { sth = H[k]; temH = true; }
      }
      if(temH && H[t] > sth) lastUp = t;
      if(temL && L[t] < stl) lastDn = t;
   }
   if(lastUp > lastDn) return 1;
   if(lastDn > lastUp) return -1;
   return 0;
}

int Tendencia(const ENUM_TEND modo)
{
   if(modo == TEND_SWING) return TendenciaSwing();
   if(modo == TEND_SMA)
   {
      if(ArraySize(g_r) < Tend_SMA_N + 2) return 0;
      double s = 0.0;
      for(int i = 1; i <= Tend_SMA_N; i++) s += g_r[i].close;
      s /= Tend_SMA_N;
      return (g_r[1].close > s) ? 1 : (g_r[1].close < s ? -1 : 0);
   }
   return 0;
}

bool TendenciaPermite(const ENUM_TEND modo, const int lado)
{
   if(modo == TEND_NENHUM) return true;
   return Tendencia(modo) == lado;
}

//+------------------------------------------------------------------+
// construcao de planos
//+------------------------------------------------------------------+
void LimparPlano(Plano &p)
{
   p.ativo = false; p.lado = 0; p.tipo = ORDER_TYPE_BUY; p.preco = 0.0;
   p.dist_sl = 0.0; p.dist_tp = 0.0; p.setup = "";
}

double BaseStop()
{
   double r1 = g_r[1].high - g_r[1].low;
   if(StopModo == STOP_ATR) { double a = CalcATR(AtrPeriodo); if(a > 0.0) return a; }
   return r1;
}

double DistStop() { return NormPreco(StopFrac * BaseStop()); }

void ArmaPlano(Plano &p, const int lado, const ENUM_ORDER_TYPE tipo, const double preco,
               const double dist, const string setup)
{
   p.ativo = true; p.lado = lado; p.tipo = tipo;
   p.preco = (preco > 0.0) ? NormPreco(preco) : 0.0;
   p.dist_sl = (dist > 0.0) ? dist : 0.0;
   p.dist_tp = (ModoSaida == SAIDA_ALVO_RR && dist > 0.0) ? NormPreco(RRAlvo * dist) : 0.0;
   p.setup = setup;
}

// entrada "na abertura" do livro: mercado, ou limite em C(S)
void ArmaPlanoAbertura(Plano &p, const int lado, const double c_s, const double dist, const string setup)
{
   if(EntradaNaAbertura == ENTRADA_MERCADO_ABERTURA)
      ArmaPlano(p, lado, lado > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, 0.0, dist, setup);
   else
      ArmaPlano(p, lado, lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT, c_s, dist, setup);
}

//+------------------------------------------------------------------+
// SETUPS DIARIOS. Cada um preenche compra/venda e devolve true se algum ativo.
// g_r[0].open = abertura de hoje; g_r[1] = S (ontem). Nada usa H/L/C de hoje.
//+------------------------------------------------------------------+
bool SetupVB(Plano &c, Plano &v)
{
   double o = g_r[0].open, r1 = g_r[1].high - g_r[1].low;
   if(r1 <= 0.0) return false;
   double d = DistStop();
   ArmaPlano(c, +1, ORDER_TYPE_BUY_STOP,  o + VB_Kc * r1, d, "VB");
   ArmaPlano(v, -1, ORDER_TYPE_SELL_STOP, o - VB_Kv * r1, d, "VB");
   return true;
}

bool SetupOops(Plano &c, Plano &v)
{
   double o = g_r[0].open, r1 = g_r[1].high - g_r[1].low;
   if(r1 <= 0.0) return false;
   double d = DistStop();
   double gmin = Oops_GapMin * r1;
   if(o < g_r[1].low && (g_r[1].low - o) >= gmin)
      if(!Oops_CompraApos17 || DiaDePregaoDoMes(0) > 17)
         ArmaPlano(c, +1, ORDER_TYPE_BUY_STOP, g_r[1].low, d, "OOPS");
   if(o > g_r[1].high && (o - g_r[1].high) >= gmin)
      ArmaPlano(v, -1, ORDER_TYPE_SELL_STOP, g_r[1].high, d, "OOPS");
   return (c.ativo || v.ativo);
}

bool SetupSmash(Plano &c, Plano &v)
{
   int n = MathMax(1, Smash_N);
   if(ArraySize(g_r) < n + 3) return false;
   if(Smash_ExcluirOutside && g_r[1].high > g_r[2].high && g_r[1].low < g_r[2].low) return false;
   double mn = DBL_MAX, mx = -DBL_MAX;
   for(int i = 2; i <= 1 + n; i++) { mn = MathMin(mn, g_r[i].low); mx = MathMax(mx, g_r[i].high); }
   if(g_r[1].close < mn)
   {
      double d = Smash_StopExtremo ? (g_r[1].high - g_r[1].low) : DistStop();
      ArmaPlano(c, +1, ORDER_TYPE_BUY_STOP, g_r[1].high, NormPreco(d), "SMASH");
   }
   if(g_r[1].close > mx)
   {
      double d = Smash_StopExtremo ? (g_r[1].high - g_r[1].low) : DistStop();
      ArmaPlano(v, -1, ORDER_TYPE_SELL_STOP, g_r[1].low, NormPreco(d), "SMASH");
   }
   return (c.ativo || v.ativo);
}

bool SetupHiddenSmash(Plano &c, Plano &v)
{
   double rg = g_r[1].high - g_r[1].low;
   if(rg <= 0.0) return false;
   double pos = (g_r[1].close - g_r[1].low) / rg;     // 0 = na minima, 1 = na maxima
   double d = Smash_StopExtremo ? rg : DistStop();
   if(g_r[1].close > g_r[2].close && pos <= HS_Zona &&
      (!HS_ExigeCloseOposto || g_r[1].close < g_r[1].open))
      ArmaPlano(c, +1, ORDER_TYPE_BUY_STOP, g_r[1].high, NormPreco(d), "HSMASH");
   if(g_r[1].close < g_r[2].close && pos >= 1.0 - HS_Zona &&
      (!HS_ExigeCloseOposto || g_r[1].close > g_r[1].open))
      ArmaPlano(v, -1, ORDER_TYPE_SELL_STOP, g_r[1].low, NormPreco(d), "HSMASH");
   return (c.ativo || v.ativo);
}

bool SetupOutside(Plano &c, Plano &v)
{
   if(Outside_EvitaQuinta && DiaSemana(g_r[0].time) == 4) return false;
   double o = g_r[0].open, d = DistStop();
   bool outside = (g_r[1].high > g_r[2].high && g_r[1].low < g_r[2].low);
   if(!outside) return false;
   if(g_r[1].close < g_r[2].low && o < g_r[1].close)
      ArmaPlanoAbertura(c, +1, g_r[1].close, d, "OUTSIDE");
   if(Outside_LadoVenda && g_r[1].close > g_r[2].high && o > g_r[1].close)
      ArmaPlanoAbertura(v, -1, g_r[1].close, d, "OUTSIDE");
   return (c.ativo || v.ativo);
}

// GSV do dia j (shift): compra = max(H[j+3]-L[j], H[j+1]-L[j+3]); venda espelhado
double GSVDia(const int j, const bool compra)
{
   if(compra) return MathMax(g_r[j + 3].high - g_r[j].low, g_r[j + 1].high - g_r[j + 3].low);
   return MathMax(g_r[j].high - g_r[j + 3].low, g_r[j + 3].high - g_r[j + 1].low);
}

bool SetupGSV(Plano &c, Plano &v)
{
   int n = MathMax(1, GSV_N);
   if(ArraySize(g_r) < n + 5) return false;
   double sc = 0.0, sv = 0.0;
   for(int j = 1; j <= n; j++) { sc += GSVDia(j, true); sv += GSVDia(j, false); }
   sc /= n; sv /= n;
   double o = g_r[0].open, d = DistStop();
   if(g_r[1].close < g_r[1].open)   // [INTERP] so' compra apos dia de baixa
      ArmaPlano(c, +1, ORDER_TYPE_BUY_STOP, o + GSV_Kc * sc, d, "GSV");
   if(g_r[1].close > g_r[1].open)   // [INTERP] so' vende apos dia de alta
      ArmaPlano(v, -1, ORDER_TYPE_SELL_STOP, o - GSV_Kv * sv, d, "GSV");
   return (c.ativo || v.ativo);
}

// compra: %R tocou 100, esperou WR_Espera pregoes e cruzou para baixo de WR_NivelCompra em S
bool SetupWR(Plano &c, Plano &v)
{
   if(ArraySize(g_r) < WR_Periodo + WR_Janela + 4) return false;
   double r1 = WilliamsR(1, WR_Periodo), r2 = WilliamsR(2, WR_Periodo);
   double d = DistStop();
   if(r1 < 0.0 || r2 < 0.0) return false;
   if(r2 >= WR_NivelCompra && r1 < WR_NivelCompra)
      for(int k = 2; k <= WR_Janela; k++)
         if(k - 1 >= WR_Espera && WilliamsR(k, WR_Periodo) >= 100.0) { ArmaPlanoAbertura(c, +1, g_r[1].close, d, "WR"); break; }
   if(r2 <= WR_NivelVenda && r1 > WR_NivelVenda)
      for(int k = 2; k <= WR_Janela; k++)
         if(k - 1 >= WR_Espera && WilliamsR(k, WR_Periodo) <= 0.0) { ArmaPlanoAbertura(v, -1, g_r[1].close, d, "WR"); break; }
   return (c.ativo || v.ativo);
}

// divergencia no UO com gatilho de rompimento do pico/fundo intermediario; pivos de 3 barras
bool SetupUO(Plano &c, Plano &v)
{
   int N = UO_Janela + 12;
   if(ArraySize(g_r) < N + UO_P3 + 3) return false;
   double uo[], lows[], highs[];
   ArrayResize(uo, N + 1); ArrayResize(lows, N + 1); ArrayResize(highs, N + 1);
   uo[0] = 0.0; lows[0] = g_r[0].low; highs[0] = g_r[0].high; // indice 0 nunca e' usado como pivo
   for(int i = 1; i <= N; i++)
   {
      uo[i] = UltimateOscillator(i);
      lows[i] = g_r[i].low; highs[i] = g_r[i].high;
   }
   double d = DistStop();
   // altista
   int a = -1, b = -1;
   for(int i = 2; i < N; i++)
      if(PivoCurto(uo, i, true)) { if(a < 0) a = i; else { b = i; break; } }
   if(a > 0 && b > 0 && (b - a) <= UO_Janela && b - a >= 2)
   {
      double pico = -DBL_MAX;
      for(int i = a + 1; i < b; i++) pico = MathMax(pico, uo[i]);
      if(lows[a] < lows[b] && uo[a] > uo[b] && uo[b] < UO_NivelCompra && uo[1] > pico && uo[2] <= pico)
         ArmaPlanoAbertura(c, +1, g_r[1].close, d, "UO");
   }
   // baixista
   a = -1; b = -1;
   for(int i = 2; i < N; i++)
      if(PivoCurto(uo, i, false)) { if(a < 0) a = i; else { b = i; break; } }
   if(a > 0 && b > 0 && (b - a) <= UO_Janela && b - a >= 2)
   {
      double fundo = DBL_MAX;
      for(int i = a + 1; i < b; i++) fundo = MathMin(fundo, uo[i]);
      if(highs[a] > highs[b] && uo[a] < uo[b] && uo[b] > UO_NivelVenda && uo[1] < fundo && uo[2] >= fundo)
         ArmaPlanoAbertura(v, -1, g_r[1].close, d, "UO");
   }
   return (c.ativo || v.ativo);
}

bool SetupTDM(Plano &c, Plano &v)
{
   int dia = DiaDePregaoDoMes(0);
   double d = DistStop();
   if(ContemInt(g_tdm_c, dia)) ArmaPlanoAbertura(c, +1, g_r[1].close, d, "TDM");
   if(ContemInt(g_tdm_v, dia)) ArmaPlanoAbertura(v, -1, g_r[1].close, d, "TDM");
   return (c.ativo || v.ativo);
}

bool SetupTDW(Plano &c, Plano &v)
{
   int dw = DiaSemana(g_r[0].time);
   double d = DistStop();
   if(g_tdw_c[dw]) ArmaPlanoAbertura(c, +1, g_r[1].close, d, "TDW");
   if(g_tdw_v[dw]) ArmaPlanoAbertura(v, -1, g_r[1].close, d, "TDW");
   return (c.ativo || v.ativo);
}

// SMA(3) das minimas/maximas das 3 ultimas barras FECHADAS do timeframe TB
bool SetupTresBarras(const int lado, double &nivelEntrada, double &nivelAlvo)
{
   double h[], l[];
   ArraySetAsSeries(h, true); ArraySetAsSeries(l, true);
   if(CopyHigh(_Symbol, TB_Timeframe, 1, 3, h) != 3) return false;
   if(CopyLow(_Symbol, TB_Timeframe, 1, 3, l) != 3) return false;
   double smaH = (h[0] + h[1] + h[2]) / 3.0, smaL = (l[0] + l[1] + l[2]) / 3.0;
   if(lado > 0) { nivelEntrada = NormPreco(smaL); nivelAlvo = NormPreco(smaH); }
   else         { nivelEntrada = NormPreco(smaH); nivelAlvo = NormPreco(smaL); }
   return true;
}

//+------------------------------------------------------------------+
// filtros aplicados ao plano e escolha por prioridade
//+------------------------------------------------------------------+
void AplicaFiltros(Plano &c, Plano &v, const ENUM_TEND tend)
{
   datetime t = g_r[0].time;
   if(c.ativo && !(PermiteCompra && FiltroDiaSemana(+1, t) && FiltroMes(t) && TendenciaPermite(tend, +1))) c.ativo = false;
   if(v.ativo && !(PermiteVenda  && FiltroDiaSemana(-1, t) && FiltroMes(t) && TendenciaPermite(tend, -1))) v.ativo = false;
}

bool GerarPlanos(Plano &c, Plano &v)
{
   LimparPlano(c); LimparPlano(v);
   if(ArraySize(g_r) < 40) return false;
   bool u[10];
   u[0] = UsarVB; u[1] = UsarOops; u[2] = UsarSmash; u[3] = UsarHiddenSmash; u[4] = UsarOutside;
   u[5] = UsarGSV; u[6] = UsarWR; u[7] = UsarUO; u[8] = UsarTDM; u[9] = UsarTDW;
   for(int s = 0; s < 10; s++)
   {
      if(!u[s]) continue;
      LimparPlano(c); LimparPlano(v);
      bool ok = false;
      switch(s)
      {
         case 0: ok = SetupVB(c, v); break;
         case 1: ok = SetupOops(c, v); break;
         case 2: ok = SetupSmash(c, v); break;
         case 3: ok = SetupHiddenSmash(c, v); break;
         case 4: ok = SetupOutside(c, v); break;
         case 5: ok = SetupGSV(c, v); break;
         case 6: ok = SetupWR(c, v); break;
         case 7: ok = SetupUO(c, v); break;
         case 8: ok = SetupTDM(c, v); break;
         case 9: ok = SetupTDW(c, v); break;
      }
      if(!ok) continue;
      AplicaFiltros(c, v, (s == 6) ? Tend_WR : Tend_Geral);
      if(c.ativo || v.ativo) return true;
   }
   LimparPlano(c); LimparPlano(v);
   return false;
}

//+------------------------------------------------------------------+
// execucao
//+------------------------------------------------------------------+
bool TemPosicao()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      return true;
   }
   return false;
}

bool SelecionaPosicao()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      return true;
   }
   return false;
}

void CancelarPendentes(const bool incluirAlvo)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
      if(!incluirAlvo && tk == g_ticket_alvo) continue;
      trade.OrderDelete(tk);
   }
   if(incluirAlvo) g_ticket_alvo = 0;
}

void FecharPosicao(const string motivo)
{
   if(!SelecionaPosicao()) return;
   ulong tk = (ulong)PositionGetInteger(POSITION_TICKET);
   g_motivo = motivo;
   CancelarPendentes(true);
   if(!trade.PositionClose(tk))
      PrintFormat("LW: falha ao fechar (%s) retcode=%d", motivo, (int)trade.ResultRetcode());
}

double SLAbs(const int lado, const double ref, const double dist)
{
   if(dist <= 0.0) return 0.0;
   return NormPreco(lado > 0 ? ref - dist : ref + dist);
}

double TPAbs(const int lado, const double ref, const double dist)
{
   if(dist <= 0.0) return 0.0;
   return NormPreco(lado > 0 ? ref + dist : ref - dist);
}

bool ColocarOrdemMercado(const Plano &p)
{
   double ref = (p.lado > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = SLAbs(p.lado, ref, p.dist_sl), tp = TPAbs(p.lado, ref, p.dist_tp);
   double vol = NormLote(Lote);
   bool ok = (p.lado > 0) ? trade.Buy(vol, _Symbol, 0.0, sl, tp, "LW " + p.setup)
                          : trade.Sell(vol, _Symbol, 0.0, sl, tp, "LW " + p.setup);
   PrintFormat("LW: %s mercado %s ref=%.5f sl=%.5f ok=%d ret=%d", p.setup, p.lado > 0 ? "COMPRA" : "VENDA",
               ref, sl, ok, (int)trade.ResultRetcode());
   return ok;
}

bool ColocarOrdemStop(const Plano &p)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if((p.lado > 0 && p.preco <= ask) || (p.lado < 0 && p.preco >= bid))
   {
      PrintFormat("LW: %s stop %.5f ja' atravessado (ask=%.5f bid=%.5f), nao arma", p.setup, p.preco, ask, bid);
      return false;
   }
   double sl = SLAbs(p.lado, p.preco, p.dist_sl), tp = TPAbs(p.lado, p.preco, p.dist_tp);
   double vol = NormLote(Lote);
   bool ok = (p.lado > 0) ? trade.BuyStop(vol, p.preco, _Symbol, sl, tp, ORDER_TIME_DAY, 0, "LW " + p.setup)
                          : trade.SellStop(vol, p.preco, _Symbol, sl, tp, ORDER_TIME_DAY, 0, "LW " + p.setup);
   PrintFormat("LW: %s %s STOP @%.5f sl=%.5f ok=%d ret=%d", p.setup, p.lado > 0 ? "BUY" : "SELL", p.preco, sl, ok, (int)trade.ResultRetcode());
   return ok;
}

bool ColocarOrdemLimite(const Plano &p)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if((p.lado > 0 && p.preco >= ask) || (p.lado < 0 && p.preco <= bid))
   {
      // [INTERP] limite ja' executavel (preco melhor que o pedido): executa a mercado
      PrintFormat("LW: %s limite %.5f executavel (ask=%.5f bid=%.5f) -> mercado", p.setup, p.preco, ask, bid);
      return ColocarOrdemMercado(p);
   }
   double sl = SLAbs(p.lado, p.preco, p.dist_sl), tp = TPAbs(p.lado, p.preco, p.dist_tp);
   double vol = NormLote(Lote);
   bool ok = (p.lado > 0) ? trade.BuyLimit(vol, p.preco, _Symbol, sl, tp, ORDER_TIME_DAY, 0, "LW " + p.setup)
                          : trade.SellLimit(vol, p.preco, _Symbol, sl, tp, ORDER_TIME_DAY, 0, "LW " + p.setup);
   PrintFormat("LW: %s %s LIMIT @%.5f sl=%.5f ok=%d ret=%d", p.setup, p.lado > 0 ? "BUY" : "SELL", p.preco, sl, ok, (int)trade.ResultRetcode());
   return ok;
}

bool ColocarPlano(const Plano &p)
{
   if(!p.ativo) return false;
   if(p.tipo == ORDER_TYPE_BUY || p.tipo == ORDER_TYPE_SELL) return ColocarOrdemMercado(p);
   if(p.tipo == ORDER_TYPE_BUY_STOP || p.tipo == ORDER_TYPE_SELL_STOP) return ColocarOrdemStop(p);
   return ColocarOrdemLimite(p);
}

//+------------------------------------------------------------------+
// saidas. fase 0 = apos a abertura do dia; fase 1 = fim do pregao
//+------------------------------------------------------------------+
int DiasDesdeEntrada()
{
   int s = iBarShift(_Symbol, PERIOD_D1, g_entrada_t, false);
   return (s < 0) ? 0 : s;
}

// saida do proprio indicador (UO / WR), avaliada na abertura com barras fechadas
bool SaidaIndicador()
{
   if(g_setup_pos == "UO")
   {
      double u = UltimateOscillator(1);
      if(u < 0.0) return false;
      if(g_lado_pos > 0)
      {
         if(u > 50.0) g_passou50 = true;
         return (u > 70.0 || (g_passou50 && u < 45.0));
      }
      if(u < 50.0) g_passou50 = true;
      return (u <= 30.0 || (g_passou50 && u > 65.0));
   }
   if(g_setup_pos == "WR")
   {
      double r = WilliamsR(1, WR_Periodo);
      if(r < 0.0) return false;
      return (g_lado_pos > 0) ? (r <= WR_NivelVenda) : (r >= WR_NivelCompra);
   }
   return false;
}

void GerenciarSaida(const int fase)
{
   if(!SelecionaPosicao()) return;
   int dias = DiasDesdeEntrada();
   double open_hoje = g_r[0].open;
   bool favoravel = (g_lado_pos > 0) ? (open_hoje > g_entrada) : (open_hoje < g_entrada);

   if(g_setup_pos == "TRES_BARRAS")
   {
      if(fase == 1) FecharPosicao("fim_pregao");
      return;
   }

   ENUM_MODO_SAIDA modo = ModoSaida;
   if(modo == SAIDA_INDICADOR && g_setup_pos != "UO" && g_setup_pos != "WR") modo = SAIDA_BAILOUT;

   if(fase == 0)
   {
      if(dias >= 1)
      {
         if(modo == SAIDA_BAILOUT && dias >= 1 + BailoutAposDias && favoravel) FecharPosicao("bailout");
         else if(modo == SAIDA_ABERTURA_SEGUINTE) FecharPosicao("abertura_seguinte");
         else if(modo == SAIDA_INDICADOR && SaidaIndicador()) FecharPosicao("indicador");
         else if(modo == SAIDA_TEMPO_N && dias > SaidaDias) FecharPosicao("tempo");
         else if(modo == SAIDA_FECHAMENTO) FecharPosicao("fechamento");
      }
      return;
   }
   // fase 1: fim do pregao
   if(modo == SAIDA_FECHAMENTO && dias >= 0) FecharPosicao("fechamento");
   else if(modo == SAIDA_TEMPO_N && dias >= SaidaDias) FecharPosicao("tempo");
}

//+------------------------------------------------------------------+
// log de auditoria
//+------------------------------------------------------------------+
void EscreveCsv(const string setup, const string linha)
{
   string nome = "LW_trades_" + _Symbol + "_" + setup + ".csv";
   int flags = FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | (LogComum ? FILE_COMMON : 0);
   int h = FileOpen(nome, flags);
   if(h == INVALID_HANDLE) { PrintFormat("LW: nao abriu %s (err %d)", nome, GetLastError()); return; }
   if(FileSize(h) == 0) FileWriteString(h, "data;lado;entrada;saida;motivo;pnl_pts\r\n");
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, linha + "\r\n");
   FileClose(h);
}

bool FinalizaRegistro()
{
   if(!HistorySelectByPosition(g_pos_id)) return false;
   int n = HistoryDealsTotal();
   for(int i = n - 1; i >= 0; i--)
   {
      ulong tk = HistoryDealGetTicket(i);
      long ent = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(ent != DEAL_ENTRY_OUT && ent != DEAL_ENTRY_OUT_BY && ent != DEAL_ENTRY_INOUT) continue;
      double px = HistoryDealGetDouble(tk, DEAL_PRICE);
      long why = HistoryDealGetInteger(tk, DEAL_REASON);
      ulong ord = (ulong)HistoryDealGetInteger(tk, DEAL_ORDER);
      string motivo = g_motivo;
      if(motivo == "")
      {
         if(why == DEAL_REASON_SL) motivo = "stop";
         else if(why == DEAL_REASON_TP) motivo = "alvo";
         else if(g_ticket_alvo != 0 && ord == g_ticket_alvo) motivo = "alvo_limite";
         else motivo = "saida";
      }
      double pnl = (px - g_entrada) * g_lado_pos;
      MqlDateTime d; TimeToStruct(g_entrada_t, d);
      string linha = StringFormat("%04d-%02d-%02d;%s;%s;%s;%s;%s", d.year, d.mon, d.day,
                                  g_lado_pos > 0 ? "C" : "V",
                                  DoubleToString(g_entrada, _Digits), DoubleToString(px, _Digits),
                                  motivo, DoubleToString(pnl, _Digits));
      EscreveCsv(g_setup_pos, linha);
      PrintFormat("LW SAIDA %s %s entrada=%.5f saida=%.5f motivo=%s pnl_pts=%.5f", g_setup_pos,
                  g_lado_pos > 0 ? "C" : "V", g_entrada, px, motivo, pnl);
      return true;
   }
   return false;
}

void ColocarAlvo3B()
{
   if(!SelecionaPosicao()) return;
   double nEnt, nAlvo;
   if(!SetupTresBarras(g_lado_pos, nEnt, nAlvo)) return;
   if(g_ticket_alvo != 0) { trade.OrderDelete(g_ticket_alvo); g_ticket_alvo = 0; }
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double vol = (double)PositionGetDouble(POSITION_VOLUME);
   bool ok = false;
   if(g_lado_pos > 0 && nAlvo > ask)      ok = trade.SellLimit(vol, nAlvo, _Symbol, 0, 0, ORDER_TIME_DAY, 0, "LW 3B alvo");
   else if(g_lado_pos < 0 && nAlvo < bid) ok = trade.BuyLimit(vol, nAlvo, _Symbol, 0, 0, ORDER_TIME_DAY, 0, "LW 3B alvo");
   if(ok) g_ticket_alvo = trade.ResultOrder();
}

// detecta abertura/fechamento da posicao e grava o log
void SincronizaPosicao()
{
   bool tem = SelecionaPosicao();
   if(tem && !g_em_pos)
   {
      g_em_pos = true;
      g_pos_id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      g_entrada = PositionGetDouble(POSITION_PRICE_OPEN);
      g_entrada_t = (datetime)PositionGetInteger(POSITION_TIME);
      g_lado_pos = ((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      g_setup_pos = g_setup_dia;
      g_motivo = "";
      g_passou50 = false;
      CancelarPendentes(false);   // OCO: derruba a ordem do outro lado
      PrintFormat("LW ENTRADA %s %s @%.5f", g_setup_pos, g_lado_pos > 0 ? "C" : "V", g_entrada);
      if(g_setup_pos == "TRES_BARRAS") ColocarAlvo3B();
   }
   else if(!tem && g_em_pos)
   {
      if(FinalizaRegistro()) { g_em_pos = false; g_motivo = ""; g_ticket_alvo = 0; CancelarPendentes(true); }
   }
}

//+------------------------------------------------------------------+
// ciclo diario
//+------------------------------------------------------------------+
void ProcessaAbertura()
{
   Plano c, v;
   bool tem = SelecionaPosicao();
   if(tem) GerenciarSaida(0);
   tem = SelecionaPosicao();

   if(!GerarPlanos(c, v)) return;
   g_setup_dia = c.ativo ? c.setup : v.setup;

   if(tem)
   {
      // REVERSAO: sinal oposto fecha e vira; fora disso, uma posicao por vez
      if(ModoSaida != SAIDA_REVERSAO) return;
      bool oposto = (g_lado_pos > 0 && v.ativo) || (g_lado_pos < 0 && c.ativo);
      if(!oposto) return;
      FecharPosicao("reversao");
      if(SelecionaPosicao()) return;
   }
   if(c.ativo) ColocarPlano(c);
   if(v.ativo && !SelecionaPosicao()) ColocarPlano(v);
}

void ProcessaTresBarras()
{
   datetime tb = iTime(_Symbol, TB_Timeframe, 0);
   if(tb == g_ult_barra_tb) return;
   g_ult_barra_tb = tb;
   if(!AposHora(HoraAbertura, MinAbertura + DelayAbertura)) return;
   if(AposHora(HoraFim, MinFim)) return;

   if(SelecionaPosicao()) { if(g_setup_pos == "TRES_BARRAS") ColocarAlvo3B(); return; }
   CancelarPendentes(true);
   if(AposHora(TB_HoraUltimaEntrada, TB_MinUltimaEntrada)) return;

   datetime t = g_r[0].time;
   int lado = 0;
   if(PermiteCompra && TendenciaPermite(Tend_3B, +1) && Tend_3B != TEND_NENHUM) lado = +1;
   else if(PermiteVenda && TendenciaPermite(Tend_3B, -1) && Tend_3B != TEND_NENHUM) lado = -1;
   else if(Tend_3B == TEND_NENHUM) lado = PermiteCompra ? +1 : (PermiteVenda ? -1 : 0);
   if(lado == 0 || !FiltroDiaSemana(lado, t) || !FiltroMes(t)) return;

   double nEnt, nAlvo;
   if(!SetupTresBarras(lado, nEnt, nAlvo)) return;
   Plano p;
   ArmaPlano(p, lado, lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT, nEnt,
             NormPreco(TB_StopFrac * (g_r[1].high - g_r[1].low)), "TRES_BARRAS");
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if((lado > 0 && p.preco >= ask) || (lado < 0 && p.preco <= bid)) return; // 100% limite: nunca converte em mercado
   g_setup_dia = "TRES_BARRAS";
   ColocarOrdemLimite(p);
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(!(UsarVB || UsarOops || UsarSmash || UsarHiddenSmash || UsarOutside || UsarGSV ||
        UsarWR || UsarUO || UsarTDM || UsarTDW || UsarTresBarras))
   {
      Print("LW: nenhum setup ligado");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(UO_P1 < 1 || UO_P2 < UO_P1 || UO_P3 < UO_P2)
   {
      Print("LW: periodos do UO invalidos (P1<=P2<=P3)");
      return(INIT_PARAMETERS_INCORRECT);
   }
   ArraySetAsSeries(g_r, true);
   ParseMascaraDias(FiltroDiasCompra, g_dia_ok);
   ParseMascaraDias(FiltroDiasVenda, g_dia_ok_v);
   ParseMascaraDias(TDW_DiasCompra, g_tdw_c);
   ParseMascaraDias(TDW_DiasVenda, g_tdw_v);
   ParseListaInt(TDM_DiasCompra, g_tdm_c);
   ParseListaInt(TDM_DiasVenda, g_tdm_v);
   int meses[];
   ParseListaInt(FiltroMeses, meses);
   for(int m = 0; m <= 12; m++) g_mes_ok[m] = ContemInt(meses, m);

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DesvioPontos);
   trade.SetTypeFillingBySymbol(_Symbol);
   PrintFormat("LW iniciado em %s tick=%.5f volmin=%.2f", _Symbol, TickSz(), SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));
   return(INIT_SUCCEEDED);
}

void OnTick()
{
   // novo dia: recarrega D1 e reinicia as flags
   datetime d0 = iTime(_Symbol, PERIOD_D1, 0);
   if(d0 != g_dia)
   {
      int n = CopyRates(_Symbol, PERIOD_D1, 0, 220, g_r);
      if(n < 40) return;
      g_dia = d0;
      g_aberto_proc = false;
      CancelarPendentes(true);
   }
   if(ArraySize(g_r) < 40) return;

   SincronizaPosicao();

   if(AposHora(HoraFim, MinFim))
   {
      CancelarPendentes(true);
      GerenciarSaida(1);
      return;
   }
   if(!AposHora(HoraAbertura, MinAbertura + DelayAbertura)) return;

   if(!g_aberto_proc)
   {
      g_aberto_proc = true;
      ProcessaAbertura();
   }
   if(UsarTresBarras) ProcessaTresBarras();
}
//+------------------------------------------------------------------+
