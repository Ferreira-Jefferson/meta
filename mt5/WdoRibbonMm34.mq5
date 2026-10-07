//+------------------------------------------------------------------+
//| WdoRibbonMm34.mq5                                                   |
//| Porte MQL5 de src/strategy/daytrade/lab/wdo_ribbon_mm34.py          |
//|                                                                      |
//| Ribbon de 4 MMs (SMA/EMA/SMMA/LWMA) a `Periodo`, calculadas SO' COM  |
//| O FECHAMENTO DO PROPRIO PREGAO (reiniciadas toda abertura -- 2026-  |
//| 09-29, a pedido do dono, reintroduzido apos resolver o bug do        |
//| indicador visual -- ver ALTERNATIVAS mais abaixo). SMA/LWMA sao      |
//| janela movel (nao carregam nada de ontem a partir da vela Periodo    |
//| do pregao); EMA/SMMA sao recursivas mas semeadas pela SMA na 1a vela |
//| em que da' pra fechar o periodo inteiro, exatamente como o MT5       |
//| semeia o iMA nativo, so' que reiniciando o "inicio da serie" a cada  |
//| pregao em vez de usar o historico continuo. O ribbon so' fica valido |
//| (e o robo so' comeca a avaliar entrada) a partir da vela Periodo+1   |
//| (35, com Periodo=34) do pregao -- antes disso nao ha' referencia     |
//| real: era o problema do ribbon "encolhido" na abertura, com residuo  |
//| do fechamento de ontem, que abria operacao sem base nenhuma logo    |
//| nas primeiras velas do dia.                                          |
//| M1 e' fixo de proposito -- ja' confirmado que a estrategia e' para  |
//| 1 minuto, testar outro grafico nao faz sentido aqui.                |
//|                                                                      |
//| Vela "limpa" = a vela INTEIRA (corpo E pavio, maxima e minima)      |
//| acima da MM mais alta (compra) ou abaixo da mais baixa (venda) --   |
//| nem o pavio pode encostar no ribbon (2026-09-29, a pedido do dono). |
//| COMPRA: N verdes limpas -> EXATAMENTE 1 vermelha limpa -> verde     |
//| limpa seguinte dispara (2 vermelhas seguidas queimam a onda). Venda |
//| e' o espelho. 1 operacao por onda: lado trava apos a entrada ate'   |
//| um fechamento voltar para dentro do ribbon.                         |
//| Cancela a espera se qualquer vela (corpo OU pavio) encostar numa MM,|
//| OU se uma MM cruzar outra CONTRA o lado (compra: rapida fura p/    |
//| baixo da lenta),                                                    |
//| OU se as 4 MMs pararem de apontar a favor em alguma vela da espera  |
//| (da 1a a favor ate' o gatilho). Gatilho reprovado queima a onda.    |
//| MaxOndasDia: so' as N primeiras entradas do pregao (o ribbon        |
//| degrada depois de varias ondas no mesmo dia). RangeMaxAntesEntrada: |
//| bloqueia se o range acumulado do pregao ja' passou disso.           |
//|                                                                      |
//| Entrada: sempre a mercado (nao ha' caminho de ordem-limite real     |
//| para ela nesta estrategia -- decisao do dono, 2026-09-29).          |
//| So' para WDO@ -- testado no WIN@ e descartado (RangeMaxAntesEntrada |
//| e' calibrado em pontos absolutos do WDO; o range diario do WIN e'   |
//| ~77x maior, o filtro trava a entrada o dia inteiro todo dia).       |
//| Stop: >= StopAlemDaMM da MM mais proxima (compra: MM mais alta -    |
//| StopAlemDaMM; venda: MM mais baixa + StopAlemDaMM), reposicionado a |
//| cada fechamento e so' aperta. Alvo fixo = o tamanho do CORPO        |
//| (abertura-fechamento, pavio NAO conta) da VELA DO GATILHO, SEM      |
//| multiplo (entrada +/- esse tamanho, 1 pra 1), nao se move depois    |
//| (2026-09-29: trocado do "25x largura do ribbon" a pedido do dono,   |
//| pra observar o comportamento -- essa troca especifica ja' tinha     |
//| sido medida e perdido do alvo por ribbon em todo multiplo testado,  |
//| ver a memoria do projeto; entra mesmo assim, e' decisao do dono).   |
//| Zera a partir de HoraZerar:MinutoZerar.                             |
//|                                                                      |
//| TipoSaida escolhe COMO o stop e o alvo saem depois de abertos:      |
//|  - A_MERCADO (padrao): SL/TP nativos da posicao. Disparam e a       |
//|    corretora executa a mercado -- rapido e garantido, mas pode      |
//|    perder 1 tick de preco no alvo (ja' medido em outro robo: ~90%   |
//|    das saidas por alvo nativo deslizam contra a posicao).           |
//|  - A_LIMITE: duas ordens PARADAS NO LIVRO -- uma stop-limite pro    |
//|    stop, uma limite pura pro alvo. Se preencherem, preenchem no     |
//|    preco exato (sem deslize); mas podem demorar ou nunca preencher  |
//|    se o preco nao voltar la'. A que nao preencher e' cancelada      |
//|    assim que a outra fechar a posicao (ver LimparSaidasOrfas).      |
//|                                                                      |
//| ALTERNATIVAS JA TESTADAS E REJEITADAS (nao reintroduzir sem medir   |
//| de novo -- numeros e datas em wdo_ribbon_mm34_recorde_2026_09_29    |
//| na memoria do projeto):                                             |
//|  - Alvo fixo em multiplo do risco inicial (entrada-stop): perde do  |
//|    alvo pela largura do ribbon em quase todos os multiplos.         |
//|  - Filtro "MMs em ordem" (empilhadas por velocidade LWMA>EMA>SMA>   |
//|    SMMA no gatilho): dominava o resultado DENTRO da amostra (ago/   |
//|    2026) mas quase nao sobrevivia FORA dela (set/2026) -- overfit.  |
//|  - Sem filtro de alinhamento nenhum: pior que os dois de cima nos   |
//|    dois periodos testados.                                          |
//|  - Stop fixo (na vela contraria, ou parado onde nasceu na MM, sem   |
//|    trailing): piora muito -- o trailing e' o que sustenta o alvo    |
//|    distante, deixando a operacao boa correr.                        |
//|  - (SUPERADO em 2026-09-29) Exigir o PAVIO inteiro fora do ribbon:  |
//|    tinha sido medido como pior (corta operacoes boas, atrasa entrada|
//|    nas ruins) -- reintroduzido mesmo assim a pedido explicito do     |
//|    dono, agora e' o comportamento PADRAO (ver "Vela limpa" acima).   |
//|  - (SUPERADO em 2026-09-29) MMs continuas via iMA nativo (historico |
//|    ininterrupto entre pregoes): causava ribbon "encolhido" residual |
//|    do fechamento de ontem logo na abertura, permitindo entrada sem  |
//|    referencia real do pregao (flagrado pelo dono numa imagem real). |
//|    1a tentativa de trocar por MMs so' do pregao (mesmo dia) quebrou |
//|    o indicador visual companheiro (bug de alinhamento de array no   |
//|    OnCalculate dele -- nao deste EA, que nunca usou OnCalculate) e   |
//|    foi revertida temporariamente pra depurar. Bug isolado e         |
//|    corrigido no indicador (CopyTime/CopyClose em vez de confiar no  |
//|    array de entrada do OnCalculate); MMs so'-do-pregao reintroduzidas|
//|    aqui e no indicador, desta vez pra ficar (ver acima).             |
//+------------------------------------------------------------------+
#property copyright "wdo_ribbon_mm34"
#property version   "1.77"
#property strict

