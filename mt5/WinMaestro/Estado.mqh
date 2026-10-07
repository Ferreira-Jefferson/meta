//+------------------------------------------------------------------+
//| WinMaestro/Estado.mqh                                            |
//| Passo 3 do ciclo (sec. 3): derivacao. Fichas pelos deals, papel  |
//| pelo mapa, absorcao (spec 7.1), encerramento (deal MAESTRO),     |
//| situacao, provado, Delta, confiavel (sec. 1.3, sec. 2.2), prazos |
//| de restricao (sec. 2.3), eventos e Tick dos modulos (sec. 7).    |
//| Nada aqui e' guardado entre ciclos alem do que a Tipos.mqh marca |
//| como memoria/RAM: tudo o mais e' refeito do snapshot.            |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_ESTADO_MQH
#define WINMAESTRO_ESTADO_MQH

#include "Mapa.mqh"
#include "Memoria.mqh"

//--- ganchos dos modulos (definidos no EA e no EA de teste)
int    Robo_Init(const int r, const VistaRobo &v);
void   Robo_Tick(const int r, const VistaRobo &v, Intencao &i);
void   Robo_Evento(const int r, const SEvento &e, const VistaRobo &v, Intencao &i);
double Robo_StopRegra(const int r, const int lado);
int    Robo_MinutoZerar(const int r, const datetime dia);
//--- Partida.mqh
void   Mae_Bloqueia(const string causa);
void   Mae_GravaMemoria(const bool forcar);

#define CL_IGNORA   0
#define CL_ROBO     1
#define CL_EXTERNO  2
#define CL_MAESTRO  3
#define CL_NAOCLASS 4

//+------------------------------------------------------------------+
//| Listas de tickets (memoria)                                      |
//+------------------------------------------------------------------+
bool Est_NaLista(const ulong &lista[], const ulong tk) { int n = ArraySize(lista); for(int i = 0; i < n; i++) if(lista[i] == tk) return true; return false; }
void Est_PoeLista(ulong &lista[], const ulong tk, const int maximo)
{
   if(Est_NaLista(lista, tk)) return;
   int n = ArraySize(lista);
   if(n >= maximo) { for(int i = 0; i < n - 1; i++) lista[i] = lista[i + 1]; n--; }
   ArrayResize(lista, n + 1);
   lista[n] = tk;
}
bool Est_Reconhecido(const ulong tk) { return Est_NaLista(mzReconh, tk); }

//+------------------------------------------------------------------+
//| id_entrada consumidos (sec. 1.2)                                 |
//+------------------------------------------------------------------+
bool Est_Consumido(const int r, const long id)
{
   int n = ArraySize(mzConsId);
   for(int i = 0; i < n; i++) if(mzConsR[i] == r && mzConsId[i] == id) return true;
   return false;
}
void Est_DesConsome(const int r, const long id)
{
   int n = ArraySize(mzConsId), w = 0;
   for(int i = 0; i < n; i++)
   {
      if(mzConsR[i] == r && mzConsId[i] == id) continue;
      mzConsR[w] = mzConsR[i]; mzConsId[w] = mzConsId[i]; w++;
   }
   ArrayResize(mzConsR, w); ArrayResize(mzConsId, w);
}
void Est_Consome(const int r, const long id)
{
   if(id == 0 || Est_Consumido(r, id)) return;
   int n = ArraySize(mzConsId);
   if(n >= 200) { for(int i = 0; i < n - 1; i++) { mzConsR[i] = mzConsR[i + 1]; mzConsId[i] = mzConsId[i + 1]; } n--; }
   ArrayResize(mzConsR, n + 1); ArrayResize(mzConsId, n + 1);
   mzConsR[n] = r; mzConsId[n] = id;
}

//+------------------------------------------------------------------+
//| Classificacao do deal (sec. 1.2, 1.3)                            |
//+------------------------------------------------------------------+
// Robo do deal: pela linha do mapa da ordem; sem linha, pelo DEAL_MAGIC; sem ele, pelo ORDER_MAGIC no historico.
// Papel: o do mapa; fora do mapa, pelo tipo da ordem no historico (stop = S, outro = X, nunca E). Deal cuja
// ordem nao esta' no mapa nem no historico = nao classificado, sem prazo (salvo reconhecido pelo botao).
int Est_Classifica(const int di, int &robo, int &papel)
{
   robo = -1; papel = 0;
   int tp = mzDeal[di].tipo;
   if(tp != DEAL_TYPE_BUY && tp != DEAL_TYPE_SELL) return CL_IGNORA;
   ulong ord = mzDeal[di].ordem;
   int li = Mapa_IdxTicket(ord);
   if(li >= 0)
   {
      robo = mzL[li].robo; papel = mzL[li].papel;
      return robo == R_MAE ? CL_MAESTRO : CL_ROBO;
   }
   long mg = mzDeal[di].magic;
   if(mg == MAGIC_MAESTRO) { robo = R_MAE; papel = P_X; return CL_MAESTRO; }
   int hi = Snap_HistIdx(ord);
   int rd = Mae_Robo(mg);
   if(rd >= 0 && rd < NROBOS)
   {
      robo = rd;
      if(hi >= 0) { papel = Mae_TipoStop(mzOH[hi].tipo) ? P_S : P_X; return CL_ROBO; }
      if(Est_Reconhecido(mzDeal[di].ticket)) { papel = P_X; return CL_ROBO; }
      return CL_NAOCLASS;
   }
   if(mg != 0) return CL_EXTERNO;
   if(hi >= 0)
   {
      long hm = mzOH[hi].magic;
      if(hm == MAGIC_MAESTRO) { robo = R_MAE; papel = P_X; return CL_MAESTRO; }
      int rr = Mae_Robo(hm);
      if(rr >= 0 && rr < NROBOS) { robo = rr; papel = Mae_TipoStop(mzOH[hi].tipo) ? P_S : P_X; return CL_ROBO; }
      return CL_EXTERNO;
   }
   if(Est_Reconhecido(mzDeal[di].ticket)) return CL_EXTERNO;
   return CL_NAOCLASS;
}
int Est_VolDeal(const int di) { return (mzDeal[di].tipo == DEAL_TYPE_BUY ? 1 : -1) * (int)MathRound(mzDeal[di].vol); }

