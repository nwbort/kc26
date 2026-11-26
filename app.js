(function () {
  "use strict";
  const C = window.KEPLER_CONFIG;
  const M = window.KeplerModel;
  const $ = (id) => document.getElementById(id);
  const STORE = "kepler26-v1";

  const defaults = () => ({
    mode: "race",
    actual: {},                // checkpoint index -> race seconds
    goal: M.parseDuration(C.goalFinish),
    start: M.parseClock(C.startTime),
    band: C.band.slice(),
    gender: C.gender || "all",
  });

  let S = defaults();
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || "null");
    if (saved) S = Object.assign(S, saved);
  } catch (e) { /* storage unavailable, use defaults */ }
  const save = () => { try { localStorage.setItem(STORE, JSON.stringify(S)); } catch (e) {} };

  let DATA = null, CPS = [];

  // ---------- static header ----------
  $("runnerName").textContent = C.runnerName + (C.bib ? ` (#${C.bib})` : "");
  $("trackLink").href = C.trackingUrl;
  try {
    const d = new Date(C.raceDate + "T12:00:00");
    $("raceDate").textContent = d.toLocaleDateString("en-NZ", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  } catch (e) { $("raceDate").textContent = C.raceDate; }

  fetch(C.dataUrl, { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      DATA = d;
      CPS = d.meta.checkpoints.map((c, i) => ({
        i, km: c.km,
        name: C.checkpointNames[String(+c.km)] || (i === d.meta.checkpoints.length - 1 ? "Finish" : `${c.km} km`),
      }));
      $("demoBanner").hidden = !d.meta.demo;
      const fin = d.athletes.filter((a) => a.t[a.t.length - 1] != null).length;
      $("dataInfo").textContent = `Data: ${d.meta.source}. ${d.athletes.length} starters with splits, ${fin} finishers. Built ${d.meta.generated}.`;
      buildRows();
      bindSettings();
      render();
    })
    .catch((e) => {
      const el = $("loadError");
      el.hidden = false;
      el.textContent = `Couldn't load results data (${C.dataUrl}): ${e.message}. If you opened this file directly, serve it over http (e.g. GitHub Pages or "python3 -m http.server").`;
    });

  // ---------- input helpers ----------
  const raceToInput = (sec) => S.mode === "race" ? M.fmtDur(sec, sec % 60 !== 0) : M.fmtClock(S.start + sec);
  function inputToRace(str) {
    if (S.mode === "race") return M.parseDuration(str);
    const c = M.parseClock(str, S.start);
    if (c == null) return null;
    let r = c - S.start;
    if (r < 0) r += 24 * 3600;
    return r;
  }

  function buildRows() {
    const body = $("cpBody");
    body.innerHTML = "";
    CPS.forEach((cp) => {
      const tr = document.createElement("tr");
      tr.id = "row" + cp.i;
      tr.innerHTML =
        `<td><div class="cp-name">${cp.name}</div><div class="cp-km">${cp.km} km</div></td>` +
        `<td class="plan"></td>` +
        `<td><input aria-label="Actual time at ${cp.name}" inputmode="text" autocomplete="off" spellcheck="false"><span class="small delta"></span></td>` +
        `<td class="est"></td>`;
      const inp = tr.querySelector("input");
      inp.addEventListener("input", () => inp.classList.remove("bad"));
      inp.addEventListener("change", () => {
        const v = inp.value.trim();
        if (!v) { delete S.actual[cp.i]; save(); render(); return; }
        const r = inputToRace(v);
        if (r == null || r <= 0) { inp.classList.add("bad"); return; }
        S.actual[cp.i] = r; save(); render();
      });
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });
      body.appendChild(tr);
    });

    document.querySelectorAll(".seg button").forEach((b) => {
      b.addEventListener("click", () => { S.mode = b.dataset.mode; save(); render(); });
    });
    $("clearBtn").addEventListener("click", () => {
      if (Object.keys(S.actual).length && !confirm("Clear all entered checkpoint times?")) return;
      S.actual = {}; save(); render();
    });
  }

  function bindSettings() {
    const sync = () => {
      $("goalIn").value = M.fmtDur(S.goal);
      $("startIn").value = M.fmtDur(S.start).padStart(5, "0");
      $("bandLo").value = S.band[0];
      $("bandHi").value = S.band[1];
      $("genderIn").value = S.gender;
    };
    sync();
    $("goalIn").addEventListener("change", (e) => { const g = M.parseDuration(e.target.value); if (g) S.goal = g; save(); sync(); render(); });
    $("startIn").addEventListener("change", (e) => { const s = M.parseClock(e.target.value); if (s != null) S.start = s; save(); sync(); render(); });
    const band = () => {
      let lo = Math.max(0, Math.min(99, +$("bandLo").value || 0));
      let hi = Math.max(lo + 1, Math.min(100, +$("bandHi").value || 100));
      S.band = [lo, hi]; save(); sync(); render();
    };
    $("bandLo").addEventListener("change", band);
    $("bandHi").addEventListener("change", band);
    $("genderIn").addEventListener("change", (e) => { S.gender = e.target.value; save(); render(); });
    $("resetBtn").addEventListener("click", () => {
      const keep = { actual: S.actual, mode: S.mode };
      S = Object.assign(defaults(), keep); save(); sync(); render();
    });
  }

  // ---------- render ----------
  function deltaText(d) {
    const m = Math.round(Math.abs(d) / 60);
    if (m === 0) return { t: "on plan", cls: "" };
    return d < 0 ? { t: `${m} min ahead`, cls: "delta-ahead" } : { t: `${m} min behind`, cls: "delta-behind" };
  }

  function render() {
    if (!DATA) return;
    const fin = CPS.length - 1;
    const pool = M.buildPool(DATA, { band: S.band, gender: S.gender });
    const plan = M.goalPlan(pool, S.goal);

    // mode toggle
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.mode === S.mode)));
    $("modeHint").textContent = S.mode === "race"
      ? "Enter the race time shown on tracking, e.g. 1:58 or 1:58:30, then press Enter."
      : "Enter the time of day (NZ) they passed, e.g. 7:58 or 1:05pm, then press Enter.";

    // valid actuals: must increase with distance
    const idxs = Object.keys(S.actual).map(Number).sort((a, b) => a - b);
    const bad = new Set();
    let prev = 0;
    idxs.forEach((i) => { if (S.actual[i] <= prev) bad.add(i); else prev = S.actual[i]; });
    const good = idxs.filter((i) => !bad.has(i));
    const latest = good.length ? good[good.length - 1] : null;
    const T = latest != null ? S.actual[latest] : null;
    const proj = latest != null && latest < fin ? M.project(pool, latest, T) : null;

    // rows
    CPS.forEach((cp) => {
      const tr = $("row" + cp.i);
      tr.classList.toggle("latest", cp.i === latest);
      const p = plan.plan[cp.i];
      tr.querySelector(".plan").innerHTML = p != null
        ? `<span class="big">${M.fmtClock(S.start + p)}</span><span class="small">${M.fmtDur(p)}</span>` : "–";

      const inp = tr.querySelector("input");
      if (document.activeElement !== inp) inp.value = S.actual[cp.i] != null ? raceToInput(S.actual[cp.i]) : "";
      inp.placeholder = S.mode === "race" ? "h:mm" : "clock";
      inp.classList.toggle("bad", bad.has(cp.i));
      const dEl = tr.querySelector(".delta");
      dEl.className = "small delta";
      if (S.actual[cp.i] != null && !bad.has(cp.i) && p != null) {
        const d = deltaText(S.actual[cp.i] - p);
        dEl.textContent = d.t; if (d.cls) dEl.classList.add(d.cls);
      } else dEl.textContent = bad.has(cp.i) ? "out of order" : "";

      const est = tr.querySelector(".est");
      if (latest != null && cp.i <= latest) {
        est.innerHTML = S.actual[cp.i] != null && !bad.has(cp.i) ? `<span class="passed">Passed ✓</span>` : `<span class="passed">–</span>`;
      } else if (proj && proj.byCp[cp.i]) {
        const q = proj.byCp[cp.i];
        est.innerHTML = `<span class="big">${M.fmtClock(S.start + q.p50)}</span>` +
          `<span class="small">${M.fmtClock(S.start + q.p25)}–${M.fmtClock(S.start + q.p75)}</span>` +
          `<span class="small">race ${M.fmtDur(q.p50)}</span>`;
      } else {
        est.innerHTML = `<span class="passed">–</span>`;
      }
    });

    // hero
    const cpName = latest != null ? CPS[latest].name : "";
    if (latest === fin) {
      $("heroLabel").textContent = "Finished!";
      $("heroClock").textContent = M.fmtDur(T, true);
      $("heroMeta").textContent = `Crossed the line at ${M.fmtClock(S.start + T)}`;
      const d = deltaText(T - S.goal);
      $("heroBasis").textContent = `Goal was ${M.fmtDur(S.goal)}: ${d.t}. ` + rankLine(fin, T);
    } else if (proj && proj.byCp[fin]) {
      const q = proj.byCp[fin];
      $("heroLabel").textContent = "Estimated finish (NZ time)";
      $("heroClock").textContent = M.fmtClock(S.start + q.p50);
      $("heroMeta").textContent = `${M.fmtDur(q.p50)} race time · likely ${M.fmtClock(S.start + q.p25)}–${M.fmtClock(S.start + q.p75)}`;
      const next = proj.byCp[latest + 1];
      const nextTxt = latest + 1 < fin && next ? ` Next up: ${CPS[latest + 1].name} around ${M.fmtClock(S.start + next.p50)}.` : "";
      const fr = M.finishRate(DATA, latest, T);
      const frTxt = fr ? ` ${Math.round(fr.rate * 100)}% of 2025 runners at a similar time there went on to finish.` : "";
      $("heroBasis").textContent = `From ${cpName} at ${M.fmtDur(T)} (${M.fmtClock(S.start + T)}). ${rankLine(latest, T)}${frTxt}${nextTxt}`;
    } else {
      $("heroLabel").textContent = "Goal finish (NZ time)";
      $("heroClock").textContent = M.fmtClock(S.start + S.goal);
      $("heroMeta").textContent = `${M.fmtDur(S.goal)} race time · start ${M.fmtClock(S.start)}`;
      $("heroBasis").textContent = `The plan uses the typical splits of 2025 runners who finished near ${M.fmtDur(S.goal)}. Enter a checkpoint time to switch to a live estimate.`;
    }

    // settings info
    $("bandInfo").textContent = pool.pool.length
      ? `Comparing with ${pool.pool.length} of ${pool.finishers.length} 2025 finishers, who finished between ${M.fmtDur(pool.fastest)} and ${M.fmtDur(pool.slowest)}.`
      : "No 2025 finishers in this band.";

    // chart
    if (proj && proj.samples.length) {
      $("chartTitle").textContent = "Projected finish spread";
      $("chartHint").textContent = `Each bar is the share of comparable 2025 runners who would finish in that window if scaled to the ${cpName} time. Closer matches count more.`;
      drawHist(proj.samples, [{ v: proj.byCp[fin].p50, label: "estimate", solid: true }, { v: S.goal, label: "goal" }]);
    } else {
      const samples = pool.pool.map((a) => ({ v: a.t[fin], w: 1 }));
      $("chartTitle").textContent = "2025 finish times in the comparison pool";
      $("chartHint").textContent = `${samples.length} runners between the ${S.band[0]}th and ${S.band[1]}th percentile. Dashed line is the goal.`;
      drawHist(samples, latest === fin ? [{ v: T, label: "actual", solid: true }, { v: S.goal, label: "goal" }] : [{ v: S.goal, label: "goal" }]);
    }
  }

  let rT; window.addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(render, 150); });

  function rankLine(k, T) {
    const r = M.rankAt(DATA, k, T);
    if (!r.of) return "";
    return `That's about ${ordinal(r.rank)} of ${r.of} at that point in 2025.`;
  }
  function ordinal(n) {
    const s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  // ---------- histogram ----------
  function drawHist(samples, marks) {
    const host = $("chart"), tip = $("tip");
    const W = Math.max(300, Math.round(host.clientWidth || 700)), H = W < 500 ? 200 : 230, ml = 8, mr = 8, mt = 26, mb = 30;
    const tot = samples.reduce((a, s) => a + s.w, 0);
    const vals = samples.map((s) => s.v).sort((a, b) => a - b);
    const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
    let lo = Math.min(q(0.01), ...marks.map((m) => m.v)), hi = Math.max(q(0.99), ...marks.map((m) => m.v));
    const span = hi - lo;
    const bin = span > 4 * 3600 ? 900 : span > 2 * 3600 ? 600 : 300;
    lo = Math.floor(lo / bin) * bin; hi = Math.ceil(hi / bin) * bin + (hi % bin === 0 ? bin : 0);
    const nb = Math.max(1, Math.round((hi - lo) / bin));
    const bins = new Array(nb).fill(0);
    samples.forEach((s) => { const b = Math.floor((s.v - lo) / bin); if (b >= 0 && b < nb) bins[b] += s.w; });
    const maxB = Math.max(...bins) || 1;
    const x = (v) => ml + ((v - lo) / (hi - lo)) * (W - ml - mr);
    const bw = (W - ml - mr) / nb;
    const y = (v) => H - mb - (v / maxB) * (H - mb - mt);

    let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Histogram of finish times">`;
    // ticks every 30 or 60 min of race time, labelled with clock time
    const tick = span > 3 * 3600 || W < 500 ? 3600 : 1800;
    svg += `<g class="axis">`;
    for (let t = Math.ceil(lo / tick) * tick; t <= hi; t += tick) {
      svg += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${mt}" y2="${H - mb}"/>`;
      svg += `<text x="${x(t)}" y="${H - mb + 16}" text-anchor="middle">${M.fmtClock(S.start + t)}</text>`;
    }
    svg += `<line class="grid" x1="${ml}" x2="${W - mr}" y1="${H - mb}" y2="${H - mb}"/></g>`;
    bins.forEach((b, i) => {
      if (!b) return;
      const x0 = ml + i * bw + 1, w = Math.max(1, bw - 2), y0 = y(b), h = H - mb - y0, r = Math.min(4, w / 2, h);
      svg += `<path class="bar" d="M${x0},${H - mb} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} H${x0 + w - r} Q${x0 + w},${y0} ${x0 + w},${y0 + r} V${H - mb} Z"/>`;
    });
    marks.forEach((m, k) => {
      const mx = x(m.v);
      svg += `<line class="${m.solid ? "mark-line" : "mark-dash"}" x1="${mx}" x2="${mx}" y1="${mt - 4}" y2="${H - mb}"/>`;
      const anchor = mx > W - 70 ? "end" : mx < 70 ? "start" : "middle";
      svg += `<text class="mark-lbl" x="${mx}" y="${mt - 8 - (k && Math.abs(x(marks[0].v) - mx) < 70 ? 12 : 0)}" text-anchor="${anchor}">${m.label} ${M.fmtClock(S.start + m.v)}</text>`;
    });
    bins.forEach((b, i) => {
      svg += `<rect class="hit" data-i="${i}" x="${ml + i * bw}" y="${mt}" width="${bw}" height="${H - mb - mt}"/>`;
    });
    svg += `</svg>`;
    host.innerHTML = svg;

    const show = (e) => {
      const t = e.target.closest(".hit");
      if (!t) { tip.hidden = true; return; }
      const i = +t.dataset.i, a = lo + i * bin, b = a + bin;
      const pct = tot ? (bins[i] / tot) * 100 : 0;
      tip.innerHTML = `<strong>${M.fmtClock(S.start + a)}–${M.fmtClock(S.start + b)}</strong> · race ${M.fmtDur(a)}–${M.fmtDur(b)}<br>${pct < 1 && pct > 0 ? "<1" : Math.round(pct)}% of comparables`;
      const card = host.parentElement.getBoundingClientRect(), r = t.getBoundingClientRect();
      tip.style.left = Math.min(card.width - 90, Math.max(90, r.left - card.left + r.width / 2)) + "px";
      tip.style.top = (r.top - card.top + 4) + "px";
      tip.hidden = false;
    };
    host.onpointermove = show;
    host.onpointerdown = show;
    host.onpointerleave = () => { tip.hidden = true; };
  }
})();
