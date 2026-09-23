/* Graphiques SVG natifs réutilisables — aucune dépendance externe. */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const empty = (node) => { node.innerHTML = '<p style="color:#A9BDB2;text-align:center;padding-top:120px;">Aucune donnée</p>'; };

  // Donut : data = {label: value}, colors = {label: '#hex'}
  window.geDonut = function (id, data, colors, legendId) {
    const node = document.getElementById(id); if (!node) return;
    const labels = Object.keys(data);
    const total = labels.reduce((s, l) => s + data[l], 0);
    if (!total) return empty(node);
    const cx = 175, cy = 165, r = 120, ir = 72;
    const svg = el('svg', { viewBox: '0 0 350 330', width: '100%', height: '100%' });
    let a0 = -Math.PI / 2;
    labels.forEach(l => {
      const frac = data[l] / total, a1 = a0 + frac * 2 * Math.PI, col = (colors && colors[l]) || '#5A8';
      if (frac >= 0.9999) {
        svg.appendChild(el('circle', { cx, cy, r: (r + ir) / 2, fill: 'none', stroke: col, 'stroke-width': r - ir }));
      } else {
        const p = (a, rad) => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
        const lg = (a1 - a0) > Math.PI ? 1 : 0;
        const [x1, y1] = p(a0, r), [x2, y2] = p(a1, r), [x3, y3] = p(a1, ir), [x4, y4] = p(a0, ir);
        svg.appendChild(el('path', { d: `M${x1} ${y1} A${r} ${r} 0 ${lg} 1 ${x2} ${y2} L${x3} ${y3} A${ir} ${ir} 0 ${lg} 0 ${x4} ${y4} Z`,
          fill: col, stroke: '#0D2A20', 'stroke-width': 2 }));
      }
      const mid = (a0 + a1) / 2, lr = (r + ir) / 2;
      const t = el('text', { x: cx + lr * Math.cos(mid), y: cy + lr * Math.sin(mid), fill: '#fff',
        'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle', 'dominant-baseline': 'middle' });
      t.textContent = Math.round(frac * 100) + '%'; svg.appendChild(t); a0 = a1;
    });
    node.appendChild(svg);
    if (legendId) {
      const lgn = document.getElementById(legendId);
      if (lgn) labels.forEach(l => {
        const s = document.createElement('span'); s.className = 'legend-item';
        s.innerHTML = `<i style="background:${(colors && colors[l]) || '#5A8'}"></i>${l} (${data[l]})`;
        lgn.appendChild(s);
      });
    }
  };

  // Barres verticales : labels[], values[], unité optionnelle
  window.geBar = function (id, labels, values, unit) {
    const node = document.getElementById(id); if (!node) return;
    if (!labels || !labels.length) return empty(node);
    const W = 700, H = 330, padL = 46, padB = 52, padT = 12, padR = 12;
    const max = Math.max(1, ...values), n = labels.length;
    const step = (W - padL - padR) / n, bw = step * 0.62;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: '100%' });
    svg.appendChild(el('line', { x1: padL, y1: H - padB, x2: W - padR, y2: H - padB, stroke: 'rgba(255,255,255,.18)' }));
    [0, 0.5, 1].forEach(f => {
      const y = padT + (1 - f) * (H - padB - padT);
      svg.appendChild(el('line', { x1: padL, y1: y, x2: W - padR, y2: y, stroke: 'rgba(255,255,255,.06)' }));
      const t = el('text', { x: padL - 6, y: y + 4, fill: '#8A9BB0', 'font-size': 11, 'text-anchor': 'end' });
      t.textContent = (Math.round(max * f * 100) / 100) + (unit ? '' : ''); svg.appendChild(t);
    });
    labels.forEach((lab, i) => {
      const v = values[i] || 0, h = (v / max) * (H - padB - padT);
      const x = padL + i * step + (step - bw) / 2, y = H - padB - h;
      const shade = 40 + Math.round((v / max) * 120);
      svg.appendChild(el('rect', { x, y, width: bw, height: Math.max(0, h), rx: 4,
        fill: `rgb(${Math.round(shade * 0.4)},${shade + 60},${Math.round(shade * 0.6)})` }));
      const t = el('text', { x: x + bw / 2, y: H - padB + 16, fill: '#A9BDB2', 'font-size': 11,
        'text-anchor': 'end', transform: `rotate(-40 ${x + bw / 2} ${H - padB + 16})` });
      t.textContent = lab; svg.appendChild(t);
    });
    node.appendChild(svg);
  };
})();
