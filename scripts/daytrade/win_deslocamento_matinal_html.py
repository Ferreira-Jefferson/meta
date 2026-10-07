"""Pagina HTML de prints do win_deslocamento_matinal (celula CONGELADA, WIN@, fila P2, corrida nominal).
Abas IS 2021-2024 / OOS 2025-2026 -> botoes de mes -> botoes de dia -> grafico M5 com abertura, banda, limiares,
10:30, stop, entrada/saida. No topo, o painel "Replay com ticks reais" (servidor local, porta 8766).

Uso: .\\.venv\\Scripts\\python.exe scripts/daytrade/win_deslocamento_matinal_html.py
Saida: .claude/artifacts/win_deslocamento_matinal/index.html (Plotly inline; abre via file:///)."""
import json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RES = HERE / "win_deslocamento_matinal_2026_10_04"
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(HERE)); sys.path.insert(0, str(RES))
import comum as c
import win_deslocamento_replay_ticks as rp

OUT = ROOT / ".claude" / "artifacts" / "win_deslocamento_matinal"
PLOTLY = ROOT / ".claude" / "artifacts" / "win_setembro" / "plotly.min.js"
CONG = dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)
BANDA, LIM = 0.05, 0.3
RS = 0.2


def trades_da_celula():
    """IS: is_grade.json (celula congelada, WIN@, P2); OOS: final.json (WIN@, P2)."""
    ig = json.loads((RES / "saidas" / "is_grade.json").read_text(encoding="utf-8"))
    fi = json.loads((RES / "saidas" / "final.json").read_text(encoding="utf-8"))
    is_ = [r for r in ig if r["simbolo"] == "WIN@" and r["premissa"] == "P2" and r["params"] == CONG]
    oo = [r for r in fi if r["simbolo"] == "WIN@" and r["premissa"] == "P2"]
    assert len(is_) == 1 and len(oo) == 1, (len(is_), len(oo))
    return is_[0]["trades"], oo[0]["trades"]


