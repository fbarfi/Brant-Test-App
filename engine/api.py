"""Brant Test app: computations behind the interface.

The ordered logit is fitted with statsmodels' OrderedModel (formula interface, logit link) and
the test of the proportional-odds assumption is computed with pybrant (BrantTest). Every function
called by the server takes and returns JSON text.

Functions
    datasets()                 the example datasets (data/catalog.json)
    load(name)                 read an example dataset
    register(name, csv_text)   read an uploaded CSV file
    columns(name)              variable descriptions for the form
    preview(name, n)           the first n rows
    run(spec_json)             ordered logit, Brant test, separate binary logits, figure
    python_code(spec_json)     a Python script (statsmodels + pybrant) that reproduces a run
"""
import io
import json
import math
import os
import re
import sys
import traceback
import warnings

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = {}      # name -> DataFrame
META = {}      # name -> catalog entry (title, description, labels, order)
MAX_CAT = 12   # numeric variables with at most this many values can be treated as categorical


class UserError(Exception):
    """A problem with the data or the specification, reported to the user as is."""


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def _catalog():
    with open(os.path.join(ROOT, "data", "catalog.json"), encoding="utf-8") as f:
        return json.load(f)


def datasets():
    return json.dumps({"ok": True, "datasets": [{k: d[k] for k in ("id", "title", "source", "description")}
                                                for d in _catalog()]})


def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def _level_strings(s):
    """String labels of a variable's values: whole numbers without '.0', text unchanged."""
    if pd.api.types.is_numeric_dtype(s):
        v = pd.to_numeric(s, errors="coerce")
        whole = v.dropna().eq(v.dropna().round()).all()
        return v.map(lambda a: None if pd.isna(a) else (str(int(a)) if whole else repr(float(a))))
    return s.map(lambda a: None if pd.isna(a) else str(a))


def _levels(name, var):
    s = DATA[name][var]
    lv = sorted(set(_level_strings(s).dropna()), key=_natural_key)
    order = (META.get(name, {}).get("order") or {}).get(var)
    if order and set(order) == set(lv):
        lv = list(order)
    elif pd.api.types.is_numeric_dtype(s):
        lv = sorted(lv, key=float)
    return lv


def _columns(name):
    df = DATA[name]
    labels = META.get(name, {}).get("labels", {})
    out = []
    for c in df.columns:
        s = df[c]
        numeric = pd.api.types.is_numeric_dtype(s)
        n_unique = int(s.nunique(dropna=True))
        info = {"name": c, "label": labels.get(c, ""), "kind": "numeric" if numeric else "categorical",
                "n_unique": n_unique, "missing": int(s.isna().sum())}
        if not numeric or n_unique <= MAX_CAT:
            info["levels"] = _levels(name, c)
        out.append(info)
    return out


def _register(name, df, meta):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if df.columns.duplicated().any():
        raise UserError("The file has duplicate column names.")
    if len(df) < 10 or df.shape[1] < 2:
        raise UserError("The file needs at least two columns and ten rows.")
    for c in df.columns:                      # text columns that hold numbers become numeric
        if df[c].dtype == object:
            conv = pd.to_numeric(df[c], errors="coerce")
            if conv.notna().sum() == df[c].notna().sum() and df[c].notna().any():
                df[c] = conv
    DATA[name], META[name] = df, meta
    return json.dumps({"ok": True, "name": name, "title": meta.get("title", name), "rows": len(df),
                       "description": meta.get("description", ""), "source": meta.get("source", ""),
                       "columns": _columns(name)})


def load(name):
    try:
        meta = {d["id"]: d for d in _catalog()}.get(name)
        if meta is None:
            raise UserError(f"Unknown dataset '{name}'.")
        df = pd.read_csv(os.path.join(ROOT, "data", f"{name}.csv"))
        return _register(name, df, meta)
    except UserError as e:
        return json.dumps({"ok": False, "error": str(e)})


def register(name, csv_text):
    try:
        try:
            df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
        except Exception as e:
            raise UserError(f"The file could not be read as CSV ({e}).")
        return _register(name, df, {"title": f"{name} (uploaded)", "description": f"{len(df)} rows uploaded from this computer."})
    except UserError as e:
        return json.dumps({"ok": False, "error": str(e)})


def columns(name):
    return json.dumps({"ok": True, "columns": _columns(name)})


