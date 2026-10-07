//+------------------------------------------------------------------+
//| WinMaestro/Mapa.mqh                                              |
//| O mapa ticket -> papel (sec. 1.2) e o passo 2 do ciclo (sec. 2.1)|
//| casamento e desfechos, ANTES de qualquer ficha ser calculada.    |
//|  - O papel de uma ordem e' o do mapa e nunca muda.               |
//|  - Linha nova so' no passo 5 (Envia.mqh); ticket, desfecho e     |
//|    sumida_msc mudam so' aqui e no passo 6.                       |
//|  - O deal sempre vence: NAO_EXECUTADA que ganha deal (ou FILLED) |
//|    passa a EXECUTADA.                                            |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_MAPA_MQH
#define WINMAESTRO_MAPA_MQH

#include "Snapshot.mqh"

string Mapa_DesfechoNome(const int d)
{
   switch(d)
   {
      case D_PENDENTE:      return "PENDENTE";
      case D_VIVA:          return "VIVA";
      case D_SUMIDA:        return "SUMIDA";
      case D_EXECUTADA:     return "EXECUTADA";
      case D_NAO_EXECUTADA: return "NAO_EXECUTADA";
      case D_RECUSADA:      return "RECUSADA";
   }
   return "?";
}

//+------------------------------------------------------------------+
//| Recusa (sec. 3 passo 6): TODO caminho de recusa passa por aqui   |
//|  - retcode de recusa no OrderSend (Envia.mqh);                   |
//|  - REJECTED no historico depois de aceita (A-2);                 |
//|  - prova por ausencia (B2-1, v2.02): conta como recusa, para que |
//|    a corretora que descarta ordens em silencio gere o ALERTA.    |
//| em_espera[dono][papel] ate' RETENTA; ALERTA na 5a seguida e a    |
//| cada 5 min. A contagem so' volta a 0 com prova de aceite (a      |
//| ordem executou, ou esta' VIVA ha' RETENTA), nunca pelo simples   |
//| retorno do OrderSend.                                            |
//+------------------------------------------------------------------+
void Rec_Registra(const int dono, const int papel, const string motivo)
{
   if(dono < 0 || dono >= NDONOS || papel <= 0 || papel >= NPAPEIS) return;
   mzEspera[dono][papel] = mzMono + RETENTA_MS;
   mzRecusaN[dono][papel]++;
   int nr = mzRecusaN[dono][papel];
   if(nr == 5 || (nr > 5 && mzMono - mzRecusaAlerta[dono][papel] >= 300000))
   {
      mzRecusaAlerta[dono][papel] = mzMono;
      Log("ALERTA", mzNome[dono], "ORDEM", StringFormat("papel %d recusado %d vezes seguidas (%s): retenta a cada 5 s", papel, nr, motivo));
   }
}
// So' a linha enviada depois da ultima recusa prova o aceite: uma ordem velha que segue viva (ou executa) nao zera a
// sequencia de recusas das novas do mesmo dono e papel.
void Rec_Aceita(const int dono, const int papel, const long enviado_mono)
{
   if(dono < 0 || dono >= NDONOS || papel <= 0 || papel >= NPAPEIS) return;
   if(mzRecusaN[dono][papel] > 0 && enviado_mono < mzEspera[dono][papel] - RETENTA_MS) return;
   mzRecusaN[dono][papel] = 0;
}

bool Mapa_Pendente(const int i) { return mzL[i].desfecho == D_PENDENTE || mzL[i].desfecho == D_SUMIDA; }
bool Mapa_TemTicketProprio(const int papel) { return papel == P_E || papel == P_S || papel == P_A || papel == P_X; }

// Linha (E/S/A/X) cujo ticket e' tk. -1 = fora do mapa.
int Mapa_IdxTicket(const ulong tk)
{
   if(tk == 0) return -1;
   int n = ArraySize(mzL);
   for(int i = n - 1; i >= 0; i--) if(mzL[i].ticket == tk && Mapa_TemTicketProprio(mzL[i].papel)) return i;
   return -1;
}
// O ticket ja' esta' gravado em outra linha? (sec. 2.1 passo 1; RV2 C-1)
bool Mapa_TicketUsado(const ulong tk, const int exceto)
{
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++) if(i != exceto && mzL[i].ticket == tk && Mapa_TemTicketProprio(mzL[i].papel)) return true;
   return false;
}
// K pendente sobre o ticket t (de qualquer dono, inclusive MAESTRO).
bool Mapa_KPend(const ulong t)
{
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++) if(mzL[i].papel == P_K && mzL[i].alvo_ticket == t && Mapa_Pendente(i)) return true;
   return false;
}
// M pendente sobre o ticket t.
bool Mapa_MPend(const ulong t)
{
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++) if(mzL[i].papel == P_M && mzL[i].alvo_ticket == t && Mapa_Pendente(i)) return true;
   return false;
}

