"use strict";
// Brant Test app: the interface. The server (server.py) does the computing; this file builds the form,
// the "The model" panel (equations and assumptions, typeset with the bundled MathJax) and the results.

const S = { datasets: [], ds: null, cols: [], rows: 0, f: {}, busy: false, previewN: 20 };
try { const v = localStorage.getItem("bta-preview-n"); if (v) S.previewN = v === "all" ? "all" : (parseInt(v, 10) || 20); } catch (e) { }
const EXAMPLE = { dataset: "political_information", y: "info_rating",
  x: ["collegeDegree", "female", "age", "homeOwn", "govt", "length"], categorical: [], baselines: {}, cov_fallback: "auto",
  standardize: false, odds_ratios: false };

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
async function call(route, body) {
  const r = await fetch(route, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  if (!r.ok) throw new Error(`Server error ${r.status}`);
  return r.json();
}
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "html") e.innerHTML = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
function setBusy(b, msg) {
  S.busy = b;
  document.getElementById("dot").classList.toggle("busy", b);
  document.getElementById("status").textContent = msg || (b ? "Working…" : "Ready");
  const run = document.getElementById("runbtn");
  if (run) run.disabled = b;
}
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, 2200);
}
async function copyText(txt, what) {
  try { await navigator.clipboard.writeText(txt); toast(`${what} copied`); }
  catch (e) {
    const ta = h("textarea", {class: "copybox", "aria-label": what}); ta.value = txt;
    document.getElementById("reslog").prepend(ta); ta.select();
    toast("Select-all is ready: press Ctrl/⌘+C");
  }
}
const num = (x, d = 3) => {
  if (x === null || x === undefined || x === "") return "";
  if (typeof x === "string") return x;
  if (!Number.isFinite(x)) return String(x);
  const a = Math.abs(x);
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return x.toExponential(2);
  if (Number.isInteger(x) && a < 1e6) return String(x);
  return x.toFixed(d);
};
const pfmt = p => p == null ? "" : p < 0.001 ? "<0.001" : p.toFixed(3);
const stars = p => p == null ? "" : p < 0.001 ? "***" : p < 0.01 ? "**" : p < 0.05 ? "*" : "";
const col = n => S.cols.find(c => c.name === n);
const canBeCat = c => c && (c.kind === "categorical" || (c.levels && c.levels.length >= 2));
const isCat = v => { const c = col(v); return c && (c.kind === "categorical" || (S.f.categorical || []).includes(v)); };

// ---------------------------------------------------------------------------
// data
// ---------------------------------------------------------------------------
async function loadDataset(name, keepSpec) {
  setBusy(true, "Loading data…");
  try {
    const r = await call("/api/load", {name});
    if (!r.ok) throw new Error(r.error);
    useData(r);
    if (!keepSpec) S.f = name === EXAMPLE.dataset ? JSON.parse(JSON.stringify(EXAMPLE)) : defaultSpec(name);
  } catch (e) { showError(e.message); }
  setBusy(false);
  render();
}
function useData(r) {
  S.ds = r.name; S.cols = r.columns; S.rows = r.rows; S.meta = {title: r.title, description: r.description, source: r.source};
}
function defaultSpec(name) {
  const ord = S.cols.find(c => c.levels && c.levels.length >= 3 && c.levels.length <= 10);
  return {dataset: name, y: ord ? ord.name : null, x: [], categorical: [], baselines: {}, cov_fallback: "auto", standardize: false, odds_ratios: false};
}
async function uploadFile(file) {
  if (!file) return;
  const name = file.name.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_]+/g, "_").slice(0, 40) || "upload";
  setBusy(true, "Reading file…");
  try {
    const r = await call("/api/register", {name, csv: await file.text()});
    if (!r.ok) throw new Error(r.error);
    useData(r);
    if (!S.datasets.some(d => d.id === name)) S.datasets.push({id: name, title: r.title, uploaded: true});
    S.f = defaultSpec(name);
    toast(`Loaded ${file.name}`);
  } catch (e) { showError(e.message); }
  setBusy(false);
  render();
}

// ---------------------------------------------------------------------------
// form
// ---------------------------------------------------------------------------
function lab(text, control, small) {
  return h("label", {class: "f"}, h("span", {class: "lab"}, h("span", {}, text)), control, small ? h("small", {}, small) : null);
}
function render() { renderData(); renderForm(); renderEquations(); }

