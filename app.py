import os
import json
import tkinter as tk
from tkinter import ttk, messagebox

from uart import init_uart, send_programming_packet, send_mode_byte

from storage import (
    ensure_files,
    load_users,
    save_users,
    load_user_params,
    save_user_params,
    load_param_config
)

# Mode encoding so that it matches the Simulink / Stateflow model.
# These are the integer mode codes that become Rx(3) in the packet.
MODE_MAP = {
    "AOO": 0x0,
    "VOO": 0x1,
    "AAI": 0x2,
    "VVI": 0x3,
    "AOOR": 0x4,
    "VOOR": 0x5,
    "AAIR": 0x6,
    "VVIR": 0x7,
}

# Activity Threshold → 0–6
ACTIVITY_THRESHOLD_MAP = {
    "V-Low": 0,
    "Low": 1,
    "Med-Low": 2,
    "Med": 3,
    "Med-High": 4,
    "High": 5,
    "V-High": 6,
}

# Hysteresis encoded as a small integer.
# Note: these are *DCM-side* encodings; Simulink currently only uses VVI/VVIR.
HYSTERESIS_MAP = {
    "Off": 0,
    "-10 bpm": 1,
    "-20 bpm": 2,
    "-30 bpm": 3,
}


# ---------------------------------------------------------------------------
# Main app window
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        ensure_files()

        self.title("Pacemaker DCM")
        self.geometry("1100x650")

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
        """Update the currently selected device ID."""
        self.device_id = new_id or ""
        if self.device_id:
            self.status_var.set(f"Comms: idle  |  Connected to device {self.device_id}")
        else:
            self.status_var.set("Comms: idle  |  No device selected")


# ---------------------------------------------------------------------------
# Login view
# ---------------------------------------------------------------------------