void Mapa_Muda(const int i, const int d, const string prova)
{
   if(mzL[i].desfecho == d) return;
   int antes = mzL[i].desfecho;
   mzL[i].desfecho = d;
   mzL[i].prova = prova;
   if(d == D_EXECUTADA) Rec_Aceita(mzL[i].robo, mzL[i].papel, mzL[i].enviado_mono);
   string nivel = (d == D_NAO_EXECUTADA && antes != D_PENDENTE && antes != D_SUMIDA) ? "AVISO" : "INFO";
   Log(nivel, mzNome[mzL[i].robo], "DESFECHO", StringFormat("lin=%I64d %s %s ord #%I64u: %s -> %s (%s)", mzL[i].id, Mae_Papel(mzL[i].papel),
       mzL[i].coment, mzL[i].ticket, Mapa_DesfechoNome(antes), Mapa_DesfechoNome(d), prova));
}

//+------------------------------------------------------------------+
//| Casamento da linha sem ticket (sec. 2.1 passo 1)                 |
//+------------------------------------------------------------------+
// 1 = casou; 0 = nenhum candidato; 2 = mais de um candidato (segue PENDENTE, ALERTA).
// setup_max > 0: so' ordens criadas ate' esse instante (casamento tardio de linha ja' NAO_EXECUTADA, B-1).
// Preferencia (B-8): candidatos vivos ou executados primeiro; os encerrados sem execucao (CANCELED/REJECTED/EXPIRED) so'
// valem quando nao ha' nenhum dos primeiros. Mais de um candidato na classe escolhida = ambiguo.
void Mapa_ContaCand(const ulong tk, const bool preferido, ulong &pref, int &npref, ulong &outro, int &noutro)
{
   if(preferido) { if(tk != pref) { pref = tk; npref++; } }
   else          { if(tk != outro) { outro = tk; noutro++; } }
}
long mzCasaChamadas = 0;   // diagnostico (RAM): chamadas de Mapa_Casa (o teste do B2-6 confere o portao do recasamento)
int Mapa_Casa(const int i, const long setup_max = 0)
{
   mzCasaChamadas++;
   ulong tk = Snap_TicketDoRequest(mzL[i].request_id);
   if(tk != 0 && !Mapa_TicketUsado(tk, i))
   {
      mzL[i].ticket = tk;
      Log("INFO", mzNome[mzL[i].robo], "DESFECHO", StringFormat("lin=%I64d %s casada pelo request_id %u: ord #%I64u", mzL[i].id, mzL[i].coment, mzL[i].request_id, tk));
      return 1;
   }
   long magic = mzMagic[mzL[i].robo];
   bool usa_preco = !Mae_TipoMercado(mzL[i].tipo);
   long piso = mzL[i].enviado_msc - FOLGA_SETUP_MS;
   ulong pref = 0, outro = 0;
   int npref = 0, noutro = 0;
   int nv = ArraySize(mzViva);
   for(int k = 0; k < nv; k++)
   {
      if(mzViva[k].magic != magic || mzViva[k].tipo != mzL[i].tipo || MathAbs(mzViva[k].vol - mzL[i].vol) > 0.5) continue;
      if(mzViva[k].setup_msc < piso || (setup_max > 0 && mzViva[k].setup_msc > setup_max)) continue;
      if(usa_preco && !Mae_Igual(mzViva[k].preco, mzL[i].preco)) continue;
      if(Mapa_TicketUsado(mzViva[k].ticket, i)) continue;
      Mapa_ContaCand(mzViva[k].ticket, true, pref, npref, outro, noutro);
   }
   int nh = ArraySize(mzOH);
   for(int k = 0; k < nh; k++)
   {
      if(mzOH[k].magic != magic || mzOH[k].tipo != mzL[i].tipo || MathAbs(mzOH[k].vol - mzL[i].vol) > 0.5) continue;
      if(mzOH[k].setup_msc < piso || (setup_max > 0 && mzOH[k].setup_msc > setup_max)) continue;
      if(usa_preco && !Mae_Igual(mzOH[k].preco, mzL[i].preco)) continue;
      if(Mapa_TicketUsado(mzOH[k].ticket, i) || mzOH[k].ticket == pref) continue;
      Mapa_ContaCand(mzOH[k].ticket, !Snap_HistFinalNao(mzOH[k].estado), pref, npref, outro, noutro);
   }
   int nachou = npref > 0 ? npref : noutro;
   ulong achou = npref > 0 ? pref : outro;
   string chave = StringFormat("casa.%I64d", mzL[i].id);
   Log_Cond(chave, nachou > 1, "ALERTA", mzNome[mzL[i].robo], "DESFECHO",
            StringFormat("lin=%I64d %s sem ticket com %d candidatos: segue PENDENTE", mzL[i].id, mzL[i].coment, nachou));
   if(nachou != 1) return nachou > 1 ? 2 : 0;
   mzL[i].ticket = achou;
   Log("INFO", mzNome[mzL[i].robo], "DESFECHO", StringFormat("lin=%I64d %s casada por magic/tipo/volume/setup: ord #%I64u", mzL[i].id, mzL[i].coment, achou));
   return 1;
}