//+------------------------------------------------------------------+
//| Fichas (sec. 1.3)                                                |
//+------------------------------------------------------------------+
int    eF[NROBOS];
double ePm[NROBOS];
long   eHora[NROBOS];
ulong  eId[NROBOS];
int    ePab[NROBOS];
bool   eAbsReal[NROBOS];
bool   eAbsVirt[NROBOS];
int    eNc[NROBOS];
int    eExt = 0;

void Est_Zera(const int r) { eF[r] = 0; ePm[r] = 0.0; eHora[r] = 0; eId[r] = 0; ePab[r] = 0; }

void Est_Aplica(const int r, const int v, const double preco, const long t, const ulong tk, const int papel)
{
   int f0 = eF[r];
   eF[r] += v;
   if(eF[r] == 0) { Est_Zera(r); return; }
   if(f0 == 0 || Mae_Sinal(f0) != Mae_Sinal(eF[r])) { ePm[r] = preco; eHora[r] = t; eId[r] = tk; ePab[r] = papel; return; }
   if(Mae_Abs(eF[r]) > Mae_Abs(f0)) ePm[r] = (ePm[r] * Mae_Abs(f0) + preco * Mae_Abs(v)) / Mae_Abs(eF[r]);
}

// Absorve na ficha de r o que der de v (v reduz |f| de r); devolve true se absorveu.
bool Est_Absorve(const int r, int &v, const bool virtual_)
{
   if(v == 0 || eF[r] == 0 || Mae_Sinal(eF[r]) != -Mae_Sinal(v)) return false;
   int a = MathMin(Mae_Abs(eF[r]), Mae_Abs(v));
   eF[r] += Mae_Sinal(v) * a;
   v -= Mae_Sinal(v) * a;
   if(virtual_) eAbsVirt[r] = true; else eAbsReal[r] = true;
   if(eF[r] == 0) Est_Zera(r);
   return true;
}

// Regra 7.1 da spec para um deal externo de volume assinado v (real ou virtual). Devolve true se absorveu ficha.
// prior >= 0 (so' o virtual, B2-4): o robo cujo deal explica o Delta absorve primeiro; o resto segue a ordem fixa.
bool Est_Externo(int v, const bool virtual_, const int prior = -1)
{
   // 1. compensa a externa existente de sinal oposto
   if(eExt != 0 && Mae_Sinal(eExt) != Mae_Sinal(v))
   {
      int c = MathMin(Mae_Abs(eExt), Mae_Abs(v));
      eExt += Mae_Sinal(v) * c;
      v -= Mae_Sinal(v) * c;
   }
   if(v == 0) return false;
   int soma = 0;
   for(int r = 0; r < NROBOS; r++) soma += eF[r];
   int liq = soma + eExt;
   // 2. o que sobra e aumenta |liquida| -> externa
   if(liq == 0 || Mae_Sinal(liq) == Mae_Sinal(v)) { eExt += v; return false; }
   // 3. o que sobra e reduz: absorcao nas fichas do lado reduzido, ordem fixa GB, CM, DM, RE, C1 (o robo atribuido antes)
   bool absorveu = false;
   if(prior >= 0 && prior < NROBOS && Est_Absorve(prior, v, virtual_)) absorveu = true;
   for(int r = 0; r < NROBOS && v != 0; r++) if(Est_Absorve(r, v, virtual_)) absorveu = true;
   if(v != 0) eExt += v;
   return absorveu;
}

// B2-4 (v2.02): o robo cujo deal explica o Delta estavel d. Candidata = linha E/S/A/X de robo sem deal na janela, do
// lado de d, que estava sem desfecho quando o Delta apareceu: PENDENTE ou SUMIDA, ou NAO_EXECUTADA por ausencia (nunca vista
// no historico como CANCELED/REJECTED/EXPIRED), com envio (ou sumico) ate' PROVA antes de delta_desde e nao depois dele; e
// o robo tem ficha do lado que d reduz. Exatamente um robo com candidata -> ele; nenhum ou mais de um -> -1 (ordem fixa,
// spec 7.1; registrado no sec. 11 do desenho).
int Est_RoboDoDelta(const int d)
{
   if(d == 0 || mzDeltaDesde <= 0) return -1;
   int achou = -1;
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      int r = mzL[i].robo;
      if(r < 0 || r >= NROBOS || !Mapa_TemTicketProprio(mzL[i].papel)) continue;
      int de = mzL[i].desfecho;
      if(de != D_PENDENTE && de != D_SUMIDA && de != D_NAO_EXECUTADA) continue;
      if(de == D_NAO_EXECUTADA && Snap_HistFinalNao(mzL[i].estado_hist)) continue;   // o historico mostra que nao executou
      if(Mae_LadoTipo(mzL[i].tipo) != Mae_Sinal(d) || Snap_DealDaOrdem(mzL[i].ticket) >= 0) continue;
      if(eF[r] == 0 || Mae_Sinal(eF[r]) != -Mae_Sinal(d)) continue;
      long desde = MathMax(mzL[i].enviado_mono, mzL[i].sumida_mono);
      if(desde > mzDeltaDesde || mzDeltaDesde - desde > PROVA_MS) continue;
      if(achou >= 0 && achou != r) return -1;                                       // dois robos: sem atribuicao
      achou = r;
   }
   return achou;
}

