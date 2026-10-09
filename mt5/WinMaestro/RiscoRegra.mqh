//+------------------------------------------------------------------+
//| WinMaestro/RiscoRegra.mqh                                        |
//| v2.03: a regra da parada diaria e o resultado de uma ficha em    |
//| funcoes puras, sem nenhuma dependencia do nucleo (inputs,        |
//| snapshot, corretora): a conta das fichas por deal que o          |
//| Est_Fichas (Estado.mqh) faz, a regra do Risco.mqh, e o teste     |
//| mt5/testes/WinMaestro_TesteParada.mq5 chama as mesmas funcoes.   |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_RISCOREGRA_MQH
#define WINMAESTRO_RISCOREGRA_MQH

int Risco_Sinal(const int x) { return x > 0 ? 1 : (x < 0 ? -1 : 0); }
int Risco_Abs(const int x)   { return x < 0 ? -x : x; }

// Aplica um deal de volume assinado v (+compra, -venda) ao preco `preco` na ficha (f, pm) de UM robo, como se o robo
// tivesse conta propria, e devolve o resultado realizado em R$ (sem custos). E' a unica conta de preco medio do maestro
// (Est_Aplica, a absorcao da spec 7.1 em Risco_Externo e o encerramento em Risco_Encerra passam por aqui):
//  - f = 0, ou o deal inverte o lado: preco medio = preco do deal (na inversao, a parte antiga fecha antes ao preco do deal);
//  - o deal aumenta |f|: preco medio ponderado;
//  - o deal reduz |f|: o preco medio fica e a parte fechada realiza (preco - pm) x lado x contratos x vp;
//  - f chega a 0: pm = 0.
// vp = valor de 1 ponto por contrato em R$ (SYMBOL_TRADE_TICK_VALUE / SYMBOL_TRADE_TICK_SIZE).
double Risco_Aplica(int &f, double &pm, const int v, const double preco, const double vp)
{
   int f0 = f;
   double rz = 0.0;
   if(f0 != 0 && v != 0 && Risco_Sinal(v) != Risco_Sinal(f0))
      rz = (preco - pm) * Risco_Sinal(f0) * MathMin(Risco_Abs(f0), Risco_Abs(v)) * vp;
   f += v;
   if(f == 0)                                                pm = 0.0;
   else if(f0 == 0 || Risco_Sinal(f) != Risco_Sinal(f0))     pm = preco;
   else if(Risco_Abs(f) > Risco_Abs(f0))                     pm = (pm * Risco_Abs(f0) + preco * Risco_Abs(v)) / Risco_Abs(f);
   return rz;
}

// Regra 7.1 da spec (Est_Externo) sobre as fichas f/pm e a externa ext, para um deal externo de volume assinado v (real ou
// virtual). Devolve true se absorveu ficha; ab[r] = true para cada robo que absorveu.
//  1. compensa a externa existente de sinal oposto;
//  2. o que sobra e aumenta |liquida| (ou liquida 0) -> externa;
//  3. o que sobra e reduz: absorcao nas fichas do lado reduzido, prior primeiro (B2-4, so' o virtual), depois a ordem fixa
//     do array (GB, CM, DM, RE, C1); o que nenhuma ficha absorve -> externa.
// Absorcao real: a parte absorvida e' uma saida da ficha ao preco do deal externo e realiza (rz[r] += , Risco_Aplica). Virtual
// (Delta sem deal): sem preco, so' reduz a ficha, nao realiza nada.
bool Risco_Externo(int &f[], double &pm[], int &ext, int v, const bool virtual_, const int prior, const double preco, const double vp,
                   double &rz[], bool &ab[])
{
   int n = ArraySize(f);
   if(ext != 0 && v != 0 && Risco_Sinal(ext) != Risco_Sinal(v))
   {
      int c = MathMin(Risco_Abs(ext), Risco_Abs(v));
      ext += Risco_Sinal(v) * c;
      v -= Risco_Sinal(v) * c;
   }
   if(v == 0) return false;
   int liq = ext;
   for(int r = 0; r < n; r++) liq += f[r];
   if(liq == 0 || Risco_Sinal(liq) == Risco_Sinal(v)) { ext += v; return false; }
   bool absorveu = false;
   for(int k = -1; k < n && v != 0; k++)
   {
      int r = k < 0 ? prior : k;
      if(r < 0 || r >= n || f[r] == 0 || Risco_Sinal(f[r]) != -Risco_Sinal(v)) continue;
      int dv = Risco_Sinal(v) * MathMin(Risco_Abs(f[r]), Risco_Abs(v));
      if(virtual_) { f[r] += dv; if(f[r] == 0) pm[r] = 0.0; }
      else         rz[r] += Risco_Aplica(f[r], pm[r], dv, preco, vp);
      v -= dv;
      ab[r] = true;
      absorveu = true;
   }
   if(v != 0) ext += v;
   return absorveu;
}

