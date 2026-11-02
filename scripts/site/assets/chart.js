/*
  Hunterson history chart. One series at a time, drawn as SVG.
  No libraries. Values are read from a JSON block written by launch/publish.py.

  Encoding:
    published assessments   solid line, series colour
    shadow period           dashed grey line, labelled: these were not assessments
    not published           a gap in the line
    reference change        a gap, and a labelled hairline
*/
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var MONTH = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"];
  var DAY = 86400000;
  var RANGES = [
    { key: "1m", label: "1 month", days: 31, needs: 0 },
    { key: "3m", label: "3 months", days: 92, needs: 35 },
    { key: "1y", label: "1 year", days: 366, needs: 100 },
    { key: "all", label: "All", days: Infinity, needs: 380 }
  ];
  var SERIES = [
    { key: "o", label: "Output", unit: "US dollars per million output tokens" },
    { key: "i", label: "Input", unit: "US dollars per million input tokens" },
    { key: "b", label: "Blended", unit: "US dollars per million tokens, 16 input to 1 output" }
  ];

  function svg(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function html(tag, cls, parent, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  function utc(s) { return Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)); }
  function longDate(t) { var d = new Date(t); return d.getUTCDate() + " " + MONTH[d.getUTCMonth()] + " " + d.getUTCFullYear(); }
  function money(v, dp) { return "$" + v.toFixed(dp); }

  function niceStep(span, count) {
    var raw = span / Math.max(count, 1);
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var steps = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * mag >= raw) return steps[i] * mag;
    return 10 * mag;
  }
  function decimalsFor(step) {
    for (var dp = 2; dp < 4; dp++) {
      var s = step * Math.pow(10, dp);
      if (Math.abs(Math.round(s) - s) < 1e-6) return dp;
    }
    return 4;
  }

  function xTicks(t0, t1) {
    var span = (t1 - t0) / DAY, out = [], d = new Date(t0), t;
    function dayLabel(t) { return new Date(t).getUTCDate() + " " + MON[new Date(t).getUTCMonth()]; }
    if (span <= 14) {
      // Every weekday.
      for (t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); t <= t1; t += DAY) {
        var wd = new Date(t).getUTCDay();
        if (wd !== 0 && wd !== 6) out.push({ t: t, label: dayLabel(t) });
      }
      return out;
    }
    if (span <= 62) {
      // Mondays, weekly or fortnightly.
      var first = t0 + ((8 - new Date(t0).getUTCDay()) % 7) * DAY;
      var every = span <= 31 ? 7 : 14;
      for (t = first; t <= t1; t += every * DAY) out.push({ t: t, label: dayLabel(t) });
      return out;
    }
    // The first of each month, every one, two, six or twelve months.
    var stepM = span <= 200 ? 1 : span <= 400 ? 2 : span <= 1100 ? 6 : 12;
    var y = d.getUTCFullYear(), m = d.getUTCMonth() + 1, lastYear = null;
    if (m > 11) { m = 0; y += 1; }
    for (; ;) {
      t = Date.UTC(y, m, 1);
      if (t > t1) break;
      if (m % stepM === 0) {
        var label = MON[m];
        if (lastYear === null) label = MON[m] + " " + y;
        else if (y !== lastYear) label = m === 0 ? String(y) : MON[m] + " " + y;
        lastYear = y;
        out.push({ t: t, label: label });
      }
      m += 1;
      if (m > 11) { m = 0; y += 1; }
    }
    return out;
  }

  function mount(root, rows, opts) {
    opts = opts || {};
    rows = rows.map(function (r) { r.t = utc(r.d); return r; });
    if (!rows.length) return;
    var state = { range: null, series: "o", focus: null };
    var spanAll = (rows[rows.length - 1].t - rows[0].t) / DAY;
    var ranges = RANGES.filter(function (r) { return spanAll > r.needs || r.key === "1m"; });
    state.range = opts.range || (ranges.some(function (r) { return r.key === "3m"; }) ? "3m" : "1m");

    root.textContent = "";
    var controls = null, unitEl = null;
    if (!opts.card) {
      controls = html("div", "chart-controls", root);
      if (ranges.length > 1) seg(controls, "Time range", ranges, "range");
      seg(controls, "Price shown", SERIES, "series");
      unitEl = html("p", "chart-unit", root);
    }
    var box = html("div", "chart-box", root);
    var tip = opts.card ? null : html("div", "chart-tip", box);
    if (tip) tip.hidden = true;

    function seg(parent, label, items, key) {
      var g = html("div", "seg", parent);
      g.setAttribute("role", "group");
      g.setAttribute("aria-label", label);
      items.forEach(function (it) {
        var b = html("button", null, g, it.label);
        b.type = "button";
        b.setAttribute("aria-pressed", String(state[key] === it.key));
        b.addEventListener("click", function () {
          state[key] = it.key;
          Array.prototype.forEach.call(g.children, function (c) { c.setAttribute("aria-pressed", String(c === b)); });
          draw();
        });
      });
    }

    var view = [], geom = null, svgEl = null, cross = null, dot = null;

    function draw() {
      var last = rows[rows.length - 1].t;
      var r = RANGES.filter(function (x) { return x.key === state.range; })[0];
      view = rows.filter(function (x) { return opts.card ? true : last - x.t <= r.days * DAY; });
      var key = state.series;
      var unit = SERIES.filter(function (s) { return s.key === key; })[0].unit;
      if (unitEl) unitEl.textContent = unit;

      var W = Math.max(280, box.clientWidth), small = W < 560;
      var H = opts.height || (small ? 250 : 320);
      var m = opts.card ? { l: 66, r: 112, t: 14, b: 14 } : { l: small ? 52 : 60, r: small ? 66 : 78, t: 26, b: 30 };
      if (svgEl) box.removeChild(svgEl);
      svgEl = svg("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H, role: "img",
        "aria-label": (opts.card ? "Last 30 assessments" : "History of the assessed price") + ", " + unit }, null);
      box.insertBefore(svgEl, tip);
      if (!opts.card) svgEl.setAttribute("tabindex", "0");

      var vals = view.map(function (x) { return x[key]; }).filter(function (v) { return v != null; });
      if (!vals.length) return;
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = Math.max((hi - lo) * 0.12, hi * 0.02);
      lo -= pad; hi += pad;
      var step = niceStep(hi - lo, small ? 4 : 5);
      lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
      var dp = decimalsFor(step);
      var t0 = view[0].t, t1 = view[view.length - 1].t;
      if (t1 - t0 < 6 * DAY) { t0 -= 3 * DAY; t1 += 3 * DAY; }
      function X(t) { return m.l + (t - t0) / (t1 - t0) * (W - m.l - m.r); }
      function Y(v) { return m.t + (hi - v) / (hi - lo) * (H - m.t - m.b); }
      geom = { X: X, Y: Y, m: m, W: W, H: H };

      var grid = svg("g", { "class": "grid" }, svgEl);
      for (var v = lo; v <= hi + step / 2; v += step) {
        svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, grid);
        var tl = svg("text", { x: m.l - 8, y: Y(v) + 4, "text-anchor": "end", "class": "tick" }, grid);
        tl.textContent = money(v, dp);
      }
      if (!opts.card) xTicks(t0, t1).forEach(function (tk) {
        if (X(tk.t) < m.l || X(tk.t) > W - m.r) return;
        var tx = svg("text", { x: X(tk.t), y: H - 8, "text-anchor": "middle", "class": "tick" }, grid);
        tx.textContent = tk.label;
      });

      // Markers: first published assessment after a shadow period; reference changes.
      var marks = svg("g", { "class": "marks" }, svgEl);
      view.forEach(function (x, idx) {
        var prev = view[idx - 1];
        var label = null;
        if (prev && prev.s === "shadow" && x.s !== "shadow") label = "First assessment";
        if (x.roll) label = "Reference changed to " + x.ref;
        if (!label) return;
        var xx = X(x.t);
        svg("line", { x1: xx, x2: xx, y1: m.t - 6, y2: H - m.b, "class": "mark-line" }, marks);
        var lt = svg("text", { x: xx + 6, y: m.t - 10, "class": "mark-label" }, marks);
        lt.textContent = label;
        if (xx + 6 + label.length * 6.6 > W) { lt.setAttribute("x", xx - 6); lt.setAttribute("text-anchor", "end"); }
      });

      // Lines, broken at gaps, status changes and reference changes.
      var segs = [], cur = null;
      view.forEach(function (x, idx) {
        var v = x[key], prev = view[idx - 1];
        var k = (x.s === "shadow" ? "shadow" : "pub") + "|" + x.ref;
        var brk = v == null || !cur || cur.k !== k || (prev && prev[key] == null) || x.roll;
        if (v == null) { cur = null; return; }
        if (brk) { cur = { k: k, shadow: x.s === "shadow", pts: [] }; segs.push(cur); }
        cur.pts.push([X(x.t), Y(v)]);
      });
      var lines = svg("g", { "class": "lines" }, svgEl);
      segs.forEach(function (sg) {
        var cls = sg.shadow ? "line shadow" : "line";
        if (sg.pts.length === 1) { svg("circle", { cx: sg.pts[0][0], cy: sg.pts[0][1], r: 3.5, "class": cls + " solo" }, lines); return; }
        svg("path", { d: "M" + sg.pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join("L"), "class": cls }, lines);
      });
      var shadowSeg = segs.filter(function (s) { return s.shadow && s.pts.length > 1; })[0];
      if (shadowSeg && !opts.card) {
        var p0 = shadowSeg.pts[0];
        var sl = svg("text", { x: p0[0], y: H - m.b - 8, "class": "shadow-label" }, marks);
        sl.textContent = "Shadow period, not assessments";
      }

      // The latest value, labelled at the end of the line.
      var lastRow = null;
      for (var j = view.length - 1; j >= 0; j--) if (view[j][key] != null) { lastRow = view[j]; break; }
      if (lastRow) {
        var ex = X(lastRow.t), ey = Y(lastRow[key]);
        svg("circle", { cx: ex, cy: ey, r: 4, "class": "end-dot" + (lastRow.s === "shadow" ? " shadow" : "") }, svgEl);
        var el = svg("text", { x: ex + 9, y: ey + 4, "class": "end-label" }, svgEl);
        el.textContent = money(lastRow[key], 4);
      }

      if (opts.card) return;
      cross = svg("line", { "class": "cross", y1: m.t, y2: H - m.b, visibility: "hidden" }, svgEl);
      dot = svg("circle", { r: 4.5, "class": "cross-dot", visibility: "hidden" }, svgEl);
      var hit = svg("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" }, svgEl);
      hit.addEventListener("pointermove", function (e) {
        var rect = svgEl.getBoundingClientRect();
        show(nearest(e.clientX - rect.left));
      });
      hit.addEventListener("pointerleave", hide);
      svgEl.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          var i = state.focus == null ? view.length - 1 : state.focus + (e.key === "ArrowRight" ? 1 : -1);
          show(Math.max(0, Math.min(view.length - 1, i)));
        } else if (e.key === "Escape") hide();
      });
      svgEl.addEventListener("blur", hide);
      if (state.focus != null) show(Math.min(state.focus, view.length - 1));
    }

    function nearest(px) {
      var best = 0, bd = Infinity;
      view.forEach(function (x, i) { var d = Math.abs(geom.X(x.t) - px); if (d < bd) { bd = d; best = i; } });
      return best;
    }
    function show(i) {
      state.focus = i;
      var x = view[i], v = x[state.series];
      var xx = geom.X(x.t);
      cross.setAttribute("x1", xx); cross.setAttribute("x2", xx); cross.setAttribute("visibility", "visible");
      if (v != null) { dot.setAttribute("cx", xx); dot.setAttribute("cy", geom.Y(v)); dot.setAttribute("visibility", "visible"); }
      else dot.setAttribute("visibility", "hidden");
      tip.textContent = "";
      html("strong", null, tip, v != null ? money(v, 4) : "Not published");
      html("span", null, tip, longDate(x.t));
      var note = x.s === "shadow" ? "Shadow period, not an assessment"
        : x.s === "not_published" ? (x.r || "Not published")
        : x.c + " contributors";
      html("span", "muted", tip, note);
      if (x.roll) html("span", "muted", tip, "Reference changed; ratio " + x.roll);
      tip.hidden = false;
      var tw = tip.offsetWidth, left = xx + 14;
      if (left + tw > geom.W - 4) left = xx - tw - 14;
      tip.style.left = Math.max(4, left) + "px";
      tip.style.top = (geom.m.t + 4) + "px";
    }
    function hide() {
      state.focus = null;
      if (cross) cross.setAttribute("visibility", "hidden");
      if (dot) dot.setAttribute("visibility", "hidden");
      if (tip) tip.hidden = true;
    }

    draw();
    if (!opts.card && "ResizeObserver" in window) {
      var lastW = box.clientWidth;
      new ResizeObserver(function () { if (Math.abs(box.clientWidth - lastW) > 2) { lastW = box.clientWidth; draw(); } }).observe(box);
    }
  }

  window.HuntersonChart = { mount: mount };
})();