function renderData() {
  const card = document.getElementById("datacard"); card.innerHTML = "";
  const sel = h("select", {id: "dssel", "aria-label": "Dataset", onchange: e => loadDataset(e.target.value)});
  const ex = h("optgroup", {label: "Examples"}), up = h("optgroup", {label: "Uploaded"});
  for (const d of S.datasets) (d.uploaded ? up : ex).append(h("option", {value: d.id, selected: d.id === S.ds}, d.title));
  sel.append(ex); if (up.children.length) sel.append(up);
  const file = h("input", {type: "file", id: "upload", accept: ".csv,.txt,.tsv,text/csv", class: "sr", onchange: e => uploadFile(e.target.files[0])});
  card.append(
    h("div", {class: "res-head"}, h("span", {class: "eyebrow"}, "Data"), h("span", {class: "kind"}, `${S.rows} rows · ${S.cols.length} variables`)),
    sel,
    h("div", {class: "dsdesc"}, (S.meta && S.meta.description) || "", " ", S.meta && S.meta.source ? h("span", {class: "src"}, S.meta.source) : null),
    h("div", {class: "btnrow"},
      h("label", {class: "btn small", for: "upload"}, "Upload CSV…"), file,
      h("button", {class: "btn small", type: "button", onclick: showCodebook}, "Codebook"),
      h("button", {class: "btn small", type: "button", onclick: showPreview}, "View rows"),
      h("label", {class: "rowsn"}, "Rows to show",
        h("select", {id: "previewn", "aria-label": "Rows to show",
                     onchange: e => { S.previewN = e.target.value === "all" ? "all" : parseInt(e.target.value, 10);
                                      try { localStorage.setItem("bta-preview-n", String(S.previewN)); } catch (err) { } }},
          ...[20, 50, 200, "all"].map(v => h("option", {value: String(v), selected: String(v) === String(S.previewN)}, v === "all" ? "All" : String(v)))))));
}

function orderEditor() {
  const c = col(S.f.y); if (!c || !c.levels) return null;
  let ord = S.f.order && S.f.order.length === c.levels.length && S.f.order.every(l => c.levels.includes(l)) ? S.f.order : c.levels.slice();
  S.f.order = ord;
  const box = h("div", {});
  ord.forEach((l, i) => box.append(h("div", {class: "order-item"}, h("span", {class: "n"}, i + 1), h("span", {style: "flex:1"}, l),
    h("button", {class: "btn small", type: "button", disabled: i === 0, "aria-label": `Move ${l} up`, onclick: () => { [ord[i - 1], ord[i]] = [ord[i], ord[i - 1]]; renderForm(); renderEquations(); }}, "↑"),
    h("button", {class: "btn small", type: "button", disabled: i === ord.length - 1, "aria-label": `Move ${l} down`, onclick: () => { [ord[i + 1], ord[i]] = [ord[i], ord[i + 1]]; renderForm(); renderEquations(); }}, "↓"))));
  return h("fieldset", {}, h("legend", {}, "Order of the outcome categories (lowest first)"), box,
    ord.length < 3 ? h("div", {class: "alert err", style: "margin-top:6px"}, "The Brant test needs at least three categories.") : null);
}

