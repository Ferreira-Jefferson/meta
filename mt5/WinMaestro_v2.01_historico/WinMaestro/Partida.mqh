//+------------------------------------------------------------------+
//| WinMaestro/Partida.mqh                                           |
//| Trava (sec. 1.6), memoria em disco (sec. 1.2, spec 10.1),        |
//| partida (sec. 6: ambiente, PRONTO, mapa refeito do log), botao e |
//| painel, e o ciclo (sec. 3): leitura -> casamento -> derivacao -> |
//| decisao -> registro -> envio, ate' RODADAS por evento.           |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_PARTIDA_MQH
#define WINMAESTRO_PARTIDA_MQH

#include "Decide.mqh"

void Robo_Exporta(const int r);   // gancho: modulo iniciado -> Exporta(); senao copia as chaves carregadas

//--- trava
string   mzTravaPrefixo = "WinMaestro";
bool     mzSemTrava = false;          // Testador (P16)
string   mzTravaNome = "";
string   mzHbNome = "";
double   mzToken = 0.0;
bool     mzTravaMinha = false;
double   mzHbAlheio = 0.0;            // ultimo heartbeat alheio visto
long     mzHbAvancaDesde = 0;         // primeira mudanca vista do heartbeat alheio (s, relogio da trava)
long     mzHbUltMuda = 0;             // ultima mudanca vista
long     mzTravaTentUlt = 0;
bool     mzRecarregar = false;
long     mzTravaRelogio = 0;          // testes: relogio da trava (0 = TimeLocal)
bool     mzTravaSoMarca = false;      // testes: no lugar do ExpertRemove, so' marca mzTravaRemoveu
bool     mzTravaRemoveu = false;
//--- memoria carregada (para os modulos: Car_*)
string   mzCarK[];
string   mzCarV[];
bool     mzCarMesmoDia = false;
//--- painel/botao
bool     mzTela = true;               // painel e botao (falso no EA de teste)

long Trava_Agora(void) { return mzTravaRelogio > 0 ? mzTravaRelogio : (long)TimeLocal(); }

//+------------------------------------------------------------------+
//| Memoria: exporta / importa                                       |
//+------------------------------------------------------------------+
string Mae_Limpo(const string s) { string t = s; StringReplace(t, ";", ","); StringReplace(t, "\n", " "); StringReplace(t, "\r", " "); return t; }

string Mae_LinhaTexto(const int i)
{
   return StringFormat("%I64d;%d;%d;%d;%I64d;%d;%s;%d;%.1f;%.0f;%I64u;%I64d;%I64u;%u;%u;%d;%I64d;%I64d;%s;%d;%d;%s",
                       mzL[i].id, mzL[i].robo, mzL[i].papel, mzL[i].episodio, mzL[i].id_entrada, mzL[i].seq, Mae_Limpo(mzL[i].coment),
                       mzL[i].tipo, mzL[i].preco, mzL[i].vol, mzL[i].alvo_ticket, mzL[i].enviado_msc, mzL[i].ticket, mzL[i].request_id,
                       mzL[i].retcode, mzL[i].desfecho, mzL[i].sumida_msc, (long)mzL[i].expira, Mae_Limpo(mzL[i].motivo), mzL[i].ev,
                       mzL[i].estado_hist, Mae_Limpo(mzL[i].prova));
}

// Instante monotonico de um instante do servidor gravado (memoria/log): o monotonico nao sobrevive a reinicio do PC,
// entao a idade e' refeita pela diferenca no relogio do servidor, uma vez, na carga.
long Mae_MonoDe(const long msc_srv)
{
   if(msc_srv <= 0) return 0;
   long mono = mzCorr.Mono();
   long idade = mzCorr.AgoraMsc() - msc_srv;
   if(idade < 0) idade = 0;
   return mono - idade;
}

bool Mae_LinhaDeTexto(const string s, SLinha &l)
{
   string c[];
   if(StringSplit(s, ';', c) < 22) return false;
   l.id = StringToInteger(c[0]); l.robo = (int)StringToInteger(c[1]); l.papel = (int)StringToInteger(c[2]);
   l.episodio = (int)StringToInteger(c[3]); l.id_entrada = StringToInteger(c[4]); l.seq = (int)StringToInteger(c[5]); l.coment = c[6];
   l.tipo = (int)StringToInteger(c[7]); l.preco = StringToDouble(c[8]); l.vol = StringToDouble(c[9]);
   l.alvo_ticket = (ulong)StringToInteger(c[10]); l.enviado_msc = StringToInteger(c[11]); l.ticket = (ulong)StringToInteger(c[12]);
   l.request_id = (uint)StringToInteger(c[13]); l.retcode = (uint)StringToInteger(c[14]); l.desfecho = (int)StringToInteger(c[15]);
   l.sumida_msc = StringToInteger(c[16]); l.expira = (datetime)StringToInteger(c[17]); l.motivo = c[18]; l.ev = (int)StringToInteger(c[19]);
   l.estado_hist = (int)StringToInteger(c[20]); l.prova = c[21];
   l.enviado_mono = Mae_MonoDe(l.enviado_msc); l.sumida_mono = Mae_MonoDe(l.sumida_msc);
   return l.robo >= 0 && l.robo < NDONOS && l.papel >= P_E && l.papel <= P_M;
}

string Mae_ListaU(const ulong &a[]) { string s = ""; int n = ArraySize(a); for(int i = 0; i < n; i++) s += (i > 0 ? "," : "") + StringFormat("%I64u", a[i]); return s; }
void   Mae_ListaLe(const string s, ulong &a[])
{
   ArrayResize(a, 0);
   if(s == "") return;
   string c[];
   int n = StringSplit(s, ',', c);
   for(int i = 0; i < n; i++) { ulong v = (ulong)StringToInteger(c[i]); if(v != 0) { int k = ArraySize(a); ArrayResize(a, k + 1); a[k] = v; } }
}

