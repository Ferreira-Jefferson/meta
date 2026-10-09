//+------------------------------------------------------------------+
//| WinMaestro_TesteParada.mq5 (script)                              |
//| Teste da parada diaria do WinMaestro v2.03: o resultado de cada  |
//| ficha e a regra da parada, pelas MESMAS funcoes que o Est_Fichas |
//| do EA chama por deal (WinMaestro/RiscoRegra.mqh): Risco_Aplica   |
//| (deal do robo), Risco_Externo (absorcao, spec 7.1), Risco_Encerra|
//| (C_CONTA), Risco_FechaDeal (um evento por deal, so' de hoje),    |
//| Risco_ParAjuste (par P14), Risco_Acumula e Risco_ParadaDe.       |
//| A classificacao dos deals (robo/maestro/externo/nao class.) fica |
//| fora: aqui cada deal ja' vem com a classe.                       |
//| Rodar: no terminal fica em MQL5\Experts\testes\; arraste para    |
//| qualquer grafico. Resultado na aba Experts: "OK n/n" ou FALHOU.  |
//| Nao manda ordem nem le a conta.                                  |
//+------------------------------------------------------------------+
#property script_show_inputs false
#property strict

#include "..\WinMaestro\RiscoRegra.mqh"

int g_ok = 0, g_n = 0;
#define VP     0.20                   // WIN: TICK_VALUE 1,00 / TICK_SIZE 5 = R$0,20 por ponto por contrato
#define HOJE   1000000000000          // inicio de hoje (ms); deals antes disso sao de ontem
#define ONTEM  (HOJE - 3600000)

//--- mini-replay: as fichas de 5 robos, a externa e os eventos do dia, deal a deal como Est_Fichas
int    tF[5];
double tPm[5];
int    tExt = 0;
double tRz[5];
double resR[5];
double tEv[];
bool   tAb[5];

void Zera(void) { ArrayInitialize(tF, 0); ArrayInitialize(tPm, 0.0); tExt = 0; ArrayInitialize(tRz, 0.0); ArrayInitialize(resR, 0.0); ArrayResize(tEv, 0); }
void Fecha(const long t) { Risco_FechaDeal(tRz, resR, tEv, t, HOJE); }
// deal do proprio robo r (CL_ROBO, Est_Aplica)
void Deal(const int r, const int v, const double preco, const long t, const double custo = 0.0) { tRz[r] += Risco_Aplica(tF[r], tPm[r], v, preco, VP) + custo; Fecha(t); }
// deal externo real (CL_EXTERNO, Est_Externo): devolve se absorveu
bool Ext(const int v, const double preco, const long t) { ArrayInitialize(tAb, false); bool a = Risco_Externo(tF, tPm, tExt, v, false, -1, preco, VP, tRz, tAb); Fecha(t); return a; }
// C_CONTA (CL_MAESTRO): toda ficha sai ao preco do deal do maestro
void CConta(const double preco, const long t) { Risco_Encerra(tF, tPm, preco, VP, tRz); Fecha(t); }
// deal de robo nao classificado (CL_NAOCLASS): so' o custo
void NaoClass(const int r, const double custo, const long t) { tRz[r] += custo; Fecha(t); }
// par de deals externos: o par AJUSTE (P14) e' pulado inteiro, senao cada um e' um externo
void Par(const int v, const double p1, const long t1, const double p2, const long t2)
{
   if(Risco_ParAjuste(v, t1, -v, t2)) return;
   Ext(v, p1, t1);
   Ext(-v, p2, t2);
}

bool Perto(const double a, const double b) { return MathAbs(a - b) < 1e-6; }
void Confere(const string nome, const bool ok, const string detalhe)
{
   g_n++;
   if(ok) g_ok++;
   PrintFormat("%s %s: %s", ok ? "ok    " : "FALHOU", nome, detalhe);
}
// confere o total do dia, um robo e a parada (capital 1000, 10%)
void ConfereDia(const string nome, const int r, const double res_r, const double total_esp, const bool para_esp)
{
   double total, pior;
   Risco_Acumula(tEv, total, pior);
   bool para = Risco_ParadaDe(pior, 1000, 10.0);
   Confere(nome, Perto(resR[r], res_r) && Perto(total, total_esp) && para == para_esp,
           StringFormat("robo %d R$%.2f (esperado %.2f), dia R$%.2f (esperado %.2f), pior %.2f, parada %s (esperado %s)",
                        r, resR[r], res_r, total, total_esp, pior, para ? "LIGA" : "nao", para_esp ? "LIGA" : "nao"));
}

