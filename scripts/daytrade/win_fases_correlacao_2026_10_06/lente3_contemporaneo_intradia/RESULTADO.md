# Lente 3 - contemporaneo x operavel, intradia M5 e perfil de volume (WIN, 127 pregoes, 2026-04-06..10-05)

Reproduzir: `.venv\Scripts\python.exe lente3.py` (tabelas em `out/`, log em `out_stdout.txt`). Permutacao 10.000x, semente fixa, BH por familia.
"limpo" = sem 07-31, 09-24, 10-05, o dia seguinte a cada um, e vencimentos 04-15, 06-17, 08-12 + dia seguinte (n=116). Metades: abr-jun x jul-out.

## Problemas de dado
- M1 do WIN$N: a barra 18:24 contem o volume e o preco do call (close = pos_preco_fechamento; volume ~21-25 mil contra ~1,5-3 mil). A 1a barra da manha contem o volume do leilao. Corrigido: subtraido pre_volume/pos_volume; fechamento do pregao e abertura tomados do CSV de fases. Sem isso o "fim do pregao" em M5 vira o call (42 dias com |dif|>100 pts).
- M1 so comeca em 09:00-09:04 (leilao termina 09:00-09:04): a barra M5 das 09:00 e parcial em ~2/3 dos dias.
- Nenhum dos tres dias problematicos e das tres rolagens muda qualitativamente o resultado (ver colunas todos/limpo). O gap de 10-05 (+17.775) distorce so Pearson, nao Spearman.

## 1. Matriz (Spearman) - 425 pares (17 variaveis x {D, D-1}, sem D-1 x D-1), todos: 101 com q<0,05; limpo: 99
Rotulos: "operavel" = X conhecido antes do inicio de Y e Y do pregao de D; "sequencial" = D-1 -> pre de D; "contemporaneo" = mesma fase; pares com call de D x pregao de D ficam na CSV marcados "contemporaneo/descritivo" e foram EXCLUIDOS do top-20 (escopo do dono). Pares mecanicos (vol x neg x vpn da mesma fase, ret x range) tambem excluidos do top-20.
Top-20 (limpo, n~115): `out/top20_limpo.csv`; todos: `out/top20_todos.csv`. Resumo:
| relacao | rho | q | rho H1 / H2 | rotulo |
|---|---|---|---|---|
| vol/negocio pregao D-1 -> D | +0,82 | <0,001 | +0,39 / +0,70 | operavel (persistencia de nivel) |
| negocios pregao D-1 -> D | +0,79 | <0,001 | +0,38 / +0,72 | operavel |
| negocios D-1 -> vol/negocio D | -0,76 | <0,001 | -0,19 / -0,71 | operavel |
| vol/negocio do leilao D -> vol/negocio pregao D | +0,67 | <0,001 | +0,10 / +0,56 | operavel |
| vol/neg leilao D -> negocios pregao D | -0,59 | <0,001 | -0,20 / -0,35 | operavel |
| negocios do call D-1 -> vol/neg pregao D | -0,60 | <0,001 | -0,20 / -0,09 | operavel (call de D-1) |
| volume leilao D x D-1 | +0,60 | <0,001 | +0,14 / +0,74 | sequencial |
| range pregao D x volume pregao D | +0,56 | <0,001 | +0,55 / +0,66 | contemporaneo (descritivo) |
| hora do cruzamento x negocios do leilao | +0,56 | <0,001 | +0,72 / +0,42 | contemporaneo |
Leitura: quase todo o top-20 e persistencia de volume/negocios/tamanho de negocio - e esta concentrada na metade 2 (rho H1 muito menor que H2): e deriva/regime de nivel (negocios e tamanho medio andam em tendencia na janela), nao relacao dia-a-dia; Spearman de niveis com tendencia comum infla rho. Nada disso e preco.
Relacoes OPERAVEIS com alvo preco/amplitude do pregao D (familia de 120 pares operaveis, q de BH da familia):
| relacao | n | rho | p perm | q (todos matriz) | H1 / H2 |
|---|---|---|---|---|---|
| gap -> retorno do pregao | 124 | -0,23 | 0,009 | 0,040 | -0,24 / -0,24 |
| (limpo) gap -> retorno do pregao | 115 | -0,18 | 0,06 | n.s. | -0,22 / -0,16 |
| volume do call D-1 -> range do pregao D | 126 | -0,23 | 0,009 | 0,040 | -0,21 / -0,23 |
| (limpo) idem | 115 | -0,28 | 0,001 | 0,007 | -0,20 / -0,34 |
| range D-1 -> d%volume D | 126 | -0,45 | <0,001 | 0,001 | -0,54 / -0,42 (parcialmente mecanico: D-1 no denominador de d%) |
Gap negativo (a favor de reversao) -> retorno do pregao: rho -0,23; efeito pequeno (retorno do pregao tem dp ~1.989 pts).