void Mae_Exporta(void)
{
   Mem_Limpa();
   Mem_Set("versao", WM_VERSAO);
   Mem_Set("servidor", mzCorr.ContaS(ACCOUNT_SERVER));
   Mem_SetI("conta", mzCorr.ContaI(ACCOUNT_LOGIN));
   Mem_Set("simbolo", _Symbol);
   Mem_SetI("dia", (long)mzMemDia);
   Mem_SetI("prox_linha", mzProxLinha);
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++) Mem_Set(StringFormat("L.%I64d", mzL[i].id), Mae_LinhaTexto(i));
   for(int r = 0; r < NROBOS; r++)
   {
      string p = StringFormat("R%d.", r);
      Mem_SetD(p + "nivS", mzNivS[r]); Mem_SetD(p + "nivSInt", mzNivSIntUlt[r]); Mem_SetD(p + "nivA", mzNivA[r]); Mem_SetD(p + "emerg", mzEmerg[r]); Mem_SetI(p + "emergLado", mzEmergLado[r]);
      Mem_SetI(p + "ultId", mzUltId[r]); Mem_SetI(p + "ultCorr", mzUltCorrMsc[r]); Mem_SetI(p + "ep", mzEp[r]); Mem_SetB(p + "epAb", mzEpAberto[r]);
   }
   for(int d = 0; d <= NROBOS; d++) Mem_SetI(StringFormat("seq%d", d), mzSeq[d]);
   Mem_SetI("seqDia", (long)mzSeqDia);
   string cons = "";
   int nc = ArraySize(mzConsId);
   for(int i = 0; i < nc; i++) cons += (i > 0 ? "," : "") + StringFormat("%I64d:%I64d", mzConsR[i], mzConsId[i]);
   Mem_Set("cons", cons);
   Mem_SetB("bloq", mzBloqBotao);
   Mem_Set("bloqMotivo", mzBloqMotivo);
   Mem_Set("reconh", Mae_ListaU(mzReconh));
   Mem_SetI("extDesc", mzExtDesc);
   Mem_Set("absVistas", Mae_ListaU(mzAbsVistas));
   Mem_Set("dealsLog", Mae_ListaU(mzDealsLog));
   Mem_SetI("janRecuo", (long)mzJanRecuo);
   Mem_SetI("janRecuoDia", (long)mzJanRecuoDia);
   for(int r = 0; r < NROBOS; r++) Robo_Exporta(r);
}

void Mae_GravaMemoria(const bool forcar)
{
   if(!mzMemCarregada) return;               // nada e' gravado antes de ler (senao apagaria a memoria)
   if(!mzSemTrava && !mzTravaMinha) return;  // sem a trava a memoria e' da outra instancia
   Mae_Exporta();
   bool ok = Mem_Grava(forcar);
   mzMemGravando = ok;
   mzMemUltGrava = mzMono;
   Log_Cond("memoria", !ok, "ALERTA", "MAESTRO", "MEMORIA", "falha ao gravar estado.txt: E e A barradas ate' gravar");
}

//--- leitura das chaves dos modulos (Importa)
int    Car_Idx(const string k)                    { int n = ArraySize(mzCarK); for(int i = 0; i < n; i++) if(mzCarK[i] == k) return i; return -1; }
bool   Car_Tem(const string k)                    { return mzCarMesmoDia && Car_Idx(k) >= 0; }
long   Car_GetI(const string k, const long def)   { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : StringToInteger(mzCarV[i]); }
double Car_GetD(const string k, const double def) { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : StringToDouble(mzCarV[i]); }
bool   Car_GetB(const string k, const bool def)   { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : (mzCarV[i] == "1"); }
// Modulo ainda sem Init: preserva as chaves dele como foram lidas.
void   Car_CopiaPrefixo(const string prefixo)
{
   int n = ArraySize(mzCarK);
   for(int i = 0; i < n; i++) if(StringFind(mzCarK[i], prefixo) == 0) Mem_Set(mzCarK[i], mzCarV[i]);
}