#include <Trade\Trade.mqh>

enum ETipoSaida { SAIDA_A_MERCADO, SAIDA_A_LIMITE };

input int    Periodo             = 34;    // Tamanho das 4 medias moveis (mantenha 34 = igual ao grafico que voce olha)
input double StopAlemDaMM        = 0.0;   // Pontos de folga do stop alem da media mais proxima (0 = grudado nela)
input int    MaxOndasDia         = 3;     // Maximo de operacoes que o robo abre por dia (0 = sem limite)
input double RangeMaxAntesEntrada = 65.0; // Para de abrir operacao se o dia ja andou mais que isso em pontos (0 = nunca para por isso)
input double Lote                = 1.0;   // Quantos contratos o robo compra/vende por operacao
input double TickSizeWdo         = 0.5;   // Tick minimo do WDO -- NAO mude (o MT5 relata errado sozinho pra WIN@/WDO@)
input int    HoraZerar           = 18;    // Hora que o robo fecha tudo e para de operar pelo resto do dia (junto com o minuto abaixo)
input int    MinutoZerar         = 20;    // Minuto (junto com a hora acima) em que o robo fecha tudo e para
input ulong  MagicNumber         = 34340001; // Codigo que identifica as ordens deste robo -- nao precisa mudar
input double LimiteEquity        = 0.0;   // So' no Testador: para o teste inteiro se o patrimonio cair ate' aqui ou menos (protege contra deixar a conta "zerada" continuar operando na simulacao)
input ETipoSaida TipoSaida       = SAIDA_A_MERCADO; // Como o stop e o alvo saem: MERCADO = disparam e saem na hora, podem perder um tiquinho de preco; LIMITE = ficam parados no livro esperando o preco exato, sem perder preco mas podem nao sair