## 2. Dentro do pregao de D (M5 fechadas; barra k fecha 09:00+5k min; mov_k = close_k - abertura; resto = fechamento 18:25 - close_k)
50 testes por base (k=1,3,6,12,24 x 10 recortes), 0 com q<0,05 em ambas as bases; melhores:
| relacao | n | rho | p perm | q | H1/H2 |
|---|---|---|---|---|---|
| range ate k=1 -> amplitude restante (limpo) | 116 | +0,25 | 0,007 | 0,28 | +0,25/+0,16 |
| \|mov12\| -> amplitude restante (todos) | 126 | +0,25 | 0,006 | 0,12 | +0,28/+0,19 |
| mov_k -> resto_k (direcao, todos os k) | ~126 | |rho|<0,1 | n.s. | | sem relacao de direcao |
Direcao: o 1o movimento nao preve o resto do pregao em geral. Condicionado ao gap (continuidade = pontos do resto na direcao do mov ate k; `out/continuidade_por_alinhamento.csv`, sign-flip 5.000, BH em 15 testes por base):
| base | k | grupo | n | media pts (R$ por contrato = x0,2) | % continua | p | q | media H1/H2 |
|---|---|---|---|---|---|---|---|---|
| todos | 1 | mov CONTRA o gap (inicio de fechamento do gap) | 66 | +707 (R$141) | 62% | 0,002 | 0,024 | +748/+676 |
| todos | 1 | mov A FAVOR do gap | 56 | -37 | 39% | 0,87 | | -200/+138 |
| todos | 1 | dif contra-favor | 122 | +744 | | 0,021 | 0,053 | |
| limpo | 1 | contra | 58 | +774 (R$155) | 62% | 0,002 | 0,030 | +822/+738 |
| todos | 3 | contra | 67 | +531 | 60% | 0,012 | 0,052 | +669/+432 |
| todos | 6 | a favor | 61 | -445 (reverte) | 43% | 0,043 | 0,092 | -574/-312 |
| todos | 12 | dif contra-favor | 123 | +832 | | 0,007 | 0,052 | |
| todos | 24 | qualquer | | | | n.s. | | |
Observacao: quando a 1a barra anda contra o gap, o resto tende a continuar nessa direcao (+700 pts medianos ~+630); quando anda a favor do gap nao ha continuacao e ate reversao nos k=6-12. Mesmo sinal nas duas metades. Tamanho tipico: |resto| mediano 1.100 pts; dp do retorno do pregao ~1.990 pts; custo e deslize nao descontados. Estamos testando agrupamentos escolhidos apos olhar (15 por base): BH deixa q~0,02-0,05, fragil.
Leilao grande x pequeno (tercis de pre_vol): sem diferenca consistente na continuidade (n=39-42 por tercil, p>0,06 em todos).
Call de D x fim do pregao (contemporaneo, fora do escopo, uma linha): rho(mov1 -> pos_ret) = -0,15 (todos, p=0,08), preg_ret -> pos_ret -0,15 (p=0,11); nada significativo.

## 3. Perfil de volume M5 (volume do pregao ex-leilao/call; share % do volume do dia)
Nao e "U" simetrico: e um pico de abertura e queda monotonica (forma de "L" / J invertido):
09:00-10:00 16,8% | 10:00-11:00 **23,4%** | 11:00-12:00 15,4% | 12:00-13:00 9,9% | 13-14h 7,8% | 14-15h 7,9% | 15-16h 7,5% | 16-17h 6,9% | 17-18h 3,5% | 18:00-18:25 0,8%.
Pico por barra: 10:30 (2,78%), 10:00, 10:35, 10:15, 09:05; minimo 18:20. O pico das 10:30 e o horario de dados dos EUA (hipotese). Nao ha segunda alta no fim (nao ha U): a barra 16:00-17:00 nao supera 13:00-16:00.
Leilao grande e volume da 1a hora (09:00-10:00, `out/parte3_testes.csv`, 28 testes, BH): pre_vol -> vol 1a hora rho +0,25 (todos; p=0,005; q=0,076; H1 +0,23/H2 +0,23), +0,23 (limpo; p=0,013). Tercis: leilao alto 3,03 mi contratos na 1a hora contra 2,85 mi (baixo), ~+6%. Em share do dia: pre_vol -> share_1h rho +0,13 (n.s.). Ou seja, so o volume absoluto, nao a concentracao.
Amplitude restante: pre_vol -> amplitude apos 10:00 rho +0,07 (n.s.); pre_vol -> |ret| restante apos 10h rho -0,17 (p=0,06; q=0,18): leilao grande, menos deslocamento liquido apos 10h (tercis: 1.192 contra 1.479 pts, p fraco). Volume da 1a hora -> amplitude restante rho +0,18-0,20 (p=0,04, q=0,15, estavel); range da 1a hora -> amplitude restante rho +0,21-0,24 (p=0,01-0,02, q=0,08-0,10, mesmo sinal nas metades: 0,30/0,08 limpo). Nenhum com q<0,05 na familia de 28. Efeitos pequenos: amplitude restante mediana ~2.600 pts.