def main():
    df = c.carregar("WIN@")                                   # UTC ingenuo (BRT + 3h)
    d1 = rp.diarias(df)                                      # mesmas diarias que a estrategia recebe
    m5_all = df[["open", "high", "low", "close"]].resample("5min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    t_is, t_oos = trades_da_celula()
    abas = []
    for nome, trs, exp_n, exp_liq in (("IS 2021–2024", t_is, 143, 4144.5), ("OOS 2025–2026", t_oos, 113, 4897.5)):
        por_dia = {}
        for t in trs:
            te, tx = pd.Timestamp(t["entry_ts"]) - pd.Timedelta(hours=3), pd.Timestamp(t["exit_ts"]) - pd.Timedelta(hours=3)
            por_dia.setdefault(te.date(), []).append((te, tx, t))
        dias = []
        for dia, ops in sorted(por_dia.items()):
            utc = pd.Timestamp(dia)
            sess = df[(df.index >= utc + pd.Timedelta(hours=9)) & (df.index < utc + pd.Timedelta(hours=24))]  # sessao em UTC
            atr = rp.atr_ate(d1, dia, 14)
            ab = float(sess.open.iloc[0]); abre_ts = sess.index[0] - pd.Timedelta(hours=3)
            m5 = m5_all[(m5_all.index >= sess.index[0]) & (m5_all.index <= sess.index[-1])]
            ops_j = []
            for te, tx, t in ops:
                s = 1 if t["side"] == "long" else -1
                ops_j.append({"te": te.strftime("%H:%M"), "ts": tx.strftime("%H:%M"), "d": s, "e": round(t["entry_price"]),
                              "x": round(t["exit_price"]), "sl": rp.nt(ab - s * BANDA * atr), "rs": round(t["pnl"], 2),
                              "mot": "stop" if t["reason"] == "STOP" else "zera (fim do pregão)"})
            liq = sum(o["rs"] for o in ops_j)
            dias.append({"dia": str(dia), "liq": round(liq, 2), "n": len(ops_j), "win": sum(o["rs"] > 0 for o in ops_j),
                         "t": [(i - pd.Timedelta(hours=3)).strftime("%H:%M") for i in m5.index],
                         "o": [round(v) for v in m5.open], "h": [round(v) for v in m5.high], "l": [round(v) for v in m5.low],
                         "c": [round(v) for v in m5.close], "ab": round(ab), "atr": round(atr),
                         "dec": (abre_ts + pd.Timedelta(minutes=90)).strftime("%H:%M"), "ops": ops_j})
        n = sum(d["n"] for d in dias); liq = round(sum(d["liq"] for d in dias), 2); w = sum(d["win"] for d in dias)
        assert n == exp_n and abs(liq - exp_liq) < 0.01, (nome, n, liq)
        abas.append({"nome": nome, "tot": {"n": n, "w": w, "liq": liq, "win": round(100 * w / n, 1), "dias": len(dias)}, "dias": dias})
        print(nome, n, liq, "dias com operacao:", len(dias), flush=True)

    html = TEMPLATE.replace("__ABAS__", json.dumps(abas, separators=(",", ":"))).replace("__PLOTLY__", PLOTLY.read_text(encoding="utf-8"))
    html = html.replace("__PAINEL__", PAINEL)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(OUT / "index.html", f"{(OUT / 'index.html').stat().st_size / 1e6:.1f} MB", flush=True)


PAINEL = r"""
<style>
#rp{padding:0}#rp>summary{padding:10px 12px;cursor:pointer;font-weight:600}#rp .corpo{padding:0 12px 12px}
#rp .lin{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:flex-end;margin:8px 0}
#rp label{display:flex;flex-direction:column;font-size:12px;color:var(--mut);gap:3px}
#rp input,#rp select{background:var(--bg);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:4px 8px;font:inherit;font-size:13px}
#rp input[type=number]{width:92px}#rp input[type=date]{width:140px}#rp input[type=text]{width:110px}
#rp .btn{background:var(--fg);color:var(--bg);border:0;border-radius:6px;padding:7px 16px;font-weight:600;cursor:pointer}
#rp .btn:disabled{opacity:.5;cursor:wait}#rp .sec{background:var(--card);color:var(--fg);border:1px solid var(--bd);font-weight:400;padding:4px 10px;font-size:12px}
#rp .barra{height:6px;background:var(--bd);border-radius:3px;overflow:hidden;margin:8px 0}#rp .barra i{display:block;height:100%;width:0;background:var(--g);transition:width .3s}
#rp .aviso{border:1px solid var(--r);border-radius:8px;padding:10px 12px;margin:10px 0}#rp pre{margin:6px 0;padding:8px;background:var(--bg);border:1px solid var(--bd);border-radius:6px;overflow:auto;user-select:all}
#rp .params{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px 14px;margin:8px 0}#rp .nota{color:var(--mut);font-size:12px;margin:6px 0}
#rp h4{margin:14px 0 4px;font-size:13px}#rp .res{overflow-x:auto}
</style>
<details class="card" id="rp"><summary>Replay com ticks reais <span style="font-weight:400;color:var(--mut)">· roda o EA tick a tick (bid/ask/last) com latência, num servidor local</span></summary><div class="corpo">
<div class="lin">
<label>início<input type="date" id="rp-ini" value="2026-09-01"></label>
<label>fim<input type="date" id="rp-fim" value="2026-09-30"></label>
<label>ativo<input type="text" id="rp-ativo" value="WINV26" list="rp-ativos"><datalist id="rp-ativos"><option>WINV26</option><option>WIN@D</option></datalist></label>
<label>latência (s)<input type="number" id="rp-lat" value="0" min="0" max="30" step="0.5"></label>
<label>modo<select id="rp-modo"><option value="fixa">fixa</option><option value="aleatoria">aleatória (0 a N s)</option></select></label>
<label>preenchimento da limite<select id="rp-fill"><option value="atravessar">atravessar (conservador)</option><option value="tocar">tocar (otimista)</option></select></label>
<button class="btn" id="rp-run">Rodar replay</button>
</div>
<details><summary class="nota">parâmetros do EA (iguais aos inputs do WinDeslocamentoMatinal.mq5)</summary><div class="params" id="rp-params"></div><button class="btn sec" id="rp-padrao">restaurar padrão</button></details>
<div id="rp-aviso"></div><div class="barra" id="rp-barra" hidden><i></i></div><div class="nota" id="rp-msg"></div>
<div class="res" id="rp-res"></div><div id="rp-hist" class="res"></div>
<div class="nota"><b>Preenchimento.</b> A fila do WIN não está calibrada. <b>Atravessar</b> (padrão): a limite só enche quando um negócio sai a preço <i>melhor</i> que ela (last &lt; limite na compra, last &gt; limite na venda) — tocar o preço não é preencher. <b>Tocar</b>: enche quando o last encosta no limite (ignora a fila, otimista). Nas duas, se o livro vem até a limite (ask ≤ limite na compra, bid ≥ limite na venda) executa no preço do livro.
Demais regras: decisão na virada para a M1 de abertura+90 min com M1 fechadas; limite no último fechamento (se já cruzou o livro, vai para bid na compra / ask na venda); prazo de 15 min; stop do outro lado da abertura reancorado ao preço executado, disparado pelo <i>last</i> e executado no bid/ask; zera 5 min antes do fim da sessão no bid/ask; 1 operação por dia; latência em toda ordem. Sem corretagem/emolumentos. Ticks só existem para os meses recentes (WINV26: desde abr/2026).</div>
</div></details>
<script>(()=>{
const PADRAO={minutos_decisao:90,janela_decisao_min:5,desloc_min_atr:0.3,banda_atr:0.05,periodo_atr:14,entrada_ttl_min:15,minutos_zerar:5,hora_fim:18,minuto_fim:25};
const ROT={minutos_decisao:'MinutosDecisao',janela_decisao_min:'JanelaDecisaoMin',desloc_min_atr:'DeslocMinATR',banda_atr:'BandaATR',periodo_atr:'PeriodoATR',entrada_ttl_min:'EntradaTTLMin',minutos_zerar:'MinutosZerar',hora_fim:'HoraFimPregao',minuto_fim:'MinutoFimPregao'};
const $=id=>document.getElementById(id),BASE=(location.protocol==='http:'&&location.hostname==='127.0.0.1'&&location.port==='8766')?'':'http://127.0.0.1:8766';
const CMD='cd C:\\Users\\Jeffe\\Documents\\study\\meta\n.\\.venv\\Scripts\\python.exe scripts/daytrade/win_deslocamento_replay_server.py';
const fm=v=>v==null?'—':v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}),cl=v=>v<0?'neg':'pos';
const box=$('rp-params');Object.keys(PADRAO).forEach(k=>box.insertAdjacentHTML('beforeend',`<label>${ROT[k]}<input type="number" step="any" data-k="${k}" value="${PADRAO[k]}"></label>`));
$('rp-padrao').onclick=()=>box.querySelectorAll('input').forEach(i=>i.value=PADRAO[i.dataset.k]);
const params=()=>{const o={fill:$('rp-fill').value};box.querySelectorAll('input').forEach(i=>{const k=i.dataset.k,v=parseFloat(i.value);if(!isNaN(v)&&v!==PADRAO[k])o[k]=v;});return o;};
const dif=p=>Object.entries(p).filter(([k,v])=>k==='fill'?v!=='atravessar':v!==PADRAO[k]).map(([k,v])=>`${k}=${v}`).join(', ');
function avisoServidor(){$('rp-aviso').innerHTML=`<div class="aviso"><b>O servidor do replay não está rodando.</b> No terminal, rode:<pre>${CMD}</pre>Depois volte aqui (ou abra <a href="http://127.0.0.1:8766/" style="color:var(--fg)">http://127.0.0.1:8766/</a>) e clique de novo. O terminal do MetaTrader 5 precisa estar aberto para baixar ticks que ainda não estão em cache. <button class="btn sec" id="rp-copia">copiar comando</button></div>`;
$('rp-copia').onclick=()=>{try{navigator.clipboard.writeText(CMD);$('rp-copia').textContent='copiado';}catch(e){}};}
function tabela(r){const m=r.por_mes.map(x=>`<tr><td>${x.mes}</td><td>${x.n}</td><td class="${cl(x.liquido)}">${fm(x.liquido)}</td><td>${fm(x.dd)}</td><td>${String(x.win).replace('.',',')}%</td><td>${x.pf==null?'—':fm(x.pf)}</td><td>${x.dias_neg}/${x.dias}</td><td>${fm(x.por_op)}</td></tr>`).join('');
const t=r.resumo;return `<table><tr><th>período</th><th>trades</th><th>líquido R$</th><th>DD máx R$</th><th>win%</th><th>fator de lucro</th><th>dias neg.</th><th>R$/op</th></tr>${m}<tr><td><b>total</b></td><td>${t.n}</td><td class="${cl(t.liquido)}"><b>${fm(t.liquido)}</b></td><td>${fm(t.dd)}</td><td>${String(t.win).replace('.',',')}%</td><td>${t.pf==null?'—':fm(t.pf)}</td><td>${t.dias_neg}/${t.dias}</td><td>${fm(t.por_op)}</td></tr></table>`;}
function mostra(r){const g=r.diag,dg=`<div class="nota">pregões: ${g.sinais} com sinal (${g.fills} preencheram, ${g.nao_encheu} não encheram no prazo), ${g.sem_sinal} sem sinal${g.sem_atr?', '+g.sem_atr+' sem ATR':''}${g.decisao_atrasada?', '+g.decisao_atrasada+' com decisão atrasada':''}${g.sem_decisao?', '+g.sem_decisao+' sem decisão':''}</div>`;
const sem=(r.avisos&&r.avisos.length?`<div class="nota" style="color:#e0a050">⚠ ${r.avisos.slice(0,5).join('<br>')}${r.avisos.length>5?'<br>… +'+(r.avisos.length-5)+' avisos':''}</div>`:'')+(r.dias_sem_ticks.length?`<div class="nota">sem ticks em: ${r.dias_sem_ticks.length>15?r.dias_sem_ticks.slice(0,15).join(', ')+' … (+'+(r.dias_sem_ticks.length-15)+')':r.dias_sem_ticks.join(', ')}</div>`:'');
const ops=r.trades.map(o=>`<tr><td>${o.te.slice(0,16)}</td><td>${o.tx.slice(0,16)}</td><td>${o.d>0?'compra':'venda'}</td><td>${o.pe}</td><td>${o.sl}</td><td>${o.px}</td><td>${o.mot}</td><td>${Math.round((o.px-o.pe)*o.d)} pts</td><td class="${cl(o.rs)}">${fm(o.rs)}</td></tr>`).join('');
const d=dif(r.params);
$('rp-res').innerHTML=`<h4>${r.ativo} · ${r.inicio} a ${r.fim} · latência ${r.latencia_s} s (${r.modo}) · preenchimento ${r.params.fill}${d?' · '+d:''}</h4>${tabela(r)}${dg}${sem}<details><summary class="nota">operações (${r.trades.length})</summary><table><tr><th>entrada</th><th>saída</th><th>lado</th><th>preço ent.</th><th>stop</th><th>preço saí.</th><th>saída por</th><th>pontos</th><th>R$</th></tr>${ops}</table></details>`;}
const HK='winDeslReplayHist';function hist(){try{return JSON.parse(localStorage.getItem(HK)||'[]');}catch(e){return [];}}
function guarda(r){const h=hist();h.unshift({q:new Date().toLocaleString('pt-BR'),ativo:r.ativo,ini:r.inicio,fim:r.fim,lat:r.latencia_s,modo:r.modo,fill:r.params.fill,dif:dif(r.params),t:r.resumo});try{localStorage.setItem(HK,JSON.stringify(h.slice(0,15)));}catch(e){}pinta();}
function pinta(){const h=hist();$('rp-hist').innerHTML=h.length?`<h4>Rodadas anteriores (mais recente primeiro)</h4><table><tr><th>quando</th><th>ativo</th><th>período</th><th>latência</th><th>preench.</th><th>ajustes</th><th>trades</th><th>líquido R$</th><th>DD R$</th><th>win%</th><th>FL</th></tr>${h.map(x=>`<tr><td>${x.q}</td><td>${x.ativo||''}</td><td>${x.ini} a ${x.fim}</td><td>${x.lat} s ${x.modo==='aleatoria'?'(alea.)':''}</td><td>${x.fill}</td><td>${x.dif||'padrão'}</td><td>${x.t.n}</td><td class="${cl(x.t.liquido)}">${fm(x.t.liquido)}</td><td>${fm(x.t.dd)}</td><td>${String(x.t.win).replace('.',',')}%</td><td>${x.t.pf==null?'—':fm(x.t.pf)}</td></tr>`).join('')}</table>`:'';}
pinta();
$('rp-run').onclick=async()=>{const btn=$('rp-run');$('rp-aviso').innerHTML='';
const req={inicio:$('rp-ini').value,fim:$('rp-fim').value,latencia_s:parseFloat($('rp-lat').value)||0,modo:$('rp-modo').value,ativo:$('rp-ativo').value.trim()||'WINV26',params:params()};
if(!req.inicio||!req.fim){$('rp-msg').textContent='escolha o período';return;}
let id;try{const r=await fetch(BASE+'/api/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});const j=await r.json();if(!r.ok){$('rp-msg').textContent=j.erro||'erro';return;}id=j.id;}catch(e){avisoServidor();return;}
btn.disabled=true;$('rp-barra').hidden=false;$('rp-res').innerHTML='';
const t=setInterval(async()=>{try{const j=await(await fetch(BASE+'/api/replay/'+id)).json();
$('rp-barra').firstElementChild.style.width=Math.round(100*(j.progresso||0))+'%';$('rp-msg').textContent=j.mensagem||'';
if(j.estado==='pronto'){clearInterval(t);btn.disabled=false;$('rp-barra').hidden=true;$('rp-msg').textContent='';mostra(j.resultado);guarda(j.resultado);}
else if(j.estado==='erro'){clearInterval(t);btn.disabled=false;$('rp-barra').hidden=true;$('rp-msg').textContent='';$('rp-aviso').innerHTML=`<div class="aviso"><b>Erro no replay:</b> ${j.erro}</div>`;}}
catch(e){clearInterval(t);btn.disabled=false;$('rp-barra').hidden=true;avisoServidor();}},800);};
})();</script>
"""

TEMPLATE = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Win deslocamento matinal</title><script>__PLOTLY__</script>
<style>:root{--bg:#0e1116;--fg:#e6e9ee;--mut:#8a93a3;--card:#161b22;--bd:#262d38;--g:#4ade80;--r:#f87171;--ab:#fbbf24;--lim:#60a5fa}
@media (prefers-color-scheme:light){:root{--bg:#f6f7f9;--fg:#15181d;--mut:#5b6472;--card:#fff;--bd:#dde1e7;--g:#15803d;--r:#b91c1c;--ab:#b45309;--lim:#1d4ed8}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 8px}.sub{color:var(--mut);margin-bottom:12px}.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:12px;margin-bottom:16px}
.h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-weight:600}.pos{color:var(--g)}.neg{color:var(--r)}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}th,td{padding:3px 8px;text-align:right;border-bottom:1px solid var(--bd)}th:first-child,td:first-child{text-align:left}
.chart{height:460px}summary{cursor:pointer}.rz{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer;margin-right:8px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}nav button{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;font-weight:600}nav button.on{background:var(--fg);color:var(--bg)}nav button.neg:not(.on){color:var(--r)}nav button.pos:not(.on){color:var(--g)}
#tests button{font-size:13px;padding:6px 14px;text-align:left}#tests small{display:block;font-weight:400;opacity:.8}</style></head><body><main>
<h1>win_deslocamento_matinal · WIN, célula congelada, fila P2</h1>
__PAINEL__
<nav id="tests"></nav><div class="sub" id="sub"></div><nav id="meses"></nav><nav id="nav"></nav><div id="view"></div></main>
<script>const ABAS=__ABAS__;const f=v=>v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const tests=document.getElementById('tests'),meses=document.getElementById('meses'),nav=document.getElementById('nav'),view=document.getElementById('view'),sub=document.getElementById('sub');
const dark=!matchMedia('(prefers-color-scheme:light)').matches,fg=dark?'#e6e9ee':'#15181d',gr=dark?'#262d38':'#dde1e7',cAb=dark?'#fbbf24':'#b45309',cLim=dark?'#60a5fa':'#1d4ed8',cMut=dark?'#8a93a3':'#5b6472';
let A=null,M=[],D=[],faixa=null,diaTodo=null;function resetaZoom(){if(faixa)Plotly.relayout('chart',faixa);}function verDia(){if(diaTodo)Plotly.relayout('chart',diaTodo);}
const cls=v=>v<0?'neg':'pos';
ABAS.forEach((z,k)=>tests.insertAdjacentHTML('beforeend',`<button data-k="${k}" class="${cls(z.tot.liq)}">${z.nome}<small>${z.tot.n} operações · R$ ${f(z.tot.liq)}</small></button>`));
function aba(k){A=ABAS[k];tests.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.k===k));const z=A.tot;
sub.innerHTML=`<b>${A.nome}</b> · ${z.n} operações em ${z.dias} pregões · <b>win: ${z.w}/${z.n} · loss: ${z.n-z.w}/${z.n}</b> · líquido <b class="${cls(z.liq)}">R$ ${f(z.liq)}</b> · ${String(z.win).replace('.',',')}% de win · R$/op <b>${f(z.liq/z.n)}</b><br>Regra: aos 90 min de pregão (10:30), se o preço está a ≥ 0,3 ATR14 da abertura e nunca fechou do outro lado dela (banda 0,05 ATR), entra a favor com limite no último preço (prazo 15 min); stop na linha da abertura, sem alvo, zera no fim do pregão; 1 contrato, 1 operação por dia. Motor do repo, M1, fila P2 (76.000/76.000), capital reposto por pregão. Compra ▲, venda ▼, saída ✕; a linha tracejada liga entrada à saída.`;
const mm={};A.dias.forEach(d=>{const m=d.dia.slice(0,7);(mm[m]=mm[m]||{m,liq:0,n:0}).liq+=d.liq;mm[m].n+=d.n;});M=Object.values(mm);
meses.innerHTML='';M.forEach((m,i)=>meses.insertAdjacentHTML('beforeend',`<button data-m="${i}" class="${cls(m.liq)}" title="${m.n} op · R$ ${f(m.liq)}">${m.m}</button>`));mes(0);}
function mes(i){const m=M[i];meses.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.m===i));
D=A.dias.filter(d=>d.dia.slice(0,7)===m.m);nav.innerHTML='';D.forEach((d,j)=>nav.insertAdjacentHTML('beforeend',`<button data-i="${j}" class="${cls(d.liq)}">${d.dia.slice(8)}</button>`));mostra(0);}
function mostra(i){
const d=D[i];nav.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.i===i));
const pts=o=>{const v=(o.x-o.e)*o.d;return (v>0?'+':'')+v+' pts';};
const rows=d.ops.map(o=>`<tr><td>${o.te}</td><td>${o.ts}</td><td>${o.d>0?'compra':'venda'}</td><td>${o.e}</td><td>${o.sl}</td><td>${o.x}</td><td>${o.mot}</td><td class="${cls(o.rs)}">${pts(o)}</td><td class="${cls(o.rs)}">${f(o.rs)}</td></tr>`).join('');
view.innerHTML=`<section class="card"><div class="h"><span>${d.dia} · abertura ${d.ab} · ATR14 ${d.atr}</span><span>win: ${d.win}/${d.n} · loss: ${d.n-d.win}/${d.n} · <span class="${cls(d.liq)}">R$ ${f(d.liq)}</span></span></div><div class="chart" id="chart"></div><button class="rz" onclick="resetaZoom()">centralizar na operação</button><button class="rz" onclick="verDia()">dia inteiro</button>
<details><summary>operações</summary><table><tr><th>entrada</th><th>saída</th><th>lado</th><th>preço ent.</th><th>stop</th><th>preço saí.</th><th>saída por</th><th>pontos</th><th>R$</th></tr>${rows}</table></details></section>`;
const X=d.t.map(h=>d.dia+' '+h),xt=h=>d.dia+' '+h,x0=X[0],x1=X[X.length-1];
const stops=d.ops.map(o=>o.sl);const lo=Math.min(...d.l,...stops),hi=Math.max(...d.h,...stops),mg=(hi-lo)*0.04;
// janela inicial: entrada e saida no centro, com folga antes e depois (>= 60 min ou a duracao da operacao)
const ms=s=>new Date(s.replace(' ','T')).getTime(),p2=n=>String(n).padStart(2,'0'),
 ds=t=>{const z=new Date(t);return `${z.getFullYear()}-${p2(z.getMonth()+1)}-${p2(z.getDate())} ${p2(z.getHours())}:${p2(z.getMinutes())}`;};