//+------------------------------------------------------------------+
//| Portao do recasamento (B2-6, v2.02)                              |
//+------------------------------------------------------------------+
// A linha de ticket 0 ja' NAO_EXECUTADA so' pode casar com uma ordem do magic do dono cujo ticket nao esta' em nenhuma
// linha do mapa. mzOrdemSemLinha[dono] diz se o snapshot tem alguma; sem ela o recasamento (Mapa_Casa) nao roda. Custo:
// um laco nas linhas e, so' se houver linha de ticket 0 NAO_EXECUTADA, uma ordenacao dos tickets do mapa e uma busca
// binaria por ordem (no lugar de Mapa_Casa por linha a cada ciclo).
bool mzOrdemSemLinha[NDONOS];
bool Mapa_TkNaLista(const long &tks[], const long tk)
{
   int lo = 0, hi = ArraySize(tks) - 1;
   while(lo <= hi)
   {
      int m = (lo + hi) / 2;
      if(tks[m] == tk) return true;
      if(tks[m] < tk) lo = m + 1; else hi = m - 1;
   }
   return false;
}
void Mapa_PortaoRecasa(void)
{
   for(int d = 0; d < NDONOS; d++) mzOrdemSemLinha[d] = false;
   int nl = ArraySize(mzL);
   bool precisa = false;
   for(int i = 0; i < nl && !precisa; i++)
      if(mzL[i].ticket == 0 && mzL[i].desfecho == D_NAO_EXECUTADA && Mapa_TemTicketProprio(mzL[i].papel)) precisa = true;
   if(!precisa) return;
   long tks[];
   ArrayResize(tks, nl);
   int k = 0;
   for(int i = 0; i < nl; i++) if(mzL[i].ticket != 0 && Mapa_TemTicketProprio(mzL[i].papel)) tks[k++] = (long)mzL[i].ticket;
   ArrayResize(tks, k);
   if(k > 1) ArraySort(tks);
   int nv = ArraySize(mzViva);
   for(int j = 0; j < nv; j++)
   {
      int d = Mae_Robo(mzViva[j].magic);
      if(d >= 0 && !Mapa_TkNaLista(tks, (long)mzViva[j].ticket)) mzOrdemSemLinha[d] = true;
   }
   int nh = ArraySize(mzOH);
   for(int j = 0; j < nh; j++)
   {
      int d = Mae_Robo(mzOH[j].magic);
      if(d >= 0 && !Mapa_TkNaLista(tks, (long)mzOH[j].ticket)) mzOrdemSemLinha[d] = true;
   }
}

