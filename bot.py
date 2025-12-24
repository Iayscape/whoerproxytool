import os
import json
import time
import threading
import subprocess
import random
import argparse
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import requests
from datetime import datetime

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

APP_NAME = "Proxy Browser Launcher + Whoer 100%"
WHOER_URL = "https://whoer.net/"
IPINFO_URL = "https://ipinfo.io/json"
PLAYWRIGHT_PROFILE_DIRNAME = "playwright-profile"

# NEW: built-in provider
PROXYSCRAPE_URL = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&proxy_format=ipport&format=text&timeout=5000"
)

PROFILES_ROOT_NAME = "Brave Profile"
DEFAULT_PROFILE_NAME = "Default"


# ===================== Basic utils =====================
def desktop_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def profiles_root_dir() -> str:
    return os.path.join(desktop_path(), PROFILES_ROOT_NAME)


def playwright_profile_dir() -> str:
    return os.path.join(profiles_root_dir(), PLAYWRIGHT_PROFILE_DIRNAME)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def run_profiling_runner(duration_minutes: int = 15, headless: bool = True) -> None:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    curated_urls = [
        "https://openai.com/research",
        "https://huggingface.co/blog",
        "https://arxiv.org/list/cs.AI/recent",
        "https://towardsdatascience.com",
        "https://www.kaggle.com/discussions",
        "https://cloud.google.com/blog/products/compute",
        "https://aws.amazon.com/blogs/compute/",
        "https://learn.microsoft.com/en-us/azure/architecture/",
        "https://playwright.dev/python/",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
        "https://github.com/microsoft/playwright",
        "https://developers.google.com/web",
    ]

    user_data_dir = playwright_profile_dir()
    ensure_dir(user_data_dir)
    end_time = time.monotonic() + (duration_minutes * 60)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            viewport={"width": 1280, "height": 800},
        )
        try:
            page = context.new_page()
            while time.monotonic() < end_time:
                url = random.choice(curated_urls)
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                except PlaywrightTimeoutError:
                    continue

                time.sleep(random.uniform(2, 5))

                for _ in range(random.randint(3, 7)):
                    if time.monotonic() >= end_time:
                        break
                    page.mouse.wheel(0, random.randint(400, 1200))
                    time.sleep(random.uniform(0.3, 1.0))

                if time.monotonic() >= end_time:
                    break

                time.sleep(random.uniform(2, 8))
        finally:
            context.close()


def find_brave_exe() -> str | None:
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
                     r"BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def config_path(profile_dir: str) -> str:
    return os.path.join(profile_dir, "launcher_config.json")


def load_config(profile_dir: str) -> dict:
    cfg_path = config_path(profile_dir)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(profile_dir: str, cfg: dict) -> None:
    cfg_path = config_path(profile_dir)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def launch_brave(brave_exe: str, user_data_dir: str, proxy_hostport: str | None) -> None:
    args = [
        brave_exe,
        f'--user-data-dir={user_data_dir}',
        '--new-window',
        WHOER_URL
    ]
    if proxy_hostport:
        args.append(f'--proxy-server={proxy_hostport}')
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_current_tz() -> str:
    p = subprocess.run(["tzutil", "/g"], capture_output=True, text=True)
    return (p.stdout or "").strip()


def set_windows_timezone(tz_id: str) -> tuple[bool, str]:
    try:
        subprocess.run(["tzutil", "/s", tz_id], check=True, capture_output=True, text=True)
        return True, "Timezone changed."
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        return False, f"Fail change Timezone. Please Run as Administrator.\n{msg}"


def build_requests_proxies(host: str, port: str, username: str = "", password: str = "") -> dict:
    host = host.strip()
    port = port.strip()
    if not host or not port:
        return {}
    if username.strip():
        proxy = f"http://{username.strip()}:{password.strip()}@{host}:{port}"
    else:
        proxy = f"http://{host}:{port}"
    return {"http": proxy, "https": proxy}


def parse_proxy_line(line: str):
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    parts = raw.split(":")
    if len(parts) == 2:
        host, port = parts
        return {"host": host.strip(), "port": port.strip(), "user": "", "pass": "", "raw": raw}
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        pwd = ":".join(parts[3:])
        return {"host": host.strip(), "port": port.strip(), "user": user.strip(), "pass": pwd.strip(), "raw": raw}
    return None


def ipinfo_request(proxies: dict | None, timeout_s: int = 15) -> tuple[int, dict, str]:
    try:
        r = requests.get(IPINFO_URL, proxies=proxies, timeout=timeout_s)
        if r.status_code != 200:
            return r.status_code, {}, f"HTTP {r.status_code}"
        return 200, r.json(), ""
    except requests.exceptions.ProxyError:
        return 0, {}, "ProxyError"
    except requests.exceptions.ConnectTimeout:
        return 0, {}, "ConnectTimeout"
    except requests.exceptions.ReadTimeout:
        return 0, {}, "ReadTimeout"
    except requests.exceptions.SSLError:
        return 0, {}, "SSLError"
    except requests.exceptions.RequestException as e:
        return 0, {}, f"RequestException:{type(e).__name__}"
    except Exception as e:
        return 0, {}, f"Exception:{type(e).__name__}"


