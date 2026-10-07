//+------------------------------------------------------------------+
//| Raschke.mq5                                                      |
//| Porte MQL5 de scripts/raschke/nucleo.py -- setups de Linda       |
//| Raschke (Street Smarts, 1995): Holy Grail, Turtle Soup, Turtle   |
//| Soup Plus One, 80-20, Momentum Pinball (LBR/RSI), Anti.          |
//|                                                                  |
//| UM setup por instancia (input Setup). Cada regra e' uma funcao   |
//| Sinal*() com o MESMO nome/ordem de condicoes do Python; os       |
//| indicadores sao calculados aqui (nao iADX/iMA) para bater com    |
//| nucleo.py. O sinal e' avaliado no FECHAMENTO da ultima barra     |
//| (indice N-1 dos arrays cronologicos) e vira ordem STOP (os       |
//| gatilhos do livro SAO rompimentos -- premissa do setup).         |
//|                                                                  |
//| PROVENIENCIA: parametros default = melhores da varredura IS/OOS  |
//| (scripts/raschke/analise.py). Resultado de backtest NAO aferido  |
//| contra extrato e' hipotese. Aferir no Testador: mesmo ativo,     |
//| timeframe, janela e parametros do CSV da varredura.              |
//+------------------------------------------------------------------+
#property copyright "raschke"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

enum ESetup { SET_HG, SET_TS, SET_TS1, SET_8020, SET_PIN, SET_ANTI };

input ESetup Setup        = SET_HG;  // Setup de Raschke
// --- Holy Grail
input double HgAdxMin     = 30.0;    // ADX(14) minimo
input bool   HgModoInicial= false;   // false='toque' (ADX[i]>min); true='inicial' (pico recente subindo)
input int    HgOlhar      = 10;      // barras p/ achar pico do ADX (modo inicial)
input int    HgInclinacao = 5;       // barras p/ inclinacao da EMA20
input int    HgSwingN     = 3;       // barras do swing do stop
// --- Turtle Soup / Plus One
input int    TsJanela     = 20;      // janela da minima/maxima
input int    TsIdade      = 4;       // idade minima (TS=4, Plus One=3)
input double TsFolgaAtr   = 0.0;     // folga da entrada em fracao do ATR14 (livro: 5-10 ticks)
input int    TsValidade   = 1;       // barras de vida da ordem (TS)
// --- 80-20 (so' intraday)
input double OitentaPenAtr= 0.05;    // perfuracao da minima de ontem, fracao do ATR14 (livro: 5-15 ticks)
input double OitentaRangeMin = 0.0;  // range de ontem / media 20 pregoes minimo (0=desligado)
// --- Pinball
input double PinRsiLo     = 30.0;    // LBR/RSI de compra
input double PinRsiHi     = 70.0;    // LBR/RSI de venda
// --- Anti
input bool   Anti310      = false;   // false=estocastico 7/4/10 (livro); true=SMA3-SMA10/SMA16
input int    AntiRecuo    = 1;       // barras de recuo da linha rapida
input int    AntiInclinacao = 3;     // barras da inclinacao da linha lenta
// --- saida
input double AlvoR        = 0.0;     // alvo em multiplos do risco (0 = sem alvo)
input bool   AlvoSwing    = false;   // Holy Grail: alvo = swing high/low de 20 barras
input int    TrailN       = 0;       // stop acompanha min/max das ultimas N barras (0=nao)
input int    MaxBarras    = 0;       // saida a mercado apos N barras (0=nunca)
input bool   FecharNoDia  = true;    // intraday: zera no fim do pregao (HoraZerar:MinutoZerar)
input bool   PinballCarrega = false; // Pinball: carrega overnight se no lucro, sai na abertura seguinte
// --- operacao
input double Lote         = 1.0;
input double TickSize     = 0.0;     // tick real (WIN 5, WDO 0.5, acao 0.01). 0 = ler do simbolo
input int    HoraZerar    = 18;
input int    MinutoZerar  = 20;
input int    BarrasPorHora= 12;      // M5=12, M15=4, H1=1 (so' Pinball intraday)
input ulong  MagicNumber  = 20261004;
input int    JanelaCalc   = 700;     // barras usadas nos indicadores
input bool   LogSinais    = false;   // imprime cada sinal (paridade com scripts/raschke/paridade.py)

