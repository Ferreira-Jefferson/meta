//+------------------------------------------------------------------+
//| WinMaestro/Tipos.mqh                                             |
//| Constantes, tipos e o estado global do nucleo v2.01.             |
//| Desenho: mt5/WinMaestro_ARQUITETURA_v2.md (v2.2). "sec. n" aponta|
//| para o desenho; "spec n" para WinMaestro_ESPECIFICACAO.md 1.0.   |
//|                                                                  |
//| Estado que sobrevive entre ciclos = a MEMORIA (sec. 1.2), listada|
//| no bloco "memoria" abaixo, mais o que fica so' em RAM (bloco     |
//| "RAM"). Todo o resto (fichas, situacao, confianca, cobertura...) |
//| e' DERIVADO a cada ciclo do snapshot (sec. 1.3) e mora em mzEst. |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_TIPOS_MQH
#define WINMAESTRO_TIPOS_MQH

#include "Corretora.mqh"

#define WM_VERSAO "2.01"

//--- robos (ordem fixa GB, CM, DM, RE, C1) e o MAESTRO (dono das ordens da conta, sec. 5)
#define NROBOS 5
#define R_GB  0
#define R_CM  1
#define R_DM  2
#define R_RE  3
#define R_C1  4
#define R_MAE 5
#define NDONOS 6
#define MAGIC_MAESTRO 80089999     // escolha: magic do C_CONTA e dos K da conta (nao colide com os 5 robos)

//--- constantes do desenho (sec. 0 do desenho); tempos em ms quando terminam em _MS
#define PROVA_MS            30000
#define CONEXAO_MS          10000
#define FOLGA_SETUP_MS       5000
#define PRAZO_ENTRAR_MS     10000
#define PRAZO_SAIR_MS       60000
#define RETENTA_MS           5000
#define PRAZO_BLOQUEIO_MS   60000
#define PRAZO_BOTAO_MS     600000
#define PRAZO_CORTE_S         120
#define HB_TOMADA_S            60
#define RODADAS                 4
#define STOP_EMERGENCIA_PTS 1200.0
#define TICK_WIN               5.0
#define IDADE_TICK_MS       10000
#define PRAZO_S_RECUSADA_MS 60000
//--- constantes da especificacao que o desenho manteve
#define MARGEM_CORTE_MIN        5   // corte C = F - 5 min (D2)
#define CALL_MIN               15   // fim da sessao = F + 15 min (escolha: janela do call de fechamento)
#define CM_RESERVA_PTS     4945.0   // O11
#define DM_CAPITAL         1000.0   // B9
#define CORRECAO_JANELA_S     600   // 2a correcao em 10 min -> bloqueio com botao (decisao 1)
#define RELEITURA_MS        10000   // recuo da janela: no maximo 1 a cada 10 s
#define RECUO_MAX              10   // ate' 10 pregoes
#define MAX_ORD                16   // ordens vivas por robo guardadas no estado derivado

//--- papeis (sec. 1.2)
#define P_E 1
#define P_S 2
#define P_A 3
#define P_X 4
#define P_K 5
#define P_M 6
#define NPAPEIS 7

//--- desfechos (sec. 1.2, sec. 2.1)
#define D_PENDENTE      0
#define D_VIVA          1
#define D_SUMIDA        2
#define D_EXECUTADA     3
#define D_NAO_EXECUTADA 4
#define D_RECUSADA      5

//--- situacao (sec. 1.3)
#define SIT_ZERO      0
#define SIT_LEGITIMA  1
#define SIT_TROCADA   2
#define SIT_DUPLICADA 3

//--- intencao (sec. 1.4)
#define INT_NADA   0
#define INT_ENTRAR 1
#define INT_MANTER 2
#define INT_SAIR   3

//--- eventos aos modulos (sec. 7)
#define EV_ENTRADA_EXECUTADA 1
#define EV_ENTRADA_CANCELADA 2
#define EV_ENTRADA_RECUSADA  3
#define EV_ENTRADA_PERDIDA   4
#define EV_SAIDA_EXPIRADA    5