// Mapa refeito das linhas ORDEM do log do dia (memoria perdida, sec. 6). Sem log: nada (papel pelo tipo, decisao 5).
string Mae_Token(const string s, const string chave)
{
   int p = StringFind(s, " " + chave);
   if(p < 0) return "";
   int ini = p + 1 + StringLen(chave);
   int fim = StringFind(s, " ", ini);
   if(fim < 0) fim = StringLen(s);
   return StringSubstr(s, ini, fim - ini);
}
int Mae_MapaDoLog(void)
{
   string linhas[];
   int n = Log_LeDia(mzCorr.Agora(), linhas);
   int lidas = 0;
   for(int k = 0; k < n; k++)
   {
      int p = StringFind(linhas[k], "| ORDEM | ");
      if(p < 0) continue;
      string d = StringSubstr(linhas[k], p + 10);
      if(StringFind(d, "envio lin=") == 0)
      {
         SLinha l;
         l.id = StringToInteger(Mae_Token(d, "lin="));
         l.robo = Mae_RoboDe(Mae_Token(d, "r="));
         l.papel = Mae_PapelDe(Mae_Token(d, "p="));
         if(l.id <= 0 || l.robo < 0 || l.papel == 0) continue;
         l.episodio = (int)StringToInteger(Mae_Token(d, "ep="));
         l.id_entrada = StringToInteger(Mae_Token(d, "ide="));
         l.seq = (int)StringToInteger(Mae_Token(d, "seq="));
         l.tipo = (int)StringToInteger(Mae_Token(d, "tipo="));
         l.preco = StringToDouble(Mae_Token(d, "preco="));
         l.vol = StringToDouble(Mae_Token(d, "vol="));
         l.alvo_ticket = (ulong)StringToInteger(Mae_Token(d, "alvo="));
         l.enviado_msc = StringToInteger(Mae_Token(d, "msc="));
         l.expira = (datetime)StringToInteger(Mae_Token(d, "exp="));
         l.motivo = Mae_Token(d, "mot=");
         l.coment = Mae_Token(d, "com=");
         l.ticket = 0; l.request_id = 0; l.retcode = 0; l.desfecho = D_PENDENTE; l.sumida_msc = 0; l.prova = "refeita do log"; l.ev = 0; l.estado_hist = -1;
         l.enviado_mono = Mae_MonoDe(l.enviado_msc); l.sumida_mono = 0;
         int i = ArraySize(mzL);
         ArrayResize(mzL, i + 1);
         mzL[i] = l;
         lidas++;
         if(l.id >= mzProxLinha) mzProxLinha = l.id + 1;
         if(l.robo < NROBOS && l.episodio > mzEp[l.robo]) { mzEp[l.robo] = l.episodio; mzEpAberto[l.robo] = true; }
         if(l.seq > mzSeq[l.robo]) mzSeq[l.robo] = l.seq;
      }
      else if(StringFind(d, "retorno lin=") == 0)
      {
         long id = StringToInteger(Mae_Token(d, "lin="));
         for(int i = ArraySize(mzL) - 1; i >= 0; i--)
         {
            if(mzL[i].id != id) continue;
            if(mzL[i].papel != P_K && mzL[i].papel != P_M) mzL[i].ticket = (ulong)StringToInteger(Mae_Token(d, "tk="));
            mzL[i].request_id = (uint)StringToInteger(Mae_Token(d, "req="));
            string rc = Mae_Token(d, "rc=");
            int barra = StringFind(rc, "/");
            if(barra > 0) rc = StringSubstr(rc, 0, barra);
            mzL[i].retcode = (uint)StringToInteger(rc);
            if(StringFind(d, "RECUSADA") >= 0) { mzL[i].desfecho = D_RECUSADA; mzL[i].ev = 1; }
            break;
         }
      }
   }
   mzSeqDia = Mae_Dia(mzCorr.Agora());
   return lidas;
}

// Carrega a memoria do disco (OnInit depois da trava, e na retomada da trava).
void Mae_CarregaMemoria(void)
{
   ArrayResize(mzL, 0);
   mzProxLinha = 1;
   int ok = Mem_Carrega();
   bool valida = ok != 2;
   string porque = ok == 2 ? "estado.txt e estado.bak ausentes ou corrompidos" : "";
   if(valida && Mem_Get("versao", "") != WM_VERSAO) { valida = false; porque = "memoria de outra versao (" + Mem_Get("versao", "?") + ")"; }
   if(valida && (Mem_GetI("conta", -1) != mzCorr.ContaI(ACCOUNT_LOGIN) || Mem_Get("servidor", "") != mzCorr.ContaS(ACCOUNT_SERVER) || Mem_Get("simbolo", "") != _Symbol))
      { valida = false; porque = "memoria de outra conta, servidor ou simbolo"; }
   // copia para os modulos (Car_*)
   int n = ArraySize(mzMemK);
   ArrayResize(mzCarK, valida ? n : 0); ArrayResize(mzCarV, valida ? n : 0);
   if(valida) for(int i = 0; i < n; i++) { mzCarK[i] = mzMemK[i]; mzCarV[i] = mzMemV[i]; }
   mzMemPerdida = !valida;
   if(!valida)
   {
      mzCarMesmoDia = false;
      int lidas = Mae_MapaDoLog();
      Log("ALERTA", "MAESTRO", "MEMORIA", StringFormat("memoria perdida (%s): %d linhas do mapa refeitas do log do dia; sem log, papel pelo tipo (decisao 5)", porque, lidas));
      mzMemCarregada = true;
      return;
   }
   mzMemDia = (datetime)Mem_GetI("dia", 0);
   mzCarMesmoDia = mzMemDia == Mae_Dia(mzCorr.Agora());
   mzProxLinha = Mem_GetI("prox_linha", 1);
   for(int i = 0; i < n; i++)
   {
      if(StringFind(mzMemK[i], "L.") != 0) continue;
      SLinha l;
      if(!Mae_LinhaDeTexto(mzMemV[i], l)) continue;
      int k = ArraySize(mzL);
      ArrayResize(mzL, k + 1);
      mzL[k] = l;
      if(l.id >= mzProxLinha) mzProxLinha = l.id + 1;
   }
   for(int r = 0; r < NROBOS; r++)
   {
      string p = StringFormat("R%d.", r);
      mzNivS[r] = Mem_GetD(p + "nivS", 0.0); mzNivSIntUlt[r] = Mem_GetD(p + "nivSInt", 0.0); mzNivA[r] = Mem_GetD(p + "nivA", 0.0);
      mzEmerg[r] = Mem_GetD(p + "emerg", 0.0); mzEmergLado[r] = (int)Mem_GetI(p + "emergLado", 0); mzUltId[r] = Mem_GetI(p + "ultId", 0); mzUltCorrMsc[r] = Mem_GetI(p + "ultCorr", 0);
      mzEp[r] = (int)Mem_GetI(p + "ep", 0); mzEpAberto[r] = Mem_GetB(p + "epAb", false);
   }
   for(int d = 0; d <= NROBOS; d++) mzSeq[d] = (int)Mem_GetI(StringFormat("seq%d", d), 0);
   mzSeqDia = (datetime)Mem_GetI("seqDia", 0);
   ArrayResize(mzConsR, 0); ArrayResize(mzConsId, 0);
   string cs[];
   int ncs = StringSplit(Mem_Get("cons", ""), ',', cs);
   for(int i = 0; i < ncs; i++)
   {
      int dp = StringFind(cs[i], ":");
      if(dp <= 0) continue;
      int k = ArraySize(mzConsId);
      ArrayResize(mzConsR, k + 1); ArrayResize(mzConsId, k + 1);
      mzConsR[k] = StringToInteger(StringSubstr(cs[i], 0, dp));
      mzConsId[k] = StringToInteger(StringSubstr(cs[i], dp + 1));
   }
   mzBloqBotao = Mem_GetB("bloq", false);
   mzBloqMotivo = Mem_Get("bloqMotivo", "");
   Mae_ListaLe(Mem_Get("reconh", ""), mzReconh);
   mzExtDesc = (int)Mem_GetI("extDesc", 0);
   Mae_ListaLe(Mem_Get("absVistas", ""), mzAbsVistas);
   Mae_ListaLe(Mem_Get("dealsLog", ""), mzDealsLog);
   mzJanRecuo = (datetime)Mem_GetI("janRecuo", 0);
   mzJanRecuoDia = (datetime)Mem_GetI("janRecuoDia", 0);
   mzMemCarregada = true;
   Log("INFO", "MAESTRO", "MEMORIA", StringFormat("memoria carregada (%s): %d linhas no mapa; bloqueio %s; externa desconhecida %+d",
       ok == 0 ? "estado.txt" : "estado.bak", ArraySize(mzL), mzBloqBotao ? "SIM (" + mzBloqMotivo + ")" : "nao", mzExtDesc));
}

