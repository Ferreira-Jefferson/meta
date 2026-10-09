//+------------------------------------------------------------------+
//| WinMaestro/Decide.mqh                                            |
//| Passo 4 do ciclo (sec. 3): motor de corte (sec. 5) e, antes de   |
//| C + PRAZO_CORTE, a tabela (sec. 4.2) de cada robo, na ordem fixa |
//| GB, CM, DM, RE, C1, ES, com no maximo UMA acao por robo por ciclo. |
//| Cada linha da tabela e' um bloco marcado com o identificador do  |
//| desenho (P1, P2, P3, X1, X2, X3, L1, L2, L3, L4, A1, A2, E1, Z); |
//| a intencao efetiva idem (I1..I6); o nivel da S segue a cadeia da |
//| sec. 4.3.                                                        |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_DECIDE_MQH
#define WINMAESTRO_DECIDE_MQH

#include "Envia.mqh"

int mzOrigemUlt[NROBOS];       // ultima origem logada (RAM; so' para o log)
int mzIntTipoUlt[NROBOS];

bool Dec_Espera(const int dono, const int papel) { return mzEspera[dono][papel] > mzMono; }

// Zeragem do robo = min(horario do robo, corte) (spec 9.2).
datetime Dec_Zeragem(const int r)
{
   datetime dia = Mae_Dia(mzAgora);
   datetime c = Mae_CDe(mzAgora);
   int z = Robo_MinutoZerar(r, dia);
   if(z <= 0) return c;
   datetime t = dia + z * 60;
   return t < c ? t : c;
}

//+------------------------------------------------------------------+
//| Intencao efetiva (sec. 4.1): a primeira que se aplica            |
//+------------------------------------------------------------------+
Intencao Dec_Efetiva(const int r, int &origem)
{
   Intencao x;
   int f = mzEst[r].f;
   //--- I1: agora >= C
   if(mzAgora >= Mae_CDe(mzAgora))
   {
      origem = I_1;
      if(f != 0) Int_Sair(x, "I1 corte"); else Int_Nada(x, "I1 corte");
      return x;
   }
   //--- I2: trocada ou duplicada (correcao que nunca trava, decisao 1)
   if(mzEst[r].sit == SIT_TROCADA)   { origem = I_2; Int_Sair(x, "I2"); return x; }
   if(mzEst[r].sit == SIT_DUPLICADA) { origem = I_2; Int_Sair(x, "I2"); x.alvo = (double)Mae_Sinal(f); return x; }
   //--- I3: noite, zeragem do robo, ou S recusada com a ficha aberta ha' PRAZO_S_RECUSADA (decisao m)
   bool sfalta = f != 0 && mzSFaltaDesde[r] > 0 && mzMono - mzSFaltaDesde[r] >= PRAZO_S_RECUSADA_MS;
   if(mzEst[r].noite || mzAgora >= Dec_Zeragem(r) || sfalta)
   {
      origem = I_3;
      Int_Sair(x, "I3");
      return x;
   }
   //--- I4: bloqueio e ficha 0
   if(Mae_Bloqueio() && f == 0) { origem = I_4; Int_Nada(x, "I4 bloqueio"); return x; }
   //--- I5: modulo sem Init, ou PROTEGENDO: CONGELADA
   if(!mzInit[r] || mzInitFalhou[r] || mzProtegendo)
   {
      origem = I_5;
      if(f != 0)
      {
         double alvo = mzEst[r].iA >= 0 ? mzViva[mzEst[r].iA].preco : 0.0;
         Int_Manter(x, 0.0, alvo, "I5 congelada");     // stop 0: a cadeia da sec. 4.3 (memoria, S viva...)
         return x;
      }
      if(mzEst[r].iE >= 0 && mzEst[r].lE >= 0)
      {
         int li = mzEst[r].lE;
         Int_Entrar(x, mzL[li].id_entrada, Mae_LadoTipo(mzL[li].tipo), mzL[li].preco, 0.0, mzL[li].expira, "I5 congelada");
         return x;
      }
      Int_Nada(x, "I5 congelada");
      return x;
   }
   //--- I6: a do modulo
   origem = I_6;
   x = mzInt[r];
   return x;
}

// pode_entrar (sec. 4.1): continuo, confiavel, ligado, memoria gravando, sem bloqueio, id nao consumido, ENTRAR recente.
bool Dec_PodeEntrar(const int r, const Intencao &ief, const int origem)
{
   if(origem != I_6 || ief.tipo != INT_ENTRAR || ief.id_entrada == 0) return false;
   if(!Mae_Continuo(mzAgora) || !mzEst[r].confiavel || !mzAtivo[r] || !mzMemGravando || Mae_Bloqueio()) return false;
   if(Est_Consumido(r, ief.id_entrada)) return false;
   return mzEntId[r] == ief.id_entrada && mzMono - mzEntDesde[r] < PRAZO_ENTRAR_MS;
}

