import os
import json
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(BASE_DIR, "data")
USERS_JSON   = os.path.join(DATA_DIR, "users.json")
PARAMS_JSON  = os.path.join(DATA_DIR, "params.json") 
USER_PARAMS_JSON = os.path.join(DATA_DIR, "user_params.json")

def ensure_files():
    """Create data/ and tiny JSON files if missing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_JSON):
        with open(USERS_JSON, "w") as f:
            json.dump({"users": []}, f, indent=2)
    


def load_users():
    with open(USERS_JSON, "r") as f:
        return json.load(f)

def save_users(data):
    with open(USERS_JSON, "w") as f:
        json.dump(data, f, indent=2)

def load_user_params():
    """Return dict of user parameters from JSON file, or {} if none."""
    if os.path.exists(USER_PARAMS_JSON):
        with open(USER_PARAMS_JSON, "r") as f:
            return json.load(f)
    return {}

def save_user_params(data):
    """Write updated user parameters dict to JSON file."""
    with open(USER_PARAMS_JSON, "w") as f:
        json.dump(data, f, indent=2)



def load_param_config():
    with open(PARAMS_JSON, "r") as f:
        cfg = json.load(f)

    schema_raw = cfg.get("schema", {})
    defaults   = cfg.get("defaults", {})

    
    type_map = {"int": int, "float": float}

    schema = {}
    for key, meta in schema_raw.items():
        m = dict(meta)                      
        m["type"] = type_map.get(m.get("type", "int"), int)  
        schema[key] = m

    return schema, defaults


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        ensure_files()

        self.title("DCM - Deliverable 1")
        self.geometry("900x600")
        self.minsize(700, 450)

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

        
        header = ttk.Frame(self)
        header.pack(side="top", fill="x")
        ttk.Label(header, text="Monitor", font=("TkDefaultFont", 16, "bold")).pack(side="left", padx=12, pady=8)
        right = ttk.Frame(header)
        right.pack(side="right")

        #Dropdown menu for mode selection
        ttk.Label(right, text="Mode:").pack(side="left", padx=(0, 6), pady=8)
        self.mode_cb = ttk.Combobox(right, values=["AOO", "VOO", "AAI", "VVI"], state="readonly", width=8)
        self.mode_cb.set("Select mode")
        self.mode_cb.pack(side="left", padx=6, pady=8)
        self.mode_cb.bind("<<ComboboxSelected>>", lambda e: self.app.set_mode(self.mode_cb.get()))

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

        #Loads paramteter data structures/defaults from params.json
        self.PARAM_SCHEMA, self.defaults = load_param_config()
        #Creates varaible for each parameter and sets its default based on params.json
        self.vars = {k: tk.StringVar(value=str(self.defaults[k])) for k in self.PARAM_SCHEMA}
        self.entries = {}

        params = ttk.LabelFrame(body, text="Programmable Parameters", padding=12)
        params.pack(side="left", fill="y", padx=(0, 8))

        row_index = 0
        for field_key, field_meta in self.PARAM_SCHEMA.items():
            #Grabs labels and units from params.json
            label_text = f"{field_meta['label']} ({field_meta['unit']}):"
            label_widget = ttk.Label(params, text=label_text)
            label_widget.grid(row=row_index, column=0, sticky="e", padx=6, pady=4)
            #Input box for values, updates stringVar variable on entry
            entry_widget = ttk.Entry(params, textvariable=self.vars[field_key], width=12)
            entry_widget.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)

            self.entries[field_key] = entry_widget
            row_index += 1

        buttons_row_frame = ttk.Frame(params)
        buttons_row_frame.grid(row=row_index + 1, column=0, columnspan=2, pady=(12, 0))

        ttk.Button(buttons_row_frame, text="Save", command=self.on_save).pack(side="left", padx=4)
        ttk.Button(buttons_row_frame, text="Reset Defaults", command=self.on_reset).pack(side="left", padx=4)

        #Display for the graphs (Deliverable_2 implementation)
        right_panel = ttk.Frame(body, padding=16, relief="groove")
        right_panel.pack(side="left", fill="both", expand=True)
        ttk.Label(right_panel, text="Placeholder").pack(expand=True)

    
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
        for key, meta in self.PARAM_SCHEMA.items():
            raw = self.vars[key].get().strip()
            ty  = meta["type"]
            try:
                #Error checking by attemping to cast to correct type
                val = ty(raw)
                #Incorrect type entered
            except ValueError:
                errors.append(f"{meta['label']}: not a valid {ty.__name__}")
                continue
            #Variable limit checking
            if val < meta["min"] or val > meta["max"]:
                errors.append(f"{meta['label']}: {val} {meta['unit']} out of range [{meta['min']}, {meta['max']}]")
            clean[key] = val
        #Edge case of LRL and URL
        if "LRL_ppm" in clean and "URL_ppm" in clean and clean["LRL_ppm"] >= clean["URL_ppm"]:
            errors.append("Lower Rate Limit must be < Upper Rate Limit")

        return clean, errors

    def on_save(self):
        clean, errors = self._parse_and_validate()
        if errors:
            messagebox.showerror("Invalid parameter(s)", "\n".join(errors))
            return
        
        data = load_user_params()
        username = self.app.current_user
        data[username] = clean
        save_user_params(data)

        #Clean parameters will be used in Deliverable 2
        self.app.status_var.set(f"Comms: idle  |  parameters saved for {username}")

    def on_reset(self):
        #Resets all parameters to defaults from params.json
        for k, v in self.defaults.items():
            self.vars[k].set(str(v))
        self.app.status_var.set("Comms: idle  |  defaults restored")
    def on_logout(self):
        self.app.status_var.set(f"Comms: idle")
        self.app.show_view(self.app.login_view)

        

# ------------------------------- Run app -----------------------------------
if __name__ == "__main__":
    App().mainloop()
