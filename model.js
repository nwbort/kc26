// Estimation model. Pure functions, no DOM: usable from the browser and node.
(function (root) {
  "use strict";

  // ---------- time helpers ----------
  function parseDuration(s) {
    // "1:58" -> h:mm, "1:58:30" -> h:mm:ss, "118" -> minutes
    s = String(s || "").trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) return +s * 60;
    const m = s.match(/^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$/);
    if (!m) return null;
    return +m[1] * 3600 + +m[2] * 60 + (m[3] ? +m[3] : 0);
  }

  // Clock time of day -> seconds since midnight. Accepts "9:41", "09:41:04",
  // "1:05pm", "13:05". Without am/pm, a time earlier than the start is
  // assumed to be pm (supporters typing "1:30" mean 1:30pm).
  function parseClock(s, startSec) {
    s = String(s || "").trim().toLowerCase().replace(/\s+/g, "");
    const m = s.match(/^(\d{1,2})(?::|\.)?(\d{2})?(?::(\d{2}))?(am|pm|a|p)?$/);
    if (!m) return null;
    let h = +m[1];
    const min = m[2] ? +m[2] : 0, sec = m[3] ? +m[3] : 0, ap = m[4];
    if (h > 23 || min > 59 || sec > 59) return null;
    if (ap && ap[0] === "p" && h < 12) h += 12;
    if (ap && ap[0] === "a" && h === 12) h = 0;
    let t = h * 3600 + min * 60 + sec;
    if (!ap && startSec != null && t < startSec && h < 12) t += 12 * 3600;
    return t;
  }

  function fmtDur(sec, withSec) {
    if (sec == null || !isFinite(sec)) return "–";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const mm = String(m).padStart(2, "0");
    return withSec ? `${h}:${mm}:${String(s).padStart(2, "0")}` : `${h}:${mm}`;
  }

  function fmtClock(sec) {
    if (sec == null || !isFinite(sec)) return "–";
    sec = Math.round(sec / 60) * 60;
    let h = Math.floor(sec / 3600) % 24;
    const m = Math.floor((sec % 3600) / 60);
    const ap = h >= 12 ? "pm" : "am";
    h = h % 12 || 12;
    return `${h}:${String(m).padStart(2, "0")}${ap}`;
  }

  // ---------- stats ----------
  function weightedQuantiles(vals, weights, qs) {
    const idx = vals.map((v, i) => i).sort((a, b) => vals[a] - vals[b]);
    const total = weights.reduce((a, b) => a + b, 0);
    return qs.map((q) => {
      const target = q * total;
      let cum = 0;
      for (const i of idx) {
        cum += weights[i];
        if (cum >= target) return vals[i];
      }
      return vals[idx[idx.length - 1]];
    });
  }

  function ess(w) {
    let s = 0, s2 = 0;
    for (const x of w) { s += x; s2 += x * x; }
    return s2 ? (s * s) / s2 : 0;
  }

  const QS = [0.1, 0.25, 0.5, 0.75, 0.9];

  // ---------- pool ----------
  // Finishers whose finish time sits inside [lo, hi] percentile of all
  // 2025 finishers (optionally one gender only).
  function buildPool(data, opts) {
    const n = data.meta.checkpoints.length, fin = n - 1;
    let finishers = data.athletes.filter((a) => a.t[fin] != null);
    if (opts.gender === "M" || opts.gender === "F") finishers = finishers.filter((a) => a.g === opts.gender);
    finishers.sort((a, b) => a.t[fin] - b.t[fin]);
    const N = finishers.length;
    const i0 = Math.floor((opts.band[0] / 100) * N);
    const i1 = Math.max(i0 + 1, Math.ceil((opts.band[1] / 100) * N));
    const pool = finishers.slice(i0, i1);
    return {
      pool, finishers, fin,
      fastest: pool.length ? pool[0].t[fin] : null,
      slowest: pool.length ? pool[pool.length - 1].t[fin] : null,
    };
  }

  // Kernel weights on log-time distance to a reference time at checkpoint k.
  // Bandwidth widens until the effective sample size is usable.
  function kernelWeights(pool, k, T, minEss) {
    const cand = pool.filter((a) => a.t[k] != null && a.t[k] > 0);
    let h = 0.06, w = [];
    for (let tries = 0; tries < 8; tries++) {
      w = cand.map((a) => { const d = Math.log(a.t[k] / T) / h; return Math.exp(-0.5 * d * d); });
      if (ess(w) >= minEss) break;
      h *= 1.5;
    }
    return { cand, w, h, ess: ess(w) };
  }

  // Given time T at checkpoint k, project times at every later checkpoint.
  function project(poolInfo, k, T) {
    const { pool, fin } = poolInfo;
    const { cand, w, h, ess: e } = kernelWeights(pool, k, T, 20);
    const out = {};
    const nCp = pool.length ? pool[0].t.length : 0;
    for (let j = k + 1; j < nCp; j++) {
      const vals = [], ws = [];
      cand.forEach((a, i) => {
        if (a.t[j] != null) { vals.push((T * a.t[j]) / a.t[k]); ws.push(w[i]); }
      });
      if (vals.length) {
        const [p10, p25, p50, p75, p90] = weightedQuantiles(vals, ws, QS);
        out[j] = { p10, p25, p50, p75, p90, n: vals.length };
      }
    }
    // finish distribution samples for the chart
    const samples = [];
    cand.forEach((a, i) => { samples.push({ v: (T * a.t[fin]) / a.t[k], w: w[i] }); });
    return { byCp: out, samples, ess: e, bandwidth: h, nCand: cand.length };
  }

  // Goal plan: typical split fractions of pool runners who finished near G.
  function goalPlan(poolInfo, G) {
    const { pool, fin } = poolInfo;
    const { cand, w, ess: e } = kernelWeights(pool, fin, G, 20);
    const nCp = pool.length ? pool[0].t.length : 0;
    const plan = [];
    for (let j = 0; j < nCp; j++) {
      if (j === fin) { plan.push(G); continue; }
      const vals = [], ws = [];
      cand.forEach((a, i) => { if (a.t[j] != null) { vals.push(a.t[j] / a.t[fin]); ws.push(w[i]); } });
      plan.push(vals.length ? G * weightedQuantiles(vals, ws, [0.5])[0] : null);
    }
    return { plan, ess: e };
  }

  // Where would time T at checkpoint k have ranked among everyone who reached k in 2025?
  function rankAt(data, k, T) {
    const ts = data.athletes.map((a) => a.t[k]).filter((x) => x != null);
    const ahead = ts.filter((x) => x < T).length;
    return { rank: ahead + 1, of: ts.length, pct: ts.length ? (ahead / ts.length) * 100 : null };
  }

  // Of the comparable runners at k (weighted), what share went on to finish?
  function finishRate(data, k, T) {
    const fin = data.meta.checkpoints.length - 1;
    const near = data.athletes.filter((a) => a.t[k] != null && Math.abs(Math.log(a.t[k] / T)) < 0.08);
    if (near.length < 5) return null;
    return { rate: near.filter((a) => a.t[fin] != null).length / near.length, n: near.length };
  }

  const api = { parseDuration, parseClock, fmtDur, fmtClock, weightedQuantiles, buildPool, project, goalPlan, rankAt, finishRate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KeplerModel = api;
})(this);