//+------------------------------------------------------------------+
//| O2: autonegociacao (sec. 4.2)                                    |
//+------------------------------------------------------------------+
// A ordem (lado, preco; preco 0 = mercado) cruzaria uma limite oposta de outro robo em vivas[] ou no mapa
// como PENDENTE/VIVA (inclusive enviada neste ciclo)?
bool Dec_Cruza(const int lado, const double preco, const int tipo_outra, const double preco_outra)
{
   if(lado > 0 && tipo_outra == ORDER_TYPE_SELL_LIMIT) return preco <= 0.0 || preco_outra <= preco;
   if(lado < 0 && tipo_outra == ORDER_TYPE_BUY_LIMIT)  return preco <= 0.0 || preco_outra >= preco;
   return false;
}
bool Dec_O2(const int r, const int lado, const double preco_pedido)
{
   double preco = preco_pedido;
   if(preco <= 0.0 && mzLivroOk) preco = lado > 0 ? mzAsk : mzBid;   // mercado: o preco que executaria; sem livro, qualquer limite oposta
   int nv = ArraySize(mzViva);
   for(int k = 0; k < nv; k++)
   {
      int ro = Mae_Robo(mzViva[k].magic);
      if(ro < 0 || ro >= NROBOS || ro == r) continue;
      if(Dec_Cruza(lado, preco, mzViva[k].tipo, mzViva[k].preco)) return true;
   }
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      int ro = mzL[i].robo;
      if(ro < 0 || ro >= NROBOS || ro == r || (mzL[i].papel != P_E && mzL[i].papel != P_A)) continue;
      if(mzL[i].desfecho != D_PENDENTE && mzL[i].desfecho != D_VIVA) continue;
      if(Dec_Cruza(lado, preco, mzL[i].tipo, mzL[i].preco)) return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Nivel da S (sec. 4.3)                                            |
//+------------------------------------------------------------------+
// Preco da E (viva, pendente ou do ENTRAR) quando f = 0; 0 sem E.
double Dec_PrecoE(const int r, const Intencao &ief)
{
   if(mzEst[r].f != 0) return 0.0;
   if(mzEst[r].iE >= 0) return mzViva[mzEst[r].iE].preco;
   if(mzEst[r].pendE)   return mzEst[r].ePendPreco;
   if(ief.tipo == INT_ENTRAR) return ief.limite;
   return 0.0;
}

// Cadeia: intencao -> memoria -> S viva -> StopRegra(r, lado) -> emergencia. Um candidato so' vale se protege o lado certo
// e esta' do lado certo da referencia: compra -> nivel < min(ref, E) - piso; venda -> nivel > max(ref, E) + piso.
// Nenhum valido -> emergencia, calculada UMA vez por episodio e gravada como nivel pedido; nunca recalculada.
// Base da validade: compra -> min(ref, E); venda -> max(ref, E). false = sem preco de referencia.
bool Dec_Base(const int r, const Intencao &ief, const int lado, double &base, double &ref)
{
   base = 0.0; ref = 0.0;
   if(lado == 0) return false;
   double pe = Dec_PrecoE(r, ief);
   double reserva = mzEst[r].f != 0 ? mzEst[r].preco : pe;
   ref = Snap_Ref(lado, reserva);
   if(ref <= 0.0) return false;
   base = ref;
   if(pe > 0.0) base = lado > 0 ? MathMin(ref, pe) : MathMax(ref, pe);
   return true;
}
// Nivel valido: protege o lado certo e fica do lado certo da base, alem do piso.
bool Dec_Valido(const int lado, const double x, const double base, const double piso)
{
   if(x <= 0.0) return false;
   return lado > 0 ? x < base - piso : x > base + piso;
}

bool Dec_NivelS(const int r, const Intencao &ief, const int lado, double &nivel)
{
   nivel = 0.0;
   double base, ref;
   if(!Dec_Base(r, ief, lado, base, ref)) return false;
   double piso = Snap_Piso();
   double cand[5];
   cand[0] = (ief.tipo == INT_ENTRAR || ief.tipo == INT_MANTER) ? ief.stop : 0.0;
   cand[1] = mzNivS[r];
   cand[2] = 0.0;
   for(int k = 0; k < mzEst[r].nS; k++)      // a primeira S viva VALIDA do lado (B-3)
   {
      int v = mzEst[r].sIdx[k];
      if(Mae_LadoTipo(mzViva[v].tipo) == -lado && Dec_Valido(lado, Mae_NoTick(mzViva[v].preco), base, piso)) { cand[2] = mzViva[v].preco; break; }
   }
   cand[3] = 0.0;
   cand[4] = (mzEmergLado[r] == lado) ? mzEmerg[r] : 0.0;   // emergencia gravada para o outro lado (ficha que inverteu) nao vale
   for(int k = 0; k < 5; k++)
   {
      if(k == 3) cand[3] = Robo_StopRegra(r, lado);     // a regra do robo so' e' consultada quando as anteriores falham
      double x = Mae_NoTick(cand[k]);
      if(Dec_Valido(lado, x, base, piso)) { nivel = x; return true; }
   }
   if(mzEmerg[r] > 0.0 && mzEmergLado[r] == lado)
   {
      // Com ficha 0 (S de uma E) nao ha' o que proteger e uma S colada no preco abriria posicao ao disparar: sem S nova.
      if(mzEst[r].f == 0)
      {
         Log_Cond(StringFormat("emerg.cruzada.%d", r), true, "ALERTA", mzNome[r], "STOP",
                  StringFormat("emergencia %.0f ja' atravessada (ref %.0f) e nenhum nivel valido: sem S nova (a emergencia nao e' recalculada)", mzEmerg[r], ref));
         return false;
      }
      // B2-3 (v2.02): com a ficha aberta o robo nunca fica sem S. A emergencia gravada nao e' recalculada nem movida; a S
      // vai ao primeiro nivel valido alem da referencia (S DAY, como toda S) e a saida segue tentando (X3 com RETENTA).
      double x = lado > 0 ? MathFloor((base - piso) / TICK_WIN) * TICK_WIN : MathCeil((base + piso) / TICK_WIN) * TICK_WIN;
      if(!Dec_Valido(lado, x, base, piso)) x -= lado * TICK_WIN;
      Log_Cond(StringFormat("emerg.cruzada.%d", r), true, "ALERTA", mzNome[r], "STOP",
               StringFormat("emergencia %.0f ja' atravessada (ref %.0f) e nenhum nivel valido: S no primeiro nivel valido %.0f (a emergencia nao e' recalculada)", mzEmerg[r], ref, x));
      nivel = x;
      return true;
   }
   double d = MathMax(STOP_EMERGENCIA_PTS, piso + TICK_WIN);
   double em = lado > 0 ? MathFloor((base - d) / TICK_WIN) * TICK_WIN : MathCeil((base + d) / TICK_WIN) * TICK_WIN;
   mzEmerg[r] = em;
   mzEmergLado[r] = lado;
   mzNivS[r] = em;
   Log("ALERTA", mzNome[r], "STOP", StringFormat("nenhum nivel valido (intencao %.0f, memoria %.0f, S viva %.0f, regra %.0f; ref %.0f): S de emergencia em %.0f, gravada e nunca movida",
       cand[0], cand[1], cand[2], cand[3], ref, em));
   Mae_GravaMemoria(true);
   nivel = em;
   return true;
}

// S do robo, do lado que protege, em nivel ja' cruzado pela referencia (ela e' a saida: X3 espera, P3 nao a move).
bool Dec_SCruzadaPreco(const int r, const int lado, const double preco_s)
{
   double ref = Snap_Ref(lado, mzEst[r].f != 0 ? mzEst[r].preco : 0.0);
   if(ref <= 0.0) return false;
   return lado > 0 ? ref <= preco_s : ref >= preco_s;
}
bool Dec_SCruzada(const int r)
{
   int lado = Mae_Sinal(mzEst[r].f);
   if(lado == 0) return false;
   for(int k = 0; k < mzEst[r].nS; k++)
   {
      int v = mzEst[r].sIdx[k];
      if(Mae_LadoTipo(mzViva[v].tipo) == -lado && Dec_SCruzadaPreco(r, lado, mzViva[v].preco)) return true;
   }
   return false;
}
// Relogio da S cruzada (B2-2, v2.02): atualizado em todo ciclo com a base firme, com qualquer intencao. O prazo da X3 (M-5)
// conta desde que a S ficou cruzada, e um SAIR que chega depois nunca herda o relogio de um cruzamento anterior que ja'
// terminou (antes so' a X3 zerava o relogio, e so' quando avaliada).
void Dec_SCruzRelogio(void)
{
   for(int r = 0; r < NROBOS; r++)
   {
      if(!Dec_SCruzada(r))              mzSCruzDesde[r] = 0;
      else if(mzSCruzDesde[r] == 0)     mzSCruzDesde[r] = mzMono;
   }
}

// L3 em RESTRITO so' com prova (sec. 4.2): a irma A/X/S do episodio LEGITIMA executou, ou a E do episodio
// esta' CANCELED/EXPIRED sem nenhum deal no episodio.
bool Dec_ProvaL3(const int r)
{
   int ep = mzEp[r];
   bool eExec = false, irmaExec = false, eCanc = false, algumDeal = false;
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
   {
      if(mzL[i].robo != r || mzL[i].episodio != ep || !Mapa_TemTicketProprio(mzL[i].papel)) continue;
      bool temDeal = Snap_DealDaOrdem(mzL[i].ticket) >= 0;
      if(temDeal) algumDeal = true;
      if(mzL[i].papel == P_E)
      {
         if(mzL[i].desfecho == D_EXECUTADA && temDeal) eExec = true;
         if(mzL[i].estado_hist == ORDER_STATE_CANCELED || mzL[i].estado_hist == ORDER_STATE_EXPIRED) eCanc = true;
      }
      else if(mzL[i].desfecho == D_EXECUTADA && temDeal) irmaExec = true;
   }
   return (eExec && irmaExec) || (eCanc && !algumDeal);
}

void Dec_Acao(SAcao &a, const int tipo, const string linha, const ulong tk, const double preco, const int lado, const int vol, const string motivo)
{
   Acao_Zera(a);
   a.tipo = tipo; a.linha = linha; a.ticket = tk; a.preco = preco; a.lado = lado; a.vol = vol; a.motivo = motivo;
}

//+------------------------------------------------------------------+
//| Tabela (sec. 4.2): age a primeira linha verdadeira por conta     |
//| propria; linha cujo papel esta' em em_espera nao age e as de     |
//| baixo seguem; RESTRITO so' avalia as linhas marcadas R.          |
//+------------------------------------------------------------------+
int Dec_Tabela(const int r, const Intencao &ief, const int origem, SAcao &a)
{
   Acao_Zera(a);
   bool conf = mzEst[r].confiavel;
   bool okR  = conf || mzEst[r].inequivoco;            // P1/P3 em RESTRITO so' com lado inequivoco
   bool pode = Dec_PodeEntrar(r, ief, origem);
   int  f    = mzEst[r].f;
   int  ladoP = mzEst[r].lado_prot;
   if(ladoP == 0 && ief.tipo == INT_ENTRAR && pode) ladoP = ief.lado;
   int  iE = mzEst[r].iE, iA = mzEst[r].iA;
   ulong tkE = iE >= 0 ? mzViva[iE].ticket : 0;
   ulong tkA = iA >= 0 ? mzViva[iA].ticket : 0;

   //--- P1 (R): precisa de S; cobertura < max(|f|, 1); nenhuma S pendente/sumida; sem X ou A pendente/sumida. S FALTANDO
   bool precisa = f != 0 || iE >= 0 || mzEst[r].pendE || (ief.tipo == INT_ENTRAR && pode);
   if(precisa && ladoP != 0 && Est_Cob(r, ladoP) < MathMax(Mae_Abs(f), 1) && !mzEst[r].pendS && !mzEst[r].pendX && !mzEst[r].pendA && okR)
   {
      if(!Dec_Espera(r, P_S))
      {
         double nivel;
         bool tem = Dec_NivelS(r, ief, ladoP, nivel);
         // sem nivel colocavel (sem referencia; ou emergencia ja' atravessada com ficha 0): P1 nao age e as linhas de baixo seguem
         Log_Cond(StringFormat("p1.semnivel.%d", r), !tem, "ALERTA", mzNome[r], "STOP", "S faltando e nenhum nivel colocavel: P1 espera");
         if(tem)
         {
            Dec_Acao(a, AC_ENVIA_S, "P1", 0, nivel, -ladoP, 1, StringFormat("S faltando: cobertura %.0f de %d", Est_Cob(r, ladoP), MathMax(Mae_Abs(f), 1)));
            if(f == 0) a.id_entrada = ((iE >= 0 || mzEst[r].pendE) && mzEst[r].lE >= 0) ? mzL[mzEst[r].lE].id_entrada : ief.id_entrada;
            return a.tipo;
         }
      }
   }
   //--- P2: confiavel; f != 0 e (S do lado que aumenta |f| ou cobertura > |f|); reduz_pend falso; sem K sobre ela. S SOBRANDO COM FICHA
   if(conf && f != 0 && !mzEst[r].reduz_pend)
   {
      int lado = Mae_Sinal(f);
      ulong alvo = 0;
      for(int k = 0; k < mzEst[r].nS && alvo == 0; k++)
      {
         int v = mzEst[r].sIdx[k];
         if(Mae_LadoTipo(mzViva[v].tipo) == lado) alvo = mzViva[v].ticket;           // S do lado que aumenta |f|
      }
      if(alvo == 0 && Est_Cob(r, lado) > Mae_Abs(f))
      {
         double pior = 0.0;
         for(int k = 0; k < mzEst[r].nS; k++)
         {
            int v = mzEst[r].sIdx[k];
            if(Mae_LadoTipo(mzViva[v].tipo) != -lado) continue;
            double p = mzViva[v].preco;
            // a menos protetora; no empate, a que esta' fora do mapa (a nossa fica)
            bool menos = alvo == 0 || (lado > 0 ? p < pior : p > pior) ||
                         (Mae_Igual(p, pior) && Mapa_IdxTicket(alvo) >= 0 && Mapa_IdxTicket(mzViva[v].ticket) < 0);
            if(menos) { alvo = mzViva[v].ticket; pior = p; }
         }
      }
      if(alvo != 0 && !Mapa_KPend(alvo) && !Dec_Espera(r, P_K))
      {
         Dec_Acao(a, AC_CANCELA, "P2", alvo, 0.0, 0, 0, "S sobrando com ficha");
         return a.tipo;
      }
   }
   //--- P3 (R): S viva fora do nivel da sec. 4.3 por > 1/2 TICK_WIN; sem M pendente. A S em nivel ja' cruzado ou dentro
   //            do piso nao e' movida (ela e' a saida; mover afrouxaria um stop prestes a executar, RV2 N-2/N-3)
   if(okR && ladoP != 0)
   {
      double base, ref;
      double piso = Snap_Piso();
      bool temBase = Dec_Base(r, ief, ladoP, base, ref);
      int elegivel = 0;
      for(int k = 0; k < mzEst[r].nS && temBase; k++)
      {
         int v = mzEst[r].sIdx[k];
         if(Mae_LadoTipo(mzViva[v].tipo) != -ladoP) continue;
         // com ficha aberta a S invalida e' a saida e fica; com ficha 0 ela nao protege nada e vai ao nivel da cadeia (M-3)
         if(Mapa_MPend(mzViva[v].ticket) || Mapa_KPend(mzViva[v].ticket) || (f != 0 && !Dec_Valido(ladoP, mzViva[v].preco, base, piso))) continue;
         elegivel++;
      }
      double nivel;
      if(elegivel > 0 && Dec_NivelS(r, ief, ladoP, nivel))
      {
         for(int k = 0; k < mzEst[r].nS; k++)
         {
            int v = mzEst[r].sIdx[k];
            if(Mae_LadoTipo(mzViva[v].tipo) != -ladoP || Mae_Igual(mzViva[v].preco, nivel)) continue;
            if(Mapa_MPend(mzViva[v].ticket) || Mapa_KPend(mzViva[v].ticket) || (f != 0 && !Dec_Valido(ladoP, mzViva[v].preco, base, piso))) continue;
            if(!Dec_Espera(r, P_M))
            {
               Dec_Acao(a, AC_MOVE_S, "P3", mzViva[v].ticket, nivel, 0, 0, StringFormat("S %.0f -> %.0f", mzViva[v].preco, nivel));
               a.tipo_alvo = mzViva[v].tipo;
               return a.tipo;
            }
            break;
         }
      }
   }
   //--- X1: SAIR; A viva; sem K sobre ela -> CANCELA A (a S fica)
   if(conf && ief.tipo == INT_SAIR && iA >= 0 && !Mapa_KPend(tkA) && !Dec_Espera(r, P_K))
   {
      Dec_Acao(a, AC_CANCELA, "X1", tkA, 0.0, 0, 0, "saida: cancela o alvo antes");
      return a.tipo;
   }
   //--- X2: SAIR; E viva; sem K sobre ela -> CANCELA E (a S fica)
   if(conf && ief.tipo == INT_SAIR && iE >= 0 && !Mapa_KPend(tkE) && !Dec_Espera(r, P_K))
   {
      Dec_Acao(a, AC_CANCELA, "X2", tkE, 0.0, 0, 0, "saida: cancela a entrada");
      return a.tipo;
   }
   //--- X3: SAIR; confiavel; continuo e antes de F; f != alvo; sem A viva; sem E viva/pendente; reduz_pend falso;
   //        sem K pendente; nenhuma S em nivel ja' cruzado -> ENVIA_X(|f - alvo|), magic do robo
   int alvoF = (int)MathRound(ief.alvo);
   if(ief.tipo == INT_SAIR && conf && Mae_Continuo(mzAgora) && mzAgora < Mae_FDe(mzAgora) && f != alvoF && iA < 0 && iE < 0 &&
      !mzEst[r].pendE && !mzEst[r].reduz_pend && !mzEst[r].pendK)
   {
      if(Dec_SCruzada(r))
      {
         long ha = mzSCruzDesde[r] > 0 ? mzMono - mzSCruzDesde[r] : 0;   // relogio de Dec_SCruzRelogio, no mesmo snapshot
         Log_Cond(StringFormat("scruzada.%d", r), ha >= PROVA_MS, "ALERTA", mzNome[r], "SAIDA",
                  "S em nivel ja' cruzado ha' 30 s sem executar: a saida espera ela (sem segunda saida)");
         // prazo proprio (M-5): cruzada e viva ha' PROVA sem executar -> cancela a S (K); com o K provado a S cruzada some, P1
         // poe a S no nivel valido da cadeia (emergencia, se preciso) e X3 sai. Nunca duas saidas: X3 continua exigindo nenhum K
         // pendente e nenhuma S cruzada. PROVA, e nao mais: o SAIR do modulo expira em PRAZO_SAIR (60 s) e o prazo da X3 tem
         // de vencer antes dele.
         if(ha >= PROVA_MS && !Dec_Espera(r, P_K))
         {
            for(int k = 0; k < mzEst[r].nS; k++)
            {
               int v = mzEst[r].sIdx[k];
               if(Mae_LadoTipo(mzViva[v].tipo) != -Mae_Sinal(f) || !Dec_SCruzadaPreco(r, Mae_Sinal(f), mzViva[v].preco) || Mapa_KPend(mzViva[v].ticket)) continue;
               Dec_Acao(a, AC_CANCELA, "X3", mzViva[v].ticket, 0.0, 0, 0, "S cruzada ha' 30 s sem executar: cancelada para a saida a mercado");
               return a.tipo;
            }
         }
      }
      else
      {
         if(!Dec_Espera(r, P_X))
         {
            Dec_Acao(a, AC_ENVIA_X, "X3", 0, 0.0, Mae_Sinal(alvoF - f), Mae_Abs(f - alvoF), origem == I_2 ? "I2" : (origem == I_1 ? "I1" : (origem == I_3 ? "I3" : "MOD")));
            return a.tipo;
         }
      }
   }
   //--- L1 (R): E viva; sem K sobre ela; (intencao != ENTRAR, ou lado/preco/id diferentes, ou f != 0) -> CANCELA E
   if(iE >= 0 && !Mapa_KPend(tkE))
   {
      long eid = mzEst[r].lE >= 0 ? mzL[mzEst[r].lE].id_entrada : 0;
      bool difere = ief.tipo != INT_ENTRAR || Mae_LadoTipo(mzViva[iE].tipo) != ief.lado || !Mae_Igual(mzViva[iE].preco, ief.limite) ||
                    eid != ief.id_entrada || f != 0;
      if(difere && !Dec_Espera(r, P_K))
      {
         Dec_Acao(a, AC_CANCELA, "L1", tkE, 0.0, 0, 0, "entrada que a intencao nao pede");
         return a.tipo;
      }
   }
   //--- L2: confiavel; A viva; sem K; (nao LEGITIMA, ou intencao != MANTER, ou alvo 0) -> CANCELA A. Nunca por absorcao virtual
   if(conf && iA >= 0 && !Mapa_KPend(tkA) && !mzEst[r].abs_virtual &&
      (mzEst[r].sit != SIT_LEGITIMA || ief.tipo != INT_MANTER || ief.alvo <= 0.0) && !Dec_Espera(r, P_K))
   {
      Dec_Acao(a, AC_CANCELA, "L2", tkA, 0.0, 0, 0, "alvo que a intencao nao pede");
      return a.tipo;
   }
   //--- L3 (R): S viva sem K; f = 0 provado; sem E viva, pendente ou sumida; nada mais pendente; nao (ENTRAR e pode_entrar).
   //            S SOBRANDO SEM FICHA (OCO). Em RESTRITO so' com prova. Nunca por absorcao virtual. Com ENTRAR e pode_entrar,
   //            a S do lado que nao protege a entrada pedida (rearme para o outro lado) tambem sobra: ela abriria posicao ao disparar.
   if(f == 0 && mzEst[r].provado && iE < 0 && !mzEst[r].pendE && mzEst[r].nada_pend && !mzEst[r].abs_virtual)
   {
      bool entra = ief.tipo == INT_ENTRAR && pode;
      double baseL = 0.0, refL = 0.0;
      bool temBaseL = entra && Dec_Base(r, ief, ief.lado, baseL, refL);
      ulong tkS = 0;
      for(int k = 0; k < mzEst[r].nS && tkS == 0; k++)
      {
         int v = mzEst[r].sIdx[k];
         if(Mapa_KPend(mzViva[v].ticket)) continue;
         // a S da entrada pedida fica, se estiver valida para ela (a invalida, que P3 nao conseguiu mover, sobra: M-3)
         if(entra && Mae_LadoTipo(mzViva[v].tipo) == -ief.lado && (!temBaseL || Dec_Valido(ief.lado, mzViva[v].preco, baseL, Snap_Piso()))) continue;
         tkS = mzViva[v].ticket;
      }
      if(tkS != 0 && (conf || Dec_ProvaL3(r)) && !Dec_Espera(r, P_K))
      {
         Dec_Acao(a, AC_CANCELA, "L3", tkS, 0.0, 0, 0, entra ? "S do lado que nao protege a entrada pedida" : "S sem ficha (OCO)");
         return a.tipo;
      }
   }
   //--- L4: limite de magic do robo fora do mapa; sem K -> CANCELA (stop fora do mapa e' S: P1-P3)
   if(conf && mzEst[r].nFora > 0)
   {
      for(int k = 0; k < mzEst[r].nFora; k++)
      {
         ulong tk = mzViva[mzEst[r].foraIdx[k]].ticket;
         if(Mapa_KPend(tk)) continue;
         if(!Dec_Espera(r, P_K))
         {
            Dec_Acao(a, AC_CANCELA, "L4", tk, 0.0, 0, 0, Mapa_IdxTicket(tk) >= 0 ? "segunda E/A viva do robo (excedente)" : "limite do robo fora do mapa");
            return a.tipo;
         }
         break;
      }
   }
   //--- A1: confiavel; LEGITIMA; continuo; nao noite; MANTER com alvo; sem A viva/pendente; reduz_pend falso; sem O2 -> ENVIA_A
   if(conf && mzEst[r].sit == SIT_LEGITIMA && Mae_Continuo(mzAgora) && !mzEst[r].noite && ief.tipo == INT_MANTER && ief.alvo > 0.0 &&
      iA < 0 && !mzEst[r].pendA && !mzEst[r].reduz_pend)
   {
      bool o2 = Dec_O2(r, -Mae_Sinal(f), ief.alvo);
      Log_Cond(StringFormat("o2.a.%d", r), o2, "AVISO", mzNome[r], "AUTONEG", StringFormat("alvo %.0f cruzaria uma limite oposta de outro robo: espera", ief.alvo));
      if(!o2 && !Dec_Espera(r, P_A))
      {
         Dec_Acao(a, AC_ENVIA_A, "A1", 0, Mae_NoTick(ief.alvo), -Mae_Sinal(f), 1, ief.motivo);
         return a.tipo;
      }
   }
   //--- A2: confiavel; A viva fora do alvo; sem M pendente; sem O2 -> MOVE_A
   if(conf && iA >= 0 && ief.tipo == INT_MANTER && ief.alvo > 0.0 && !Mae_Igual(mzViva[iA].preco, ief.alvo) && !Mapa_MPend(tkA) && !Mapa_KPend(tkA) &&
      !mzEst[r].reduz_pend)
   {
      bool o2 = Dec_O2(r, Mae_LadoTipo(mzViva[iA].tipo), ief.alvo);
      Log_Cond(StringFormat("o2.a.%d", r), o2, "AVISO", mzNome[r], "AUTONEG", StringFormat("alvo %.0f cruzaria uma limite oposta de outro robo: espera", ief.alvo));
      if(!o2 && !Dec_Espera(r, P_M))
      {
         Dec_Acao(a, AC_MOVE_A, "A2", tkA, Mae_NoTick(ief.alvo), 0, 0, StringFormat("A %.0f -> %.0f", mzViva[iA].preco, ief.alvo));
         a.tipo_alvo = mzViva[iA].tipo;
         return a.tipo;
      }
   }
   //--- E1: ENTRAR; pode_entrar; ZERO; sem E viva/pendente; S do lado que protege a E VIVA; nada pendente; sem O2 -> ENVIA_E.
   //        A E so' sai com a S no nivel que a intencao pediu: stop pedido invalido (atravessado ou dentro do piso) recusa a
   //        entrada em vez de entrar com a S de emergencia, que e' um risco que o robo nao pediu.
   if(ief.tipo == INT_ENTRAR && pode && f == 0 && iE < 0 && !mzEst[r].pendE && Est_Cob(r, ief.lado) >= 1.0 && mzEst[r].nada_pend)
   {
      double baseE, refE;
      double st = Mae_NoTick(ief.stop);
      if(!Dec_Base(r, ief, ief.lado, baseE, refE)) return AC_NENHUMA;          // sem referencia: espera (o PRAZO_ENTRAR decide)
      if(!Dec_Valido(ief.lado, st, baseE, Snap_Piso()))
      {
         Dec_Acao(a, AC_RECUSA_E, "E1", 0, ief.limite, ief.lado, 1, StringFormat("stop invalido %.0f (base %.0f)", st, baseE));
         a.id_entrada = ief.id_entrada;
         return a.tipo;
      }
      bool sNoNivel = false;
      for(int k = 0; k < mzEst[r].nS; k++)
      {
         int v = mzEst[r].sIdx[k];
         if(Mae_LadoTipo(mzViva[v].tipo) == -ief.lado && Mae_Igual(mzViva[v].preco, st)) sNoNivel = true;
      }
      if(!sNoNivel) return AC_NENHUMA;                                          // P3 poe a S no nivel antes
      if(Dec_O2(r, ief.lado, ief.limite))
      {
         Dec_Acao(a, AC_RECUSA_E, "E1", 0, ief.limite, ief.lado, 1, "autoneg");
         a.id_entrada = ief.id_entrada;
         return a.tipo;
      }
      if(!Dec_Espera(r, P_E))
      {
         Dec_Acao(a, AC_ENVIA_E, "E1", 0, Mae_NoTick(ief.limite), ief.lado, 1, ief.motivo);
         a.id_entrada = ief.id_entrada;
         a.expira = ief.expira;
         return a.tipo;
      }
   }
   //--- Z
   return AC_NENHUMA;
}

//+------------------------------------------------------------------+
//| Motor de corte da conta (sec. 5.2, 5.3): so' a base, uma acao    |
//+------------------------------------------------------------------+
bool Dec_MercadoRecente(void)
{
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
      if(Mae_TipoMercado(mzL[i].tipo) && mzL[i].desfecho != D_RECUSADA && mzL[i].desfecho != D_NAO_EXECUTADA &&
         mzMono - mzL[i].enviado_mono < PROVA_MS) return true;   // executada ou sumida tambem: a liquida pode ainda nao refletir
   return false;
}
bool Dec_MercadoViva(void)
{
   int nv = ArraySize(mzViva);
   for(int k = 0; k < nv; k++) if(Mae_TipoMercado(mzViva[k].tipo)) return true;
   return false;
}

int Dec_CorteConta(SAcao &a)
{
   Acao_Zera(a);
   bool antesF = mzAgora < Mae_FDe(mzAgora);
   int nv = ArraySize(mzViva);
   //--- 5.2 passo 1: limite de magic de robo viva, sem K pendente e fora de em_espera -> CANCELA (nao espera a prova para seguir)
   bool alheia = false;
   for(int k = 0; k < nv; k++)
   {
      if(!Mae_EhRobo(mzViva[k].magic)) { if(mzViva[k].magic != MAGIC_MAESTRO) alheia = true; continue; }
      if(!Mae_TipoLimite(mzViva[k].tipo) || Mapa_KPend(mzViva[k].ticket)) continue;
      if(Dec_Espera(R_MAE, P_K)) break;
      Dec_Acao(a, AC_CANCELA, "5.2.1", mzViva[k].ticket, 0.0, 0, 0, "corte: limite de robo");
      return a.tipo;
   }
   Log_Cond("corte.alheias", alheia, "ALERTA", "MAESTRO", "CORTE", "ha' ordem pendente de magic que nao e' de robo: nao e' tocada");
   //--- 5.2 passo 2: liquida != 0, antes de F, sem ordem a mercado recente nem viva -> C_CONTA(|liquida|)
   if(mzLiq != 0)
   {
      Log_Cond("corte.depoisF", !antesF, "ALERTA", "MAESTRO", "CORTE", StringFormat("liquida %+d em F: nenhuma ordem a mercado depois de F; as S ficam", mzLiq));
      if(antesF && !Dec_MercadoRecente() && !Dec_MercadoViva() && !Dec_Espera(R_MAE, P_X))
      {
         Dec_Acao(a, AC_C_CONTA, "5.2.2", 0, 0.0, -Mae_Sinal(mzLiq), Mae_Abs(mzLiq), "C_CONTA");
         return a.tipo;
      }
      return AC_NENHUMA;
   }
   //--- 5.2 passo 3: liquida = 0 -> CANCELA as S de robo, uma por ciclo
   for(int k = 0; k < nv; k++)
   {
      if(!Mae_EhRobo(mzViva[k].magic) || !Mae_TipoStop(mzViva[k].tipo) || Mapa_KPend(mzViva[k].ticket)) continue;
      if(Dec_Espera(R_MAE, P_K)) break;
      Dec_Acao(a, AC_CANCELA, "5.2.3", mzViva[k].ticket, 0.0, 0, 0, "corte: S com liquida 0");
      return a.tipo;
   }
   return AC_NENHUMA;
}

//+------------------------------------------------------------------+
//| Passo 4: decisao e execucao. true = algum OrderSend foi feito    |
//+------------------------------------------------------------------+
bool Dec_Passo4(void)
{
   if(mzParado || !Mae_JanelaOrdens(mzAgora)) return false;   // fora da janela de ordens: espera
   if(Mae_FaseConta(mzAgora))
   {
      SAcao a;
      if(Dec_CorteConta(a) == AC_NENHUMA) return false;
      return Env_Executa(R_MAE, a);
   }
   bool enviou = false;
   for(int r = 0; r < NROBOS; r++)
   {
      int origem = 0;
      Intencao ief = Dec_Efetiva(r, origem);
      if(origem != mzOrigemUlt[r] || ief.tipo != mzIntTipoUlt[r])
      {
         mzOrigemUlt[r] = origem; mzIntTipoUlt[r] = ief.tipo;
         Log("INFO", mzNome[r], "INTENCAO", StringFormat("I%d %s (%s); ficha %+d", origem, Int_Nome(ief.tipo), ief.motivo, mzEst[r].f));
      }
      SAcao a;
      int t = Dec_Tabela(r, ief, origem, a);
      if(t == AC_NENHUMA) continue;
      if(t == AC_RECUSA_E)
      {
         Est_Consome(r, a.id_entrada);
         Log("AVISO", mzNome[r], a.motivo == "autoneg" ? "AUTONEG" : "ORDEM", StringFormat("E %s @%.0f nao enviada (%s); id %I64d consumido",
             a.lado > 0 ? "compra" : "venda", a.preco, a.motivo == "autoneg" ? "cruzaria uma limite oposta de outro robo" : a.motivo, a.id_entrada));
         Est_Entrega(r, EV_ENTRADA_RECUSADA, a.id_entrada, 0.0, 0, a.motivo);
         continue;
      }
      // o id e' consumido ANTES do envio (um reinicio entre o envio e a gravacao nao o reaproveita); se o envio nem sai
      // (memoria que nao grava), ele volta, e o PRAZO_ENTRAR entrega ENTRADA_PERDIDA ao modulo
      if(t == AC_ENVIA_E) Est_Consome(r, a.id_entrada);
      bool saiu = Env_Executa(r, a);
      if(!saiu && t == AC_ENVIA_E) Est_DesConsome(r, a.id_entrada);
      if(saiu) enviou = true;
   }
   return enviou;
}

#endif