// Calcula as fichas a partir dos deals da janela. Efeitos colaterais (log de ABSORVIDA, bloqueio) so' uma vez por ticket.
void Est_Fichas(void)
{
   for(int r = 0; r < NROBOS; r++) { Est_Zera(r); eAbsReal[r] = false; eAbsVirt[r] = false; eNc[r] = 0; }
   eExt = mzExtDesc;
   int run = mzExtDesc;       // liquida corrida
   int ncSoma = 0;
   mzNaoClassTotal = 0;
   int n = ArraySize(mzDeal);
   for(int i = 0; i < n; i++)
   {
      int robo, papel;
      int cl = Est_Classifica(i, robo, papel);
      if(cl == CL_IGNORA) continue;
      int v = Est_VolDeal(i);
      // AJUSTE (P14): par fecha/reabre externo de mesmo volume e instante, fora do continuo: sem efeito
      if(cl == CL_EXTERNO && i + 1 < n && !Mae_Continuo((datetime)(mzDeal[i].time_msc / 1000)))
      {
         int r2, p2;
         int cl2 = Est_Classifica(i + 1, r2, p2);
         if(cl2 == CL_EXTERNO && Est_VolDeal(i + 1) == -v && MathAbs(mzDeal[i + 1].time_msc - mzDeal[i].time_msc) <= 1000)
         {
            if(!Est_NaLista(mzDealsLog, mzDeal[i].ticket))
            {
               Log("ALERTA", "MAESTRO", "AJUSTE", StringFormat("par fecha/reabre #%I64u/#%I64u de %d contrato(s) fora do continuo: sem efeito nas fichas (P14 sem resposta)",
                   mzDeal[i].ticket, mzDeal[i + 1].ticket, Mae_Abs(v)));
               Est_PoeLista(mzDealsLog, mzDeal[i].ticket, 500);
               Est_PoeLista(mzDealsLog, mzDeal[i + 1].ticket, 500);
            }
            i++;
            continue;
         }
      }
      run += v;
      if(cl == CL_ROBO)          Est_Aplica(robo, v, mzDeal[i].preco, mzDeal[i].time_msc, mzDeal[i].ticket, papel);
      else if(cl == CL_MAESTRO)
      {
         // encerramento (sec. 1.2, RV2 N-4): todas as fichas a 0; a externa e' a liquida que sobra; sem absorcao nem bloqueio
         for(int r = 0; r < NROBOS; r++) Est_Zera(r);
         eExt = run - ncSoma;
      }
      else if(cl == CL_EXTERNO)
      {
         bool absorveu = Est_Externo(v, false);
         if(absorveu && !Est_NaLista(mzAbsVistas, mzDeal[i].ticket))
         {
            Est_PoeLista(mzAbsVistas, mzDeal[i].ticket, 500);
            Log("ALERTA", "MAESTRO", "ABSORVIDA", StringFormat("deal externo #%I64u (%+d @%.0f, magic %I64d) reduziu a liquida abaixo da soma das fichas: zeragem manual absorvida (ordem GB, CM, DM, RE, C1)",
                mzDeal[i].ticket, v, mzDeal[i].preco, mzDeal[i].magic));
            if(!Est_Reconhecido(mzDeal[i].ticket)) Mae_Bloqueia(StringFormat("zeragem manual (deal #%I64u)", mzDeal[i].ticket));
         }
      }
      else   // CL_NAOCLASS
      {
         mzNaoClassTotal++;
         ncSoma += v;
         if(robo >= 0 && robo < NROBOS) eNc[robo]++;
      }
   }
   mzSomaDeals = run - mzExtDesc;
   mzDelta = mzLiq - run;
   // Delta_resto: descontadas as linhas EXECUTADA ainda sem deal (sec. 2.2)
   int semDeal = 0;
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
      if(mzL[i].desfecho == D_EXECUTADA && Mapa_TemTicketProprio(mzL[i].papel) && Snap_DealDaOrdem(mzL[i].ticket) < 0)
         semDeal += Mae_LadoTipo(mzL[i].tipo) * (int)MathRound(mzL[i].vol);
   mzDeltaResto = mzDelta - semDeal;
}

//+------------------------------------------------------------------+
//| Ordens vivas e pendentes do robo (sec. 1.3)                      |
//+------------------------------------------------------------------+
double Est_Cob(const int r, const int lado)
{
   if(lado == 0) return 0.0;
   double c = 0.0;
   for(int k = 0; k < mzEst[r].nS; k++)
   {
      int v = mzEst[r].sIdx[k];
      if(Mae_LadoTipo(mzViva[v].tipo) == -lado) c += mzViva[v].vol;
   }
   return c;
}

