

import serial
import struct
import time
import matplotlib.pyplot as plt

# Global serial handle
ser = None

def init_uart(port="/dev/ttyS0", baudrate=115200):
    global ser
    ser = serial.Serial(port, baudrate, timeout=0.1)
    return ser

def uart_send_set_params(params: dict):
    global ser
    frame = build_set_param_frame(params)
    ser.write(frame)

def uart_send_recv_only():
    global ser
    frame = build_recv_only_frame()
    ser.write(frame)

#NEW CODE 
 
# ---------------------------------------------------------
# Protocol parameters
# ---------------------------------------------------------
CMD_PARAM        = 0x00   # Rx(1)
SUBCMD_SET_PAR   = 0x00   # Rx(2) for SET_PARAM
SUBCMD_RECV_ONLY = 0x01   # Rx(2) for READ / EGRAM ONLY

# ---------------------------------------------------------
# Protocol parameters
# ---------------------------------------------------------
CMD_PARAM        = 0x00   # Rx(1)
SUBCMD_SET_PAR   = 0x00   # Rx(2) for SET_PARAM
SUBCMD_RECV_ONLY = 0x01   # Rx(2) for READ / EGRAM ONLY
 
FRAME_LEN   = 105       # 89 param bytes + 16 egram bytes
PARAM_LEN   = 89
EGRAM_LEN   = 16        # 2 doubles (ATR, VENT)
 
# Plot / log settings
MAX_POINTS            = 500    # how many recent samples to show
SLEEP_BETWEEN_SAMPLES = 0.0    # small delay between requests
PRINT_EVERY           = 10     # print frame info every N samples
PLOT_EVERY            = 2      # update plot every N samples
 
 
def build_set_param_frame():
    """
    Build the 91 byte SET_PARAM frame.
    """
 
    # Defaults from your "Default" state
    MODE   = 1
    LRL    = 60
    URL    = 180
    Reaction_Time = 30
    RF     = 16
 
    W_Thres = 0.5
    J_Thres = 1.75
    R_Thres = 3.0
 
    Recovery_Time = 5
    W_MSR  = 80
    J_MSR  = 120
    R_MSR  = 160
 
    W_Hys = 0.5
    J_Hys = 1.75
    R_Hys = 2.75
 
    Atrium_Amp       = 1.0
    ATR_Pulse_Width  = 1
    A_Refractory_Per = 250
    ATR_Sense        = 4.0
 
    Vent_Amp           = 1.0
    Vent_Pulse_Width   = 1
    V_Refractory_Per   = 200
    VENT_Sense         = 4.0
 
    frame = bytearray()
 
    frame.append(CMD_PARAM)        # Rx(1)
    frame.append(SUBCMD_SET_PAR)   # Rx(2)
 
    frame.extend(struct.pack('<B', MODE))
 
    frame.extend(struct.pack('<H', LRL))
    frame.extend(struct.pack('<H', URL))
    frame.extend(struct.pack('<H', Reaction_Time))
    frame.extend(struct.pack('<H', RF))
 
    frame.extend(struct.pack('<d', W_Thres))
    frame.extend(struct.pack('<d', J_Thres))
    frame.extend(struct.pack('<d', R_Thres))
 
    frame.extend(struct.pack('<H', Recovery_Time))
    frame.extend(struct.pack('<H', W_MSR))
    frame.extend(struct.pack('<H', J_MSR))
    frame.extend(struct.pack('<H', R_MSR))
 
    frame.extend(struct.pack('<d', W_Hys))
    frame.extend(struct.pack('<d', J_Hys))
    frame.extend(struct.pack('<d', R_Hys))
 
    frame.extend(struct.pack('<f', Atrium_Amp))
    frame.extend(struct.pack('<H', ATR_Pulse_Width))
    frame.extend(struct.pack('<H', A_Refractory_Per))
    frame.extend(struct.pack('<f', ATR_Sense))
 
    frame.extend(struct.pack('<f', Vent_Amp))
    frame.extend(struct.pack('<H', Vent_Pulse_Width))
    frame.extend(struct.pack('<H', V_Refractory_Per))
    frame.extend(struct.pack('<f', VENT_Sense))
 
    assert len(frame) == 91, "SET frame length is %d, expected 91" % len(frame)
    return bytes(frame)
 
 
def build_recv_only_frame():
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
    assert len(frame) == 91, "RECV frame length is %d, expected 91" % len(frame)
    return bytes(frame)
 
 
def hex_dump(b):
    return ' '.join('%02X' % x for x in b)
 
 