// Dia novo: retencao do mapa (sec. 1.2), seq, ids consumidos e recuo do dia.
void Mae_DiaNovo(void)
{
   datetime hoje = Mae_Dia(mzAgora);
   if(mzMemDia != 0) Mapa_Retencao(hoje);
   if(mzMemDia != 0 && mzExtDesc != 0)
   {
      Log("AVISO", "MAESTRO", "EXTERNA", StringFormat("dia novo: externa de origem desconhecida %+d deixa de valer (a janela nova recomeca)", mzExtDesc));
      mzExtDesc = 0;
   }
   mzExtZeroDesde = 0;
   ArrayResize(mzConsR, 0); ArrayResize(mzConsId, 0);
   mzJanRecuo = 0; mzJanRecuoDia = 0; mzRecuoN = 0;
   mzMemDia = hoje;
   mzProntoLogado = false;
}

//+------------------------------------------------------------------+
//| Trava (sec. 1.6, mudanca E, decisao do dono sobre o ChartID)      |
//+------------------------------------------------------------------+
void Trava_Nomes(void)
{
   string conta = StringFormat("%I64d", mzCorr.ContaI(ACCOUNT_LOGIN));
   mzTravaNome = mzTravaPrefixo + ".lock." + conta + "." + _Symbol;
   mzHbNome    = mzTravaPrefixo + ".hb." + conta + "." + _Symbol;
   long cid = ChartID();
   uint tk = (uint)(cid ^ (cid >> 32));
   if(tk == 0) tk = 1;
   mzToken = (double)tk;                     // uint cabe exato num double (armadilha do double em GlobalVariable)
}

void Trava_Hb(void)
{
   if(mzSemTrava || !mzTravaMinha || mzHbNome == "") return;
   GlobalVariableSet(mzHbNome, (double)Trava_Agora());
}

// Tenta tomar a trava. true = minha.
bool Trava_Tenta(void)
{
   if(mzSemTrava) { mzTravaMinha = true; return true; }
   if(!GlobalVariableCheck(mzTravaNome)) GlobalVariableSet(mzTravaNome, 0.0);
   double v = GlobalVariableGet(mzTravaNome);
   bool ok = false;
   if(v == mzToken) ok = true;                                               // mesmo grafico (reinicio por input/timeframe; ChartID que sobrevive)
   else if(v == 0.0) ok = GlobalVariableSetOnCondition(mzTravaNome, mzToken, 0.0);
   else
   {
      double hb = GlobalVariableCheck(mzHbNome) ? GlobalVariableGet(mzHbNome) : 0.0;
      long agora = Trava_Agora();
      if(agora - (long)hb >= HB_TOMADA_S)
      {
         ok = GlobalVariableSetOnCondition(mzTravaNome, mzToken, v);        // heartbeat alheio parado: toma (crash; ChartID que mudou)
         if(ok) Log("AVISO", "MAESTRO", "TRAVA", StringFormat("trava de outro token (%.0f) com heartbeat parado ha' %I64d s: tomada", v, agora - (long)hb));
      }
      else
      {
         // segunda instancia viva = heartbeat alheio visto AVANCANDO durante mais de HB_TOMADA (primeira e ultima mudanca vistas)
         if(mzHbAlheio != 0.0 && hb != mzHbAlheio)
         {
            if(mzHbAvancaDesde == 0) mzHbAvancaDesde = agora;
            mzHbUltMuda = agora;
         }
         mzHbAlheio = hb;
         Log_Cond("trava.inerte", true, "AVISO", "MAESTRO", "TRAVA", "trava de outro token com heartbeat recente: EA inerte, tenta de novo a cada 1 s");
         if(mzHbAvancaDesde > 0 && mzHbUltMuda - mzHbAvancaDesde > HB_TOMADA_S)
         {
            string m = StringFormat("WinMaestro ja' roda em outro grafico deste terminal (%s): esta instancia sai", _Symbol);
            Log("ALERTA", "MAESTRO", "TRAVA", m);
            mzTravaRemoveu = true;
            if(!mzTravaSoMarca) ExpertRemove();
         }
      }
   }
   if(!ok) return false;
   mzTravaMinha = true;
   mzHbAvancaDesde = 0; mzHbUltMuda = 0; mzHbAlheio = 0.0;
   Log_Cond("trava.inerte", false, "INFO", "MAESTRO", "TRAVA", "");
   GlobalVariableSet(mzHbNome, (double)Trava_Agora());
   Log("INFO", "MAESTRO", "TRAVA", StringFormat("trava tomada (%s, token %.0f)", mzTravaNome, mzToken));
   return true;
}