const tE=Math.min(...d.ops.map(o=>ms(xt(o.te)))),tS=Math.max(...d.ops.map(o=>ms(xt(o.ts)))),dur=tS-tE,
 meio=(tE+tS)/2,met=dur/2+Math.max(60*60000,dur);
let w0=meio-met,w1=meio+met;const a0=ms(x0),a1=ms(x1);
if(w0<a0){w1=Math.min(a1,w1+(a0-w0));w0=a0;}if(w1>a1){w0=Math.max(a0,w0-(w1-a1));w1=a1;}
const dentro=X.map(x=>{const t=ms(x);return t>=w0&&t<=w1;}),
 ys=[...d.l.filter((v,j)=>dentro[j]),...d.h.filter((v,j)=>dentro[j]),...stops,...d.ops.map(o=>o.e),...d.ops.map(o=>o.x),d.ab],
 wlo=Math.min(...ys),whi=Math.max(...ys),wmg=(whi-wlo)*0.06;
faixa={'xaxis.range':[ds(w0),ds(w1)],'yaxis.range':[wlo-wmg,whi+wmg],'xaxis.autorange':false,'yaxis.autorange':false};
diaTodo={'xaxis.range':[x0,x1],'yaxis.range':[lo-mg,hi+mg],'xaxis.autorange':false,'yaxis.autorange':false};
const dj=d.o.map((v,j)=>v===d.c[j]),nd=a=>a.map((v,j)=>dj[j]?null:v),so=a=>a.map((v,j)=>dj[j]?v:null);
const tr=[{type:'candlestick',x:X,open:nd(d.o),high:nd(d.h),low:nd(d.l),close:nd(d.c),name:'WIN M5',increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#ffffff'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#000000'}},
{type:'candlestick',x:X,open:so(d.o),high:so(d.h),low:so(d.l),close:so(d.c),name:'doji',showlegend:false,increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'}}];
const H=(y,nome,cor,dash,w)=>tr.push({x:[x0,x1],y:[y,y],mode:'lines',name:nome,line:{color:cor,width:w,dash:dash},hovertext:nome+' '+Math.round(y),hoverinfo:'text'});
const b=0.05*d.atr,L=0.3*d.atr;
H(d.ab,'abertura '+d.ab,cAb,'solid',1.5);H(d.ab+b,'banda +0,05 ATR',cAb,'dash',0.8);H(d.ab-b,'banda −0,05 ATR',cAb,'dash',0.8);
H(d.ab+L,'+0,3 ATR (limiar do sinal)',cLim,'dot',1);H(d.ab-L,'−0,3 ATR (limiar do sinal)',cLim,'dot',1);
tr.push({x:[xt(d.dec),xt(d.dec)],y:[lo-mg,hi+mg],mode:'lines',name:'decisão '+d.dec,line:{color:cMut,width:1,dash:'dashdot'},hoverinfo:'skip'});
d.ops.forEach(o=>{const c=o.rs>=0?'#4ade80':'#f87171';
tr.push({x:[xt(o.te),xt(o.ts)],y:[o.sl,o.sl],mode:'lines',name:'stop '+o.sl,line:{color:'#f87171',width:1.5},hovertext:'stop '+o.sl,hoverinfo:'text'});
tr.push({x:[xt(o.te),xt(o.ts)],y:[o.e,o.x],mode:'lines',line:{color:c,width:1.5,dash:'dot'},showlegend:false,hoverinfo:'skip'});
tr.push({x:[xt(o.te)],y:[o.e],mode:'markers',marker:{symbol:o.d>0?'triangle-up':'triangle-down',size:12,color:c,line:{color:fg,width:1}},showlegend:false,hovertext:`${o.d>0?'compra':'venda'} ${o.te} @ ${o.e}`,hoverinfo:'text'});
tr.push({x:[xt(o.ts)],y:[o.x],mode:'markers',marker:{symbol:'x',size:9,color:c,line:{color:c,width:2}},showlegend:false,hovertext:`saída ${o.ts} @ ${o.x}<br>${o.mot} · ${pts(o)} · R$ ${f(o.rs)}`,hoverinfo:'text'});});
Plotly.newPlot('chart',tr,{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:fg},dragmode:'pan',margin:{l:55,r:10,t:10,b:30},xaxis:{rangeslider:{visible:false},gridcolor:gr},yaxis:{gridcolor:gr},legend:{orientation:'h',y:1.12}},{responsive:true,scrollZoom:true,doubleClick:'reset'}).then(resetaZoom);}
tests.addEventListener('click',e=>{const b=e.target.closest('button');if(b)aba(+b.dataset.k);});
meses.addEventListener('click',e=>{const b=e.target.closest('button');if(b)mes(+b.dataset.m);});
nav.addEventListener('click',e=>{const b=e.target.closest('button');if(b)mostra(+b.dataset.i);});
aba(0);
</script></body></html>"""

if __name__ == "__main__":
    main()
