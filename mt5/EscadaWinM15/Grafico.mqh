//+------------------------------------------------------------------+
//| Grafico.mqh — desenha no gráfico o que o robô usa para decidir:  |
//| médias, pivôs da escada, sinais, entrada e stop. Só figuras.     |
//|                                                                  |
//| Cada valor é desenhado na barra M15 em que ficou conhecido. Os   |
//| objetos levam o índice da barra no nome, e os de mais de         |
//| GR_DIAS dias são apagados. Não desenha no Testador sem visual.   |
//+------------------------------------------------------------------+
#ifndef ESCADA_GRAFICO
#define ESCADA_GRAFICO

#include "Escada.mqh"
#include "Indicadores.mqh"

#define GR_PREFIXO     "ESC_"
#define GR_DIAS        10                 // dias de histórico desenhados
#define GR_BARRAS_MAX  (GR_DIAS * 40)     // ~barras M15 nesses dias (o resto é apagado)

#define SINAL_NENHUM   0
#define SINAL_FILTRADO 1                  // escada armou, mas algum filtro barrou
#define SINAL_OK       2

#define COR_MME38      clrOrange          // stop apertado
#define COR_MMS17      clrAqua            // filtro MMS17 x MMS34 (close)
#define COR_MMS34      clrYellow
#define COR_MMS72      clrDodgerBlue      // MMS72 do open (inclinação)
#define COR_H1_9       clrPlum            // tendência H1: MME 9 / 21 / 34
#define COR_H1_21      clrMediumOrchid
#define COR_H1_34      clrDarkViolet
#define COR_ABERTURA   clrGray            // abertura do pregão
#define COR_TOPO       clrTomato
#define COR_FUNDO      clrMediumSeaGreen
#define COR_ZIGZAG     clrSilver
#define COR_COMPRA     clrLime
#define COR_VENDA      clrRed
#define COR_FILTRADO   clrDimGray
#define COR_LIMITE     clrGold
#define COR_STOP       clrRed

bool   g_desenha = false;
double g_h1_ant[3];                       // MMEs do H1 desenhadas na barra anterior

//=================== primitivas ===================
string NomeObj(int i, string o) { return GR_PREFIXO + IntegerToString(i) + "_" + o; }

void Estilo(string nome, color cor, int largura, ENUM_LINE_STYLE estilo = STYLE_SOLID)
{
   ObjectSetInteger(0, nome, OBJPROP_COLOR, cor);
   ObjectSetInteger(0, nome, OBJPROP_WIDTH, largura);
   ObjectSetInteger(0, nome, OBJPROP_STYLE, estilo);
   ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, nome, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, nome, OBJPROP_BACK, true);
}

void Segmento(string nome, datetime t1, double p1, datetime t2, double p2, color cor, int largura,
              ENUM_LINE_STYLE estilo = STYLE_SOLID)
{
   if(p1 <= 0 || p2 <= 0) return;                  // SEM_VALOR ou série ainda vazia
   if(!ObjectCreate(0, nome, OBJ_TREND, 0, t1, p1, t2, p2)) return;
   ObjectSetInteger(0, nome, OBJPROP_RAY_RIGHT, false);
   Estilo(nome, cor, largura, estilo);
}

void Seta(string nome, datetime t, double p, int codigo, color cor, int largura, ENUM_ARROW_ANCHOR ancora)
{
   if(!ObjectCreate(0, nome, OBJ_ARROW, 0, t, p)) return;
   ObjectSetInteger(0, nome, OBJPROP_ARROWCODE, codigo);
   ObjectSetInteger(0, nome, OBJPROP_ANCHOR, ancora);
   Estilo(nome, cor, largura);
}

//--- Visual do gráfico igual ao template MM34_4medias (sem as médias dele): velas, sem grade, sem volume.
void AplicaVisual()
{
   ChartSetInteger(0, CHART_MODE, CHART_CANDLES);
   ChartSetInteger(0, CHART_SHOW_GRID, false);
   ChartSetInteger(0, CHART_SHOW_VOLUMES, CHART_VOLUME_HIDE);
   ChartSetInteger(0, CHART_SHIFT, true);
   ChartSetInteger(0, CHART_COLOR_BACKGROUND, CLR_NONE);
   ChartSetInteger(0, CHART_COLOR_FOREGROUND, C'224,255,255');
   ChartSetInteger(0, CHART_COLOR_CHART_UP, clrGreen);
   ChartSetInteger(0, CHART_COLOR_CANDLE_BULL, clrGreen);
   ChartSetInteger(0, CHART_COLOR_CHART_DOWN, clrTomato);
   ChartSetInteger(0, CHART_COLOR_CANDLE_BEAR, clrTomato);
   ChartSetInteger(0, CHART_COLOR_CHART_LINE, clrWhite);
   ChartSetInteger(0, CHART_COLOR_BID, C'119,136,153');
   ChartSetInteger(0, CHART_COLOR_LAST, C'32,178,170');
   ChartSetInteger(0, CHART_COLOR_STOP_LEVEL, clrRed);
   ChartRedraw(0);
}

//=================== partes do desenho ===================
void GraficoInicia()
{
   g_desenha = !MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_VISUAL_MODE);
   if(g_desenha) AplicaVisual();
   ArrayInitialize(g_h1_ant, 0.0);
   ObjectsDeleteAll(0, GR_PREFIXO);
}