#define NANV MathSqrt(-1.0)

double g_tick = 0.0;
datetime g_ultima_barra = 0;
datetime g_dia_ultimo_trade = 0;
bool     g_intraday = false;

struct Ordem
{
   bool   ok;
   int    lado;      // +1/-1
   double entrada, stop, alvo;
   int    validade;  // barras; 0 = ate o fim do dia
};

//------------------------------------------------------------------ utilidades
bool V(const double x) { return MathIsValidNumber(x); }

void Sma(const double &x[], const int n, double &out[])
{
   int m = ArraySize(x); ArrayResize(out, m);
   for(int i = 0; i < m; i++)
   {
      if(i < n - 1) { out[i] = NANV; continue; }
      double s = 0; for(int k = 0; k < n; k++) s += x[i - k];
      out[i] = s / n;
   }
}
void Ema(const double &x[], const int n, double &out[])
{
   int m = ArraySize(x); ArrayResize(out, m);
   for(int i = 0; i < m; i++) out[i] = NANV;
   if(m < n) return;
   double s = 0; for(int k = 0; k < n; k++) s += x[k];
   out[n - 1] = s / n; double k2 = 2.0 / (n + 1.0);
   for(int i = n; i < m; i++) out[i] = out[i - 1] + k2 * (x[i] - out[i - 1]);
}
void Wilder(const double &x[], const int n, double &out[])
{
   int m = ArraySize(x); ArrayResize(out, m);
   for(int i = 0; i < m; i++) out[i] = NANV;
   if(m < n) return;
   double s = 0; for(int k = 0; k < n; k++) s += x[k];
   out[n - 1] = s / n;
   for(int i = n; i < m; i++) out[i] = (out[i - 1] * (n - 1) + x[i]) / n;
}
void Atr(const double &h[], const double &l[], const double &c[], const int n, double &out[])
{
   int m = ArraySize(c); double tr[]; ArrayResize(tr, m);
   tr[0] = h[0] - l[0];
   for(int i = 1; i < m; i++)
      tr[i] = MathMax(h[i] - l[i], MathMax(MathAbs(h[i] - c[i - 1]), MathAbs(l[i] - c[i - 1])));
   Wilder(tr, n, out);
}
void Adx(const double &h[], const double &l[], const double &c[], const int n, double &out[])
{
   int m = ArraySize(c); ArrayResize(out, m);
   for(int i = 0; i < m; i++) out[i] = NANV;
   if(m < 2 * n + 1) return;
   int q = m - 1;
   double pdm[], mdm[], tr[], sp[], sm[], st[], dx[], a[];
   ArrayResize(pdm, q); ArrayResize(mdm, q); ArrayResize(tr, q);
   ArrayResize(sp, q); ArrayResize(sm, q); ArrayResize(st, q); ArrayResize(dx, q); ArrayResize(a, q);
   for(int t = 0; t < q; t++)
   {
      double up = h[t + 1] - h[t], dn = l[t] - l[t + 1];
      pdm[t] = (up > dn && up > 0) ? up : 0.0;
      mdm[t] = (dn > up && dn > 0) ? dn : 0.0;
      tr[t]  = MathMax(h[t + 1] - l[t + 1], MathMax(MathAbs(h[t + 1] - c[t]), MathAbs(l[t + 1] - c[t])));
      sp[t] = sm[t] = st[t] = dx[t] = a[t] = NANV;
   }
   double s1 = 0, s2 = 0, s3 = 0;
   for(int t = 0; t < n; t++) { s1 += tr[t]; s2 += pdm[t]; s3 += mdm[t]; }
   st[n - 1] = s1; sp[n - 1] = s2; sm[n - 1] = s3;
   for(int t = n; t < q; t++)
   {
      st[t] = st[t - 1] - st[t - 1] / n + tr[t];
      sp[t] = sp[t - 1] - sp[t - 1] / n + pdm[t];
      sm[t] = sm[t - 1] - sm[t - 1] / n + mdm[t];
   }
   for(int t = n - 1; t < q; t++)
   {
      if(st[t] > 0)
      {
         double pdi = 100.0 * sp[t] / st[t], mdi = 100.0 * sm[t] / st[t], den = pdi + mdi;
         dx[t] = den > 0 ? 100.0 * MathAbs(pdi - mdi) / den : 0.0;
      }
      else dx[t] = 0.0;
   }
   int first = 2 * n - 2; double s = 0;
   for(int t = n - 1; t <= first; t++) s += dx[t];
   a[first] = s / n;
   for(int t = first + 1; t < q; t++) a[t] = (a[t - 1] * (n - 1) + dx[t]) / n;
   for(int t = 0; t < q; t++) out[t + 1] = a[t];
}
// RSI de Wilder sobre uma serie arbitraria x (usa x[t]-x[t-1])
void RsiDeSerie(const double &x[], const int n, double &out[])
{
   int m = ArraySize(x); ArrayResize(out, m);
   for(int i = 0; i < m; i++) out[i] = NANV;
   if(m < n + 1) return;
   double ag = 0, ap = 0;
   for(int t = 0; t < n; t++) { double d = x[t + 1] - x[t]; if(d > 0) ag += d; else ap -= d; }
   ag /= n; ap /= n;
   out[n] = ap == 0 ? 100.0 : 100.0 - 100.0 / (1.0 + ag / ap);
   for(int t = n; t < m - 1; t++)
   {
      double d = x[t + 1] - x[t], g = d > 0 ? d : 0, p = d < 0 ? -d : 0;
      ag = (ag * (n - 1) + g) / n; ap = (ap * (n - 1) + p) / n;
      out[t + 1] = ap == 0 ? 100.0 : 100.0 - 100.0 / (1.0 + ag / ap);
   }
}
// Momentum Pinball: RSI(3) do ROC(1)
void LbrRsi(const double &c[], double &out[])
{
   int m = ArraySize(c); ArrayResize(out, m);
   for(int i = 0; i < m; i++) out[i] = NANV;
   if(m < 6) return;
   double roc[]; ArrayResize(roc, m - 1);
   for(int t = 1; t < m; t++) roc[t - 1] = c[t] - c[t - 1];
   double sub[]; RsiDeSerie(roc, 3, sub);
   for(int t = 0; t < m - 1; t++) out[t + 1] = sub[t];
}
void EstocasticoAnti(const double &h[], const double &l[], const double &c[], double &fast[], double &slow[])
{
   int m = ArraySize(c); double raw[]; ArrayResize(raw, m);
   for(int t = 0; t < m; t++)
   {
      if(t < 6) { raw[t] = 50.0; continue; }
      double hh = h[t], ll = l[t];
      for(int k = 1; k < 7; k++) { hh = MathMax(hh, h[t - k]); ll = MathMin(ll, l[t - k]); }
      raw[t] = hh == ll ? 50.0 : 100.0 * (c[t] - ll) / (hh - ll);
   }
   Sma(raw, 4, fast);
   for(int t = 0; t < 7 + 4 - 2; t++) fast[t] = NANV;
   double tmp[]; ArrayResize(tmp, m);
   for(int t = 0; t < m; t++) tmp[t] = V(fast[t]) ? fast[t] : 50.0;
   Sma(tmp, 10, slow);
   for(int t = 0; t < 7 + 4 + 10 - 3; t++) slow[t] = NANV;
}
void Osc310(const double &h[], const double &l[], double &fast[], double &slow[])
{
   int m = ArraySize(h); double mid[], s3[], s10[]; ArrayResize(mid, m);
   for(int t = 0; t < m; t++) mid[t] = (h[t] + l[t]) / 2.0;
   Sma(mid, 3, s3); Sma(mid, 10, s10); ArrayResize(fast, m);
   double tmp[]; ArrayResize(tmp, m);
   for(int t = 0; t < m; t++) { fast[t] = (V(s3[t]) && V(s10[t])) ? s3[t] - s10[t] : NANV; tmp[t] = V(fast[t]) ? fast[t] : 0.0; }
   Sma(tmp, 16, slow);
   for(int t = 0; t < 10 + 16 - 2; t++) slow[t] = NANV;
}

