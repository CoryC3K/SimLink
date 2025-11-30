import time
import hid

class InputDevice:
    """Base class for input devices."""
    def __init__(self, vendor_id, product_id):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device = None
        self.connected = False

    def connect(self):
        """Connect to the device."""
        try:
            self.device = hid.device()
            self.device.open(self.vendor_id, self.product_id)
            self.device.set_nonblocking(1)
            self.device.read(64, timeout_ms=1)  # Initial read to establish connection
            self.connected = True
            print(f"Connected to device (VID: {self.vendor_id}, PID: {self.product_id})")
        except IOError as e:
            print(f"Failed to connect to device (VID: {self.vendor_id}, PID: {self.product_id}): {e}")
            self.device = None
            self.connected = False
            return None

    def read_data(self, size=64):
        """Read data from the device."""
        if self.device:
            try:
                return self.device.read(size, timeout_ms=1)
            except Exception as e:
                print(f"Error reading device: {e}")
        return None

    def disconnect(self):
        """Disconnect the device."""
        if self.device:
            self.device.close()
            self.device = None
            self.connected = False

    def handle_input(self):
        """Handle input data (to be implemented by subclasses)."""
        raise NotImplementedError


class FanatecPedals(InputDevice):
    """Fanatec ClubSport Pedals."""
    def handle_input(self):
        data = self.read_data()
        if data:
            throttle = int(data[0])
            brake = int(data[1])
            #print(f"Fanatec data: {data} -> Throttle: {throttle}, Brake: {brake}")
            return throttle, brake
        return None, None


class SimagicWheel(InputDevice):
    """Simagic Alpha Mini Wheel."""
    def handle_input(self):
        data = self.read_data()
        if data:
            rough_angle = int(data[2])
            sub_angle = int(data[1])
            steering_angle = int((rough_angle + (sub_angle / 255)) * 10)
            #print(f"Simagic data: {data} -> Steering Angle: {steering_angle}")
            return steering_angle
        return None


class RadiomasterJoystick(InputDevice):
    """Radiomaster Pocket Joystick."""
    def handle_input(self):
        data = self.read_data(128)
        if data:
            # Map joystick axes to throttle, brake, and steering
            throttle = (int(data[5]) + int(data[6]) * 256 - 1024) // 4 + 128
            brake = int(data[1])
            steering = int(data[3])
            steering_rev = int(data[4])
            steering += 256 * steering_rev
            #print(f"RM data: {data} -> T:{throttle} B:{brake} S:{steering}")
            return throttle, brake, steering
        return None, None, None


class GenericHIDDevice(InputDevice):
    """Generic HID device with user-defined mapping."""
    def __init__(self, vendor_id, product_id, mapping=None):
        super().__init__(vendor_id, product_id)
        self.mapping = mapping or {}  # e.g. {'throttle': {'index': 2, 'min': 0, 'max': 255}, ...}

    def handle_input(self):
        data = self.read_data(128)
        if not data or not self.mapping:
            return None, None, None
        def get_val(name):
            info = self.mapping.get(name)
            if info is None:
                return None
            val = int(data[info['index']])
            # Optionally scale to 0-255 or 0-2560 here if needed
            return val
        throttle = get_val('throttle')
        brake = get_val('brake')
        steering = get_val('steering')
        return throttle, brake, steering


