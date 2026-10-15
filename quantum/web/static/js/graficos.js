/* Gráficos Plotly do Quantum: cores lidas dos tokens CSS (tema claro/escuro). */
(function () {
  var Q = window.Q = { desenhos: [] };

  function cor(nome) { return getComputedStyle(document.documentElement).getPropertyValue(nome).trim(); }

  Q.cores = function () {
    return { fg: cor('--fg'), muted: cor('--fg-muted'), grid: cor('--grid'), amber: cor('--accent-amber'),
             green: cor('--accent-green'), red: cor('--accent-red'), faint: cor('--fg-faint'), strong: cor('--fg-strong') };
  };

  Q.layout = function (extra) {
    var c = Q.cores();
    var base = {
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'JetBrainsMono, monospace', size: 11, color: c.fg },
      margin: { l: 56, r: 16, t: 28, b: 40 }, hovermode: 'x unified',
      legend: { orientation: 'h', y: 1.12, x: 0 },
      xaxis: { gridcolor: c.grid, zeroline: false, linecolor: c.grid },
      yaxis: { gridcolor: c.grid, zeroline: false, linecolor: c.grid },
      separators: ',.'
    };
    var out = Object.assign(base, extra || {});
    // eixo log: só 1-2-5 em cada década, senão os rótulos se amontoam
    if (out.yaxis && out.yaxis.type === 'log' && !out.yaxis.dtick) { out.yaxis.dtick = 'D2'; out.yaxis.tickformat = out.yaxis.tickformat || '.1f'; }
    return out;
  };

  Q.plot = function (id, tracos, layout) {
    var el = document.getElementById(id);
    if (!el || !window.Plotly) return;
    Plotly.react(el, tracos(), Q.layout(layout), { responsive: true, displaylogo: false });
    Q.desenhos = Q.desenhos.filter(function (d) { return d.id !== id; });
    Q.desenhos.push({ id: id, tracos: tracos, layout: layout });
  };

  Q.redesenhar = function () { Q.desenhos.forEach(function (d) { Q.plot(d.id, d.tracos, d.layout); }); };

  /* curva carteira × Ibovespa × CDI (base 1) */
  Q.curva = function (id, s, titulo, logy) {
    Q.plot(id, function () {
      var c = Q.cores();
      return [
        { x: s.datas, y: s.carteira, name: titulo || 'Carteira', line: { color: c.amber, width: 2 } },
        { x: s.datas, y: s.ibov, name: 'Ibovespa', line: { color: c.muted, width: 1.4 } },
        { x: s.datas, y: s.cdi, name: '100% CDI', line: { color: c.green, width: 1.2, dash: 'dot' } }
      ];
    }, { yaxis: { type: logy ? 'log' : 'linear', gridcolor: Q.cores().grid, tickformat: '.2f' } });
  };

  Q.quando = function (fn) {
    if (window.Plotly) return fn();
    window.addEventListener('load', fn);
  };
})();
