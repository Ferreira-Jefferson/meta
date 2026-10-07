//+------------------------------------------------------------------+
//| WinSeletor/WinRetanguloEma34.mqh
//| WinRetanguloEma34 v1.07: retangulo M1->M15 ajustado, filtro EMA34, filtro de amplitude 0,5 ATR, regra NaoOperarGapATR.
//|
//| Modulo do WinMaestro.mq5 v2.00, copiado de WinSeletor/WinRetanguloEma34.mqh. A logica de SINAL
//| e' a mesma; so' a camada de execucao mudou (desenho v2.2 sec. 7, spec Apendice A):
//|  - o modulo escreve a INTENCAO: ArmarEntrada -> ENTRAR(limite, S pre-calculada);
//|    ENTRADA_EXECUTADA -> MANTER(stop reancorado, alvo) (era DetectarPreenchimentoEntrada);
//|    AproximarAlvo -> MANTER(alvo novo); LimparAlvoOrfao e ZerarPregao sairam (L2 e corte do
//|    maestro), o reset do estado na zeragem fica;
//|  - o fill tardio de uma entrada ja' cancelada e' adotado pelos niveis guardados por id_entrada;
//|  - entrada e alvo DAY (B1/B2) no lugar de GTC (o maestro manda as ordens);
//|  - TesterStop por equity desligado (RE_LimiteEquity saiu); o Deinit nao cancela a entrada;
//|  - hora = v.agora (no lugar de TimeCurrent); decisao anterior a' partida = DECISAO PERDIDA;
//|  - estado persistido como instantes (Apendice A).
//| Adaptacoes marcadas com "WinMaestro:" (as "WinSeletor:" sao da copia anterior).
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_RETANGULOEMA34_MQH
#define WINMAESTRO_RETANGULOEMA34_MQH