CTrade trade;

datetime g_dia_atual = 0;

// series do PREGAO ATUAL (reiniciadas em cada abertura) usadas pra montar
// as 4 MMs so' com dado de hoje -- indice 0 = 1a vela fechada do pregao
double g_fechamentos_dia[];
double g_sma_dia[], g_ema_dia[], g_smma_dia[], g_lwma_dia[];

enum ELado { LADO_NENHUM, LADO_LONG, LADO_SHORT };
enum EFase { FASE_NENHUMA, FASE_TENDENCIA, FASE_CONTRARIA };
ELado    g_lado = LADO_NENHUM;
EFase    g_fase = FASE_NENHUMA;
double   g_medias_referencia[4];  // valores das 4 MMs na 1a vela da espera
bool     g_travado_long = false;  // 1 operacao por onda
bool     g_travado_short = false;
bool     g_sempre_apontando = true;  // as 4 MMs apontaram a favor em toda vela da espera
int      g_entradas_hoje = 0;        // contagem de entradas JA' FEITAS no pregao atual
double   g_dia_high = 0.0, g_dia_low = 0.0;  // maxima/minima acumuladas do pregao atual
bool     g_dia_tem_range = false;

// usados so' quando TipoSaida = SAIDA_A_LIMITE
ulong    g_ticket_alvo = 0;   // ticket da ordem-limite do alvo
ulong    g_ticket_stop = 0;   // ticket da ordem stop-limite do stop
double   g_stop_rastreado = 0.0;  // preco do stop atual (espelha POSITION_SL, que fica zerado neste modo)

int      g_handle_visual = INVALID_HANDLE;  // so' pra desenhar o ribbon no grafico -- o EA nao le os buffers dele

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   g_ticket_alvo = 0;
   g_ticket_stop = 0;
   ChartSetInteger(0, CHART_SHOW_GRID, false);

   // carrega o indicador visual (WdoRibbonMm34Indicador) sozinho, so' pra
   // ele aparecer no grafico enquanto o EA roda -- nao precisa anexar nada
   // na mao. So' cosmetico: se falhar (arquivo nao compilado/nao achado),
   // o EA continua normalmente, so' fica sem o desenho do ribbon.
   // Pulado em otimizacao/backtest sem visual (ninguem olha o grafico ali).
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_VISUAL_MODE))
   {
      g_handle_visual = iCustom(_Symbol, PERIOD_M1, "WdoRibbonMm34Indicador", Periodo);
      if(g_handle_visual == INVALID_HANDLE)
         PrintFormat("indicador visual WdoRibbonMm34Indicador nao carregou (so' cosmetico, EA continua): %d", GetLastError());
   }

   PrintFormat("WdoRibbonMm34 v1.77 -- MMs so' com fechamento do proprio pregao (validas a partir da vela %d), vela limpa exige pavio inteiro fora do ribbon, stop encostado na MM (+%.1f pt), MMs apontando a favor na espera, max %d ondas/dia, range max %.1f pt antes da entrada, alvo = corpo da vela do gatilho (sem pavio, sem multiplo), saida %s, zera %02d:%02d",
               Periodo + 1, StopAlemDaMM, MaxOndasDia, RangeMaxAntesEntrada,
               (TipoSaida == SAIDA_A_MERCADO ? "A_MERCADO" : "A_LIMITE"), HoraZerar, MinutoZerar);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(g_handle_visual != INVALID_HANDLE) IndicatorRelease(g_handle_visual);
}