void Est_Ordens(const int r)
{
   mzEst[r].nS = 0; mzEst[r].iE = -1; mzEst[r].iA = -1; mzEst[r].nFora = 0; mzEst[r].lE = -1;
   mzEst[r].pendS = false; mzEst[r].pendE = false; mzEst[r].pendA = false; mzEst[r].pendX = false; mzEst[r].pendK = false; mzEst[r].pendM = false;
   mzEst[r].ePendLado = 0; mzEst[r].ePendPreco = 0.0;
   bool algum = false;
   int nv = ArraySize(mzViva);
   for(int k = 0; k < nv; k++)
   {
      if(mzViva[k].magic != mzMagic[r]) continue;
      int li = Mapa_IdxTicket(mzViva[k].ticket);
      int papel = (li >= 0) ? mzL[li].papel : (Mae_TipoStop(mzViva[k].tipo) ? P_S : (Mae_TipoLimite(mzViva[k].tipo) ? -1 : 0));
      if(papel == P_S)       { if(mzEst[r].nS < MAX_ORD) mzEst[r].sIdx[mzEst[r].nS++] = k; }
      else if(papel == P_E && Mae_TipoMercado(mzViva[k].tipo)) { mzEst[r].pendE = true; algum = true; mzEst[r].ePendLado = Mae_LadoTipo(mzViva[k].tipo); mzEst[r].ePendPreco = 0.0; if(mzEst[r].lE < 0) mzEst[r].lE = li; }   // E a mercado nunca e' "viva" para L1/X2
      else if(papel == P_E && mzEst[r].iE < 0) { mzEst[r].iE = k; mzEst[r].lE = li; }
      else if(papel == P_A && mzEst[r].iA < 0) mzEst[r].iA = k;
      else if(papel == P_X)  { mzEst[r].pendX = true; algum = true; }
      else if(Mae_TipoLimite(mzViva[k].tipo)) { if(mzEst[r].nFora < MAX_ORD) mzEst[r].foraIdx[mzEst[r].nFora++] = k; }   // limite fora do mapa (L4) ou excedente
   }
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      if(mzL[i].robo != r || !Mapa_Pendente(i)) continue;
      algum = true;
      switch(mzL[i].papel)
      {
         case P_S: mzEst[r].pendS = true; break;
         case P_A: mzEst[r].pendA = true; break;
         case P_X: mzEst[r].pendX = true; break;
         case P_K: mzEst[r].pendK = true; break;
         case P_M: mzEst[r].pendM = true; break;
         case P_E:
            mzEst[r].pendE = true;
            mzEst[r].ePendLado = Mae_LadoTipo(mzL[i].tipo);
            mzEst[r].ePendPreco = mzL[i].preco;
            if(mzEst[r].lE < 0) mzEst[r].lE = i;
            break;
      }
   }
   mzEst[r].reduz_pend = mzEst[r].pendS || mzEst[r].pendA || mzEst[r].pendX;
   mzEst[r].nada_pend = !algum;
   int f = mzEst[r].f;
   if(f != 0)                   mzEst[r].lado_prot = Mae_Sinal(f);
   else if(mzEst[r].iE >= 0)    mzEst[r].lado_prot = Mae_LadoTipo(mzViva[mzEst[r].iE].tipo);
   else if(mzEst[r].pendE)      mzEst[r].lado_prot = mzEst[r].ePendLado;
   else                         mzEst[r].lado_prot = 0;
   mzEst[r].cobertura = Est_Cob(r, mzEst[r].lado_prot);
}

//+------------------------------------------------------------------+
//| provado / confiavel / lado inequivoco (sec. 2.2)                 |
//+------------------------------------------------------------------+
bool Est_Provado(const int r)
{
   if(!mzHistOk || eNc[r] > 0) return false;
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      if(mzL[i].robo != r) continue;
      if(Mapa_Pendente(i)) return false;
      if(mzL[i].desfecho == D_EXECUTADA && Mapa_TemTicketProprio(mzL[i].papel) && Snap_DealDaOrdem(mzL[i].ticket) < 0) return false;
   }
   return true;
}

void Est_Confianca(void)
{
   mzTodosProvados = true;
   for(int r = 0; r < NROBOS; r++)
   {
      mzEst[r].provado = Est_Provado(r);
      if(!mzEst[r].provado) mzTodosProvados = false;
   }
   // Delta externo estavel (sec. 2.2, regra de 2026-10-07 no sec. 11): Delta_resto com o MESMO valor ha' PROVA, historico lido e
   // conexao ok o tempo todo. Nao depende de todos os robos estarem provados: um robo nao provado ja' nao e' confiavel por
   // conta propria, e uma diferenca externa duradoura nao pode congelar todos a cada ordem de qualquer um (M-1).
   if(!mzHistOk || mzDeltaResto == 0 || !mzConexaoOk) { mzDeltaDesde = 0; mzDeltaVal = 0; }
   else if(mzDeltaDesde == 0 || mzDeltaResto != mzDeltaVal) { mzDeltaVal = mzDeltaResto; mzDeltaDesde = mzMono; }
   mzDeltaEstavel = mzDeltaDesde > 0 && mzMono - mzDeltaDesde >= PROVA_MS;
   Log_Cond("delta", mzDeltaEstavel, "ALERTA", "MAESTRO", "EXTERNA",
            StringFormat("liquida %+d difere dos deals da janela em %+d ha' 30 s com tudo provado: deal externo virtual (sec. 2.2); bloqueio automatico se absorver", mzLiq, mzDeltaResto));
}

//+------------------------------------------------------------------+
//| Derivacao completa (passo 3, parte 1)                            |
//+------------------------------------------------------------------+
void Est_Deriva(void)
{
   if(mzHistOk)
   {
      Est_Fichas();
      // externa de origem desconhecida (gravada pelo botao): regra de saida (A-1). Ela so' existe para explicar uma posicao
      // anterior a' janela; vale enquanto essa posicao existe. Zera:
      //  - no dia novo (Mae_DiaNovo): a janela recomeca, e o corte da vespera deixou a liquida em 0;
      //  - durante o dia, quando a liquida real e os deals da janela somam 0 por PROVA seguidos com o historico lido: nada na
      //    janela fecha a posicao antiga e nao ha' posicao a explicar, entao ela so' fabricaria um Delta. Os 30 s seguram o
      //    deal atrasado (a posicao zera antes de o deal de fechamento aparecer: sem a espera, a externa sumiria cedo demais).
      // Com o deal de fechamento DENTRO da janela (zeragem manual, ou o C_CONTA do corte) a soma dos deals nao e' 0 e ela fica
      // ate' o dia novo: e' ela que explica esse deal.
      if(mzExtDesc != 0 && mzLiq == 0 && mzSomaDeals == 0)
      {
         if(mzExtZeroDesde == 0) mzExtZeroDesde = mzMono;
         if(mzMono - mzExtZeroDesde >= PROVA_MS)
         {
            Log("AVISO", "MAESTRO", "EXTERNA", StringFormat("liquida e deals da janela em 0 ha' 30 s: externa de origem desconhecida %+d deixa de valer", mzExtDesc));
            mzExtDesc = 0;
            mzExtZeroDesde = 0;
            Est_Fichas();
         }
      }
      else mzExtZeroDesde = 0;
      Est_Confianca();
      mzAbsVirtual = false;
      if(mzDeltaEstavel && mzDeltaResto != 0)
      {
         Est_Externo(mzDeltaResto, true, Est_RoboDoDelta(mzDeltaResto));
         for(int r = 0; r < NROBOS; r++) if(eAbsVirt[r]) mzAbsVirtual = true;
      }
      mzExterna = eExt;
      for(int r = 0; r < NROBOS; r++)
      {
         mzEst[r].f = eF[r];
         mzEst[r].preco = ePm[r];
         mzEst[r].hora_msc = eHora[r];
         mzEst[r].id = eId[r];
         mzEst[r].papel_ab = ePab[r];
         mzEst[r].abs_virtual = eAbsVirt[r];
         mzEst[r].nao_class = eNc[r];
         int af = Mae_Abs(eF[r]);
         if(af == 0)               mzEst[r].sit = SIT_ZERO;
         else if(af >= 2)          mzEst[r].sit = SIT_DUPLICADA;
         else if(ePab[r] == P_E)   mzEst[r].sit = SIT_LEGITIMA;
         else                      mzEst[r].sit = SIT_TROCADA;
         mzEst[r].noite = af != 0 && Mae_Dia((datetime)(eHora[r] / 1000)) < Mae_Dia(mzAgora);
      }
   }
   else
   {
      // historico ilegivel: as fichas ficam as do ultimo calculo; ninguem e' provado (todos RESTRITOS, sec. 1.1)
      mzTodosProvados = false;
      mzExtZeroDesde = 0;
      mzDeltaDesde = 0;
      mzDeltaEstavel = false;
      for(int r = 0; r < NROBOS; r++) mzEst[r].provado = false;
   }
   for(int r = 0; r < NROBOS; r++)
   {
      Est_Ordens(r);
      bool conf = mzEst[r].provado && mzNaoClassTotal == 0 && (mzDeltaResto == 0 || mzDeltaEstavel);
      mzEst[r].confiavel = conf;
      int f = mzEst[r].f;
      mzEst[r].inequivoco = mzEst[r].provado && mzNaoClassTotal == 0 &&
                            ((f == 0 && mzEst[r].iE >= 0) || (f != 0 && Mae_Sinal(mzLiq) == Mae_Sinal(f)));
   }
}