def fetch_proxyscrape_list(timeout_s: int = 15) -> tuple[bool, list[str], str]:
    """Fetch ip:port lines from ProxyScrape endpoint."""
    try:
        r = requests.get(PROXYSCRAPE_URL, timeout=timeout_s)
        if r.status_code != 200:
            return False, [], f"HTTP {r.status_code}"
        txt = (r.text or "").strip()
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        return True, lines, ""
    except requests.exceptions.ConnectTimeout:
        return False, [], "ConnectTimeout"
    except requests.exceptions.ReadTimeout:
        return False, [], "ReadTimeout"
    except requests.exceptions.RequestException as e:
        return False, [], f"RequestException:{type(e).__name__}"
    except Exception as e:
        return False, [], f"Exception:{type(e).__name__}"


# ===================== Timezone mapping helpers =====================
_TZUTIL_ITEMS_CACHE = None


def parse_utc_offset_minutes(display: str) -> int | None:
    if "(UTC" not in display:
        return None
    try:
        inside = display.split("(UTC", 1)[1].split(")", 1)[0].strip()
        if inside == "":
            return 0
        if inside.startswith("+"):
            sign = 1
            hhmm = inside[1:]
        elif inside.startswith("-"):
            sign = -1
            hhmm = inside[1:]
        else:
            return 0
        hh, mm = hhmm.split(":")
        return sign * (int(hh) * 60 + int(mm))
    except Exception:
        return None


def get_tzutil_items_cached() -> list[dict]:
    global _TZUTIL_ITEMS_CACHE
    if _TZUTIL_ITEMS_CACHE is not None:
        return _TZUTIL_ITEMS_CACHE

    p = subprocess.run(["tzutil", "/l"], capture_output=True, text=True)
    lines = [ln.rstrip() for ln in (p.stdout or "").splitlines() if ln.strip()]

    items = []
    i = 0
    while i < len(lines) - 1:
        display = lines[i]
        tzid = lines[i + 1]
        off_min = parse_utc_offset_minutes(display)
        items.append({"display": display, "id": tzid, "offset_min": off_min})
        i += 2

    _TZUTIL_ITEMS_CACHE = items
    return items