//------------------------------------------------------------------ dados
double O[], H[], L[], C[]; datetime T[];
int N = 0;

bool Carregar()
{
   MqlRates r[];
   int got = CopyRates(_Symbol, _Period, 1, JanelaCalc, r);   // pos 1 = ultima barra FECHADA
   if(got < 120) return false;
   N = got; ArrayResize(O, N); ArrayResize(H, N); ArrayResize(L, N); ArrayResize(C, N); ArrayResize(T, N);
   for(int i = 0; i < N; i++) { O[i] = r[i].open; H[i] = r[i].high; L[i] = r[i].low; C[i] = r[i].close; T[i] = r[i].time; }
   return true;
}
datetime Dia(const datetime t) { return (datetime)((long)t / 86400 * 86400); }
double MinArr(const double &x[], int a, int b) { double m = x[a]; for(int i = a; i <= b; i++) m = MathMin(m, x[i]); return m; }
double MaxArr(const double &x[], int a, int b) { double m = x[a]; for(int i = a; i <= b; i++) m = MathMax(m, x[i]); return m; }

//------------------------------------------------------------------ setups (i = N-1)
Ordem Nada() { Ordem o; o.ok = false; o.lado = 0; o.entrada = o.stop = o.alvo = 0; o.validade = 1; return o; }

