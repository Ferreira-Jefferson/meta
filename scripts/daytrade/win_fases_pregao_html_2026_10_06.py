"""Gera .claude/artifacts/win_fases_pregao/index.html a partir de data/win_fases_pregao_6m.csv (dados embutidos)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data" / "win_fases_pregao_6m.csv"
OUT = ROOT / ".claude" / "artifacts" / "win_fases_pregao" / "index.html"
FLAGS = ROOT / "scripts" / "daytrade" / "win_fases_correlacao_2026_10_06" / "lente4_cetica_integridade" / "dias_flag.csv"

COLS = ["data", "dia_semana", "pre_hora_leilao", "pre_preco_inicio", "pre_preco_fechamento", "pre_volume", "pre_negocios",
        "pregao_hora_inicio", "pregao_hora_fim", "pregao_preco_inicio", "pregao_maxima", "pregao_minima",
        "pregao_preco_fechamento", "pregao_volume", "pregao_negocios",
        "pos_hora_leilao", "pos_preco_inicio", "pos_preco_fechamento", "pos_volume", "pos_negocios",
        "volume_total_dia", "observacao", "grade_preabertura", "grade_negociacao", "grade_call"]

HTML = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WIN — fases do pregão</title>
<style>
:root{--bg:#f7f6f2;--panel:#fff;--ink:#1d1d1b;--mut:#6b6a64;--line:#e3e1d9;--pre:#2f6db5;--preg:#3d7a3a;--pos:#a5562a;--warn:#fff3cd;--warnink:#7a5b00;--up:#2e7d32;--dn:#c62828}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--mut:#9c9a92;--line:#33322e;--pre:#7fb0ef;--preg:#8cc787;--pos:#e39a6d;--warn:#3a3000;--warnink:#f0d36b;--up:#81c784;--dn:#ef9a9a}}
:root[data-theme="dark"]{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--mut:#9c9a92;--line:#33322e;--pre:#7fb0ef;--preg:#8cc787;--pos:#e39a6d;--warn:#3a3000;--warnink:#f0d36b;--up:#81c784;--dn:#ef9a9a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1600px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:16px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.tile .k{font-size:12px;color:var(--mut)}.tile .v{font:600 18px/1.3 ui-monospace,Consolas,monospace}
.tile.pre{border-top:3px solid var(--pre)}.tile.preg{border-top:3px solid var(--preg)}.tile.pos{border-top:3px solid var(--pos)}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
select,button{font:inherit;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 9px}
.note{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:14px;color:var(--mut);font-size:13px}
.note b{color:var(--ink)}
.tbl{overflow:auto;max-height:75vh;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{border-collapse:separate;border-spacing:0;font:12.5px/1.35 ui-monospace,Consolas,monospace;white-space:nowrap;width:100%}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right}
td.l,th.l{text-align:left}
thead th{position:sticky;background:var(--panel);z-index:2;font-family:system-ui,sans-serif;font-weight:600}
thead tr:first-child th{top:0;font-size:13px}thead tr:nth-child(2) th{top:29px;font-size:11.5px;color:var(--mut);cursor:pointer}
thead tr:nth-child(2) th:hover{color:var(--ink)}
th.g-pre{color:var(--pre);border-bottom:2px solid var(--pre)}th.g-preg{color:var(--preg);border-bottom:2px solid var(--preg)}th.g-pos{color:var(--pos);border-bottom:2px solid var(--pos)}
td.s{border-left:2px solid var(--line)}
td.d,th.d{position:sticky;left:0;background:var(--panel);z-index:1}thead th.d{z-index:3}
tr.flag td{background:var(--warn)}tr.flag td.obs{color:var(--warnink)}
tr:hover td{filter:brightness(0.96)}
.up{color:var(--up)}.dn{color:var(--dn)}.obs{text-align:left;font-family:system-ui,sans-serif;color:var(--mut)}
.mut{color:var(--mut)}
.tabs{display:flex;gap:6px;margin-bottom:14px;border-bottom:1px solid var(--line)}
.tab{border:none;border-bottom:2px solid transparent;border-radius:0;background:none;padding:8px 12px;color:var(--mut);cursor:pointer}
.tab.on{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}
</style></head><body><div class="wrap">
<h1>WIN — pré-pregão, pregão e pós-pregão</h1>
<p class="sub" id="sub"></p>
<div class="tabs"><button class="tab on" data-t="fases">Fases do pregão</button><button class="tab" data-t="var">Variações dia a dia</button><button class="tab" data-t="seq">Contra o estágio anterior</button></div>
<div class="tiles" id="tiles"></div>
<div class="note" id="note-fases"><b>Como ler.</b> <b style="color:var(--pre)">Pré-pregão</b> (pré-abertura: Início = 08:55 pela grade B3, Fim = instante do leilão): não há negócio, só ofertas; o único negócio é o <b>leilão de abertura</b>, que cruza tudo num preço só — por isso início = fechamento. <b style="color:var(--preg)">Pregão</b>: negociação contínua do leilão de abertura até 18:25. <b style="color:var(--pos)">Pós-pregão</b> (call de fechamento: Início = 18:25 pela grade B3, Fim = instante do leilão, ~18:31): de novo só o leilão. Fronteiras pela grade oficial da B3 vigente em cada data (OC 005/2026-PRE). Fonte: negócios (ticks) do WIN$N no MT5. Linhas em amarelo: abertura sem leilão identificável na fonte.</div>
<div class="note" id="note-var" hidden><b>Como ler.</b> <b>Var. preço</b> em pontos: <b style="color:var(--preg)">pregão</b> = fechamento − abertura do pregão. Cada leilão tem um preço só (abertura = fechamento, variação sempre 0), então nos leilões ela é medida contra a fase anterior: <b style="color:var(--pre)">pré</b> = leilão de abertura − call de fechamento do <b>dia anterior</b>; <b style="color:var(--pos)">pós</b> = call de fechamento − fechamento do pregão do mesmo dia. <b>Δ Volume</b>, <b>Δ Negócios</b> e <b>Δ Vol/neg.</b> (tamanho médio do negócio = volume ÷ negócios): variação % contra a <b>mesma fase do pregão anterior</b>. "—" = sem pregão anterior na tabela, ou fase sem negócio (linhas em amarelo e o dia seguinte a elas).</div>
<div class="note" id="note-seq" hidden><b>Como ler.</b> Cada fase comparada com a fase que veio <b>imediatamente antes</b> dela: <b style="color:var(--pre)">pré</b> contra o <b>pós do dia anterior</b>, <b style="color:var(--preg)">pregão</b> contra o <b>pré do mesmo dia</b>, <b style="color:var(--pos)">pós</b> contra o <b>pregão do mesmo dia</b>. <b>Var. preço</b> em pontos: pré = leilão de abertura − call de D−1; pregão = fechamento do pregão − leilão de abertura; pós = call − fechamento do pregão. <b>Volume</b>, <b>Negócios</b> e <b>Vol/neg.</b> aparecem como <b>razão (×)</b> = fase ÷ fase anterior, porque as fases têm tamanhos muito diferentes (pregão ~300× o leilão; call ~0,1% do pregão) e um Δ% daria +30.000% ou −99,9% sem distinguir um dia do outro. <b>⚠</b> = troca de contrato no WIN$N (15/04, 17/06, 12/08): a var. do pré nesses dias é o degrau entre contratos, não gap de mercado. "—" = fase sem negócio na fonte (31/07) ou sem dia anterior. Dias com ticks faltando na fonte (06/05, 10/08, 24/09) estão completados pelo M1 (ver Observação); o leilão de 24/09 e seu volume são estimados.</div>
<div class="bar"><label>Mês <select id="mes"><option value="">todos</option></select></label>
<button id="ord">Mais antigo primeiro</button><span class="mut" id="cnt"></span></div>
<div class="tbl"><table><thead><tr id="grp"></tr><tr id="hdr"></tr></thead><tbody id="tb"></tbody></table></div>
</div>
<script>
const D = __DATA__;
const nf = new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0});
const pf = new Intl.NumberFormat('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1});
const f = v => v==null||v===''||Number.isNaN(v) ? '—' : nf.format(v);
const hm = v => v ? v.slice(0,8) : '—';
const sg = (v,txt) => v==null||!isFinite(v) ? '—' : `<span class="${v>0?'up':v<0?'dn':''}">${v>0?'+':''}${txt}</span>`;
const pts = v => sg(v, v==null?'':nf.format(v));
const pct = v => sg(v, v==null?'':pf.format(v)+'%');
const dt = r => r.data.split('-').reverse().join('/');
const CF = [
 ['data','Data','l d',dt],['dia_semana','Dia','l',r=>r.dia_semana],
 ['grade_preabertura','Início','s',r=>r.grade_preabertura+':00'],['pre_hora_leilao','Fim','',r=>hm(r.pre_hora_leilao)],['pre_preco_inicio','Abertura','',r=>f(r.pre_preco_inicio)],
 ['pre_preco_fechamento','Fech.','',r=>f(r.pre_preco_fechamento)],['pre_volume','Volume','',r=>f(r.pre_volume)],['pre_negocios','Neg.','',r=>f(r.pre_negocios)],
 ['pregao_hora_inicio','Início','s',r=>hm(r.pregao_hora_inicio)],['pregao_hora_fim','Fim','',r=>hm(r.pregao_hora_fim)],
 ['pregao_preco_inicio','Abertura','',r=>f(r.pregao_preco_inicio)],['pregao_maxima','Máxima','',r=>f(r.pregao_maxima)],['pregao_minima','Mínima','',r=>f(r.pregao_minima)],
 ['pregao_preco_fechamento','Fech.','',r=>f(r.pregao_preco_fechamento)],
 ['pregao_volume','Volume','',r=>f(r.pregao_volume)],['pregao_negocios','Neg.','',r=>f(r.pregao_negocios)],
 ['amp','Amplitude','',r=>f(r.amp)],
 ['grade_call','Início','s',r=>r.grade_call+':00'],['pos_hora_leilao','Fim','',r=>hm(r.pos_hora_leilao)],['pos_preco_inicio','Abertura','',r=>f(r.pos_preco_inicio)],
 ['pos_preco_fechamento','Fech.','',r=>f(r.pos_preco_fechamento)],['pos_volume','Volume','',r=>f(r.pos_volume)],['pos_negocios','Neg.','',r=>f(r.pos_negocios)],
 ['volume_total_dia','Vol. total dia','s',r=>f(r.volume_total_dia)],['observacao','Observação','obs',r=>r.observacao||''],
];
const GF = [['',2,'l d'],['Pré-pregão (leilão de abertura)',6,'g-pre'],['Pregão',9,'g-preg'],['Pós-pregão (call de fechamento)',6,'g-pos'],['',2,'']];
const FASES=[['pre','pre'],['preg','pregao'],['pos','pos']];
const CV = [['data','Data','l d',dt],['dia_semana','Dia','l',r=>r.dia_semana]];
FASES.forEach(([g,k])=>CV.push(
 [`${k}_dpx`,'Var. preço (pts)','s',r=>pts(r[`${k}_dpx`])],[`${k}_dvol`,'Δ Volume','',r=>pct(r[`${k}_dvol`])],
 [`${k}_dneg`,'Δ Negócios','',r=>pct(r[`${k}_dneg`])],[`${k}_dvpn`,'Δ Vol/neg.','',r=>pct(r[`${k}_dvpn`])]));
const GV = [['',2,'l d'],['Pré-pregão (leilão de abertura)',4,'g-pre'],['Pregão',4,'g-preg'],['Pós-pregão (call de fechamento)',4,'g-pos']];
// derivados: D vem em ordem cronologica; "anterior" = pregao anterior presente na tabela
D.forEach((r,i)=>{
 r.amp=(r.pregao_maxima!=null)?r.pregao_maxima-r.pregao_minima:null;
 const q=i?D[i-1]:null;
 r.pregao_dpx=(r.pregao_preco_fechamento!=null&&r.pregao_preco_inicio!=null)?r.pregao_preco_fechamento-r.pregao_preco_inicio:null;
 r.pre_dpx=(q&&q.pos_preco_fechamento!=null&&r.pre_preco_inicio!=null)?r.pre_preco_inicio-q.pos_preco_fechamento:null;
 r.pos_dpx=(r.pos_preco_fechamento!=null&&r.pregao_preco_fechamento!=null)?r.pos_preco_fechamento-r.pregao_preco_fechamento:null;
 const ok=x=>x!=null&&x>0;
 FASES.forEach(([g,k])=>{
  const v=r[`${k}_volume`],n=r[`${k}_negocios`],vq=q&&q[`${k}_volume`],nq=q&&q[`${k}_negocios`];
  r[`${k}_dvol`]=q&&ok(v)&&ok(vq)?(v/vq-1)*100:null;
  r[`${k}_dneg`]=q&&ok(n)&&ok(nq)?(n/nq-1)*100:null;
  r[`${k}_dvpn`]=q&&ok(v)&&ok(n)&&ok(vq)&&ok(nq)?((v/n)/(vq/nq)-1)*100:null;
 });
});
const ROLAGEM = __ROLAGEM__;
const rf = new Intl.NumberFormat('pt-BR',{maximumSignificantDigits:3});
const rz = v => v==null||!isFinite(v) ? '—' : rf.format(v)+'×';
D.forEach((r,i)=>{
 const q=i?D[i-1]:null, ok=x=>x!=null&&x>0;
 const rat=(a,b)=>ok(a)&&ok(b)?a/b:null, vpn=(v,n)=>ok(v)&&ok(n)?v/n:null;
 r.s_pre_px=r.pre_dpx;
 r.s_pre_vol=q?rat(r.pre_volume,q.pos_volume):null; r.s_pre_neg=q?rat(r.pre_negocios,q.pos_negocios):null;
 r.s_pre_vpn=q?rat(vpn(r.pre_volume,r.pre_negocios),vpn(q.pos_volume,q.pos_negocios)):null;
 r.s_preg_px=(r.pregao_preco_fechamento!=null&&ok(r.pre_preco_fechamento))?r.pregao_preco_fechamento-r.pre_preco_fechamento:null;
 r.s_preg_vol=rat(r.pregao_volume,r.pre_volume); r.s_preg_neg=rat(r.pregao_negocios,r.pre_negocios);
 r.s_preg_vpn=rat(vpn(r.pregao_volume,r.pregao_negocios),vpn(r.pre_volume,r.pre_negocios));
 r.s_pos_px=r.pos_dpx;
 r.s_pos_vol=rat(r.pos_volume,r.pregao_volume); r.s_pos_neg=rat(r.pos_negocios,r.pregao_negocios);
 r.s_pos_vpn=rat(vpn(r.pos_volume,r.pos_negocios),vpn(r.pregao_volume,r.pregao_negocios));
});
const CS = [['data','Data','l d',dt],['dia_semana','Dia','l',r=>r.dia_semana]];
[['pre','pré'],['preg','pregão'],['pos','pós']].forEach(([k])=>CS.push(
 [`s_${k}_px`,'Var. preço (pts)','s',r=>pts(r[`s_${k}_px`])+(k==='pre'&&ROLAGEM.includes(r.data)?' ⚠':'')],
 [`s_${k}_vol`,'Volume','',r=>rz(r[`s_${k}_vol`])],[`s_${k}_neg`,'Negócios','',r=>rz(r[`s_${k}_neg`])],[`s_${k}_vpn`,'Vol/neg.','',r=>rz(r[`s_${k}_vpn`])]));
const GS = [['',2,'l d'],['Pré ÷ pós do dia anterior',4,'g-pre'],['Pregão ÷ pré do mesmo dia',4,'g-preg'],['Pós ÷ pregão do mesmo dia',4,'g-pos']];
let tab='fases', key='data', asc=false, mes='';
const med=a=>{a=a.filter(x=>x!=null&&isFinite(x)).sort((x,y)=>x-y);const n=a.length;return n?(n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2):null};
const meses=[...new Set(D.map(r=>r.data.slice(0,7)))];
const ms=document.getElementById('mes');meses.forEach(m=>ms.insertAdjacentHTML('beforeend',`<option>${m}</option>`));
ms.onchange=()=>{mes=ms.value;render()};
document.getElementById('ord').onclick=()=>{key='data';asc=!asc;render()};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.t;key='data';asc=false;
 document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));
 document.getElementById('note-fases').hidden=tab!=='fases';document.getElementById('note-var').hidden=tab!=='var';document.getElementById('note-seq').hidden=tab!=='seq';
 try{localStorage.setItem('win_fases_tab',tab)}catch(e){}
 render()});
function render(){
 const C=tab==='fases'?CF:tab==='var'?CV:CS, G=tab==='fases'?GF:tab==='var'?GV:GS;
 document.getElementById('grp').innerHTML=G.map(([t,n,c])=>`<th class="${c}" colspan="${n}">${t}</th>`).join('');
 const hdr=document.getElementById('hdr');
 hdr.innerHTML=C.map((c,i)=>`<th class="${c[2].includes('l')?'l':''} ${c[2].includes('d')?'d':''}" data-i="${i}">${c[1]}</th>`).join('');
 hdr.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=C[th.dataset.i][0];if(k===key)asc=!asc;else{key=k;asc=false}render()});
 let rows=D.filter(r=>!mes||r.data.startsWith(mes));
 rows.sort((a,b)=>{let x=a[key],y=b[key];if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*(asc?1:-1)});
 document.getElementById('tb').innerHTML=rows.map(r=>`<tr class="${r.observacao?'flag':''}">`+C.map(c=>`<td class="${c[2]}">${c[3](r)}</td>`).join('')+'</tr>').join('');
 document.getElementById('ord').textContent=(key==='data'&&!asc)?'Mais antigo primeiro':'Mais recente primeiro';
 document.getElementById('cnt').textContent=`${rows.length} pregões`;
 let t;
 if(tab==='fases') t=[['pre','Leilão de abertura — volume mediano',f(med(rows.map(r=>r.pre_volume).filter(v=>v>0)))+' contratos'],
  ['pre','Leilão de abertura — horário mediano',(()=>{const s=rows.map(r=>r.pre_hora_leilao).filter(Boolean).map(h=>{const[a,b,c]=h.split(':');return +a*3600+ +b*60+ +c});const m=med(s);return m==null?'—':new Date(m*1000).toISOString().slice(11,19)})()],
  ['preg','Pregão — volume mediano',f(med(rows.map(r=>r.pregao_volume)))+' contratos'],
  ['preg','Pregão — amplitude mediana',f(med(rows.map(r=>r.amp)))+' pts'],
  ['pos','Call de fechamento — volume mediano',f(med(rows.map(r=>r.pos_volume)))+' contratos'],
  ['pos','Call − fech. do pregão (mediana)',(()=>{const m=med(rows.map(r=>r.pos_dpx));return m==null?'—':(m>0?'+':'')+nf.format(m)+' pts'})()]];
 else if(tab==='seq'){const lim=rows.filter(r=>!ROLAGEM.includes(r.data));
  t=[['pre','Pré ÷ pós anterior — volume (mediana)',rz(med(rows.map(r=>r.s_pre_vol)))],
   ['pre','Pré − pós anterior — |var.| mediana (sem rolagem)',f(med(lim.map(r=>r.s_pre_px==null?null:Math.abs(r.s_pre_px))))+' pts'],
   ['preg','Pregão ÷ pré — volume (mediana)',rz(med(rows.map(r=>r.s_preg_vol)))],
   ['preg','Pregão − pré — |var.| mediana',f(med(rows.map(r=>r.s_preg_px==null?null:Math.abs(r.s_preg_px))))+' pts'],
   ['pos','Pós ÷ pregão — volume (mediana)',rz(med(rows.map(r=>r.s_pos_vol)))],
   ['pos','Pós − pregão — |var.| mediana',f(med(rows.map(r=>r.s_pos_px==null?null:Math.abs(r.s_pos_px))))+' pts']];}
 else {const nome={pre:'Pré (vs call anterior)',preg:'Pregão',pos:'Pós (vs fech. pregão)'};
  t=FASES.map(([g,k])=>{const a=rows.map(r=>r[`${k}_dpx`]).filter(v=>v!=null);const up=a.filter(v=>v>0).length,dn=a.filter(v=>v<0).length;
   return [g,`${nome[g]} — dias ↑ / ↓ / =`,`${up} / ${dn} / ${a.length-up-dn}`]}).concat(
   FASES.map(([g,k])=>[g,`${nome[g]} — |Var. preço| mediana`,f(med(rows.map(r=>r[`${k}_dpx`]==null?null:Math.abs(r[`${k}_dpx`]))))+' pts']));}
 document.getElementById('tiles').innerHTML=t.map(([c,k,v])=>`<div class="tile ${c}"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
}
document.getElementById('sub').textContent=`${D.length} pregões · ${dt(D[0])} a ${dt(D[D.length-1])} · grade B3 ${D[0].grade_preabertura} pré-abertura / ${D[0].grade_negociacao} pregão / call ${D[0].grade_call}`;
let sv=null;try{sv=localStorage.getItem('win_fases_tab')}catch(e){}
if(sv==='var'||sv==='seq')document.querySelector(`.tab[data-t="${sv}"]`).click();else render();
</script></body></html>"""


def main():
    d = pd.read_csv(CSV, sep=";")[COLS]
    d = d.astype(object).where(d.notna(), None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fl = pd.read_csv(FLAGS, sep=";", encoding="utf-8-sig")
    rolagem = sorted(fl.loc[fl.motivo.str.startswith("rolagem"), "data"])
    html = HTML.replace("__DATA__", json.dumps(d.to_dict("records"), ensure_ascii=False))
    OUT.write_text(html.replace("__ROLAGEM__", json.dumps(rolagem)), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