//--- acoes (sec. 1.5)
#define AC_NENHUMA  0
#define AC_ENVIA_S  1
#define AC_MOVE_S   2
#define AC_ENVIA_E  3
#define AC_ENVIA_A  4
#define AC_MOVE_A   5
#define AC_ENVIA_X  6
#define AC_CANCELA  7
#define AC_RECUSA_E 8    // E1 com O2: ENTRADA_RECUSADA(autoneg) e id consumido, sem ordem
#define AC_C_CONTA  9

//--- origem da intencao efetiva (sec. 4.1)
#define I_1 1
#define I_2 2
#define I_3 3
#define I_4 4
#define I_5 5
#define I_6 6

//+------------------------------------------------------------------+
//| Tipos                                                            |
//+------------------------------------------------------------------+
// Intencao escrita pelo modulo no Tick (sec. 1.4).
struct Intencao
{
   int      tipo;          // INT_*
   long     id_entrada;    // ENTRAR: uma E por id; rearmar = id novo
   int      lado;          // ENTRAR: +1 compra, -1 venda
   double   limite;        // ENTRAR: preco da limite (0 = mercado, C1)
   double   stop;          // ENTRAR / MANTER: nivel da S (0 = sem pedido: vale a cadeia da sec. 4.3)
   datetime expira;        // ENTRAR: 0 = DAY; GB = g_exp
   double   alvo;          // MANTER: nivel do A (0 = sem A); SAIR: ficha desejada (0, ou +/-1 na duplicada)
   string   motivo;
};

// Vista do robo no ciclo (sec. 7). So' ficha LEGITIMA aparece como posicao (`tem`).
struct VistaRobo
{
   datetime agora;
   bool     tem;
   int      lado;
   double   preco;
   datetime hora;
   ulong    id;
   double   stop_pedido;
   double   alvo_vivo;
   bool     tem_entrada;   // entrada_viva
   int      ent_lado;
   double   ent_preco;
   long     ent_id;
   datetime ent_setup;
   bool     continuo;
};

struct SEvento
{
   int      ev;            // EV_*
   long     id_entrada;
   double   preco;
   datetime hora;
   string   motivo;
};

// Linha do mapa: uma por ordem que o EA enviou (sec. 1.2).
struct SLinha
{
   long     id;            // numero da linha (unico, persistido)
   int      robo;          // 0..4 ou R_MAE
   int      papel;         // P_*
   int      episodio;
   long     id_entrada;    // E e a S da entrada
   int      seq;
   string   coment;
   int      tipo;          // ENUM_ORDER_TYPE (K: -1; M: tipo da ordem alvo)
   double   preco;         // E/S/A: preco pedido; M: preco novo; X: 0
   double   vol;
   ulong    alvo_ticket;   // K, M
   long     enviado_msc;   // relogio do servidor (casamento com ORDER_TIME_SETUP_MSC)
   long     enviado_mono;  // relogio monotonico (prazos); refeito na carga pela diferenca do servidor
   ulong    ticket;
   uint     request_id;
   uint     retcode;
   int      desfecho;      // D_*
   long     sumida_msc;
   long     sumida_mono;
   string   prova;
   datetime expira;       // E: validade pedida (0 = DAY)
   string   motivo;       // I1/I2/I3/MOD (quem pediu); I2 = correcao (decisao 1)
   int      ev;           // eventos ja' entregues da E: bit 1 = final (cancelada/recusada), bit 2 = executada
   int      estado_hist;  // ultimo ORDER_STATE visto no historico (-1 = nao visto)
};