Ordem SinalHolyGrail(const int i)
{
   Ordem od = Nada();
   double e20[], a[]; Ema(C, 20, e20); Adx(H, L, C, 14, a);
   if(i < MathMax(60, MathMax(HgOlhar + 2, HgInclinacao + 1))) return od;
   if(!V(a[i]) || !V(e20[i]) || !V(e20[i - 1])) return od;
   bool ok;
   if(!HgModoInicial) ok = a[i] > HgAdxMin;
   else
   {
      int k = i - HgOlhar; double mx = -1;
      for(int t = i - HgOlhar; t <= i; t++) if(V(a[t]) && a[t] > mx) { mx = a[t]; k = t; }
      ok = (mx > HgAdxMin && k >= 1 && V(a[k - 1]) && a[k] > a[k - 1]);
   }
   if(!ok) return od;
   bool sobe = e20[i] > e20[i - HgInclinacao], cai = e20[i] < e20[i - HgInclinacao];
   if(sobe && L[i] <= e20[i] && L[i - 1] > e20[i - 1])
   { od.ok = true; od.lado = 1; od.entrada = H[i] + g_tick; od.stop = MinArr(L, i - HgSwingN + 1, i) - g_tick;
     od.alvo = MaxArr(H, i - 20, i); od.validade = 1; }
   else if(cai && H[i] >= e20[i] && H[i - 1] < e20[i - 1])
   { od.ok = true; od.lado = -1; od.entrada = L[i] - g_tick; od.stop = MaxArr(H, i - HgSwingN + 1, i) + g_tick;
     od.alvo = MinArr(L, i - 20, i); od.validade = 1; }
   return od;
}