// A trava ainda e' minha? (passo 1, base). Perdida: tenta retomar com heartbeat alheio parado; retomada recarrega a memoria.
bool Trava_Confere(void)
{
   if(mzSemTrava) return true;
   if(!mzTravaMinha) return false;
   if(GlobalVariableCheck(mzTravaNome) && GlobalVariableGet(mzTravaNome) == mzToken) return true;
   mzTravaMinha = false;
   Log("ALERTA", "MAESTRO", "TRAVA", "a trava nao e' mais desta instancia: INVALIDO ate' retomar");
   if(Trava_Tenta()) { mzRecarregar = true; Log("AVISO", "MAESTRO", "TRAVA", "trava retomada: memoria recarregada do disco antes do proximo ciclo"); }
   return false;
}

void Trava_Libera(void)
{
   if(mzSemTrava || !mzTravaMinha || mzTravaNome == "") return;
   GlobalVariableSetOnCondition(mzTravaNome, 0.0, mzToken);
   mzTravaMinha = false;
}

//+------------------------------------------------------------------+
//| Bloqueio e botao (sec. 2.4; spec 7.2)                            |
//+------------------------------------------------------------------+
void Mae_BotaoMostra(const bool mostra)
{
   if(!mzTela) return;
   if(!mostra) { ObjectDelete(0, MAE_BOTAO); return; }
   if(ObjectFind(0, MAE_BOTAO) >= 0) return;
   ObjectCreate(0, MAE_BOTAO, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_XDISTANCE, 170);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_XSIZE, 160);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_YSIZE, 30);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_BGCOLOR, clrFireBrick);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_COLOR, clrWhite);
   ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Desbloquear");
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_STATE, false);
}

void Mae_Bloqueia(const string causa)
{
   if(StringFind(mzBloqMotivo, causa) < 0) mzBloqMotivo = (mzBloqMotivo == "") ? causa : mzBloqMotivo + "; " + causa;
   if(!mzBloqBotao) Log("ALERTA", "MAESTRO", "BLOQUEIO", "entradas bloqueadas: " + causa + " -- olhe o extrato e use o botao Desbloquear (2 cliques em 3 s)");
   else Log("AVISO", "MAESTRO", "BLOQUEIO", "nova causa: " + causa);
   mzBloqBotao = true;
   Mae_BotaoMostra(true);
   Mae_GravaMemoria(true);
}

// O botao: reconhece as absorcoes e os deals nao classificados; linhas sem desfecho ha' PRAZO_BOTAO viram NAO_EXECUTADA
// (o deal ainda vence, sec. 2.1); um Delta estavel vira externa de origem desconhecida (sec. 2.3).
void Mae_Desbloqueia(void)
{
   int na = ArraySize(mzAbsVistas);
   for(int i = 0; i < na; i++) Est_PoeLista(mzReconh, mzAbsVistas[i], 500);
   int nd = ArraySize(mzDeal);
   for(int i = 0; i < nd; i++)
   {
      int rb, pp;
      if(Est_Classifica(i, rb, pp) == CL_NAOCLASS) Est_PoeLista(mzReconh, mzDeal[i].ticket, 500);
   }
   int nl = ArraySize(mzL);
   for(int i = 0; i < nl; i++)
      if(Mapa_Pendente(i) && mzMono - mzL[i].enviado_mono >= PRAZO_BOTAO_MS) Mapa_Muda(i, D_NAO_EXECUTADA, "sem desfecho ha' 10 min: retirada pelo botao");
   if(mzDeltaEstavel && mzDeltaResto != 0)
   {
      mzExtDesc += mzDeltaResto;
      Log("AVISO", "MAESTRO", "DESBLOQUEIO", StringFormat("diferenca estavel %+d gravada como externa de origem desconhecida (total %+d)", mzDeltaResto, mzExtDesc));
   }
   Log("INFO", "MAESTRO", "DESBLOQUEIO", "dono liberou as entradas (causas: " + mzBloqMotivo + ")");
   mzBloqBotao = false; mzBloqMotivo = "";
   for(int r = 0; r < NROBOS; r++) if(mzRestritoDesde[r] > 0) mzRestritoDesde[r] = mzMono;
   Mae_BotaoMostra(false);
   Mae_GravaMemoria(true);
}

void Mae_BotaoClique(const string obj)
{
   if(obj != MAE_BOTAO) return;
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_STATE, false);
   if(!mzBloqBotao) { Mae_BotaoMostra(false); return; }
   datetime agora = TimeLocal();
   if(mzBotaoClique > 0 && agora - mzBotaoClique <= 3)
   {
      mzBotaoClique = 0;
      ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Desbloquear");
      Mae_Desbloqueia();
      return;
   }
   mzBotaoClique = agora;
   ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Confirmar (clique de novo)");
}

