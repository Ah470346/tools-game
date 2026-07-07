"""
ui/app.py

Minimal configuration UI for Priston Tale Auto Tool, modernized with CustomTkinter.
"""

import os
import sys
import json
import base64
import time
import threading
import subprocess
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

# Configure CustomTkinter appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Ensure project root is in sys.path if needed
if getattr(sys, 'frozen', False):
    # If compiled with PyInstaller, use the executable's directory
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    # If running from source, use the parent directory of ui/
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

from security.hwid import get_hardware_id
from security.license import LicenseChecker, LicenseError

PUBLIC_KEY_HEX = "24c6aead5a57ba82e1667e2fedc31245dfef9c7606c039315105a2bf69c9334d"

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "settings.json")
WHITELIST_PATH = os.path.join(PROJECT_ROOT, "config", "loot_whitelist.json")
SOAK_RUN_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "soak_run.py")

class AutoToolUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Priston Tale Auto Tool - PRO")
        self.geometry("450x650")
        self.minsize(420, 600)
        
        # We will use this to keep track of the background process
        self.bot_process = None

        self.settings = self.load_settings()
        self.whitelist_data = self.load_whitelist()

        self.create_widgets()
        self.populate_ui()

    def load_settings(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load settings.json:\n{e}")
        return {}

    def load_whitelist(self):
        if os.path.exists(WHITELIST_PATH):
            try:
                with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load loot_whitelist.json:\n{e}")
        return {"whitelist": [], "blacklist": []}

    def save_settings(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            
            with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
                json.dump(self.whitelist_data, f, indent=2)
                
            self.log_message("Settings saved successfully.\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings.json:\n{e}")

    def create_widgets(self):
        self.left_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.left_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.create_config_panel()

    def create_config_panel(self):
        self.tabview = ctk.CTkTabview(self.left_frame)
        self.tabview.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tabs
        self.tab_license = self.tabview.add("License")
        self.tab_combat = self.tabview.add("Combat")
        self.tab_potions = self.tabview.add("Potions")
        self.tab_loot = self.tabview.add("Loot")

        # --- LICENSE TAB ---
        ctk.CTkLabel(self.tab_license, text="Hardware ID (HWID):", font=("Roboto", 13, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(15, 5))
        self.var_hwid = tk.StringVar(value=get_hardware_id())
        entry_hwid = ctk.CTkEntry(self.tab_license, textvariable=self.var_hwid, state="readonly", width=360)
        entry_hwid.grid(row=1, column=0, sticky="w", padx=10, pady=0)

        ctk.CTkLabel(self.tab_license, text="License Key:", font=("Roboto", 13, "bold")).grid(row=2, column=0, sticky="w", padx=10, pady=(15, 5))
        self.var_license_key = tk.StringVar()
        entry_license = ctk.CTkEntry(self.tab_license, textvariable=self.var_license_key, width=360, show="*")
        entry_license.grid(row=3, column=0, sticky="w", padx=10, pady=0)

        # BIG REMAINING DAYS LABEL
        self.lbl_remaining_days = ctk.CTkLabel(self.tab_license, text="", font=("Roboto", 32, "bold"), text_color="#2ecc71")
        self.lbl_remaining_days.grid(row=4, column=0, pady=(40, 0), sticky="n")
        
        self.var_license_key.trace_add("write", lambda *args: self.update_license_display())

        # --- COMBAT TAB ---
        ctk.CTkLabel(self.tab_combat, text="Target Source:").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.var_target_source = tk.StringVar(value="yolo")
        cb_target = ctk.CTkComboBox(self.tab_combat, variable=self.var_target_source, values=["yolo", "tab"], state="readonly", width=120)
        cb_target.grid(row=0, column=1, sticky="w", padx=10, pady=10)

        # LMB
        self.var_lmb_enabled = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.tab_combat, text="Enable Left Click", variable=self.var_lmb_enabled).grid(row=1, column=0, sticky="w", padx=10, pady=10)
        ctk.CTkLabel(self.tab_combat, text="Interval (s):").grid(row=1, column=1, sticky="e", padx=5, pady=10)
        self.var_lmb_interval = tk.DoubleVar(value=0.5)
        ctk.CTkEntry(self.tab_combat, textvariable=self.var_lmb_interval, width=60).grid(row=1, column=2, sticky="w", padx=5, pady=10)

        # RMB
        self.var_rmb_enabled = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.tab_combat, text="Enable Right Click", variable=self.var_rmb_enabled).grid(row=2, column=0, sticky="w", padx=10, pady=10)
        ctk.CTkLabel(self.tab_combat, text="Interval (s):").grid(row=2, column=1, sticky="e", padx=5, pady=10)
        self.var_rmb_interval = tk.DoubleVar(value=1.0)
        ctk.CTkEntry(self.tab_combat, textvariable=self.var_rmb_interval, width=60).grid(row=2, column=2, sticky="w", padx=5, pady=10)

        # --- POTIONS TAB ---
        headers = ["Type", "Threshold (%)", "Key", "CD (s)"]
        for i, header in enumerate(headers):
            ctk.CTkLabel(self.tab_potions, text=header, font=("Roboto", 13, "bold")).grid(row=0, column=i, padx=5, pady=10)

        # HP
        ctk.CTkLabel(self.tab_potions, text="HP").grid(row=1, column=0, padx=5, pady=5)
        self.var_hp_pct = tk.IntVar(value=75)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_hp_pct, width=60).grid(row=1, column=1, padx=5, pady=5)
        self.var_hp_key = tk.StringVar(value="1")
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_hp_key, width=60).grid(row=1, column=2, padx=5, pady=5)
        self.var_hp_cd = tk.DoubleVar(value=1.0)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_hp_cd, width=60).grid(row=1, column=3, padx=5, pady=5)

        # MP
        ctk.CTkLabel(self.tab_potions, text="MP").grid(row=2, column=0, padx=5, pady=5)
        self.var_mp_pct = tk.IntVar(value=50)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_mp_pct, width=60).grid(row=2, column=1, padx=5, pady=5)
        self.var_mp_key = tk.StringVar(value="4")
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_mp_key, width=60).grid(row=2, column=2, padx=5, pady=5)
        self.var_mp_cd = tk.DoubleVar(value=2.0)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_mp_cd, width=60).grid(row=2, column=3, padx=5, pady=5)

        # STM
        ctk.CTkLabel(self.tab_potions, text="STM").grid(row=3, column=0, padx=5, pady=5)
        self.var_stm_pct = tk.IntVar(value=40)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_stm_pct, width=60).grid(row=3, column=1, padx=5, pady=5)
        self.var_stm_key = tk.StringVar(value="3")
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_stm_key, width=60).grid(row=3, column=2, padx=5, pady=5)
        self.var_stm_cd = tk.DoubleVar(value=2.0)
        ctk.CTkEntry(self.tab_potions, textvariable=self.var_stm_cd, width=60).grid(row=3, column=3, padx=5, pady=5)

        # --- LOOT TAB ---
        self.var_loot_enabled = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.tab_loot, text="Enable Auto Loot", variable=self.var_loot_enabled).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)

        ctk.CTkLabel(self.tab_loot, text="Scan Key:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.var_loot_key = tk.StringVar(value="a")
        ctk.CTkEntry(self.tab_loot, textvariable=self.var_loot_key, width=60).grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # Whitelist UI
        ctk.CTkLabel(self.tab_loot, text="Whitelist Items:").grid(row=2, column=0, sticky="nw", padx=10, pady=5)
        
        whitelist_frame = ctk.CTkFrame(self.tab_loot, fg_color="transparent")
        whitelist_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=10, pady=5)
        
        # Use classic tk Listbox but stylized for dark mode
        self.list_whitelist = tk.Listbox(whitelist_frame, height=6, width=25, bg="#2b2b2b", fg="white", 
                                         selectbackground="#1f538d", highlightthickness=0, borderwidth=0, font=("Roboto", 12))
        self.list_whitelist.pack(side=tk.LEFT, fill=tk.Y)
        
        btn_frame = ctk.CTkFrame(self.tab_loot, fg_color="transparent")
        btn_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=10, pady=5)
        
        self.var_new_item = tk.StringVar()
        ctk.CTkEntry(btn_frame, textvariable=self.var_new_item, width=120).pack(side=tk.LEFT, padx=(0, 5))
        ctk.CTkButton(btn_frame, text="Add", command=self.add_whitelist_item, width=50).pack(side=tk.LEFT, padx=(0, 5))
        ctk.CTkButton(btn_frame, text="Remove", command=self.remove_whitelist_item, width=60, fg_color="#C0392B", hover_color="#922B21").pack(side=tk.LEFT)

        # --- CONTROLS ---
        controls_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        controls_frame.pack(fill=tk.X, pady=15, padx=5)

        self.btn_save = ctk.CTkButton(controls_frame, text="Save Settings", command=self.on_save, fg_color="#5D6D7E", hover_color="#34495E")
        self.btn_save.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.btn_start = ctk.CTkButton(controls_frame, text="▶ START BOT", command=self.on_start, fg_color="#27AE60", hover_color="#1E8449", font=("Roboto", 14, "bold"))
        self.btn_start.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.btn_stop = ctk.CTkButton(controls_frame, text="⏹ STOP BOT", command=self.on_stop, state=tk.DISABLED, fg_color="#C0392B", hover_color="#922B21", font=("Roboto", 14, "bold"))
        self.btn_stop.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

    def add_whitelist_item(self):
        item = self.var_new_item.get().strip()
        if item:
            self.list_whitelist.insert(tk.END, item)
            self.var_new_item.set("")
            
    def remove_whitelist_item(self):
        selection = self.list_whitelist.curselection()
        if selection:
            self.list_whitelist.delete(selection[0])

    def populate_ui(self):
        """Fill UI fields from settings."""
        if not self.settings:
            return

        self.var_license_key.set(self.settings.get("license_key", ""))

        combat = self.settings.get("combat", {})
        self.var_target_source.set(combat.get("target_source", "yolo"))
        
        lc = combat.get("left_click", {})
        self.var_lmb_enabled.set(lc.get("enabled", True))
        self.var_lmb_interval.set(lc.get("interval_sec", 0.5))

        rc = combat.get("right_click", {})
        self.var_rmb_enabled.set(rc.get("enabled", False))
        self.var_rmb_interval.set(rc.get("interval_sec", 1.0))

        thresholds = self.settings.get("thresholds", {})
        hp_list = thresholds.get("hp", [])
        if hp_list:
            self.var_hp_pct.set(hp_list[0].get("percent", 75))
            self.var_hp_key.set(hp_list[0].get("key", "1"))
            self.var_hp_cd.set(hp_list[0].get("cooldown_sec", 1.0))

        mp_list = thresholds.get("mp", [])
        if mp_list:
            self.var_mp_pct.set(mp_list[0].get("percent", 50))
            self.var_mp_key.set(mp_list[0].get("key", "4"))
            self.var_mp_cd.set(mp_list[0].get("cooldown_sec", 2.0))

        stm_list = thresholds.get("stm", [])
        if stm_list:
            self.var_stm_pct.set(stm_list[0].get("percent", 40))
            self.var_stm_key.set(stm_list[0].get("key", "3"))
            self.var_stm_cd.set(stm_list[0].get("cooldown_sec", 2.0))

        loot = self.settings.get("loot", {})
        self.var_loot_enabled.set(loot.get("enabled", True))
        self.var_loot_key.set(loot.get("scan_key", "a"))
        
        # Populate whitelist
        self.list_whitelist.delete(0, tk.END)
        for item in self.whitelist_data.get("whitelist", []):
            self.list_whitelist.insert(tk.END, item)

    def update_settings_dict(self):
        """Update settings dict from UI fields."""
        self.settings["license_key"] = self.var_license_key.get().strip()
        
        if "combat" not in self.settings:
            self.settings["combat"] = {}
        self.settings["combat"]["target_source"] = self.var_target_source.get()
        self.settings["combat"]["left_click"] = {
            "enabled": self.var_lmb_enabled.get(),
            "interval_sec": self.var_lmb_interval.get()
        }
        self.settings["combat"]["right_click"] = {
            "enabled": self.var_rmb_enabled.get(),
            "interval_sec": self.var_rmb_interval.get()
        }

        if "thresholds" not in self.settings:
            self.settings["thresholds"] = {}
        
        # Keep existing list structure, just update the first item
        self.settings["thresholds"]["hp"] = [{
            "percent": self.var_hp_pct.get(),
            "key": self.var_hp_key.get(),
            "cooldown_sec": self.var_hp_cd.get()
        }]
        self.settings["thresholds"]["mp"] = [{
            "percent": self.var_mp_pct.get(),
            "key": self.var_mp_key.get(),
            "cooldown_sec": self.var_mp_cd.get()
        }]
        self.settings["thresholds"]["stm"] = [{
            "percent": self.var_stm_pct.get(),
            "key": self.var_stm_key.get(),
            "cooldown_sec": self.var_stm_cd.get()
        }]

        if "loot" not in self.settings:
            self.settings["loot"] = {}
        self.settings["loot"]["enabled"] = self.var_loot_enabled.get()
        self.settings["loot"]["scan_key"] = self.var_loot_key.get()
        
        # Update whitelist_data
        self.whitelist_data["whitelist"] = list(self.list_whitelist.get(0, tk.END))

    def update_license_display(self):
        key_str = self.var_license_key.get().strip()
        if not key_str:
            self.lbl_remaining_days.configure(text="No License", text_color="#e74c3c")
            return
            
        try:
            # Parse it directly to get the expiry for the UI display,
            # actual strict verification is done on START BOT
            decoded_json = base64.b64decode(key_str).decode('utf-8')
            license_data = json.loads(decoded_json)
            expiry = license_data.get("payload", {}).get("expiry", 0)
            
            if expiry:
                time_left = expiry - time.time()
                if time_left <= 0:
                    self.lbl_remaining_days.configure(text="EXPIRED", text_color="#e74c3c")
                else:
                    days = int(time_left / 86400)
                    self.lbl_remaining_days.configure(text=f"{days} Days Remaining", text_color="#2ecc71")
            else:
                self.lbl_remaining_days.configure(text="Invalid Format", text_color="#e74c3c")
        except Exception:
            self.lbl_remaining_days.configure(text="Invalid Key", text_color="#e74c3c")

    def on_save(self):
        self.update_settings_dict()
        self.save_settings()

    def on_start(self):
        if self.bot_process is not None and self.bot_process.poll() is None:
            messagebox.showwarning("Warning", "Bot is already running!")
            return

        # --- LICENSE CHECK ---
        license_key_str = self.var_license_key.get().strip()
        hwid = self.var_hwid.get()
        
        if not license_key_str:
            messagebox.showerror("License Required", "Please enter a License Key to start the bot.")
            return
            
        checker = LicenseChecker(PUBLIC_KEY_HEX)
        try:
            checker.verify_key(license_key_str, hwid)
        except LicenseError as e:
            messagebox.showerror("License Verification Failed", str(e))
            self.log_message(f"[ERROR] License check failed: {e}\n")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error during license validation:\n{e}")
            return

        self.on_save()
        
        self.log_message("Starting bot process...\n")
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)

        # Start subprocess
        cmd = [sys.executable, "--bot", "--active", "--duration_hours", "999"]
        
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        self.bot_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1, # Line buffered
            creationflags=creationflags
        )

        # Start background thread to read logs
        self.log_thread = threading.Thread(target=self._read_logs, daemon=True)
        self.log_thread.start()

    def on_stop(self):
        if self.bot_process is not None:
            self.log_message("Attempting to stop bot process...\n")
            self.bot_process.terminate()
            self.btn_start.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)

    def _read_logs(self):
        """Runs in a background thread to read stdout from bot."""
        if not self.bot_process:
            return

        try:
            for line in self.bot_process.stdout:
                self.log_message(line)
        except Exception as e:
            self.log_message(f"[UI ERROR] {e}\n")

        self.bot_process.wait()
        
        # Safely update UI from thread
        self.after(0, self._on_process_ended)

    def _on_process_ended(self):
        self.log_message("\n--- Bot process terminated ---\n")
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        self.bot_process = None

    def log_message(self, message: str):
        """Thread-safe way to update the console. Now just prints to stdout."""
        print(message, end="", flush=True)

if __name__ == "__main__":
    app = AutoToolUI()
    app.mainloop()