def iana_offset_minutes_now(iana_tz: str) -> int | None:
    if not iana_tz or iana_tz == "-":
        return None
    if ZoneInfo is None:
        return None
    try:
        dt = datetime.now(ZoneInfo(iana_tz))
        off = dt.utcoffset()
        if off is None:
            return None
        return int(off.total_seconds() // 60)
    except Exception:
        return None


def iana_to_windows_best(iana_tz: str) -> str:
    if not iana_tz or iana_tz in ("-", ""):
        return "(no map)"

    items = get_tzutil_items_cached()
    off = iana_offset_minutes_now(iana_tz)
    if off is None:
        return "(no map)"

    cands = [it for it in items if it["offset_min"] == off]
    if not cands:
        return "(no map)"

    keyword = ""
    if "/" in iana_tz:
        keyword = iana_tz.split("/")[-1].replace("_", " ").strip().lower()

    if keyword:
        for it in cands:
            if keyword in (it["display"] or "").lower():
                return it["id"]

    return cands[0]["id"]


def windows_tz_candidates_by_offset(offset_min: int) -> list[dict]:
    items = get_tzutil_items_cached()
    return [it for it in items if it["offset_min"] == offset_min]


# ===================== Scrollable Frame =====================
class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.window_id, width=event.width)

    def _bind_wheel(self, event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_wheel(self, event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        delta = -1 * (event.delta // 120)
        self.canvas.yview_scroll(delta, "units")


# ===================== Profiles helpers =====================
def list_profiles() -> list[tuple[str, str]]:
    root = profiles_root_dir()
    ensure_dir(root)
    out = []
    try:
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                out.append((name, p))
    except Exception:
        pass
    out.sort(key=lambda x: x[0].lower())
    return out


def sanitize_profile_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    name = (name or "").strip()
    for ch in bad:
        name = name.replace(ch, "")
    name = name.strip().strip(".")
    return name


# ===================== App =====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1040x900")
        self.minsize(940, 740)
        self.resizable(True, True)

        ensure_dir(profiles_root_dir())
        default_profile_dir = os.path.join(profiles_root_dir(), DEFAULT_PROFILE_NAME)
        ensure_dir(default_profile_dir)

        self.active_profile_dir = default_profile_dir
        self.cfg = load_config(self.active_profile_dir)

        self.brave_path_var = tk.StringVar(value=self.cfg.get("brave_exe", find_brave_exe() or ""))

        self.profile_selected_name_var = tk.StringVar(value=DEFAULT_PROFILE_NAME)
        self.profile_dir_var = tk.StringVar(value=self.cfg.get("profile_dir", self.active_profile_dir))

        self.proxy_hostport_var = tk.StringVar(value=self.cfg.get("proxy_hostport", ""))
        self.proxy_host_var = tk.StringVar(value=self.cfg.get("proxy_host", ""))
        self.proxy_port_var = tk.StringVar(value=self.cfg.get("proxy_port", ""))
        self.proxy_user_var = tk.StringVar(value=self.cfg.get("proxy_user", ""))
        self.proxy_pass_var = tk.StringVar(value=self.cfg.get("proxy_pass", ""))

        self.detect_ip_var = tk.StringVar(value="-")
        self.detect_country_var = tk.StringVar(value="-")
        self.detect_iana_tz_var = tk.StringVar(value="-")
        self.tz_windows_reco_var = tk.StringVar(value="-")
        self.tz_current_var = tk.StringVar(value=get_current_tz() or "-")
        self.mismatch_var = tk.StringVar(value="(Belum dicek)")

        # Manual UTC/GMT picker state
        self.utc_offset_var = tk.StringVar(value="UTC+00:00")
        self.manual_win_tz_pick_var = tk.StringVar(value="(belum dipilih)")

        # Auto options
        self.auto_proxy_source_var = tk.StringVar(value="provider")  # provider | proxyscrape
        self.auto_timeout_var = tk.IntVar(value=12)
        self.auto_stop_first_var = tk.BooleanVar(value=True)
        self.auto_progress_var = tk.IntVar(value=0)
        self.auto_status_var = tk.StringVar(value="Siap.")
        self.auto_is_running = False
        self.auto_results = []

        self.all_profile_names: list[str] = []
        self.profile_search_typed = ""
        self.profile_search_last_ts = 0.0

        self._build_ui()
        self.refresh_profile_list()
        self.load_profile_by_name(DEFAULT_PROFILE_NAME)

    def browse_brave(self):
        path = filedialog.askopenfilename(
            title="Select brave.exe",
            filetypes=[("Brave executable", "brave.exe"), ("All files", "*.*")]
        )
        if path:
            self.brave_path_var.set(path)
            self.save_current_profile_config()

    # ===== Unified detect state =====
    def unified_apply_detect_state(self, ip: str, country: str, iana_tz: str):
        ip = (ip or "-").strip()
        country = (country or "-").strip()
        iana_tz = (iana_tz or "-").strip()

        self.detect_ip_var.set(ip)
        self.detect_country_var.set(country)
        self.detect_iana_tz_var.set(iana_tz)

        win_tz = iana_to_windows_best(iana_tz)
        self.tz_windows_reco_var.set(win_tz)

        self.refresh_timezone()
        self.check_mismatch()

    # ===== Profile list/search/create =====
    def refresh_profile_list(self):
        profs = list_profiles()
        names = [n for n, _ in profs]
        if DEFAULT_PROFILE_NAME not in names:
            names.insert(0, DEFAULT_PROFILE_NAME)
        self.all_profile_names = names
        self.profile_combo["values"] = self.all_profile_names

    def _reset_profile_type_search_if_needed(self):
        now = time.time()
        if now - self.profile_search_last_ts > 1.2:
            self.profile_search_typed = ""
        self.profile_search_last_ts = now

    def on_profile_type_filter(self, event=None):
        ch = ""
        if event and getattr(event, "char", ""):
            ch = event.char

        if event and event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return

        self._reset_profile_type_search_if_needed()

        if event and event.keysym == "BackSpace":
            self.profile_search_typed = self.profile_search_typed[:-1]
        elif ch and ch.isprintable() and ch not in ("\r", "\n", "\t"):
            self.profile_search_typed += ch

        typed = self.profile_search_typed.strip().lower()
        if not typed:
            self.profile_combo["values"] = self.all_profile_names
            return

        filtered = [n for n in self.all_profile_names if typed in n.lower()]
        if not filtered:
            filtered = self.all_profile_names

        self.profile_combo["values"] = filtered
        try:
            self.profile_combo.event_generate("<Down>")
        except Exception:
            pass

    def create_new_profile(self):
        name = simpledialog.askstring("Create Profile", "New Profile Name:", parent=self)
        if name is None:
            return
        name = sanitize_profile_name(name)
        if not name:
            messagebox.showerror("Error", "Name Profile Empty / Invalid.")
            return

        new_dir = os.path.join(profiles_root_dir(), name)
        if os.path.exists(new_dir) and os.listdir(new_dir):
            ok = messagebox.askyesno("Duplicate", f"Folder profile '{name}' already.\nUse that profile?")
            if not ok:
                return
        ensure_dir(new_dir)

        cfg = {
            "brave_exe": self.brave_path_var.get().strip(),
            "profile_dir": new_dir,
            "proxy_hostport": "",
            "proxy_host": "",
            "proxy_port": "",
            "proxy_user": "",
            "proxy_pass": "",
            "auto_proxy_list": "",
            "auto_proxy_source": "provider",
        }
        save_config(new_dir, cfg)

        self.refresh_profile_list()
        self.profile_selected_name_var.set(name)
        self.load_profile_by_name(name)
        messagebox.showinfo("OK", f"Profile '{name}' created:\n{new_dir}")

    def load_profile_by_name(self, name: str):
        name = (name or "").strip()
        if not name:
            return

        p = os.path.join(profiles_root_dir(), name)
        if not os.path.isdir(p):
            messagebox.showwarning("Not Found", f"Profile '{name}' not found.")
            return

        self.active_profile_dir = p
        ensure_dir(self.active_profile_dir)

        cfg = load_config(self.active_profile_dir)
        self.cfg = cfg

        if cfg.get("brave_exe"):
            self.brave_path_var.set(cfg.get("brave_exe", ""))

        self.profile_dir_var.set(cfg.get("profile_dir", self.active_profile_dir))

        self.proxy_hostport_var.set(cfg.get("proxy_hostport", ""))
        self.proxy_host_var.set(cfg.get("proxy_host", ""))
        self.proxy_port_var.set(cfg.get("proxy_port", ""))
        self.proxy_user_var.set(cfg.get("proxy_user", ""))
        self.proxy_pass_var.set(cfg.get("proxy_pass", ""))

        if hasattr(self, "auto_list_text"):
            self.auto_list_text.delete("1.0", "end")
            if cfg.get("auto_proxy_list"):
                self.auto_list_text.insert("1.0", cfg.get("auto_proxy_list"))

        if cfg.get("auto_proxy_source"):
            self.auto_proxy_source_var.set(cfg.get("auto_proxy_source", "provider"))

        self.unified_apply_detect_state("-", "-", "-")
        self.manual_win_tz_pick_var.set("(no selected)")

    # ===== Config save =====
    def save_current_profile_config(self):
        prof_dir = self.profile_dir_var.get().strip()
        ensure_dir(prof_dir)
        cfg = {
            "brave_exe": self.brave_path_var.get().strip(),
            "profile_dir": prof_dir,
            "proxy_hostport": self.proxy_hostport_var.get().strip(),
            "proxy_host": self.proxy_host_var.get().strip(),
            "proxy_port": self.proxy_port_var.get().strip(),
            "proxy_user": self.proxy_user_var.get().strip(),
            "proxy_pass": self.proxy_pass_var.get().strip(),
            "auto_proxy_list": self.auto_list_text.get("1.0", "end").strip() if hasattr(self, "auto_list_text") else "",
            "auto_proxy_source": self.auto_proxy_source_var.get().strip(),
        }
        save_config(prof_dir, cfg)

    # ===== UI =====
    def _build_ui(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=12, pady=10)

        top = ttk.LabelFrame(outer, text="Brave & Profile Settings")
        top.pack(fill="x")

        row = ttk.Frame(top)
        row.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(row, text="Brave executable (brave.exe):").pack(anchor="w")
        r2 = ttk.Frame(row)
        r2.pack(fill="x", pady=4)
        r2.columnconfigure(0, weight=1)
        ttk.Entry(r2, textvariable=self.brave_path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(r2, text="Browse...", command=self.browse_brave).grid(row=0, column=1, padx=8)

        srow = ttk.Frame(top)
        srow.pack(fill="x", padx=10, pady=(2, 8))
        srow.columnconfigure(1, weight=1)

        ttk.Label(srow, text="Select Profile:").grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(srow, textvariable=self.profile_selected_name_var, state="readonly")
        self.profile_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.profile_combo.bind("<<ComboboxSelected>>", lambda e: self.load_profile_by_name(self.profile_selected_name_var.get()))
        self.profile_combo.bind("<KeyRelease>", self.on_profile_type_filter)
        ttk.Button(srow, text="Create New Profile...", command=self.create_new_profile).grid(row=0, column=2, sticky="e")

        ttk.Label(srow, text="Folder Path Profile:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(srow, textvariable=self.profile_dir_var, state="readonly").grid(row=1, column=1, columnspan=2,
                                                                                 sticky="ew", padx=(8, 0), pady=(6, 0))

        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True, pady=10)

        manual_tab = ScrollableFrame(nb)
        auto_tab = ScrollableFrame(nb)
        nb.add(manual_tab, text="Manual Settings")
        nb.add(auto_tab, text="Semi Auto Settings")

        self._build_manual_tab(manual_tab.content)
        self._build_auto_tab(auto_tab.content)

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Exit", command=self.destroy).pack(side="right")

    def _build_manual_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        brave_proxy = ttk.LabelFrame(parent, text="Proxy Browser(host:port)")
        brave_proxy.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        brave_proxy.columnconfigure(0, weight=1)

        ttk.Label(brave_proxy, text="Fill HOST:PORT").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        ttk.Entry(brave_proxy, textvariable=self.proxy_hostport_var).grid(row=1, column=0, sticky="ew", padx=10, pady=8)

        launch_row = ttk.Frame(brave_proxy)
        launch_row.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(launch_row, text="Launch Browser (With proxy)", command=self.manual_launch_brave).pack(side="left")
        ttk.Button(launch_row, text="Launch Browser (Without proxy)", command=self.manual_launch_brave_no_proxy).pack(side="left", padx=10)

        detect = ttk.LabelFrame(parent, text="Detect Proxy Country (username:pass optional)")
        detect.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        detect.columnconfigure(0, weight=1)

        grid = ttk.Frame(detect)
        grid.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        for i in range(4):
            grid.columnconfigure(i, weight=1)

        ttk.Label(grid, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.proxy_host_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(grid, text="Port").grid(row=0, column=1, sticky="w")
        ttk.Entry(grid, textvariable=self.proxy_port_var).grid(row=1, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(grid, text="Username").grid(row=0, column=2, sticky="w")
        ttk.Entry(grid, textvariable=self.proxy_user_var).grid(row=1, column=2, sticky="ew", padx=(0, 8))

        ttk.Label(grid, text="Password").grid(row=0, column=3, sticky="w")
        ttk.Entry(grid, textvariable=self.proxy_pass_var, show="*").grid(row=1, column=3, sticky="ew")

        btns = ttk.Frame(detect)
        btns.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(btns, text="Detect", command=self.detect_manual).pack(side="left")
        ttk.Button(btns, text="Apply Recomended Timezone (Sometimes Run as Admin Require)", command=self.apply_recommended_timezone).pack(side="left", padx=10)
        ttk.Button(btns, text="Refresh Timezone", command=self.refresh_timezone).pack(side="left")

        out = ttk.LabelFrame(parent, text="Results")
        out.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        out.columnconfigure(0, weight=1)

        outgrid = ttk.Frame(out)
        outgrid.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        outgrid.columnconfigure(1, weight=1)

        ttk.Label(outgrid, text="Detected IP:").grid(row=0, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.detect_ip_var).grid(row=0, column=1, sticky="w")

        ttk.Label(outgrid, text="Detected Country:").grid(row=1, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.detect_country_var).grid(row=1, column=1, sticky="w")

        ttk.Label(outgrid, text="Detected Timezone:").grid(row=2, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.detect_iana_tz_var).grid(row=2, column=1, sticky="w")

        ttk.Label(outgrid, text="Recomended Timezone (Windows):").grid(row=3, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.tz_windows_reco_var).grid(row=3, column=1, sticky="w")

        ttk.Label(outgrid, text="Windows Timezone(Now):").grid(row=4, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.tz_current_var).grid(row=4, column=1, sticky="w")

        ttk.Label(outgrid, text="Match Status:").grid(row=5, column=0, sticky="w")
        ttk.Label(outgrid, textvariable=self.mismatch_var).grid(row=5, column=1, sticky="w")

        mtz = ttk.LabelFrame(parent, text="Manual Timezone (Select UTC/GMT)")
        mtz.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 12))
        mtz.columnconfigure(1, weight=1)

        ttk.Label(mtz, text="Select Offset:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        offsets = [
            "UTC-12:00", "UTC-11:00", "UTC-10:00", "UTC-09:30", "UTC-09:00",
            "UTC-08:00", "UTC-07:00", "UTC-06:00", "UTC-05:00", "UTC-04:00",
            "UTC-03:30", "UTC-03:00", "UTC-02:00", "UTC-01:00", "UTC+00:00",
            "UTC+01:00", "UTC+02:00", "UTC+03:00", "UTC+03:30", "UTC+04:00",
            "UTC+04:30", "UTC+05:00", "UTC+05:30", "UTC+05:45", "UTC+06:00",
            "UTC+06:30", "UTC+07:00", "UTC+08:00", "UTC+08:45", "UTC+09:00",
            "UTC+09:30", "UTC+10:00", "UTC+10:30", "UTC+11:00", "UTC+12:00",
            "UTC+12:45", "UTC+13:00", "UTC+14:00"
        ]
        cb = ttk.Combobox(mtz, textvariable=self.utc_offset_var, values=offsets, state="readonly", width=12)
        cb.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(10, 6))

        ttk.Button(mtz, text="Search Timezone", command=self.manual_tz_pick_offset).grid(row=0, column=2, sticky="e", padx=10, pady=(10, 6))

        ttk.Label(mtz, text="Selected Timezone:").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
        ttk.Label(mtz, textvariable=self.manual_win_tz_pick_var).grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 10), pady=(0, 6))

        mbtn = ttk.Frame(mtz)
        mbtn.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(mbtn, text="Apply Timezone (Sometimes Run as Admin Require)", command=self.manual_tz_apply_selected).pack(side="left")
        ttk.Button(mbtn, text="Refresh Timezone", command=self.refresh_timezone).pack(side="left", padx=10)

    def _build_auto_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        top = ttk.LabelFrame(parent, text="Proxy Filter")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        top.columnconfigure(0, weight=1)

        src_row = ttk.Frame(top)
        src_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ttk.Label(src_row, text="Proxy Source:").pack(side="left")

        ttk.Radiobutton(src_row, text="Manual Source", value="provider",
                        variable=self.auto_proxy_source_var,
                        command=self.save_current_profile_config).pack(side="left", padx=10)

        ttk.Button(src_row, text="Generate From ProxyScrape", command=self.fetch_proxyscrape_into_text).pack(side="right")

        hint = ("Format Use:\n"
                "  host:port\n"
                "or\n"
                "  host:port:user:pass\n"
                ""
                )
        ttk.Label(top, text=hint).grid(row=1, column=0, sticky="w", padx=10, pady=(4, 0))

        self.auto_list_text = tk.Text(top, height=10)
        self.auto_list_text.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        if self.cfg.get("auto_proxy_list"):
            self.auto_list_text.insert("1.0", self.cfg["auto_proxy_list"])

        ctl = ttk.Frame(top)
        ctl.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Label(ctl, text="Timeout (second):").pack(side="left")
        ttk.Spinbox(ctl, from_=5, to=60, textvariable=self.auto_timeout_var, width=6).pack(side="left", padx=6)
        ttk.Checkbutton(ctl, text="Stop When Proxy is Alive", variable=self.auto_stop_first_var).pack(side="left", padx=12)
        ttk.Button(ctl, text="Load from file .txt", command=self.load_proxy_file).pack(side="right")

        bar = ttk.Frame(parent)
        bar.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        bar.columnconfigure(0, weight=1)

        self.auto_pb = ttk.Progressbar(bar, orient="horizontal", mode="determinate",
                                       maximum=100, variable=self.auto_progress_var)
        self.auto_pb.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, textvariable=self.auto_status_var, width=14).grid(row=0, column=1, padx=10)

        btns = ttk.Frame(bar)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Check proxies", command=self.auto_test_proxies).pack(side="left")
        ttk.Button(btns, text="Use selected proxy (fill to manual settings)", command=self.use_selected_proxy).pack(side="left", padx=10)
        ttk.Button(btns, text="Launch Browser (selected proxy)", command=self.auto_launch_selected).pack(side="left", padx=10)

        table_frame = ttk.LabelFrame(parent, text="Results Proxy (ALIVE)")
        table_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        table_frame.columnconfigure(0, weight=1)

        cols = ("proxy", "status", "latency_ms", "ip", "country", "IP_timezone", "WIN_timezone")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=10)
        for c in cols:
            self.tree.heading(c, text=c)

        self.tree.column("proxy", width=220)
        self.tree.column("status", width=70)
        self.tree.column("latency_ms", width=90)
        self.tree.column("ip", width=150)
        self.tree.column("country", width=70)
        self.tree.column("IP_timezone", width=170)
        self.tree.column("WIN_timezone", width=220)

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.grid(row=0, column=0, sticky="ew", padx=(10, 0), pady=10)
        yscroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)

        log_frame = ttk.LabelFrame(parent, text="Checking Process (realtime)")
        log_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 20))
        log_frame.columnconfigure(0, weight=1)

        self.auto_log = tk.Text(log_frame, height=10)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.auto_log.yview)
        self.auto_log.configure(yscrollcommand=log_scroll.set)

        self.auto_log.grid(row=0, column=0, sticky="ew", padx=(10, 0), pady=10)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.auto_log.configure(state="disabled")

    # ===== Auto: fetch provider =====
    def fetch_proxyscrape_into_text(self):
        self.auto_status_var.set("Fetch...")
        self.update_idletasks()

        ok, lines, err = fetch_proxyscrape_list(timeout_s=20)
        if not ok:
            messagebox.showerror("Failed", f"Failed fetch ProxyScrape: {err}")
            self.auto_status_var.set("Ready.")
            return

        self.auto_list_text.delete("1.0", "end")
        self.auto_list_text.insert("1.0", "\n".join(lines) + ("\n" if lines else ""))
        self.save_current_profile_config()
        messagebox.showinfo("OK", f"Fetch {len(lines)} proxy from ProxyScrape.\n")
        self.auto_status_var.set("Ready.")

    # ===== Manual tz by offset =====
    def _parse_offset_string_to_minutes(self, s: str) -> int | None:
        s = (s or "").strip().upper()
        if not s.startswith("UTC"):
            return None
        rest = s[3:].strip()
        if rest in ("", "+00:00"):
            return 0
        try:
            sign = 1
            if rest.startswith("+"):
                sign = 1
                hhmm = rest[1:]
            elif rest.startswith("-"):
                sign = -1
                hhmm = rest[1:]
            else:
                return None
            hh, mm = hhmm.split(":")
            return sign * (int(hh) * 60 + int(mm))
        except Exception:
            return None

    def manual_tz_pick_offset(self):
        off_min = self._parse_offset_string_to_minutes(self.utc_offset_var.get())
        if off_min is None:
            messagebox.showerror("Error", "Format offset invalid.")
            return

        cands = windows_tz_candidates_by_offset(off_min)
        if not cands:
            self.manual_win_tz_pick_var.set("(no match)")
            messagebox.showwarning("None", "None Windows with current timezone")
            return

        pick = None
        for it in cands:
            if it["id"].upper().startswith("UTC") or "COORDINATED UNIVERSAL TIME" in (it["display"] or "").upper():
                pick = it
                break
        if pick is None:
            pick = cands[0]

        self.manual_win_tz_pick_var.set(pick["id"])
        self.check_mismatch()

    def manual_tz_apply_selected(self):
        tzid = (self.manual_win_tz_pick_var.get() or "").strip()
        if not tzid or tzid in ("(Not Selected)", "(no match)"):
            messagebox.showwarning("Not Selected", "Please Hit Search Timezone First")
            return

        cur = get_current_tz() or "-"
        if cur == tzid:
            self.refresh_timezone()
            self.check_mismatch()
            messagebox.showinfo("OK", "Timezone Windows OK")
            return

        ok = messagebox.askyesno("Confirm", f"Change Windows Timezone from:\n{cur}\n\nto:\n{tzid}\n\nNext?")
        if not ok:
            return

        ok2, msg = set_windows_timezone(tzid)
        if ok2:
            self.refresh_timezone()
            self.check_mismatch()
            messagebox.showinfo("Success", "Timezone changed succesfully")
        else:
            messagebox.showerror("Gagal", msg)

    # ===== Auto helpers =====
    def load_proxy_file(self):
        path = filedialog.askopenfilename(
            title="Select file proxy list(.txt)",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        self.auto_list_text.delete("1.0", "end")
        self.auto_list_text.insert("1.0", content)
        self.save_current_profile_config()

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def log_auto(self, msg: str):
        self.auto_log.configure(state="normal")
        self.auto_log.insert("end", msg + "\n")
        self.auto_log.see("end")
        self.auto_log.configure(state="disabled")

    def refresh_timezone(self):
        self.tz_current_var.set(get_current_tz() or "-")

    def check_mismatch(self):
        cur = (get_current_tz() or "-").strip()
        reco = (self.tz_windows_reco_var.get() or "-").strip()
        if reco in ("-", "", "(no map)"):
            self.mismatch_var.set("(No recomended timezone)")
        elif cur == reco:
            self.mismatch_var.set("OK (Timezone Match)")
        else:
            self.mismatch_var.set("Mismatch (Timezone Mismatch)")

    def _auto_set_remaining_list(self, remaining_lines: list[str]):
        self.auto_list_text.delete("1.0", "end")
        if remaining_lines:
            self.auto_list_text.insert("1.0", "\n".join(remaining_lines).rstrip() + "\n")

    def _get_lines_for_testing(self) -> list[str]:
        """
        Decide proxy lines source:
        - provider: from textbox as-is
        - proxyscrape: if textbox empty, fetch automatically; else use textbox content
        """
        source = self.auto_proxy_source_var.get().strip()
        current = [ln.strip() for ln in self.auto_list_text.get("1.0", "end").splitlines() if ln.strip()]

        if source == "proxyscrape":
            # If user hasn't fetched yet (textbox empty), auto-fetch now.
            if not current:
                ok, lines, err = fetch_proxyscrape_list(timeout_s=20)
                if not ok:
                    raise RuntimeError(f"Failed fetch ProxyScrape: {err}")
                self.auto_list_text.delete("1.0", "end")
                self.auto_list_text.insert("1.0", "\n".join(lines) + ("\n" if lines else ""))
                self.save_current_profile_config()
                return lines
            return current

        # provider
        return current

    def auto_test_proxies(self):
        if ZoneInfo is None:
            messagebox.showerror("ZoneInfo not available", "Please Install tzdata :\n\npip install tzdata")
            return

        if self.auto_is_running:
            messagebox.showwarning("Running", "Running")
            return

        try:
            original_lines = self._get_lines_for_testing()
        except Exception as e:
            messagebox.showerror("Failed", str(e))
            return

        candidates = []
        for idx, line in enumerate(original_lines):
            p = parse_proxy_line(line)
            if p:
                candidates.append((idx, line, p))

        if not candidates:
            messagebox.showwarning("List empty", "Fill list first")
            return

        timeout_s = int(self.auto_timeout_var.get())
        stop_first = bool(self.auto_stop_first_var.get())

        self.clear_tree()
        self.auto_results = []
        self.auto_progress_var.set(0)
        self.auto_status_var.set("Mulai")

        self.auto_log.configure(state="normal")
        self.auto_log.delete("1.0", "end")
        self.auto_log.configure(state="disabled")

        self.auto_is_running = True
        get_tzutil_items_cached()

        def ui_log(s: str):
            self.after(0, lambda: self.log_auto(s))

        def ui_row(vals):
            self.after(0, lambda: self.tree.insert("", "end", values=vals))

        def ui_prog(pct: int, text: str):
            self.after(0, lambda: (self.auto_progress_var.set(pct), self.auto_status_var.set(text)))

        def ui_replace_remaining(remaining):
            self.after(0, lambda: self._auto_set_remaining_list(remaining))

        def worker():
            total = len(candidates)
            ui_log(f"starting test {total} proxy (timeout={timeout_s}s, stop_first={stop_first}, source={self.auto_proxy_source_var.get()})")

            tested_line_indexes = set()

            for seq, (line_idx, line_text, p) in enumerate(candidates, start=1):
                host, port, user, pwd = p["host"], p["port"], p["user"], p["pass"]
                show_proxy = f"{host}:{port}"
                ui_log(f"[{seq}/{total}] {show_proxy} - checking...")

                t0 = time.time()
                status = "FAIL"
                ip = "-"
                cc = "-"
                iana_tz = "-"
                win_tz = "-"
                err = ""

                proxies = build_requests_proxies(host, port, user, pwd)
                code, info, err = ipinfo_request(proxies=proxies, timeout_s=timeout_s)
                latency_ms = int((time.time() - t0) * 1000)

                tested_line_indexes.add(line_idx)

                if code == 200:
                    status = "OK"
                    ip = info.get("ip", "-")
                    cc = info.get("country", "-")
                    iana_tz = info.get("timezone", "-")
                    win_tz = iana_to_windows_best(iana_tz)

                proxy_show = show_proxy + (":***" if user else "")
                rec = {
                    "host": host, "port": port, "user": user, "pass": pwd,
                    "proxy_show": proxy_show,
                    "status": status,
                    "latency_ms": latency_ms,
                    "ip": ip, "country": cc,
                    "iana_tz": iana_tz,
                    "win_tz": win_tz,
                    "error": err,
                    "source_line": line_text,
                }
                self.auto_results.append(rec)

                if status == "OK":
                    ui_row((proxy_show, status, latency_ms, ip, cc, iana_tz, win_tz))
                    ui_log(f"{show_proxy} - OK(200) - {cc} - {iana_tz} -> {win_tz} - {latency_ms}ms")
                else:
                    ui_log(f"{show_proxy} - ERROR({err or 'Unknown'}) - {latency_ms}ms")

                pct = int((seq / total) * 100)
                ui_prog(pct, f"{pct}%")

                remaining_lines = [ln for i, ln in enumerate(original_lines) if i not in tested_line_indexes]
                ui_replace_remaining(remaining_lines)

                if stop_first and status == "OK":
                    ui_log("Found Alive Proxy")
                    break

            ui_prog(100, "Done")
            ui_log("Done.")
            self.auto_is_running = False
            self.after(0, lambda: messagebox.showinfo(
                "Done",
                "Testing Done.\n- Table will show Alive Proxy"
            ))
            self.after(0, self.save_current_profile_config)

        threading.Thread(target=worker, daemon=True).start()

    def _get_selected_ok_record(self):
        sel = self.tree.selection()
        if not sel:
            return None, "Select Alive Proxy From Table"
        values = self.tree.item(sel[0], "values")
        if not values:
            return None, "Selection empty."
        proxy_show, status, latency_ms, ip, cc, iana_tz, win_tz = values
        if status != "OK":
            return None, "Select Alive Proxy"

        hostport = str(proxy_show).replace(":***", "")
        rec = None
        for r in self.auto_results:
            if r["proxy_show"].replace(":***", "") == hostport and r["status"] == "OK":
                rec = r
                break
        if not rec:
            return None, "No Data Proxy"
        return rec, ""

    def use_selected_proxy(self):
        rec, err = self._get_selected_ok_record()
        if not rec:
            messagebox.showwarning("Cannot", err)
            return

        self.proxy_hostport_var.set(f'{rec["host"]}:{rec["port"]}')
        self.proxy_host_var.set(rec["host"])
        self.proxy_port_var.set(rec["port"])
        self.proxy_user_var.set(rec["user"])
        self.proxy_pass_var.set(rec["pass"])

        self.unified_apply_detect_state(rec["ip"], rec["country"], rec["iana_tz"])
        self.save_current_profile_config()
        messagebox.showinfo("OK", "Alive Proxy has filled")

    def auto_launch_selected(self):
        rec, err = self._get_selected_ok_record()
        if not rec:
            messagebox.showwarning("Cannot", err)
            return

        brave_exe = self.brave_path_var.get().strip()
        prof_dir = self.profile_dir_var.get().strip()
        if not brave_exe or not os.path.isfile(brave_exe):
            messagebox.showerror("Error", "Path brave.exe invalid.")
            return

        ensure_dir(prof_dir)
        proxy_hp = f'{rec["host"]}:{rec["port"]}'
        self.proxy_hostport_var.set(proxy_hp)

        self.unified_apply_detect_state(rec["ip"], rec["country"], rec["iana_tz"])

        cur = get_current_tz() or "-"
        reco = (self.tz_windows_reco_var.get() or "").strip()
        if reco not in ("", "-", "(no map)") and cur != reco:
            ok = messagebox.askyesno(
                "Timezone mismatch",
                f"Now Timezone:\n{cur}\n\nRecomended:\n{reco}\n\nApply timezone?"
            )
            if ok:
                ok2, msg = set_windows_timezone(reco)
                if not ok2:
                    messagebox.showerror("Gagal", msg)

        self.save_current_profile_config()
        launch_brave(brave_exe, prof_dir, proxy_hp)
        messagebox.showinfo("Success", "Browser Opened With Proxy")

    # ===== Manual actions =====
    def manual_launch_brave(self):
        brave_exe = self.brave_path_var.get().strip()
        prof_dir = self.profile_dir_var.get().strip()
        proxy_hp = self.proxy_hostport_var.get().strip() or None

        if not brave_exe or not os.path.isfile(brave_exe):
            messagebox.showerror("Error", "Path brave.exe invalid.")
            return

        ensure_dir(prof_dir)
        self.save_current_profile_config()
        launch_brave(brave_exe, prof_dir, proxy_hp)
        messagebox.showinfo("OK", "Browser Opened With Proxy")

    def manual_launch_brave_no_proxy(self):
        brave_exe = self.brave_path_var.get().strip()
        prof_dir = self.profile_dir_var.get().strip()

        if not brave_exe or not os.path.isfile(brave_exe):
            messagebox.showerror("Error", "Path brave.exe invalid.")
            return

        ensure_dir(prof_dir)
        self.save_current_profile_config()
        launch_brave(brave_exe, prof_dir, proxy_hostport=None)
        messagebox.showinfo("OK", "Browser Opened (Without proxy)")

    def detect_manual(self):
        if ZoneInfo is None:
            messagebox.showerror("ZoneInfo not available", "Please Install tzdata :\n\npip install tzdata")
            return

        host = self.proxy_host_var.get().strip()
        port = self.proxy_port_var.get().strip()
        user = self.proxy_user_var.get().strip()
        pwd = self.proxy_pass_var.get().strip()

        if not host or not port:
            messagebox.showwarning("Proxy empty", "Fill Host and Port")
            return

        proxies = build_requests_proxies(host, port, user, pwd)
        code, info, err = ipinfo_request(proxies=proxies, timeout_s=15)
        if code != 200:
            messagebox.showerror("Failed", f"Failed: {err}")
            return

        ip = info.get("ip", "-")
        country = info.get("country", "-")
        iana_tz = info.get("timezone", "-")
        self.unified_apply_detect_state(ip, country, iana_tz)
        self.save_current_profile_config()

    def apply_recommended_timezone(self):
        reco = (self.tz_windows_reco_var.get() or "").strip()
        if reco in ("", "-", "(no map)"):
            messagebox.showwarning("No Any Recomend", "Recomended Timezone not available")
            return

        cur = get_current_tz() or "-"
        if cur == reco:
            self.refresh_timezone()
            self.check_mismatch()
            messagebox.showinfo("OK", "Timezone Windows as Recomend")
            return

        ok = messagebox.askyesno("Confirm", f"Change Windows Timezone from:\n{cur}\n\nto:\n{reco}\n\nNext?")
        if not ok:
            return

        ok2, msg = set_windows_timezone(reco)
        if ok2:
            self.refresh_timezone()
            self.check_mismatch()
            messagebox.showinfo("Success", "Timezone has changed, Please Refresh whoer status")
        else:
            messagebox.showerror("Failed", msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy Browser Launcher + Profiling Runner")
    parser.add_argument("--profiling-runner", action="store_true", help="Run Playwright profiling runner")
    parser.add_argument("--duration-minutes", type=int, default=15, help="Total runtime in minutes")
    parser.add_argument("--headed", action="store_true", help="Run Chromium with UI")
    args = parser.parse_args()

    if args.profiling_runner:
        run_profiling_runner(duration_minutes=args.duration_minutes, headless=not args.headed)
        return

    App().mainloop()


if __name__ == "__main__":
    main()
