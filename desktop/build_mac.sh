#!/bin/bash
# Builds "Brant Test.app" and a .dmg on this Mac, with the same steps as the GitHub workflow.
# Run from Terminal, in the repository folder:
#   bash desktop/build_mac.sh                 the kind of Mac this is (Apple silicon or Intel)
#   bash desktop/build_mac.sh intel           the Intel app (on Apple silicon it is built under Rosetta)
#   bash desktop/build_mac.sh apple-silicon   the Apple silicon app (needs an Apple silicon Mac)
#   bash desktop/build_mac.sh all             both (on an Apple silicon Mac)
# Options: PYTHON=/path/to/python3 (Python 3.10-3.13; 3.12 is used on GitHub), RUN_TESTS=1 (also run tests/test_app.py),
#          BTA_VERSION=1.0.0 (the version number stamped into the app).
# The Intel build needs a Python that can run as Intel: the python.org installer (universal2) can;
# Miniforge/Anaconda for Apple silicon cannot. It also needs Rosetta:
#   softwareupdate --install-rosetta --agree-to-license
# Packages go into private folders (.build-venv-<arch>), so no existing Python environment is changed.
# Results: dist/<arch>/Brant Test.app and dist/Brant-Test-macOS-<arch>.dmg
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=$([ "$(uname -m)" = "arm64" ] && echo apple-silicon || echo intel)
TARGET="${1:-$HOST}"

pick_python() {  # $1 = arch; prints a Python 3.10-3.13 that runs as that arch (3.12 first, as on GitHub)
  # Newer Pythons are skipped: packages such as pandas have no ready-made (binary) downloads for them yet,
  # so pip would compile them, and a universal2 Python labels such builds "universal2" even when they
  # contain only the build machine's architecture.
  local want=$([ "$1" = intel ] && echo x86_64 || echo arm64) c v
  for c in ${PYTHON:-} \
           /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
           /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
           /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
           /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 \
           python3.12 python3.13 python3.11 python3.10 /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    [ "$(arch -"$want" "$c" -c 'import platform; print(platform.machine())' 2>/dev/null)" = "$want" ] || continue
    v=$(arch -"$want" "$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
    case "$v" in
      3.10|3.11|3.12|3.13) command -v "$c"; return 0 ;;
      *) [ -n "${PYTHON:-}" ] && [ "$c" = "$PYTHON" ] && { echo "Note: $c is Python $v; 3.10-3.13 is recommended." >&2; command -v "$c"; return 0; } ;;
    esac
  done
  return 1
}

check_arch() {  # $1 = venv python, $2 = machine; every compiled module must contain that architecture
  local bad
  bad=$("$1" - "$2" <<'PY'
import sys, sysconfig, pathlib, subprocess
want = sys.argv[1]
site = pathlib.Path(sysconfig.get_paths()["platlib"])
bad = []
for so in site.rglob("*.so"):
    out = subprocess.run(["lipo", "-archs", str(so)], capture_output=True, text=True).stdout.split()
    if out and want not in out:
        bad.append(f"{so.relative_to(site)} ({' '.join(out)})")
print("\n".join(bad[:10]))
PY
)
  if [ -n "$bad" ]; then
    echo "These compiled files are not built for $2:"; echo "$bad"
    return 1
  fi
}

build_one() {  # $1 = apple-silicon | intel
  local A="$1" M PY VPY APP BIN PID OK i
  M=$([ "$A" = intel ] && echo x86_64 || echo arm64)
  if [ "$A" = apple-silicon ] && [ "$HOST" = intel ]; then
    echo "The Apple silicon app can only be built on an Apple silicon Mac."; return 1
  fi
  if [ "$A" = intel ] && [ "$HOST" = apple-silicon ] && ! arch -x86_64 /usr/bin/true 2>/dev/null; then
    echo "Rosetta is needed for the Intel build. Install it with:"
    echo "  softwareupdate --install-rosetta --agree-to-license"; return 1
  fi
  if ! PY=$(pick_python "$A"); then
    echo "No Python 3.10-3.13 that runs as $M was found."
    echo "Install Python 3.12 from python.org (the macOS installer is universal2), then run this again."
    return 1
  fi
  RUN="arch -$M"
  PYV=$($RUN "$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  echo "== [$A] Python: $PY ($PYV, $M)"
  VPY=".build-venv-$A/bin/python"
  # a build environment made with another Python version (or broken) is replaced
  if [ -x "$VPY" ] && [ "$($RUN "$VPY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" != "$PYV" ]; then
    echo "== [$A] Replacing .build-venv-$A (it was made with another Python)"
    rm -rf ".build-venv-$A"
  fi
  [ -x "$VPY" ] || $RUN "$PY" -m venv ".build-venv-$A"
  # --no-cache-dir: never reuse a wheel compiled earlier for the other architecture
  $RUN "$VPY" -m pip install --no-cache-dir --upgrade pip
  $RUN "$VPY" -m pip install --no-cache-dir --prefer-binary -r requirements.txt pyinstaller "pywebview>=5.0"
  if ! check_arch "$VPY" "$M"; then
    echo "Delete the folder .build-venv-$A and run this again."; return 1
  fi

  if [ "${RUN_TESTS:-0}" = "1" ]; then
    echo "== [$A] Checks of the computations"
    $RUN "$VPY" tests/test_app.py || return 1
  fi

  echo "== [$A] Build the app"
  APP="dist/$A/Brant Test.app"
  BIN="$APP/Contents/MacOS/Brant Test"
  rm -rf "build/$A" "$APP"
  $RUN "$VPY" -m PyInstaller desktop/app.spec --noconfirm --distpath "dist/$A" --workpath "build/$A"
  file "$BIN" | grep -q "$M" || { echo "The app was not built for $M."; return 1; }

  echo "== [$A] Check that the app can open its own window"
  BTA_CHECK_WINDOW=1 "$BIN" || { echo "The built app cannot open its own window (pywebview was not bundled)."; return 1; }

  echo "== [$A] Smoke test (the app answers an analysis request)"
  BTA_NO_WINDOW=1 "$BIN" & PID=$!
  OK=0
  for i in $(seq 1 60); do
    if curl -s -m 10 -X POST localhost:8766/api/load -d '{"name":"political_information"}' | grep -q '"ok": true'; then OK=1; break; fi
    sleep 2
  done
  if [ $OK = 1 ]; then
    curl -s -m 300 -X POST localhost:8766/api/run \
      -d '{"spec":{"dataset":"political_information","y":"info_rating","x":["collegeDegree","female","age","homeOwn","govt","length"]}}' \
      | grep -q 'pybrant' || OK=0
  fi
  kill $PID 2>/dev/null || true; wait $PID 2>/dev/null || true
  [ $OK = 1 ] || { echo "The app did not answer the test analysis."; return 1; }

  echo "== [$A] Disk image"
  rm -rf dmg && mkdir dmg && cp -R "$APP" dmg/ && ln -s /Applications dmg/Applications
  hdiutil create -volname "Brant Test" -srcfolder dmg -ov -format UDZO "dist/Brant-Test-macOS-$A.dmg"
  rm -rf dmg
  echo "== [$A] Done: $APP and dist/Brant-Test-macOS-$A.dmg"
}

case "$TARGET" in
  apple-silicon|intel) build_one "$TARGET" ;;
  all) build_one apple-silicon; build_one intel ;;
  *) echo "Unknown target '$TARGET'. Use apple-silicon, intel or all."; exit 1 ;;
esac
