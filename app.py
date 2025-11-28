import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import threading


from uart import init_uart, uart_send_set_params, uart_send_recv_only, stream_with_echo_and_plot


from storage import (
    ensure_files,
    load_users,
    save_users,
    load_user_params,
    save_user_params,
    load_param_config
)


MODE_MAP = {
        "AOO": 0x0,
        "VOO": 0x1,
        "AAI": 0x2,
        "VVI": 0x3,
        "AOOR": 0x4,
        "VOOR": 0x5,
        "AAIR": 0x6,
        "VVIR": 0x7
}

# Activity Threshold → 0–6
ACTIVITY_THRESHOLD_MAP = {
    "V-Low": 0,
    "Low": 1,
    "Med-Low": 2,
    "Med": 3,
    "Med-High": 4,
    "High": 5,
    "V-High": 6
}

# Hysteresis → 0–1
HYSTERESIS_MAP = {
    "Off": 0,
    "Track LRL": 1
}


BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(BASE_DIR, "data")
USERS_JSON   = os.path.join(DATA_DIR, "users.json")
PARAMS_JSON  = os.path.join(DATA_DIR, "params.json") 
USER_PARAMS_JSON = os.path.join(DATA_DIR, "user_params.json")

#order of parameters


    
class App(tk.Tk):
    def __init__(self):
        super().__init__()

        ensure_files()

        self.title("DCM - Deliverable 1")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.serial = init_uart("COM10", 115200)

        self.current_user   = None
        self.device_id      = None    
        self.prev_device_id = None      

        # variables for status bar
        self.status_var = tk.StringVar(value="Comms: idle")
        self.mode_var   = tk.StringVar(value="Mode: N/A")

        # top status bar for variables
        top = ttk.Frame(self, padding=6)
        top.pack(side="top", fill="x")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=8)
        ttk.Label(top, textvariable=self.mode_var).pack(side="left", padx=16)

        # container for screens
        self.container = ttk.Frame(self, padding=12)
        self.container.pack(side="top", fill="both", expand=True)

        # Different views
        self.login_view   = LoginView(self.container, self)
        self.monitor_view = MonitorView(self.container, self)

        self.current_view = None
        self.show_view(self.login_view)

    def show_view(self, view):
        if self.current_view is not None:
            self.current_view.pack_forget()
        view.pack(fill="both", expand=True)
        self.current_view = view

    def set_mode(self, mode):
        self.mode_var.set(f"Mode: {mode}")

   
    def set_device(self, new_id: str):
        old = self.device_id
        self.prev_device_id = old
        self.device_id = new_id

        # status bar update only if logged in
        user_txt = f"  |  user: {self.current_user}" if self.current_user else ""
        dev_txt  = f"  |  device: {self.device_id}" if self.device_id else ""
        self.status_var.set(f"Comms: idle{user_txt}{dev_txt}")

        # show clear notice on the Monitor view
        if old is None and new_id:
            self.monitor_view.show_notice(f"Connected to pacemaker: {new_id}", bg="#e6ffea", fg="#0a5c1a")
        elif old and new_id and old != new_id:
            self.monitor_view.show_notice(f"Different pacemaker detected: {new_id} (previous: {old})", bg="#ffe6e6", fg="#700000")
        elif old == new_id:
            self.monitor_view.show_notice(f"Same pacemaker reconnected: {new_id}", bg="#e8f0fe", fg="#123a89")

