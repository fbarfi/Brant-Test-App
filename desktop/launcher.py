"""Desktop entry point for the Brant Test app.

Starts the app's local web server on this computer and shows the app in its
own application window (pywebview: WebKit on macOS, Edge WebView2 on Windows).
Closing the window quits the app.

If the window cannot be created (pywebview missing, or no WebView2 runtime on
an old Windows installation), the app falls back to the earlier behaviour: it
opens in the default browser and shows a small window with a Quit button and
the reason the app window could not be made.
All analysis runs locally; nothing is sent over the network.
"""

import os
import sys
import threading
import webbrowser

APP_NAME = "Brant Test"


def user_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    d = os.path.join(base, "BrantTestApp")
    os.makedirs(d, exist_ok=True)
    return d


# matplotlib needs a writable cache folder; set it before the engine imports it
os.environ.setdefault("MPLCONFIGDIR", os.path.join(user_dir(), "matplotlib"))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def log(msg):
    """Append a line to a log file in the user folder (the app has no console)."""
    try:
        with open(os.path.join(user_dir(), "launcher.log"), "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except OSError:
        pass


def webview2_available():
    """True if the Microsoft Edge WebView2 runtime is installed (Windows only)."""
    if os.name != "nt":
        return True
    try:
        import winreg
    except ImportError:
        return False
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    keys = [(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
            (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}")]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as k:
                version, _ = winreg.QueryValueEx(k, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def run_in_window(url):
    """Show the app in its own window. Returns None on success, otherwise the reason no window could be made."""
    if not webview2_available():
        reason = "The Microsoft Edge WebView2 runtime is not installed."
        log(reason + " Using the browser instead.")
        return reason
    try:
        import webview
    except Exception as e:  # pywebview not installed or not bundled
        log(f"pywebview unavailable ({e!r}); using the browser instead.")
        return "pywebview is not installed." + ("" if getattr(sys, "frozen", False) else
                                                 f"  Install it with:  {sys.executable} -m pip install pywebview")
    try:
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True   # Save CSV / PNG / SVG buttons
        except Exception:
            pass
        webview.create_window(APP_NAME, url, width=1400, height=900, min_size=(900, 600),
                              text_select=True)
        kwargs = {"gui": "edgechromium"} if os.name == "nt" else {}
        webview.start(private_mode=False, storage_path=os.path.join(user_dir(), "webview"), **kwargs)
        return None
    except Exception as e:
        log(f"The app window could not be opened ({e!r}); using the browser instead.")
        return f"The app window could not be opened ({e})."


def run_in_browser(srv, url, reason=""):
    """Fallback: open the default browser and show a small window with a Quit button and the reason."""
    webbrowser.open(url)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        print(f"{APP_NAME} is running at {url}. Press Ctrl+C to stop.", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    root = tk.Tk()
    root.title(APP_NAME)
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=18)
    frm.grid()
    ttk.Label(frm, text=APP_NAME, font=("Helvetica", 15, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(frm, text="The app is running and has opened in your web browser.").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Label(frm, text=f"Address: {url}").grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 10))
    ttk.Label(frm, text="Keep this window open while you work. Quitting stops the app.",
              foreground="#555").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))
    if reason:
        ttk.Label(frm, text=f"Why not in its own window: {reason}", foreground="#a33", wraplength=520,
                  justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def quit_app():
        root.destroy()

    ttk.Button(frm, text="Open in browser", command=lambda: webbrowser.open(url)).grid(row=4, column=0, sticky="w")
    ttk.Button(frm, text="Quit", command=quit_app).grid(row=4, column=1, sticky="e")
    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.createcommand("::tk::mac::Quit", quit_app) if sys.platform == "darwin" else None
    root.mainloop()


def check_window_backend():
    """Exit 0 if pywebview and this system's window backend are importable, 1 otherwise (used by the build script)."""
    try:
        import webview  # noqa: F401
        if sys.platform == "darwin":
            import webview.platforms.cocoa  # noqa: F401
        elif os.name == "nt":
            import webview.platforms.edgechromium  # noqa: F401
    except Exception as e:
        print(f"window backend missing: {e!r}", flush=True)
        sys.exit(1)
    print("window backend ok", flush=True)
    sys.exit(0)


def main():
    if os.environ.get("BTA_CHECK_WINDOW"):       # used by the build script
        check_window_backend()
    srv = server.make_server("127.0.0.1", server.PORT)
    url = f"http://localhost:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if os.environ.get("BTA_NO_WINDOW"):          # used by the automated build test
        print(url, flush=True)
        threading.Event().wait()
        return
    try:
        reason = run_in_window(url)
        if reason:
            run_in_browser(srv, url, reason)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    # Windows apps re-launch themselves for any worker process a library starts (scikit-learn/joblib);
    # freeze_support lets those workers run instead of starting a second copy of the app
    import multiprocessing
    multiprocessing.freeze_support()
    main()
