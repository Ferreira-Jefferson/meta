# Lente 2 - dia anterior (D-1) -> pregao de D

Maiores |gap| (call D-1 -> leilao D): 2026-10-05:17775, 2026-04-08:4875, 2026-04-15:4415, 2026-08-12:3960, 2026-06-17:3350, 2026-09-08:2880

## Preditores D-1 x alvos de D (com 10-05); testes=110; p<0.05 bruto=14 (acaso ~6); q<0.10=2; q_cons(max p embaralhado/circular)<0.10=0
       pred         alvo   n    rho     p  p_circ  rho_h1  rho_h2  pmax     q  q_cons  estavel
     d1_vol          vol 122  0.342 0.000   0.025   0.162   0.492 0.025 0.011   0.386     True
     d1_neg          vol 122  0.336 0.000   0.230   0.237   0.524 0.230 0.011   0.851     True
 d1_callvol          rng 122 -0.239 0.007   0.041  -0.205  -0.254 0.041 0.148   0.405     True
     d1_l30         m5_1 122 -0.243 0.008   0.016  -0.341  -0.236 0.016 0.148   0.301     True
d1_closepos          rng 122  0.225 0.009   0.016   0.129   0.301 0.016 0.148   0.301     True
     d1_l30         m5_3 122 -0.240 0.009   0.016  -0.377  -0.163 0.016 0.148   0.301     True
     d1_l30         m5_6 122 -0.231 0.010   0.008  -0.314  -0.192 0.010 0.148   0.301     True
d1_closepos gap_pregopen 119 -0.230 0.011   0.008  -0.304  -0.133 0.011 0.148   0.301     True
d1_closepos          gap 119 -0.231 0.015   0.008  -0.305  -0.135 0.015 0.186   0.301     True
d1_closepos          vol 122  0.216 0.017   0.049  -0.018   0.477 0.049 0.189   0.405    False
     d1_l60         m5_1 122 -0.204 0.022   0.033  -0.329  -0.194 0.033 0.222   0.401     True
     d1_ret          rng 122  0.199 0.028   0.033   0.039   0.305 0.033 0.237   0.401    False
     d1_ret gap_pregopen 119 -0.196 0.028   0.050  -0.303  -0.059 0.050 0.237   0.405    False
     d1_ret          gap 119 -0.197 0.034   0.042  -0.304  -0.060 0.042 0.270   0.405    False
     d1_l30        m5_12 122 -0.176 0.052   0.049  -0.280  -0.117 0.052 0.345   0.405     True

## Preditores D-1 x alvos de D (sem 10-05); testes=110; p<0.05 bruto=19 (acaso ~6); q<0.10=3; q_cons(max p embaralhado/circular)<0.10=0
       pred         alvo   n    rho     p  p_circ  rho_h1  rho_h2  pmax     q  q_cons  estavel
     d1_vol          vol 121  0.325 0.000   0.025   0.162   0.465 0.025 0.011   0.273     True
     d1_neg          vol 121  0.321 0.000   0.256   0.237   0.500 0.256 0.011   0.909     True
 d1_callvol          rng 121 -0.267 0.001   0.008  -0.205  -0.310 0.008 0.051   0.266     True
d1_closepos          gap 118 -0.257 0.004   0.008  -0.305  -0.186 0.008 0.104   0.266     True
d1_closepos gap_pregopen 118 -0.255 0.006   0.008  -0.304  -0.183 0.008 0.123   0.266     True
     d1_l30         m5_3 121 -0.245 0.008   0.017  -0.377  -0.178 0.017 0.126   0.266     True
     d1_l30         m5_6 121 -0.237 0.008   0.017  -0.314  -0.208 0.017 0.126   0.266     True
     d1_l30         m5_1 121 -0.248 0.010   0.025  -0.341  -0.254 0.025 0.130   0.273     True
     d1_l60         m5_1 121 -0.234 0.011   0.033  -0.329  -0.256 0.033 0.130   0.303     True
     d1_ret gap_pregopen 118 -0.226 0.013   0.017  -0.303  -0.115 0.017 0.139   0.266     True
     d1_ret          gap 118 -0.228 0.016   0.017  -0.304  -0.116 0.017 0.158   0.266     True
d1_closepos          rng 121  0.213 0.019   0.025   0.129   0.282 0.025 0.174   0.273     True
     d1_l60         m5_3 121 -0.204 0.027   0.033  -0.327  -0.162 0.033 0.217   0.303     True
d1_closepos          vol 121  0.200 0.028   0.041  -0.018   0.460 0.041 0.217   0.325    False
     d1_rng          ret 121  0.192 0.038   0.050   0.297   0.050 0.050 0.276   0.364    False

## Linha de base: autocorrelacao do pregao (lag 1-5, permutacao, todos os dias)
serie  lag   n    rho     p     q
  ret    1 126  0.051 0.582 0.779
  ret    2 125  0.078 0.378 0.581
  ret    3 124  0.140 0.119 0.217
  ret    4 123  0.004 0.962 0.962
  ret    5 122  0.049 0.584 0.779
  rng    1 126  0.022 0.812 0.902
  rng    2 125  0.045 0.623 0.779
  rng    3 124 -0.091 0.309 0.515
  rng    4 123 -0.012 0.893 0.940
  rng    5 122  0.038 0.677 0.796
  vol    1 126  0.379 0.000 0.001
  vol    2 125  0.244 0.006 0.016
  vol    3 124  0.223 0.015 0.032
  vol    4 123  0.324 0.000 0.001
  vol    5 122  0.208 0.024 0.048
  neg    1 126  0.791 0.000 0.001
  neg    2 125  0.711 0.000 0.001
  neg    3 124  0.694 0.000 0.001
  neg    4 123  0.699 0.000 0.001
  neg    5 122  0.628 0.000 0.001

## Efeito do call de D-1 controlando persistencia (rank parcial; sem dias problematicos)
- d1_callvol -> vol | ctrl d1_vol: n=121 rho=-0.148 p=0.1106
- d1_callvol -> rng | ctrl d1_rng: n=121 rho=-0.269 p=0.0034
- d1_vol -> vol | ctrl None: n=121 rho=0.325 p=0.0008
- d1_callvar -> gap | ctrl d1_ret: n=118 rho=-0.089 p=0.3343
- d1_callpct -> m5_6 | ctrl d1_ret: n=121 rho=-0.092 p=0.3181
- d1_callvar -> ret | ctrl d1_ret: n=121 rho=0.036 p=0.7021

## Cadeia: continua ou reverte? (sem dias problematicos; pontos)
                              elo   n  pct_continua    rho  p_perm  media_b_se_a_pos  media_b_se_a_neg
pregao D-1 -> call D-1 [contemp.] 119          41.2 -0.136  0.1454              -9.5              17.0
       call D-1 -> gap D (leilao) 114          44.7 -0.076  0.4115              10.5             205.5
              pregao D-1 -> gap D 117          41.9 -0.230  0.0110              10.8             182.5
                gap D -> pregao D 117          39.3 -0.178  0.0510            -522.8             264.5
             call D-1 -> pregao D 118          56.8  0.036  0.6971            -137.1            -272.0
           pregao D-1 -> pregao D 121          53.7  0.063  0.4775              94.6            -349.4

(R$ por contrato = pontos x 0,20)
