//+------------------------------------------------------------------+
//| Calendario.mqh — horário do pregão (grade B3 por data) e         |
//| vencimentos do WIN.                                              |
//|                                                                  |
//| Relógio: o servidor da corretora já está em Brasília (BRT).      |
//| Espelha dados.py (vencimentos) e a grade data/b3_grade_horaria_  |
//| win.csv (fim do contínuo por vigência).                          |
//+------------------------------------------------------------------+
#ifndef ESCADA_CALENDARIO
#define ESCADA_CALENDARIO

#define SEG_DIA            86400
#define MIN_ABERTURA       (9 * 60)   // 09:00, início do contínuo
#define MIN_CORTE_ANTES    5          // zera 5 min antes do fim do contínuo (regra do dono)

//--- Grade da B3: a partir de cada data, a que horas acaba o contínuo.
struct Vigencia { datetime inicio; int fim_min; };
Vigencia GRADE[] = {
   {D'2020.11.03', 18 * 60 + 25}, {D'2021.03.15', 17 * 60 + 55},
   {D'2021.11.08', 18 * 60 + 25}, {D'2022.03.14', 17 * 60 + 55},
   {D'2022.11.07', 18 * 60 + 25}, {D'2023.03.13', 17 * 60 + 55},
   {D'2023.11.06', 18 * 60 + 25}, {D'2024.03.11', 18 * 60 + 25}
};

//--- Meia-noite do dia de um instante.
datetime DiaDe(datetime t) { return t - (t % SEG_DIA); }

//--- Minuto do dia (0..1439) de um instante.
int MinutoDoDia(datetime t) { return (int)((t % SEG_DIA) / 60); }

//--- Minuto do dia em que acaba o pregão contínuo, pela grade vigente na data.
int FimContinuoMin(datetime dia)
{
   int fim = GRADE[0].fim_min;
   for(int k = 0; k < ArraySize(GRADE); k++)
      if(dia >= GRADE[k].inicio) fim = GRADE[k].fim_min;
   return fim;
}

datetime FimContinuo(datetime dia) { return DiaDe(dia) + FimContinuoMin(dia) * 60; }
datetime HoraCorte(datetime dia)   { return FimContinuo(dia) - MIN_CORTE_ANTES * 60; }

//--- O minuto t pertence ao pregão contínuo (sem leilão de fechamento)?
bool NoContinuo(datetime t)
{
   int m = MinutoDoDia(t);
   return m >= MIN_ABERTURA && m < FimContinuoMin(DiaDe(t));
}

//--- Vencimento do WIN: quarta-feira mais próxima do dia 15 dos meses pares.
datetime Vencimento(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime d15 = StructToTime(d);
   TimeToStruct(d15, d);
   int dif = 3 - d.day_of_week;           // quarta = 3 (domingo = 0)
   if(dif > 3)  dif -= 7;
   if(dif < -3) dif += 7;
   return d15 + dif * SEG_DIA;
}

//--- Número do contrato vigente no dia: quantos vencimentos já passaram (o dia do vencimento já é o novo).
int ContratoDe(datetime dia)
{
   int n = 0;
   for(int ano = 2021; ano <= 2030; ano++)
      for(int mes = 2; mes <= 12; mes += 2)
         if(Vencimento(ano, mes) <= dia) n++;
   return n;
}

#endif
