import serial
import struct



def init_uart(port="/dev/ttyUSB0", baudrate=115200, timeout=1):

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


def send_params(packet_params, mode_byte):
    """
    Test function to print the UART packet instead of sending.
    packet_params: dict of parameters in fixed order
    mode: string, e.g., "VOO"
    """

    # Example: map mode string to 4-bit integer (adjust to your encoding)


    # Mode byte: 4-bit repeated
    mode_byte = (mode_byte << 4) | mode_byte

    print(f"(mode byte: {mode_byte:08b})")

    values = [mode_byte] + list(packet_params.values()) #append the mode byte to the front of the parameter data
    fmt = ">B" + "H"*len(packet_params)  #16-bit per parameter big-endian MSB first
    packet = struct.pack(fmt, *values)

    # Print simulated UART packet
    print("Simulated UART packet (hex):", packet.hex())
    print(f"(mode byte: {mode_byte:08b})")
    print("Parameters (in order):")
    for k, v in packet_params.items():
        print(f"  {k}: {v}")



if __name__ == "__main__":
    import json
    # Load parameters from a JSON file
    with open("params.json", "r") as f:
        data = json.load(f)

    ser = init_uart()
    send_params(ser, data)
