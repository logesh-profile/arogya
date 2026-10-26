"""
ESP32 Physical Display Bridge
=============================
Provides a robust, non-blocking USB Serial connection to an external ESP32 microcontroller.
Streams lightweight emotion tags (EMO:...) and speaking state markers (SPK:1, SPK:0) over 115200 baud.
Runs seamlessly on both local development machines and cloud environments (e.g. Render) with graceful degradation.
"""

import time
import queue
import threading
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    serial = None
    HAS_SERIAL = False


class ESP32Bridge:
    def __init__(self, baud: int = 115200):
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.q = queue.Queue(maxsize=30)
        self.last_connected_port: Optional[str] = None
        self._logged_no_port = False

        if HAS_SERIAL:
            threading.Thread(target=self._run, daemon=True, name="ESP32-Serial-Worker").start()

    def send(self, line: str):
        """
        Enqueues an opcode line to send to the ESP32 (e.g. 'EMO:caring', 'SPK:1').
        Non-blocking: drops message if queue is full rather than stalling audio/LLM.
        """
        if not HAS_SERIAL:
            return
        clean_line = line.strip()
        if not clean_line:
            return
        try:
            self.q.put_nowait(clean_line)
        except queue.Full:
            pass

    def _connect(self):
        if not HAS_SERIAL:
            return
        try:
            ports = list(serial.tools.list_ports.comports())
            if not ports:
                if not self._logged_no_port:
                    print("[*] ESP32 Bridge: No physical COM ports detected. Running in cloud/mock mode.")
                    self._logged_no_port = True
                return

            for p in ports:
                d = (p.description or "").lower()
                dev = (p.device or "").lower()
                # Matches CH340, CP2102, FTDI, USB-Serial, ESP32 on Windows/Linux/macOS
                if any(k in d or k in dev for k in ("cp210", "ch340", "usb-serial", "esp32", "usb to uart", "ttyusb", "ttyacm")):
                    try:
                        s = serial.Serial()
                        s.port = p.device
                        s.baudrate = self.baud
                        s.timeout = 0.1
                        s.dtr = False
                        s.rts = False
                        s.open()
                        self.ser = s
                        self.last_connected_port = p.device
                        self._logged_no_port = False
                        print(f"[✓] Connected to ESP32 Display on {p.device} at {self.baud} baud")
                        # Send initial idle state
                        self.send("EMO:thinking")
                        return
                    except Exception as ce:
                        # Port might be busy (e.g. Arduino Serial Monitor open)
                        pass
        except Exception as e:
            pass

    def is_connected(self) -> bool:
        """Returns True if physical serial connection to ESP32 is actively open."""
        return bool(self.ser and self.ser.is_open)

    def get_status(self) -> dict:
        """Returns diagnostic status of ESP32 connection."""
        return {
            "connected": self.is_connected(),
            "port": self.last_connected_port,
            "baud": self.baud,
            "queue_pending": self.q.qsize(),
            "has_pyserial": HAS_SERIAL
        }

    def _run(self):
        while True:
            if not (self.ser and self.ser.is_open):
                self._connect()
                if not (self.ser and self.ser.is_open):
                    time.sleep(3)
                    continue
            try:
                line = self.q.get(timeout=1.0)
                if self.ser and self.ser.is_open:
                    msg = (line + "\n").encode("utf-8")
                    self.ser.write(msg)
                    self.ser.flush()
                    print(f"[*] ESP32 Serial -> {line}")
            except queue.Empty:
                pass
            except Exception as ex:
                print(f"[!] ESP32 Serial connection dropped: {ex}")
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(2)


# Singleton bridge instance
_global_bridge: Optional[ESP32Bridge] = None

def get_esp32_bridge() -> ESP32Bridge:
    global _global_bridge
    if _global_bridge is None:
        _global_bridge = ESP32Bridge(baud=115200)
    return _global_bridge
