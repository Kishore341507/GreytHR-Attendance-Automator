import os
import sys
import time
import json
import ctypes
import threading
import webbrowser
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw

# --- Paths & Storage ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "greythr_url": "",
    "username": "",
    "password": "",
    "work_location": "Office",
    "headless": True,
    "check_interval_seconds": 120,
    "idle_threshold_seconds": 300,
}

DEFAULT_STATE = {
    "last_marked_date": "",
    "skipped_date": "",
    "snooze_until": 0,
}

# --- Config & State Helpers ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(json.load(f))
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(data):
    try:
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=4)
        return True
    except Exception:
        return False

def load_state():
    if not os.path.exists(STATE_FILE):
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = DEFAULT_STATE.copy()
            st.update(json.load(f))
            return st
    except Exception:
        return DEFAULT_STATE.copy()

def save_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False

def get_today():
    return date.today().isoformat()

def is_weekend():
    return date.today().weekday() >= 5

# Fixed Office Hours: 9:00 AM to 8:00 PM (20:00)
OFFICE_START_HOUR = 9
OFFICE_END_HOUR = 20

def is_office_hours():
    now = datetime.now()
    start_dt = datetime.combine(now.date(), datetime.min.time()).replace(hour=OFFICE_START_HOUR, minute=0)
    end_dt = datetime.combine(now.date(), datetime.min.time()).replace(hour=OFFICE_END_HOUR, minute=0)
    return start_dt <= now <= end_dt

def get_seconds_until_office_start():
    now = datetime.now()
    start_dt = datetime.combine(now.date(), datetime.min.time()).replace(hour=OFFICE_START_HOUR, minute=0)
    if now < start_dt:
        return max(60, int((start_dt - now).total_seconds()))
    next_start_dt = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).replace(hour=OFFICE_START_HOUR, minute=0)
    return max(60, int((next_start_dt - now).total_seconds()))

def set_marked_today():
    st = load_state()
    st["last_marked_date"], st["snooze_until"] = get_today(), 0
    return save_state(st)

def set_skipped_today():
    st = load_state()
    st["skipped_date"], st["snooze_until"] = get_today(), 0
    return save_state(st)

def set_snooze(hours=1.0):
    st = load_state()
    st["snooze_until"] = time.time() + (hours * 3600)
    return save_state(st)

def trim_memory():
    """Flushes unneeded process memory pages from RAM and collects garbage."""
    if sys.platform == "win32":
        try:
            import gc
            gc.collect()
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except Exception:
            pass

def get_seconds_until_midnight():
    """Calculates remaining seconds until midnight (next calendar day)."""
    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(60, int((midnight - now).total_seconds()))

def get_attendance_status():
    """Determines today's attendance state: weekend, outside_hours, marked, skipped, snoozed, or ready."""
    today = get_today()
    if is_weekend():
        return "weekend", "Weekend"
    if not is_office_hours():
        return "outside_hours", get_seconds_until_office_start()
    st = load_state()
    if st.get("last_marked_date") == today:
        return "marked", "Already marked today"
    if st.get("skipped_date") == today:
        return "skipped", "Skipped today"
    snooze_until = float(st.get("snooze_until", 0))
    if snooze_until > time.time():
        return "snoozed", snooze_until - time.time()
    return "ready", "Ready"

def should_show_prompt():
    status, msg = get_attendance_status()
    return status == "ready", msg