void GraficoLimpa() { if(!MQLInfoInteger(MQL_TESTER)) ObjectsDeleteAll(0, GR_PREFIXO); }

//--- A barra i entra no desenho (dentro dos últimos GR_DIAS dias)?
bool DeveDesenhar(int i) { return g_desenha && g_barras[i].t >= TimeCurrent() - GR_DIAS * SEG_DIA; }

//--- Médias: MME38, MMS17 e MMS34 do close e MMS72 do open (M15), MMEs 9/21/34 do último H1
//--- fechado, abertura do dia.
void DesenhaMedias(int i)
{
   double h1[3]; h1[0] = g_h1.mme9; h1[1] = g_h1.mme21; h1[2] = g_h1.mme34;
   if(g_h1.n == 0) ArrayInitialize(h1, 0.0);
   if(i > 0)
   {
      datetime t0 = g_barras[i - 1].t, t1 = g_barras[i].t;
      Segmento(NomeObj(i, "mme38"), t0, g_mme38[i - 1], t1, g_mme38[i], COR_MME38, 2);
      Segmento(NomeObj(i, "mms17"), t0, MMS(i - 1, 17), t1, MMS(i, 17), COR_MMS17, 1);
      Segmento(NomeObj(i, "mms34"), t0, MMS(i - 1, 34), t1, MMS(i, 34), COR_MMS34, 1);
      Segmento(NomeObj(i, "mms72"), t0, MMS(i - 1, 72, true), t1, MMS(i, 72, true), COR_MMS72, 2);
      Segmento(NomeObj(i, "h1_9"),  t0, g_h1_ant[0], t1, h1[0], COR_H1_9,  1, STYLE_DOT);
      Segmento(NomeObj(i, "h1_21"), t0, g_h1_ant[1], t1, h1[1], COR_H1_21, 1, STYLE_DOT);
      Segmento(NomeObj(i, "h1_34"), t0, g_h1_ant[2], t1, h1[2], COR_H1_34, 1, STYLE_DOT);
   }
   ArrayCopy(g_h1_ant, h1);
   double abertura = g_barras[InicioDoDia(i)].o;
   Segmento(NomeObj(i, "abert"), g_barras[i].t, abertura, g_barras[i].t + SEG_BARRA, abertura, COR_ABERTURA, 1, STYLE_DASH);
}

//--- Pivô confirmado nesta barra: ponto no topo/fundo e a perna do ZigZag até ele.
void DesenhaPivo(int i, const Pivo &piv[], int p)
{
   if(p < 0) return;
   datetime t = g_barras[piv[p].i_pivo].t;
   bool topo = piv[p].tipo == PIVO_TOPO;
   Seta(NomeObj(i, "pivo"), t, piv[p].preco, 159, topo ? COR_TOPO : COR_FUNDO, 4, topo ? ANCHOR_BOTTOM : ANCHOR_TOP);
   if(p > 0) Segmento(NomeObj(i, "zz"), g_barras[piv[p - 1].i_pivo].t, piv[p - 1].preco, t, piv[p].preco, COR_ZIGZAG, 1, STYLE_DASH);
}

//--- Sinal na barra de confirmação: seta cheia se passou nos filtros, cinza se foi barrado.
void DesenhaSinal(int i, const Pivo &piv[], int p, int sinal)
{
   if(sinal == SINAL_NENHUM) return;
   bool compra = LadoDoPivo(piv[p]) == 1;
   bool ok = sinal == SINAL_OK;
   color cor = !ok ? COR_FILTRADO : (compra ? COR_COMPRA : COR_VENDA);
   Seta(NomeObj(i, "sinal"), g_barras[i].t, compra ? g_barras[i].l : g_barras[i].h, compra ? 233 : 234, cor, ok ? 3 : 1,
        compra ? ANCHOR_TOP : ANCHOR_BOTTOM);
}

//--- Tudo o que a barra i fechada mostra; apaga o que saiu da janela.
void DesenhaBarra(int i, const Pivo &piv[], int p, int sinal)
{
   DesenhaMedias(i);
   DesenhaPivo(i, piv, p);
   DesenhaSinal(i, piv, p, sinal);
   if(i >= GR_BARRAS_MAX) ObjectsDeleteAll(0, NomeObj(i - GR_BARRAS_MAX, ""));
}

//--- Entrada enviada na confirmação i: limite e stop durante a validade (3 barras).
void DesenhaEntrada(int i, double limite, double stop, int validade)
{
   if(!g_desenha) return;
   datetime t0 = g_barras[i].t + SEG_BARRA, t1 = g_barras[i].t + (validade + 1) * SEG_BARRA;
   Segmento(NomeObj(i, "limite"), t0, limite, t1, limite, COR_LIMITE, 2, STYLE_DASH);
   Segmento(NomeObj(i, "stop_ini"), t0, stop, t1, stop, COR_STOP, 1, STYLE_DASH);
}

//--- Stop da posição valendo na barra seguinte à i.
void DesenhaStop(int i, double stop)
{
   if(!g_desenha || stop <= 0) return;
   datetime t0 = g_barras[i].t + SEG_BARRA;
   Segmento(NomeObj(i, "stop"), t0, stop, t0 + SEG_BARRA, stop, COR_STOP, 2);
}

#endif
