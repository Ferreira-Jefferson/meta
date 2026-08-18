/* Charts com identidade visual do Terminal Editorial.
   Assume Plotly.js já carregado via CDN em base.html. */

(function () {
  function getTokens() {
    const css = getComputedStyle(document.documentElement);
    const c = (name) => css.getPropertyValue(name).trim();
    return {
      bg:       c('--bg-elevated'),
      fg:       c('--fg'),
      fgMuted:  c('--fg-muted'),
      grid:     c('--grid'),
      amber:    c('--accent-amber'),
      green:    c('--accent-green'),
      red:      c('--accent-red'),
      fontMono: 'JetBrainsMono, ui-monospace, monospace',
    };
  }

  function makeLayout(t) {
    return {
      paper_bgcolor: t.bg,
      plot_bgcolor: t.bg,
      font: { family: t.fontMono, color: t.fg, size: 11 },
      margin: { l: 56, r: 24, t: 12, b: 40 },
      xaxis: {
        showgrid: true, gridcolor: t.grid, gridwidth: 1,
        zeroline: false, tickfont: { color: t.fgMuted, size: 10 },
        linecolor: t.grid,
      },
      yaxis: {
        showgrid: true, gridcolor: t.grid, gridwidth: 1,
        zeroline: false, tickfont: { color: t.fgMuted, size: 10 },
        linecolor: t.grid,
      },
      hoverlabel: {
        bgcolor: t.bg, bordercolor: t.amber,
        font: { family: t.fontMono, color: t.fg, size: 11 },
      },
      showlegend: false,
    };
  }

  const CONFIG = { displayModeBar: false, responsive: true };

  window.MetaCharts = {
    equityCurve(el, points) {
      const t = getTokens();
      const dates = points.map(p => p.date);
      const equity = points.map(p => p.equity);
      const bench = points.map(p => p.benchmark);
      const traces = [
        { x: dates, y: bench, name: 'IBOV', line: { color: t.fgMuted, width: 1, dash: 'dot' }, hovertemplate: 'IBOV %{y:,.0f}<extra></extra>' },
        { x: dates, y: equity, name: 'Robô', line: { color: t.amber, width: 1.5 }, hovertemplate: 'Robô %{y:,.0f}<extra></extra>' },
      ];
      Plotly.newPlot(el, traces, { ...makeLayout(t), height: 380 }, CONFIG);
    },
    drawdown(el, points) {
      const t = getTokens();
      const layout = makeLayout(t);
      const dates = points.map(p => p.date);
      const eq = points.map(p => p.equity);
      let peak = -Infinity;
      const dd = eq.map(v => { peak = Math.max(peak, v); return (v / peak - 1) * 100; });
      const trace = [{
        x: dates, y: dd, fill: 'tozeroy',
        line: { color: t.red, width: 1 },
        fillcolor: 'rgba(194,90,76,0.18)',
        hovertemplate: '%{y:.1f}%<extra></extra>',
      }];
      Plotly.newPlot(el, trace, { ...layout, height: 140,
        yaxis: { ...layout.yaxis, ticksuffix: '%' } }, CONFIG);
    },
    async tradeChart(el, tradeId) {
      const r = await fetch(`/api/trades/${tradeId}/chart`);
      if (!r.ok) { el.innerHTML = '<p style="color:var(--fg-muted);padding:24px;text-align:center;">Sem histórico do ativo.</p>'; return; }
      const d = await r.json();
      const t = getTokens();
      const layout = makeLayout(t);

      const candle = {
        x: d.dates,
        open: d.open, high: d.high, low: d.low, close: d.close,
        type: 'candlestick',
        name: d.ticker,
        increasing: { line: { color: t.green, width: 1 }, fillcolor: t.green },
        decreasing: { line: { color: t.red, width: 1 }, fillcolor: t.bg },
        showlegend: false,
        hoverinfo: 'x+y',
      };
      const mm50 = {
        x: d.dates, y: d.mm50, mode: 'lines',
        line: { color: t.amber, width: 1 },
        name: 'MM50', hoverinfo: 'skip',
      };
      const mm200 = {
        x: d.dates, y: d.mm200, mode: 'lines',
        line: { color: t.fgMuted, width: 1, dash: 'dot' },
        name: 'MM200', hoverinfo: 'skip',
      };

      const shapes = [];
      const annotations = [];
      if (d.entry_date) {
        shapes.push({
          type: 'line', xref: 'x', yref: 'paper',
          x0: d.entry_date, x1: d.entry_date, y0: 0, y1: 1,
          line: { color: t.green, width: 1, dash: 'dash' },
        });
        annotations.push({
          x: d.entry_date, y: 1, xref: 'x', yref: 'paper', xanchor: 'left', yanchor: 'top',
          text: '▲ ENTRADA',
          showarrow: false, font: { color: t.green, size: 10, family: t.fontMono },
          bgcolor: t.bg, borderpad: 2,
        });
      }
      if (d.exit_date) {
        shapes.push({
          type: 'line', xref: 'x', yref: 'paper',
          x0: d.exit_date, x1: d.exit_date, y0: 0, y1: 1,
          line: { color: t.red, width: 1, dash: 'dash' },
        });
        annotations.push({
          x: d.exit_date, y: 1, xref: 'x', yref: 'paper', xanchor: 'left', yanchor: 'top',
          text: '▼ SAÍDA',
          showarrow: false, font: { color: t.red, size: 10, family: t.fontMono },
          bgcolor: t.bg, borderpad: 2,
        });
      }

      Plotly.newPlot(el, [mm200, mm50, candle], {
        ...layout, height: 440, shapes, annotations,
        xaxis: { ...layout.xaxis, rangeslider: { visible: false } },
      }, CONFIG);
    },
    ifrHistogram(el, rows) {
      const t = getTokens();
      const layout = makeLayout(t);
      const wins  = rows.filter(r => r.outcome === 'winner').map(r => r.ifr);
      const loses = rows.filter(r => r.outcome === 'loser').map(r => r.ifr);
      const traces = [
        { x: loses, name: 'Losers',  type: 'histogram', opacity: 0.55, marker: { color: t.red   }, xbins: { start: 0, end: 100, size: 5 } },
        { x: wins,  name: 'Winners', type: 'histogram', opacity: 0.75, marker: { color: t.green }, xbins: { start: 0, end: 100, size: 5 } },
      ];
      Plotly.newPlot(el, traces, { ...layout, barmode: 'overlay', height: 260,
        xaxis: { ...layout.xaxis, title: { text: 'IFR na entrada', font: { color: t.fgMuted, size: 10 } } } }, CONFIG);
    },
    updateTheme() {
      const t = getTokens();
      const update = {
        paper_bgcolor: t.bg,
        plot_bgcolor:  t.bg,
        'font.color':              t.fg,
        'xaxis.gridcolor':         t.grid,
        'xaxis.linecolor':         t.grid,
        'xaxis.tickfont.color':    t.fgMuted,
        'yaxis.gridcolor':         t.grid,
        'yaxis.linecolor':         t.grid,
        'yaxis.tickfont.color':    t.fgMuted,
        'hoverlabel.bgcolor':      t.bg,
        'hoverlabel.font.color':   t.fg,
      };
      document.querySelectorAll('.js-plotly-plot').forEach(el => {
        try { Plotly.relayout(el, update); } catch (e) {}
      });
    },
  };
})();