//+------------------------------------------------------------------+
//| Ambiente (sec. 6; spec 10.2 passo 3) e PRONTO                    |
//+------------------------------------------------------------------+
void Mae_Ambiente(void)
{
   if(!mzHistOk) return;
   if(mzAmbVisto && !mzProtegendo && !mzParado) return;
   if(mzAmbVisto && mzMono - mzAmbUlt < 30000) return;
   mzAmbUlt = mzMono;
   long mm = mzCorr.ContaI(ACCOUNT_MARGIN_MODE);
   if(mm != ACCOUNT_MARGIN_MODE_RETAIL_NETTING && mm != ACCOUNT_MARGIN_MODE_EXCHANGE)
   {
      mzNaoNetting = true;
      Log("ALERTA", "MAESTRO", "AMBIENTE", "conta nao e' NETTING: INVALIDO permanente (nenhuma ordem)");
      return;
   }
   string falha = "";
   if(mzCorr.SimboloI(SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) falha = "simbolo nao negociavel";
   else if(mzCorr.SimboloD(SYMBOL_TRADE_TICK_SIZE) <= 0.0 || mzCorr.SimboloD(SYMBOL_TRADE_TICK_VALUE) <= 0.0) falha = "tamanho ou valor do tick zerado";
   if(!mzAmbVisto)
   {
      long exe = mzCorr.SimboloI(SYMBOL_TRADE_EXEMODE);
      long fm = mzCorr.SimboloI(SYMBOL_FILLING_MODE);
      if(exe == SYMBOL_TRADE_EXECUTION_EXCHANGE) mzFillMercado = ORDER_FILLING_RETURN;                 // P15
      else mzFillMercado = ((fm & SYMBOL_FILLING_IOC) != 0) ? ORDER_FILLING_IOC : ORDER_FILLING_FOK;
      mzSpecifiedOk = (mzCorr.SimboloI(SYMBOL_EXPIRATION_MODE) & SYMBOL_EXPIRATION_SPECIFIED) != 0;    // decisao 7
      datetime venc = Grade_VencimentoDoSimbolo(_Symbol);
      Log("INFO", "MAESTRO", "AMBIENTE", StringFormat("NETTING ok; mercado %s; E com validade %s; vencimento do contrato %s",
          EnumToString(mzFillMercado), mzSpecifiedOk ? "SPECIFIED" : "DAY (SPECIFIED nao aceito)", venc > 0 ? TimeToString(venc, TIME_DATE) : "(serie continua)"));
      if(mzCorr.RoboEmOutroSimbolo(mzMagic)) Log("AVISO", "MAESTRO", "AMBIENTE", "ha' ordem ou posicao com magic de robo em outro simbolo (O16)");
   }
   mzAmbVisto = true;
   if(falha == "")
   {
      if(mzProtegendo || mzParado) Log("INFO", "MAESTRO", "AMBIENTE", "ambiente voltou ao normal");
      mzProtegendo = false; mzParado = false;
      return;
   }
   bool algo = mzLiq != 0;
   for(int k = 0; k < ArraySize(mzViva) && !algo; k++) if(Mae_EhRobo(mzViva[k].magic)) algo = true;
   for(int r = 0; r < NROBOS && !algo; r++) if(mzEst[r].f != 0) algo = true;
   if(algo)
   {
      if(!mzProtegendo) Log("ALERTA", "MAESTRO", "PROTEGENDO", "ambiente: " + falha + " com ficha ou ordem de robo: modo PROTEGENDO (I5; S, cancelamentos, correcao, zeragem e corte)");
      mzProtegendo = true; mzParado = false;
   }
   else
   {
      if(!mzParado) Log("ALERTA", "MAESTRO", "AMBIENTE", "ambiente: " + falha + " sem ficha nem ordem de robo: parado (nenhuma ordem); confere de novo a cada 30 s");
      mzParado = true; mzProtegendo = false;
   }
}

void Mae_Pronto(void)
{
   if(mzProntoLogado || !mzHistOk) return;
   mzProntoLogado = true;
   long off = (long)mzCorr.Agora() - (long)TimeGMT();
   string s = StringFormat("v%s; liquida %+d; externa %+d; janela desde %s; memoria %s", WM_VERSAO, mzLiq, mzExterna,
                           TimeToString(mzJanIni, TIME_DATE | TIME_MINUTES), mzMemPerdida ? "PERDIDA" : "ok");
   for(int r = 0; r < NROBOS; r++)
      s += StringFormat("; %s ficha %+d%s S %.0f A %.0f", mzNome[r], mzEst[r].f, mzEst[r].noite ? " (noite)" : "", mzNivS[r], mzNivA[r]);
   Log("INFO", "MAESTRO", "PRONTO", s);
   if(!mzCorr.Testador() && MathAbs(off + 3 * 3600) > 900)
      Log("AVISO", "MAESTRO", "PRONTO", StringFormat("relogio do servidor - GMT = %+.1f h (esperado -3 h, P22)", off / 3600.0));
}

//+------------------------------------------------------------------+
//| Painel (spec O7): so' leitura                                    |
//+------------------------------------------------------------------+
void Mae_Painel(void)
{
   if(!mzTela) return;
   if(mzCorr.Testador() && !MQLInfoInteger(MQL_VISUAL_MODE)) return;
   if(mzMono - mzPainelUlt < 1000) return;
   mzPainelUlt = mzMono;
   string est = !mzTravaMinha ? "INERTE (trava de outro grafico)" : (!mzBaseOk ? "INVALIDO" : (mzNaoNetting ? "INVALIDO (nao NETTING)" : (mzParado ? "PARADO (ambiente)" : (mzProtegendo ? "PROTEGENDO" : "ok"))));
   string s = StringFormat("WinMaestro v%s | %s | %s | %s\n", WM_VERSAO, _Symbol, TimeToString(mzAgora, TIME_DATE | TIME_SECONDS), est);
   s += StringFormat("liquida %+d | externa %+d | Delta %+d | corte %s | %s\n", mzLiq, mzExterna, mzDeltaResto,
                     TimeToString(Mae_CDe(mzAgora), TIME_MINUTES), Mae_Bloqueio() ? "BLOQUEIO: " + (mzBloqBotao ? mzBloqMotivo : "automatico") : "entradas liberadas");
   string sits[4] = {"zero", "legitima", "TROCADA", "DUPLICADA"};
   for(int r = 0; r < NROBOS; r++)
   {
      string x = "";
      if(!mzAtivo[r]) x += " [desligado]";
      if(mzInitFalhou[r]) x += " [Init falhou]";
      if(!mzEst[r].confiavel) x += " [RESTRITO]";
      if(mzEst[r].noite) x += " [noite]";
      int ie = mzEst[r].iE;
      string e = (ie >= 0 && ie < ArraySize(mzViva)) ? DoubleToString(mzViva[ie].preco, 0) : "-";
      int sit = (mzEst[r].sit >= 0 && mzEst[r].sit <= 3) ? mzEst[r].sit : 0;
      s += StringFormat("%s: ficha %+d %s @%.0f | S %.0f | A %.0f | E %s | %s%s\n", mzNome[r], mzEst[r].f, sits[sit], mzEst[r].preco,
                        mzNivS[r], mzVista[r].alvo_vivo, e, Int_Nome(mzInt[r].tipo), x);
   }
   Comment(s);
}

//+------------------------------------------------------------------+
//| Ciclo (sec. 3)                                                   |
//+------------------------------------------------------------------+
void Mae_Invalido(void)
{
   if(mzInvalidoDesde == 0) mzInvalidoDesde = mzMono;
   mzDeltaDesde = 0;
   mzExtZeroDesde = 0;                  // a regra de saida da externa desconhecida conta so' com a base firme (A-1)
   // o snapshot desta leitura nao vale: os indices de ordens vivas do ciclo anterior deixam de apontar para mzViva
   for(int r = 0; r < NROBOS; r++)
   {
      mzEst[r].nS = 0; mzEst[r].iE = -1; mzEst[r].iA = -1; mzEst[r].nFora = 0; mzEst[r].lE = -1;
      mzEst[r].confiavel = false; mzEst[r].inequivoco = false;
      mzSairConta[r] = false;            // PRAZO_SAIR so' conta ciclos confiaveis
      mzSFaltaDesde[r] = 0;              // a S faltando conta de novo depois de a base firmar (B-9)
   }
   long ha = mzMono - mzInvalidoDesde;
   Log_Cond("invalido", ha >= 30000, "ALERTA", "MAESTRO", "ESTADO",
            StringFormat("INVALIDO ha' %d s (conexao %s, trava %s): nenhum envio nem cancelamento; as S seguem no servidor",
                         (int)(ha / 1000), mzConexaoOk ? "ok" : "NAO", mzTravaOk ? "ok" : "NAO"));
}

// Um ciclo: leitura, casamento, derivacao, decisao, registro e envio. true = houve envio (roda outro ciclo).
bool Mae_CicloUm(void)
{
   bool base = Snap_Le();                                     // 1
   if(Mae_Dia(mzAgora) != mzMemDia) Mae_DiaNovo();
   Trava_Hb();
   if(!base) { Mae_Invalido(); return false; }
   if(mzInvalidoDesde != 0) { mzInvalidoDesde = 0; Log_Cond("invalido", false, "INFO", "MAESTRO", "ESTADO", ""); }
   if(mzNaoNetting) return false;
   Mapa_Passo2();                                             // 2
   Est_Deriva();                                              // 3
   Est_Recuo();
   Mae_Ambiente();
   if(mzNaoNetting) return false;
   Est_LogDeals();
   Est_Correcoes();
   Est_Episodios();
   Est_Prazos();
   Mae_Pronto();
   if(!mzParado) Est_Modulos();
   return Dec_Passo4();                                       // 4, 5, 6
}

// Disparado por OnTimer, OnTick e OnTradeTransaction. Trava de outro token no OnInit: so' tenta a trava (1 s).
void Mae_Ciclo(void)
{
   if(mzCorr == NULL) return;
   if(!mzTravaMinha)
   {
      long t = Trava_Agora();
      if(t == mzTravaTentUlt) return;
      mzTravaTentUlt = t;
      if(!Trava_Tenta()) return;
      Mae_CarregaMemoria();
   }
   if(mzRecarregar) { mzRecarregar = false; Mae_CarregaMemoria(); }
   for(int k = 0; k < RODADAS; k++) if(!Mae_CicloUm()) break;
   Mae_Painel();
   if(mzMono - mzMemUltGrava >= 1000) Mae_GravaMemoria(false);
}

void Mae_OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(mzCorr == NULL || !mzTravaMinha) return;
   bool do_simbolo = (trans.symbol == _Symbol) || (trans.type == TRADE_TRANSACTION_REQUEST && request.symbol == _Symbol);
   if(!do_simbolo) return;
   Log_Trans(StringFormat("%s ordem #%I64u deal #%I64u estado %s preco %.0f vol %.0f magic %I64u req %u",
             EnumToString(trans.type), trans.order, trans.deal, EnumToString(trans.order_state), trans.price, trans.volume,
             request.magic, result.request_id));
   if(trans.type == TRADE_TRANSACTION_REQUEST) Snap_RequestVisto(result.request_id, result.order);
   Mae_Ciclo();
}