function renderForm() {
  const card = document.getElementById("formcard"); card.innerHTML = "";
  card.append(h("div", {}, h("div", {class: "eyebrow"}, "Ordered logit and Brant test"),
    h("h2", {}, "Test of the proportional-odds assumption"),
    h("p", {class: "hint", style: "margin:4px 0 0"}, "Fits an ordered logit, then tests whether each slope is the same at every split of the outcome (Brant 1990).")));
  const form = h("form", {class: "stack", style: "gap:12px", onsubmit: e => { e.preventDefault(); runModel(); }});
  const ys = h("select", {id: "f-y", onchange: e => { S.f.y = e.target.value || null; S.f.order = null; S.f.x = (S.f.x || []).filter(v => v !== S.f.y); renderForm(); renderEquations(); }});
  ys.append(h("option", {value: ""}, "—"));
  for (const c of S.cols) if (c.levels && c.levels.length >= 3) ys.append(h("option", {value: c.name, selected: c.name === S.f.y}, `${c.name}${c.label ? " — " + c.label.slice(0, 50) : ""} (${c.levels.length} categories)`));
  form.append(lab("Ordered outcome", ys, "variables with 3 to 12 distinct values"));
  const oe = orderEditor(); if (oe) form.append(oe);

  // covariates
  const chosen = new Set(S.f.x || []);
  const list = h("div", {class: "varlist", id: "f-x"});
  for (const c of S.cols) {
    if (c.name === S.f.y) continue;
    list.append(h("label", {title: c.label || c.name},
      h("input", {type: "checkbox", checked: chosen.has(c.name), onchange: e => {
        const cur = (S.f.x || []).filter(v => v !== c.name); if (e.target.checked) cur.push(c.name); S.f.x = cur; renderForm(); renderEquations(); }}),
      h("span", {}, c.name), h("span", {class: "kind"}, c.kind[0])));
  }
  form.append(h("fieldset", {}, h("legend", {}, "Covariates"), list));

  // terms: categorical coding and baselines
  const xs = (S.f.x || []).filter(v => col(v));
  if (xs.length) {
    S.f.categorical = S.f.categorical || []; S.f.baselines = S.f.baselines || {};
    const box = h("div", {class: "terms"});
    for (const v of xs) {
      const c = col(v), forced = c.kind === "categorical", asCat = isCat(v);
      const cells = [h("span", {}, v, " ", h("span", {class: "kind"}, asCat ? "categorical" : "numeric"))];
      if (asCat) {
        const s = h("select", {"aria-label": `Baseline of ${v}`, onchange: e => { S.f.baselines[v] = e.target.value; renderEquations(); }});
        for (const l of c.levels || []) s.append(h("option", {value: l, selected: (S.f.baselines[v] ?? c.levels[0]) === l}, `base: ${l}`));
        cells.push(s);
      } else cells.push(h("span"));
      if (!forced && canBeCat(c)) cells.push(h("label", {class: "check", style: "font-size:11.5px"}, h("input", {type: "checkbox", checked: asCat, onchange: e => {
        S.f.categorical = e.target.checked ? [...new Set([...S.f.categorical, v])] : S.f.categorical.filter(x => x !== v); renderForm(); renderEquations(); }}), "categorical"));
      else cells.push(h("span"));
      box.append(h("div", {class: "term"}, ...cells));
    }
    form.append(h("fieldset", {}, h("legend", {}, "Terms"), box,
      h("div", {class: "hint", style: "margin-top:6px"}, "A categorical covariate enters as dummies against its baseline and is tested jointly over them.")));
  }

  // options
  const cov = h("select", {id: "f-cov", onchange: e => { S.f.cov_fallback = e.target.value; }},
    ...[["auto", "auto: observed information, ridge fallback (default)"], ["oim", "oim: observed information"],
        ["hc0", "hc0: robust within each split"], ["ridge", "ridge: ridge-stabilized information"]]
      .map(([v, l]) => h("option", {value: v, selected: (S.f.cov_fallback || "auto") === v}, l)));
  const chk = (key, text) => h("label", {class: "check"}, h("input", {type: "checkbox", checked: !!S.f[key], onchange: e => S.f[key] = e.target.checked}), text);
  form.append(h("details", {open: true}, h("summary", {}, "Options"), h("div", {class: "stack", style: "gap:10px"},
    lab("Covariance of the binary-logit slopes (pybrant cov_fallback)", cov),
    chk("standardize", "Standardize the predictors in the binary logits (pybrant standardize; the statistic is unchanged)"),
    chk("odds_ratios", "Show odds ratios"))));

  form.append(h("div", {class: "btnrow"}, h("button", {class: "btn primary", type: "submit", id: "runbtn", disabled: S.busy}, "Run"),
    h("button", {class: "btn small", type: "button", onclick: () => { S.f = S.ds === EXAMPLE.dataset ? JSON.parse(JSON.stringify(EXAMPLE)) : defaultSpec(S.ds); render(); }}, "Reset")));
  card.append(form);
}

function buildSpec() {
  const f = S.f;
  const xs = (f.x || []).filter(v => col(v));
  const categorical = xs.filter(v => isCat(v));
  const baselines = {}; for (const v of categorical) { const c = col(v); baselines[v] = f.baselines[v] ?? (c.levels || [])[0]; }
  return {dataset: S.ds, y: f.y, order: f.order, x: xs, categorical, baselines,
          cov_fallback: f.cov_fallback || "auto", standardize: !!f.standardize, odds_ratios: !!f.odds_ratios};
}