//+------------------------------------------------------------------+
//| Desfecho de E/S/A/X com ticket (sec. 2.1 passo 2)                |
//+------------------------------------------------------------------+
void Mapa_DesfechoOrdem(const int i)
{
   int d0 = mzL[i].desfecho;
   if(d0 == D_EXECUTADA || d0 == D_RECUSADA) return;
   if(mzL[i].ticket == 0)
   {
      if(d0 == D_NAO_EXECUTADA)
      {
         // o deal sempre vence tambem para a linha sem ticket (B-1): a ordem que aparecer depois, criada ate' PROVA depois do
         // envio (antes de qualquer reenvio dela), e' casada; com deal, a linha vira EXECUTADA com o papel dela.
         // So' roda com alguma ordem do magic do dono fora do mapa (portao do B2-6).
         if(mzL[i].enviado_msc < (long)Mae_Dia(mzAgora) * 1000 || !mzOrdemSemLinha[mzL[i].robo] || Mapa_Casa(i, mzL[i].enviado_msc + PROVA_MS) != 1) return;
      }
      else
      {
      int c = Mapa_Casa(i);
      if(c == 0 && Snap_AusenciaProvada(mzL[i].enviado_mono))
      {
         Mapa_Muda(i, D_NAO_EXECUTADA, "sem ticket, ausente das vivas e do historico ha' mais de 30 s");
         Rec_Registra(mzL[i].robo, mzL[i].papel, "ausente");
         return;
      }
      if(c != 1) return;
      }
   }
   ulong tk = mzL[i].ticket;
   int dl = Snap_DealDaOrdem(tk);
   int hi = Snap_HistIdx(tk);
   if(hi >= 0) mzL[i].estado_hist = mzOH[hi].estado;
   if(dl >= 0) { Mapa_Muda(i, D_EXECUTADA, StringFormat("deal #%I64u", mzDeal[dl].ticket)); return; }
   if(hi >= 0 && Snap_HistFinalExec(mzOH[hi].estado)) { Mapa_Muda(i, D_EXECUTADA, "historico FILLED/PARTIAL, deal a caminho"); return; }
   if(d0 == D_NAO_EXECUTADA) return;                        // so' o deal (ou FILLED) a tira dai'
   if(hi >= 0 && Snap_HistFinalNao(mzOH[hi].estado))
   {
      Mapa_Muda(i, D_NAO_EXECUTADA, "historico " + EnumToString((ENUM_ORDER_STATE)mzOH[hi].estado));
      // recusa que chega pelo historico (aceita no envio, REJECTED depois): a mesma recusa do retcode (A-2)
      if(mzOH[hi].estado == ORDER_STATE_REJECTED) Rec_Registra(mzL[i].robo, mzL[i].papel, "REJECTED no historico");
      return;
   }
   if(Snap_VivaIdx(tk) >= 0)
   {
      Mapa_Muda(i, D_VIVA, "listada nas vivas");
      // aceite provado so' depois de RETENTA viva: a recusa assincrona pode listar a ordem por um instante antes do REJECTED
      if(mzMono - mzL[i].enviado_mono >= RETENTA_MS) Rec_Aceita(mzL[i].robo, mzL[i].papel, mzL[i].enviado_mono);
      return;
   }
   // ausente das vivas e sem estado final no historico
   if(d0 == D_VIVA)
   {
      mzL[i].sumida_msc = mzAgoraMsc;
      mzL[i].sumida_mono = mzMono;
      Mapa_Muda(i, D_SUMIDA, "saiu das vivas sem estado final no historico");
      return;
   }
   long desde = MathMax(mzL[i].enviado_mono, mzL[i].sumida_mono);
   if(Snap_AusenciaProvada(desde))
   {
      Mapa_Muda(i, D_NAO_EXECUTADA, "ausente das vivas e do historico ha' mais de 30 s (decisao C)");
      Rec_Registra(mzL[i].robo, mzL[i].papel, "ausente");
   }
}

//+------------------------------------------------------------------+
//| K: cancelamento (sec. 2.1)                                       |
//+------------------------------------------------------------------+
void Mapa_DesfechoK(const int i)
{
   if(mzL[i].desfecho != D_PENDENTE) return;
   ulong t = mzL[i].alvo_ticket;
   int dl = Snap_DealDaOrdem(t);
   int hi = Snap_HistIdx(t);
   if(dl >= 0 || (hi >= 0 && Snap_HistFinalExec(mzOH[hi].estado))) { Mapa_Muda(i, D_NAO_EXECUTADA, "o alvo executou antes"); return; }
   if(hi >= 0 && Snap_HistFinalNao(mzOH[hi].estado))                { Mapa_Muda(i, D_EXECUTADA, "cancelamento confirmado no historico"); return; }
   if(Snap_VivaIdx(t) >= 0)
   {
      if(mzMono - mzL[i].enviado_mono >= PROVA_MS) Mapa_Muda(i, D_NAO_EXECUTADA, "alvo ainda viva depois de 30 s: K nao executado");
      return;
   }
   if(Snap_AusenciaProvada(mzL[i].enviado_mono)) Mapa_Muda(i, D_NAO_EXECUTADA, "alvo ausente das vivas e do historico ha' mais de 30 s");
}

