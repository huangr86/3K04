import serial
import struct

# Protocol bytes chosen to match the Simulink / Stateflow chart:
#   Rx(1) == hex2dec('16')  -> START_BYTE
#   Rx(2) == hex2dec('55')  -> SET / write command
#   Rx(2) == hex2dec('22')  -> RECEIVE / read command
START_BYTE   = 0x16
SET_BYTE     = 0x55
RECEIVE_BYTE = 0x22


def init_uart(port: str = "COM5", baudrate: int = 9600, timeout: float = 1.0) -> serial.Serial:
    """Open and return a configured UART port."""
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

    print(f"UART initialized on {ser.port} at {baudrate} baud.")
    return ser


def _encode_param_values(packet_params) -> list:
    """Convert ordered dict of param values into a list of 16-bit ints."""
    values = []
    for v in packet_params.values():
        v_int = int(v) & 0xFFFF
        values.append(v_int)
    return values


def send_params(ser: serial.Serial, packet_params: dict, mode_byte: int) -> None:
    """Send full parameter packet.

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


def receive_params(ser: serial.Serial, num_params: int):
    """Request a full parameter packet and decode it.

    Sends:   [START_BYTE, RECEIVE_BYTE]
    Expects: [START_BYTE, SET_BYTE, MODE_BYTE,
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
    print("Decoded params:", params)
    return start, cmd, mode, params


def send_mode_byte(ser: serial.Serial, mode_byte: int) -> None:
    """Send only the mode byte (no parameters).

    Packet format:
        [START_BYTE, SET_BYTE, MODE_BYTE]
    """
    mode_byte = int(mode_byte) & 0xFF
    packet = bytes([START_BYTE, SET_BYTE, mode_byte])
    print("TX (send_mode_byte):", packet.hex(" "))
    ser.write(packet)
    ser.flush()


def receive_one_param_byte(ser: serial.Serial):
    """Request data and return the first parameter byte.

    This is a simple debug helper that assumes the device answers with at
    least 4 bytes:

        [START_BYTE, SET_BYTE, MODE_BYTE, first_param_byte, ...]
    """
    # Send request header
    request = bytes([START_BYTE, RECEIVE_BYTE])
    print("TX (receive_one_param_byte request):", request.hex(" "))
    ser.write(request)
    ser.flush()

    # Read 4 bytes: 3-byte header + first param byte
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