// ---------------------------------------------------------------------------
// "The model": equations and assumptions
// ---------------------------------------------------------------------------
// variable names and levels go inside \text{…}, where only braces and backslashes need care
const tt = s => String(s).replace(/[\\{}]/g, " ");
const tv = s => `\\text{${tt(s)}}`;
function modelEquations() {
  const f = S.f, c = col(f.y);
  const J = (f.order || (c && c.levels) || []).length;
  const xs = (f.x || []).filter(v => col(v));
  const general = [
    "\\Pr(y_i \\le j \\mid x_i) = \\Lambda(\\kappa_j - x_i'\\beta), \\quad j = 1, \\dots, J-1, \\qquad \\Lambda(u) = \\frac{1}{1 + e^{-u}}",
    "\\kappa_1 < \\kappa_2 < \\dots < \\kappa_{J-1}, \\qquad \\Pr(y_i = j \\mid x_i) = \\Lambda(\\kappa_j - x_i'\\beta) - \\Lambda(\\kappa_{j-1} - x_i'\\beta)",
    "\\text{Proportional odds: } \\operatorname{logit} \\Pr(y_i > j \\mid x_i) = x_i'\\beta - \\kappa_j \\text{ has the same } \\beta \\text{ at every split } j",
  ];
  const spec = [];
  let K = 0;
  if (f.y && xs.length && J >= 3) {
    const terms = [];
    for (const v of xs) {
      if (isCat(v)) {
        const lv = (col(v).levels || []); const base = (f.baselines || {})[v] ?? lv[0];
        const others = lv.filter(l => l !== base);
        K += others.length;
        if (others.length <= 3) for (const l of others) terms.push(`\\beta_{${tv(v + ": " + l)}}\\, 1[${tv(v)} = ${tv(l)}]`);
        else terms.push(`\\textstyle\\sum_{l \\ne ${tv(base)}} \\beta_{${tv(v)}, l}\\, 1[${tv(v)} = l]`);
      } else { K += 1; terms.push(`\\beta_{${tv(v)}}\\, ${tv(v)}`); }
    }
    const rowsTex = [];
    for (let i = 0; i < terms.length; i += 2) rowsTex.push((i ? "&+ " : "x'\\beta &= ") + terms.slice(i, i + 2).join(" + "));
    spec.push(`\\operatorname{logit} \\Pr(${tv(f.y)} \\le j) = \\kappa_j - x'\\beta, \\quad j = 1, \\dots, ${J - 1}`);
    spec.push(`\\begin{aligned} ${rowsTex.join(" \\\\ ")} \\end{aligned}`);
    spec.push(`\\text{Binary logits: } \\operatorname{logit} \\Pr(${tv(f.y)} > j) = \\alpha_j + x'\\beta_j, \\quad j = 1, \\dots, ${J - 1}`);
    spec.push(`H_0\\colon \\beta_1 = \\beta_2 = \\dots = \\beta_{${J - 1}}, \\qquad W = (D\\hat\\beta^*)'\\,(D \\hat V D')^{-1} (D\\hat\\beta^*) \\;\\overset{a}{\\sim}\\; \\chi^2_{(J-2)K} = \\chi^2_{${(J - 2) * K}}`);
  }
  const brant = [
    "\\hat\\beta^* = (\\hat\\beta_1', \\dots, \\hat\\beta_{J-1}')' \\text{ stacks the slopes of the } J-1 \\text{ binary logits of } 1[y > j]",
    "\\operatorname{Cov}(\\hat\\beta_m, \\hat\\beta_l) = (X'W_mX)^{-1} X'W_{ml}X\\,(X'W_lX)^{-1}, \\quad W_{ml} = \\operatorname{diag}(\\pi_l - \\pi_m\\pi_l), \\; m < l",
    "D\\hat\\beta^* = (\\hat\\beta_1 - \\hat\\beta_2, \\dots, \\hat\\beta_{J-2} - \\hat\\beta_{J-1}): \\text{ adjacent differences; a covariate's own test uses its rows, } (J-2) \\text{ df per column}",
  ];
  const assume = [
    "Observations are independent.",
    "The outcome categories are ordered as listed, lowest first, and the latent-variable error is logistic (logit link).",
    "The same slope vector applies at every split (proportional odds): this is the hypothesis the Brant test examines.",
    "No covariate, or combination of covariates, perfectly separates the categories at any split.",
    "Rows with a missing value in the outcome or a chosen covariate are dropped (listwise deletion).",
    "The Brant statistic is a large-sample (Wald) test; with sparse categories its χ² approximation can be poor.",
  ];
  return {general, spec, brant, assume, K, J};
}
let eqTimer = null;
function renderEquations() {
  clearTimeout(eqTimer);
  eqTimer = setTimeout(() => {
    const slot = document.getElementById("eqslot");
    const E = modelEquations();
    const disp = t => h("div", {class: "eq"}, `\\[${t}\\]`);
    let open = true; try { open = localStorage.getItem("bta-eq-open") !== "0"; } catch (e) {}
    const box = h("details", {class: "eqpanel", open, ontoggle: e => { try { localStorage.setItem("bta-eq-open", e.target.open ? "1" : "0"); } catch (err) {} }},
      h("summary", {}, "The model: equations and assumptions"),
      h("div", {class: "eqhead"}, "Ordered logit"), ...E.general.map(disp));
    if (E.spec.length) box.append(h("div", {class: "eqhead"}, "Your specification"), ...E.spec.map(disp),
      h("div", {class: "eqnote"}, `J = ${E.J} categories and K = ${E.K} covariate columns (dummies counted separately).`));
    box.append(h("div", {class: "eqhead"}, "Brant's test"), ...E.brant.map(disp),
      h("div", {class: "eqhead"}, "Assumptions"), h("ul", {class: "assume"}, ...E.assume.map(a => h("li", {}, a))));
    slot.replaceChildren(box);
    typesetMath(box);
  }, 150);
}
function typesetMath(el) {
  const MJ = window.MathJax;
  if (MJ && MJ.typesetPromise) (MJ.startup && MJ.startup.promise ? MJ.startup.promise : Promise.resolve()).then(() => MJ.typesetPromise([el])).catch(e => console.error(e));
  else setTimeout(() => { if (el.isConnected) typesetMath(el); }, 200);
}

