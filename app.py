import json
import logging
import os
import platform
import re
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

APP_TITLE = "Ballot Finder & Printer"

# ---------- paths & state ----------

def app_base_dir() -> str:
    # Where config.json lives (next to exe when frozen, next to app.py in dev)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def user_state_dir() -> str:
    # Store per-user state/logs here (cross-platform)
    path = os.path.join(os.path.expanduser("~"), ".ballotlookup")
    os.makedirs(path, exist_ok=True)
    return path

STATE_PATH = os.path.join(user_state_dir(), "state.json")

def compute_log_path(cfg: dict) -> str:
    """
    Decide where to place the log file.
    If cfg has "log_in_app_dir": true, put it next to the app/config.
    Otherwise (default), use the per-user folder ~/.ballotlookup/.
    """
    try:
        if cfg.get("log_in_app_dir"):
            return os.path.join(app_base_dir(), "ballotfinder.log")
    except Exception:
        pass
    return os.path.join(user_state_dir(), "ballotfinder.log")

# ---------- logging ----------

def setup_logging(cfg: dict):
    global LOG_PATH
    LOG_PATH = compute_log_path(cfg)
    # Ensure log directory exists and the file is created
    log_dir = os.path.dirname(LOG_PATH)
    os.makedirs(log_dir, exist_ok=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8"):
            pass  # touch the file
    except Exception:
        pass
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        force=True
    )
    logging.info("=== App start ===")
    logging.info(f"Log file: {LOG_PATH}")

# ---------- config ----------

def load_config():
    here = app_base_dir()
    cfg_path = os.path.join(here, "config.json")
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"Missing config.json at: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------- state (remember last precinct) ----------

def read_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def write_state(d: dict):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception as e:
        logging.warning(f"Failed to write state: {e}")

# ---------- core helpers ----------

def norm(path: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(path)))

def validate_precinct_split(s: str) -> tuple[bool, str]:
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[._](\d{3})", s)
    if not m:
        return False, "Use format ####.### (e.g., 1774.234)"
    return True, f"{m.group(1)}.{m.group(2)}"

def build_candidates(prec_dot: str) -> list[str]:
    p4, p3 = prec_dot.split(".")
    return [f"{p4}.{p3}", f"{p4}_{p3}"]

def find_pdf(base_dir: str, lang_dirname: str, needle_parts: list[str], ballot_type: str, case_insensitive: bool = True) -> list[str]:
    hits = []
    lang_path = os.path.join(base_dir, lang_dirname)
    if not os.path.isdir(lang_path):
        return hits

    if case_insensitive:
        needle_parts_l = [n.lower() for n in needle_parts]
        ballot_l = ballot_type.lower()
        for root, _, files in os.walk(lang_path):
            for fn in files:
                if not fn.lower().endswith(".pdf"):
                    continue
                low = fn.lower()
                if any(n in low for n in needle_parts_l) and ballot_l in low:
                    hits.append(os.path.join(root, fn))
    else:
        for root, _, files in os.walk(lang_path):
            for fn in files:
                if not fn.endswith(".pdf"):
                    continue
                if any(n in fn for n in needle_parts) and ballot_type in fn:
                    hits.append(os.path.join(root, fn))
    return hits

def open_or_print_pdf(path: str, open_instead: bool = False) -> None:
    system = platform.system()
    if open_instead:
        logging.info(f"Opening: {path}")
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return

    # Print
    logging.info(f"Printing: {path}")
    if system == "Windows":
        try:
            os.startfile(path, "print")
        except OSError:
            messagebox.showerror("Print Error", "Windows could not find a registered PDF print handler.")
    elif system == "Darwin":
        subprocess.run(["lp", path], check=False)
    else:
        subprocess.run(["lp", path], check=False)

# ---------- GUI ----------