class LoginView(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app

        card = ttk.Frame(self, padding=24, relief="groove")
        card.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(
            card,
            text="Welcome to DCM",
            font=("TkDefaultFont", 16, "bold")
        ).grid(row=0, column=0, columnspan=3, pady=(0, 12))

        # Username/password entries
        ttk.Label(card, text="Username").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.user_entry = ttk.Entry(card, width=28)
        self.user_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=6)

        ttk.Label(card, text="Password").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.pass_entry = ttk.Entry(card, width=28, show="*")
        self.pass_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        # Show password if user desires
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            card,
            text="Show",
            variable=self.show_var,
            command=lambda: self.pass_entry.config(
                show="" if self.show_var.get() else "*"
            ),
        ).grid(row=2, column=2, padx=6)

        # Login/Register buttons
        actions = ttk.Frame(card)
        actions.grid(row=3, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(actions, text="Login", command=self.on_login).pack(side="left", padx=6)
        ttk.Button(actions, text="Register", command=self.on_register).pack(side="left", padx=6)

        card.columnconfigure(1, weight=1)
        self.user_entry.focus_set()

        # Load existing users
        self.users = load_users()

    def on_login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not username or not password:
            messagebox.showwarning("Missing fields", "Enter both username and password.")
            return

        for user in self.users["users"]:
            if user["name"] == username and user["pw"] == password:
                self.app.status_var.set(f"Comms: idle  |  Logged in as {username}")
                self.app.show_view(self.app.monitor_view)
                self.app.monitor_view.set_user(username)
                return

        messagebox.showerror("Login failed", "Invalid username or password.")

    def on_register(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not username or not password:
            messagebox.showwarning("Missing fields", "Enter both username and password.")
            return

        if any(u["name"] == username for u in self.users["users"]):
            messagebox.showerror("Register failed", "User already exists.")
            return

        if len(self.users["users"]) >= 10:
            messagebox.showerror("Register failed", "Maximum of 10 users reached.")
            return

        self.users["users"].append({"name": username, "pw": password})
        save_users(self.users)
        messagebox.showinfo("Register", "User registered. You can now log in.")


# ---------------------------------------------------------------------------
# Monitor view (parameters + UART)
# ---------------------------------------------------------------------------


class MonitorView(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.current_user = None

        self.PARAM_SCHEMA, self.defaults, self.modes = load_param_config()

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        # Left side: parameters
        left = ttk.Frame(body, padding=12, relief="groove")
        left.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(left)
        header.pack(side="top", fill="x")

        ttk.Label(
            header,
            text="Programmable Parameters",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(side="left")

        right = ttk.Frame(left)
        right.pack(side="top", fill="x", pady=(4, 8))

        # Order of parameters for display / storage
        self.PARAM_ORDER = list(self.PARAM_SCHEMA.keys())

        self.mode_cb = ttk.Combobox(
            right,
            values=self.modes,
            state="readonly",
            width=8,
        )
        self.mode_cb.set("Select mode")
        self.mode_cb.pack(side="left", padx=6, pady=8)
        self.mode_cb.bind("<<ComboboxSelected>>", lambda e: self.on_mode_change())

        # Device ID entry and Set button
        ttk.Label(right, text="Device ID:").pack(side="left", padx=(12, 6), pady=8)
        self.device_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.device_var, width=16).pack(side="left", pady=8)
        ttk.Button(right, text="Set", command=self.on_set_device).pack(side="left", padx=6, pady=8)

        # Transfer back to login view
        ttk.Button(right, text="Logout", command=self.on_logout).pack(side="left", padx=6, pady=8)

        # Notification banner for device connections
        self.banner_frame = tk.Frame(self, bg="#ffefc6")
        self.banner_label = tk.Label(
            self.banner_frame,
            text="",
            bg="#ffefc6",
            fg="#333",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.banner_label.pack(side="left", padx=12, pady=6)
        ttk.Button(
            self.banner_frame, text="Dismiss", command=self.hide_notice
        ).pack(side="right", padx=12, pady=6)
        self.banner_visible = False

        # Parameters grid
        params = ttk.Frame(left)
        params.pack(side="top", fill="both", expand=True, pady=(4, 0))

        self.vars = {}
        self.rows = {}

        row_index = 0

        for field_key, meta in self.PARAM_SCHEMA.items():
            label = meta["label"]
            unit = meta.get("unit", "")

            label_widget = ttk.Label(params, text=f"{label} ({unit})" if unit else label)
            label_widget.grid(row=row_index, column=0, sticky="w", padx=4, pady=3)

            var = tk.StringVar()
            self.vars[field_key] = var

            # Input widget
            if "choices" in meta:
                input_widget = ttk.Combobox(
                    params,
                    textvariable=var,
                    values=meta["choices"],
                    state="readonly",
                    width=12,
                )
            else:
                input_widget = ttk.Entry(params, textvariable=var, width=12)

            input_widget.grid(row=row_index, column=1, sticky="w", padx=4, pady=3)

            # Slider for ranged numeric params
            slider_widget = None
            if "ranges" in meta and meta["type"] in (int, float):
                slider_widget = tk.Scale(
                    params,
                    from_=meta["ranges"][0]["min"],
                    to=meta["ranges"][-1]["max"],
                    orient="horizontal",
                    resolution=meta["ranges"][0]["inc"],
                    length=200,
                )
                slider_widget.grid(
                    row=row_index,
                    column=2,
                    sticky="we",
                    padx=4,
                    pady=3,
                )

                # Sync slider → entry
                def slider_changed(event, k=field_key, sv=var):
                    sv.set(str(event.widget.get()))

                slider_widget.bind("<ButtonRelease-1>", slider_changed)

                # Sync entry → slider
                var.trace_add(
                    "write",
                    lambda *_,
                    k=field_key,
                    sl=slider_widget: self._entry_changed(k, sl),
                )

            self.rows[field_key] = (label_widget, input_widget, slider_widget)
            row_index += 1

        buttons_row_frame = ttk.Frame(params)
        buttons_row_frame.grid(row=row_index + 1, column=0, columnspan=2, pady=(12, 0))

        ttk.Button(buttons_row_frame, text="Save", command=self.on_save).pack(side="left", padx=4)
        ttk.Button(buttons_row_frame, text="Send", command=self.on_send).pack(side="left", padx=4)
        ttk.Button(buttons_row_frame, text="Receive", command=self.on_receive).pack(side="left", padx=4)
        ttk.Button(buttons_row_frame, text="Reset Defaults", command=self.on_reset).pack(side="left", padx=4)

        # Right panel placeholder for Deliverable 2 egram graphs
        right_panel = ttk.Frame(body, padding=16, relief="groove")
        right_panel.pack(side="left", fill="both", expand=True)
        ttk.Label(right_panel, text="Placeholder").pack(expand=True)

        self.on_mode_change()

    # --------------- helper methods for MonitorView -----------------

    def set_user(self, username: str):
        self.current_user = username
        self.app.set_mode("N/A")
        self.load_user_params()

    def on_set_device(self):
        new_id = self.device_var.get().strip()
        self.app.set_device(new_id)
        if new_id:
            self.show_notice(f"Connected to pacemaker {new_id}")

    def show_notice(self, text: str):
        self.banner_label.config(text=text)
        if not self.banner_visible:
            self.banner_frame.pack(side="top", fill="x", pady=(0, 4))
            self.banner_visible = True

    def hide_notice(self):
        if self.banner_visible:
            self.banner_frame.pack_forget()
            self.banner_visible = False

    def _entry_changed(self, key, slider_widget):
        try:
            val = float(self.vars[key].get())
        except ValueError:
            return
        slider_widget.set(val)

    def on_mode_change(self):
        mode = self.mode_cb.get()
        self.app.set_mode(mode or "N/A")

        # show/hide fields depending on mode usage
        for key, meta in self.PARAM_SCHEMA.items():
            use_in_mode = mode in meta.get("modes", [])
            label_widget, input_widget, slider_widget = self.rows[key]

            if use_in_mode:
                label_widget.grid()
                input_widget.grid()
                if slider_widget is not None:
                    slider_widget.grid()
            else:
                label_widget.grid_remove()
                input_widget.grid_remove()
                if slider_widget is not None:
                    slider_widget.grid_remove()

        self.load_user_params()

    def load_user_params(self):
        # Load defaults for all fields
        for k, v in self.defaults.items():
            self.vars[k].set(str(v))

        # Overwrite with user-specific settings if they exist
        username = self.current_user
        if not username:
            return

        param_config = load_user_params()
        mode = self.mode_cb.get()

        mode_cfg = param_config.get(username, {}).get(mode, {})
        for key, value in mode_cfg.items():
            if key in self.vars:
                self.vars[key].set(str(value))

    def _parse_and_validate(self):
        clean = {}
        errors = []

        def value_in_ranges(value, ranges):
            for r in ranges:
                if r["min"] <= value <= r["max"]:
                    return True
            return False

        def find_range(value, ranges):
            for r in ranges:
                if r["min"] <= value <= r["max"]:
                    return r
            return None

        for key, meta in self.PARAM_SCHEMA.items():
            raw = self.vars[key].get().strip()

            if "ranges" in meta:
                ty = meta["type"]
                try:
                    # type casting for validation
                    val = ty(raw)
                except ValueError:
                    errors.append(f"{meta['label']}: not a valid {ty.__name__}")
                    continue

                if not value_in_ranges(val, meta["ranges"]):
                    # Build readable range string
                    range_str = " or ".join(
                        f"[{r['min']}, {r['max']}]" for r in meta["ranges"]
                    )
                    errors.append(
                        f"{meta['label']}: {val} {meta['unit']} out of valid ranges {range_str}"
                    )
                    continue

                # snap to step increment
                r = find_range(val, meta["ranges"])
                if r is not None and r.get("inc"):
                    inc = r["inc"]
                    snapped = r["min"] + round((val - r["min"]) / inc) * inc
                    if meta["type"] is int:
                        snapped = int(snapped)
                    val = snapped

                clean[key] = val
            else:
                # free-form fields (e.g. enums)
                clean[key] = raw

        # cross-constraints: LRL < URL
        if "LRL_ppm" in clean and "URL_ppm" in clean:
            if isinstance(clean["LRL_ppm"], int) and isinstance(clean["URL_ppm"], int):
                if not (clean["LRL_ppm"] < clean["URL_ppm"]):
                    errors.append("Lower Rate Limit must be less than Upper Rate Limit.")

        return clean, errors

    def on_save(self):
        username = self.current_user
        if not username:
            messagebox.showwarning("No user", "Log in before saving parameters.")
            return

        clean, errors = self._parse_and_validate()
        if errors:
            messagebox.showerror("Invalid parameter(s)", "\n".join(errors))
            return

        mode = self.mode_cb.get()
        param_config = load_user_params()
        if username not in param_config:
            param_config[username] = {}

        filtered = {}
        for key, meta in self.PARAM_SCHEMA.items():
            if mode in meta.get("modes", []):  # only parameters used by this mode
                filtered[key] = clean[key]

        param_config[username][mode] = filtered
        save_user_params(param_config)

        self.app.status_var.set(
            f"Comms: idle  |  parameters saved for {username} ({mode})"
        )

    def on_reset(self):
        # Reset all parameters to defaults from params.json
        for k, v in self.defaults.items():
            self.vars[k].set(str(v))
        self.app.status_var.set("Comms: idle  |  defaults restored")

    def on_logout(self):
        self.app.status_var.set("Comms: idle")
        self.app.show_view(self.app.login_view)

    def on_send(self):
        # 1. Validate parameters from the GUI against the JSON schema
        clean, errors = self._parse_and_validate()
        if errors:
            messagebox.showerror("Invalid parameter(s)", "\n".join(errors))
            return

        mode_name = self.mode_cb.get()
        if not mode_name:
            messagebox.showwarning("Mode", "Select a pacing mode first.")
            return

        # 2. Map mode name -> integer index (Rx(3))
        mode_select = MODE_MAP.get(mode_name, 0)

        # Helper for pulling values out of the validated dict
        def get_or_default(key, default):
            return clean.get(key, default)

        # ---------------- Map GUI fields to the 10 packet variables ----------------

        # (1) LRL_interval [ms] from LRL_ppm, using SRS range 343–2000 ms
        lrl_ppm = get_or_default("LRL_ppm", 60)
        try:
            lrl_ppm = int(lrl_ppm)
            if lrl_ppm < 30 or lrl_ppm > 175:
                raise ValueError
        except ValueError:
            messagebox.showerror("LRL error", "LRL must be an integer between 30 and 175 ppm.")
            return
        LRL_interval_ms = int(round(60000.0 / lrl_ppm))  # 60 000 ms / min

        # (2) / (3) Atrial/Ventricular pulse widths in 0.1 ms units, SRS 0.1–1.9 ms
        a_pw_ms = float(get_or_default("Atrial_PW_ms", 0.4))
        v_pw_ms = float(get_or_default("Ventricular_PW_ms", 0.4))
        if not (0.1 <= a_pw_ms <= 1.9 and 0.1 <= v_pw_ms <= 1.9):
            messagebox.showerror(
                "Pulse width error",
                "Pulse widths must be between 0.1 ms and 1.9 ms.",
            )
            return
        a_pace_width_code = int(round(a_pw_ms * 10.0))  # 0.1 ms steps
        v_pace_width_code = int(round(v_pw_ms * 10.0))

        # (4) Ventricular sense amplitude in 0.1 mV units (0.25–10.0 mV)
        v_sense_mv = float(get_or_default("Ventricular Sensitivity", 4.0))
        if not (0.25 <= v_sense_mv <= 10.0):
            messagebox.showerror(
                "Ventricular sensitivity error",
                "Ventricular sensitivity must be between 0.25 mV and 10.0 mV.",
            )
            return
        v_sense_amp_code = int(round(v_sense_mv * 10.0))

        # (5) ARP and (6) VRP in ms (150–500 ms)
        ARP_ms = int(round(float(get_or_default("ARP_ms", 250))))
        VRP_ms = int(round(float(get_or_default("VRP_ms", 320))))
        if not (150 <= ARP_ms <= 500 and 150 <= VRP_ms <= 500):
            messagebox.showerror(
                "Refractory period error",
                "ARP and VRP must be between 150 ms and 500 ms.",
            )
            return

        # (7) Atrial sensitivity in 0.1 mV units (0.25–10.0 mV)
        a_sense_mv = float(get_or_default("Atrial Sensitivity", 4.0))
        if not (0.25 <= a_sense_mv <= 10.0):
            messagebox.showerror(
                "Atrial sensitivity error",
                "Atrial sensitivity must be between 0.25 mV and 10.0 mV.",
            )
            return
        a_sense_amp_code = int(round(a_sense_mv * 10.0))

        # (8) / (9) Ventricular & atrial pace amplitudes in 0.1 V units (0.5–7.0 V)
        v_amp_v = float(get_or_default("Ventricular_Amp_V", 3.5))
        a_amp_v = float(get_or_default("Atrial_Amp_V", 3.5))
        if not (0.5 <= v_amp_v <= 7.0 and 0.5 <= a_amp_v <= 7.0):
            messagebox.showerror(
                "Amplitude error",
                "Pace amplitudes must be between 0.5 V and 7.0 V.",
            )
            return
        v_pace_amp_code = int(round(v_amp_v * 10.0))
        a_pace_amp_code = int(round(a_amp_v * 10.0))

        # 3. Ensure a UART device has been chosen
        if not self.app.device_id:
            messagebox.showwarning("No Device", "Set a Device ID before sending.")
            return

        # 4. Open UART and send the programming packet
        try:
            ser = init_uart()
            send_programming_packet(
                ser,
                mode_select,
                LRL_interval_ms,
                a_pace_width_code,
                v_pace_width_code,
                v_sense_amp_code,
                ARP_ms,
                VRP_ms,
                a_sense_amp_code,
                v_pace_amp_code,
                a_pace_amp_code,
            )
            ser.close()
            self.app.status_var.set(
                f"Comms: sent programming packet to {self.app.device_id} "
                f"(mode={mode_name}, LRL_interval={LRL_interval_ms} ms)"
            )
        except Exception as e:
            messagebox.showerror("UART Error", f"Failed to send parameters:\n{e}")

    def on_receive(self):
        if not self.app.device_id:
            messagebox.showwarning("No Device", "Set a Device ID before receiving.")
            return

        try:
            ser = init_uart()
            from uart import receive_one_param_byte  # small test helper
            byte = receive_one_param_byte(ser)
            ser.close()

            if byte is not None:
                self.app.status_var.set(
                    f"Comms: received byte {byte:02X} from {self.app.device_id}"
                )
            else:
                self.app.status_var.set(
                    f"Comms: receive timeout from {self.app.device_id}"
                )

        except Exception as e:
            messagebox.showerror("UART Error", f"Failed to receive byte:\n{e}")


# ------------------------------- Run app -----------------------------------
if __name__ == "__main__":
    App().mainloop()