class LoginView(ttk.Frame):
    
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app

        card = ttk.Frame(self, padding=24, relief="groove")
        card.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(card, text="Welcome to DCM", font=("TkDefaultFont", 16, "bold")).grid(row=0, column=0, columnspan=3, pady=(0, 12))
        # Username/password entries
        ttk.Label(card, text="Username").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.user_entry = ttk.Entry(card, width=28)
        self.user_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=6)

        ttk.Label(card, text="Password").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.pass_entry = ttk.Entry(card, width=28, show="*")
        self.pass_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        # Show password if user desires
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Show", variable=self.show_var,
                        command=lambda: self.pass_entry.config(show="" if self.show_var.get() else "*")
                        ).grid(row=2, column=2, padx=6)

        # Login/Register buttons
        actions = ttk.Frame(card)
        actions.grid(row=3, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(actions, text="Login", command=self.on_login).pack(side="left", padx=6)
        ttk.Button(actions, text="Register", command=self.on_register).pack(side="left", padx=6)

        #Allows for enter button to be used to submit login.
        card.grid_columnconfigure(1, weight=1)
        self.user_entry.bind("<Return>", lambda e: self.on_login())
        self.pass_entry.bind("<Return>", lambda e: self.on_login())

    def on_register(self):
        data = load_users()
        users = data["users"]
        if len(users) >= 10:
            messagebox.showwarning("Limit", "Maximum of 10 users stored locally")
            return

        name = self.user_entry.get().strip()
        pw   = self.pass_entry.get()
        #Require both fields or else warning
        if not name or not pw:
            messagebox.showwarning("Missing info", "Enter both username and password")
            return
        #No registeration of duplicate users.
        if any(u["name"] == name for u in users):
            messagebox.showwarning("Exists", "That username already exists")
            return
        #Saves new user but requires user to login to continue.
        users.append({"name": name, "pw": pw})
        save_users({"users": users})
        messagebox.showinfo("Registered", f"User '{name}' registered")
        self.pass_entry.delete(0, "end")

    def on_login(self):
        data  = load_users()
        users = data["users"]
        name  = self.user_entry.get().strip()
        pw    = self.pass_entry.get()

        match = next((u for u in users if u["name"] == name and u["pw"] == pw), None)
        if not match:
            messagebox.showerror("Login failed", "Invalid username or password")
            return
        
        self.app.current_user = name
        #Sets status bar to user ID
        self.app.status_var.set(f"Comms: idle  |  user: {name}")
        user_params = load_user_params()
        if name in user_params:
            for k, v in user_params[name].items():
                if k in self.app.monitor_view.vars:
                    self.app.monitor_view.vars[k].set(str(v))

        #After successful login swap to monitor view
        self.app.show_view(self.app.monitor_view)


class MonitorView(ttk.Frame):
 
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app

        self.default_mode = "VOO"

        header = ttk.Frame(self)
        header.pack(side="top", fill="x")
        ttk.Label(header, text="Monitor", font=("TkDefaultFont", 16, "bold")).pack(side="left", padx=12, pady=8)
        right = ttk.Frame(header)
        right.pack(side="right")

        #Dropdown menu for mode selection
        #Loads paramteter data structures/defaults from params.json
        ttk.Label(right, text="Mode:").pack(side="left", padx=(0, 6), pady=8)
        self.PARAM_SCHEMA, self.defaults, self.modes = load_param_config()

        #Order of parameters for UART
        self.PARAM_ORDER = list(self.PARAM_SCHEMA.keys())

        self.mode_cb = ttk.Combobox(
            right,
            values=self.modes,
            state="readonly",
            width=8
        )
        self.mode_cb.set("Select mode")
        self.mode_cb.pack(side="left", padx=6, pady=8)
        self.mode_cb.bind("<<ComboboxSelected>>", lambda e: self.on_mode_change())

        # Device ID entry and Set button
        ttk.Label(right, text="Device ID:").pack(side="left", padx=(12, 6), pady=8)
        self.device_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.device_var, width=16).pack(side="left", pady=8)
        ttk.Button(right, text="Set", command=self.on_set_device).pack(side="left", padx=6, pady=8)

        #Transfer back to login view 
        ttk.Button(right, text="Logout", command= self.on_logout).pack(side="left", padx=6, pady=8)

        #Sets up notifcation banner for device connections
        self.banner_frame = tk.Frame(self, bg="#ffefc6")
        self.banner_label = tk.Label(self.banner_frame, text="", bg="#ffefc6", fg="#333", font=("TkDefaultFont", 10, "bold"))
        self.banner_label.pack(side="left", padx=12, pady=6)
        ttk.Button(self.banner_frame, text="Dismiss", command=self.hide_notice).pack(side="right", padx=12, pady=6)
        self.banner_visible = False

        
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        #Creates varaible for each parameter and sets its default based on params.json
        self.vars = {k: tk.StringVar(value=str(self.defaults[k])) for k in self.PARAM_SCHEMA}
        self.entries = {}

        params = ttk.LabelFrame(body, text="Programmable Parameters", padding=12)
        params.pack(side="left", fill="y", padx=(0, 8))

        self.rows = {}
        row_index = 0


        for field_key, field_meta in self.PARAM_SCHEMA.items():
            unit = field_meta.get("unit", "")  # default to empty string if not present
            label_text = f"{field_meta['label']}" + (f" ({unit})" if unit else "") + ":"
            label_widget = ttk.Label(params, text=label_text)
            label_widget.grid(row=row_index, column=0, sticky="e", padx=6, pady=4)

            var = self.vars[field_key]

            # Create slider ONLY if parameter has ranges
            input_widget = None
            slider_widget = None

            if "allowed" in field_meta:
                # Create combobox for parameters with a fixed list of allowed values
                input_widget = ttk.Combobox(
                    params,
                    values=field_meta["allowed"],
                    textvariable=var,
                    state="readonly",
                    width=12
                )
                input_widget.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)
                


            elif "ranges" in field_meta:

                input_widget = ttk.Entry(params, textvariable=var, width=10)
                input_widget.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)

                allowed_vals = []
                for r in field_meta["ranges"]:
                    v = r["min"]
                    while v <= r["max"]:
                        allowed_vals.append(v)
                        v = round(v + r["inc"], 5)  # prevent float drift

                # Sort & remove duplicates
                allowed_vals = sorted(set(allowed_vals))

                # Store these for later use
                field_meta["allowed_vals"] = allowed_vals



                slider_widget = tk.Scale(
                    params,
                    label="",
                    showvalue=0,
                    from_=0,
                    to=len(allowed_vals) - 1,
                    orient="horizontal",
                    length=160,
                    resolution=1,
                    command=lambda idx, k=field_key: self._slider_changed(k, idx)
                )
                slider_widget.grid(row=row_index, column=2, padx=6, pady=4)

                # sync entry → slider
                var.trace_add(
                    "write",
                    lambda *_,
                    k=field_key,
                    sl=slider_widget: self._entry_changed(k, sl)
                )

            

            self.rows[field_key] = (label_widget, input_widget, slider_widget)
            row_index += 1
        


        buttons_row_frame = ttk.Frame(params)
        buttons_row_frame.grid(row=row_index + 1, column=0, columnspan=2, pady=(12, 0))

        ttk.Button(buttons_row_frame, text="Save", command=self.on_save).pack(side="left", padx=4)

        self.send_btn = ttk.Button(buttons_row_frame, text="Send", command=self.on_send)
        self.send_btn.pack(side="left", padx=4)

        self.receive_btn = ttk.Button(buttons_row_frame, text="Receive", command=self.on_receive)
        self.receive_btn.pack(side="left", padx=4)

        ttk.Button(buttons_row_frame, text="Reset Defaults", command=self.on_reset).pack(side="left", padx=4)

        self.egram_enabled = tk.BooleanVar(value=False)

        # Styles for ON/OFF colors
        style = ttk.Style()
        style.configure("On.TButton",  foreground="black", background="#28a745")
        style.map("On.TButton", background=[("active", "#218838")])
        style.configure("Off.TButton", foreground="black", background="#dd1a1a")
        style.map("Off.TButton", background=[("active", "#dd1a1a")])

        self.egram_btn = ttk.Button(
            buttons_row_frame,
            text="Egram: OFF",
            style="Off.TButton",
            command=lambda: (
                self.egram_enabled.set(not self.egram_enabled.get()),
                toggle_egram()
            )
        )
        self.egram_btn.pack(side="left", padx=4)

        def toggle_egram():
            state = self.egram_enabled.get()

            # Change button appearance
            if state:
                self.egram_btn.config(text="Egram: ON", style="On.TButton")
            else:
                self.egram_btn.config(text="Egram: OFF", style="Off.TButton")

            # Enable/Disable Send + Receive
            if state:
                self.send_btn.config(state="disabled")
                self.receive_btn.config(state="disabled")
            else:
                self.send_btn.config(state="normal")
                self.receive_btn.config(state="normal")
                


        #Display for the graphs (Deliverable_2 implementation)
        right_panel = ttk.Frame(body, padding=16, relief="groove")
        right_panel.pack(side="left", fill="both", expand=True)
        ttk.Label(right_panel, text="Placeholder").pack(expand=True)

        self.mode_cb.set(self.default_mode)  # select default mode in dropdown
        self.on_mode_change()                # update visible parameters

    def on_mode_change(self):
        mode = self.mode_cb.get()
        self.app.set_mode(mode)

        for key, meta in self.PARAM_SCHEMA.items():
            widgets = self.rows[key]  # label, entry, maybe slider
            allowed_modes = meta.get("modes", [])

            if mode in allowed_modes:
                # show parameter widgets
                for w in widgets:
                    if w is not None:
                        w.grid()
            else:
                # hide widgets not used by this mode
                for w in widgets:
                    if w is not None:
                        w.grid_remove()

            saved = load_user_params().get(self.app.current_user, {}).get(mode)

            if saved:
                for k, v in saved.items():
                    if k in self.vars:
                        self.vars[k].set(str(v))
            else:
                # load defaults for this mode
                for k, v in self.defaults.items():
                    meta = self.PARAM_SCHEMA[k]
                    if mode in meta.get("modes", []):
                        self.vars[k].set(str(v))

    
    def on_set_device(self):
        new_id = self.device_var.get().strip() #Grabs ID from entry box
        if not new_id:
            messagebox.showwarning("Missing Device ID", "Enter a device ID first") #Error Case for empty device ID
            return
        self.app.set_device(new_id) #Calls function to set the ID accordingly

    #Helper Functions for visibility of notification banner
    def show_notice(self, text, bg="#ffefc6", fg="#333"):
        self.banner_label.config(text=text, bg=bg, fg=fg)
        self.banner_frame.config(bg=bg)
        if not self.banner_visible:
            self.banner_frame.pack(side="top", fill="x", padx=0, pady=(0, 6))
            self.banner_visible = True

    def hide_notice(self):
        if self.banner_visible:
            self.banner_frame.pack_forget()
            self.banner_visible = False

    def _parse_and_validate(self):
        clean, errors = {}, []

        def value_in_ranges(value, ranges):
            for r in ranges:
                if r["min"] <= value <= r["max"]:
                    return True
            return False
        
        def snap(value, inc):
            snapped = round(value / inc) * inc

            # compute decimal places needed from increment
            if isinstance(inc, float):
                decimals = len(str(inc).split(".")[1])
                return round(snapped, decimals)

            return int(snapped)
        
        def find_range(value, ranges):
            for r in ranges:
                if r["min"] <= value <= r["max"]:
                    return r
            return None
    

        for key, meta in self.PARAM_SCHEMA.items():
            raw = self.vars[key].get().strip()

            if "ranges" in meta:
                ty  = meta["type"]
                try:
                    #Error checking by attemping to cast to correct type
                    val = ty(raw)
                    #Incorrect type entered
                except ValueError:
                    errors.append(f"{meta['label']}: not a valid {ty.__name__}")
                    continue
                #Variable limit checking

                if not value_in_ranges(val, meta["ranges"]):
                    # Build readable range string
                    range_str = " or ".join(
                        f"[{r['min']}, {r['max']}]" for r in meta["ranges"]
                    )
                    errors.append(
                        f"{meta['label']}: {val} {meta['unit']} out of valid ranges {range_str}"
                    )
                    continue

            clean[key] = val

            if "allowed" in meta:
                if raw not in meta["allowed"]:
                    errors.append(f"{meta['label']}: '{raw}' not a valid option")
                else:
                    clean[key] = raw

        if errors:
            return clean, errors
            
        for key, meta in self.PARAM_SCHEMA.items():
            if key not in clean:
                continue

            val = clean[key]

            # Only snap if the parameter has ranges and increments
            if "ranges" in meta:
                r = find_range(val, meta["ranges"])
                if r is not None:
                    snapped = snap(val, r["inc"])
                    # clamp after snap
                    snapped = max(r["min"], min(snapped, r["max"]))
                    clean[key] = snapped
                    self.vars[key].set(str(snapped))
            
            

        #Edge case of LRL and URL
        if "LRL_ppm" in clean and "URL_ppm" in clean and clean["LRL_ppm"] >= clean["URL_ppm"]:
            errors.append("Lower Rate Limit must be < Upper Rate Limit")


        return clean, errors
    

    def _slider_changed(self, key, idx):
        """When slider moves, update entry."""
        meta = self.PARAM_SCHEMA[key]
        allowed = meta.get("allowed_vals")
        if not allowed:
            return

        idx = int(float(idx))
        idx = max(0, min(idx, len(allowed) - 1))
        self.vars[key].set(str(allowed[idx]))



    def _entry_changed(self, key, slider):
        raw = self.vars[key].get()

        # 1. Ignore incomplete or mid-typing inputs
        if raw == "" or raw.endswith(".") or raw.startswith("."):
            return

        # If the string isn't a clean float, ignore
        try:
            v = float(raw)
        except ValueError:
            return

        meta = self.PARAM_SCHEMA[key]
        allowed = meta.get("allowed_vals")
        if not allowed:
            return

        # 2. Prevent snapping: only update slider if the float matches EXACT allowed value
        #    "3" → float(3.0) → allowed contains 3.0 → but we should NOT snap on "3"
        #    Therefore: ensure the *string* matches the exact allowed representation
        allowed_strs = [str(a) for a in allowed]

        if raw not in allowed_strs:
            return

        # 3. Now safe to update slider
        idx = allowed_strs.index(raw)
        slider.set(idx)


            



    def on_save(self):
        clean, errors = self._parse_and_validate()
        if errors:
            messagebox.showerror("Invalid parameter(s)", "\n".join(errors))
            return
        
        param_config = load_user_params()
        username = self.app.current_user
        mode = self.mode_cb.get()

        if username not in param_config:
            param_config[username] = {}

        filtered = {}
        for key, meta in self.PARAM_SCHEMA.items():
            if mode in meta.get("modes", []):     # only parameters used by this mode
                filtered[key] = clean[key]


        param_config[username][mode] = filtered
        save_user_params(param_config)

        #Clean parameters will be used in Deliverable 2
        self.app.status_var.set(f"Comms: idle  |  parameters saved for {username} ({mode})")

    def on_reset(self):
        #Resets all parameters to defaults from params.json
        for k, v in self.defaults.items():
            self.vars[k].set(str(v))
        self.app.status_var.set("Comms: idle  |  defaults restored")
    def on_logout(self):
        self.app.status_var.set(f"Comms: idle")
        self.app.show_view(self.app.login_view)


    def on_send(self):
        if self.app.serial is None:
            self.output_area.appendPlainText("Not connected to device.")
            return

        try:
            uart_send_set_params()
            self.output_area.appendPlainText("Sent SET PARAMS frame.")
        except Exception as e:
            self.output_area.appendPlainText(f"Send failed: {e}")


    def on_receive(self):
        if self.app.serial is None:
            self.output_area.appendPlainText("Not connected to device.")
            return

        try:
            uart_send_recv_only()
            self.output_area.appendPlainText("Sent RECV ONLY frame.")
        except Exception as e:
            self.output_area.appendPlainText(f"Receive command failed: {e}")




        

# ------------------------------- Run app -----------------------------------
if __name__ == "__main__":
    App().mainloop()