//+------------------------------------------------------------------+
bool IsNewBar()
{
   static datetime ultima_barra = 0;
   datetime barra_atual = iTime(_Symbol, PERIOD_M1, 0);
   if(barra_atual != ultima_barra)
   {
      ultima_barra = barra_atual;
      return true;
   }
   return false;
}

// acrescenta o fechamento da barra ao pregao atual e recalcula as 4 MMs so'
// com dado de hoje. SMA/LWMA sao janela movel (dependem so' dos ultimos
// `Periodo` fechamentos, entao ficam automaticamente "so' de hoje" assim
// que o pregao acumula esse tanto). EMA/SMMA sao recursivas: semeadas pela
// SMA na 1a vela em que o periodo fecha inteiro (indice Periodo-1), e dai
// em diante evoluidas so' com fechamento de hoje -- exatamente como o MT5
// semeia o iMA nativo, so' que reiniciando a semente a cada pregao.
void AtualizarMediasDia(double fechamento)
{
   int n = ArraySize(g_fechamentos_dia);
   ArrayResize(g_fechamentos_dia, n + 1);
   ArrayResize(g_sma_dia,  n + 1);
   ArrayResize(g_ema_dia,  n + 1);
   ArrayResize(g_smma_dia, n + 1);
   ArrayResize(g_lwma_dia, n + 1);
   g_fechamentos_dia[n] = fechamento;

   if(n < Periodo - 1) return;  // ainda nao da' pra fechar nem a 1a media do dia

   double soma = 0.0, soma_pond = 0.0, soma_pesos = 0.0;
   for(int w = 1; w <= Periodo; w++)
   {
      double c = g_fechamentos_dia[n - Periodo + w];
      soma       += c;
      soma_pond  += c * w;
      soma_pesos += w;
   }
   g_sma_dia[n]  = soma / Periodo;
   g_lwma_dia[n] = soma_pond / soma_pesos;

   if(n == Periodo - 1)
   {
      g_ema_dia[n]  = g_sma_dia[n];
      g_smma_dia[n] = g_sma_dia[n];
   }
   else
   {
      double k = 2.0 / (Periodo + 1);
      g_ema_dia[n]  = fechamento * k + g_ema_dia[n - 1] * (1.0 - k);
      g_smma_dia[n] = (g_smma_dia[n - 1] * (Periodo - 1) + fechamento) / Periodo;
   }
}

// as 4 MMs apontam para o lado: todas subiram (compra) / cairam (venda) desde a vela anterior
bool MediasApontam(ELado lado, const double &atual[], const double &antes[])
{
   for(int i = 0; i < 4; i++)
   {
      if(lado == LADO_LONG  && !(atual[i] > antes[i])) return false;
      if(lado == LADO_SHORT && !(atual[i] < antes[i])) return false;
   }
   return true;
}

//+------------------------------------------------------------------+
// rapidez de cada MM (0=SMA,1=EMA,2=SMMA,3=LWMA): LWMA > EMA > SMA > SMMA
int VELOCIDADE[4] = { 1, 2, 0, 3 };

