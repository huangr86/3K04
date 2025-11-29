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
CMD_PARAM        = 0x16   # Rx(1)
SUBCMD_SET_PAR   = 0x55   # Rx(2) for SET_PARAM
SUBCMD_RECV_ONLY = 0x22   # Rx(2) for READ / EGRAM ONLY

# 2 command bytes + 89 parameter bytes + 16 egram bytes
FRAME_LEN   = 105       # total RX frame
PARAM_LEN   = 89        # echo parameter region
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
# Frame builders – aligned with NEW Simulink layout
# ---------------------------------------------------------------------
def build_set_param_frame(params: dict | None, mode_code: int = 1) -> bytes:
    """
    Build the 91-byte SET_PARAM frame.

    Layout after CMD and SUBCMD:

        Rx(3)  MODE              uint8
        Rx(4:5)  LRL             uint16
        Rx(6:7)  URL             uint16

        % pacing and sensing first
        Rx(8:11)   a_PaceAmp     single
        Rx(12:13)  a_PulseWidth  uint16
        Rx(14:15)  ARP           uint16
        Rx(16:19)  a_SenseAmp    single

        Rx(20:23)  v_PaceAmp     single
        Rx(24:25)  v_PulseWidth  uint16
        Rx(26:27)  VRP           uint16
        Rx(28:31)  v_SenseAmp    single

        % then rate response block
        Rx(32:33)  Reaction_Time   uint16
        Rx(34:35)  Response_Factor uint16
        Rx(36:43)  Walk_Thresh     double
        Rx(44:51)  Jog_Thresh      double
        Rx(52:59)  Run_Thresh      double
        Rx(60:61)  Recovery_Time   uint16
        Rx(62:63)  Walk_MSR        uint16
        Rx(64:65)  Jog_MSR         uint16
        Rx(66:67)  Run_MSR         uint16
        Rx(68:75)  Walk_Hys        double
        Rx(76:83)  Jog_Hys         double
        Rx(84:91)  Run_Hys         double
    """

    MODE = int(mode_code) & 0xFF

    # ---- drawn from DCM JSON params ----
    # heart rates (ppm)
    LRL_ppm = _get_val(params, "LRL_ppm", 60)
    URL_ppm = _get_val(params, "URL_ppm", 120)

    # atrial side
    a_PaceAmp_V  = _get_val(params, "Pace_Atrial_Amp_V", 3.5)      # V
    a_PW_ms      = _get_val(params, "Atrial_PW_ms", 1.0)           # ms
    ARP_ms       = _get_val(params, "ARP_ms", 250)                 # ms
    a_SenseAmp_V = _get_val(params, "Sense_Atrial_Amp_V", 3.5)     # V, used as a_SenseAmp

    # ventricular side
    v_PaceAmp_V  = _get_val(params, "Pace_Ventricular_Amp_V", 3.5) # V
    v_PW_ms      = _get_val(params, "Ventricular_PW_ms", 1.0)      # ms
    VRP_ms       = _get_val(params, "VRP_ms", 320)                 # ms
    v_SenseAmp_V = _get_val(params, "Sense_Ventricular_Amp_V", 3.5)# V

    # rate response
    Reaction_Time   = _get_val(params, "Reaction Time", 30)        # s
    Response_Factor = _get_val(params, "Response Factor", 8)       # unitless
    Recovery_Time   = _get_val(params, "Recovery Time", 5)         # min

    # The Walk/Jog/Run thresholds and hysteresis we keep as internal defaults for now
    Walk_Thresh = 0.5
    Jog_Thresh  = 1.75
    Run_Thresh  = 3.0

    Walk_MSR = 90
    Jog_MSR  = 110
    Run_MSR  = 130

    Walk_Hys = 0.5
    Jog_Hys  = 1.75
    Run_Hys  = 2.75

    # ---- pack into bytes ----
    frame = bytearray()

    # CMD and SUBCMD
    frame.append(CMD_PARAM)        # Rx(1)
    frame.append(SUBCMD_SET_PAR)   # Rx(2)

    # mode and main rates
    frame.extend(struct.pack("<B", MODE))         # Rx(3)
    frame.extend(struct.pack("<H", LRL_ppm))      # Rx(4:5)
    frame.extend(struct.pack("<H", URL_ppm))      # Rx(6:7)

    # pacing and sensing first
    frame.extend(struct.pack("<f", a_PaceAmp_V))                # Rx(8:11)
    frame.extend(struct.pack("<H", int(round(a_PW_ms))))        # Rx(12:13)
    frame.extend(struct.pack("<H", int(round(ARP_ms))))         # Rx(14:15)
    frame.extend(struct.pack("<f", a_SenseAmp_V))               # Rx(16:19)

    frame.extend(struct.pack("<f", v_PaceAmp_V))                # Rx(20:23)
    frame.extend(struct.pack("<H", int(round(v_PW_ms))))        # Rx(24:25)
    frame.extend(struct.pack("<H", int(round(VRP_ms))))         # Rx(26:27)
    frame.extend(struct.pack("<f", v_SenseAmp_V))               # Rx(28:31)

    # rate response bloc
    frame.extend(struct.pack("<H", int(Reaction_Time)))         # Rx(32:33)
    frame.extend(struct.pack("<H", int(Response_Factor)))       # Rx(34:35)

    frame.extend(struct.pack("<d", Walk_Thresh))                # Rx(36:43)
    frame.extend(struct.pack("<d", Jog_Thresh))                 # Rx(44:51)
    frame.extend(struct.pack("<d", Run_Thresh))                 # Rx(52:59)

    frame.extend(struct.pack("<H", int(Recovery_Time)))         # Rx(60:61)
    frame.extend(struct.pack("<H", int(Walk_MSR)))              # Rx(62:63)
    frame.extend(struct.pack("<H", int(Jog_MSR)))               # Rx(64:65)
    frame.extend(struct.pack("<H", int(Run_MSR)))               # Rx(66:67)

    frame.extend(struct.pack("<d", Walk_Hys))                   # Rx(68:75)
    frame.extend(struct.pack("<d", Jog_Hys))                    # Rx(76:83)
    frame.extend(struct.pack("<d", Run_Hys))                    # Rx(84:91)

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
    _stream_running = True

    set_frame  = build_set_param_frame(params, mode_code)
    recv_frame = build_recv_only_frame()

    ser.reset_input_buffer()
    ser.reset_output_buffer()
    print("Streaming: sending initial SET_PARAM (00 00 ...)")
    print(hex_dump(set_frame))
    ser.write(set_frame)
    ser.flush()

    # read initial echo
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