class InputController:
    """Controller to manage multiple input devices and allow external (GUI) input with smoothing."""
    def __init__(self):
        self.devices = []
        self.steering_value = 2560/2 # Center position in wheel degrees
        self.throttle_value = 0   # 0-255 throttle
        self.brake_value = 0
        self.max_throttle = 255
        self.max_brake = 255

        # Rolling buffer for smoothing/filtering
        self.filter_size = 5
        self.steering_buffer = [992] * self.filter_size
        self.throttle_buffer = [0] * self.filter_size
        self.brake_buffer = [0] * self.filter_size

        # Mapping ranges (adjust as needed)
        self.steer_range = 200 # maximum deviation from center in wheel degrees
        self.steering_center_offset = 0

    def map(self, x, in_min, in_max, out_min, out_max):
        """Map x from one range to another."""
        return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min


    def update_inputs(self):
        """Update inputs from all registered devices and apply smoothing.

            Note: It is assumed the handle_input methods return values in raw ranges: 
            Steering: 0-2560
            Throttle: 0-255
            Brake: 0-255
        """
        # Load current values in case the input misses a read
        steering, throttle, brake = self.steering_value, self.throttle_value, self.brake_value

        for input_device in self.devices:
            if isinstance(input_device, FanatecPedals):
                t, b = input_device.handle_input()
                if t is not None and b is not None:
                    throttle, brake = t, b
            elif isinstance(input_device, SimagicWheel):
                s = input_device.handle_input()
                if s is not None:
                    steering = s
            elif isinstance(input_device, RadiomasterJoystick):
                t, b, s = input_device.handle_input()
                if t is not None:
                    throttle = t
                if b is not None:
                    brake = b
                if s is not None:
                    steering = s

        #print(f"Raw Inputs - Steering: {steering}, Throttle: {throttle}, Brake: {brake}")

        # Apply moving average filter to raw values first
        self.steering_buffer = self.steering_buffer[1:] + [steering]
        self.throttle_buffer = self.throttle_buffer[1:] + [throttle]
        self.brake_buffer = self.brake_buffer[1:] + [brake]

        # Get filtered raw values
        steering_avg = sum(self.steering_buffer) // self.filter_size
        throttle_avg = sum(self.throttle_buffer) // self.filter_size
        brake_avg = sum(self.brake_buffer) // self.filter_size

        # Store the values
        self.steering_value = steering_avg + self.steering_center_offset
        self.throttle_value = throttle_avg
        self.brake_value = brake_avg

        #print(f"Updated Inputs - Steering: {self.steering_value}, Throttle: {self.throttle_value}, Brake: {self.brake_value}")

    def register_device(self, vendor_id, product_id):
        """Register a new input device."""
        # (FanatecPedals, 0x0eb7, 0x1a95),
        # (SimagicWheel, 0x483, 0x522),
        # (RadiomasterJoystick, 0x1209, 0x4f54),

        if isinstance(vendor_id, str):
            vendor_id = int(vendor_id, 16) if vendor_id.startswith("0x") else int(vendor_id)
        if isinstance(product_id, str):
            product_id = int(product_id, 16) if product_id.startswith("0x") else int(product_id)

        print(f"Registering device VID: {vendor_id}, PID: {product_id}")
        if vendor_id == 0xeb7:
            # Fanatec Pedals
            device = FanatecPedals(vendor_id, product_id)
        elif vendor_id == 0x483:
            # Simagic Wheel
            device = SimagicWheel(vendor_id, product_id)
        elif vendor_id == 0x1209:
            # Radiomaster Joystick
            device = RadiomasterJoystick(vendor_id, product_id)
        else:
            # Try to load mapping for unknown devices
            mapping = self.load_device_mapping(vendor_id, product_id)
            if mapping:
                device = GenericHIDDevice(vendor_id, product_id, mapping)
                device.connect()
                self.devices.append(device)
                print(f"Generic device registered: VID: {vendor_id}, PID: {product_id}, mapping: {mapping}")
            else:
                print(f"Unknown device (VID: {vendor_id}, PID: {product_id}), please calibrate.")
                # Optionally trigger calibration wizard here
                return
        device.connect()
        self.devices.append(device)
        print(f"Device registered: VID: {vendor_id}, PID: {product_id}")
        print(f"devices list: {self.devices}")
        self.update_inputs()

    def load_device_mapping(self, vendor_id, product_id):
        import json
        try:
            with open("simlink.json", "r") as f:
                settings = json.load(f)
            key = f"{vendor_id:04x}:{product_id:04x}"
            return settings.get("mappings", {}).get(key)
        except Exception:
            return None

    def print_inputs(self):
        """Print the current input values."""
        src = "InputController"

        print(f"[{src}] Steering: {self.steering_value}, Throttle: {self.throttle_value}, Brake: {self.brake_value}")


if __name__ == "__main__":
    controller = InputController()

    # Register devices
    fanatec_pedals = FanatecPedals(vendor_id=0x0eb7, product_id=0x1a95)
    simagic_wheel = SimagicWheel(vendor_id=0x483, product_id=0x522)
    radiomaster_joystick = RadiomasterJoystick(vendor_id=0x1209, product_id=0x4f54)

    fanatec_pedals.connect()
    simagic_wheel.connect()
    radiomaster_joystick.connect()
    controller.devices.extend([fanatec_pedals, simagic_wheel, radiomaster_joystick])

    try:
        while True:
            controller.update_inputs()
            controller.print_inputs()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Exiting...")
        for device in controller.devices:
            device.disconnect()