Ordem SinalTurtleSoup(const int i, const bool plusOne)
{
   Ordem od = Nada();
   if(i < MathMax(TsJanela + 1, 20)) return od;
   double at[]; Atr(H, L, C, 14, at);
   double Lmin = MinArr(L, i - TsJanela, i - 1), Hmax = MaxArr(H, i - TsJanela, i - 1);
   double folga = plusOne ? 0.0 : TsFolgaAtr * (V(at[i]) ? at[i] : 0.0);
   int idadeL = 0, idadeH = 0;
   for(int t = i - TsJanela; t <= i - 1; t++) { if(L[t] == Lmin) { idadeL = TsJanela - (t - (i - TsJanela)); break; } }
   for(int t = i - TsJanela; t <= i - 1; t++) { if(H[t] == Hmax) { idadeH = TsJanela - (t - (i - TsJanela)); break; } }
   if(L[i] < Lmin && idadeL >= TsIdade)
   {
      double nivel = Lmin + (plusOne ? 0.0 : MathMax(folga, g_tick));
      if((!plusOne && C[i] < nivel) || (plusOne && C[i] <= Lmin))
      { od.ok = true; od.lado = 1; od.entrada = nivel; od.stop = L[i] - g_tick; od.validade = plusOne ? 1 : TsValidade; return od; }
   }
   if(H[i] > Hmax && idadeH >= TsIdade)
   {
      double nivel = Hmax - (plusOne ? 0.0 : MathMax(folga, g_tick));
      if((!plusOne && C[i] > nivel) || (plusOne && C[i] >= Hmax))
      { od.ok = true; od.lado = -1; od.entrada = nivel; od.stop = H[i] + g_tick; od.validade = plusOne ? 1 : TsValidade; return od; }
   }
   return od;
}

// pregao anterior (D1): open/high/low/close e RSI LBR do fechamento diario
bool PregaoAnterior(double &po, double &ph, double &pl, double &pc, double &rsiPrev, double &rngRatio)
{
   MqlRates d[]; int got = CopyRates(_Symbol, PERIOD_D1, 1, 60, d);   // 1 = ontem
   if(got < 25) return false;
   // d[] cronologico: d[got-1] = ontem
   po = d[got - 1].open; ph = d[got - 1].high; pl = d[got - 1].low; pc = d[got - 1].close;
   double dc[]; ArrayResize(dc, got); for(int k = 0; k < got; k++) dc[k] = d[k].close;
   double r[]; LbrRsi(dc, r); rsiPrev = r[got - 1];
   double s = 0; for(int k = got - 20; k < got; k++) s += d[k].high - d[k].low;
   double med = s / 20.0; rngRatio = med > 0 ? (ph - pl) / med : NANV;
   return true;
}

Ordem Sinal8020(const int i)
{
   Ordem od = Nada();
   double po, ph, pl, pc, rs, rr; if(!PregaoAnterior(po, ph, pl, pc, rs, rr)) return od;
   double at[]; Atr(H, L, C, 14, at); if(!V(at[i]) || ph <= pl) return od;
   if(OitentaRangeMin > 0 && !(V(rr) && rr >= OitentaRangeMin)) return od;
   // minima/maxima de HOJE ate a barra i
   datetime hoje = Dia(T[i]); double mn = 1e18, mx = -1e18;
   for(int t = i; t >= 0 && Dia(T[t]) == hoje; t--) { mn = MathMin(mn, L[t]); mx = MathMax(mx, H[t]); }
   double r = ph - pl, pen = OitentaPenAtr * at[i];
   if((po - pl) / r >= 0.8 && (pc - pl) / r <= 0.2)
   { if(mn <= pl - pen && C[i] < pl) { od.ok = true; od.lado = 1; od.entrada = pl; od.stop = mn - g_tick; od.validade = 0; } }
   else if((po - pl) / r <= 0.2 && (pc - pl) / r >= 0.8)
   { if(mx >= ph + pen && C[i] > ph) { od.ok = true; od.lado = -1; od.entrada = ph; od.stop = mx + g_tick; od.validade = 0; } }
   return od;
}

