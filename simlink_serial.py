"""Serial port manager class for SimLink"""

from typing import List
import serial
import serial.tools.list_ports

class SerialManager:
    """Serial port manager class"""
    def __init__(self):
        self.serial = None
        self.last_ports = []

    def get_available_ports(self) -> List[str]:
        """Get list of available serial ports"""
        return [port.device for port in serial.tools.list_ports.comports()]

    def connect(self, port: str, baud: int = 960000) -> bool:
        """Connect to specified serial port"""
        try:
            if self.serial:
                self.disconnect()
            self.serial = serial.Serial(port, baud, timeout=0.01)
            return True
        except serial.SerialException as e:
            print(f"Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from current port"""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.serial = None

    def is_connected(self) -> bool:
        """Check if serial is connected and open"""
        if not self.serial:
            return False
        try:
            _ = self.serial.in_waiting
            return self.serial.is_open
        except serial.SerialException:
            return False

    def has_new_ports(self) -> bool:
        """Check if available ports have changed"""
        current_ports = self.get_available_ports()
        if current_ports != self.last_ports:
            self.last_ports = current_ports
            return True
        return False

if __name__ == "__main__":
    print("Go run the GUI")
    exit()
