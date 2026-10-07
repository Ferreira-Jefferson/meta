//+------------------------------------------------------------------+
//| WinMaestro/Log.mqh                                               |
//| Log do maestro (especificacao sec. 11).                              |
//|  - Diario do MT5 + <pasta>logs/AAAA-MM-DD.log (FileFlush por      |
//|    linha; e' fonte da recuperacao) + logs/AAAA-MM-DD_trans.log.   |
//|  - Formato: HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe |      |
//|    [tick HH:MM:SS.mmm loc HH:MM:SS]                               |
//|  - ALERTA tambem dispara Alert(). Anti-spam por objeto (item 1.12)|
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_LOG_MQH
#define WINMAESTRO_LOG_MQH

#include "Corretora.mqh"

string mzLogPasta   = "";                 // pasta base (termina em "\\")
int    mzLogH       = INVALID_HANDLE;
string mzLogDiaAb   = "";
int    mzTransH     = INVALID_HANDLE;
string mzTransDiaAb = "";
bool   mzLogImprime = true;                // false = nao repete no Diario (testes unitarios)
bool   mzLogAlert   = true;                // false = sem Alert() (testes unitarios)

// anti-spam por objeto
string   mzCondChave[];
datetime mzCondInicio[];
datetime mzCondUltimo[];
int      mzCondConta[];

datetime Log_Agora(void)
{
   if(mzCorr != NULL) return mzCorr.Agora();
   return TimeTradeServer();
}

string Log_DataArq(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return StringFormat("%04d-%02d-%02d", d.year, d.mon, d.day);
}

string Log_Hms(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return StringFormat("%02d:%02d:%02d", d.hour, d.min, d.sec);
}

string Log_HmsMsc(const long msc)
{
   datetime t = (datetime)(msc / 1000);
   return Log_Hms(t) + StringFormat(".%03d", (int)(msc % 1000));
}

void Log_Fecha(void)
{
   if(mzLogH != INVALID_HANDLE) { FileClose(mzLogH); mzLogH = INVALID_HANDLE; }
   if(mzTransH != INVALID_HANDLE) { FileClose(mzTransH); mzTransH = INVALID_HANDLE; }
   mzLogDiaAb = ""; mzTransDiaAb = "";
}

void Log_Pasta(const string pasta)
{
   Log_Fecha();
   mzLogPasta = pasta;
}

int Log_Abre(const string nome)
{
   int h = FileOpen(nome, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h != INVALID_HANDLE) FileSeek(h, 0, SEEK_END);
   return h;
}

string Log_ArquivoDia(const datetime t) { return mzLogPasta + "logs\\" + Log_DataArq(t) + ".log"; }

void Log_Escreve(const string linha, const datetime agora)
{
   if(mzLogPasta == "") return;
   string dia = Log_DataArq(agora);
   if(dia != mzLogDiaAb || mzLogH == INVALID_HANDLE)
   {
      if(mzLogH != INVALID_HANDLE) FileClose(mzLogH);
      mzLogH = Log_Abre(Log_ArquivoDia(agora));
      mzLogDiaAb = dia;
   }
   if(mzLogH == INVALID_HANDLE) return;
   FileWriteString(mzLogH, linha + "\r\n");
   FileFlush(mzLogH);
}

// Linha principal do log.
void Log(const string nivel, const string robo, const string evento, const string detalhe)
{
   datetime agora = Log_Agora();
   long ms = (long)(GetMicrosecondCount() / 1000) % 1000;
   string tick = "--:--:--.---";
   MqlTick t;
   if(mzCorr != NULL && mzCorr.UltimoTick(t) && t.time_msc > 0) tick = Log_HmsMsc(t.time_msc);
   string niv = nivel;
   while(StringLen(niv) < 6) niv += " ";
   string linha = StringFormat("%s.%03d | %s | %s | %s | %s | [tick %s loc %s]",
                               Log_Hms(agora), (int)ms, niv, robo, evento, detalhe, tick, Log_Hms(TimeLocal()));
   if(mzLogImprime) Print(linha);
   Log_Escreve(linha, agora);
   if(nivel == "ALERTA" && mzLogAlert) Alert("WinMaestro ", robo, " ", evento, ": ", detalhe);
}