def stream_with_echo_and_plot(port="COM10", baudrate=115200):
    set_frame  = build_set_param_frame()
    recv_frame = build_recv_only_frame()
 
    atr_values = []
    vent_values = []
 
    # Live plot setup
    plt.ion()
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
 
    line_atr, = ax1.plot([], [], label="Atrium")
    ax1.set_title("Atrium Egram")
    ax1.set_ylabel("Amplitude")
    ax1.grid(True)
 
    line_vent, = ax2.plot([], [], label="Ventricle")
    ax2.set_title("Ventricle Egram")
    ax2.set_xlabel("Sample index")
    ax2.set_ylabel("Amplitude")
    ax2.grid(True)
 
    fig.tight_layout()
 
    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.05,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
 
        print("Sending SET_PARAM (00 00 ...) once...")
        ser.write(set_frame)
        ser.flush()
        time.sleep(0.1)
        ser.read(256)   # clear any immediate response
 
        print("Streaming with RECV_ONLY (00 01 ...) (Ctrl+C to stop)...")
 
        sample_idx = 0
 
        try:
            while True:
                # 1) Send RECV_ONLY frame
                ser.write(recv_frame)
                ser.flush()
 
                # 2) Read exactly one frame (up to 105 bytes)
                rx = b""
                t0 = time.time()
                while len(rx) < FRAME_LEN and time.time() - t0 < 0.1:
                    chunk = ser.read(FRAME_LEN - len(rx))
                    if not chunk:
                        break
                    rx += chunk
 
                if len(rx) < FRAME_LEN:
                    # Just skip silently if a frame is missing; do not spam prints
                    time.sleep(SLEEP_BETWEEN_SAMPLES)
                    sample_idx += 1
                    continue
 
                rx_frame = rx[:FRAME_LEN]
                params_echo = rx_frame[:PARAM_LEN]
                egram_bytes = rx_frame[PARAM_LEN:PARAM_LEN + EGRAM_LEN]
 
                # Decode egram doubles
                atr, vent = struct.unpack('<dd', egram_bytes)
                atr_values.append(atr)
                vent_values.append(vent)
 
                if len(atr_values) > MAX_POINTS:
                    atr_values = atr_values[-MAX_POINTS:]
                    vent_values = vent_values[-MAX_POINTS:]
 
                # 3) Print echo and egram only every PRINT_EVERY frames
                if sample_idx % PRINT_EVERY == 0:
                    print("[%d] RX length: %d" % (sample_idx, len(rx_frame)))
                    print("[%d] Echo bytes (89):" % sample_idx)
                    print(hex_dump(params_echo))
                    print("[%d] Egram bytes (16):" % sample_idx)
                    print(hex_dump(egram_bytes))
 
                # 4) Update plots every PLOT_EVERY frames
                if sample_idx % PLOT_EVERY == 0:
                    x = range(len(atr_values))
                    line_atr.set_data(x, atr_values)
                    line_vent.set_data(x, vent_values)
 
                    ax1.set_xlim(0, max(len(atr_values), 10))
                    if atr_values:
                        ax1.set_ylim(min(atr_values) - 0.1, max(atr_values) + 0.1)
 
                    ax2.set_xlim(0, max(len(vent_values), 10))
                    if vent_values:
                        ax2.set_ylim(min(vent_values) - 0.1, max(vent_values) + 0.1)
 
                    plt.pause(0.001)
 
                sample_idx += 1
                time.sleep(SLEEP_BETWEEN_SAMPLES)
 
        except KeyboardInterrupt:
            print("\nStopping stream...")
 
    plt.ioff()
    plt.show()
 
 
if __name__ == "__main__":
    stream_with_echo_and_plot()

FRAME_LEN   = 105       # 89 param bytes + 16 egram bytes
PARAM_LEN   = 89
EGRAM_LEN   = 16        # 2 doubles (ATR, VENT)
 
# Plot / log settings
MAX_POINTS            = 500    # how many recent samples to show
SLEEP_BETWEEN_SAMPLES = 0.0    # small delay between requests
PRINT_EVERY           = 10     # print frame info every N samples
PLOT_EVERY            = 2      # update plot every N samples
 
 
def build_set_param_frame():
    """
    Build the 91 byte SET_PARAM frame.
    """
 
    # Defaults from your "Default" state
    MODE   = 1
    LRL    = 60
    URL    = 180
    Reaction_Time = 30
    RF     = 16
 
    W_Thres = 0.5
    J_Thres = 1.75
    R_Thres = 3.0
 
    Recovery_Time = 5
    W_MSR  = 80
    J_MSR  = 120
    R_MSR  = 160
 
    W_Hys = 0.5
    J_Hys = 1.75
    R_Hys = 2.75
 
    Atrium_Amp       = 1.0
    ATR_Pulse_Width  = 1
    A_Refractory_Per = 250
    ATR_Sense        = 4.0
 
    Vent_Amp           = 1.0
    Vent_Pulse_Width   = 1
    V_Refractory_Per   = 200
    VENT_Sense         = 4.0
 
    frame = bytearray()
 
    frame.append(CMD_PARAM)        # Rx(1)
    frame.append(SUBCMD_SET_PAR)   # Rx(2)
 
    frame.extend(struct.pack('<B', MODE))
 
    frame.extend(struct.pack('<H', LRL))
    frame.extend(struct.pack('<H', URL))
    frame.extend(struct.pack('<H', Reaction_Time))
    frame.extend(struct.pack('<H', RF))
 
    frame.extend(struct.pack('<d', W_Thres))
    frame.extend(struct.pack('<d', J_Thres))
    frame.extend(struct.pack('<d', R_Thres))
 
    frame.extend(struct.pack('<H', Recovery_Time))
    frame.extend(struct.pack('<H', W_MSR))
    frame.extend(struct.pack('<H', J_MSR))
    frame.extend(struct.pack('<H', R_MSR))
 
    frame.extend(struct.pack('<d', W_Hys))
    frame.extend(struct.pack('<d', J_Hys))
    frame.extend(struct.pack('<d', R_Hys))
 
    frame.extend(struct.pack('<f', Atrium_Amp))
    frame.extend(struct.pack('<H', ATR_Pulse_Width))
    frame.extend(struct.pack('<H', A_Refractory_Per))
    frame.extend(struct.pack('<f', ATR_Sense))
 
    frame.extend(struct.pack('<f', Vent_Amp))
    frame.extend(struct.pack('<H', Vent_Pulse_Width))
    frame.extend(struct.pack('<H', V_Refractory_Per))
    frame.extend(struct.pack('<f', VENT_Sense))
 
    assert len(frame) == 91, "SET frame length is %d, expected 91" % len(frame)
    return bytes(frame)
 
 
