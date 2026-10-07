# Volume e participação no WIN, setembro/2026 (exploração)

Dados: WINV26 M1, 21 pregões. Pernadas pelo zigzag de 750 pts. Volume normalizado pela média do mesmo horário (vrel = vol / média do horário em setembro, incluindo o próprio dia, vazamento pequeno). tsz = VOL/TICKVOL (contratos por negócio), também normalizado por horário.
Pernadas (todas / fechadas): M5 190/169, M15 172/151, H1 121/100. Tabela completa em legs.csv.

## Achados
1. Volume da vela anterior ao início: sem relação com o tamanho. Spearman com o tamanho final: M5 +0,12, M15 +0,02, H1 +0,03. Por terços, o tamanho mediano foi 1205/1470/1220 pts (M5) e 1297/1465/1185 (M15), não monotônico. A mediana do vrel é ~1,0 a 1,07 (a vela anterior é pouco distinta do normal).
2. Volume médio da pernada (vrel) vs tamanho: +0,14 (M5), +0,23 (M15), +0,06 (H1). Fraco e positivo.
3. Volume por ponto andado (leg_vpp) correlaciona forte com a duração (M5 +0,83, M15 +0,62). Isso é em boa parte mecânico (mais tempo, mais volume, mesmo tamanho). No H1 correlaciona -0,41 com o tamanho, o que é divisão por tamanho.
4. Tamanho médio por negócio (tsz) ao longo da pernada: mediana normalizada ~1,00 em todos os tempos gráficos. Nenhum viés alto ou baixo. tsz bruto ~3,1 contratos/negócio. Spearman com duração +0,56 (M5), +0,53 (M15) e com nº de correções +0,54/+0,49 (M5/M15). Pernadas lentas e com mais correções têm negócios maiores em média; pode ser efeito de horário (pernadas longas no meio do dia, onde o negócio médio é maior), pois o tsz bruto foi usado nessa coluna. Suspeito de artefato de horário.
5. Candles de avanço (fazem novo extremo na direção da pernada) vs candles de correção, M5: vrel mediano 1,09 (n=981) vs 0,86 (n=653). O volume seca nas correções. Parte mecânica: candle que faz novo extremo tende a ter mais range, logo mais volume. Volume por ponto de range é ~igual (591 vs 574).
6. Candle do extremo final da pernada vs candles que são extremos intermediários (extremos seguidos de recuo >=5 pts e depois novo extremo), M5: vrel mediano 1,16 (dp 0,38, n=169) vs 1,07 (dp 0,31, n=655). AUC 0,60 (vrel), 0,62 (volume do extremo / média das 3 velas anteriores), 0,47 (tsz). Há uma pista de clímax de volume, mas pequena e sobreposta. O tsz do extremo não diferencia. Rótulo "final" só é conhecido depois, então é descritivo.
7. Altas vs baixas: indistinguíveis. M15: vrel 1,04 vs 1,00, tsz 3,11 vs 3,10; M5 tsz 3,09 vs 3,09.
8. Horário de início: pernadas que começam 09h-10h são a maioria (M5: 58+53 de 169) e maiores (mediana 1512 no 9h vs 850 no 14h). O volume é em boa parte um proxy de horário; a normalização retira isso.
9. Última pernada do dia (aberta) excluída das estatísticas de tamanho e duração.

## Ressalvas
n pequeno, 21 dias, observações dependentes entre pernadas do mesmo dia e entre tempos gráficos (as pernadas M5/M15/H1 se sobrepõem). Sazonalidade estimada na mesma amostra. O caminho dentro da vela é uma convenção, então o "extremo" fica na vela e não no minuto exato. Nenhum lucro de estratégia foi calculado.