//+------------------------------------------------------------------+
//| Reinicio de todo o estado (P17) e partida                        |
//+------------------------------------------------------------------+
void Mae_Reseta(void)
{
   mzAgoraMsc = 0; mzMono = 0; mzAgora = 0; mzConectado = false; mzConexaoDesde = 0; mzConexaoOk = false; mzTravaOk = false; mzBaseOk = false;
   mzLiq = 0; ArrayResize(mzViva, 0); mzHistOk = false; mzHistOkDesde = 0; ArrayResize(mzDeal, 0); ArrayResize(mzOH, 0);
   mzBid = 0.0; mzAsk = 0.0; mzLivroOk = false; mzUltLast = 0.0; mzUltTickMsc = 0; mzRelogioDesvio = false; mzGPre = 0; mzGNeg = 0; mzGFim = 0; mzGTem = true;
   ArrayResize(mzReqId, 0); ArrayResize(mzReqTk, 0);
   ArrayResize(mzL, 0); mzProxLinha = 1;
   ArrayResize(mzConsR, 0); ArrayResize(mzConsId, 0);
   for(int r = 0; r < NROBOS; r++)
   {
      mzNivS[r] = 0.0; mzNivSIntUlt[r] = 0.0; mzNivA[r] = 0.0; mzEmerg[r] = 0.0; mzEmergLado[r] = 0; mzUltId[r] = 0; mzUltCorrMsc[r] = 0;
      mzEp[r] = 0; mzEpAberto[r] = false; mzRestritoDesde[r] = 0; mzSFaltaDesde[r] = 0;
      Int_Nada(mzInt[r], ""); mzEntId[r] = 0; mzEntDesde[r] = 0; mzSairAcum[r] = 0; mzSairUlt[r] = 0; mzSairConta[r] = false;
      mzInit[r] = false; mzInitFalhou[r] = false; mzSCruzDesde[r] = 0; mzOrigemUlt[r] = 0; mzIntTipoUlt[r] = -1;
      ZeroMemory(mzEst[r]); mzEst[r].iE = -1; mzEst[r].iA = -1; mzEst[r].lE = -1;
      ZeroMemory(mzVista[r]);
      mzAtivo[r] = true;
   }
   for(int d = 0; d < NDONOS; d++) for(int p = 0; p < NPAPEIS; p++) { mzEspera[d][p] = 0; mzRecusaN[d][p] = 0; mzRecusaAlerta[d][p] = 0; }
   for(int d = 0; d <= NROBOS; d++) mzSeq[d] = 0;
   mzSeqDia = 0; mzBloqBotao = false; mzBloqMotivo = ""; ArrayResize(mzReconh, 0); mzExtDesc = 0; mzExtZeroDesde = 0;
   ArrayResize(mzAbsVistas, 0); ArrayResize(mzDealsLog, 0); mzJanRecuo = 0; mzJanRecuoDia = 0; mzMemDia = 0;
   mzInvalidoDesde = 0; mzDeltaVal = 0; mzDeltaDesde = 0; mzRecuoUlt = 0; mzRecuoN = 0;
   mzMemPerdida = false; mzMemGravando = true; mzMemUltGrava = 0; mzMemCarregada = false; mzPartidaMsc = 0;
   mzProntoLogado = false; mzAmbVisto = false; mzProtegendo = false; mzParado = false; mzNaoNetting = false; mzAmbUlt = 0;
   mzSpecifiedOk = false; mzFillMercado = ORDER_FILLING_RETURN; mzPainelUlt = 0; mzBotaoClique = 0;
   mzExterna = 0; mzSomaDeals = 0; mzDelta = 0; mzDeltaResto = 0; mzNaoClassTotal = 0; mzDeltaEstavel = false; mzTodosProvados = false;
   mzBloqAuto = false; mzAbsVirtual = false; mzJanIni = 0; mzGradeAvisoDia = 0;
   mzTravaNome = ""; mzHbNome = ""; mzToken = 0.0; mzTravaMinha = false; mzHbAlheio = 0.0; mzHbAvancaDesde = 0; mzHbUltMuda = 0; mzTravaTentUlt = 0;
   mzRecarregar = false; mzTravaRemoveu = false; ArrayResize(mzCarK, 0); ArrayResize(mzCarV, 0); mzCarMesmoDia = false;
   Mem_Limpa(); mzMemUltimoTexto = "";
   Log_CondLimpa();
}

// OnInit (sec. 6): zera as globais, toma a trava, carrega a memoria. Os ciclos comecam no timer.
void Mae_Partida(void)
{
   mzPartidaMsc = mzCorr.AgoraMsc();
   mzAgoraMsc = mzPartidaMsc; mzMono = mzCorr.Mono(); mzAgora = (datetime)(mzPartidaMsc / 1000);
   Trava_Nomes();
   mzTravaTentUlt = Trava_Agora();
   if(Trava_Tenta()) Mae_CarregaMemoria();
   else Log("AVISO", "MAESTRO", "TRAVA", "trava de outro token com heartbeat recente: EA inerte (nenhuma ordem, nao grava memoria); tenta de novo a cada 1 s");
}

void Mae_Fim(const int reason)
{
   Log("INFO", "MAESTRO", "FIM", StringFormat("reason %d", reason));
   if(mzTravaMinha)
   {
      Mae_GravaMemoria(true);
      if(reason != REASON_PARAMETERS && reason != REASON_CHARTCHANGE && reason != REASON_TEMPLATE) Trava_Libera();
   }
   Mae_BotaoMostra(false);
   if(mzTela) Comment("");
}

#endif
