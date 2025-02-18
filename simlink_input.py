"""
USB HID input handling for Fanatec ClubSport pedals and Simagic Alpha Mini racing wheel.

Hopefully it'll be easy to adapt to others

I left in the bit to watch for other inputs (buttons, shifter)
"""

import time
import hid

# Constants for the Fanatec ClubSport pedals
PEDAL_VENDOR = 0x0eb7  # Fanatec
PEDALS_ID = 0x1a95  # ClubSport

# Constants for the Simagic Alpha Mini
WHEEL_VENDOR = 0x483  # Simagic
WHEEL_ID = 0x522  # Alpha Mini

class RCInputController:
    def __init__(self, steering_device=None, pedal_device=None):
        self.steering_device = steering_device
        self.pedal_device = pedal_device

        # Moving average filter for smoothing inputs
        self.steering_buffer = [992] * 5
        self.throttle_buffer = [992] * 5
        self.brake_buffer = [0] * 5
        self.filter_size = 5

        # Default values
        self.steering_value = 992
        self.throttle_value = 992
        self.brake_value = 0

        # Limits
        self.min_throttle = 992
        self.max_throttle = 1811
        self.min_brake = 992
        self.max_brake = 172
        self.max_steer = 1811
        self.min_steer = 172

        # Track input changes so we can figure out buttons or other devices
        self.last_other_data = None

    def get_pedals(self, vendor=PEDAL_VENDOR, id=PEDALS_ID):
        """Open a connection to the pedals."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Searching for pedals...")
        try:
            device = hid.device()
            device.open(vendor, id)
            device.set_nonblocking(1)  # Set non-blocking mode
            device.read(64, timeout_ms=1)  # Read once to establish connection
            print(f"Connected to pedals (VID: {vendor}, PID: {id})")
            return device
        except IOError as e:
            print(f"[{timestamp}] Device connection error: {e}")
            return None
        except Exception as e:
            print(f"[{timestamp}] Error: {e}")
            return None

    def handle_pedals(self, device):
        """Handling pedal inputs"""
        throttle = 0
        brake = 0

        try:
            if not device:
                print("No pedals found, reconnecting")
                return None

            data = device.read(64, timeout_ms=1)  # Read pedal
            if data:
                # WARN: Only for my specific pedals, will need to be adapted for others
                throttle = int(data[0])
                brake = int(data[1])

            return throttle, brake

        except Exception as e:
            print(f"Pedal thread error: {e}")
            return None

    def get_steering(self, vendor=WHEEL_VENDOR, id=WHEEL_ID):
        """Open a connection to the wheel"""
        try:
            device = hid.device()
            device.open(vendor, id)
            print(f"Connected to (VID: {vendor}, PID: {id})")
            device.read(64)  # Read once to establish connection
            return device
        except IOError as e:
            print(f"Can't connect to Simagic Alpha Mini: {e}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def handle_steering(self, steering_device):
        """Async handler for steering updates"""
        try:
            data = steering_device.read(64)
            if data:
                # WARN: Only for my specific wheel, will need to be adapted for others
                rough_angle = int(data[2])
                sub_angle = int(data[1])
                steering_angle = int((rough_angle + (sub_angle / 255)) * 10)
            else:
                return False

            other_data = data[3:] if len(data) > 3 else None
            if other_data and other_data != self.last_other_data:
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                print(f"[{timestamp}] Steering Input: {self.last_other_data} -> \n\t\t\t   {other_data}")
                self.last_other_data = other_data

            return steering_angle

        except Exception as e:
            print(f"Steering handler error: {e}")
            if steering_device:
                steering_device.close()
                steering_device = None
                steering_device = self.get_steering()
            return False

    def update_inputs(self):
        """Get control values from RCInputController"""
        steering = 992  # Default to mid-position
        throttle = 992  # Default to mid-position
        brake = 0

        if self.steering_device:
            steering = self.handle_steering(self.steering_device)
            if not steering:
                print("Steering read missing, searching...")
                self.steering_device = None
                return False
        else:
            print("No steering device, searching...")
            self.steering_device = self.get_steering()
            return False

        if self.pedal_device:
            res = self.handle_pedals(self.pedal_device)
            if res is not None:
                throttle, brake = res
            else:
                print("Pedal read missing, searching...")
                self.pedal_device = None
                return False
        else:
            print("No pedals, searching...")
            self.pedal_device = self.get_pedals()
            return False

        #print(f"Steering: {steering}, Throttle: {throttle}, Brake: {brake}")

        # Convert to CRSF values (172-1811 range)
        steering_crsf = int(self.map(steering, 0, 2560, self.min_steer, self.max_steer))
        throttle_crsf = int(self.map(throttle, 0, 256, self.min_throttle, self.max_throttle))  # middle to full, no brakes
        brake_crsf = int(self.map(brake, 0, 256, self.min_brake, self.max_brake))  # middle to full, no brakes

        # Apply moving average filter
        self.steering_buffer = self.steering_buffer[1:] + [steering_crsf]
        self.throttle_buffer = self.throttle_buffer[1:] + [throttle_crsf]
        self.brake_buffer = self.brake_buffer[1:] + [brake_crsf]

        self.steering_value = sum(self.steering_buffer) // self.filter_size
        self.throttle_value = sum(self.throttle_buffer) // self.filter_size
        self.brake_value = sum(self.brake_buffer) // self.filter_size

    @staticmethod
    def map(value, from_low, from_high, to_low, to_high):
        """Map a value from one range to another"""
        return (value - from_low) * (to_high - to_low) // (from_high - from_low) + to_low

if __name__ == "__main__":
    print("Go run the GUI")
    exit()