// Estado derivado do robo (sec. 1.3), refeito a cada ciclo.
struct SEst
{
   int      f;
   int      sit;
   bool     noite;
   double   preco;
   long     hora_msc;
   ulong    id;            // ticket do deal de abertura
   int      papel_ab;
   bool     abs_virtual;   // ficha absorvida pelo Delta externo virtual (sec. 2.2): sem L2/L3
   int      nao_class;     // deals deste robo nao classificados
   bool     provado;
   bool     confiavel;
   bool     inequivoco;    // lado inequivoco (sec. 2.2)
   int      lado_prot;     // lado protegido: +1 compra, -1 venda, 0 nenhum
   double   cobertura;
   // ordens vivas do robo (vivas[] x mapa)
   int      nS;
   int      sIdx[MAX_ORD]; // indices em mzViva
   int      iE;            // E viva (indice em mzViva; -1)
   int      iA;            // A viva
   int      nFora;
   int      foraIdx[MAX_ORD]; // limites do magic do robo fora do mapa (L4)
   int      lE;            // linha do mapa da E viva/pendente (-1)
   // pendentes (linhas PENDENTE/SUMIDA; X viva conta como pendente)
   bool     pendS, pendE, pendA, pendX, pendK, pendM;
   bool     reduz_pend;
   bool     nada_pend;
   int      ePendLado;     // lado da E pendente (para o lado protegido com f = 0)
   double   ePendPreco;
};

//+------------------------------------------------------------------+
//| Estado global                                                    |
//+------------------------------------------------------------------+
string mzNome[NDONOS]  = {"GB", "CM", "DM", "RE", "C1", "MAESTRO"};
long   mzMagic[NDONOS] = {80080601, 80080501, 80080101, 20261005, 80080002, MAGIC_MAESTRO};
bool   mzAtivo[NROBOS];

//--- snapshot (sec. 1.1), refeito no passo 1 de cada ciclo
long       mzAgoraMsc = 0;          // relogio do servidor (grade, horarios, ids)
long       mzMono = 0;              // relogio monotonico (todos os prazos, M-4)
datetime   mzAgora = 0;
bool       mzConectado = false;
long       mzConexaoDesde = 0;      // TERMINAL_CONNECTED verdadeiro desde (RAM)
bool       mzConexaoOk = false;
bool       mzTravaOk = false;
bool       mzBaseOk = false;
int        mzLiq = 0;
SOrdemViva mzViva[];
bool       mzHistOk = false;
long       mzHistOkDesde = 0;
SDealInfo  mzDeal[];
SOrdemHist mzOH[];
double     mzBid = 0.0, mzAsk = 0.0;
bool       mzLivroOk = false;       // bid > 0, ask >= bid, tick com menos de IDADE_TICK
double     mzUltLast = 0.0;         // ultimo last > 0 visto (RAM)
long       mzUltTickMsc = 0;        // instante do ultimo tick visto (desvio do relogio, M-4)
bool       mzRelogioDesvio = false;
int        mzGPre = 0, mzGNeg = 0, mzGFim = 0;   // grade de hoje, minutos do dia
bool       mzGTem = true;
uint       mzReqId[];               // pares request_id -> ticket (OnTradeTransaction REQUEST)
ulong      mzReqTk[];

