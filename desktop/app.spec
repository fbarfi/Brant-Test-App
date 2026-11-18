# PyInstaller recipe for the Brant Test desktop app.
# Build from the repository root:  pyinstaller desktop/app.spec --noconfirm
import glob
import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))   # repository root
block_cipher = None
APP = "Brant Test"
VERSION = os.environ.get("BTA_VERSION", "1.0.0")

datas = [(os.path.join(ROOT, "web"), "web"), (os.path.join(ROOT, "data", "catalog.json"), "data")]
datas += [(f, "data") for f in glob.glob(os.path.join(ROOT, "data", "*.csv"))]

# pybrant and the formula engines statsmodels may use
hidden_libs = []
for lib in ["pybrant", "patsy", "formulaic", "interface_meta"]:
    try:
        hidden_libs += collect_submodules(lib, filter=lambda n: ".tests" not in n)
        datas += collect_data_files(lib, excludes=["**/tests/**"])
    except Exception as e:                      # a library that is not installed is reported, not fatal
        print(f"app.spec: could not collect {lib}: {e}")

# pywebview (the app's own window): its JavaScript and DLL files, and the backend for this system,
# which pywebview imports only when the window opens.
try:
    datas += collect_data_files("webview")
except Exception as e:                          # without pywebview the app opens in the browser instead
    print(f"app.spec: could not collect webview: {e}")
if sys.platform == "darwin":
    webview_backend = ["webview.platforms.cocoa", "objc", "AppKit", "Foundation", "WebKit", "Quartz",
                       "Security", "UniformTypeIdentifiers"]
elif sys.platform == "win32":
    webview_backend = ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr", "clr_loader"]
else:
    webview_backend = []

a = Analysis(
    [os.path.join(ROOT, "desktop", "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    binaries=[],
    hiddenimports=hidden_libs + webview_backend + [
        "server", "engine", "engine.api", "webview",
        "matplotlib.backends.backend_agg", "matplotlib.backends.backend_svg",
        "statsmodels.miscmodels.ordinal_model", "statsmodels.discrete.discrete_model", "statsmodels.api"],
    excludes=["IPython", "jupyter", "notebook", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter.test"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon = os.path.join(ROOT, "desktop", "icon.icns" if sys.platform == "darwin" else "icon.ico")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP, console=False, icon=icon,
          target_arch=None, codesign_identity=os.environ.get("MAC_SIGN_IDENTITY") or None,
          entitlements_file=os.path.join(ROOT, "desktop", "entitlements.plist") if sys.platform == "darwin" else None)
coll = COLLECT(exe, a.binaries, a.datas, name=APP)

if sys.platform == "darwin":
    app = BUNDLE(coll, name=f"{APP}.app", icon=icon, bundle_identifier="edu.ufl.polsci.branttest",
                 version=VERSION,
                 info_plist={"CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                             "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                             "NSHumanReadableCopyright": "Brant Test, Badredine Arfi"})