// ---------------------------------------------------------------------------
// running and results
// ---------------------------------------------------------------------------
async function runModel() {
  if (S.busy) return;
  const spec = buildSpec();
  setBusy(true, "Estimating…");
  const t0 = performance.now();
  try {
    const r = await call("/api/run", {spec});
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    if (!r.ok) showError(r.error, r.trace);
    else addResult({title: `Brant test · ${spec.y} · ${spec.dataset}`, spec: r.spec_text, specObj: spec, outputs: r.outputs, secs});
  } catch (e) { showError(`The analysis could not run: ${e.message}.`); }
  setBusy(false);
}
function coefTable(o) {
  const head = ["Term", "β", "", "SE", "z", "p", "95% CI"].concat(o.odds_ratios ? ["Odds ratio", "95% CI"] : []);
  const t = h("table", {class: "t"}, h("thead", {}, h("tr", {}, ...head.map(x => h("th", {}, x)))));
  const tb = h("tbody");
  for (const r of o.rows) tb.append(h("tr", {class: r.p < 0.05 ? "sig" : ""},
    h("td", {}, r.term), h("td", {class: "num"}, num(r.est, 4)), h("td", {class: "stars"}, stars(r.p)), h("td", {class: "num"}, num(r.se, 4)),
    h("td", {class: "num"}, num(r.z, 2)), h("td", {class: "num"}, pfmt(r.p)), h("td", {class: "num"}, `[${num(r.lo, 3)}, ${num(r.hi, 3)}]`),
    ...(o.odds_ratios ? [h("td", {class: "num"}, num(r.or, 3)), h("td", {class: "num"}, `[${num(r.or_lo, 3)}, ${num(r.or_hi, 3)}]`)] : [])));
  t.append(tb); return t;
}
function genTable(o) {
  const t = h("table", {class: "t"}, h("thead", {}, h("tr", {}, ...o.columns.map(c => h("th", {}, c)))));
  const tb = h("tbody");
  for (const r of o.rows) tb.append(h("tr", {class: o.brant && r.p < 0.05 ? "sig" : ""}, ...o.columns.map(c => {
    const v = r[c], isNum = typeof v === "number";
    return h("td", {class: isNum ? "num" : ""}, isNum ? (c === "p" ? pfmt(v) : c === "df" || c === "Observations" ? String(v) : num(v, c === "Share" ? 3 : 4)) : (v ?? ""));
  })));
  t.append(tb); return t;
}
const texEsc = s => String(s ?? "").replace(/\\/g, "\\textbackslash{}").replace(/([&%$#_{}])/g, "\\$1").replace(/χ²/g, "$\\chi^2$").replace(/β/g, "$\\beta$").replace(/κ(\d*)/g, (m, d) => `$\\kappa${d ? "_{" + d + "}" : ""}$`).replace(/ⱼ/g, "$_j$").replace(/≤/g, "$\\le$");
function latexCoef(o) {
  const lines = [`% ${o.title}`, "\\begin{tabular}{l" + "r".repeat(o.odds_ratios ? 4 : 3) + "}", "\\toprule",
    `Term & $\\beta$ & SE & $p$${o.odds_ratios ? " & Odds ratio" : ""} \\\\`, "\\midrule"];
  for (const r of o.rows) lines.push(`${texEsc(r.term)} & ${num(r.est, 3)}${stars(r.p) ? "$^{" + stars(r.p) + "}$" : ""} & (${num(r.se, 3)}) & ${pfmt(r.p)}${o.odds_ratios ? " & " + num(r.or, 3) : ""} \\\\`);
  lines.push("\\bottomrule", "\\end{tabular}", "% * p<0.05, ** p<0.01, *** p<0.001");
  return lines.join("\n");
}
function latexTable(o) {
  const lines = [`% ${o.title}`, "\\begin{tabular}{l" + "r".repeat(o.columns.length - 1) + "}", "\\toprule", o.columns.map(texEsc).join(" & ") + " \\\\", "\\midrule"];
  for (const r of o.rows) lines.push(o.columns.map(c => typeof r[c] === "number" ? (c === "p" ? pfmt(r[c]) : c === "df" ? String(r[c]) : num(r[c], 3)) : texEsc(r[c])).join(" & ") + " \\\\");
  lines.push("\\bottomrule", "\\end{tabular}");
  return lines.join("\n");
}
function csvTable(o) {
  const q = v => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  if (o.type === "coef") {
    const cols = ["term", "est", "se", "z", "p", "lo", "hi"].concat(o.odds_ratios ? ["or", "or_lo", "or_hi"] : []);
    return [cols.join(",")].concat(o.rows.map(r => cols.map(c => q(r[c])).join(","))).join("\n");
  }
  return [o.columns.map(q).join(",")].concat(o.rows.map(r => o.columns.map(c => q(r[c])).join(","))).join("\n");
}
function svgDoc(svg) { return svg.includes("xmlns=") ? svg : svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"'); }
function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = h("a", {href: url, download: name}); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast(`Saved ${name} to your Downloads folder`);
}
function savePNG(svg, name, scale = 3) {
  const doc = svgDoc(svg);
  const m = doc.match(/width="([\d.]+)pt" height="([\d.]+)pt"/);
  const w = m ? parseFloat(m[1]) * 96 / 72 : 800, ht = m ? parseFloat(m[2]) * 96 / 72 : 500;
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas"); c.width = Math.round(w * scale); c.height = Math.round(ht * scale);
    const ctx = c.getContext("2d"); ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    c.toBlob(b => saveBlob(b, name), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(doc);
}
function addResult(res) {
  const log = document.getElementById("reslog");
  const empty = log.querySelector(".empty"); if (empty) empty.remove();
  const box = h("article", {class: "result card"});
  box.append(h("div", {class: "res-head"}, h("h3", {}, res.title), h("span", {class: "kind"}, `${res.secs} s`)));
  if (res.spec) box.append(h("div", {class: "spec"}, res.spec), h("div", {class: "btnrow"},
    h("button", {class: "btn small", type: "button", onclick: () => copyText(res.spec, "Specification")}, "Copy specification"),
    h("button", {class: "btn small", type: "button", title: "Python script (statsmodels + pybrant) that reproduces this run",
      onclick: async () => { const r = await call("/api/pycode", {spec: res.specObj}); if (!r.ok) return showError(r.error); copyText(r.code, "Python code"); }}, "Copy Python code"),
    h("button", {class: "btn small", type: "button", onclick: async () => { const r = await call("/api/csv", {name: res.specObj.dataset}); copyText(r.csv, "Data (CSV)"); }}, "Copy data as CSV")));
  for (const o of res.outputs) {
    if (o.type === "coef" || o.type === "table") {
      const base = (o.title || "table").normalize("NFKD").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50);
      box.append(h("div", {},
        h("div", {class: "res-head"}, h("div", {class: "out-title"}, o.title),
          h("div", {class: "btnrow"},
            h("button", {class: "btn small", type: "button", onclick: () => copyText(o.type === "coef" ? latexCoef(o) : latexTable(o), "LaTeX table")}, "Copy LaTeX"),
            h("button", {class: "btn small", type: "button", onclick: () => saveBlob(new Blob([csvTable(o)], {type: "text/csv"}), base + ".csv")}, "Save CSV"))),
        h("div", {class: "tablewrap"}, o.type === "coef" ? coefTable(o) : genTable(o)),
        o.note ? h("div", {class: "note"}, o.note) : null));
    } else if (o.type === "stats") {
      const dl = h("dl", {class: "stats"});
      for (const [k, v] of Object.entries(o.items)) dl.append(h("dt", {}, k), h("dd", {}, typeof v === "number" ? num(v, 4) : String(v)));
      box.append(h("div", {}, h("div", {class: "out-title"}, o.title), dl));
    } else if (o.type === "figure") {
      box.append(h("div", {}, h("div", {class: "res-head"}, h("div", {class: "out-title"}, o.title),
        h("div", {class: "btnrow"},
          h("button", {class: "btn small", type: "button", onclick: () => savePNG(o.svg, "brant_slopes.png")}, "Save PNG"),
          h("button", {class: "btn small", type: "button", onclick: () => saveBlob(new Blob([svgDoc(o.svg)], {type: "image/svg+xml"}), "brant_slopes.svg")}, "Save SVG"))),
        h("div", {class: "figure", html: o.svg})));
    } else if (o.type === "text") {
      box.append(h("div", {}, h("div", {class: "out-title"}, o.title), h("p", {class: "reading"}, o.text)));
    } else if (o.type === "warning") {
      box.append(h("div", {class: "alert"}, o.text));
    }
  }
  log.prepend(box);
  box.scrollIntoView({behavior: "smooth", block: "start"});
}
function showError(msg, trace) {
  const log = document.getElementById("reslog");
  const box = h("div", {class: "alert err card", role: "alert"}, h("b", {}, "The analysis did not run. "), msg);
  if (trace) box.append(h("details", {}, h("summary", {}, "Technical details"), h("pre", {style: "white-space:pre-wrap;font-size:11px"}, trace)));
  log.prepend(box);
}
async function showCodebook() {
  const rows = S.cols.map(c => ({Variable: c.name, Type: c.kind, Description: c.label || "", "Distinct values": c.n_unique, Missing: c.missing}));
  addResult({title: `Codebook: ${S.meta.title || S.ds}`, spec: "", secs: "0.0", specObj: {dataset: S.ds},
    outputs: [{type: "table", title: "", columns: ["Variable", "Type", "Description", "Distinct values", "Missing"], rows}]});
}
async function showPreview() {
  const r = await call("/api/preview", {name: S.ds, n: S.previewN === "all" ? 0 : S.previewN});
  const rows = r.rows.map(row => Object.fromEntries(r.columns.map((c, i) => [c, row[i]])));
  addResult({title: rows.length >= S.rows ? `All ${rows.length} rows of ${S.ds}` : `First ${rows.length} rows of ${S.ds}`, spec: "", secs: "0.0", specObj: {dataset: S.ds},
    outputs: [{type: "table", title: "", columns: r.columns, rows}]});
}

// ---------------------------------------------------------------------------
async function start() {
  document.getElementById("clearres").onclick = () => { document.getElementById("reslog").innerHTML = '<div class="empty">Results of each run appear here, newest first.</div>'; };
  try {
    const r = await call("/api/datasets");
    S.datasets = r.datasets;
  } catch (e) { showError("The app's server is not reachable. Restart the app."); setBusy(false, "Offline"); return; }
  await loadDataset(EXAMPLE.dataset);
}
start();