// Linha bruta por OnTradeTransaction do simbolo.
void Log_Trans(const string linha)
{
   if(mzLogPasta == "") return;
   datetime agora = Log_Agora();
   string dia = Log_DataArq(agora);
   if(dia != mzTransDiaAb || mzTransH == INVALID_HANDLE)
   {
      if(mzTransH != INVALID_HANDLE) FileClose(mzTransH);
      mzTransH = Log_Abre(mzLogPasta + "logs\\" + dia + "_trans.log");
      mzTransDiaAb = dia;
   }
   if(mzTransH == INVALID_HANDLE) return;
   FileWriteString(mzTransH, Log_Hms(agora) + " | " + linha + "\r\n");
   FileFlush(mzTransH);
}

// Anti-spam por objeto: a mesma condicao e' logada ao comecar, a cada 5 min com contador e ao terminar.
void Log_Cond(const string chave, const bool ativa, const string nivel, const string robo, const string evento, const string detalhe)
{
   datetime agora = Log_Agora();
   int n = ArraySize(mzCondChave);
   int idx = -1;
   for(int i = 0; i < n; i++) if(mzCondChave[i] == chave) { idx = i; break; }
   if(ativa)
   {
      if(idx < 0)
      {
         ArrayResize(mzCondChave, n + 1); ArrayResize(mzCondInicio, n + 1);
         ArrayResize(mzCondUltimo, n + 1); ArrayResize(mzCondConta, n + 1);
         mzCondChave[n] = chave; mzCondInicio[n] = agora; mzCondUltimo[n] = agora; mzCondConta[n] = 1;
         Log(nivel, robo, evento, detalhe);
         return;
      }
      mzCondConta[idx]++;
      if(agora - mzCondUltimo[idx] >= 300)
      {
         mzCondUltimo[idx] = agora;
         Log(nivel, robo, evento, StringFormat("%s (continua: %d vezes desde %s)", detalhe, mzCondConta[idx], Log_Hms(mzCondInicio[idx])));
      }
      return;
   }
   if(idx < 0) return;
   Log("INFO", robo, evento, StringFormat("terminou: %s (%d vezes, %d s)", chave, mzCondConta[idx], (int)(agora - mzCondInicio[idx])));
   for(int i = idx; i < n - 1; i++)
   {
      mzCondChave[i] = mzCondChave[i + 1]; mzCondInicio[i] = mzCondInicio[i + 1];
      mzCondUltimo[i] = mzCondUltimo[i + 1]; mzCondConta[i] = mzCondConta[i + 1];
   }
   ArrayResize(mzCondChave, n - 1); ArrayResize(mzCondInicio, n - 1);
   ArrayResize(mzCondUltimo, n - 1); ArrayResize(mzCondConta, n - 1);
}

// Encerra todas as condicoes cuja chave comeca com o prefixo (ex.: o envio seguinte do robo passou no D1).
void Log_CondEncerraPrefixo(const string prefixo)
{
   for(int i = ArraySize(mzCondChave) - 1; i >= 0; i--)
      if(StringFind(mzCondChave[i], prefixo) == 0) Log_Cond(mzCondChave[i], false, "", "MAESTRO", "ESTADO", "");
}

void Log_CondLimpa(void)
{
   ArrayResize(mzCondChave, 0); ArrayResize(mzCondInicio, 0);
   ArrayResize(mzCondUltimo, 0); ArrayResize(mzCondConta, 0);
}

// Le as linhas do log de um dia (para a recuperacao sem memoria e o resumo). Devolve o numero de linhas.
int Log_LeDia(const datetime dia, string &linhas[])
{
   ArrayResize(linhas, 0);
   if(mzLogPasta == "") return 0;
   string nome = Log_ArquivoDia(dia);
   if(mzLogH != INVALID_HANDLE && mzLogDiaAb == Log_DataArq(dia)) FileFlush(mzLogH);
   int h = FileOpen(nome, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) return 0;
   int n = 0;
   while(!FileIsEnding(h))
   {
      string s = FileReadString(h);
      if(s == "") continue;
      ArrayResize(linhas, n + 1);
      linhas[n++] = s;
   }
   FileClose(h);
   return n;
}

#endif