namespace WRE
{

// ---- inputs do EA original (mesmos nomes e padroes), preenchidos por Configura() ----
int JanelaBarras = 20;
double ToleranciaBorda = 0.20;
double AlvoFracaoLargura = 0.90;
double StopFracaoLargura = 0.45;
int TtlBarrasEntrada = 10;
double LarguraMinimaPontos = 328.0;
int PeriodoEma = 34;
int AlvoAproximaBarras = 5;
double AlvoAproximaPasso = 0.10;
double AlvoPisoFracao = 0.50;
const double Lote = 1.0;   // WinMaestro: lote fixo 1 (input removido, spec 1)
double TickSizeWin = 5.0;
int HoraZerar = 17;
int MinutoZerar = 0;
int HoraInicio = 9;
int MinutoInicio = 1;
double RangeMaximoBarraPontos = 2000.0;
double FiltroAmplitudeATR = 0.5;
double NaoOperarGapATR = 1.0;

// WinMaestro: o maestro e' o unico dono das saidas por horario (spec 9.1); a zeragem abaixo so' arruma o estado do robo.
bool MaestroDonoHorario = true;

void Configura()
{
   JanelaBarras = RE_JanelaBarras;
   ToleranciaBorda = RE_ToleranciaBorda;
   AlvoFracaoLargura = RE_AlvoFracaoLargura;
   StopFracaoLargura = RE_StopFracaoLargura;
   TtlBarrasEntrada = RE_TtlBarrasEntrada;
   LarguraMinimaPontos = RE_LarguraMinimaPontos;
   PeriodoEma = RE_PeriodoEma;
   AlvoAproximaBarras = RE_AlvoAproximaBarras;
   AlvoAproximaPasso = RE_AlvoAproximaPasso;
   AlvoPisoFracao = RE_AlvoPisoFracao;
   TickSizeWin = RE_TickSizeWin;
   HoraZerar = RE_HoraZerar;
   MinutoZerar = RE_MinutoZerar;
   HoraInicio = RE_HoraInicio;
   MinutoInicio = RE_MinutoInicio;
   RangeMaximoBarraPontos = RE_RangeMaximoBarraPontos;
   FiltroAmplitudeATR = RE_FiltroAmplitudeATR;
   NaoOperarGapATR = RE_NaoOperarGapATR;
}

// ---------------------------- logica original ----------------------------
// v1.05: tempo grafico FIXO no codigo (padrao do dono), nao e' input -- detector, EMA, novo-barra e aproximacao do alvo
const ENUM_TIMEFRAMES TempoGrafico = PERIOD_M15;
// v1.05 ajuste B: o corte de entrada antes da zeragem nunca passa disto (minutos)
#define CORTE_ENTRADA_MAX_MIN 60
//: constantes do detector -- congeladas, herdadas do win_retangulo (adimensionais, nao viram input de proposito)
#define TOQUES_MINIMOS      2
#define VISITAS_MINIMAS     2
#define CRUZAMENTOS_MINIMOS 3
#define CONTENCAO_MINIMA    0.95
#define CONTRACAO_MAXIMA    0.55
#define ESPALHAMENTO_MINIMO (1.0/3.0)
#define DERIVA_MAXIMA       0.25
//: piso ESTRUTURAL de largura em ticks do WIN@ (win_retangulo.py: LARGURA_MINIMA_TICKS = 6.0)
#define LARGURA_MINIMA_TICKS 6.0
#define MARGEM_MORTE         0.25
#define BARRAS_MORTE         3

enum ELadoRetangulo { RET_NENHUM, RET_LONG, RET_SHORT };

datetime g_dia_atual = 0;
int      g_handle_ema = INVALID_HANDLE;

// historico de velas validas (v1.05: NAO reinicia na virada do dia -- atravessa pregoes; guarda so' as ultimas 3 x JanelaBarras)
double   g_high_dia[], g_low_dia[], g_close_dia[];
datetime g_time_dia[];

// retangulo detectado no momento (valido so' se g_tem_retangulo)
bool     g_tem_retangulo = false;
double   g_topo = 0.0, g_piso = 0.0, g_largura = 0.0, g_meio = 0.0;
datetime g_retangulo_inicio_ts = 0; // hora da 1a barra da janela que gerou o retangulo -- so' pro desenho
int      g_fora_seguidas = 0;

//: nomes fixos -- so' existe 1 retangulo por vez nesta instancia (1 simbolo, 1 grafico)
#define OBJ_NOME_CAIXA "WinRetEma_Caixa"
#define OBJ_NOME_MEIO  "WinRetEma_Meio"

// limite de ENTRADA pendente
bool             g_ordem_pendente = false;
ulong            g_ticket_entrada = 0;
int              g_barras_esperando = 0;
ELadoRetangulo   g_lado_entrada = RET_NENHUM;
double           g_meio_original = 0.0, g_stop_original = 0.0, g_alvo_original = 0.0;
datetime         g_vela_entrada = 0;    // WinMaestro: vela M15 que armou a entrada (instante; recalcula g_barras_esperando)
long             g_id = 0;              // WinMaestro: id_entrada da entrada armada
// WinMaestro: a entrada anterior (para adotar um fill que chegou depois de a E ter sido cancelada e rearmada)
// WinMaestro (M-6): as ultimas entradas armadas antes da atual, num anel de 4 (um K sem desfecho pode atravessar mais de
// um rearme), para adotar o fill tardio de qualquer uma delas com os niveis dela.
#define RE_ANEL 4
long             g_anel_id[RE_ANEL];
int              g_anel_lado[RE_ANEL];
double           g_anel_meio[RE_ANEL], g_anel_stop[RE_ANEL], g_anel_alvo[RE_ANEL];
int              g_anel_pos = 0;
// WinMaestro (M-6): fill que chegou com a ficha ainda nao LEGITIMA (trocada, duplicada, absorvida): fica pendente e e'
// adotado no primeiro Tick com a posicao propria.
long             g_fill_id = 0;
double           g_fill_preco = 0.0;
datetime         g_fill_hora = 0;
datetime         g_agora = 0;           // WinMaestro: relogio da vista (v.agora), no lugar de TimeCurrent()
datetime Agora() { return g_agora; }

// limite de ALVO (saida), armada so' depois que a entrada preenche
ulong g_ticket_alvo = 0;

// alvo que se aproxima (G37): estado da posicao aberta
double   g_preco_entrada = 0.0, g_largura_posicao = 0.0, g_frac_alvo_atual = 0.0;
datetime g_barra_do_fill = 0;
int      g_barras_posicao = 0;

// v1.05: o historico de velas e' pre-carregado uma vez, na 1a vela processada
bool     g_historico_carregado = false;

// v1.06: abertura da ultima vela que passou por ProcessarBarraFechada (para trocar a vela pos-pregao
// pela ultima vela da sessao ainda nao processada) e cache diario do ATR14 D1 do filtro f3
datetime g_ultima_vela_processada = 0;
datetime g_atr_dia = 0;
double   g_atr_d1 = 0.0;
bool     g_atr_ok = false;

//+------------------------------------------------------------------+
// minutos de uma vela do TempoGrafico (M15 -> 15)
int MinutosVela()
{
   return PeriodSeconds(TempoGrafico) / 60;
}

// v1.05 ajuste B: nao arma entrada nos ultimos min((TTL+1) x vela, 60) minutos antes da zeragem
int CorteEntradaMinutos()
{
   return (int)MathMin((TtlBarrasEntrada + 1) * MinutosVela(), CORTE_ENTRADA_MAX_MIN);
}

// v1.05 ajuste C: a amplitude normal de uma vela cresce com a raiz do tempo dela,
// entao o limite de vela anomala e' o de referencia (M1) x raiz(minutos da vela)
double RangeMaximoEfetivo()
{
   return RangeMaximoBarraPontos * MathSqrt((double)MinutosVela());
}

// filtros de vela valida (os mesmos para o pre-carregamento e para a vela fechada):
// abre a partir de HoraInicio:MinutoInicio (fora do leilao) e faixa dentro do limite
bool VelaNoLeilao(datetime ts)
{
   MqlDateTime dt;
   TimeToStruct(ts, dt);
   return (dt.hour * 60 + dt.min < HoraInicio * 60 + MinutoInicio);
}

bool VelaAnomala(double high, double low)
{
   return (RangeMaximoBarraPontos > 0.0 && (high - low) > RangeMaximoEfetivo());
}

// meia-noite (servidor) do dia de `ts`
datetime InicioDoDia(datetime ts)
{
   return ts - (ts % 86400);
}

// v1.06: fim da sessao de negociacao do dia de `ts`, em minutos desde 00:00. Vem de SymbolInfoSessionTrade
// (fim da ultima sessao do dia da semana); se nao vier, ou vier fora de [zeragem, 18:30], usa 18:25.
#define FIM_SESSAO_FALLBACK_MIN (18 * 60 + 25)
// WinMaestro: o cache era `static` local; virou global do modulo para voltar ao inicial no Reseta() (P17).
int g_fs_dia_semana_cache = -1, g_fs_fim_cache = FIM_SESSAO_FALLBACK_MIN;
int FimSessaoMinutos(datetime ts)
{
   MqlDateTime dt;
   TimeToStruct(ts, dt);
   if(dt.day_of_week == g_fs_dia_semana_cache) return g_fs_fim_cache;
   int fim = -1;
   datetime de, ate;
   for(uint i = 0; i < 10; i++)
   {
      if(!SymbolInfoSessionTrade(_Symbol, (ENUM_DAY_OF_WEEK)dt.day_of_week, i, de, ate)) break;
      int m = (int)((ulong)ate % 86400) / 60;
      if((ulong)ate >= 86400) m = 24 * 60;   // sessao ate' 24:00
      if(m > fim) fim = m;
   }
   int usado = (fim >= HoraZerar * 60 + MinutoZerar && fim <= 18 * 60 + 30) ? fim : FIM_SESSAO_FALLBACK_MIN;
   PrintFormat("fim da sessao (%s, dia da semana %d): %s -> usando %02d:%02d para ignorar velas pos-pregao",
               _Symbol, dt.day_of_week, (fim < 0 ? "nao informado" : StringFormat("%02d:%02d", fim / 60, fim % 60)),
               usado / 60, usado % 60);
   g_fs_dia_semana_cache = dt.day_of_week;
   g_fs_fim_cache = usado;
   return usado;
}

// v1.06: vela que ABRE no fim da sessao ou depois (ex.: o tick isolado das 18:30 do WIN$N)
bool VelaPosPregao(datetime ts)
{
   MqlDateTime dt;
   TimeToStruct(ts, dt);
   return (dt.hour * 60 + dt.min >= FimSessaoMinutos(ts));
}

// v1.06 (f3): ATR14 D1 dos pregoes ANTERIORES ao dia `dia0` -- media simples do True Range dos 14 ultimos
// pregoes, com cada pregao montado das velas M1 (maxima, minima, ultimo fechamento), igual ao port_z4.
// Calculado uma vez por dia.
bool AtrD1Anterior(datetime dia0, double &out_atr)
{
   if(dia0 == g_atr_dia) { out_atr = g_atr_d1; return g_atr_ok; }
   g_atr_dia = dia0;
   g_atr_ok = false;
   g_atr_d1 = 0.0;
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, dia0 - 45 * 86400, dia0 - 1, r);
   double dh[], dl[], dc[];
   int nd = 0;
   datetime d_ant = 0;
   for(int i = 0; i < n; i++)
   {
      datetime d = InicioDoDia(r[i].time);
      if(d >= dia0) break;
      if(nd == 0 || d != d_ant)
      {
         nd++;
         ArrayResize(dh, nd); ArrayResize(dl, nd); ArrayResize(dc, nd);
         dh[nd - 1] = r[i].high; dl[nd - 1] = r[i].low;
         d_ant = d;
      }
      if(r[i].high > dh[nd - 1]) dh[nd - 1] = r[i].high;
      if(r[i].low  < dl[nd - 1]) dl[nd - 1] = r[i].low;
      dc[nd - 1] = r[i].close;
   }
   if(nd >= 15)
   {
      double soma = 0.0;
      for(int k = nd - 14; k < nd; k++)
         soma += MathMax(dh[k] - dl[k], MathMax(MathAbs(dh[k] - dc[k - 1]), MathAbs(dl[k] - dc[k - 1])));
      g_atr_d1 = soma / 14.0;
      g_atr_ok = (g_atr_d1 > 0.0);
   }
   if(!g_atr_ok)
      PrintFormat("%s ATR14 D1 indisponivel (%d pregoes M1 anteriores lidos, preciso de 15) -- filtro de amplitude bloqueia o dia",
                  TimeToString(dia0, TIME_DATE), nd);
   out_atr = g_atr_d1;
   return g_atr_ok;
}

// v1.06 (f3): true = pode armar. Decisao no fim da vela M15 `ts_vela` (abertura + 15 min); amplitude =
// maxima - minima das M1 do dia com abertura <= decisao - 1 min. Bloqueio nao muda estado nenhum.
bool FiltroAmplitudeLibera(datetime ts_vela)
{
   if(FiltroAmplitudeATR <= 0.0) return true;
   datetime decisao = ts_vela + PeriodSeconds(TempoGrafico);
   datetime dia0 = InicioDoDia(ts_vela);
   double atr = 0.0;
   bool atr_ok = AtrD1Anterior(dia0, atr);
   double hs[], ls[];
   int nh = CopyHigh(_Symbol, PERIOD_M1, dia0, decisao - 60, hs);
   int nl = CopyLow (_Symbol, PERIOD_M1, dia0, decisao - 60, ls);
   if(nh < 1 || nl < 1 || !atr_ok)
   {
      PrintFormat("%s entrada BLOQUEADA (filtro amplitude): sem dado (M1 do dia=%d, ATR ok=%s)",
                  TimeToString(decisao), nh, (atr_ok ? "sim" : "nao"));
      return false;
   }
   double amplitude = hs[ArrayMaximum(hs, 0, nh)] - ls[ArrayMinimum(ls, 0, nl)];
   if(amplitude >= FiltroAmplitudeATR * atr) return true;
   PrintFormat("%s entrada BLOQUEADA (filtro amplitude): amplitude do pregao %.0f pts < %.2f x ATR14 D1 %.1f = %.1f pts (%.3f ATR)",
               TimeToString(decisao), amplitude, FiltroAmplitudeATR, atr, FiltroAmplitudeATR * atr, amplitude / atr);
   return false;
}

