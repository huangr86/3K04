import serial
import struct
import time

START_BYTE = 0x10
SET_BYTE = 0x37
RECEIVE_BYTE = 0x16


def init_uart(port="COM10", baudrate=115200, timeout=1):

    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
        write_timeout=timeout,
    )

    if ser.is_open:
        print(f"UART initialized on {port} at {baudrate} baud.")
    else:
        ser.open()
        print(f"UART opened on {port} at {baudrate} baud.")

    return ser



def send_params(ser, packet_params, mode_byte):
    """
    Test function to print the UART packet instead of sending.
    packet_params: dict of parameters in fixed order
    mode: string, e.g., "VOO"
    """

    

    # Example: map mode string to 4-bit integer (adjust to your encoding)


    # Mode byte: 4-bit repeated
    mode_byte = (mode_byte << 4) | mode_byte

    print(f"(mode byte: {mode_byte:08b})")

    values = [START_BYTE, SET_BYTE,mode_byte] + list(packet_params.values()) #append the mode byte to the front of the parameter data
    fmt = ">BBB" + "H"*len(packet_params)  #16-bit per parameter big-endian MSB first
    packet = struct.pack(fmt, *values)

    # Print simulated UART packet
    print("Simulated UART packet (hex):", packet.hex())
    print(f"(mode byte: {mode_byte:08b})")
    print("Parameters (in order):")
    for k, v in packet_params.items():
        print(f"  {k}: {v}")


    # ---- SEND OVER UART ----
    ser.write(packet)
    ser.flush()

    print("Sent UART packet:", packet.hex())


def send_params_test(ser, packet_params, mode_byte):

    # ---- Parameter order with sizes ----
    PARAM_ORDER = [
        ("LRL_ppm", "H"),                  # 2 bytes
        ("Atrial_PW_ms", "B"),             # 1 byte
        ("Ventricular_PW_ms", "B"),        # 1 byte
        ("ARP_ms", "H"),                   # 2 bytes
        ("VRP_ms", "H"),                   # 2 bytes
        ("Sense_Ventricular_Amp_V", "B"),  # 1 byte
        ("Sense_Atrial_Amp_V", "B"),       # 1 byte
        ("Pace_Atrial_Amp_V", "B"),        # 1 byte
        ("Pace_Ventricular_Amp_V", "B"),   # 1 byte
    ]

    # Mode byte duplicated into upper + lower nibble
    mode_byte = (mode_byte << 4) | mode_byte
    print(f"(mode byte: {mode_byte:08b})")

    # ---- Build parameter list according to mixed widths ----
    ordered_values = []
    fmt_params = ""  # will hold something like "HBBHHBBB"

    for name, code in PARAM_ORDER:
        if name not in packet_params:
            raise KeyError(f"Missing parameter '{name}' in packet_params")

        ordered_values.append(packet_params[name])
        fmt_params += code

    # Full format string: start, set, mode, then parameters
    fmt = ">BBB" + fmt_params

    # Build packet
    values = [START_BYTE, SET_BYTE, mode_byte] + ordered_values
    packet = struct.pack(fmt, *values)

    print("Simulated UART packet:", packet.hex())
    print("Sent UART packet:", packet.hex())

    # Send packet
    ser.write(packet)
    ser.flush()

    # ------------------ RECEIVE --------------------------
    time.sleep(1)

def send_params_test(ser, packet_params, mode_byte):

    # ---- Parameter order with sizes ----
    PARAM_ORDER = [
        ("LRL_ppm", "H"),                  # 2 bytes
        ("Atrial_PW_ms", "B"),             # 1 byte
        ("Ventricular_PW_ms", "B"),        # 1 byte
        ("ARP_ms", "H"),                   # 2 bytes
        ("VRP_ms", "H"),                   # 2 bytes
        ("Sense_Ventricular_Amp_V", "B"),  # 1 byte
        ("Sense_Atrial_Amp_V", "B"),       # 1 byte
        ("Pace_Atrial_Amp_V", "B"),        # 1 byte
        ("Pace_Ventricular_Amp_V", "B"),   # 1 byte
    ]

    # Mode byte duplicated into upper + lower nibble
    mode_byte = (mode_byte << 4) | mode_byte
    print(f"(mode byte: {mode_byte:08b})")

    # ---- Build parameter list according to mixed widths ----
    ordered_values = []
    fmt_params = ""  # will hold something like "HBBHHBBB"

    for name, code in PARAM_ORDER:
        if name not in packet_params:
            raise KeyError(f"Missing parameter '{name}' in packet_params")

        ordered_values.append(packet_params[name])
        fmt_params += code

    # Full format string: start, set, mode, then parameters
    fmt = ">BBB" + fmt_params

    # Build packet
    values = [START_BYTE, SET_BYTE, mode_byte] + ordered_values
    packet = struct.pack(fmt, *values)

    print("Simulated UART packet:", packet.hex())
    print("Sent UART packet:", packet.hex())

    # Send packet
    ser.write(packet)
    ser.flush()

    # ------------------ RECEIVE --------------------------
    time.sleep(1)

    # Simulink returns ONLY: mode + params
    rx_fmt = ">B" + fmt_params
    expected_len = struct.calcsize(rx_fmt)

    rx = ser.read(expected_len)

    if len(rx) != expected_len:
        print(f"WARNING: Expected {expected_len} bytes, got {len(rx)}")
        print("Raw RX:", rx.hex())
        return

    unpacked = struct.unpack(rx_fmt, rx)
    rx_mode = unpacked[0]
    rx_params = unpacked[1:]

    print("\nSimulink Response:")
    print(f"  Mode byte: {rx_mode:08b}")

    print("\nReturned Parameters:")
    for (name, _), value in zip(PARAM_ORDER, rx_params):
        print(f"  {name}: {value}")