# --- Windows Idle Detection ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds():
    if sys.platform != "win32":
        return 0.0
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return max(0.0, (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0)
    except Exception:
        pass
    return 0.0

def is_user_active(threshold=300.0):
    return get_idle_seconds() < threshold

# --- GreytHR Automation Bot ---
def mark_greythr_attendance(url, username, password, work_location="Office", headless=False, timeout_ms=45000):
    if not url or not username or not password:
        return False, "Missing GreytHR URL, Username, or Password."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = url.rstrip("/")

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return False, "Playwright library is not installed in the Python environment."

    print(f"[GreytHR Bot] Connecting to {url} (Headless: {headless}, Location: {work_location})...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(viewport={"width": 1366, "height": 768})
            page = context.new_page()

            # 1. Login
            print("[GreytHR Bot] Navigating to login page...")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(1)

            u_field = page.locator('input[name="username"], input[id="username"], input[type="text"]').first
            p_field = page.locator('input[name="password"], input[id="password"], input[type="password"]').first
            if not u_field.is_visible() or not p_field.is_visible():
                browser.close()
                return False, "Login fields not found."

            u_field.fill(username)
            p_field.fill(password)

            login_btn = page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")').first
            login_btn.click() if login_btn.is_visible() else page.keyboard.press("Enter")

            print("[GreytHR Bot] Logged in. Waiting for dashboard to load...")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=12000)
            except Exception:
                pass
            time.sleep(5)

            # Check invalid credentials or if still on login page
            err = page.locator('.error, .alert-danger, [class*="error-msg"], [class*="login-error"], [class*="danger"], [role="alert"]')
            if err.count() > 0 and err.first.is_visible() and err.first.inner_text().strip():
                msg = err.first.inner_text().strip()
                browser.close()
                return False, f"Login failed: {msg}"

            if p_field.is_visible() or "/auth/login" in page.url.lower():
                msg = "Invalid User ID or Password. Please try again."
                try:
                    for line in page.locator("body").inner_text().splitlines():
                        if "invalid user id or password" in line.lower():
                            msg = line.strip()
                            break
                except Exception:
                    pass
                browser.close()
                return False, f"Login failed: {msg}"

            # 2. Check dashboard status (poll up to 25s)
            print("[GreytHR Bot] Checking dashboard status (polling up to 25s for attendance card)...")
            found_sign_in = False
            for i in range(25):
                # Already marked check
                sign_out = page.locator('button:has-text("Sign Out"), gt-button:has-text("Sign Out"), [data-automation-id="sign-out"]')
                if sign_out.count() > 0 and sign_out.first.is_visible():
                    print("[GreytHR Bot] 'Sign Out' button detected! Attendance already marked today.")
                    browser.close()
                    return True, "Attendance is already marked for today!"

                # Sign In button check
                sign_in = page.locator('button:has-text("Sign In"), gt-button:has-text("Sign In"), button.btn-primary:has-text("Sign In"), [data-automation-id="sign-in-btn"], button:has-text("Swipe In")')
                if sign_in.count() > 0 and sign_in.first.is_visible():
                    print(f"[GreytHR Bot] Located 'Sign In' on dashboard after {i+1}s. Clicking...")
                    sign_in.first.click()
                    found_sign_in = True
                    break
                time.sleep(1)

            if not found_sign_in:
                if page.locator('button:has-text("Sign Out"), gt-button:has-text("Sign Out")').count() > 0:
                    browser.close()
                    return True, "Attendance is already marked for today!"
                browser.close()
                return False, "Could not find 'Sign In' button on dashboard."

            time.sleep(2)

            # 3. Select location via Shadow DOM
            print(f"[GreytHR Bot] Waiting for modal and selecting '{work_location}' in gt-dropdown...")
            try:
                page.locator('gt-dropdown, [role="modal"], .highlight-modal').first.wait_for(state="visible", timeout=6000)
            except Exception:
                pass
            time.sleep(1)

            select_res = page.evaluate("""async (loc) => {
                const drop = document.querySelector('gt-dropdown');
                if (!drop) return { success: false };
                const root = drop.shadowRoot || drop;
                try { drop.value = loc; } catch(e) {}
                const btn = root.querySelector('button.dropdown-button, .dropdown-button, button');
                if (btn) { btn.click(); await new Promise(r => setTimeout(r, 250)); }
                for (let el of root.querySelectorAll('.item-label, .dropdown-item, .dropdown-body div')) {
                    const txt = el.textContent.trim();
                    if (txt.toLowerCase().includes(loc.toLowerCase())) {
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                        el.click();
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                        return { success: true, selectedText: txt };
                    }
                }
                return { success: false };
            }""", work_location)
            print(f"[GreytHR Bot] Shadow DOM selection result: {select_res}")
            time.sleep(1)

            # 4. Click Modal Sign In
            print("[GreytHR Bot] Submitting modal 'Sign In'...")
            modal_btn = page.locator('[role="modal"] gt-button:has-text("Sign In"), [role="modal"] button:has-text("Sign In"), .highlight-modal gt-button:has-text("Sign In"), .highlight-modal button:has-text("Sign In"), .modal-footer-container gt-button:has-text("Sign In"), .modal-footer-container button:has-text("Sign In")')
            if modal_btn.count() > 0 and modal_btn.last.is_visible():
                modal_btn.last.click(force=True)
            else:
                all_btns = page.locator('gt-button:has-text("Sign In"), button:has-text("Sign In")')
                if all_btns.count() > 1:
                    print(f"[GreytHR Bot] Clicking the pop up 'Sign In' button (index {all_btns.count() - 1})...")
                    all_btns.last.click(force=True)
                elif all_btns.count() == 1:
                    all_btns.first.click(force=True)
                else:
                    page.keyboard.press("Enter")

            time.sleep(3)
            browser.close()
            return True, f"Successfully processed sign-in at {work_location}!"
    except PlaywrightTimeoutError:
        return False, "Connection timeout."
    except Exception as e:
        return False, f"Automation error: {str(e)}"
    finally:
        trim_memory()

# --- UI Application ---
class AttendanceApp:
    def __init__(self):
        self.config = load_config()
        self.root = None
        self.is_popup_open = False
        self.tray_icon = None
        self.wake_event = threading.Event()

    def create_tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(img)
        dc.ellipse((4, 4, 60, 60), fill="#18181b", outline="#3f3f46", width=2)
        dc.line((20, 36, 28, 44), fill="#fafafa", width=5)
        dc.line((28, 44, 46, 22), fill="#fafafa", width=5)
        return img

    def run_tray(self):
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("Mark Attendance Now", lambda: self.prompt_now()),
                pystray.MenuItem("Settings", lambda: self.show_settings()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda: self.quit_app())
            )
            self.tray_icon = pystray.Icon("GreytHR Attendance", self.create_tray_image(), "GreytHR Attendance Manager", menu)
            self.tray_icon.run()
        except Exception as e:
            print(f"[Tray] Warning: {e}")

    def quit_app(self):
        if hasattr(self, "wake_event") and self.wake_event:
            self.wake_event.set()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.quit()
            self.root.destroy()
        sys.exit(0)

    def reset_today(self):
        st = load_state()
        st["last_marked_date"], st["skipped_date"], st["snooze_until"] = "", "", 0
        save_state(st)
        messagebox.showinfo("Status Reset", "Today's state has been reset.")

    def prompt_now(self):
        if self.root:
            self.root.after(0, self.show_popup)

    def show_popup(self):
        if self.is_popup_open:
            return
        self.is_popup_open = True

        win = tk.Toplevel(self.root)
        win.title("GreytHR Attendance Manager")
        win.geometry("450x360")
        win.resizable(False, False)
        win.configure(bg="#09090b")
        win.attributes("-topmost", True)

        # Center on screen
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - 225
        y = (win.winfo_screenheight() // 2) - 180
        win.geometry(f"450x360+{x}+{y}")

        # Header
        hdr = tk.Frame(win, bg="#18181b", height=50)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text="⏰ GreytHR Attendance", font=("Segoe UI", 11, "bold"), fg="#fafafa", bg="#18181b").pack(side="left", padx=16, pady=12)
        tk.Button(hdr, text="⚙ Settings", font=("Segoe UI", 9), fg="#fafafa", bg="#27272a", activebackground="#3f3f46", activeforeground="#fff", bd=1, relief="solid", padx=12, pady=3, cursor="hand2", command=lambda: self.show_settings(win)).pack(side="right", padx=16, pady=10)
        tk.Frame(win, bg="#27272a", height=1).pack(fill="x", side="top")

        # Body
        body = tk.Frame(win, bg="#09090b", padx=25, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Would you like to mark your attendance for today?", font=("Segoe UI", 11, "bold"), fg="#fafafa", bg="#09090b", wraplength=400, justify="center").pack(pady=(5, 10))
        status_var = tk.StringVar(value="Click 'Mark Attendance' to automatically log into GreytHR.")
        tk.Label(body, textvariable=status_var, font=("Segoe UI", 9), fg="#a1a1aa", bg="#09090b", wraplength=400, justify="center").pack(pady=(0, 15))

        load_var = tk.StringVar(value="")
        tk.Label(body, textvariable=load_var, font=("Segoe UI", 9, "italic"), fg="#fafafa", bg="#09090b").pack(pady=(0, 10))

        def close():
            self.is_popup_open = False
            win.destroy()
            if self.root:
                self.root.after(400, trim_memory)

        def do_mark():
            cfg = load_config()
            if not cfg.get("greythr_url") or not cfg.get("username") or not cfg.get("password"):
                messagebox.showwarning("Missing Configuration", "Please set Portal URL, Username and Password in Settings first!", parent=win)
                self.show_settings(win)
                return

            btn_m.config(state="disabled")
            btn_d.config(state="disabled")
            btn_s.config(state="disabled")
            load_var.set("Connecting to GreytHR and marking attendance...")
            win.update()

            def task():
                ok, msg = mark_greythr_attendance(cfg.get("greythr_url"), cfg.get("username"), cfg.get("password"), cfg.get("work_location", "Office"), cfg.get("headless", True))
                def fin():
                    if ok:
                        set_marked_today()
                        if hasattr(self, "wake_event") and self.wake_event:
                            self.wake_event.set()
                        messagebox.showinfo("Success", "Attendance marked successfully!", parent=win)
                        close()
                    else:
                        load_var.set("❌ Failed to mark attendance.")
                        status_var.set(f"Error: {msg}")
                        btn_m.config(state="normal")
                        btn_d.config(state="normal")
                        btn_s.config(state="normal")
                win.after(0, fin)
            threading.Thread(target=task, daemon=True).start()

        def do_skip():
            set_skipped_today()
            if hasattr(self, "wake_event") and self.wake_event:
                self.wake_event.set()
            messagebox.showinfo("Skipped", "Attendance prompts skipped for today.", parent=win)
            close()

        def do_snooze():
            set_snooze(1.0)
            if hasattr(self, "wake_event") and self.wake_event:
                self.wake_event.set()
            messagebox.showinfo("Snoozed", "Notification snoozed for 1 hour.", parent=win)
            close()

        win.protocol("WM_DELETE_WINDOW", do_snooze)

        btns = tk.Frame(body, bg="#09090b")
        btns.pack(fill="x", pady=5)

        btn_m = tk.Button(btns, text="✔ Mark Attendance", font=("Segoe UI", 10, "bold"), fg="#09090b", bg="#fafafa", activebackground="#e4e4e7", bd=0, pady=8, cursor="hand2", command=do_mark)
        btn_m.pack(fill="x", pady=3)

        btn_d = tk.Button(btns, text="🚫 Don't mark today", font=("Segoe UI", 9, "bold"), fg="#fafafa", bg="#dc2626", activebackground="#b91c1c", bd=0, pady=6, cursor="hand2", command=do_skip)
        btn_d.pack(fill="x", pady=3)

        btn_s = tk.Button(btns, text="⏳ Remind in 1 Hour", font=("Segoe UI", 9), fg="#fafafa", bg="#18181b", activebackground="#27272a", bd=1, relief="solid", pady=6, cursor="hand2", command=do_snooze)
        btn_s.pack(fill="x", pady=3)

        credit = tk.Label(body, text="github.com/Kishore341507", font=("Segoe UI", 7), fg="#71717a", bg="#09090b", cursor="hand2")
        credit.pack(side="bottom", pady=(10, 0))
        credit.bind("<Button-1>", lambda e: webbrowser.open_new_tab("https://github.com/Kishore341507"))

    def show_settings(self, parent=None):
        cfg = load_config()
        win = tk.Toplevel(parent or self.root)
        win.title("GreytHR Settings")
        win.geometry("480x570")
        win.resizable(False, False)
        win.configure(bg="#09090b")
        win.attributes("-topmost", True)
        win.grab_set()

        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() // 2) - 240)
        y = max(0, (win.winfo_screenheight() // 2) - 285)
        win.geometry(f"480x570+{x}+{y}")

        hdr = tk.Frame(win, bg="#18181b", height=60)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text="⚙ GreytHR Settings", font=("Segoe UI", 12, "bold"), fg="#fafafa", bg="#18181b").pack(anchor="w", padx=20, pady=(12, 2))
        tk.Label(hdr, text="Configure company portal URL and login credentials.", font=("Segoe UI", 8), fg="#a1a1aa", bg="#18181b").pack(anchor="w", padx=20, pady=(0, 12))
        tk.Frame(win, bg="#27272a", height=1).pack(fill="x", side="top")

        form = tk.Frame(win, bg="#09090b", padx=24, pady=16)
        form.pack(fill="both", expand=True)

        # 1. URL
        tk.Label(form, text="GreytHR Portal URL:", font=("Segoe UI", 9, "bold"), fg="#fafafa", bg="#09090b").pack(anchor="w", pady=(0, 2))
        e_url = tk.Entry(form, font=("Segoe UI", 10), bg="#09090b", fg="#fafafa", insertbackground="#fafafa", relief="solid", bd=1, highlightthickness=1, highlightbackground="#27272a")
        e_url.insert(0, cfg.get("greythr_url", "https://briskminds-software.greythr.com/"))
        e_url.pack(fill="x", ipady=4, pady=(0, 12))

        # 2. Username
        tk.Label(form, text="User ID / Employee ID:", font=("Segoe UI", 9, "bold"), fg="#fafafa", bg="#09090b").pack(anchor="w", pady=(0, 2))
        e_usr = tk.Entry(form, font=("Segoe UI", 10), bg="#09090b", fg="#fafafa", insertbackground="#fafafa", relief="solid", bd=1, highlightthickness=1, highlightbackground="#27272a")
        e_usr.insert(0, cfg.get("username", ""))
        e_usr.pack(fill="x", ipady=4, pady=(0, 12))

        # 3. Password
        tk.Label(form, text="Password:", font=("Segoe UI", 9, "bold"), fg="#fafafa", bg="#09090b").pack(anchor="w", pady=(0, 2))
        p_frame = tk.Frame(form, bg="#09090b", bd=1, relief="solid", highlightthickness=1, highlightbackground="#27272a")
        p_frame.pack(fill="x", pady=(0, 12))

        e_pwd = tk.Entry(p_frame, font=("Segoe UI", 10), show="*", bg="#09090b", fg="#fafafa", insertbackground="#fafafa", bd=0, relief="flat")
        e_pwd.insert(0, cfg.get("password", ""))
        e_pwd.pack(side="left", fill="x", expand=True, ipady=4, padx=5)

        vis = [False]
        def toggle_pwd():
            vis[0] = not vis[0]
            e_pwd.config(show="" if vis[0] else "*")
            btn_t.config(text="🙈" if vis[0] else "👁")

        btn_t = tk.Button(p_frame, text="👁", font=("Segoe UI", 9), fg="#a1a1aa", bg="#09090b", activebackground="#18181b", bd=0, padx=8, cursor="hand2", command=toggle_pwd)
        btn_t.pack(side="right")

        # 4. Work Location
        tk.Label(form, text="Default Work Location:", font=("Segoe UI", 9, "bold"), fg="#fafafa", bg="#09090b").pack(anchor="w", pady=(0, 2))
        style = ttk.Style(win)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('Dark.TCombobox', fieldbackground='#09090b', background='#18181b', foreground='#fafafa', darkcolor='#09090b', lightcolor='#09090b', bordercolor='#27272a', arrowcolor='#fafafa')
        win.option_add('*TCombobox*Listbox.background', '#09090b')
        win.option_add('*TCombobox*Listbox.foreground', '#fafafa')
        win.option_add('*TCombobox*Listbox.selectBackground', '#27272a')

        loc_var = tk.StringVar(value=cfg.get("work_location", "Office"))
        opt_loc = ttk.Combobox(form, textvariable=loc_var, values=["Office", "Work from Home", "Client Location", "On-Duty"], state="readonly", font=("Segoe UI", 9), style='Dark.TCombobox')
        opt_loc.pack(fill="x", ipady=3, pady=(0, 12))

        # 5. Headless
        head_var = tk.BooleanVar(value=cfg.get("headless", True))
        tk.Checkbutton(form, text="Headless", variable=head_var, font=("Segoe UI", 9), fg="#fafafa", bg="#09090b", selectcolor="#18181b", activebackground="#09090b", cursor="hand2").pack(anchor="w", pady=(0, 16))

        def on_close():
            win.destroy()
            if self.root:
                self.root.after(400, trim_memory)

        def save():
            u, usr, pwd = e_url.get().strip(), e_usr.get().strip(), e_pwd.get().strip()
            if not u or not usr or not pwd:
                messagebox.showwarning("Missing Info", "Please fill in all URL, Username, and Password fields.", parent=win)
                return
            if not u.startswith(("http://", "https://")):
                u = "https://" + u
            save_config({"greythr_url": u, "username": usr, "password": pwd, "work_location": loc_var.get(), "headless": head_var.get()})
            if hasattr(self, "wake_event") and self.wake_event:
                self.wake_event.set()
            messagebox.showinfo("Saved", "Settings saved successfully!", parent=win)
            on_close()

        win.protocol("WM_DELETE_WINDOW", on_close)

        tk.Button(form, text="💾 Save Configuration", font=("Segoe UI", 10, "bold"), fg="#09090b", bg="#fafafa", activebackground="#e4e4e7", bd=0, pady=9, cursor="hand2", command=save).pack(fill="x", pady=(10, 0))

        credit = tk.Label(form, text="github.com/Kishore341507", font=("Segoe UI", 7), fg="#71717a", bg="#09090b", cursor="hand2")
        credit.pack(side="bottom", pady=(10, 0))
        credit.bind("<Button-1>", lambda e: webbrowser.open_new_tab("https://github.com/Kishore341507"))

    def loop(self):
        # Allow initial setup to finish, then trim initial memory footprint
        self.wake_event.wait(timeout=3)
        trim_memory()

        while True:
            sleep_duration = 120  # Default check interval: 2 minutes
            try:
                status, detail = get_attendance_status()

                if status in ("marked", "skipped", "weekend"):
                    # Sleep 1 hour (3600 seconds) or until midnight, whichever is shorter
                    sleep_duration = min(3600, get_seconds_until_midnight())
                elif status == "outside_hours":
                    # Sleep until office hours start (or up to 30 mins before re-checking)
                    sleep_duration = max(60, min(int(detail), 1800))
                elif status == "snoozed":
                    # Sleep for the remaining snooze duration (up to 1 hour, at least 30s)
                    remaining_snooze = int(detail)
                    sleep_duration = max(30, min(remaining_snooze, 3600))
                elif status == "ready":
                    cfg = load_config()
                    if is_user_active(float(cfg.get("idle_threshold_seconds", 300))):
                        self.prompt_now()
                    sleep_duration = 120  # 2 minutes default check interval
            except Exception:
                sleep_duration = 120

            self.wake_event.wait(timeout=sleep_duration)
            self.wake_event.clear()

    def start(self):
        threading.Thread(target=self.run_tray, daemon=True).start()
        threading.Thread(target=self.loop, daemon=True).start()
        self.root = tk.Tk()
        self.root.withdraw()

        cfg = load_config()
        if not cfg.get("greythr_url") or not cfg.get("username") or not cfg.get("password"):
            self.root.after(1000, self.show_settings)

        self.root.mainloop()

# --- Entry Point ---
if __name__ == "__main__":
    if "--test" in sys.argv:
        cfg = load_config()
        print(f"Loaded Config: {cfg.get('greythr_url')} | User: {cfg.get('username')} | Location: {cfg.get('work_location')}")
        ok, msg = mark_greythr_attendance(
            url=cfg.get("greythr_url", ""),
            username=cfg.get("username", ""),
            password=cfg.get("password", ""),
            work_location=cfg.get("work_location", "Office"),
            headless=False
        )
        print(f"\nResult: {'SUCCESS' if ok else 'FAILED'}\nMessage: {msg}")
    else:
        print("Starting GreytHR Attendance Assistant...")
        AttendanceApp().start()
