//+------------------------------------------------------------------+
//| CriarTemplateRibbon.mq5                                             |
//| Anexa o WdoRibbonMm34Indicador ao grafico atual e salva o template  |
//| "ribbon.tpl" -- rode UMA VEZ num grafico WDO normal; depois use     |
//| Graficos > Templates (modelos) > Carregar modelo > ribbon dentro    |
//| da janela do Strategy Tester Visualization pra ver as 4 MMs la.     |
//+------------------------------------------------------------------+
#property copyright "wdo_ribbon_mm34"
#property version   "1.00"
#property script_show_inputs

void OnStart()
{
   int handle = iCustom(_Symbol, _Period, "WdoRibbonMm34Indicador");
   if(handle == INVALID_HANDLE)
   {
      Print("Erro ao criar o indicador WdoRibbonMm34Indicador: ", GetLastError());
      return;
   }
   if(!ChartIndicatorAdd(0, 0, handle))
   {
      Print("Erro ao anexar o indicador ao grafico: ", GetLastError());
      return;
   }
   if(ChartSaveTemplate(0, "ribbon"))
      Print("OK -- template 'ribbon.tpl' salvo. Use Graficos > Templates > Carregar modelo > ribbon.");
   else
      Print("Erro ao salvar o template: ", GetLastError());
}
//+------------------------------------------------------------------+