// cruzamento CONTRA o lado: na compra, uma MM mais rapida que estava acima de
// uma mais lenta passou para baixo dela; na venda, o espelho. A favor nao conta.
bool CruzouContra(ELado lado, const double &ref[], const double &atual[])
{
   for(int i = 0; i < 4; i++)
      for(int j = 0; j < 4; j++)
      {
         if(VELOCIDADE[i] <= VELOCIDADE[j]) continue;
         if(lado == LADO_LONG  && ref[i] > ref[j] && atual[i] < atual[j]) return true;
         if(lado == LADO_SHORT && ref[i] < ref[j] && atual[i] > atual[j]) return true;
      }
   return false;
}

//+------------------------------------------------------------------+
double NoTick(double preco)
{
   return NormalizeDouble(MathRound(preco / TickSizeWdo) * TickSizeWdo, _Digits);
}
// stop sempre a PELO MENOS StopAlemDaMM da MM: arredonda para longe dela
double StopCompra(double mm) { return NormalizeDouble(MathFloor((mm - StopAlemDaMM) / TickSizeWdo + 1e-9) * TickSizeWdo, _Digits); }
double StopVenda(double mm)  { return NormalizeDouble(MathCeil((mm + StopAlemDaMM) / TickSizeWdo - 1e-9) * TickSizeWdo, _Digits); }

//+------------------------------------------------------------------+
bool TemPosicaoAberta(ENUM_POSITION_TYPE &tipo, double &stop_atual)
{
   if(!PositionSelect(_Symbol)) return false;
   if(PositionGetInteger(POSITION_MAGIC) != (long)MagicNumber) return false;
   tipo = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   stop_atual = PositionGetDouble(POSITION_SL);
   return true;
}

void ResetRegime()
{
   g_lado = LADO_NENHUM;
   g_fase = FASE_NENHUMA;
}

//+------------------------------------------------------------------+
// ----- abertura de posicao: uma funcao por tipo de saida -----------
//+------------------------------------------------------------------+

// TipoSaida = A_MERCADO: abre com SL/TP anexados na propria posicao
bool AbrirAMercado(ELado lado, double stop, double alvo)
{
   bool ok = (lado == LADO_LONG)
      ? trade.Buy(Lote, _Symbol, 0.0, stop, alvo, "wdo_ribbon_mm34")
      : trade.Sell(Lote, _Symbol, 0.0, stop, alvo, "wdo_ribbon_mm34");
   if(ok) g_stop_rastreado = stop;
   return ok;
}

// arma as duas ordens paradas no livro depois que a posicao ja' abriu:
// uma limite pura no alvo, uma stop-limite no stop
void ColocarSaidasLimite(ELado lado, double stop, double alvo)
{
   bool ok_alvo = (lado == LADO_LONG)
      ? trade.SellLimit(Lote, alvo, _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, "wdo_ribbon_mm34 alvo")
      : trade.BuyLimit(Lote, alvo, _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, "wdo_ribbon_mm34 alvo");
   g_ticket_alvo = ok_alvo ? trade.ResultOrder() : 0;
   if(!ok_alvo)
      PrintFormat("alvo-limite FALHOU: preco=%.3f retcode=%d (%s)", alvo, trade.ResultRetcode(), trade.ResultRetcodeDescription());

   ENUM_ORDER_TYPE tipo_stop = (lado == LADO_LONG) ? ORDER_TYPE_SELL_STOP_LIMIT : ORDER_TYPE_BUY_STOP_LIMIT;
   bool ok_stop = trade.OrderOpen(_Symbol, tipo_stop, Lote, stop, stop, 0.0, 0.0, ORDER_TIME_GTC, 0, "wdo_ribbon_mm34 stop");
   g_ticket_stop = ok_stop ? trade.ResultOrder() : 0;
   if(!ok_stop)
      PrintFormat("stop-limite FALHOU: preco=%.3f retcode=%d (%s)", stop, trade.ResultRetcode(), trade.ResultRetcodeDescription());

   g_stop_rastreado = stop;
}