//+------------------------------------------------------------------+
//| REGRA NaoOperarGapATR (Z8, 2026-10-06) -- BLOCO IDENTICO nos 5   |
//| EAs do WIN (Win, Win_c1, WinCincoMedias, WinDeslocamentoMatinal, |
//| WinRetanguloEma34). Copiado de proposito, sem include: mudar aqui|
//| = mudar nos 5. Referencia Python: comparativo_win_2026/          |
//| filtro_gap.py (mesma definicao de combinacoes/z7_dias_extremos/  |
//| z7.py).                                                          |
//|  - Dia BLOQUEADO: |abertura do pregao - fechamento do pregao     |
//|    anterior| >= NaoOperarGapATR x ATR14 D1. Nao abre posicao nova|
//|    no dia; saidas seguem normais.                                |
//|  - Diarias montadas das velas M1 com abertura <= 18:25 (abertura |
//|    = 1a M1 do dia, maxima, minima, ultimo fechamento).           |
//|  - ATR14 D1 = media SIMPLES do True Range dos 14 pregoes         |
//|    ANTERIORES (nada do dia corrente).                            |
//|  - Simbolo CONTINUO (nome com '$' ou '@': WIN$N, WIN@, WIN$): no |
//|    dia do vencimento (4a-feira mais proxima do dia 15 dos meses  |
//|    pares; sem pregao nele, o 1o pregao ate' 3 dias depois) a     |
//|    serie troca de contrato: o gap NAO bloqueia e o True Range    |
//|    desse dia vale so' a amplitude (ignora o salto). Num contrato |
//|    especifico (WINV26...) nao ha salto: sem exclusao, TR completo|
//|  - Decide no 1o tick do pregao (com a 1a vela M1 do dia ja'      |
//|    formada) e guarda o resultado ate' o dia virar.               |
//+------------------------------------------------------------------+
long g_gap_dia_avaliado = -1;    // dia (TimeCurrent / 86400) ja' avaliado
bool g_gap_bloqueado    = false; // resultado do dia avaliado

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime GapVencimentoWIN(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime t15 = StructToTime(d);
   TimeToStruct(t15, d);
   int dif = 3 - d.day_of_week;           // 3 = quarta
   if(dif > 3) dif -= 7;
   if(dif < -3) dif += 7;
   return t15 + dif * 86400;
}

// Serie continua (troca de contrato no vencimento): nome com '$' ou '@'.
bool GapSimboloContinuo()
{
   return StringFind(_Symbol, "$") >= 0 || StringFind(_Symbol, "@") >= 0;
}

// `dia` (00:00) e' o 1o pregao em/apos um vencimento, ate' 3 dias depois; `dia_ant` = pregao anterior.
bool GapDiaDeRolagem(datetime dia, datetime dia_ant)
{
   MqlDateTime d; TimeToStruct(dia, d);
   int ano = d.year, mes = d.mon;
   for(int k = 0; k < 2; k++)             // vencimento deste mes e do mes anterior
   {
      if(mes % 2 == 0)
      {
         datetime v = GapVencimentoWIN(ano, mes);
         if(v > dia_ant && v <= dia && dia - v < 4 * 86400) return true;
      }
      mes--; if(mes == 0) { mes = 12; ano--; }
   }
   return false;
}

