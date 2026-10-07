//+------------------------------------------------------------------+
//| WinMaestro/Memoria.mqh                                           |
//| Memoria em disco (especificacao sec. 10.1).                          |
//|  - <pasta>estado.txt (+ .bak), formato chave=valor.              |
//|  - Escrita atomica: estado.tmp inteiro com ultima linha          |
//|    fim=<checksum>, fecha, copia .txt -> .bak, move .tmp -> .txt. |
//|  - Leitura: .txt; ausente/vazio/sem fim=/checksum errado -> .bak;|
//|    os dois ruins -> memoria perdida.                             |
//| Guarda so' o que a corretora nao sabe. Instantes, nunca contagens|
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_MEMORIA_MQH
#define WINMAESTRO_MEMORIA_MQH

string mzMemPasta = "";      // pasta (termina em "\\")
string mzMemK[];             // chaves da memoria em montagem/carregada
string mzMemV[];
string mzMemUltimoTexto = "";

void Mem_Limpa(void) { ArrayResize(mzMemK, 0); ArrayResize(mzMemV, 0); }

int Mem_Idx(const string k)
{
   int n = ArraySize(mzMemK);
   for(int i = 0; i < n; i++) if(mzMemK[i] == k) return i;
   return -1;
}

string Mem_Limpo(const string v)
{
   string s = v;
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
}

void Mem_Set(const string k, const string v)
{
   int i = Mem_Idx(k);
   if(i < 0)
   {
      i = ArraySize(mzMemK);
      ArrayResize(mzMemK, i + 1); ArrayResize(mzMemV, i + 1);
      mzMemK[i] = k;
   }
   mzMemV[i] = Mem_Limpo(v);
}
void Mem_SetI(const string k, const long v)       { Mem_Set(k, IntegerToString(v)); }
void Mem_SetU(const string k, const ulong v)      { Mem_Set(k, StringFormat("%I64u", v)); }
void Mem_SetD(const string k, const double v)     { Mem_Set(k, DoubleToString(v, 8)); }
void Mem_SetB(const string k, const bool v)       { Mem_Set(k, v ? "1" : "0"); }

bool   Mem_Tem(const string k)                    { return Mem_Idx(k) >= 0; }
string Mem_Get(const string k, const string def)  { int i = Mem_Idx(k); return i < 0 ? def : mzMemV[i]; }
long   Mem_GetI(const string k, const long def)   { int i = Mem_Idx(k); return i < 0 ? def : StringToInteger(mzMemV[i]); }
ulong  Mem_GetU(const string k, const ulong def)  { int i = Mem_Idx(k); return i < 0 ? def : (ulong)StringToInteger(mzMemV[i]); }
double Mem_GetD(const string k, const double def) { int i = Mem_Idx(k); return i < 0 ? def : StringToDouble(mzMemV[i]); }
bool   Mem_GetB(const string k, const bool def)   { int i = Mem_Idx(k); return i < 0 ? def : (mzMemV[i] == "1"); }

// FNV-1a 32 bits sobre os caracteres do texto.
uint Mem_Checksum(const string texto)
{
   uint h = 2166136261;
   int n = StringLen(texto);
   for(int i = 0; i < n; i++)
   {
      h ^= (uint)StringGetCharacter(texto, i);
      h *= 16777619;
   }
   return h;
}

string Mem_Texto(void)
{
   string t = "";
   int n = ArraySize(mzMemK);
   for(int i = 0; i < n; i++) t += mzMemK[i] + "=" + mzMemV[i] + "\n";
   return t;
}

// Grava o conteudo atual de mzMemK/mzMemV. forcar=false pula se nada mudou.
bool Mem_Grava(const bool forcar)
{
   if(mzMemPasta == "") return false;
   string corpo = Mem_Texto();
   if(!forcar && corpo == mzMemUltimoTexto) return true;
   string arq = corpo + "fim=" + StringFormat("%u", Mem_Checksum(corpo)) + "\n";
   string tmp = mzMemPasta + "estado.tmp", txt = mzMemPasta + "estado.txt", bak = mzMemPasta + "estado.bak";
   int h = FileOpen(tmp, FILE_WRITE | FILE_TXT | FILE_UNICODE);   // Unicode: o checksum e' sobre o mesmo texto que vai ao disco (B-8)
   if(h == INVALID_HANDLE) return false;
   uint esc = FileWriteString(h, arq);
   FileClose(h);
   if(esc == 0) return false;
   if(FileIsExist(txt)) FileCopy(txt, 0, bak, FILE_REWRITE);
   if(!FileMove(tmp, 0, txt, FILE_REWRITE)) return false;
   mzMemUltimoTexto = corpo;
   return true;
}

// Le e valida um arquivo. true = valido (mzMemK/mzMemV preenchidos).
bool Mem_LeArquivo(const string nome)
{
   Mem_Limpa();
   if(!FileIsExist(nome)) return false;
   int h = FileOpen(nome, FILE_READ | FILE_TXT | FILE_UNICODE);
   if(h == INVALID_HANDLE) return false;
   string corpo = "";
   string fim = "";
   bool achou_fim = false;
   while(!FileIsEnding(h))
   {
      string s = FileReadString(h);
      if(s == "") continue;
      if(StringFind(s, "fim=") == 0) { fim = StringSubstr(s, 4); achou_fim = true; break; }
      corpo += s + "\n";
      int p = StringFind(s, "=");
      if(p <= 0) { FileClose(h); Mem_Limpa(); return false; }
      int n = ArraySize(mzMemK);
      ArrayResize(mzMemK, n + 1); ArrayResize(mzMemV, n + 1);
      mzMemK[n] = StringSubstr(s, 0, p);
      mzMemV[n] = StringSubstr(s, p + 1);
   }
   FileClose(h);
   if(!achou_fim || corpo == "" || StringFormat("%u", Mem_Checksum(corpo)) != fim) { Mem_Limpa(); return false; }
   return true;
}

// 0 = estado.txt valido; 1 = usou o .bak; 2 = memoria perdida.
int Mem_Carrega(void)
{
   if(mzMemPasta == "") { Mem_Limpa(); return 2; }
   if(Mem_LeArquivo(mzMemPasta + "estado.txt")) return 0;
   if(Mem_LeArquivo(mzMemPasta + "estado.bak")) return 1;
   Mem_Limpa();
   return 2;
}

#endif