Ordem SinalPinball(const int i)
{
   Ordem od = Nada();
   if(_Period == PERIOD_D1)
   {
      double r[]; LbrRsi(C, r); if(!V(r[i])) return od;
      if(r[i] < PinRsiLo)      { od.ok = true; od.lado = 1;  od.entrada = H[i] + g_tick; od.stop = L[i] - g_tick; od.validade = 1; }
      else if(r[i] > PinRsiHi) { od.ok = true; od.lado = -1; od.entrada = L[i] - g_tick; od.stop = H[i] + g_tick; od.validade = 1; }
      return od;
   }
   // intraday: so' na barra que FECHA a primeira hora do pregao
   datetime hoje = Dia(T[i]); int idx = 0;
   for(int t = i - 1; t >= 0 && Dia(T[t]) == hoje; t--) idx++;
   if(idx != BarrasPorHora - 1) return od;
   double po, ph, pl, pc, rs, rr; if(!PregaoAnterior(po, ph, pl, pc, rs, rr) || !V(rs)) return od;
   double h1 = MaxArr(H, i - BarrasPorHora + 1, i), l1 = MinArr(L, i - BarrasPorHora + 1, i);
   if(rs < PinRsiLo)      { od.ok = true; od.lado = 1;  od.entrada = h1 + g_tick; od.stop = l1 - g_tick; od.validade = 0; }
   else if(rs > PinRsiHi) { od.ok = true; od.lado = -1; od.entrada = l1 - g_tick; od.stop = h1 + g_tick; od.validade = 0; }
   return od;
}

Ordem SinalAnti(const int i)
{
   Ordem od = Nada();
   double f[], s[];
   if(!Anti310) EstocasticoAnti(H, L, C, f, s); else Osc310(H, L, f, s);
   if(i < MathMax(40, AntiInclinacao + AntiRecuo + 2)) return od;
   if(!V(s[i]) || !V(s[i - AntiInclinacao]) || !V(f[i - AntiRecuo - 1])) return od;
   bool sobe = s[i] > s[i - AntiInclinacao], desce = s[i] < s[i - AntiInclinacao];
   bool up = f[i] > f[i - 1], dn = f[i] < f[i - 1];
   for(int k = 1; k <= AntiRecuo; k++) { if(!(f[i - k] < f[i - k - 1])) up = false; if(!(f[i - k] > f[i - k - 1])) dn = false; }
   if(sobe && up) { od.ok = true; od.lado = 1;  od.entrada = H[i] + g_tick; od.stop = MinArr(L, i - AntiRecuo, i) - g_tick; od.validade = 1; }
   else if(desce && dn) { od.ok = true; od.lado = -1; od.entrada = L[i] - g_tick; od.stop = MaxArr(H, i - AntiRecuo, i) + g_tick; od.validade = 1; }
   return od;
}

Ordem GerarOrdem()
{
   int i = N - 1;
   switch(Setup)
   {
      case SET_HG:   return SinalHolyGrail(i);
      case SET_TS:   return SinalTurtleSoup(i, false);
      case SET_TS1:  return SinalTurtleSoup(i, true);
      case SET_8020: return Sinal8020(i);
      case SET_PIN:  return SinalPinball(i);
      case SET_ANTI: return SinalAnti(i);
   }
   return Nada();
}

//------------------------------------------------------------------ execucao
double Norm(const double p) { return MathRound(p / g_tick) * g_tick; }

bool TemPosicao(ulong &ticket)
{
   for(int k = PositionsTotal() - 1; k >= 0; k--)
   {
      ulong tk = PositionGetTicket(k);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber) { ticket = tk; return true; }
   }
   return false;
}
bool TemPendente()
{
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      ulong tk = OrderGetTicket(k);
      if(OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == MagicNumber) return true;
   }
   return false;
}
void CancelarPendentes()
{
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      ulong tk = OrderGetTicket(k);
      if(OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == MagicNumber) trade.OrderDelete(tk);
   }
}
bool FimDoPregao(const datetime t)
{
   MqlDateTime s; TimeToStruct(t, s); return s.hour * 60 + s.min >= HoraZerar * 60 + MinutoZerar;
}

void EnviarOrdem(const Ordem &od)
{
   double entrada = Norm(od.entrada), stop = Norm(od.stop);
   double risco = (entrada - stop) * od.lado;
   if(risco < 2.0 * g_tick) return;
   double tp = 0.0;
   if(AlvoR > 0)        tp = Norm(entrada + od.lado * AlvoR * risco);
   else if(AlvoSwing && od.alvo != 0 && (od.alvo - entrada) * od.lado > 0.5 * risco) tp = Norm(od.alvo);
   datetime exp = 0; ENUM_ORDER_TYPE_TIME tt = ORDER_TIME_DAY;
   if(od.validade > 0) { tt = ORDER_TIME_SPECIFIED; exp = TimeCurrent() + (datetime)(od.validade * PeriodSeconds(_Period)); }
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(od.lado == 1)
   {
      if(entrada <= ask) return;                       // ja passou do nivel: seria ordem a mercado disfarcada
      trade.BuyStop(Lote, entrada, _Symbol, stop, tp, tt, exp, "raschke");
   }
   else
   {
      if(entrada >= bid) return;
      trade.SellStop(Lote, entrada, _Symbol, stop, tp, tt, exp, "raschke");
   }
}

