"""
USB HID input handling for Fanatec ClubSport pedals and Simagic Alpha Mini racing wheel.

Hopefully it'll be easy to adapt to others

I left in the bit to watch for other inputs (buttosn, shifter)

"""


import time
import hid

# Constants for the Fanatec ClubSport pedals
PEDAL_VENDOR = 0x0eb7  # Fanatec
PEDALS_ID = 0x1a95  # ClubSport

# Constants for the Simagic Alpha Mini
WHEEL_VENDOR = 0x483  # Simagic
WHEEL_ID = 0x522  # Alpha Mini

def get_pedals():
    """Open a connection to the Fanatec ClubSport pedals."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Searching for Fanatec ClubSport pedals...")
    try:
        # for device in hid.enumerate():
        #     print(f"Found device: Vendor ID: {hex(device['vendor_id'])}, "
        #         f"Product ID: {hex(device['product_id'])}, Product: {device['product_string']}")
        device = hid.device()
        device.open(PEDAL_VENDOR, PEDALS_ID)
        device.set_nonblocking(1) # Set non-blocking mode
        device.read(64) # Read once to establish connection
        print(f"Connected to Fanatec ClubSport pedals (VID: {PEDAL_VENDOR}, PID: {PEDALS_ID})")
        return device
    except IOError as e:
        print(f"[{timestamp}] Device connection error: {e}")
        return None
    except Exception as e:
        print(f"[{timestamp}]Error: {e}")
        return None

def handle_pedals(device):
    """handling pedal inputs"""
    try:
        #current_time = time.time()
        throttle = None
        brake = None
        if not device:
            print("No pedals found, reconnecting")
            return None

        data = device.read(32, timeout_ms=1)
        #print(f"Pedal data: {data}")
        if data:
            # current_time = time.perf_counter()  # More precise timing

            #  # Track timing and values
            # if self.timing_stats['last_pedal_read'] > 0:
            #     interval = current_time - self.timing_stats['last_pedal_read']
            #     if interval > 0.02:  # Log slow updates
            #         print(f"Slow pedal read: {interval*1000:.1f}ms")
            # self.timing_stats['last_pedal_read'] = current_time

            # Fast path - direct value updates
            throttle = int(data[0])
            brake = int(data[1])

        return throttle, brake

    except Exception as e:
        print(f"Pedal thread error: {e}")
        return None



def get_steering():
    """Open a connection to the Simagic Alpha Mini device."""
    try:
        # for device in hid.enumerate():
        #     print(f"Found device: Vendor ID: {hex(device['vendor_id'])}, "
        #         f"Product ID: {hex(device['product_id'])}, Product: {device['product_string']}")

        #Open the Simagic Alpha Mini racing wheel
        device = hid.device()
        device.open(WHEEL_VENDOR, WHEEL_ID)
        device.set_nonblocking(1) # Set non-blocking mode
        print(f"Connected to Simagic Alpha Mini (VID: {WHEEL_VENDOR}, PID: {WHEEL_ID})")
        device.read(64) # Read once to establish connection
        return device
    except IOError as e:
        print(f"Cant connect to Simagic Alpha Mini: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
    return None


def handle_steering(steering_device):
    """Async handler for steering updates"""
    #last_other_data = None
    try:
        if not steering_device:
            steering_device = get_steering()
            if not steering_device:
                print("No steering wheel found.")
                return False

        data = steering_device.read(64)
        if data:
            rough_angle = int(data[2])
            sub_angle = int(data[1])
            steering_angle =  int((rough_angle + (sub_angle / 255)) * 10)
        else:
            return False

        # Check if any other data changed
        # other_data = data[3:] if len(data) > 3 else None
        # if other_data and other_data != last_other_data:
        #     timestamp = time.strftime("%H:%M:%S", time.localtime())
        #     ##print(f"[{timestamp}] Steering Input: {last_other_data} -> \n\t\t\t   {other_data}")
        #     last_other_data = other_data

        return steering_angle

    except Exception as e:
        print(f"Steering handler error: {e}")
        if steering_device:
            steering_device.close()
            steering_device = None
            steering_device = get_steering()