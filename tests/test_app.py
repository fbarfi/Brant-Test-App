"""Checks of the app's computations (engine/api.py).

    python tests/test_app.py

1. The Brant statistics reported by the app equal pybrant's BrantTest applied directly to the same
   OrderedModel fit, and, for the political_information example, the values in the Advanced
   Statistics Lab's cross-check report (the Lab's own implementation of Brant's test and the code of
   statsmodels pull request #10248 agree on them to 14 digits).
2. The cutpoints equal statsmodels' transform_threshold_params.
3. The separate binary-logit slopes equal statsmodels Logit fits of 1{y > j}.
4. A numeric outcome and an uploaded CSV work; an outcome with two categories is refused.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import api  # noqa: E402

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {label}{': ' + detail if detail else ''}", flush=True)


def run(spec):
    r = json.loads(api.run(json.dumps(spec)))
    if not r["ok"]:
        print(r.get("trace", r["error"]))
    return r


def table(r, title_start):
    return [o for o in r["outputs"] if o.get("title", "").startswith(title_start)][0]


# 1. political_information: the Lab's cross-check values
assert json.loads(api.load("political_information"))["ok"]
spec = {"dataset": "political_information", "y": "info_rating",
        "x": ["collegeDegree", "female", "age", "homeOwn", "govt", "length"], "categorical": [], "baselines": {}}
r = run(spec)
check("political_information runs", r["ok"])
b = {row["Test for"]: row for row in table(r, "Brant test")["rows"]}
lab = {"Omnibus (all covariates)": 32.7908, "collegeDegree": 1.39978, "female": 6.82038, "age": 3.44636,
       "homeOwn": 5.00474, "govt": 4.9231, "length": 10.3321}
for k, v in lab.items():
    got = b[k]["χ²"]
    check(f"Brant χ² {k} equals the Lab's cross-check value", abs(got - v) <= 5e-4 * max(1, abs(v)), f"{got:.5f} vs {v}")
check("omnibus df = (J − 2)K = 3·6 = 18", b["Omnibus (all covariates)"]["df"] == 18, str(b["Omnibus (all covariates)"]["df"]))

# direct pybrant on the same fit
from pybrant import BrantTest  # noqa: E402
P = api._prepare(spec)
mod, res = api._fit_ordered(P)
direct = BrantTest(res, use_formula=True, by_var=True).test_results()
check("omnibus equals pybrant applied directly", abs(direct.omnibus_stat - b["Omnibus (all covariates)"]["χ²"]) < 1e-9,
      f"{direct.omnibus_stat:.8f}")
for _, row in direct.by_variable.iterrows():
    name = api._term_name(P, row["Test for"])
    check(f"per-term test {name} equals pybrant", abs(row["Chi-square"] - b[name]["χ²"]) < 1e-9)

# 2. cutpoints
kap = table(r, "Ordered logit: cutpoints")["rows"]
th = np.asarray(res.model.transform_threshold_params(res.params))[1:-1]
check("cutpoints equal transform_threshold_params", np.allclose([k["Estimate"] for k in kap], th, atol=1e-10),
      str(np.round(th, 4)))

# 3. binary logits
import statsmodels.api as sm  # noqa: E402
X = sm.add_constant(np.asarray(mod.exog, float), has_constant="add")
codes = np.asarray(P["work"].iloc[:, 0].cat.codes)
srows = table(r, "Slopes of the separate binary logits")["rows"]
col = f"y > {P['order'][0]}"
lr = sm.Logit((codes > 0).astype(float), X).fit(disp=False)
got = [float(s[col].split(" ")[0]) for s in srows]
check("binary logit of y > first category matches statsmodels Logit", np.allclose(got, np.asarray(lr.params)[1:], atol=5e-4))

# wvs: categorical covariates tested jointly
assert json.loads(api.load("wvs"))["ok"]
r2 = run({"dataset": "wvs", "y": "poverty", "x": ["country", "gender", "religion", "degree", "age"],
          "categorical": [], "baselines": {"country": "USA"}})
check("wvs runs", r2["ok"])
b2 = {row["Test for"]: row for row in table(r2, "Brant test")["rows"]}
check("country (4 countries) tested jointly with (J − 2)·3 = 3 df", b2["country"]["df"] == 3, str(b2["country"]["df"]))
check("slope table names the baseline-coded dummies", any("country: Norway" == o["term"] for o in table(r2, "Ordered logit: slopes")["rows"]))

# 4. uploaded CSV with a numeric outcome; too few categories
rng = np.random.default_rng(1)
n = 800
x = rng.normal(size=n)
ystar = 0.8 * x + rng.logistic(size=n)
df = pd.DataFrame({"y": np.searchsorted([-1, 0, 1], ystar) + 1, "x": x, "g": rng.choice(["a", "b", "c"], n)})
assert json.loads(api.register("sim", df.to_csv(index=False)))["ok"]
r3 = run({"dataset": "sim", "y": "y", "x": ["x", "g"], "categorical": [], "baselines": {}})
check("uploaded data with a numeric outcome run", r3["ok"])
b3 = {row["Test for"]: row for row in table(r3, "Brant test")["rows"]}
check("data simulated under proportional odds: x not rejected at 1%", b3["x"]["p"] > 0.01, f"p = {b3['x']['p']:.3f}")
df["y2"] = (df["y"] > 2).astype(int)
assert json.loads(api.register("sim2", df.to_csv(index=False)))["ok"]
r4 = json.loads(api.run(json.dumps({"dataset": "sim2", "y": "y2", "x": ["x"]})))
check("an outcome with two categories is refused with a message", (not r4["ok"]) and "three" in r4["error"], r4.get("error", ""))
code = json.loads(api.python_code(json.dumps(spec)))
check("Python code is produced", code["ok"] and "BrantTest" in code["code"])

print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
sys.exit(0 if all(RESULTS) else 1)