//+------------------------------------------------------------------+
//| Recuo da janela (spec 3.2; sec. 1.1)                             |
//+------------------------------------------------------------------+
void Est_Recuo(void)
{
   if(!mzHistOk || mzDeltaResto == 0) return;
   bool pede = mzDeltaEstavel;   // com ou sem memoria: so' diferenca estavel recua (B-4)
   if(!pede || mzRecuoN >= RECUO_MAX || mzMono - mzRecuoUlt < RELEITURA_MS) return;
   datetime ant = Mae_PregaoAnterior(mzJanIni);
   mzJanRecuo = Mae_InicioDe(ant) - 600;
   mzJanRecuoDia = Mae_Dia(mzAgora);
   mzRecuoN++;
   mzRecuoUlt = mzMono;
   Log("AVISO", "MAESTRO", "HISTORICO", StringFormat("liquida %+d e deals da janela diferem em %+d: janela recua para %s (%d de %d)",
       mzLiq, mzDeltaResto, TimeToString(mzJanRecuo, TIME_DATE | TIME_MINUTES), mzRecuoN, RECUO_MAX));
}

//+------------------------------------------------------------------+
//| Log de deals (ENTROU/SAIU/EXTERNA), PRONTO com o EA fora (sec. 6)|
//+------------------------------------------------------------------+
void Est_LogDeals(void)
{
   if(!mzHistOk) return;
   int n = ArraySize(mzDeal);
   for(int i = 0; i < n; i++)
   {
      if(Est_NaLista(mzDealsLog, mzDeal[i].ticket)) continue;
      int robo, papel;
      int cl = Est_Classifica(i, robo, papel);
      if(cl == CL_NAOCLASS || cl == CL_IGNORA) continue;
      Est_PoeLista(mzDealsLog, mzDeal[i].ticket, 500);
      string fora = (mzDeal[i].time_msc < mzPartidaMsc) ? " [com o EA fora]" : "";
      string det = StringFormat("deal #%I64u ord #%I64u %s %.0f @%.0f as %s%s", mzDeal[i].ticket, mzDeal[i].ordem,
                                mzDeal[i].tipo == DEAL_TYPE_BUY ? "compra" : "venda", mzDeal[i].vol, mzDeal[i].preco, Log_HmsMsc(mzDeal[i].time_msc), fora);
      if(cl == CL_ROBO)          Log(fora != "" ? "AVISO" : "INFO", mzNome[robo], papel == P_E ? "ENTROU" : "SAIU", StringFormat("papel %s; %s", Mae_Papel(papel), det));
      else if(cl == CL_MAESTRO)  Log("INFO", "MAESTRO", "CORTE", "C_CONTA executado (encerramento): " + det);
      else                       Log("AVISO", "MAESTRO", "EXTERNA", StringFormat("deal externo (magic %I64d): %s", mzDeal[i].magic, det));
   }
}

//+------------------------------------------------------------------+
//| Correcoes (decisao 1): a 2a em 10 min liga o bloqueio com botao  |
//+------------------------------------------------------------------+
void Est_Correcoes(void)
{
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      int r = mzL[i].robo;
      if(r < 0 || r >= NROBOS || mzL[i].papel != P_X || mzL[i].motivo != "I2" || mzL[i].desfecho != D_EXECUTADA || (mzL[i].ev & 4) != 0) continue;
      int dl = Snap_DealDaOrdem(mzL[i].ticket);
      if(dl < 0) continue;
      mzL[i].ev |= 4;
      long t = mzDeal[dl].time_msc;
      Log("AVISO", mzNome[r], "CORRECAO", StringFormat("correcao executada: deal #%I64u", mzDeal[dl].ticket));
      if(mzUltCorrMsc[r] > 0 && t - mzUltCorrMsc[r] < (long)CORRECAO_JANELA_S * 1000)
         Mae_Bloqueia(StringFormat("%s: 2a correcao em 10 min", mzNome[r]));
      mzUltCorrMsc[r] = t;
   }
}

