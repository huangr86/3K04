import serial
import struct

# Protocol bytes chosen to match the Simulink / Stateflow chart:
#   Rx(1) == hex2dec('16')  -> START_BYTE
#   Rx(2) == hex2dec('55')  -> SET / write command
#   Rx(2) == hex2dec('22')  -> RECEIVE / read command
START_BYTE   = 0x16
SET_BYTE     = 0x55
RECEIVE_BYTE = 0x22


def init_uart(port: str = "COM10", baudrate: int = 115200, timeout: float = 1.0) -> serial.Serial:
    """Open and return a configured UART port."""
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    )
    print(f"Opened UART on {ser.port} at {baudrate} baud.")
    return ser


def _encode_param_values(packet_params) -> list:
    """Convert ordered dict of param values into a list of 16-bit ints."""
    values = []
    for v in packet_params.values():
        v_int = int(v) & 0xFFFF
        values.append(v_int)
    return values


def send_params(ser: serial.Serial, packet_params: dict, mode_byte: int) -> None:
    """Send full parameter packet (legacy / debugging helper).

    Packet format on the wire:
        [START_BYTE, SET_BYTE, MODE_BYTE,
         p1_hi, p1_lo, p2_hi, p2_lo, ..., pN_hi, pN_lo]

    - MODE_BYTE is the raw mode index 0..7 (no nibble repetition).
    - Each parameter is sent as a big-endian 16-bit unsigned integer.
    """
    mode_byte = int(mode_byte) & 0xFF
    param_words = _encode_param_values(packet_params)

    # Build header
    values = [START_BYTE, SET_BYTE, mode_byte]

    # Append parameters as bytes (big-endian)
    for w in param_words:
        hi = (w >> 8) & 0xFF
        lo = w & 0xFF
        values.extend([hi, lo])

    packet = bytes(values)
    print("TX (send_params):", packet.hex(" "))
    ser.write(packet)
    ser.flush()


def send_programming_packet(
    ser: serial.Serial,
    mode_select: int,
    LRL_interval_ms: int,
    a_pace_width_code: int,
    v_pace_width_code: int,
    v_sense_amp_code: int,
    ARP_ms: int,
    VRP_ms: int,
    a_sense_amp_code: int,
    v_pace_amp_code: int,
    a_pace_amp_code: int,
) -> None:
    """
    Send a programming packet that matches the Stateflow Rx(1:15) layout:

        Rx(1)  = 0x16                  (START_BYTE / k_sync)
        Rx(2)  = 0x55                  (SET_BYTE   / k_pparams)
        Rx(3)  = mode_select           (uint8)
        Rx(4)  = LRL_interval_hi       (ms, uint16, big-endian)
        Rx(5)  = LRL_interval_lo
        Rx(6)  = p_aPaceWidth          (uint8, width in 0.1 ms units)
        Rx(7)  = p_vPaceWidth          (uint8, width in 0.1 ms units)
        Rx(8)  = p_vSenseAmp           (uint8, sensitivity in 0.1 mV units)
        Rx(9)  = ARP_hi                (uint16, ms, big-endian)
        Rx(10) = ARP_lo
        Rx(11) = VRP_hi                (uint16, ms, big-endian)
        Rx(12) = VRP_lo
        Rx(13) = p_aSenseAmp           (uint8, sensitivity in 0.1 mV units)
        Rx(14) = P_vPaceAmp            (uint8, amplitude in 0.1 V units)
        Rx(15) = p_aPaceAmp            (uint8, amplitude in 0.1 V units)
    """

    def u8(v: int) -> int:
        return int(v) & 0xFF

    def u16_bytes(v: int):
        v = int(v) & 0xFFFF
        return (v >> 8) & 0xFF, v & 0xFF

    values = [
        START_BYTE,
        SET_BYTE,
        u8(mode_select),
    ]

    # LRL interval (ms)
    values.extend(u16_bytes(LRL_interval_ms))

    # Widths and ventricular sense amplitude (single-byte codes)
    values.append(u8(a_pace_width_code))
    values.append(u8(v_pace_width_code))
    values.append(u8(v_sense_amp_code))

    # ARP, VRP (ms)
    values.extend(u16_bytes(ARP_ms))
    values.extend(u16_bytes(VRP_ms))

    # Atrial sense / pace amps and ventricular pace amp
    values.append(u8(a_sense_amp_code))
    values.append(u8(v_pace_amp_code))
    values.append(u8(a_pace_amp_code))

    packet = bytes(values)
    print("TX (send_programming_packet):", packet.hex(" "))
    ser.write(packet)
    ser.flush()


def receive_params(ser: serial.Serial, num_params: int):
    """Request parameters from the device and decode them.

    Request packet:
        [START_BYTE, RECEIVE_BYTE]

    Response packet:
        [START_BYTE, RECEIVE_BYTE, MODE_BYTE,
         p1_hi, p1_lo, ..., pN_hi, pN_lo]
    """
    # Send request
    request_packet = bytes([START_BYTE, RECEIVE_BYTE])
    print("TX (receive_params request):", request_packet.hex(" "))
    ser.write(request_packet)
    ser.flush()

    # 3 header bytes + 2 bytes per parameter
    expected_size = 3 + 2 * num_params
    raw = ser.read(expected_size)

    if len(raw) < expected_size:
        print(
            f"RX timeout in receive_params: expected {expected_size} bytes, "
            f"got {len(raw)} ({raw.hex(' ')})"
        )
        return None

    print("RX (receive_params raw):", raw.hex(" "))

    # Decode
    start = raw[0]
    cmd = raw[1]
    mode = raw[2]
    params = []
    for i in range(num_params):
        hi = raw[3 + 2 * i]
        lo = raw[4 + 2 * i]
        params.append((hi << 8) | lo)

    print(f"Decoded header: start={start:02X}, cmd={cmd:02X}, mode={mode:02X}")
    print("Params:", params)
    return start, cmd, mode, params


def send_mode_byte(ser: serial.Serial, mode_byte: int) -> None:
    """Send only the header and mode byte (for quick serial tests)."""
    mode_byte = int(mode_byte) & 0xFF
    packet = bytes([START_BYTE, SET_BYTE, mode_byte])
    print("TX (send_mode_byte):", packet.hex(" "))
    ser.write(packet)
    ser.flush()


def receive_one_param_byte(ser: serial.Serial):
    """Small helper that requests parameters and prints the first param byte.

    Request packet:
        [START_BYTE, RECEIVE_BYTE]

    Response packet:
        [START_BYTE, RECEIVE_BYTE, MODE_BYTE, first_param_byte, ...]
    """
    # Send request
    request_packet = bytes([START_BYTE, RECEIVE_BYTE])
    print("TX (receive_one_param_byte request):", request_packet.hex(" "))
    ser.write(request_packet)
    ser.flush()

    # Expect 4 bytes minimum
    raw = ser.read(4)

    if len(raw) < 4:
        print(
            f"RX timeout in receive_one_param_byte: expected 4 bytes, "
            f"got {len(raw)} ({raw.hex(' ')})"
        )
        return None

    print("RX (receive_one_param_byte raw):", raw.hex(" "))

    start, cmd, mode, param0 = raw[0], raw[1], raw[2], raw[3]
    print(f"Decoded header: start={start:02X}, cmd={cmd:02X}, mode={mode:02X}")
    print(f"First param byte: {param0:02X} ({param0})")
    return param0
