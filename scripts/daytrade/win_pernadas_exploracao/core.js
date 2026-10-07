function caminho(bars){const pts=[];bars.forEach((b,i)=>{const[t,o,h,l,c]=b;(c>=o?[l,h]:[h,l]).forEach(p=>pts.push({p,i}));});pts.forEach((x,k)=>x.k=k);return pts;}
function zigzag(pts,thr){let dir=0,hi=pts[0],lo=pts[0],ext=null;const piv=[];
for(const x of pts){if(dir===0){if(x.p>hi.p)hi=x;if(x.p<lo.p)lo=x;if(hi.p-lo.p>=thr){if(lo.k<hi.k){piv.push(lo);dir=1;ext=hi;}else{piv.push(hi);dir=-1;ext=lo;}}}
else if(dir===1){if(x.p>ext.p)ext=x;else if(ext.p-x.p>=thr){piv.push(ext);dir=-1;ext=x;}}
else{if(x.p<ext.p)ext=x;else if(x.p-ext.p>=thr){piv.push(ext);dir=1;ext=x;}}}
if(ext)piv.push(ext);return piv;}
const TICK=5;
function correcoes(pts,a,b){const s=b.p>a.p?1:-1,tot=Math.abs(b.p-a.p),out=[];let rh=a,pm=null;
for(let k=a.k+1;k<=b.k;k++){const x=pts[k];if(s*(x.p-rh.p)>0){if(pm&&s*(rh.p-pm.p)>=TICK){const av=s*(rh.p-a.p),dep=s*(rh.p-pm.p);out.push({topo:rh,fundo:pm,avanco:av,pctPernada:av/tot*100,prof:dep,pctLeg:dep/tot*100,pctRetr:av>0?dep/av*100:0});}rh=x;pm=null;}
else if(!pm||s*(x.p-pm.p)<0)pm=x;}return out;}
function analisaDia(bars,thr){const pts=caminho(bars);const piv=zigzag(pts,thr);const legs=[];
for(let j=0;j+1<piv.length;j++){const a=piv[j],b=piv[j+1];legs.push({a,b,up:b.p>a.p,pts:Math.abs(b.p-a.p),mult:Math.abs(b.p-a.p)/thr,velas:b.i-a.i+1,volAnt:a.i>0?bars[a.i-1][5]:null,aberta:j+2===piv.length,corr:correcoes(pts,a,b)});}
return{legs,thr};}
if(typeof module!=="undefined")module.exports={analisaDia};