// true = hoje NAO abre posicao nova. Avalia uma vez por dia; chame em todo tick (o 1o tick do pregao decide).
bool GapDiaBloqueado()
{
   if(NaoOperarGapATR <= 0.0) return false;
   datetime agora = Agora();               // WinMaestro: era TimeCurrent()
   long dia_n = (long)(agora / 86400);
   if(dia_n == g_gap_dia_avaliado) return g_gap_bloqueado;
   datetime dia0 = (datetime)(dia_n * 86400);
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, dia0 - 45 * 86400, agora, r);
   if(n < 1 || r[n - 1].time < dia0) return false;   // ainda sem vela M1 de hoje: decide no proximo tick
   datetime dd[];
   double   dO[], dH[], dL[], dC[];
   int nd = 0;
   for(int i = 0; i < n; i++)
   {
      MqlDateTime t; TimeToStruct(r[i].time, t);
      if(t.hour * 60 + t.min > 18 * 60 + 25) continue;          // so' velas M1 com abertura <= 18:25
      datetime d = (datetime)((long)(r[i].time / 86400) * 86400);
      if(nd == 0 || d != dd[nd - 1])
      {
         nd++;
         ArrayResize(dd, nd); ArrayResize(dO, nd); ArrayResize(dH, nd); ArrayResize(dL, nd); ArrayResize(dC, nd);
         dd[nd - 1] = d; dO[nd - 1] = r[i].open; dH[nd - 1] = r[i].high; dL[nd - 1] = r[i].low;
      }
      if(r[i].high > dH[nd - 1]) dH[nd - 1] = r[i].high;
      if(r[i].low  < dL[nd - 1]) dL[nd - 1] = r[i].low;
      dC[nd - 1] = r[i].close;
   }
   g_gap_dia_avaliado = dia_n;
   g_gap_bloqueado = false;
   if(nd < 16 || dd[nd - 1] != dia0)
   {
      PrintFormat("NaoOperarGapATR: %s sem historico para o ATR14 D1 (%d pregoes M1 lidos, preciso de 15 + hoje) -- dia liberado",
                  TimeToString(dia0, TIME_DATE), nd);
      return false;
   }
   bool continuo = GapSimboloContinuo();
   double soma = 0.0;
   for(int k = nd - 15; k <= nd - 2; k++)                        // 14 pregoes anteriores a hoje
   {
      double amp = dH[k] - dL[k];
      double tr = MathMax(amp, MathMax(MathAbs(dH[k] - dC[k - 1]), MathAbs(dL[k] - dC[k - 1])));
      if(continuo && GapDiaDeRolagem(dd[k], dd[k - 1])) tr = amp;  // salto da troca de contrato nao e' volatilidade
      soma += tr;
   }
   double atr = soma / 14.0;
   double gap = dO[nd - 1] - dC[nd - 2];
   if(atr <= 0.0) return false;
   if(MathAbs(gap) < NaoOperarGapATR * atr) return false;
   if(continuo && GapDiaDeRolagem(dd[nd - 1], dd[nd - 2]))
   {
      PrintFormat("NaoOperarGapATR: %s gap %.0f pts = %.2f ATR, mas e' dia de vencimento numa serie continua (%s): troca de contrato, dia liberado",
                  TimeToString(dia0, TIME_DATE), gap, MathAbs(gap) / atr, _Symbol);
      return false;
   }
   g_gap_bloqueado = true;
   PrintFormat("Dia bloqueado: gap %.0f pts = %.2f ATR (abertura %.0f, fechamento anterior %.0f, ATR14 D1 %.1f, limite %.2f ATR) -- sem entrada nova hoje",
               gap, MathAbs(gap) / atr, dO[nd - 1], dC[nd - 2], atr, NaoOperarGapATR);
   return true;
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
int InitBase()
{
   if(JanelaBarras < 6)
   {
      PrintFormat("JanelaBarras=%d curto demais: o espalhamento exige W/3 barras entre 1a e ultima visita de cada borda", JanelaBarras);
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(!(ToleranciaBorda > 0.0 && ToleranciaBorda < 0.5))
   {
      PrintFormat("ToleranciaBorda=%.4f fora de (0; 0,5): acima de 0,5 as duas bordas se encontram no meio", ToleranciaBorda);
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(AlvoFracaoLargura <= 0.0 || StopFracaoLargura <= 0.0)
   {
      Print("AlvoFracaoLargura e StopFracaoLargura tem de ser distancias positivas");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(AlvoFracaoLargura < 2.0 * StopFracaoLargura - 1e-9)
      PrintFormat("AVISO: AlvoFracaoLargura=%.2f < 2x StopFracaoLargura=%.2f -- fora do piso de razao do mandato do dono (perda>=ganho proibido)",
                  AlvoFracaoLargura, StopFracaoLargura);
   if(TtlBarrasEntrada <= 0)
   {
      Print("TtlBarrasEntrada e' obrigatorio: limite de entrada sem prazo vira ordem esquecida no livro (medido: fill 269,7 min depois do sinal)");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(PeriodoEma < 2)
   {
      Print("PeriodoEma precisa ser >= 2");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(AlvoAproximaBarras > 0 && AlvoPisoFracao <= StopFracaoLargura)
   {
      PrintFormat("AlvoPisoFracao=%.2f <= StopFracaoLargura=%.2f: o alvo chegaria a ficar menor ou igual ao stop (perda>=ganho proibido)",
                  AlvoPisoFracao, StopFracaoLargura);
      return(INIT_PARAMETERS_INCORRECT);
   }

   g_handle_ema = iMA(_Symbol, TempoGrafico, PeriodoEma, 0, MODE_EMA, PRICE_CLOSE);
   if(g_handle_ema == INVALID_HANDLE)
   {
      Print("Falha ao criar o indicador EMA (iMA) -- abortando");
      return(INIT_FAILED);
   }

   g_ticket_entrada = 0;
   g_ticket_alvo = 0;

   // WinSeletor: aviso de periodo do grafico removido (o modulo calcula em M15, qualquer grafico serve).

   PrintFormat("WinRetanguloEma34 v1.06 M15 ajustado + filtro amplitude >= %.2f x ATR14 D1 (0 = desligado) (alvo aproxima a cada %d velas, passo %.2f, piso %.2f) -- timeframe %s, janela %d velas entre dias, tolerancia borda %.2f, alvo %.2fxL, stop %.2fxL, EMA%d, "
               "ttl entrada %d velas, corte de entrada %d min antes da zeragem, descarte de vela > %.0f pts, piso largura max(%.1f ticks estrutural; %.1f pontos empirico), zera %02d:%02d -- "
               "ATENCAO: o filtro melhora 2022-2024 e piora 2025-2026, NAO e' validada para dinheiro real",
               FiltroAmplitudeATR, AlvoAproximaBarras, AlvoAproximaPasso, AlvoPisoFracao, EnumToString(TempoGrafico), JanelaBarras, ToleranciaBorda, AlvoFracaoLargura, StopFracaoLargura, PeriodoEma,
               TtlBarrasEntrada, CorteEntradaMinutos(), RangeMaximoEfetivo(), LARGURA_MINIMA_TICKS, LarguraMinimaPontos, HoraZerar, MinutoZerar);
   return(INIT_SUCCEEDED);
}

void DeinitBase(const int reason)
{
   if(g_handle_ema != INVALID_HANDLE) IndicatorRelease(g_handle_ema);
}

//+------------------------------------------------------------------+
datetime g_nb_ultima = 0;
bool IsNewBar()
{
   datetime barra_atual = iTime(_Symbol, TempoGrafico, 0);
   if(barra_atual != g_nb_ultima)   // WinSeletor: era `static ultima_barra`; agora zera em Reseta()
   {
      g_nb_ultima = barra_atual;
      return true;
   }
   return false;
}

double NoTick(double preco)
{
   return NormalizeDouble(MathRound(preco / TickSizeWin) * TickSizeWin, _Digits);
}

// WinMaestro: a posicao do robo e' a ficha dele.
bool TemPosicaoPropria()
{
   return Ficha_Tem(R_RE);
}

// EMA do fechamento da ultima barra FECHADA (shift 1 -- mesma barra que
// decide o lado do retangulo). false se o indicador ainda nao tem valor
// (poucas barras de historico, raro fora do 1o minuto do backtest).
bool ValorEma(double &out_ema)
{
   double buf[];
   if(CopyBuffer(g_handle_ema, 0, 1, 1, buf) < 1) return false;
   out_ema = buf[0];
   return true;
}

//+------------------------------------------------------------------+
// ----- desenho: so' visual, o EA nunca LE estes objetos de volta ---
//+------------------------------------------------------------------+

void DesenharRetangulo(datetime ts)
{
   if(ObjectFind(0, OBJ_NOME_CAIXA) < 0)
   {
      ObjectCreate(0, OBJ_NOME_CAIXA, OBJ_RECTANGLE, 0, g_retangulo_inicio_ts, g_topo, ts, g_piso);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_FILL, false);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_BACK, true);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, OBJ_NOME_CAIXA, OBJPROP_HIDDEN, true);

      ObjectCreate(0, OBJ_NOME_MEIO, OBJ_TREND, 0, g_retangulo_inicio_ts, g_meio, ts, g_meio);
      ObjectSetInteger(0, OBJ_NOME_MEIO, OBJPROP_COLOR, clrYellow);
      ObjectSetInteger(0, OBJ_NOME_MEIO, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, OBJ_NOME_MEIO, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, OBJ_NOME_MEIO, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, OBJ_NOME_MEIO, OBJPROP_HIDDEN, true);
   }
   else
   {
      ObjectMove(0, OBJ_NOME_CAIXA, 1, ts, g_piso);
      ObjectMove(0, OBJ_NOME_MEIO,  1, ts, g_meio);
   }
}

void ApagarRetangulo()
{
   ObjectDelete(0, OBJ_NOME_CAIXA);
   ObjectDelete(0, OBJ_NOME_MEIO);
}

//+------------------------------------------------------------------+
// ----- detector de retangulo (puro: arrays entram, retangulo sai) --
//+------------------------------------------------------------------+

double Quantile(const double &origem[], int n, double q)
{
   double copia[];
   ArrayResize(copia, n);
   for(int i = 0; i < n; i++) copia[i] = origem[i];
   ArraySort(copia);
   double pos = q * (n - 1);
   int lo = (int)MathFloor(pos);
   int hi = (int)MathCeil(pos);
   if(lo == hi) return copia[lo];
   double frac = pos - lo;
   return copia[lo] + frac * (copia[hi] - copia[lo]);
}

int Visitas(const int &pos[], int n)
{
   int visitas = 1;
   for(int i = 0; i < n - 1; i++)
      if(pos[i + 1] - pos[i] > 1) visitas++;
   return visitas;
}

bool DetectaRetangulo(const double &high[], const double &low[], const double &close[], int n,
                       double tolerancia, double amplitude_anterior, bool tem_amplitude_anterior,
                       double &out_topo, double &out_piso, double &out_largura, double &out_meio)
{
   double topo = Quantile(high, n, 0.90);
   double piso = Quantile(low,  n, 0.10);
   double largura = topo - piso;
   if(largura <= 0.0) return false;
   double meio = (topo + piso) / 2.0;
   double zona = tolerancia * largura;

   int pos_topo[], pos_piso[], lados[];
   ArrayResize(pos_topo, n); ArrayResize(pos_piso, n); ArrayResize(lados, n);
   int n_topo = 0, n_piso = 0, n_lados = 0;
   for(int i = 0; i < n; i++)
   {
      if(high[i] >= topo - zona)      { lados[n_lados++] = 1;  pos_topo[n_topo++] = i; }
      else if(low[i] <= piso + zona)  { lados[n_lados++] = -1; pos_piso[n_piso++] = i; }
   }
   if(n_topo < TOQUES_MINIMOS || n_piso < TOQUES_MINIMOS) return false;

   int visitas_topo = Visitas(pos_topo, n_topo);
   int visitas_piso = Visitas(pos_piso, n_piso);
   if(visitas_topo < VISITAS_MINIMAS || visitas_piso < VISITAS_MINIMAS) return false;

   double minimo = ESPALHAMENTO_MINIMO * n;
   if((pos_topo[n_topo - 1] - pos_topo[0]) < minimo || (pos_piso[n_piso - 1] - pos_piso[0]) < minimo) return false;

   int trocas = 0;
   for(int i = 0; i < n_lados - 1; i++) if(lados[i] != lados[i + 1]) trocas++;
   if(trocas < 2) return false;

   int cruzamentos = 0;
   bool acima_ant = close[0] > meio;
   for(int i = 1; i < n; i++)
   {
      bool acima = close[i] > meio;
      if(acima != acima_ant) cruzamentos++;
      acima_ant = acima;
   }
   if(cruzamentos < CRUZAMENTOS_MINIMOS) return false;

   int dentro = 0;
   for(int i = 0; i < n; i++) if(close[i] >= piso && close[i] <= topo) dentro++;
   double contencao = (double)dentro / n;
   if(contencao < CONTENCAO_MINIMA) return false;

   int terco = n / 3;
   double soma1 = 0.0, soma2 = 0.0;
   for(int i = 0; i < terco; i++) soma1 += close[i];
   for(int i = n - terco; i < n; i++) soma2 += close[i];
   double primeiro = soma1 / terco;
   double ultimo   = soma2 / terco;
   if(MathAbs(ultimo - primeiro) > DERIVA_MAXIMA * largura) return false;

   if(tem_amplitude_anterior && amplitude_anterior > 0.0)
   {
      double contracao = largura / amplitude_anterior;
      if(contracao > CONTRACAO_MAXIMA) return false;
   }

   out_topo = topo; out_piso = piso; out_largura = largura; out_meio = meio;
   return true;
}

//+------------------------------------------------------------------+
// ----- estado de sessao / historico do dia -------------------------
//+------------------------------------------------------------------+

// WinMaestro: cancelar = intencao NADA (o maestro cancela a E). O estado de espera e' limpo como no original
// (o modulo pode rearmar na mesma vela); os niveis da entrada ficam guardados por id para adotar um fill tardio.
void CancelarEntradaPendente(Intencao &ped)
{
   if(g_ordem_pendente && ped.tipo == INT_ENTRAR && ped.id_entrada == g_id)
      Int_Nada(ped, "win_retangulo_ema34: cancela entrada");
   g_ordem_pendente = false;
   g_ticket_entrada = 0;
   g_barras_esperando = 0;
}

// virada do pregao: zera o RETANGULO ativo e a ordem de entrada pendente.
// v1.05 (ajuste A): o historico de velas NAO e' zerado -- a janela atravessa
// dias. A EMA (iMA) tambem e' continua, igual ao `ewm` do backtest Python.
void ResetSessao(Intencao &ped)
{
   g_tem_retangulo = false;
   g_fora_seguidas = 0;
   CancelarEntradaPendente(ped);
   ApagarRetangulo();
}

void AcrescentarBarraDia(datetime ts, double high, double low, double close)
{
   int n = ArraySize(g_close_dia);
   // o detector so' le as ultimas 3 x JanelaBarras velas: descarta a mais antiga
   int maximo = 3 * JanelaBarras;
   if(n >= maximo)
   {
      int sobra = n - maximo + 1;
      for(int i = 0; i < n - sobra; i++)
      {
         g_high_dia[i]  = g_high_dia[i + sobra];
         g_low_dia[i]   = g_low_dia[i + sobra];
         g_close_dia[i] = g_close_dia[i + sobra];
         g_time_dia[i]  = g_time_dia[i + sobra];
      }
      n -= sobra;
   }
   ArrayResize(g_high_dia,  n + 1);
   ArrayResize(g_low_dia,   n + 1);
   ArrayResize(g_close_dia, n + 1);
   ArrayResize(g_time_dia,  n + 1);
   g_high_dia[n]  = high;
   g_low_dia[n]   = low;
   g_close_dia[n] = close;
   g_time_dia[n]  = ts;
}

// v1.05 (ajuste A): na 1a vela processada, enche o historico com as velas
// validas ANTERIORES a ela (mesmos filtros de leilao e de vela anomala), para
// o detector ja' ter a janela cheia no 1o pregao do teste.
#define VELAS_PRE_CARGA 600
// v1.06: carrega so' velas ANTERIORES a `ts_proc` (a vela que vai ser processada agora) e descarta tambem as
// velas pos-pregao, como o port sem pos-pregao
void CarregarHistorico(datetime ts_proc)
{
   g_historico_carregado = true;
   MqlRates r[];
   int n = CopyRates(_Symbol, TempoGrafico, 1, VELAS_PRE_CARGA + 1, r);
   int usadas = 0;
   for(int i = 0; i < n; i++)
   {
      if(r[i].time >= ts_proc) break;
      usadas++;
      if(VelaNoLeilao(r[i].time) || VelaPosPregao(r[i].time) || VelaAnomala(r[i].high, r[i].low)) continue;
      AcrescentarBarraDia(r[i].time, r[i].high, r[i].low, r[i].close);
   }
   PrintFormat("historico pre-carregado: %d velas validas de %d lidas", ArraySize(g_close_dia), usadas);
}

// v1.06: a vela FECHADA a processar agora. Normalmente a de shift 1; se ela abriu no fim da sessao ou depois
// (vela pos-pregao), troca pela ultima vela da sessao que ainda nao passou por aqui (no contrato real e' a das
// 18:15, que chega de manha). false = nada a processar.
bool VelaParaProcessar(MqlRates &out)
{
   MqlRates r[];
   if(CopyRates(_Symbol, TempoGrafico, 1, 1, r) < 1) return false;
   if(!VelaPosPregao(r[0].time)) { out = r[0]; return true; }
   MqlRates q[];
   int n = CopyRates(_Symbol, TempoGrafico, 2, 8, q);
   for(int i = n - 1; i >= 0; i--)
   {
      if(q[i].time <= g_ultima_vela_processada) break;
      if(VelaPosPregao(q[i].time)) continue;
      PrintFormat("%s vela pos-pregao ignorada; processando no lugar a vela %s", TimeToString(r[0].time), TimeToString(q[i].time));
      out = q[i];
      return true;
   }
   PrintFormat("%s vela pos-pregao ignorada", TimeToString(r[0].time));
   return false;
}

void TentaDetectar()
{
   int n = ArraySize(g_close_dia);
   int W = JanelaBarras;
   if(n < 3 * W) return;

   double high_rec[], low_rec[], close_rec[];
   ArrayResize(high_rec, W); ArrayResize(low_rec, W); ArrayResize(close_rec, W);
   int base = n - W;
   for(int i = 0; i < W; i++)
   {
      high_rec[i]  = g_high_dia[base + i];
      low_rec[i]   = g_low_dia[base + i];
      close_rec[i] = g_close_dia[base + i];
   }

   int desde = n - 3 * W;
   double hmax = g_high_dia[desde], lmin = g_low_dia[desde];
   for(int idx = desde + 1; idx < n - W; idx++)
   {
      if(g_high_dia[idx] > hmax) hmax = g_high_dia[idx];
      if(g_low_dia[idx]  < lmin) lmin = g_low_dia[idx];
   }
   double amplitude_anterior = hmax - lmin;

   double topo, piso, largura, meio;
   if(!DetectaRetangulo(high_rec, low_rec, close_rec, W, ToleranciaBorda, amplitude_anterior, true, topo, piso, largura, meio))
      return;
   if(largura < LARGURA_MINIMA_TICKS * TickSizeWin) return;
   if(largura < LarguraMinimaPontos) return;

   g_topo = topo; g_piso = piso; g_largura = largura; g_meio = meio;
   g_retangulo_inicio_ts = g_time_dia[base];
   g_tem_retangulo = true;
   g_fora_seguidas = 0;
}

bool Morreu(double fechamento)
{
   double margem = MARGEM_MORTE * g_largura;
   if(fechamento > g_topo + margem || fechamento < g_piso - margem)
   {
      g_fora_seguidas++;
      return (g_fora_seguidas >= BARRAS_MORTE);
   }
   g_fora_seguidas = 0;
   return false;
}

//+------------------------------------------------------------------+
// ----- ordens: entrada limite, ancoragem no preenchimento, alvo ----
//+------------------------------------------------------------------+

void ArmarEntrada(Intencao &ped, ELadoRetangulo lado, double limite, double stop, double alvo, datetime vela)
{
   // WinMaestro: momento = fechamento da vela; antes da partida = DECISAO PERDIDA (nada muda no estado).
   if(Ficha_DecisaoPerdida(R_RE, vela + PeriodSeconds(TempoGrafico), lado == RET_SHORT ? "entrada SHORT" : "entrada LONG")) return;
   // WinMaestro: guarda a entrada anterior (fill tardio) e pede ENTRAR DAY (B2) com a S pre-calculada em `stop` (spec 5.3).
   if(g_id != 0)
   {
      g_anel_id[g_anel_pos] = g_id; g_anel_lado[g_anel_pos] = (int)g_lado_entrada; g_anel_meio[g_anel_pos] = g_meio_original;
      g_anel_stop[g_anel_pos] = g_stop_original; g_anel_alvo[g_anel_pos] = g_alvo_original;
      g_anel_pos = (g_anel_pos + 1) % RE_ANEL;
   }
   g_id = Ficha_NovoId(R_RE);
   Int_Entrar(ped, g_id, lado == RET_SHORT ? -1 : 1, limite, stop, 0, "win_retangulo_ema34 entrada");
   g_ticket_entrada = 1;
   g_vela_entrada = vela;
   g_ordem_pendente = true;
   g_barras_esperando = 0;
   g_lado_entrada = lado;
   g_meio_original = limite;
   g_stop_original = stop;
   g_alvo_original = alvo;
}

// WinMaestro: chamado no evento ENTRADA_EXECUTADA (o preenchimento vem do maestro, nao da liquida).
void DetectarPreenchimentoEntrada(Intencao &ped, const double preco_fill, const datetime hora_fill)
{
   if(!TemPosicaoPropria()) return;

   double preco_preenchido = preco_fill;               // WinMaestro: preco do deal da E, nao a media da liquida
   double delta = preco_preenchido - g_meio_original;
   double stop_ancorado = NoTick(g_stop_original + delta);
   double alvo_ancorado = NoTick(g_alvo_original + delta);

   // WinMaestro: a S (pre-calculada na E) vai para o nivel reancorado e o alvo limite DAY nasce: MANTER(stop, alvo).
   Int_Manter(ped, stop_ancorado, alvo_ancorado, "win_retangulo_ema34 preenchida: stop reancorado e alvo");
   g_ticket_alvo = 1;

   g_preco_entrada = preco_preenchido;
   g_largura_posicao = MathAbs(alvo_ancorado - preco_preenchido) / AlvoFracaoLargura;
   g_frac_alvo_atual = AlvoFracaoLargura;
   g_barra_do_fill = iTime(_Symbol, TempoGrafico, iBarShift(_Symbol, TempoGrafico, hora_fill > 0 ? hora_fill : Agora()));   // WinMaestro: vela do fill (B-17)
   g_barras_posicao = 0;

   g_ordem_pendente = false;
   g_ticket_entrada = 0;
   g_barras_esperando = 0;
}

// G37: chamada uma vez por vela fechada. Conta so' velas que fecharam DEPOIS
// da vela do preenchimento (igual ao Python: o extremo da propria vela do
// fill pode ter acontecido antes dele). A cada AlvoAproximaBarras velas o
// alvo vem AlvoAproximaPasso x largura mais perto, ate' AlvoPisoFracao.
// Se o preco ja' passou do alvo novo, a limite vai para o melhor preco do
// nosso lado (bid na venda, ask na compra) e executa na hora -- continua
// sendo ordem-LIMITE (nunca pior que o preco pedido), nunca a mercado.
void AproximarAlvo(Intencao &ped)
{
   if(AlvoAproximaBarras <= 0 || g_ticket_alvo == 0 || g_largura_posicao <= 0.0) return;
   if(!TemPosicaoPropria()) return;
   if(iTime(_Symbol, TempoGrafico, 1) <= g_barra_do_fill) return;
   g_barras_posicao++;

   double frac = MathMax(AlvoFracaoLargura - AlvoAproximaPasso * (g_barras_posicao / AlvoAproximaBarras), AlvoPisoFracao);
   if(frac >= g_frac_alvo_atual - 1e-9) return;
   if(!Ficha_TemAlvo(R_RE)) return;                    // WinMaestro: o alvo vivo vem da vista

   bool comprado = (Ficha_Lado(R_RE) > 0);
   double novo = NoTick(comprado ? g_preco_entrada + frac * g_largura_posicao
                                 : g_preco_entrada - frac * g_largura_posicao);
   double preco = comprado ? MathMax(novo, SymbolInfoDouble(_Symbol, SYMBOL_BID))
                           : MathMin(novo, SymbolInfoDouble(_Symbol, SYMBOL_ASK));
   preco = NoTick(preco);

   // WinMaestro: MANTER(stop atual, alvo novo); o maestro faz o OrderModify (A2).
   Int_Manter(ped, ped.tipo == INT_MANTER ? ped.stop : Ficha_Stop(R_RE), preco, "win_retangulo_ema34 alvo se aproxima");
   g_frac_alvo_atual = frac;
}

// WinMaestro: LimparAlvoOrfao saiu (L2 do maestro cancela o alvo sem ficha).

// WinMaestro: ZerarPregao: o maestro cancela E e A e zera a ficha (I3 no horario do robo); aqui so' o estado
// do robo volta ao inicial (o reset de g_ticket_alvo fica, desenho sec. 7).
void ZerarPregao(Intencao &ped)
{
   if(ped.tipo == INT_ENTRAR) Int_Nada(ped, "win_retangulo_ema34: zeragem");
   g_ordem_pendente = false; g_ticket_entrada = 0; g_barras_esperando = 0;
   g_ticket_alvo = 0;
   g_tem_retangulo = false;
   ApagarRetangulo();
}

//+------------------------------------------------------------------+
void ProcessarBarraFechada(Intencao &ped)
{
   MqlRates barra[1];
   if(!VelaParaProcessar(barra[0])) return;
   if(!g_historico_carregado) CarregarHistorico(barra[0].time);
   g_ultima_vela_processada = barra[0].time;
   datetime ts = barra[0].time;
   double fechamento = barra[0].close;

   // novo pregao: zera o RETANGULO e a entrada pendente; o historico de velas
   // e a EMA continuam (ver ResetSessao). A ultima vela do dia anterior chega
   // aqui no 1o tick do dia seguinte e conta como vela do dia anterior.
   MqlDateTime dt_barra;
   TimeToStruct(ts, dt_barra);
   datetime dia_da_barra = StringToTime(StringFormat("%04d.%02d.%02d", dt_barra.year, dt_barra.mon, dt_barra.day));
   if(dia_da_barra != g_dia_atual)
   {
      g_dia_atual = dia_da_barra;
      ResetSessao(ped);
   }

   // pula o leilao de abertura -- cotacoes indicativas (nao negociaveis) do
   // B3 entre ~08:55 e a abertura de verdade podem oscilar dezenas de MIL
   // pontos numa so' vela (medido direto nos ticks reais: ate' 17.335 pts
   // de vai-e-vem so' no bid entre 08:55 e 09:01 de um unico pregao) --
   // deixar isso entrar na janela do retangulo infla `largura` e produz
   // stop/alvo a dezenas de milhares de pontos de distancia, uma posicao
   // que nunca mais encontra o proprio risco. So' comeca a contar vela
   // a partir de HoraInicio:MinutoInicio.
   if(VelaNoLeilao(ts)) return;

   // rede de seguranca extra: qualquer vela (de qualquer horario) com faixa
   // maior que RangeMaximoEfetivo() = RangeMaximoBarraPontos x raiz(minutos
   // da vela) e' tratada como tick ruim e descartada do historico -- nao
   // participa da deteccao do retangulo nem de nada mais. 0 = desligado.
   if(VelaAnomala(barra[0].high, barra[0].low))
   {
      PrintFormat("%s vela descartada: faixa=%.0f pts > limite=%.0f (provavel tick ruim)",
                  TimeToString(ts), barra[0].high - barra[0].low, RangeMaximoEfetivo());
      return;
   }

   AcrescentarBarraDia(ts, barra[0].high, barra[0].low, fechamento);

   if(g_tem_retangulo && Morreu(fechamento))
   {
      g_tem_retangulo = false;
      CancelarEntradaPendente(ped);
      ApagarRetangulo();
   }
   if(!g_tem_retangulo)
   {
      TentaDetectar();
      if(!g_tem_retangulo) return;
   }
   DesenharRetangulo(ts);

   if(TemPosicaoPropria()) return;

   if(g_ordem_pendente)
   {
      g_barras_esperando++;
      if(g_barras_esperando < TtlBarrasEntrada) return;
      CancelarEntradaPendente(ped);
   }

   double meio = g_meio, largura = g_largura;
   ELadoRetangulo lado; double alvo, stop;
   if(fechamento < meio)
   {
      lado = RET_SHORT;
      alvo = meio - AlvoFracaoLargura * largura;
      stop = meio + StopFracaoLargura * largura;
   }
   else if(fechamento > meio)
   {
      lado = RET_LONG;
      alvo = meio + AlvoFracaoLargura * largura;
      stop = meio - StopFracaoLargura * largura;
   }
   else
   {
      return;
   }

   // FILTRO DA G29: so' passa do lado certo da EMA (fechamento da mesma
   // vela que decidiu o lado acima). Sem EMA pronta (raro, so' no inicio
   // do historico), nao arrisca sem o filtro -- mesma regra do Python
   // (`_ema_em` retorna None -> `on_bar` devolve [] / nao arma).
   double ema;
   if(!ValorEma(ema)) return;
   if(lado == RET_LONG  && fechamento < ema) return;
   if(lado == RET_SHORT && fechamento > ema) return;

   // nao arma entrada perto da zeragem: corte = min((TTL+1) x vela, 60 min)
   // antes de HoraZerar:MinutoZerar (v1.05 ajuste B; no M15 = a partir das 16:00)
   if(dt_barra.hour * 60 + dt_barra.min >= HoraZerar * 60 + MinutoZerar - CorteEntradaMinutos()) return;

   double limite = NoTick(meio);
   if(lado == RET_SHORT && limite <= fechamento) return;
   if(lado == RET_LONG  && limite >= fechamento) return;

   // v1.06 (f3): so' arma se o pregao ja' andou (amplitude ate' a decisao >= FiltroAmplitudeATR x ATR14 D1).
   // Bloqueio nao muda estado: na proxima vela tenta de novo.
   // v1.07 (Z8): dia bloqueado pelo gap nao arma (nao muda estado nenhum).
   if(GapDiaBloqueado()) { PrintFormat("%s entrada %s nao armada: dia bloqueado pelo gap (NaoOperarGapATR)", TimeToString(ts), lado == RET_LONG ? "COMPRA" : "VENDA"); return; }
   if(!FiltroAmplitudeLibera(ts)) return;

   ArmarEntrada(ped, lado, limite, NoTick(stop), NoTick(alvo), ts);
}

//+------------------------------------------------------------------+
void Tick(const VistaRobo &v, Intencao &ped)
{
   g_agora = v.agora;   // WinMaestro: o relogio da vista
   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)
   // WinMaestro: o TesterStop por equity (RE_LimiteEquity) saiu: pararia os cinco robos (spec 1).
   // WinMaestro: DetectarPreenchimentoEntrada vem no evento ENTRADA_EXECUTADA; LimparAlvoOrfao saiu (L2).
   // WinMaestro (M-6): fill que chegou sem a posicao propria (ficha trocada/duplicada: modulo suspenso, sem Tick) e' adotado
   // no primeiro Tick com a posicao. Regra de saida: um Tick SEM a posicao descarta o fill (a posicao dele nao existe mais:
   // foi corrigida a 0 ou absorvida), entao ele nunca e' aplicado a uma posicao posterior.
   if(g_fill_id != 0)
   {
      if(TemPosicaoPropria() && AdotaNiveis(g_fill_id)) DetectarPreenchimentoEntrada(ped, g_fill_preco, g_fill_hora);
      g_fill_id = 0;
   }
   // WinMaestro (B-17): sem posicao, o estado do alvo velho volta ao inicial (era o LimparAlvoOrfao).
   if(!TemPosicaoPropria() && g_ticket_alvo != 0) { g_ticket_alvo = 0; g_largura_posicao = 0.0; }
   if(!IsNewBar()) return;
   MqlDateTime agora;
   TimeToStruct(Agora(), agora);
   if(agora.hour * 60 + agora.min >= HoraZerar * 60 + MinutoZerar)
   {
      ZerarPregao(ped);
      return;
   }
   AproximarAlvo(ped);
   ProcessarBarraFechada(ped);
}

// ---------------------------- fim da logica original ----------------------------

// WinMaestro: volta TODO o estado global do modulo ao valor inicial (P17).
void Reseta()
{
   g_dia_atual = 0; g_handle_ema = INVALID_HANDLE;
   ArrayResize(g_high_dia, 0); ArrayResize(g_low_dia, 0); ArrayResize(g_close_dia, 0); ArrayResize(g_time_dia, 0);
   g_tem_retangulo = false; g_topo = 0.0; g_piso = 0.0; g_largura = 0.0; g_meio = 0.0; g_retangulo_inicio_ts = 0; g_fora_seguidas = 0;
   g_ordem_pendente = false; g_ticket_entrada = 0; g_barras_esperando = 0; g_lado_entrada = RET_NENHUM;
   g_meio_original = 0.0; g_stop_original = 0.0; g_alvo_original = 0.0;
   g_ticket_alvo = 0;
   g_preco_entrada = 0.0; g_largura_posicao = 0.0; g_frac_alvo_atual = 0.0; g_barra_do_fill = 0; g_barras_posicao = 0;
   g_historico_carregado = false;
   g_ultima_vela_processada = 0; g_atr_dia = 0; g_atr_d1 = 0.0; g_atr_ok = false;
   g_gap_dia_avaliado = -1; g_gap_bloqueado = false;
   g_nb_ultima = 0;
   g_vela_entrada = 0; g_id = 0; g_agora = 0;
   ArrayInitialize(g_anel_id, 0); ArrayInitialize(g_anel_lado, 0); ArrayInitialize(g_anel_meio, 0.0); ArrayInitialize(g_anel_stop, 0.0); ArrayInitialize(g_anel_alvo, 0.0);
   g_anel_pos = 0; g_fill_id = 0; g_fill_preco = 0.0; g_fill_hora = 0;
   g_fs_dia_semana_cache = -1; g_fs_fim_cache = FIM_SESSAO_FALLBACK_MIN;
}

// WinMaestro: velas M15 com abertura em (depois_de, ate_inclusive].
int ContaVelas(const datetime depois_de, const datetime ate_inclusive)
{
   if(depois_de <= 0 || ate_inclusive <= depois_de) return 0;
   datetime t[];
   int n = CopyTime(_Symbol, TempoGrafico, depois_de + 1, ate_inclusive, t);
   return n > 0 ? n : 0;
}

// WinMaestro: estado persistido (Apendice A). Contagens de velas NAO sao guardadas: saem dos instantes.
void Exporta()
{
   Mem_SetI("RE.dia_atual", (long)g_dia_atual);
   Mem_SetB("RE.tem_ret", g_tem_retangulo);
   Mem_SetD("RE.topo", g_topo); Mem_SetD("RE.piso", g_piso); Mem_SetD("RE.largura", g_largura); Mem_SetD("RE.meio", g_meio);
   Mem_SetI("RE.ret_inicio", (long)g_retangulo_inicio_ts);
   Mem_SetI("RE.fora_seguidas", g_fora_seguidas);
   Mem_SetB("RE.ordem_pendente", g_ordem_pendente);
   Mem_SetI("RE.ticket_entrada", (long)g_ticket_entrada);
   Mem_SetI("RE.vela_entrada", (long)g_vela_entrada);
   Mem_SetI("RE.lado_entrada", (long)g_lado_entrada);
   Mem_SetD("RE.meio_orig", g_meio_original); Mem_SetD("RE.stop_orig", g_stop_original); Mem_SetD("RE.alvo_orig", g_alvo_original);
   Mem_SetI("RE.id", g_id);
   for(int k = 0; k < RE_ANEL; k++)
   {
      string p = StringFormat("RE.anel%d.", k);
      Mem_SetI(p + "id", g_anel_id[k]); Mem_SetI(p + "lado", g_anel_lado[k]);
      Mem_SetD(p + "meio", g_anel_meio[k]); Mem_SetD(p + "stop", g_anel_stop[k]); Mem_SetD(p + "alvo", g_anel_alvo[k]);
   }
   Mem_SetI("RE.anel_pos", g_anel_pos);
   Mem_SetI("RE.fill_id", g_fill_id); Mem_SetD("RE.fill_preco", g_fill_preco); Mem_SetI("RE.fill_hora", (long)g_fill_hora);
   Mem_SetI("RE.ticket_alvo", (long)g_ticket_alvo);
   Mem_SetD("RE.preco_entrada", g_preco_entrada);
   Mem_SetD("RE.largura_pos", g_largura_posicao);
   Mem_SetD("RE.frac_alvo", g_frac_alvo_atual);
   Mem_SetI("RE.barra_fill", (long)g_barra_do_fill);
   Mem_SetI("RE.ultima_vela_proc", (long)g_ultima_vela_processada);
   Mem_SetI("RE.nb_ultima", (long)g_nb_ultima);
}

void Importa()
{
   if(!Car_Tem("RE.dia_atual")) return;
   g_dia_atual = (datetime)Car_GetI("RE.dia_atual", 0);
   g_tem_retangulo = Car_GetB("RE.tem_ret", false);
   g_topo = Car_GetD("RE.topo", 0.0); g_piso = Car_GetD("RE.piso", 0.0); g_largura = Car_GetD("RE.largura", 0.0); g_meio = Car_GetD("RE.meio", 0.0);
   g_retangulo_inicio_ts = (datetime)Car_GetI("RE.ret_inicio", 0);
   g_fora_seguidas = (int)Car_GetI("RE.fora_seguidas", 0);
   g_ordem_pendente = Car_GetB("RE.ordem_pendente", false);
   g_ticket_entrada = (ulong)Car_GetI("RE.ticket_entrada", 0);
   g_vela_entrada = (datetime)Car_GetI("RE.vela_entrada", 0);
   g_lado_entrada = (ELadoRetangulo)Car_GetI("RE.lado_entrada", (long)RET_NENHUM);
   g_meio_original = Car_GetD("RE.meio_orig", 0.0); g_stop_original = Car_GetD("RE.stop_orig", 0.0); g_alvo_original = Car_GetD("RE.alvo_orig", 0.0);
   g_id = Car_GetI("RE.id", 0);
   for(int k = 0; k < RE_ANEL; k++)
   {
      string p = StringFormat("RE.anel%d.", k);
      g_anel_id[k] = Car_GetI(p + "id", 0); g_anel_lado[k] = (int)Car_GetI(p + "lado", 0);
      g_anel_meio[k] = Car_GetD(p + "meio", 0.0); g_anel_stop[k] = Car_GetD(p + "stop", 0.0); g_anel_alvo[k] = Car_GetD(p + "alvo", 0.0);
   }
   g_anel_pos = (int)Car_GetI("RE.anel_pos", 0) % RE_ANEL;
   g_fill_id = Car_GetI("RE.fill_id", 0); g_fill_preco = Car_GetD("RE.fill_preco", 0.0); g_fill_hora = (datetime)Car_GetI("RE.fill_hora", 0);
   g_ticket_alvo = (ulong)Car_GetI("RE.ticket_alvo", 0);
   g_preco_entrada = Car_GetD("RE.preco_entrada", 0.0);
   g_largura_posicao = Car_GetD("RE.largura_pos", 0.0);
   g_frac_alvo_atual = Car_GetD("RE.frac_alvo", 0.0);
   g_barra_do_fill = (datetime)Car_GetI("RE.barra_fill", 0);
   g_ultima_vela_processada = (datetime)Car_GetI("RE.ultima_vela_proc", 0);
   g_nb_ultima = (datetime)Car_GetI("RE.nb_ultima", 0);
   // recalculo a partir dos instantes (Apendice A): velas esperando e em posicao
   datetime b0 = iTime(_Symbol, TempoGrafico, 0), b1 = iTime(_Symbol, TempoGrafico, 1), b2 = iTime(_Symbol, TempoGrafico, 2);
   bool barra_atual_processada = (g_nb_ultima == b0);
   if(g_ordem_pendente) g_barras_esperando = ContaVelas(g_vela_entrada, barra_atual_processada ? b1 : b2);
   if(g_barra_do_fill > 0) g_barras_posicao = ContaVelas(g_barra_do_fill, barra_atual_processada ? b1 : b2);
}

// WinMaestro: poe os niveis da entrada `id` (a atual ou uma do anel) como os da entrada em curso. false = id desconhecido.
bool AdotaNiveis(const long id)
{
   if(id == 0) return false;
   if(id != g_id)
   {
      int k = -1;
      for(int j = 0; j < RE_ANEL; j++) if(g_anel_id[j] == id) k = j;
      if(k < 0) return false;
      g_lado_entrada = (ELadoRetangulo)g_anel_lado[k]; g_meio_original = g_anel_meio[k]; g_stop_original = g_anel_stop[k]; g_alvo_original = g_anel_alvo[k];
   }
   return g_lado_entrada != RET_NENHUM && g_meio_original > 0.0;
}

// WinMaestro: avisos do maestro (desenho sec. 7).
//  ENTRADA_EXECUTADA da entrada atual -> DetectarPreenchimentoEntrada (MANTER stop reancorado + alvo).
//  ENTRADA_EXECUTADA da entrada anterior (cancelada e rearmada, mas a E encheu antes do cancelamento) ->
//    volta os niveis dela e adota o fill do mesmo jeito.
//  ENTRADA_CANCELADA/RECUSADA/PERDIDA da entrada atual -> a espera acaba (nao rearma: o retangulo decide na vela).
void Evento(const SEvento &e, const VistaRobo &v, Intencao &ped)
{
   if(e.ev == EV_ENTRADA_EXECUTADA)
   {
      if(!AdotaNiveis(e.id_entrada)) return;
      if(!TemPosicaoPropria()) { g_fill_id = e.id_entrada; g_fill_preco = e.preco; g_fill_hora = e.hora; return; }   // adota no Tick
      DetectarPreenchimentoEntrada(ped, e.preco, e.hora);
      return;
   }
   if(e.id_entrada == g_id) { g_ordem_pendente = false; g_ticket_entrada = 0; g_barras_esperando = 0; }
}

// WinMaestro: o RE nao tem regra para refazer o stop sem a memoria (o retangulo nao e' reconstruivel).
double StopRegra(const int lado) { return 0.0; }

// WinMaestro: horario proprio de zeragem (17:00; o maestro limita ao corte).
int MinutoZerarRobo(const datetime dia) { return HoraZerar * 60 + MinutoZerar; }

int Init(const VistaRobo &v)
{
   Reseta();
   Configura();
   int r = InitBase();
   if(r != INIT_SUCCEEDED) return r;
   Importa();
   g_agora = v.agora;
   return INIT_SUCCEEDED;
}

void Deinit(const int reason)
{
   // WinMaestro: nao cancela a entrada no proprio Deinit (spec 10.4, Apendice A): toda E ja' tem a sua S.
   DeinitBase(reason);
}

} // namespace WRE

#endif