class App(tk.Tk):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.title(APP_TITLE)
        self.resizable(False, False)
        self.configure(padx=16, pady=16)

        self.var_split = tk.StringVar()
        self.var_ballot = tk.StringVar(value=list(self.cfg["ballot_types"].keys())[0])
        self.var_lang = tk.StringVar(value=list(self.cfg["languages"].keys())[0])

        # restore last precinct if available
        st = read_state()
        if "last_precinct" in st:
            self.var_split.set(st["last_precinct"])

        row = 0
        ttk.Label(self, text="Precinct Split (####.###):").grid(row=row, column=0, sticky="w")
        self.ent_split = ttk.Entry(self, textvariable=self.var_split, width=18)
        self.ent_split.grid(row=row, column=1, sticky="we", padx=(6,0))
        row += 1

        # ttk.Label(self, text="Ballot Type:").grid(row=row, column=0, sticky="w")
        # self.cmb_ballot = ttk.Combobox(self, textvariable=self.var_ballot, values=list(self.cfg["ballot_types"].keys()), state="readonly", width=16)
        # self.cmb_ballot.grid(row=row, column=1, sticky="we", padx=(6,0))
        # row += 1

        ttk.Label(self, text="Language:").grid(row=row, column=0, sticky="w")
        self.cmb_lang = ttk.Combobox(self, textvariable=self.var_lang, values=list(self.cfg["languages"].keys()), state="readonly", width=16)
        self.cmb_lang.grid(row=row, column=1, sticky="we", padx=(6,0))
        row += 1

        # action buttons
        action_frame = ttk.Frame(self)
        action_frame.grid(row=row, column=0, columnspan=2, pady=(10,0), sticky="we")
        # ttk.Button(action_frame, text="Find & Print", command=self.on_find_print).pack(side="left")
        ttk.Button(action_frame, text="Find & Open", command=lambda: self.on_find_print(open_instead=True)).pack(side="left", padx=6)
        ttk.Button(action_frame, text="Test Paths", command=self.on_test_paths).pack(side="left", padx=6)
        ttk.Button(action_frame, text="Open Log", command=self.on_open_log).pack(side="left", padx=6)
        ttk.Button(action_frame, text="Exit", command=self.on_exit).pack(side="left", padx=6)
        row += 1

        # single-line status box (read-only)
        self.var_status = tk.StringVar(value="Ready.")
        self.ent_status = ttk.Entry(self, textvariable=self.var_status, state="readonly", width=80)
        self.ent_status.grid(row=row, column=0, columnspan=2, pady=(10,0), sticky="we")
        # Hide the status line if log_in_app_dir is false
        if not self.cfg.get("log_in_app_dir", True):
            self.ent_status.grid_remove()
        row += 1

        # --- previously used multi-line log box ---
        # self.txt = tk.Text(self, width=80, height=12, state="disabled")
        # self.txt.grid(row=row, column=0, columnspan=2, pady=(10,0), sticky="we")
        # row += 1

        ttk.Label(self, text=f"Primary: {self.cfg['primary_dir']}").grid(row=row, column=0, columnspan=2, sticky="w", pady=(8,0)); row+=1
        ttk.Label(self, text=f"Backup : {self.cfg['backup_dir']}").grid(row=row, column=0, columnspan=2, sticky="w"); row+=1
        # ttk.Label(self, text=f"Log   : {LOG_PATH}").grid(row=row, column=0, columnspan=2, sticky="w")  # previous always-on version
        self.lbl_log = ttk.Label(self, text=f"Log   : {LOG_PATH}")
        if self.cfg.get("log_in_app_dir", True):
            self.lbl_log.grid(row=row, column=0, columnspan=2, sticky="w")

        self.columnconfigure(1, weight=1)

    def log(self, msg: str):
        logging.info(msg)
        # update single-line status
        if hasattr(self, "var_status"):
            self.var_status.set(msg)
        # --- previous log box handling ---
        # if hasattr(self, "txt"):
        #     self.txt.configure(state="normal")
        #     self.txt.insert("end", msg + "\n")
        #     self.txt.see("end")
        #     self.txt.configure(state="disabled")

    def on_find_print(self, open_instead: bool = False):
        ok, normalized = validate_precinct_split(self.var_split.get())
        if not ok:
            self.log(f"Error: {normalized}")
            messagebox.showerror("Invalid Input", normalized)
            return

        # remember last precinct
        st = read_state()
        st["last_precinct"] = normalized
        write_state(st)

        ballot = self.cfg["ballot_types"][self.var_ballot.get()]
        lang_dirname = self.cfg["languages"][self.var_lang.get()]
        needles = build_candidates(normalized)
        ci = bool(self.cfg.get("case_insensitive", True))

        primary = norm(self.cfg["primary_dir"])
        backup = norm(self.cfg["backup_dir"])

        self.log(f"Searching for {normalized} [{ballot}] in '{lang_dirname}' ...")

        hits = find_pdf(primary, lang_dirname, needles, ballot, case_insensitive=ci)
        where = "primary"
        if not hits:
            self.log("Not found in primary. Trying backup...")
            hits = find_pdf(backup, lang_dirname, needles, ballot, case_insensitive=ci)
            where = "backup"

        if not hits:
            self.log("No matching PDF found.")
            messagebox.showwarning("Not Found", f"No PDF found for {normalized} ({ballot}, {lang_dirname}).")
            return

        target = hits[0]
        if len(hits) > 1:
            self.log(f"Multiple matches ({len(hits)}) in {where} path.")
            choice = self.choose_from_list(hits)
            if not choice:
                self.log("User cancelled.")
                return
            target = choice

        self.log(f"Found: {target}")
        open_or_print_pdf(target, open_instead=open_instead)
        self.log("Opened." if open_instead else "Sent to printer / print command issued.")

    def choose_from_list(self, paths: list[str]) -> str | None:
        dlg = tk.Toplevel(self)
        dlg.title("Choose a file to print")
        dlg.geometry("900x320")
        lb = tk.Listbox(dlg, width=140, height=12)
        for p in paths:
            lb.insert("end", p)
        lb.pack(fill="both", expand=True, padx=10, pady=10)

        chosen = {"path": None}

        def on_ok():
            sel = lb.curselection()
            if sel:
                chosen["path"] = lb.get(sel[0])
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(pady=8)
        ttk.Button(btns, text="OK", command=on_ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="left", padx=6)

        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        return chosen["path"]

    def on_test_paths(self):
        pri = norm(self.cfg["primary_dir"])
        bak = norm(self.cfg["backup_dir"])
        langs = self.cfg["languages"].values()

        def summarize(base):
            if not os.path.isdir(base):
                return f"✗ {base} (missing)"
            # count PDFs under each language folder
            total = 0
            missing = []
            for lang in langs:
                p = os.path.join(base, lang)
                if not os.path.isdir(p):
                    missing.append(lang)
                    continue
                for root, _, files in os.walk(p):
                    total += sum(1 for f in files if f.lower().endswith(".pdf"))
            mis = f"; missing language dirs: {', '.join(missing)}" if missing else ""
            return f"✓ {base} (PDFs found: {total}){mis}"

        pri_msg = summarize(pri)
        bak_msg = summarize(bak)

        self.log("[Test Paths]")
        self.log("Primary -> " + pri_msg)
        self.log("Backup  -> " + bak_msg)
        messagebox.showinfo("Test Paths", pri_msg + "\n\n" + bak_msg)

    def on_open_log(self):
        try:
            self.log(f"Opening log: {LOG_PATH}")
            system = platform.system()
            log_dir = os.path.dirname(LOG_PATH)
            if system == "Windows":
                # Reveal the file in Explorer
                subprocess.run(["explorer", "/select,", LOG_PATH], check=False)
            elif system == "Darwin":
                # Reveal in Finder
                subprocess.run(["open", "-R", LOG_PATH], check=False)
            else:
                # Linux/other: open the directory
                subprocess.run(["xdg-open", log_dir], check=False)
        except Exception as e:
            logging.exception("Failed to open log")
            messagebox.showerror(APP_TITLE, f"Failed to open log: {e}")

    def on_exit(self):
        self.log("Exiting application")
        self.destroy()

def main():
    try:
        cfg = load_config()
        setup_logging(cfg)
        logging.info("Config loaded.")
        app = App(cfg)
        app.mainloop()
    except Exception as e:
        logging.exception("Fatal error")
        try:
            messagebox.showerror(APP_TITLE, str(e))
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()