void GerirPosicao(const ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return;
   int lado = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
   double abre = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   datetime t0 = (datetime)PositionGetInteger(POSITION_TIME);
   int barras = iBarShift(_Symbol, _Period, t0, false);   // barras desde a entrada
   // tempo
   if(MaxBarras > 0 && barras >= MaxBarras) { trade.PositionClose(ticket); return; }
   // fim do pregao
   if(g_intraday && FimDoPregao(TimeCurrent()))
   {
      double px = PositionGetDouble(POSITION_PRICE_CURRENT);
      if(PinballCarrega && (px - abre) * lado > 0 && Dia(t0) == Dia(TimeCurrent())) return; // carrega
      if(FecharNoDia || PinballCarrega) { trade.PositionClose(ticket); return; }
   }
   // Pinball: dia seguinte -> sai na abertura
   if(PinballCarrega && Dia(t0) < Dia(TimeCurrent())) { trade.PositionClose(ticket); return; }
}

void AtualizarTrailing(const ulong ticket)
{
   if(TrailN <= 0 || !PositionSelectByTicket(ticket)) return;
   int lado = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   datetime t0 = (datetime)PositionGetInteger(POSITION_TIME);
   int desde = iBarShift(_Symbol, _Period, t0, false);          // 0 = barra da entrada em formacao
   int a = MathMin(TrailN, MathMax(desde, 1));
   double novo;
   if(lado == 1) { novo = Norm(MinArr(L, N - a, N - 1) - g_tick); if(novo > sl) trade.PositionModify(ticket, novo, tp); }
   else          { novo = Norm(MaxArr(H, N - a, N - 1) + g_tick); if(novo < sl) trade.PositionModify(ticket, novo, tp); }
}

//------------------------------------------------------------------ eventos
int OnInit()
{
   g_tick = TickSize > 0 ? TickSize : SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_tick <= 0) return INIT_PARAMETERS_INCORRECT;
   g_intraday = (_Period < PERIOD_D1);
   if(Setup == SET_8020 && !g_intraday) { Print("80-20 exige timeframe intraday"); return INIT_PARAMETERS_INCORRECT; }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(50);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // gestao de posicao a cada tick (tempo/fim de pregao)
   ulong tk;
   bool pos = TemPosicao(tk);
   if(pos) GerirPosicao(tk);

   datetime barra = iTime(_Symbol, _Period, 0);
   if(barra == g_ultima_barra) return;                  // so' no fechamento da barra
   g_ultima_barra = barra;
   if(!Carregar()) return;

   pos = TemPosicao(tk);
   if(pos) { AtualizarTrailing(tk); return; }
   CancelarPendentes();                                  // ordem da barra anterior que nao encheu
   if(g_intraday && FimDoPregao(TimeCurrent())) return;
   if((Setup == SET_8020 || Setup == SET_PIN) && g_intraday && g_dia_ultimo_trade == Dia(TimeCurrent())) return;
   Ordem od = GerarOrdem();
   if(!od.ok) return;
   if(LogSinais) PrintFormat("SINAL %s lado=%d entrada=%.4f stop=%.4f", TimeToString(T[N - 1], TIME_DATE|TIME_MINUTES), od.lado, Norm(od.entrada), Norm(od.stop));
   EnviarOrdem(od);
   if(TemPendente() && (Setup == SET_8020 || Setup == SET_PIN)) g_dia_ultimo_trade = Dia(TimeCurrent());
}
//+------------------------------------------------------------------+