//+------------------------------------------------------------------+
//| Episodios (sec. 1.2)                                             |
//+------------------------------------------------------------------+
void Est_FechaEpisodio(const int r, const string porque)
{
   if(!mzEpAberto[r]) return;
   mzEpAberto[r] = false;
   mzEmerg[r] = 0.0; mzEmergLado[r] = 0;
   mzNivS[r] = 0.0; mzNivSIntUlt[r] = 0.0; mzNivA[r] = 0.0;
   mzSCruzDesde[r] = 0;
   Log("INFO", mzNome[r], "EPISODIO", StringFormat("episodio %d fechado (%s)", mzEp[r], porque));
}

void Est_Episodios(void)
{
   bool faseConta = Mae_FaseConta(mzAgora);
   for(int r = 0; r < NROBOS; r++)
   {
      if(!mzEpAberto[r]) continue;
      if(faseConta) { if(mzLiq == 0) Est_FechaEpisodio(r, "corte: liquida 0"); continue; }
      if(!mzEst[r].provado || mzEst[r].f != 0) continue;
      bool vivo = false;
      int nv = ArraySize(mzViva);
      for(int k = 0; k < nv && !vivo; k++) if(mzViva[k].magic == mzMagic[r]) vivo = true;
      int nl = ArraySize(mzL);
      for(int i = 0; i < nl && !vivo; i++) if(mzL[i].robo == r && (Mapa_Pendente(i) || mzL[i].desfecho == D_VIVA)) vivo = true;
      if(!vivo) Est_FechaEpisodio(r, "ficha 0 e nenhuma ordem viva ou pendente");
   }
}

//+------------------------------------------------------------------+
//| Prazos de restricao (sec. 2.3), S faltando (decisao m)           |
//+------------------------------------------------------------------+
void Est_Prazos(void)
{
   bool janela = Mae_JanelaPrazos(mzAgora);
   bool auto_ = false;
   for(int r = 0; r < NROBOS; r++)
   {
      if(!janela || mzEst[r].confiavel) mzRestritoDesde[r] = 0;
      else if(mzRestritoDesde[r] == 0) mzRestritoDesde[r] = mzMono;
      long ha = mzRestritoDesde[r] > 0 ? mzMono - mzRestritoDesde[r] : 0;
      if(ha >= PRAZO_BLOQUEIO_MS) auto_ = true;
      Log_Cond(StringFormat("restrito.%d", r), ha >= PRAZO_BLOQUEIO_MS, "ALERTA", mzNome[r], "ESTADO",
               StringFormat("RESTRITO ha' %d s (provado %s, nao classificados %d, Delta_resto %+d): bloqueio de entradas", (int)(ha / 1000),
                            mzEst[r].provado ? "sim" : "nao", mzNaoClassTotal, mzDeltaResto));
      if(ha >= PRAZO_BOTAO_MS && !mzBloqBotao) Mae_Bloqueia(StringFormat("%s RESTRITO ha' 10 min", mzNome[r]));
      // S faltando com a ficha aberta (decisao m)
      int f = mzEst[r].f;
      if(f != 0 && Est_Cob(r, Mae_Sinal(f)) < Mae_Abs(f)) { if(mzSFaltaDesde[r] == 0) mzSFaltaDesde[r] = mzMono; }
      else mzSFaltaDesde[r] = 0;
   }
   mzBloqAuto = auto_ || mzAbsVirtual;
}
bool Mae_Bloqueio(void) { return mzBloqBotao || mzBloqAuto; }

//+------------------------------------------------------------------+
//| Vista e getters dos modulos (sec. 7)                             |
//+------------------------------------------------------------------+
void Est_Vista(const int r)
{
   mzVista[r].agora = mzAgora;
   bool tem = mzEst[r].sit == SIT_LEGITIMA;
   mzVista[r].tem = tem;
   mzVista[r].lado = tem ? Mae_Sinal(mzEst[r].f) : 0;
   mzVista[r].preco = tem ? mzEst[r].preco : 0.0;
   mzVista[r].hora = tem ? (datetime)(mzEst[r].hora_msc / 1000) : 0;
   mzVista[r].id = tem ? mzEst[r].id : 0;
   mzVista[r].stop_pedido = mzNivS[r];
   mzVista[r].alvo_vivo = mzEst[r].iA >= 0 ? mzViva[mzEst[r].iA].preco : 0.0;
   int ie = mzEst[r].iE;
   mzVista[r].tem_entrada = ie >= 0;
   mzVista[r].ent_lado = ie >= 0 ? Mae_LadoTipo(mzViva[ie].tipo) : 0;
   mzVista[r].ent_preco = ie >= 0 ? mzViva[ie].preco : 0.0;
   mzVista[r].ent_id = (ie >= 0 && mzEst[r].lE >= 0) ? mzL[mzEst[r].lE].id_entrada : 0;
   mzVista[r].ent_setup = ie >= 0 ? (datetime)(mzViva[ie].setup_msc / 1000) : 0;
   mzVista[r].continuo = Mae_Continuo(mzAgora);
}