// Encerramento pelo C_CONTA (sec. 1.2): toda ficha sai ao preco do deal do maestro e realiza (rz[r] +=).
void Risco_Encerra(int &f[], double &pm[], const double preco, const double vp, double &rz[])
{
   int n = ArraySize(f);
   for(int r = 0; r < n; r++)
      if(f[r] != 0) rz[r] += Risco_Aplica(f[r], pm[r], -f[r], preco, vp);
}

// Fecha um deal no resultado do dia: rz[r] = o que o deal realizou (com custos) para cada robo. Se o deal e' de hoje
// (t_msc >= inicio do dia), soma no resultado de cada robo (res) e vira UM evento (a soma de todos os robos), na ordem do
// historico: um deal que realiza varias fichas (absorcao, C_CONTA) nao mostra ao pior acumulado estados intermediarios
// que a conta nunca teve. Zera rz para o proximo deal.
void Risco_FechaDeal(double &rz[], double &res[], double &ev[], const long t_msc, const long hoje_msc)
{
   int n = ArraySize(rz);
   double soma = 0.0;
   bool tem = false;
   for(int r = 0; r < n; r++)
   {
      if(rz[r] != 0.0) tem = true;
      if(t_msc >= hoje_msc) { res[r] += rz[r]; soma += rz[r]; }
      rz[r] = 0.0;
   }
   if(!tem || t_msc < hoje_msc) return;
   int k = ArraySize(ev);
   ArrayResize(ev, k + 1, 64);
   ev[k] = soma;
}

// AJUSTE (P14): dois deals externos consecutivos de volumes opostos e instantes a ate' 1 s formam o par fecha/reabre do
// ajuste (fora do continuo), sem efeito nas fichas nem no resultado. A classificacao (externos) e o "fora do continuo"
// ficam com Est_Fichas.
bool Risco_ParAjuste(const int v, const long t_msc, const int v2, const long t2_msc)
{
   return v != 0 && v2 == -v && MathAbs(t2_msc - t_msc) <= 1000;
}

// Resultado acumulado do dia a partir dos resultados liquidos dos eventos do dia, em ordem de instante: total e o PIOR
// acumulado (0 se nunca ficou negativo).
void Risco_Acumula(const double &res[], double &total, double &pior)
{
   total = 0.0; pior = 0.0;
   int n = ArraySize(res);
   for(int i = 0; i < n; i++)
   {
      total += res[i];
      if(total < pior) pior = total;
   }
}

// A parada liga com o pior acumulado <= -(pct % do capital), inclusive exatamente o limite. pct <= 0 ou capital <= 0:
// desligada. A folga de 1e-6 so' absorve o erro de ponto flutuante da soma (R$ tem 2 casas).
bool Risco_ParadaDe(const double pior, const double capital, const double pct)
{
   if(pct <= 0.0 || capital <= 0.0) return false;
   return pior <= -(capital * pct / 100.0) + 1e-6;
}

#endif
