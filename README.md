# Brant Test

A point-and-click desktop app for Brant's (1990) test of the proportional-odds (parallel regression)
assumption of the ordered logit model. It opens in its own window on macOS (Apple silicon and Intel)
and Windows; no code is typed and nothing else needs to be installed.

The computations use [pybrant](https://github.com/fbarfi/pybrant) for the Brant test and statsmodels'
`OrderedModel` for the ordered logit. Everything runs on the user's computer.

## What the app does

- **Data:** two example datasets (ANES 2000 interviewer ratings of political information; World Values
  Survey attitudes to government action on poverty) or any CSV file.
- **Specification:** the ordered outcome and the order of its categories, covariates, categorical coding
  with a chosen baseline (a categorical covariate is tested jointly over its dummies), and pybrant's
  options (`cov_fallback`, `standardize`).
- **The model: equations and assumptions:** a panel above the results shows the ordered logit, the
  equation for the current specification, the Brant statistic with its degrees of freedom, and the
  assumptions. It follows the form as it changes.
- **Results:** ordered-logit slopes (optionally odds ratios) and cutpoints, model fit, the Brant test
  (omnibus and for each covariate), the slopes of the separate binary logits of y > j, a figure of those
  slopes across the splits, and a plain-language reading of the test. Each table can be copied as
  LaTeX or saved as CSV; the figure can be saved as PNG or SVG. **Copy Python code** gives a script
  (statsmodels + pybrant) that reproduces the run.

## Installing

Download from the **Releases** page:
- `Brant-Test-macOS-apple-silicon.dmg` (M1 and later) or `Brant-Test-macOS-intel.dmg`: open it and
  drag **Brant Test** onto Applications. The app is not signed: the first time, right-click it and
  choose **Open**.
- `Brant.Test.Setup.exe` (Windows 10/11): run the installer.

## Running from source

```
pip install -r requirements.txt pywebview
python desktop/launcher.py      # own window
python server.py                # or in the browser at http://localhost:8766
```

## Building the apps

GitHub builds the apps (`.github/workflows/build-apps.yml`):
- **Release build:** publish a release with a new tag such as `v1.0.0`. The workflow builds all three
  apps, stamps them with the version, and attaches them to the release.
- **Manual build:** Actions → Build desktop apps → Run workflow, choosing all apps or one. The files are
  kept as artifacts for one day.

Each job first runs `tests/test_app.py`, then smoke-tests the built app. Jobs stop after 90 minutes.

Both Mac apps can also be built on an Apple silicon Mac, free of GitHub minutes:

```
bash desktop/build_mac.sh all        # BTA_VERSION=1.0.0 sets the version; RUN_TESTS=1 runs tests/test_app.py
```

## Checks

`tests/test_app.py` compares the app's Brant statistics with pybrant applied directly to the same fit
and, for the example data, with the values of the Advanced Statistics Lab's cross-check; it also checks
the cutpoints, the separate binary logits, categorical covariates, uploaded data and error messages.

## Reference

Brant, R. (1990). Assessing proportionality in the proportional odds model for ordinal logistic
regression. *Biometrics* 46(4): 1171–1178.

## License

MIT. Example data: American National Election Study 2000 (via `pscl::politicalInformation`; Jackman 2009)
and World Values Survey (via `carData::WVS`; Fox and Andersen 2006).