bool     Ficha_Tem(const int r)       { return mzVista[r].tem; }
int      Ficha_Lado(const int r)      { return mzVista[r].lado; }
double   Ficha_Preco(const int r)     { return mzVista[r].preco; }
datetime Ficha_Hora(const int r)      { return mzVista[r].hora; }
ulong    Ficha_Id(const int r)        { return mzVista[r].id; }
double   Ficha_Stop(const int r)      { return mzVista[r].stop_pedido; }
bool     Ficha_TemAlvo(const int r)   { return mzVista[r].alvo_vivo > 0.0; }
bool     Ficha_Entrada(const int r, int &lado, double &preco, datetime &setup)
{
   if(!mzVista[r].tem_entrada) return false;
   lado = mzVista[r].ent_lado; preco = mzVista[r].ent_preco; setup = mzVista[r].ent_setup;
   return true;
}
double   Ficha_PisoStop(void)         { return Snap_Piso(); }
// id_entrada novo, unico e crescente por robo (persistido).
long     Ficha_NovoId(const int r)
{
   long id = MathMax(mzAgoraMsc, mzUltId[r] + 1);
   mzUltId[r] = id;
   return id;
}
// Decisao cujo momento passou com o EA fora (antes do OnInit desta execucao) = DECISAO PERDIDA (sec. 6, spec 10.2 passo 10).
#define DECISAO_ATRASO_MAX_S 120
bool     Ficha_DecisaoPerdida(const int r, const datetime momento, const string oque)
{
   // tambem perdida a decisao que chega mais de 120 s depois do seu momento (robo RESTRITO, sem Tick): a cotacao ja' nao e'
   // a da decisao (B-19)
   if((long)mzAgora - (long)momento > DECISAO_ATRASO_MAX_S)
   {
      Log("AVISO", mzNome[r], "DECISAO PERDIDA", StringFormat("%s decidido em %s, %I64d s atras: nao entra", oque, TimeToString(momento, TIME_DATE | TIME_SECONDS),
          (long)mzAgora - (long)momento));
      return true;
   }
   if((long)momento * 1000 >= mzPartidaMsc) return false;
   Log("AVISO", mzNome[r], "DECISAO PERDIDA", StringFormat("%s decidido em %s, antes da partida (%s): nao entra", oque, TimeToString(momento, TIME_DATE | TIME_SECONDS),
       Log_HmsMsc(mzPartidaMsc)));
   return true;
}

//--- intencao: atalhos usados pelos modulos
void Int_Nada(Intencao &i, const string motivo)   { i.tipo = INT_NADA; i.id_entrada = 0; i.lado = 0; i.limite = 0.0; i.stop = 0.0; i.expira = 0; i.alvo = 0.0; i.motivo = motivo; }
void Int_Entrar(Intencao &i, const long id, const int lado, const double limite, const double stop, const datetime expira, const string motivo)
{
   i.tipo = INT_ENTRAR; i.id_entrada = id; i.lado = lado; i.limite = limite; i.stop = stop; i.expira = expira; i.alvo = 0.0; i.motivo = motivo;
}
void Int_Manter(Intencao &i, const double stop, const double alvo, const string motivo)
{
   i.tipo = INT_MANTER; i.id_entrada = 0; i.lado = 0; i.limite = 0.0; i.stop = stop; i.expira = 0; i.alvo = alvo; i.motivo = motivo;
}
void Int_Sair(Intencao &i, const string motivo)   { i.tipo = INT_SAIR; i.id_entrada = 0; i.lado = 0; i.limite = 0.0; i.stop = 0.0; i.expira = 0; i.alvo = 0.0; i.motivo = motivo; }
string Int_Nome(const int t) { switch(t) { case INT_NADA: return "NADA"; case INT_ENTRAR: return "ENTRAR"; case INT_MANTER: return "MANTER"; case INT_SAIR: return "SAIR"; } return "?"; }

//+------------------------------------------------------------------+
//| Eventos e modulos (passo 3, parte 2; sec. 7)                     |
//+------------------------------------------------------------------+
// O nivel que o modulo pede vira o "nivel da memoria" so' quando ele pede um nivel NOVO (a emergencia gravada
// fica ate' o modulo pedir outro, RV2 N-2).
void Est_NivelDoModulo(const int r)
{
   if((mzInt[r].tipo == INT_MANTER || mzInt[r].tipo == INT_ENTRAR) && mzInt[r].stop > 0.0 && !Mae_Igual(mzInt[r].stop, mzNivSIntUlt[r]))
   {
      mzNivSIntUlt[r] = mzInt[r].stop;
      mzNivS[r] = Mae_NoTick(mzInt[r].stop);
      Log("INFO", mzNome[r], "STOP", StringFormat("nivel pedido %.0f (%s)", mzNivS[r], mzInt[r].motivo));
   }
   if(mzInt[r].tipo == INT_MANTER) mzNivA[r] = mzInt[r].alvo;
}

// Entrega um evento ao modulo (so' depois do Init). Antes, o maestro ajusta a intencao guardada.
void Est_Entrega(const int r, const int ev, const long id, const double preco, const datetime hora, const string motivo)
{
   if(ev == EV_ENTRADA_EXECUTADA && mzInt[r].tipo == INT_ENTRAR)
   {
      // so' a entrada pedida herda o stop do ENTRAR; o fill de outra entrada (rearme) fica sem nivel pedido e o modulo decide (M-2)
      if(mzInt[r].id_entrada == id) Int_Manter(mzInt[r], mzInt[r].stop, 0.0, "entrada executada");
      else                          Int_Manter(mzInt[r], 0.0, 0.0, "executou uma entrada anterior");
   }
   else if((ev == EV_ENTRADA_CANCELADA || ev == EV_ENTRADA_RECUSADA || ev == EV_ENTRADA_PERDIDA) && mzInt[r].tipo == INT_ENTRAR && mzInt[r].id_entrada == id)
      Int_Nada(mzInt[r], "entrada encerrada");
   else if(ev == EV_SAIDA_EXPIRADA && mzInt[r].tipo == INT_SAIR)
      Int_Manter(mzInt[r], 0.0, 0.0, "saida expirada: a S protege");
   string nomes[6] = {"", "ENTRADA_EXECUTADA", "ENTRADA_CANCELADA", "ENTRADA_RECUSADA", "ENTRADA_PERDIDA", "SAIDA_EXPIRADA"};
   Log(ev == EV_ENTRADA_EXECUTADA ? "INFO" : "AVISO", mzNome[r], "EVENTO", StringFormat("%s id %I64d %s", nomes[ev], id, motivo));
   SEvento e;
   e.ev = ev; e.id_entrada = id; e.preco = preco; e.hora = hora; e.motivo = motivo;
   Robo_Evento(r, e, mzVista[r], mzInt[r]);
   Est_NivelDoModulo(r);
}