def preview(name, n=200):
    df = DATA[name].head(int(n))
    rows = [[None if (isinstance(v, float) and math.isnan(v)) else (v.item() if hasattr(v, "item") else v)
             for v in r] for r in df.itertuples(index=False)]
    return json.dumps({"ok": True, "columns": list(df.columns), "rows": rows})


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------
def _safe(name, used):
    base = re.sub(r"\W", "_", name)
    if not base or base[0].isdigit():
        base = "v_" + base
    out, k = base, 1
    while out in used:
        k += 1
        out = f"{base}_{k}"
    used.add(out)
    return out


def _prepare(spec):
    """Estimation sample, formula and name maps for a specification."""
    name = spec.get("dataset")
    if name not in DATA:
        raise UserError("Choose a dataset first.")
    df = DATA[name]
    y = spec.get("y")
    xs = [v for v in dict.fromkeys(spec.get("x") or []) if v != y]
    if not y or y not in df.columns:
        raise UserError("Choose the ordered outcome.")
    if not xs:
        raise UserError("Choose at least one covariate.")
    for v in xs:
        if v not in df.columns:
            raise UserError(f"Variable '{v}' is not in the data.")
    cat = set(spec.get("categorical") or [])
    baselines = spec.get("baselines") or {}

    d = df[[y] + xs].dropna()
    n_dropped = len(df) - len(d)
    yl = _level_strings(d[y])
    order = [str(v) for v in (spec.get("order") or _levels(name, y))]
    present = set(yl)
    missing = [l for l in order if l not in present]
    if missing:
        raise UserError(f"Outcome categories with no observations in the estimation sample: {', '.join(missing)}. "
                        "Remove them from the order or recode the outcome.")
    extra = present - set(order)
    if extra:
        raise UserError(f"Outcome values not in the order of categories: {', '.join(sorted(extra))}.")
    if len(order) < 3:
        raise UserError("The Brant test needs an outcome with at least three ordered categories.")

    used = set()
    work = pd.DataFrame(index=d.index)
    ysafe = _safe("y_" + y, used)
    work[ysafe] = pd.Categorical(yl, categories=order, ordered=True)
    terms, term_label, col_label = [], {}, {}
    for v in xs:
        sv = _safe(v, used)
        s = d[v]
        is_cat = (not pd.api.types.is_numeric_dtype(s)) or v in cat
        if is_cat:
            lv = sorted(set(_level_strings(s)), key=_natural_key)
            if pd.api.types.is_numeric_dtype(s):
                lv = sorted(lv, key=float)
            if len(lv) < 2:
                raise UserError(f"'{v}' has only one value in the estimation sample.")
            if len(lv) > 60:
                raise UserError(f"'{v}' has {len(lv)} distinct values: too many to treat as categorical.")
            base = str(baselines.get(v, lv[0]))
            if base not in lv:
                base = lv[0]
            cats = [base] + [l for l in lv if l != base]
            work[sv] = pd.Categorical(_level_strings(s), categories=cats)
            t = f"C({sv})"
            terms.append(t)
            term_label[t] = v
            for l in cats[1:]:
                col_label[f"{t}[T.{l}]"] = f"{v}: {l}"
                col_label[f"{t}[{l}]"] = f"{v}: {l}"
            col_label[f"__base__{v}"] = base
        else:
            work[sv] = pd.to_numeric(s, errors="coerce").astype(float)
            if work[sv].std() == 0:
                raise UserError(f"'{v}' does not vary in the estimation sample.")
            terms.append(sv)
            term_label[sv] = v
            col_label[sv] = v
    formula = f"{ysafe} ~ " + " + ".join(terms)
    counts = pd.Series(yl).value_counts().reindex(order).astype(int)
    return {"name": name, "y": y, "xs": xs, "work": work, "formula": formula, "order": order, "counts": counts,
            "term_label": term_label, "col_label": col_label, "n_dropped": n_dropped,
            "categorical": [v for v in xs if (not pd.api.types.is_numeric_dtype(df[v])) or v in cat]}


def _col_name(P, c):
    c = str(c)
    if c in P["col_label"]:
        return P["col_label"][c]
    m = re.match(r"^(C\(\w+\))\[(?:T\.)?(.+)\]$", c)
    if m and m.group(1) in P["term_label"]:
        return f"{P['term_label'][m.group(1)]}: {m.group(2)}"
    return c


