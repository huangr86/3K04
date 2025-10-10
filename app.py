import os
import json
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_JSON = os.path.join(DATA_DIR, "users.json")

def _ensure_users_file():
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

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        _ensure_users_file()
        self.title("DCM - Deliverable 1")
        self.geometry("900x600")
        self.minsize(700, 450)
        self.current_user = None
        self.status_var = tk.StringVar(value="Comms: idle")
        self.mode_var = tk.StringVar(value="Mode: N/A")
        top = ttk.Frame(self, padding=6)
        top.pack(side="top", fill="x")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=8)
        ttk.Label(top, textvariable=self.mode_var).pack(side="left", padx=16)
        self.container = ttk.Frame(self, padding=12)
        self.container.pack(side="top", fill="both", expand=True)
        self.views = {}
        self.current_view = None
        self.views["login"] = LoginView(self.container, self)
        self.views["modes"] = ModesView(self.container, self)
        self.views["monitor"] = MonitorView(self.container, self)
        self.show_view("login")
        self.bind_all("<Control-m>", lambda e: self.show_view("modes"))
        self.bind_all("<Control-n>", lambda e: self.show_view("monitor"))

    def show_view(self, name: str):
        if self.current_view:
            self.current_view.pack_forget()
        view = self.views[name]
        view.pack(fill="both", expand=True)
        self.current_view = view

    def set_mode(self, mode: str):
        self.mode_var.set(f"Mode: {mode}")

class LoginView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        card = ttk.Frame(self, padding=24, relief="groove")
        card.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(card, text="Welcome to DCM", font=("TkDefaultFont", 16, "bold")).grid(row=0, column=0, columnspan=3, pady=(0, 12))
        ttk.Label(card, text="Username").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.user_entry = ttk.Entry(card, width=28)
        self.user_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        ttk.Label(card, text="Password").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.pass_entry = ttk.Entry(card, width=28, show="*")
        self.pass_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Show", variable=self.show_var, command=lambda: self.pass_entry.config(show="" if self.show_var.get() else "*")).grid(row=2, column=2, padx=6)
        btns = ttk.Frame(card)
        btns.grid(row=3, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text="Login", command=self.on_login).pack(side="left", padx=6)
        ttk.Button(btns, text="Register", command=self.on_register).pack(side="left", padx=6)
        card.grid_columnconfigure(1, weight=1)
        self.user_entry.bind("<Return>", lambda e: self.on_login())
        self.pass_entry.bind("<Return>", lambda e: self.on_login())

    def on_register(self):
        data = load_users()
        users = data["users"]
        if len(users) >= 10:
            messagebox.showwarning("Limit reached", "Maximum of 10 users stored locally")
            return
        name = self.user_entry.get().strip()
        pw = self.pass_entry.get()
        if not name or not pw:
            messagebox.showwarning("Missing info", "Enter both username and password")
            return
        if any(u["name"] == name for u in users):
            messagebox.showwarning("Exists", "That username already exists")
            return
        users.append({"name": name, "pw": hash_pw(pw)})
        save_users({"users": users})
        messagebox.showinfo("Registered", f"User '{name}' registered")
        self.pass_entry.delete(0, "end")

    def on_login(self):
        data = load_users()
        users = data["users"]
        name = self.user_entry.get().strip()
        pw = self.pass_entry.get()
        hpw = hash_pw(pw)
        match = next((u for u in users if u["name"] == name and u["pw"] == hpw), None)
        if not match:
            messagebox.showerror("Login failed", "Invalid username or password")
            return
        self.app.current_user = name
        self.app.status_var.set(f"Comms: idle  |  user: {name}")
        self.app.show_view("modes")

class ModesView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        top = ttk.Frame(self)
        top.pack(side="top", fill="x")
        ttk.Label(top, text="Modes", font=("TkDefaultFont", 16, "bold")).pack(side="left", padx=12, pady=8)
        ttk.Button(top, text="Monitor", command=lambda: app.show_view("monitor")).pack(side="right", padx=12, pady=8)
        ttk.Button(top, text="Logout", command=lambda: app.show_view("login")).pack(side="right", padx=4, pady=8)
        grid = ttk.Frame(self, padding=12)
        grid.pack(fill="both", expand=True)
        cards = [
            ("AOO", "Asynchronous atrial pacing"),
            ("VOO", "Asynchronous ventricular pacing"),
            ("AAI", "Atrial sensing, pace if needed"),
            ("VVI", "Ventricular sensing, pace if needed"),
        ]
        for i, (name, desc) in enumerate(cards):
            card = ttk.Frame(grid, padding=16, relief="groove")
            r, c = divmod(i, 2)
            card.grid(row=r, column=c, padx=12, pady=12, sticky="nsew")
            ttk.Label(card, text=name, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
            ttk.Label(card, text=desc).pack(anchor="w", pady=(2, 8))
            ttk.Button(card, text=f"Select {name}", command=lambda m=name: (self.app.set_mode(m), self.app.show_view("monitor"))).pack(anchor="e")
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1)
        for r in range(2):
            grid.grid_rowconfigure(r, weight=1)

class MonitorView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        top = ttk.Frame(self)
        top.pack(side="top", fill="x")
        ttk.Label(top, text="Monitor", font=("TkDefaultFont", 16, "bold")).pack(side="left", padx=12, pady=8)
        right = ttk.Frame(top)
        right.pack(side="right")
        ttk.Button(right, text="Modes", command=lambda: app.show_view("modes")).pack(side="left", padx=6, pady=8)
        ttk.Button(right, text="Logout", command=lambda: app.show_view("login")).pack(side="left", padx=6, pady=8)
        center = ttk.Frame(self, padding=16, relief="groove")
        center.pack(fill="both", expand=True, padx=12, pady=8)
        ttk.Label(center, text="Egram view placeholder\n(we will draw here later)", anchor="center").pack(expand=True)

if __name__ == "__main__":
    App().mainloop()
