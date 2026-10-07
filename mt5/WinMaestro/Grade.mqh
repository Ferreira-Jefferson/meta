//+------------------------------------------------------------------+
//| WinMaestro/Grade.mqh                                             |
//| Grade de horarios do WIN embutida (especificacao sec. 1, sec. 9.1).      |
//| Fonte: data/b3_grade_horaria_win.csv (atualizar = recompilar).   |
//| Cada linha vale de vigencia_inicio ate' a vespera da proxima.    |
//| Linha sem horarios (2026-11-02, OC nao publicado) = "sem linha": |
//| F = 17:55 e AVISO (sec. 9.1).                                        |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_GRADE_MQH
#define WINMAESTRO_GRADE_MQH

#define GRADE_N 13
// AAAAMMDD de vigencia_inicio; minutos do dia de preabertura_inicio, negociacao_inicio, negociacao_fim, vencimento_fim.
// -1 = linha sem horarios (sem linha).
const int GRADE_INI[GRADE_N]  = {20201103, 20210315, 20211108, 20220314, 20221107, 20230313, 20231106,
                                 20240311, 20241104, 20250310, 20251103, 20260309, 20261102};
const int GRADE_PRE[GRADE_N]  = {535, 535, 535, 535, 535, 535, 535, 535, 535, 535, 535, 535, -1};
const int GRADE_NEG[GRADE_N]  = {540, 540, 540, 540, 540, 540, 540, 540, 540, 540, 540, 540, -1};
const int GRADE_FIM[GRADE_N]  = {1105, 1075, 1105, 1075, 1105, 1075, 1105, 1105, 1105, 1105, 1105, 1105, -1};
const int GRADE_VENC[GRADE_N] = {1075, 1020, 1080, 1020, 1080, 1020, 1080, 1020, 1080, 1020, 1080, 1020, -1};

#define GRADE_SEM_LINHA_FIM 1075   // 17:55
#define GRADE_SEM_LINHA_NEG 540    // 09:00 (escolha: a especificacao so' fixa o F)
#define GRADE_SEM_LINHA_PRE 535    // 08:55 (idem)

int Grade_Chave(const datetime dia)
{
   MqlDateTime d; TimeToStruct(dia, d);
   return d.year * 10000 + d.mon * 100 + d.day;
}

// true = a data tem linha na grade. Sempre preenche os horarios (com o padrao "sem linha" quando nao tem).
bool Grade_Le(const datetime dia, int &pre, int &neg, int &fim, int &venc)
{
   int k = Grade_Chave(dia);
   int idx = -1;
   for(int i = 0; i < GRADE_N; i++) if(GRADE_INI[i] <= k) idx = i;
   if(idx < 0 || GRADE_FIM[idx] < 0)
   {
      pre = GRADE_SEM_LINHA_PRE; neg = GRADE_SEM_LINHA_NEG; fim = GRADE_SEM_LINHA_FIM; venc = GRADE_SEM_LINHA_FIM;
      return false;
   }
   pre = GRADE_PRE[idx]; neg = GRADE_NEG[idx]; fim = GRADE_FIM[idx]; venc = GRADE_VENC[idx];
   return true;
}

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime Grade_VencimentoWIN(const int ano, const int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime t15 = StructToTime(d);
   TimeToStruct(t15, d);
   int dif = 3 - d.day_of_week;
   if(dif > 3) dif -= 7;
   if(dif < -3) dif += 7;
   return t15 + dif * 86400;
}

// Dia de vencimento do contrato do grafico (WIN + letra + 2 digitos, ex. WINV26). 0 = nao e' contrato
// especifico (serie continua WIN$N/WIN@: sem vencimento proprio -- escolha documentada).
datetime Grade_VencimentoDoSimbolo(const string simbolo)
{
   if(StringLen(simbolo) != 6 || StringSubstr(simbolo, 0, 3) != "WIN") return 0;
   string letra = StringSubstr(simbolo, 3, 1);
   string meses = "FGHJKMNQUVXZ";
   int m = StringFind(meses, letra);
   if(m < 0) return 0;
   string aa = StringSubstr(simbolo, 4, 2);
   ushort c0 = StringGetCharacter(aa, 0), c1 = StringGetCharacter(aa, 1);
   if(c0 < '0' || c0 > '9' || c1 < '0' || c1 > '9') return 0;
   int ano = 2000 + (int)StringToInteger(aa);
   int mes = m + 1;
   if(mes % 2 != 0) return 0;
   return Grade_VencimentoWIN(ano, mes);
}

#endif