//--- memoria (sec. 1.2): o unico estado que sobrevive entre ciclos alem da RAM
SLinha   mzL[];
long     mzProxLinha = 1;
double   mzNivS[NROBOS];            // nivel de S pedido (inclui a emergencia gravada)
double   mzNivSIntUlt[NROBOS];      // ultimo nivel de S que o modulo pediu (so' troca o pedido quando o modulo pede outro)
double   mzNivA[NROBOS];            // nivel de A pedido
double   mzEmerg[NROBOS];           // emergencia do episodio (sec. 4.3): gravada uma vez, nunca movida
int      mzEmergLado[NROBOS];       // lado que a emergencia protege (+1 compra, -1 venda); outro lado = outra emergencia
long     mzConsR[];                 // id_entrada consumidos: robo
long     mzConsId[];                //                         id
long     mzUltId[NROBOS];           // ultimo id_entrada gerado (Ficha_NovoId)
int      mzSeq[NROBOS + 1];
datetime mzSeqDia = 0;
long     mzUltCorrMsc[NROBOS];      // instante da ultima correcao executada (decisao 1)
int      mzEp[NROBOS];              // numero do episodio atual
bool     mzEpAberto[NROBOS];
bool     mzBloqBotao = false;       // bloqueio que exige o botao
string   mzBloqMotivo = "";
ulong    mzReconh[];                // tickets reconhecidos pelo botao
int      mzExtDesc = 0;             // externa de origem desconhecida
long     mzExtZeroDesde = 0;        // RAM (A-1): desde quando (monotonico) a liquida e os deals da janela somam 0 com mzExtDesc != 0
ulong    mzAbsVistas[];             // deals externos que absorveram fichas, ja' vistos
ulong    mzDealsLog[];              // deals ja' logados
datetime mzJanRecuo = 0;            // inicio da janela recuado (0 = sem recuo)
datetime mzJanRecuoDia = 0;
datetime mzMemDia = 0;

//--- RAM (sec. 1.2, refeitos na partida)
long     mzInvalidoDesde = 0;
long     mzRestritoDesde[NROBOS];
int      mzDeltaVal = 0;
long     mzDeltaDesde = 0;
long     mzSFaltaDesde[NROBOS];
long     mzEspera[NDONOS][NPAPEIS];     // em_espera ate' (ms)
int      mzRecusaN[NDONOS][NPAPEIS];     // recusas seguidas
long     mzRecusaAlerta[NDONOS][NPAPEIS];
Intencao mzInt[NROBOS];                // intencao do modulo
long     mzEntId[NROBOS];              // ENTRAR visto: id e desde quando (PRAZO_ENTRAR)
long     mzEntDesde[NROBOS];
long     mzSairAcum[NROBOS];           // PRAZO_SAIR contado so' em ciclos confiaveis
long     mzSairUlt[NROBOS];
bool     mzSairConta[NROBOS];
bool     mzInit[NROBOS];               // modulo recebeu Init
bool     mzInitFalhou[NROBOS];
long     mzSCruzDesde[NROBOS];         // S em nivel cruzado ha' (ALERTA apos PROVA)
long     mzRecuoUlt = 0;
int      mzRecuoN = 0;
bool     mzMemPerdida = false;
bool     mzMemGravando = true;         // a ultima gravacao funcionou
long     mzMemUltGrava = 0;
bool     mzMemCarregada = false;
long     mzPartidaMsc = 0;             // OnInit (decisao anterior = DECISAO PERDIDA)
bool     mzProntoLogado = false;
bool     mzAmbVisto = false;           // primeiro snapshot com historico ja' conferiu o ambiente
bool     mzProtegendo = false;
bool     mzParado = false;             // ambiente falhou sem ficha nem ordem de robo: nada sai (re-confere a cada 30 s)
bool     mzNaoNetting = false;         // INVALIDO permanente
long     mzAmbUlt = 0;
bool     mzSpecifiedOk = false;        // E com validade SPECIFIED aceita pelo simbolo (decidido na partida)
ENUM_ORDER_TYPE_FILLING mzFillMercado = ORDER_FILLING_RETURN;
long     mzPainelUlt = 0;
datetime mzBotaoClique = 0;
#define  MAE_BOTAO "WinMaestro_Desbloquear"

//--- derivado (sec. 1.3, sec. 2.2), refeito no passo 3
SEst     mzEst[NROBOS];
VistaRobo mzVista[NROBOS];
int      mzExterna = 0;
int      mzSomaDeals = 0;
int      mzDelta = 0;
int      mzDeltaResto = 0;
int      mzNaoClassTotal = 0;
bool     mzDeltaEstavel = false;
bool     mzTodosProvados = false;
bool     mzBloqAuto = false;
bool     mzAbsVirtual = false;
datetime mzJanIni = 0;

#endif