// TipoSaida = A_LIMITE: abre a posicao SEM protecao nativa (sl=0,tp=0) e
// em seguida arma as duas ordens paradas no livro
bool AbrirALimite(ELado lado, double stop, double alvo)
{
   bool ok = (lado == LADO_LONG)
      ? trade.Buy(Lote, _Symbol, 0.0, 0.0, 0.0, "wdo_ribbon_mm34")
      : trade.Sell(Lote, _Symbol, 0.0, 0.0, 0.0, "wdo_ribbon_mm34");
   if(!ok)
   {
      PrintFormat("entrada a limite FALHOU: retcode=%d (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return false;
   }
   ColocarSaidasLimite(lado, stop, alvo);
   return true;
}

bool AbrirPosicao(ELado lado, double stop, double alvo)
{
   return (TipoSaida == SAIDA_A_MERCADO) ? AbrirAMercado(lado, stop, alvo) : AbrirALimite(lado, stop, alvo);
}

//+------------------------------------------------------------------+
// ----- trailing (aperta o stop a cada fechamento): uma funcao por tipo
//+------------------------------------------------------------------+

// TipoSaida = A_MERCADO: reenvia o SL/TP da posicao (TP nao muda)
void AtualizarStopMercado(double stop_atual, double candidato)
{
   if(!trade.PositionModify(_Symbol, candidato, PositionGetDouble(POSITION_TP)))
      PrintFormat("trailing FALHOU: stop_atual=%.3f candidato=%.3f retcode=%d (%s)",
                  stop_atual, candidato, trade.ResultRetcode(), trade.ResultRetcodeDescription());
   else
      g_stop_rastreado = candidato;
}

// TipoSaida = A_LIMITE: move o preco de gatilho E o preco-limite da mesma
// ordem stop-limite (OrderModify aceita os dois numa chamada so')
void AtualizarStopLimite(double candidato)
{
   if(g_ticket_stop == 0) return;
   if(!trade.OrderModify(g_ticket_stop, candidato, 0.0, 0.0, ORDER_TIME_GTC, 0, candidato))
      PrintFormat("trailing (limite) FALHOU: candidato=%.3f retcode=%d (%s)",
                  candidato, trade.ResultRetcode(), trade.ResultRetcodeDescription());
   else
      g_stop_rastreado = candidato;
}

// so' chama quando ha' posicao aberta: calcula o candidato a novo stop e
// despacha para a funcao de trailing certa, so' se o novo stop for mais
// apertado que o atual (o stop nunca afrouxa)
void AtualizarStopSePreciso(ENUM_POSITION_TYPE tipo_posicao, double ribbon_max, double ribbon_min)
{
   double stop_atual = (TipoSaida == SAIDA_A_MERCADO) ? PositionGetDouble(POSITION_SL) : g_stop_rastreado;
   double candidato;
   bool aperta;
   if(tipo_posicao == POSITION_TYPE_BUY)
   {
      candidato = StopCompra(ribbon_max);
      aperta = (candidato > stop_atual);
   }
   else
   {
      candidato = StopVenda(ribbon_min);
      aperta = (candidato < stop_atual);
   }
   if(!aperta) return;
   if(TipoSaida == SAIDA_A_MERCADO) AtualizarStopMercado(stop_atual, candidato);
   else                             AtualizarStopLimite(candidato);
}

//+------------------------------------------------------------------+
// TipoSaida = A_LIMITE: quando uma das duas ordens (alvo/stop) preenche e
// fecha a posicao, a OUTRA fica parada no livro sem posicao nenhuma para
// proteger -- cancela ela e destrava a onda. Chamada em TODO tick (nao so'
// em barra nova) para nao deixar a ordem orfa exposta por muito tempo.
void LimparSaidasOrfas()
{
   if(g_ticket_alvo == 0 && g_ticket_stop == 0) return;
   if(PositionSelect(_Symbol) && PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber)
      return; // posicao ainda aberta, as duas ordens continuam validas
   if(g_ticket_alvo != 0 && OrderSelect(g_ticket_alvo)) trade.OrderDelete(g_ticket_alvo);
   if(g_ticket_stop != 0 && OrderSelect(g_ticket_stop)) trade.OrderDelete(g_ticket_stop);
   g_ticket_alvo = 0;
   g_ticket_stop = 0;
}

//+------------------------------------------------------------------+
void ProcessarBarraFechada()
{
   MqlRates barra[];
   if(CopyRates(_Symbol, PERIOD_M1, 1, 1, barra) < 1) return;
   datetime ts = barra[0].time;
   double abertura = barra[0].open;
   double fechamento = barra[0].close;

   // novo pregao: zera a espera e as travas de onda (as MMs NAO resetam)
   MqlDateTime dt_barra;
   TimeToStruct(ts, dt_barra);
   datetime dia_da_barra = StringToTime(StringFormat("%04d.%02d.%02d", dt_barra.year, dt_barra.mon, dt_barra.day));
   if(dia_da_barra != g_dia_atual)
   {
      g_dia_atual = dia_da_barra;
      ResetRegime();
      g_travado_long = false;
      g_travado_short = false;
      g_entradas_hoje = 0;
      g_dia_tem_range = false;
      ArrayResize(g_fechamentos_dia, 0);
      ArrayResize(g_sma_dia, 0);
      ArrayResize(g_ema_dia, 0);
      ArrayResize(g_smma_dia, 0);
      ArrayResize(g_lwma_dia, 0);
   }

   if(!g_dia_tem_range) { g_dia_high = barra[0].high; g_dia_low = barra[0].low; g_dia_tem_range = true; }
   else { g_dia_high = MathMax(g_dia_high, barra[0].high); g_dia_low = MathMin(g_dia_low, barra[0].low); }

   AtualizarMediasDia(fechamento);
   int n = ArraySize(g_fechamentos_dia);
   if(n < Periodo + 1) return;  // ribbon ainda nao valido -- menos de Periodo+1 velas hoje

   double valores[4]    = { g_sma_dia[n - 1],  g_ema_dia[n - 1],  g_smma_dia[n - 1],  g_lwma_dia[n - 1] };
   double anteriores[4] = { g_sma_dia[n - 2],  g_ema_dia[n - 2],  g_smma_dia[n - 2],  g_lwma_dia[n - 2] };
   double ribbon_max = MathMax(MathMax(valores[0], valores[1]), MathMax(valores[2], valores[3]));
   double ribbon_min = MathMin(MathMin(valores[0], valores[1]), MathMin(valores[2], valores[3]));

   if(fechamento <= ribbon_max) g_travado_long = false;
   if(fechamento >= ribbon_min) g_travado_short = false;

   ENUM_POSITION_TYPE tipo_posicao;
   double stop_atual;
   if(TemPosicaoAberta(tipo_posicao, stop_atual))
   {
      AtualizarStopSePreciso(tipo_posicao, ribbon_max, ribbon_min);
      return;
   }

   bool verde    = fechamento > abertura;
   bool vermelha = fechamento < abertura;

   ELado lado;
   bool a_favor, contra;
   double ref;
   if(barra[0].low > ribbon_max)  // vela INTEIRA (corpo E pavio) acima do ribbon
   {
      lado = LADO_LONG; a_favor = verde; contra = vermelha; ref = ribbon_max;
   }
   else if(barra[0].high < ribbon_min)  // vela INTEIRA (corpo E pavio) abaixo do ribbon
   {
      lado = LADO_SHORT; a_favor = vermelha; contra = verde; ref = ribbon_min;
   }
   else
   {
      // vela (corpo OU pavio) encostou em alguma MM -> cancela qualquer espera
      ResetRegime();
      return;
   }

   if(g_lado != lado || (g_lado != LADO_NENHUM && CruzouContra(lado, g_medias_referencia, valores)))
      ResetRegime();

   bool travado = (lado == LADO_LONG) ? g_travado_long : g_travado_short;
   if(g_fase == FASE_NENHUMA)
   {
      if(a_favor && !travado)
      {
         g_lado = lado;
         g_fase = FASE_TENDENCIA;
         ArrayCopy(g_medias_referencia, valores);
         g_sempre_apontando = MediasApontam(lado, valores, anteriores);
      }
      return;
   }
   g_sempre_apontando = g_sempre_apontando && MediasApontam(lado, valores, anteriores);
   if(g_fase == FASE_TENDENCIA)
   {
      if(contra) g_fase = FASE_CONTRARIA;
      return;
   }
   if(contra)
   {
      // segunda contraria seguida queima a onda: sem entrada ate' voltar ao ribbon
      ResetRegime();
      if(lado == LADO_LONG) g_travado_long = true; else g_travado_short = true;
      return;
   }
   if(!a_favor) return;
   if(!g_sempre_apontando)
   {
      // gatilho com MMs desalinhadas: nao opera esta onda
      ResetRegime();
      if(lado == LADO_LONG) g_travado_long = true; else g_travado_short = true;
      return;
   }
   if(MaxOndasDia > 0 && g_entradas_hoje >= MaxOndasDia)
   {
      // ja' passou do numero de ondas permitido no pregao: nao opera mais hoje
      ResetRegime();
      if(lado == LADO_LONG) g_travado_long = true; else g_travado_short = true;
      return;
   }
   if(RangeMaxAntesEntrada > 0.0 && (g_dia_high - g_dia_low) >= RangeMaxAntesEntrada)
   {
      // pregao ja' esta' agitado demais ate' aqui: nao opera esta onda
      ResetRegime();
      if(lado == LADO_LONG) g_travado_long = true; else g_travado_short = true;
      return;
   }

   ResetRegime();
   g_entradas_hoje++;
   double distancia = MathAbs(fechamento - abertura);  // alvo = tamanho do corpo da vela do gatilho, sem multiplo
   double stop = (lado == LADO_LONG) ? StopCompra(ref) : StopVenda(ref);
   double alvo = (lado == LADO_LONG) ? NoTick(fechamento + distancia) : NoTick(fechamento - distancia);
   if(lado == LADO_LONG) g_travado_long = true; else g_travado_short = true;
   if(!AbrirPosicao(lado, stop, alvo))
      PrintFormat("entrada %s falhou: stop=%.3f alvo=%.3f retcode=%d (%s)",
                  (lado == LADO_LONG ? "BUY" : "SELL"), stop, alvo, trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void ZerarPregao()
{
   if(TipoSaida == SAIDA_A_LIMITE)
   {
      if(g_ticket_alvo != 0 && OrderSelect(g_ticket_alvo)) trade.OrderDelete(g_ticket_alvo);
      if(g_ticket_stop != 0 && OrderSelect(g_ticket_stop)) trade.OrderDelete(g_ticket_stop);
      g_ticket_alvo = 0;
      g_ticket_stop = 0;
   }
   ENUM_POSITION_TYPE tipo; double sl;
   if(TemPosicaoAberta(tipo, sl) && !trade.PositionClose(_Symbol))
      PrintFormat("zeragem FALHOU: retcode=%d (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   ResetRegime();
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(MQLInfoInteger(MQL_TESTER) && AccountInfoDouble(ACCOUNT_EQUITY) <= LimiteEquity)
   {
      PrintFormat("Conta zerada (equity=%.2f <= limite=%.2f) em %s -- parando o teste",
                  AccountInfoDouble(ACCOUNT_EQUITY), LimiteEquity, TimeToString(TimeCurrent()));
      TesterStop();
      return;
   }
   if(TipoSaida == SAIDA_A_LIMITE) LimparSaidasOrfas();
   if(!IsNewBar()) return;
   MqlDateTime agora;
   TimeToStruct(TimeCurrent(), agora);
   if(agora.hour * 60 + agora.min >= HoraZerar * 60 + MinutoZerar)
   {
      // fim do pregao: nunca dorme posicionado e nao abre nada novo
      ZerarPregao();
      return;
   }
   ProcessarBarraFechada();
}
//+------------------------------------------------------------------+
