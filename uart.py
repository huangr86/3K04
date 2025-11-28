import serial
import struct
import time

# ---------------------------------------------------------------------
# Global serial handle (shared with DCM)
# ---------------------------------------------------------------------
ser = None

# Streaming control flags
_stream_stop_requested = False
_stream_running = False

# ---------------------------------------------------------------------
# Protocol parameters
# ---------------------------------------------------------------------
CMD_PARAM        = 0x00   # Rx(1)
SUBCMD_SET_PAR   = 0x00   # Rx(2) for SET_PARAM
SUBCMD_RECV_ONLY = 0x01   # Rx(2) for READ / EGRAM ONLY

FRAME_LEN   = 105       # 89 param bytes + 16 egram bytes
PARAM_LEN   = 89
EGRAM_LEN   = 16        # 2 doubles (ATR, VENT)

SLEEP_BETWEEN_SAMPLES = 0.005
PRINT_EVERY           = 10


# ---------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------
def init_uart(port="COM10", baudrate=115200, timeout=0.05):
    """
    Open and return a configured UART port, stored in global `ser`.
    Called once in App.__init__.
    """
    global ser
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
        write_timeout=timeout,
    )
    if not ser.is_open:
        ser.open()

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print(f"UART initialized on {ser.port} at {baudrate} baud.")
    return ser


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def hex_dump(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def _ensure_ser():
    if ser is None:
        raise RuntimeError("UART not initialized. Call init_uart() first.")


def _read_one_frame() -> bytes:
    """
    Read exactly one 105-byte frame from `ser`, or raise RuntimeError.
    """
    _ensure_ser()
    rx = b""
    t0 = time.time()
    while len(rx) < FRAME_LEN and time.time() - t0 < 0.2:
        chunk = ser.read(FRAME_LEN - len(rx))
        if not chunk:
            break
        rx += chunk

    if len(rx) < FRAME_LEN:
        raise RuntimeError(
            f"RX too short: got {len(rx)} bytes, expected {FRAME_LEN}. "
            f"Raw: {rx.hex(' ')}"
        )

    return rx[:FRAME_LEN]


def _decode_frame(frame: bytes):
    """
    Given a 105-byte frame, return (params_echo, atr, vent).
    """
    params_echo = frame[:PARAM_LEN]
    egram_bytes = frame[PARAM_LEN:PARAM_LEN + EGRAM_LEN]
    atr, vent = struct.unpack("<dd", egram_bytes)
    return params_echo, atr, vent


def _get_val(params: dict | None, key: str, default):
    """
    Helper to pull a value from params with a default.
    Casts to type of `default`.
    """
    if params is None:
        return default
    if key not in params:
        return default
    ty = type(default)
    try:
        return ty(params[key])
    except Exception:
        return default


# ---------------------------------------------------------------------
# Frame builders – GUI params to pacemaker bytes
# ---------------------------------------------------------------------
def build_set_param_frame(params: dict | None, mode_code: int = 1) -> bytes:
    """
    Build the 91 byte SET_PARAM frame using the keys from params.json:

      LRL_ppm, URL_ppm,
      "Reaction Time", "Response Factor", "Recovery Time",
      Atrial_PW_ms, Ventricular_PW_ms, ARP_ms, VRP_ms,
      Pace_Atrial_Amp_V, Sense_Atrial_Amp_V,
      Pace_Ventricular_Amp_V, Sense_Ventricular_Amp_V,
      etc.

    Layout must match the Stateflow SET_PARAM block.
    """

    MODE = int(mode_code) & 0xFF

    # Rate limits
    LRL = int(_get_val(params, "LRL_ppm", 60))
    URL = int(_get_val(params, "URL_ppm", 120))

    # Rate adaptive high level settings
    Reaction_Time = int(_get_val(params, "Reaction Time", 30))   # seconds
    RF            = int(_get_val(params, "Response Factor", 8))  # dimensionless

    # Thresholds and hysteresis - internal to model, keep as constants
    W_Thres = 0.5
    J_Thres = 1.75
    R_Thres = 3.0

    Recovery_Time = int(_get_val(params, "Recovery Time", 5))    # minutes

    # Max sensor rates (just tie them to URL for now)
    W_MSR = URL
    J_MSR = URL
    R_MSR = URL

    W_Hys = 0.5
    J_Hys = 1.75
    R_Hys = 2.75

    # Helper to clamp amplitudes to hardware range 0.5–5.0 V
    def clamp_amp(v):
        return max(0.5, min(5.0, float(v)))

    # Atrial parameters
    Atrium_Amp = clamp_amp(_get_val(params, "Pace_Atrial_Amp_V", 3.5))
    ATR_Sense  = clamp_amp(_get_val(params, "Sense_Atrial_Amp_V", 3.5))

    # Ventricular parameters
    Vent_Amp   = clamp_amp(_get_val(params, "Pace_Ventricular_Amp_V", 3.5))
    VENT_Sense = clamp_amp(_get_val(params, "Sense_Ventricular_Amp_V", 3.5))

    # Pulse widths - GUI uses 0.1–1.9 ms in 0.1 steps, model expects uint16 ms
    def clamp_pw(v):
        v = max(0.1, min(1.9, float(v)))
        return max(1, int(round(v)))  # never send 0 ms

    ATR_Pulse_Width  = clamp_pw(_get_val(params, "Atrial_PW_ms", 1.0))
    Vent_Pulse_Width = clamp_pw(_get_val(params, "Ventricular_PW_ms", 1.0))

    # Refractory periods
    A_Refractory_Period = int(_get_val(params, "ARP_ms", 250))
    V_Refractory_Period = int(_get_val(params, "VRP_ms", 320))

    # Now pack in the exact order expected by the Simulink chart
    frame = bytearray()

    frame.append(CMD_PARAM)      # Rx(1)
    frame.append(SUBCMD_SET_PAR) # Rx(2)

    frame.extend(struct.pack("<B", MODE))          # Rx(3)

    frame.extend(struct.pack("<H", LRL))           # Rx(4:5)
    frame.extend(struct.pack("<H", URL))           # Rx(6:7)
    frame.extend(struct.pack("<H", Reaction_Time)) # Rx(8:9)
    frame.extend(struct.pack("<H", RF))            # Rx(10:11)

    frame.extend(struct.pack("<d", W_Thres))       # Rx(12:19)
    frame.extend(struct.pack("<d", J_Thres))       # Rx(20:27)
    frame.extend(struct.pack("<d", R_Thres))       # Rx(28:35)

    frame.extend(struct.pack("<H", Recovery_Time)) # Rx(36:37)
    frame.extend(struct.pack("<H", W_MSR))         # Rx(38:39)
    frame.extend(struct.pack("<H", J_MSR))         # Rx(40:41)
    frame.extend(struct.pack("<H", R_MSR))         # Rx(42:43)

    frame.extend(struct.pack("<d", W_Hys))         # Rx(44:51)
    frame.extend(struct.pack("<d", J_Hys))         # Rx(52:59)
    frame.extend(struct.pack("<d", R_Hys))         # Rx(60:67)

    frame.extend(struct.pack("<f", Atrium_Amp))           # Rx(68:71)
    frame.extend(struct.pack("<H", ATR_Pulse_Width))      # Rx(72:73)
    frame.extend(struct.pack("<H", A_Refractory_Period))  # Rx(74:75)
    frame.extend(struct.pack("<f", ATR_Sense))            # Rx(76:79)

    frame.extend(struct.pack("<f", Vent_Amp))             # Rx(80:83)
    frame.extend(struct.pack("<H", Vent_Pulse_Width))     # Rx(84:85)
    frame.extend(struct.pack("<H", V_Refractory_Period))  # Rx(86:87)
    frame.extend(struct.pack("<f", VENT_Sense))           # Rx(88:91)

    assert len(frame) == 91, f"SET frame length is {len(frame)}, expected 91"
    return bytes(frame)


def build_recv_only_frame() -> bytes:
    """
    91 byte frame:
      Rx(1) = 0x00 (CMD_PARAM)
      Rx(2) = 0x01 (READ / EGRAM ONLY)
      Remaining 89 bytes = 0 (ignored for params).
    """
    frame = bytearray()
    frame.append(CMD_PARAM)
    frame.append(SUBCMD_RECV_ONLY)
    frame.extend([0x00] * 89)
    assert len(frame) == 91, f"RECV frame length is {len(frame)}, expected 91"
    return bytes(frame)


# ---------------------------------------------------------------------
# 1) Send SET once and print echo
# ---------------------------------------------------------------------
def uart_send_set_params(params: dict, mode_code: int):
    """
    Send SET_PARAM frame once, built from GUI `params` + `mode_code`,
    then read and print the echo plus one egram sample to the terminal.
    """
    _ensure_ser()
    set_frame = build_set_param_frame(params, mode_code)

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print("TX: SET_PARAM (00 00 ...) frame:")
    print(hex_dump(set_frame))
    ser.write(set_frame)
    ser.flush()

    try:
        frame = _read_one_frame()
    except RuntimeError as e:
        print(f"RX error after SET_PARAM: {e}")
        return

    params_echo, atr, vent = _decode_frame(frame)

    print("RX echo bytes (89):")
    print(hex_dump(params_echo))
    print(f"Atrium Egram sample:    {atr:.6f}")
    print(f"Ventricle Egram sample: {vent:.6f}")


# ---------------------------------------------------------------------
# 2) Send RECV_ONLY once and print echo
# ---------------------------------------------------------------------
def uart_send_recv_only():
    """
    Send RECV_ONLY frame once, then read and print the echo plus one
    egram sample to the terminal.
    """
    _ensure_ser()
    recv_frame = build_recv_only_frame()

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print("TX: RECV_ONLY (00 01 ...) frame:")
    print(hex_dump(recv_frame))
    ser.write(recv_frame)
    ser.flush()

    try:
        frame = _read_one_frame()
    except RuntimeError as e:
        print(f"RX error after RECV_ONLY: {e}")
        return

    params_echo, atr, vent = _decode_frame(frame)

    print("RX echo bytes (89):")
    print(hex_dump(params_echo))
    print(f"Atrium Egram sample:    {atr:.6f}")
    print(f"Ventricle Egram sample: {vent:.6f}")


# ---------------------------------------------------------------------
# 3) Continuous egram streaming
# ---------------------------------------------------------------------
def stream_egram(callback, params: dict | None, mode_code: int = 1):
    """
    Continuous egram stream.

    - Builds SET_PARAM from `params` + `mode_code` and sends it once.
    - Then repeatedly sends RECV_ONLY, reads one frame,
      decodes egram and calls `callback(atr, vent, params_echo, sample_idx)`.

    This is designed to run in a background thread.
    """
    global _stream_stop_requested, _stream_running

    _ensure_ser()

    if _stream_running:
        print("Egram stream already running.")
        return

    _stream_stop_requested = False    # request flag
    _stream_running = True            # state flag

    set_frame  = build_set_param_frame(params, mode_code)
    recv_frame = build_recv_only_frame()

    ser.reset_input_buffer()
    ser.reset_output_buffer()
    print("Streaming: sending initial SET_PARAM (00 00 ...)")
    print(hex_dump(set_frame))
    ser.write(set_frame)
    ser.flush()

    try:
        _ = _read_one_frame()
    except RuntimeError as e:
        print(f"Initial frame after SET failed: {e}")

    print("Streaming with RECV_ONLY (00 01 ...). Call stop_stream() to stop.")

    sample_idx = 0

    try:
        while not _stream_stop_requested:
            ser.write(recv_frame)
            ser.flush()

            try:
                frame = _read_one_frame()
            except RuntimeError:
                sample_idx += 1
                time.sleep(SLEEP_BETWEEN_SAMPLES)
                continue

            params_echo, atr, vent = _decode_frame(frame)

            if callback is not None:
                try:
                    callback(atr, vent, params_echo, sample_idx)
                except Exception as cb_e:
                    print(f"Callback error: {cb_e}")

            if sample_idx % PRINT_EVERY == 0:
                print(f"[{sample_idx}] Atr={atr:.6f} Vent={vent:.6f}")

            sample_idx += 1
            time.sleep(SLEEP_BETWEEN_SAMPLES)
    finally:
        _stream_running = False
        _stream_stop_requested = False
        print("Egram stream stopped.")


def stop_stream():
    """
    Request that stream_egram() stop.
    """
    global _stream_stop_requested
    _stream_stop_requested = True


if __name__ == "__main__":
    # Simple manual test with default params
    init_uart("COM10", 115200)
    uart_send_set_params(params=None, mode_code=1)
    uart_send_recv_only()