//+------------------------------------------------------------------+
//| M: modificacao (sec. 2.1; P4)                                    |
//+------------------------------------------------------------------+
void Mapa_DesfechoM(const int i)
{
   if(mzL[i].desfecho != D_PENDENTE) return;
   ulong t = mzL[i].alvo_ticket;
   int v = Snap_VivaIdx(t);
   if(v >= 0)
   {
      if(Mae_Igual(mzViva[v].preco, mzL[i].preco)) { Mapa_Muda(i, D_EXECUTADA, "ordem no preco novo"); return; }
      if(mzMono - mzL[i].enviado_mono >= PROVA_MS) Mapa_Muda(i, D_NAO_EXECUTADA, "preco antigo depois de 30 s: M nao executado");
      return;
   }
   // P4: o ticket sumiu e outra ordem do mesmo magic, tipo e volume, no preco novo, com setup posterior ao M, apareceu
   int alvo = Mapa_IdxTicket(t);
   int nv = ArraySize(mzViva);
   long magic = mzMagic[mzL[i].robo];
   for(int k = 0; k < nv; k++)
   {
      if(mzViva[k].magic != magic || mzViva[k].tipo != mzL[i].tipo || MathAbs(mzViva[k].vol - mzL[i].vol) > 0.5) continue;
      if(!Mae_Igual(mzViva[k].preco, mzL[i].preco) || mzViva[k].setup_msc < mzL[i].enviado_msc - FOLGA_SETUP_MS) continue;
      if(Mapa_TicketUsado(mzViva[k].ticket, -1)) continue;
      if(alvo >= 0)
      {
         Log("AVISO", mzNome[mzL[i].robo], "DESFECHO", StringFormat("lin=%I64d: OrderModify trocou o ticket #%I64u -> #%I64u (P4); a linha %I64d passa ao ticket novo",
             mzL[i].id, t, mzViva[k].ticket, mzL[alvo].id));
         mzL[alvo].ticket = mzViva[k].ticket;
         mzL[alvo].desfecho = D_VIVA;
      }
      mzL[i].alvo_ticket = mzViva[k].ticket;
      Mapa_Muda(i, D_EXECUTADA, "P4: ordem nova no preco novo");
      return;
   }
   int dl = Snap_DealDaOrdem(t);
   int hi = Snap_HistIdx(t);
   if(dl >= 0 || (hi >= 0 && (Snap_HistFinalExec(mzOH[hi].estado) || Snap_HistFinalNao(mzOH[hi].estado))))
      { Mapa_Muda(i, D_NAO_EXECUTADA, "alvo do M nao esta' mais viva"); return; }
   if(Snap_AusenciaProvada(mzL[i].enviado_mono)) Mapa_Muda(i, D_NAO_EXECUTADA, "alvo do M ausente ha' mais de 30 s");
}

//+------------------------------------------------------------------+
//| Passo 2 (sec. 2.1): M primeiro (P4 troca o ticket da S/A), depois|
//| K, depois E/S/A/X na ordem das linhas                           |
//+------------------------------------------------------------------+
void Mapa_Passo2(void)
{
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++) if(mzL[i].papel == P_M) Mapa_DesfechoM(i);
   for(int i = 0; i < n; i++) if(mzL[i].papel == P_K) Mapa_DesfechoK(i);
   Mapa_PortaoRecasa();
   for(int i = 0; i < n; i++) if(Mapa_TemTicketProprio(mzL[i].papel)) Mapa_DesfechoOrdem(i);
}

//+------------------------------------------------------------------+
//| Retencao (sec. 1.2): linhas do dia e de todo episodio aberto     |
//+------------------------------------------------------------------+
void Mapa_Retencao(const datetime hoje)
{
   int n = ArraySize(mzL), w = 0;
   for(int i = 0; i < n; i++)
   {
      bool fica = (datetime)(mzL[i].enviado_msc / 1000) >= hoje;
      int r = mzL[i].robo;
      if(!fica && r >= 0 && r < NROBOS && mzEpAberto[r] && mzL[i].episodio == mzEp[r]) fica = true;
      if(!fica) continue;
      if(w != i) mzL[w] = mzL[i];
      w++;
   }
   if(w != n) Log("INFO", "MAESTRO", "MEMORIA", StringFormat("dia novo: %d linhas do mapa de dias anteriores sem episodio aberto descartadas", n - w));
   ArrayResize(mzL, w);
}

#endif