def build_recv_only_frame():
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
    assert len(frame) == 91, "RECV frame length is %d, expected 91" % len(frame)
    return bytes(frame)
 
 
def hex_dump(b):
    return ' '.join('%02X' % x for x in b)
 
 
def stream_with_echo_and_plot(port="COM10", baudrate=115200):
    set_frame  = build_set_param_frame()
    recv_frame = build_recv_only_frame()
 
    atr_values = []
    vent_values = []
 
    # Live plot setup
    plt.ion()
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
 
    line_atr, = ax1.plot([], [], label="Atrium")
    ax1.set_title("Atrium Egram")
    ax1.set_ylabel("Amplitude")
    ax1.grid(True)
 
    line_vent, = ax2.plot([], [], label="Ventricle")
    ax2.set_title("Ventricle Egram")
    ax2.set_xlabel("Sample index")
    ax2.set_ylabel("Amplitude")
    ax2.grid(True)
 
    fig.tight_layout()
 
    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.05,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
 
        print("Sending SET_PARAM (00 00 ...) once...")
        ser.write(set_frame)
        ser.flush()
        time.sleep(0.1)
        ser.read(256)   # clear any immediate response
 
        print("Streaming with RECV_ONLY (00 01 ...) (Ctrl+C to stop)...")
 
        sample_idx = 0
 
        try:
            while True:
                # 1) Send RECV_ONLY frame
                ser.write(recv_frame)
                ser.flush()
 
                # 2) Read exactly one frame (up to 105 bytes)
                rx = b""
                t0 = time.time()
                while len(rx) < FRAME_LEN and time.time() - t0 < 0.1:
                    chunk = ser.read(FRAME_LEN - len(rx))
                    if not chunk:
                        break
                    rx += chunk
 
                if len(rx) < FRAME_LEN:
                    # Just skip silently if a frame is missing; do not spam prints
                    time.sleep(SLEEP_BETWEEN_SAMPLES)
                    sample_idx += 1
                    continue
 
                rx_frame = rx[:FRAME_LEN]
                params_echo = rx_frame[:PARAM_LEN]
                egram_bytes = rx_frame[PARAM_LEN:PARAM_LEN + EGRAM_LEN]
 
                # Decode egram doubles
                atr, vent = struct.unpack('<dd', egram_bytes)
                atr_values.append(atr)
                vent_values.append(vent)
 
                if len(atr_values) > MAX_POINTS:
                    atr_values = atr_values[-MAX_POINTS:]
                    vent_values = vent_values[-MAX_POINTS:]
 
                # 3) Print echo and egram only every PRINT_EVERY frames
                if sample_idx % PRINT_EVERY == 0:
                    print("[%d] RX length: %d" % (sample_idx, len(rx_frame)))
                    print("[%d] Echo bytes (89):" % sample_idx)
                    print(hex_dump(params_echo))
                    print("[%d] Egram bytes (16):" % sample_idx)
                    print(hex_dump(egram_bytes))
 
                # 4) Update plots every PLOT_EVERY frames
                if sample_idx % PLOT_EVERY == 0:
                    x = range(len(atr_values))
                    line_atr.set_data(x, atr_values)
                    line_vent.set_data(x, vent_values)
 
                    ax1.set_xlim(0, max(len(atr_values), 10))
                    if atr_values:
                        ax1.set_ylim(min(atr_values) - 0.1, max(atr_values) + 0.1)
 
                    ax2.set_xlim(0, max(len(vent_values), 10))
                    if vent_values:
                        ax2.set_ylim(min(vent_values) - 0.1, max(vent_values) + 0.1)
 
                    plt.pause(0.001)
 
                sample_idx += 1
                time.sleep(SLEEP_BETWEEN_SAMPLES)
 
        except KeyboardInterrupt:
            print("\nStopping stream...")
 
    plt.ioff()
    plt.show()
 
 
if __name__ == "__main__":
    stream_with_echo_and_plot()