// Eventos das linhas E do robo (cada um uma vez; bits persistidos na linha).
void Est_EventosLinhas(const int r)
{
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      if(mzL[i].robo != r || mzL[i].papel != P_E) continue;
      if(mzL[i].desfecho == D_EXECUTADA && (mzL[i].ev & 2) == 0)
      {
         int dl = Snap_DealDaOrdem(mzL[i].ticket);
         if(dl < 0) continue;
         mzL[i].ev |= 2;
         Est_Entrega(r, EV_ENTRADA_EXECUTADA, mzL[i].id_entrada, mzDeal[dl].preco, (datetime)(mzDeal[dl].time_msc / 1000), "");
      }
      else if(mzL[i].desfecho == D_NAO_EXECUTADA && (mzL[i].ev & 3) == 0)
      {
         mzL[i].ev |= 1;
         // REJECTED no historico depois de aceita (recusa assincrona, A-2) e' recusa tambem para o modulo (B2-5)
         int ev = mzL[i].estado_hist == ORDER_STATE_REJECTED ? EV_ENTRADA_RECUSADA : EV_ENTRADA_CANCELADA;
         Est_Entrega(r, ev, mzL[i].id_entrada, 0.0, 0, mzL[i].prova);
      }
      else if(mzL[i].desfecho == D_RECUSADA && (mzL[i].ev & 1) == 0)
      {
         mzL[i].ev |= 1;
         Est_Entrega(r, EV_ENTRADA_RECUSADA, mzL[i].id_entrada, 0.0, 0, StringFormat("rc %u", mzL[i].retcode));
      }
   }
}

// Intencao inicial no Init (a mesma da CONGELADA, I5): f != 0 -> MANTER nos niveis da memoria; E viva -> ENTRAR dela.
void Est_IntencaoInicial(const int r)
{
   if(mzEst[r].f != 0) { Int_Manter(mzInt[r], mzNivS[r], mzNivA[r], "partida: niveis da memoria"); return; }
   if(mzEst[r].iE >= 0 && mzEst[r].lE >= 0)
   {
      int li = mzEst[r].lE;
      Int_Entrar(mzInt[r], mzL[li].id_entrada, Mae_LadoTipo(mzL[li].tipo), mzL[li].preco, mzNivS[r], mzL[li].expira, "partida: E viva");
      mzEntId[r] = mzL[li].id_entrada; mzEntDesde[r] = mzMono;
      return;
   }
   Int_Nada(mzInt[r], "partida");
}

// PRAZO_ENTRAR e PRAZO_SAIR (sec. 4.1), so' em ciclos confiaveis.
void Est_PrazosIntencao(const int r)
{
   if(mzInt[r].tipo == INT_ENTRAR && !Est_Consumido(r, mzInt[r].id_entrada))
   {
      if(mzEntId[r] != mzInt[r].id_entrada) { mzEntId[r] = mzInt[r].id_entrada; mzEntDesde[r] = mzMono; }
      else if(mzMono - mzEntDesde[r] >= PRAZO_ENTRAR_MS)
      {
         long id = mzInt[r].id_entrada;
         Est_Consome(r, id);
         Est_Entrega(r, EV_ENTRADA_PERDIDA, id, 0.0, 0, "ENTRAR venceu sem E enviada (PRAZO_ENTRAR)");
      }
   }
   if(mzInt[r].tipo == INT_SAIR && mzEst[r].f != 0)
   {
      if(mzSairConta[r]) mzSairAcum[r] += mzMono - mzSairUlt[r];
      mzSairUlt[r] = mzMono;
      mzSairConta[r] = true;
      if(mzSairAcum[r] >= PRAZO_SAIR_MS)
      {
         mzSairAcum[r] = 0; mzSairConta[r] = false;
         Est_Entrega(r, EV_SAIDA_EXPIRADA, 0, 0.0, 0, "SAIR nao executou em 60 s de ciclos confiaveis");
      }
   }
   else { mzSairAcum[r] = 0; mzSairConta[r] = false; }
}

void Est_Modulos(void)
{
   for(int r = 0; r < NROBOS; r++) Est_Vista(r);
   bool janela = Mae_JanelaTick(mzAgora);
   for(int r = 0; r < NROBOS; r++)
   {
      if(!mzEst[r].confiavel) { mzSairConta[r] = false; continue; }
      if(!mzInit[r] && !mzInitFalhou[r])
      {
         int ini = Robo_Init(r, mzVista[r]);
         if(ini == INIT_SUCCEEDED)
         {
            mzInit[r] = true;
            Est_IntencaoInicial(r);
            Log("INFO", mzNome[r], "PRONTO", StringFormat("modulo iniciado; ficha %+d; intencao inicial %s", mzEst[r].f, Int_Nome(mzInt[r].tipo)));
         }
         else
         {
            mzInitFalhou[r] = true;
            Log("ALERTA", mzNome[r], "PRONTO", StringFormat("Init do modulo falhou (codigo %d, veja os inputs): sem Tick e sem entrada; o maestro segue protegendo (I5)", ini));
         }
      }
      if(!mzInit[r]) continue;
      Est_EventosLinhas(r);
      // a ficha voltou a 0: MANTER/SAIR terminaram
      if(mzEst[r].f == 0 && !mzEst[r].abs_virtual && (mzInt[r].tipo == INT_MANTER || mzInt[r].tipo == INT_SAIR)) Int_Nada(mzInt[r], "ficha zerada");
      // Tick: da pre-abertura ao corte, so' com ficha ZERO ou LEGITIMA de hoje (trocada/duplicada/noite: modulo suspenso, spec 8 e 9.3)
      bool suspenso = mzEst[r].sit == SIT_TROCADA || mzEst[r].sit == SIT_DUPLICADA || mzEst[r].noite || mzProtegendo;
      if(janela && !suspenso)
      {
         Robo_Tick(r, mzVista[r], mzInt[r]);
         Est_NivelDoModulo(r);
      }
      Est_PrazosIntencao(r);
   }
}

#endif
