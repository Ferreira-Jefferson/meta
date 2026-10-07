# -*- coding: utf-8 -*-
"""Monta `.claude/artifacts/g21_retangulo/index.html` (MESMO caminho de
antes, para o atalho do dono continuar funcionando) a partir de
`replay_g29.json` -- agora com o filtro de EMA34, o PADRÃO ATUAL da
candidata nº1 (ver ORQUESTRACAO.md). Mesmo molde visual de antes (nav de
testes -> nav de dias -> candle M5 + marcadores de operação), com 2
elementos novos: a linha laranja da EMA34 (o que decide se a operação
passa) e uma 3ª aba (Setembro/26, o teste final que reprovou).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DATA = Path(__file__).parent / "replay_g29.json"
OUT_DIR = ROOT / ".claude" / "artifacts" / "g21_retangulo"
OUT = OUT_DIR / "index.html"

HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>G21+EMA34 WIN · replay</title><script src="plotly.min.js"></script>
<style>:root{--bg:#0e1116;--fg:#e6e9ee;--mut:#8a93a3;--card:#161b22;--bd:#262d38;--g:#4ade80;--r:#f87171;--box:#f0b429;--ema:#fb923c}
@media (prefers-color-scheme:light){:root{--bg:#f6f7f9;--fg:#15181d;--mut:#5b6472;--card:#fff;--bd:#dde1e7;--g:#15803d;--r:#b91c1c;--box:#b45309;--ema:#c2410c}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 8px}.sub{color:var(--mut);margin-bottom:16px;font-size:12.5px}.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:12px;margin-bottom:16px}
.h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-weight:600}.pos{color:var(--g)}.neg{color:var(--r)}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}th,td{padding:3px 8px;text-align:right;border-bottom:1px solid var(--bd)}th:first-child,td:first-child{text-align:left}
.chart{height:460px}summary{cursor:pointer}.rz{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer;margin-right:8px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}nav button{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;font-weight:600}
nav button.on{background:var(--fg);color:var(--bg)}nav button.neg:not(.on){color:var(--r)}nav button.pos:not(.on){color:var(--g)}
#tests button{font-size:13px;padding:8px 16px;text-align:left}#tests small{display:block;font-weight:400;opacity:.8}
.legenda{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--mut);margin:6px 0 2px}
.legenda span{display:inline-flex;align-items:center;gap:5px}.sw{width:11px;height:11px;border-radius:2px;display:inline-block}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;background:var(--ema);color:#1a0f02;padding:2px 8px;border-radius:4px;margin-left:8px;vertical-align:middle}
</style></head><body><main>
<h1>Retângulo + EMA34 <span class="badge">padrão atual</span><br><span style="font-weight:400;color:var(--mut);font-size:15px">WIN · replay de operações</span></h1>
<p class="sub">Candidata nº1 da busca de EA, agora SEMPRE com o filtro de EMA34 (venda só com fechamento ≤ EMA34, compra só com fechamento ≥ EMA34) — substitui o retângulo sem filtro a partir de 2026-10-05, porque a EMA34 melhorou o resultado nos 3 períodos abaixo sem exceção. <b>Ainda NÃO é uma estratégia validada para operar ao vivo</b>: setembro continua negativo, com 80,8% de chance de ruína projetada a partir do próprio mês. Stop 0,45× a largura do retângulo, alvo 0,90× (2× o stop), capital de teste R$1.000. Entrada e alvo por ordem-limite real, só o stop a mercado. Compra ▲, venda ▼, saída ✕; linha pontilhada verde/vermelha liga entrada à saída pelo resultado.</p>
<nav id="tests"></nav><div class="sub" id="sub"></div>
<div class="legenda">
<span><i class="sw" style="background:var(--g)"></i>operação com lucro</span>
<span><i class="sw" style="background:var(--r)"></i>operação com prejuízo</span>
<span><i class="sw" style="background:var(--ema)"></i>EMA34 (decide se a operação passa)</span>
<span><i class="sw" style="background:var(--box);opacity:.6"></i>retângulo reconstruído (topo/piso)</span>
</div>
<nav id="nav"></nav><div id="view"></div>
</main>
<script>const TESTES = __DATA__;
const tests=document.getElementById('tests'),nav=document.getElementById('nav'),view=document.getElementById('view'),sub=document.getElementById('sub');
const dark=!matchMedia('(prefers-color-scheme:light)').matches,fg=dark?'#e6e9ee':'#15181d',gr=dark?'#262d38':'#dde1e7',boxc=dark?'#f0b429':'#b45309',emac=dark?'#fb923c':'#c2410c';
const f=v=>v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
let D=[],faixa=null;function resetaZoom(){if(faixa)Plotly.relayout('chart',faixa);}
TESTES.forEach((z,k)=>tests.insertAdjacentHTML('beforeend',`<button data-k="${k}" class="${z.tot.liq<0?'neg':'pos'}">${z.hora}<small>${z.tot.n} operações · ${z.tot.dias} pregões · R$ ${f(z.tot.liq)} · ${String(z.tot.win).replace('.',',')}% win</small></button>`));
function teste(k){const z=TESTES[k];D=z.dias;
tests.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.k===k));
sub.innerHTML=`<b>${z.hora}</b> · ${z.tot.n} operações em ${z.tot.dias} pregões · <b>win: ${z.tot.w}/${z.tot.n} · loss: ${z.tot.n-z.tot.w}/${z.tot.n}</b> · líquido <b class="${z.tot.liq<0?'neg':'pos'}">R$ ${f(z.tot.liq)}</b> · ${String(z.tot.win).replace('.',',')}% de win · ${z.params}<br>${z.nota}`;
nav.innerHTML='';D.forEach((d,i)=>nav.insertAdjacentHTML('beforeend',`<button data-i="${i}" class="${d.liq<0?'neg':d.n?'pos':''}">${d.dia.slice(8)}${d.n?'':' ·'}</button>`));
mostra(0);}
function mostra(i){
const d=D[i];nav.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.i===i));
const pts=o=>{const v=Math.round(o.rs/0.2);return (v>0?'+':'')+v+' pts';};
const rows=d.ops.map(o=>`<tr><td>${o.te.slice(11,16)}</td><td>${o.ts.slice(11,16)}</td><td>${o.d>0?'compra':'venda'}</td><td>${o.e}</td><td>${o.x}</td><td>${o.mot}</td><td class="${o.rs<0?'neg':'pos'}">${pts(o)}</td><td class="${o.rs<0?'neg':'pos'}">${f(o.rs)}</td></tr>`).join('');
view.innerHTML=`<section class="card"><div class="h"><span>${d.dia}</span><span>${d.n?`win: ${d.win}/${d.n} · loss: ${d.n-d.win}/${d.n} · `:'sem operação · '}<span class="${d.liq<0?'neg':d.n?'pos':''}">R$ ${f(d.liq)}</span></span></div><div class="chart" id="chart"></div><button class="rz" onclick="resetaZoom()">resetar zoom (zoom out)</button>
${d.n?`<details><summary>operações (${d.n})</summary><table><tr><th>entrada</th><th>saída</th><th>lado</th><th>preço ent.</th><th>preço saí.</th><th>saída por</th><th>pontos</th><th>R$</th></tr>${rows}</table></details>`:''}</section>`;
if(!d.t.length){return;}
const lo=Math.min(...d.l),hi=Math.max(...d.h),mg=(hi-lo)*0.04;faixa={'xaxis.range':[d.t[0],d.t[d.t.length-1]],'yaxis.range':[lo-mg,hi+mg],'xaxis.autorange':false,'yaxis.autorange':false};
const dj=d.o.map((v,j)=>v===d.c[j]),nd=a=>a.map((v,j)=>dj[j]?null:v),so=a=>a.map((v,j)=>dj[j]?v:null);
const tr=[{type:'candlestick',x:d.t,open:nd(d.o),high:nd(d.h),low:nd(d.l),close:nd(d.c),name:'WIN@ M5',increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#ffffff'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#000000'}},
{type:'candlestick',x:d.t,open:so(d.o),high:so(d.h),low:so(d.l),close:so(d.c),name:'doji',showlegend:false,increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'}},
{x:d.t,y:d.ema,mode:'lines',name:'EMA34',line:{color:emac,width:1.6},connectgaps:true}];
d.ops.forEach(o=>{const c=o.rs>=0?'#4ade80':'#f87171';
if(o.box){tr.push({x:[o.box.ini,o.te],y:[o.box.topo,o.box.topo],mode:'lines',line:{color:boxc,width:1.3,dash:'dash'},showlegend:false,hoverinfo:'skip',opacity:.75});
tr.push({x:[o.box.ini,o.te],y:[o.box.piso,o.box.piso],mode:'lines',line:{color:boxc,width:1.3,dash:'dash'},showlegend:false,hoverinfo:'skip',opacity:.75});}
tr.push({x:[o.te,o.ts],y:[o.e,o.x],mode:'lines',line:{color:c,width:1.5,dash:'dot'},showlegend:false,hoverinfo:'skip'});
tr.push({x:[o.te],y:[o.e],mode:'markers',marker:{symbol:o.d>0?'triangle-up':'triangle-down',size:11,color:c,line:{color:fg,width:1}},showlegend:false,hovertext:`${o.d>0?'compra':'venda'} ${o.te.slice(11,16)} @ ${o.e}`,hoverinfo:'text'});
tr.push({x:[o.ts],y:[o.x],mode:'markers',marker:{symbol:'x',size:8,color:c},showlegend:false,hovertext:`saída ${o.mot} ${o.ts.slice(11,16)} @ ${o.x} · ${pts(o)} · R$ ${f(o.rs)}`,hoverinfo:'text'});});
Plotly.newPlot('chart',tr,{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:fg},dragmode:'pan',margin:{l:55,r:10,t:10,b:30},xaxis:{rangeslider:{visible:false},gridcolor:gr},yaxis:{gridcolor:gr},legend:{orientation:'h',y:1.08}},{responsive:true,scrollZoom:true,doubleClick:'reset'}).then(resetaZoom);}
tests.addEventListener('click',e=>{const b=e.target.closest('button');if(b)teste(+b.dataset.k);});
nav.addEventListener('click',e=>{const b=e.target.closest('button');if(b)mostra(+b.dataset.i);});
teste(0);
</script></body></html>"""


def main() -> None:
    data = DATA.read_text(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HTML.replace("__DATA__", data), encoding="utf-8")
    print(f"Salvo em {OUT} ({OUT.stat().st_size / 1_048_576:.2f} MB)")


if __name__ == "__main__":
    main()