def _term_name(P, t):
    t = str(t)
    return P["term_label"].get(t, P["term_label"].get(t.replace(" ", ""), t))


def _fit_ordered(P):
    from statsmodels.miscmodels.ordinal_model import OrderedModel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = OrderedModel.from_formula(P["formula"], data=P["work"], distr="logit")
        res = mod.fit(method="bfgs", disp=False, maxiter=2000)
    return mod, res


def _cutpoints(res, J):
    """Cutpoints kappa_1 < ... < kappa_{J-1} with delta-method standard errors.

    statsmodels parameterizes them as kappa_1 = a_1, kappa_j = kappa_{j-1} + exp(a_j)."""
    params = np.asarray(res.params, float)
    V = np.asarray(res.cov_params(), float)
    k = len(params) - (J - 1)
    a = params[k:]
    kap = np.cumsum(np.r_[a[0], np.exp(a[1:])])
    G = np.zeros((J - 1, J - 1))
    for j in range(J - 1):
        G[j, 0] = 1.0
        for i in range(1, j + 1):
            G[j, i] = math.exp(a[i])
    Va = V[k:, k:]
    se = np.sqrt(np.diag(G @ Va @ G.T))
    return kap, se


def _svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    s = buf.getvalue()
    return s[s.find("<svg"):]


def _p_text(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def run(spec_json):
    try:
        spec = json.loads(spec_json)
        return json.dumps(_run(spec), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    except UserError as e:
        return json.dumps({"ok": False, "error": str(e)})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})