def receive_params(ser, num_params, start_byte=START_BYTE, receive_byte=RECEIVE_BYTE):
    """
    Request and receive a packet from the device.
    Protocol:
    1. Send [START_BYTE, RECEIVE_BYTE] to request a response.
    2. Wait for the response: [START_BYTE, SET_BYTE, MODE_BYTE, PARAM1, PARAM2...]
    """
    # Step 1: Send the receive request
    request_packet = bytes([start_byte, receive_byte])
    ser.write(request_packet)
    ser.flush()
    print(f"Sent receive request: {request_packet.hex()}")

    # Step 2: Read response packet
    packet_size = 3 + 2*num_params  # START + SET + MODE + N*2 bytes
    raw = ser.read(packet_size)

    if len(raw) < packet_size:
        print(f"Receive timeout: expected {packet_size} bytes, got {len(raw)}")
        return None

    print("Received UART packet (hex):", raw.hex())

    # Step 3: Unpack
    fmt = ">BBB" + "H"*num_params
    unpacked = struct.unpack(fmt, raw)

    start, set_byte, mode_byte, *params = unpacked

    print(f"Decoded START_BYTE: {start:02X}")
    print(f"Decoded SET_BYTE: {set_byte:02X}")
    print(f"Decoded MODE_BYTE: {mode_byte:02X}")
    print("Decoded PARAMS:", params)

    return start, set_byte, mode_byte, params



#test send_mode
def send_mode_byte(ser, mode_byte):
    """
    Elementary test function to send only a single mode byte
    with START_BYTE and SET_BYTE header.
    """
    # Mode byte: 4-bit repeated
    mode_byte = (mode_byte << 4) | mode_byte
    print(f"(mode byte: {mode_byte:08b})")

    # Build values: START_BYTE, SET_BYTE, MODE_BYTE only
    values = [START_BYTE, SET_BYTE, mode_byte]

    # Format: 3 bytes (B = 1 byte each)nnnn  nb hnbzsa
    fmt = ">BBB"
    packet = struct.pack(fmt, *values)

    # Debug print
    print("Simulated UART packet (hex):", packet.hex())
    print(f"(mode byte: {mode_byte:08b})")

    # Send over UART
    ser.write(packet)
    ser.flush()
    print("Sent UART packet:", packet.hex())


#test_receive mode
def receive_one_param_byte(ser):
    """
    Elementary test function to request a packet and only read the first parameter byte.
    Protocol:
    1. Send [START_BYTE, RECEIVE_BYTE] to request data.
    2. Wait for the response: [START_BYTE, SET_BYTE, MODE_BYTE, PARAM_BYTE, ...]
    3. Return only the first parameter byte.
    """
    # Step 1: send receive request
    request_packet = bytes([START_BYTE, RECEIVE_BYTE])
    ser.write(request_packet)
    ser.flush()
    print(f"Sent receive request: {request_packet.hex()}")

    # Step 2: read response (header + 1 parameter byte)
    # Header = 3 bytes (START, SET, MODE) + 1 byte parameter
    raw = ser.read(4)  # 3 header bytes + 1 payload byte

    if len(raw) < 4:
        print(f"Receive timeout: expected 4 bytes, got {len(raw)}")
        return None

    print("Received raw packet (hex):", raw.hex())

    # Step 3: unpack header + first parameter byte
    start, set_byte, mode_byte, param_byte = struct.unpack(">BBB B", raw)
    print(f"START_BYTE: {start:02X}, SET_BYTE: {set_byte:02X}, MODE_BYTE: {mode_byte:02X}")
    print(f"First PARAM byte: {param_byte:02X} ({param_byte})")

    return param_byte


if __name__ == "__main__":
    import json
    # Load parameters from a JSON file
    with open("params.json", "r") as f:
        data = json.load(f)

    ser = init_uart()
    send_params(ser, data)