// Regra da parada sobre uma lista de eventos ja' calculados
void Caso(const string nome, const double &res[], const double capital, const double pct, const bool espera, const double total_esp)
{
   double total, pior;
   Risco_Acumula(res, total, pior);
   bool para = Risco_ParadaDe(pior, capital, pct);
   Confere(nome, para == espera && Perto(total, total_esp), StringFormat("total %.2f pior %.2f -> parada %s (esperado %s)", total, pior,
           para ? "LIGA" : "nao", espera ? "LIGA" : "nao"));
}

void OnStart()
{
   //--- regra da parada
   double a[] = {-100.00};                Caso("fronteira: exatamente -10% de R$1000 para", a, 1000, 10.0, true, -100.00);
   double b[] = {-99.90};                 Caso("fronteira: -9,99% nao para", b, 1000, 10.0, false, -99.90);
   double c[] = {60.0, 50.0, -200.0};     Caso("dois gains e um stop grande: -9% nao para", c, 1000, 10.0, false, -90.0);
   double d[] = {60.0, 50.0, -210.0};     Caso("dois gains e um stop grande: chega a -10% para", d, 1000, 10.0, true, -100.0);
   double e[] = {60.0, 50.0, -230.0};     Caso("dois gains e um stop grande: -12% para", e, 1000, 10.0, true, -120.0);
   double g[] = {-210.0, 60.0, 50.0};     Caso("stop primeiro (-21%), gains depois: fica parado no dia", g, 1000, 10.0, true, -100.0);
   double h[] = {-40.10, -30.00, -29.90}; Caso("tres perdas somando exatamente -10% (ponto flutuante)", h, 1000, 10.0, true, -100.0);
   double i[] = {-700.0};                 Caso("capital R$7000: -R$700 = -10% para", i, 7000, 10.0, true, -700.0);
   double j[] = {-699.30};                Caso("capital R$7000: -R$699,30 = -9,99% nao para", j, 7000, 10.0, false, -699.30);
   double k[] = {-500.0};                 Caso("Risco_PerdaDiaPct = 0: desligada", k, 1000, 0.0, false, -500.0);
   double l[];                            Caso("pregao seguinte: nenhum deal do dia, parada desfeita", l, 1000, 10.0, false, 0.0);

   //--- resultado por robo (GB 0, CM 1, DM 2, RE 3, C1 4)
   // Caso real 2026-10-08 (demo): liquida -3 por vendas manuais @204.591,67; a ENTRADA do CM (compra 1 @207.310) recebeu
   // DEAL_PROFIT -543,67 (prejuizo da venda manual). O deal manual nao toca ficha (aumentou |liquida|: externa).
   Zera();
   Ext(-3, 204591.67, HOJE + 500);              // vendas manuais: liquida 0 -> externa -3, nenhuma ficha
   Deal(1, +1, 207310, HOJE + 1000);
   ConfereDia("real 08/10: manual -3 + entrada do CM -> CM R$0 (nao -543,67), sem parada", 1, 0.0, 0.0, false);
   Deal(1, -1, 207200, HOJE + 2000, -1.00);   // o CM sai pelo stop 110 pts abaixo, com R$1,00 de custo
   ConfereDia("real 08/10: o CM sai 110 pts abaixo -> CM -R$23,00", 1, -23.0, -23.0, false);

   // Dois robos em lados opostos (em NETTING o lucro do CM apareceria no deal do GB)
   Zera();
   Deal(1, +1, 130000, HOJE + 1000);           // CM compra
   Deal(0, -1, 130100, HOJE + 2000);           // GB vende: liquida 0, DEAL_PROFIT +20 no deal do GB
   ConfereDia("lados opostos: GB abre vendido com o CM comprado -> GB R$0", 0, 0.0, 0.0, false);
   Deal(1, -1, 130200, HOJE + 3000);           // CM sai +200 pts
   ConfereDia("lados opostos: CM sai +200 pts -> CM +R$40", 1, 40.0, 40.0, false);
   Deal(0, +1, 130050, HOJE + 4000);           // GB sai +50 pts
   ConfereDia("lados opostos: GB sai +50 pts -> GB +R$10, dia +R$50 (= soma da conta)", 0, 10.0, 50.0, false);

   // Inversao: ficha +1 @130000, deal -2 @129900 fecha a antiga (-100 pts) e abre -1 @129900
   Zera();
   Deal(2, +1, 130000, HOJE + 1000);
   Deal(2, -2, 129900, HOJE + 2000);
   Confere("inversao: ficha nova -1 ao preco do deal", tF[2] == -1 && Perto(tPm[2], 129900), StringFormat("f %d pm %.2f", tF[2], tPm[2]));
   ConfereDia("inversao: fecha a antiga -> DM -R$20", 2, -20.0, -20.0, false);
   Deal(2, +1, 129800, HOJE + 3000);
   ConfereDia("inversao: a nova sai +100 pts -> DM R$0 no dia", 2, 0.0, 0.0, false);

   // Ficha de ontem fechada hoje: a parte realizada ontem nao entra; o preco de entrada e' o da ficha (de ontem)
   Zera();
   Deal(3, +2, 130000, ONTEM);
   Deal(3, -1, 129600, ONTEM + 1000);          // -R$80 ontem: fora do dia
   Deal(3, -1, 129500, HOJE + 1000, -0.50);    // hoje: -500 pts x R$0,20 - R$0,50
   ConfereDia("ficha de ontem fechada hoje: so' o de hoje -> RE -R$100,50, parada liga", 3, -100.50, -100.50, true);

   // Preco medio ponderado: +1 @130000, +1 @130100 -> pm 130050; sai -2 @130150 -> +R$40
   Zera();
   Deal(4, +1, 130000, HOJE + 1000);
   Deal(4, +1, 130100, HOJE + 2000);
   Confere("preco medio ponderado", Perto(tPm[4], 130050), StringFormat("pm %.2f", tPm[4]));
   Deal(4, -2, 130150, HOJE + 3000);
   ConfereDia("preco medio: sai 2 a +100 pts do medio -> C1 +R$40", 4, 40.0, 40.0, false);

   // Zeragem manual absorvida (spec 7.1): a ficha sai ao preco do deal externo, o robo realiza a perda
   Zera();
   Deal(1, +1, 130000, HOJE + 1000);
   Ext(-1, 129500, HOJE + 2000);
   ConfereDia("absorcao: manual zera o CM @-500 pts -> CM -R$100, parada liga", 1, -100.0, -100.0, true);

   // C_CONTA do corte: as fichas saem ao preco do deal do maestro
   Zera();
   Deal(1, +1, 130000, HOJE + 1000);
   Deal(2, +1, 130050, HOJE + 2000);
   CConta(130100, HOJE + 3000);
   ConfereDia("C_CONTA: CM e DM zerados @130100 -> DM +R$10, dia +R$30", 2, 10.0, 30.0, false);

   // Pior acumulado com resultado por robo: GB perde 120 e depois o CM ganha 50 -> dia -70, mas a parada ja' ligou
   Zera();
   Deal(0, -1, 130000, HOJE + 1000);
   Deal(0, +1, 130600, HOJE + 2000);           // GB -600 pts = -R$120
   Deal(1, +1, 130000, HOJE + 3000);
   Deal(1, -1, 130250, HOJE + 4000);           // CM +250 pts = +R$50
   ConfereDia("pior acumulado: GB -R$120 antes do CM +R$50 -> dia -R$70, parada liga", 1, 50.0, -70.0, true);

   //--- um deal que realiza varias fichas vira UM evento (a soma): o pior acumulado nao ve estados intermediarios
   Zera();
   Deal(0, +2, 130250, HOJE + 1000);           // GB comprado 2 @130250
   Deal(1, -1, 130500, HOJE + 2000);           // CM vendido 1 @130500 (liquida +1)
   CConta(130000, HOJE + 3000);                // C_CONTA vende 1 @130000: GB -250 x 2 = -R$100, CM +500 = +R$100
   ConfereDia("C_CONTA lados opostos: GB -R$100 e CM +R$100 no mesmo deal -> dia R$0, parada NAO liga", 0, -100.0, 0.0, false);
   Confere("C_CONTA lados opostos: um evento so' (R$0)", ArraySize(tEv) == 1 && Perto(tEv[0], 0.0) && Perto(resR[1], 100.0) && tF[0] == 0 && tF[1] == 0,
           StringFormat("eventos %d, CM %.2f, fichas %d/%d", ArraySize(tEv), resR[1], tF[0], tF[1]));

   Zera();
   Deal(0, +1, 130500, HOJE + 1000);           // GB comprado @130500
   Deal(1, +1, 129500, HOJE + 2000);           // CM comprado @129500
   Confere("absorcao de 2 fichas num deal", Ext(-2, 130000, HOJE + 3000) && tAb[0] && tAb[1] && tF[0] == 0 && tF[1] == 0 && tExt == 0,
           StringFormat("ab %d/%d fichas %d/%d ext %d", tAb[0], tAb[1], tF[0], tF[1], tExt));
   ConfereDia("absorcao de 2 fichas: GB -R$100 e CM +R$100 -> um evento R$0, parada NAO liga", 1, 100.0, 0.0, false);

   //--- absorcao parcial: o que a ficha nao absorve vira externa
   Zera();
   Deal(1, +1, 130000, HOJE + 1000);
   Ext(-3, 129500, HOJE + 2000);
   Confere("absorcao parcial: CM zera, sobra -2 vira externa", tF[1] == 0 && tExt == -2, StringFormat("CM %d ext %d", tF[1], tExt));
   ConfereDia("absorcao parcial: CM -R$100 (so' o contrato absorvido), parada liga", 1, -100.0, -100.0, true);

   //--- deal nao classificado de robo: fora da ficha, so' o custo
   Zera();
   Deal(2, +1, 130000, HOJE + 1000, -1.00);
   NaoClass(2, -1.50, HOJE + 2000);
   Confere("nao classificado: ficha do DM intacta", tF[2] == 1 && Perto(tPm[2], 130000), StringFormat("f %d pm %.2f", tF[2], tPm[2]));
   ConfereDia("nao classificado: DM so' os custos -R$2,50", 2, -2.50, -2.50, false);

   //--- absorcao virtual (Delta sem deal): reduz a ficha, nao realiza nada nem gera evento
   Zera();
   Deal(1, +1, 130000, HOJE + 1000);
   ArrayInitialize(tAb, false);
   bool av = Risco_Externo(tF, tPm, tExt, -1, true, 1, 0.0, VP, tRz, tAb);
   Confere("absorcao virtual: CM absorve, nada realizado", av && tAb[1] && tF[1] == 0 && Perto(tPm[1], 0.0) && Perto(tRz[1], 0.0) && ArraySize(tEv) == 0 && Perto(resR[1], 0.0),
           StringFormat("ab %d f %d pm %.2f rz %.2f eventos %d", tAb[1], tF[1], tPm[1], tRz[1], ArraySize(tEv)));

   //--- virada do dia: deal das 23:59 de ontem nao entra; o das 00:00 de hoje entra
   Zera();
   Deal(3, +1, 130000, ONTEM);
   Deal(3, -1, 129500, HOJE - 60000);          // ontem 23:59: -R$100, fora do dia
   Deal(3, +1, 130000, HOJE - 30000);
   Deal(3, -1, 129750, HOJE);                  // hoje 00:00:00.000: -R$50, dentro
   ConfereDia("virada do dia: so' o deal de 00:00 conta -> RE -R$50, parada nao liga (o -R$100 de 23:59 ficou ontem)", 3, -50.0, -50.0, false);

   //--- par AJUSTE (P14): fecha/reabre de mesmo volume a ate' 1 s, sem efeito nas fichas nem no resultado
   Zera();
   Deal(1, +2, 130000, HOJE + 1000);
   Par(-2, 129000, HOJE + 2000, 129000, HOJE + 2500);
   Confere("par AJUSTE ignorado: CM +2 @130000 intacto, nada realizado", tF[1] == 2 && Perto(tPm[1], 130000) && Perto(resR[1], 0.0) && tExt == 0,
           StringFormat("f %d pm %.2f CM %.2f ext %d", tF[1], tPm[1], resR[1], tExt));
   Confere("par a 1,5 s nao e' AJUSTE", !Risco_ParAjuste(-2, HOJE + 2000, 2, HOJE + 3500) && !Risco_ParAjuste(-2, HOJE + 2000, 1, HOJE + 2500), "");

   PrintFormat("WinMaestro_TesteParada: %s %d/%d", g_ok == g_n ? "OK" : "FALHOU", g_ok, g_n);
}