def _run(spec):
    import statsmodels
    import statsmodels.api as sm
    from pybrant import BrantTest
    import pybrant

    P = _prepare(spec)
    order, counts = P["order"], P["counts"]
    J = len(order)
    n = int(counts.sum())
    mod, res = _fit_ordered(P)
    out = []
    warn = []
    conv = bool((getattr(res, "mle_retvals", None) or {}).get("converged", True))
    if not conv:
        warn.append("The ordered-logit optimiser did not report convergence. Interpret the estimates with caution.")
    small = [f"{l} ({c})" for l, c in counts.items() if c < 10]
    if small:
        warn.append("Few observations in some outcome categories: " + ", ".join(small) +
                    ". The binary logits for the splits next to them, and the Brant test, rest on little information.")

    # ordered logit: slopes
    names = list(mod.exog_names)
    K = len(names)
    params = np.asarray(res.params, float)
    se = np.asarray(res.bse, float)
    z = params / se
    p = 2 * stats.norm.sf(np.abs(z))
    zc = stats.norm.ppf(0.975)
    rows = []
    for i, c in enumerate(names):
        r = {"term": _col_name(P, c), "est": params[i], "se": se[i], "z": z[i], "p": p[i],
             "lo": params[i] - zc * se[i], "hi": params[i] + zc * se[i]}
        if spec.get("odds_ratios"):
            r.update({"or": math.exp(params[i]), "or_lo": math.exp(r["lo"]), "or_hi": math.exp(r["hi"])})
        rows.append(r)
    base_notes = [f"{v}: baseline {P['col_label']['__base__' + v]}" for v in P["categorical"]]
    out.append({"type": "coef", "title": "Ordered logit: slopes", "rows": rows, "odds_ratios": bool(spec.get("odds_ratios")),
                "note": "Pr(y ≤ j) = Λ(κⱼ − x′β): a positive β moves probability toward the higher categories. "
                        "Standard errors from the inverse of the observed information. "
                        + ("Categorical covariates are dummy-coded (" + "; ".join(base_notes) + "). " if base_notes else "")
                        + f"Estimated with statsmodels {statsmodels.__version__} OrderedModel (logit link, BFGS)."})
    kap, kse = _cutpoints(res, J)
    out.append({"type": "table", "title": "Ordered logit: cutpoints κⱼ",
                "columns": ["Cutpoint", "Between", "Estimate", "SE"],
                "rows": [{"Cutpoint": f"κ{j + 1}", "Between": f"{order[j]} | {order[j + 1]}", "Estimate": kap[j], "SE": kse[j]}
                         for j in range(J - 1)],
                "note": "Cutpoints in the parameterization of R's MASS::polr and Stata's ologit. statsmodels reports the first "
                        "cutpoint and then the logs of the increments; the table converts them (delta-method standard errors)."})
    ll = float(res.llf)
    ll0 = float(np.sum(counts.values * np.log(counts.values / n)))
    LR = 2 * (ll - ll0)
    kpar = len(params)
    fit = {"Observations": n, "Dropped (missing values)": P["n_dropped"], "Outcome categories J": J,
           "Covariate columns K": K, "Log-likelihood": ll, "Null log-likelihood (cutpoints only)": ll0,
           "LR χ² (all slopes = 0)": f"χ²({K}) = {LR:.3f}, p = {_p_text(stats.chi2.sf(LR, K))}",
           "McFadden pseudo-R²": 1 - ll / ll0, "AIC": -2 * ll + 2 * kpar, "BIC": -2 * ll + math.log(n) * kpar}
    out.append({"type": "stats", "title": "Model fit", "items": fit})
    out.append({"type": "table", "title": "Observations by outcome category",
                "columns": ["Category", "Observations", "Share"],
                "rows": [{"Category": l, "Observations": int(c), "Share": c / n} for l, c in counts.items()]})

    # Brant test (pybrant)
    cov = spec.get("cov_fallback", "auto")
    bt = BrantTest(res, use_formula=True, by_var=True, standardize=bool(spec.get("standardize", False)),
                   cov_fallback=cov, ridge=float(spec.get("ridge", 1e-8)))
    br = bt.test_results()
    brows = [{"Test for": "Omnibus (all covariates)", "χ²": br.omnibus_stat, "df": int(br.omnibus_df), "p": br.omnibus_p}]
    if br.by_variable is not None:
        for _, r in br.by_variable.iterrows():
            brows.append({"Test for": _term_name(P, r["Test for"]), "χ²": float(r["Chi-square"]), "df": int(r["df"]),
                          "p": float(r["p-value"])})
    out.append({"type": "table", "title": "Brant test of the proportional-odds (parallel regression) assumption",
                "columns": ["Test for", "χ²", "df", "p"], "rows": brows, "brant": True,
                "note": f"H₀: each slope is the same at every split Pr(y > j), j = 1, …, {J - 1}. The omnibus test has "
                        f"(J − 2)K = {J - 2}·{K} = {(J - 2) * K} degrees of freedom; the test of a covariate has (J − 2) per "
                        "column, so a categorical covariate is tested jointly over its dummies. "
                        f"Computed with pybrant {getattr(pybrant, '__version__', '')} (BrantTest; covariance option "
                        f"'{cov}'{', standardized predictors' if spec.get('standardize') else ''})."})

    # separate binary logits of y > j
    X = np.asarray(mod.exog, float)
    yidx = np.asarray(pd.Series(P["work"].iloc[:, 0]).cat.codes)
    Xc = sm.add_constant(X, has_constant="add")
    split_b, split_se = [], []
    for j in range(J - 1):
        zj = (yidx > j).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lr = sm.Logit(zj, Xc).fit(method="newton", disp=False, maxiter=200)
        split_b.append(np.asarray(lr.params, float)[1:])
        split_se.append(np.asarray(lr.bse, float)[1:])
    split_b, split_se = np.array(split_b), np.array(split_se)
    cols = ["Covariate", "Ordered logit β"] + [f"y > {order[j]}" for j in range(J - 1)]
    srows = []
    for i, c in enumerate(names):
        r = {"Covariate": _col_name(P, c), "Ordered logit β": params[i]}
        for j in range(J - 1):
            r[f"y > {order[j]}"] = f"{split_b[j, i]:.3f} ({split_se[j, i]:.3f})"
        srows.append(r)
    out.append({"type": "table", "title": "Slopes of the separate binary logits of y > j",
                "columns": cols, "rows": srows,
                "note": "Each column is a binary logit of 1{y > j} on the same covariates (standard errors in parentheses). "
                        "Under proportional odds every row is constant across the columns and close to the ordered-logit β; "
                        "the Brant test asks whether the differences between adjacent columns are larger than sampling error."})

    # figure: slopes across splits
    ncols = min(3, K)
    nrows = int(math.ceil(K / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.6 * ncols, 2.7 * nrows), squeeze=False)
    xpos = np.arange(J - 1)
    for i in range(nrows * ncols):
        ax = axes[i // ncols][i % ncols]
        if i >= K:
            ax.axis("off")
            continue
        ax.errorbar(xpos, split_b[:, i], yerr=zc * split_se[:, i], fmt="o", color="#2563eb", capsize=3, lw=1.2)
        ax.axhline(params[i], color="#dc2626", lw=1.2, ls="--")
        ax.set_xticks(xpos)
        ax.set_xticklabels([f">{order[j]}" for j in range(J - 1)], fontsize=7, rotation=20)
        ax.set_title(_col_name(P, names[i]), fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    fig.suptitle("Binary-logit slopes at each split (95% CI); dashed: ordered-logit β", fontsize=9.5)
    fig.tight_layout()
    out.append({"type": "figure", "title": "Slopes across the splits", "svg": _svg(fig)})

    # reading of the test
    sig = [r["Test for"] for r in brows[1:] if r["p"] < 0.05]
    txt = (f"Omnibus test: χ²({int(br.omnibus_df)}) = {br.omnibus_stat:.2f}, p = {_p_text(br.omnibus_p)}. ")
    txt += ("Covariates whose slopes differ across splits at the 5% level: " + ", ".join(sig) + ". " if sig else
            "No covariate's test rejects equal slopes across splits at the 5% level. ")
    txt += ("A rejection says that the slopes are not equal at every split; how large the differences are, and whether "
            "they matter for the question at hand, is read from the table and the figure of the separate binary logits. "
            f"With {n} observations, small departures can be statistically significant.")
    out.append({"type": "text", "title": "Reading the test", "text": txt})
    for w in warn:
        out.insert(0, {"type": "warning", "text": w})

    cats = "; categorical: " + ", ".join(f"{v} (baseline {P['col_label']['__base__' + v]})" for v in P["categorical"]) \
        if P["categorical"] else ""
    spec_text = (f"Dataset: {P['name']}. Ordered logit of {P['y']} (categories, lowest first: {', '.join(order)}) on "
                 f"{', '.join(P['xs'])}{cats}. Brant test with pybrant (covariance option '{cov}'). "
                 f"Estimation sample: {n} observations"
                 + (f" ({P['n_dropped']} dropped for missing values)." if P["n_dropped"] else "."))
    return {"ok": True, "outputs": out, "spec_text": spec_text}


# ---------------------------------------------------------------------------
# Python code that reproduces a run
# ---------------------------------------------------------------------------
def python_code(spec_json):
    try:
        spec = json.loads(spec_json)
        P = _prepare(spec)
        y, xs = P["y"], P["xs"]
        cat = P["categorical"]
        lines = [
            f"# Brant test app: ordered logit of {y} and Brant's test of proportional odds",
            "# Requires: pip install statsmodels pandas git+https://github.com/fbarfi/pybrant.git",
            "import pandas as pd",
            "from statsmodels.miscmodels.ordinal_model import OrderedModel",
            "from pybrant import BrantTest",
            "",
            f'df = pd.read_csv("{P["name"]}.csv")   # the data from the app ("Copy data as CSV")',
            f"df = df[{[y] + xs!r}].dropna()",
            f"order = {P['order']!r}   # lowest first",
            f'df["{y}"] = pd.Categorical(df["{y}"].astype(str).str.replace(r"\\.0$", "", regex=True), categories=order, ordered=True)',
        ]
        for v in cat:
            base = P["col_label"]["__base__" + v]
            lines.append(f'df["{v}"] = df["{v}"].astype(str).str.replace(r"\\.0$", "", regex=True)')
            lines.append(f'df["{v}"] = pd.Categorical(df["{v}"], categories=["{base}"] + sorted(set(df["{v}"]) - {{"{base}"}}))   # baseline first')
        q = lambda v: f'Q("{v}")' if not re.match(r"^[A-Za-z_]\w*$", v) else v
        rhs = " + ".join(f"C({q(v)})" if v in cat else q(v) for v in xs)
        lines += [
            "",
            f'res = OrderedModel.from_formula("{q(y)} ~ {rhs}", data=df, distr="logit").fit(method="bfgs", disp=False, maxiter=2000)',
            "print(res.summary())",
            "",
            f'bt = BrantTest(res, use_formula=True, by_var=True, standardize={bool(spec.get("standardize", False))}, '
            f'cov_fallback="{spec.get("cov_fallback", "auto")}")',
            "print(bt.summary())",
        ]
        return json.dumps({"ok": True, "code": "\n".join(lines) + "\n"})
    except UserError as e:
        return json.dumps({"ok": False, "error": str(e)})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})


def get_csv(name):
    return DATA[name].to_csv(index=False)
