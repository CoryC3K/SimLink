
import time
from enum import Enum, auto
import serial
from typing import Dict, Any
import array as Array
from simlink_input import get_steering, get_pedals, handle_steering, handle_pedals

class ConnectionState(Enum):
    """Connection state for CRSF device"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    DEVICE_INFO = auto()
    PARAMETERS = auto()
    CONNECTED = auto()

class CRSFParser:
    """CRSF packet parser"""
    @staticmethod
    def crc8(data: bytearray) -> int:
        """CRC8 calculation for CRSF packets"""
        crc = 0
        for byte in data[2:]:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0xD5
                else:
                    crc = crc << 1
            crc &= 0xFF
        return crc

    @staticmethod
    def parse_device_info(data: bytearray) -> Dict[str, Any]:
        # Device info
        idx = 3
        name = ""
        while data[idx] != 0:
            name += chr(data[idx])
            idx += 1
        idx += 1

        return {
            "name": name,
            "serial": data[idx:idx+4].decode(),
            "hw_version": int.from_bytes(data[idx+4:idx+8], 'little'),
            "sw_version": int.from_bytes(data[idx+8:idx+12], 'little'),
            "param_count": data[idx+12],
            "protocol_version": data[idx+13]
        }

    @staticmethod
    def parse_parameter(self, data: bytearray) -> Dict[str, Any]:
        # Extended message format: [sync][len][type][dest][src][payload][crc]
        # Payload is [field index] [field chunks remaining] [parent] [type/hidden] [label] [value]
        idx = 5  # Start after header
        payload = data[idx:len(data) - 1] # Skip sync and CRC
        name = ""
        store_data = ""

        param = {
            "index": payload[0],
            "chunk_index": payload[1],  # chunks remaining, but it works as a pkt index too
            "parent": payload[2],       # parent field index in bytes, so you know it's a chunk
            "type": payload[3] & 0x7F,
            "hidden": bool(payload[3] & 0x80),
            "chunk": {}
        }

        if param["chunk_index"] > 0 and param["parent"] == 0:
            # first of new parameter
            self.chunks_expected = param["chunk_index"]

        if param["parent"] == 0:
            # Only non-chunked parameters have name field, undocumented...
            name = ""
            try:
                nm_idx = payload.index(b'\t') + 1
                end_idx = payload.index(b'\x00', nm_idx)
                name = payload[nm_idx:end_idx].decode()
            except ValueError:
                end_idx = len(payload)
                name = "Unknown"

            store_data = payload[end_idx+1:]

            #print(f"RX: \"{name}\":{param['index']} with {self.chunks_expected} chunks: {store_data}")


        if param["type"] == 0x0A:
            # String parameter null terminated
            for i in range(4, len(payload)):
                if payload[i] == b'\x00':
                    break
                store_data += chr(payload[i])
            print(f"String: {store_data}")
        elif store_data == "":
            # Unhandled, store for now
            store_data = payload[2:]

        # search array for null terminator and trim it
        try:
            store_data = store_data[:store_data.index(b'\x00')]
        except ValueError:
            pass

        # Store chunk info
        param["chunk"] = {
            "name": name,
            "value": store_data,
            "complete": param["chunk_index"]
        }

        #print(f"Chunk {param['index']} ({param['chunk_index']}): {param['chunk']}")
        return param

class CRSFDevice:
    """CRSF device class"""
    def __init__(self, port: str = "COM8", baud: int = 921600):
        self.serial = serial.Serial(port, baud, timeout=1)
        self.state = ConnectionState.DISCONNECTED
        self.last_tx = 0
        self.timeout = 0.005  # 50ms timeout
        self.device_info: Dict[str, Any] = {}
        self.parameters: Dict[int, Dict[str, Any]] = {}
        self.param_buff = {}
        self.param_idx = 1
        self.current_chunk = 0
        self.chunk_index = 0
        self.chunks_expected = 0
        self.RC_CHANNELS = [0] * 16
        self.RC_CHANNELS[0] = 1300 # Steering turn so I know it's alive
        self.steering_device = None
        self.throttle_device = None
        # CRSF packets
        self.ping_packet = bytearray([0xEE, 0x04, 0x28, 0x00]) # CRSF_FRAMETYPE_DEVICE_PING [sync] [len] [type] [00 EA = extended] [crc8]
        self.ping_packet.append(CRSFParser.crc8(self.ping_packet) ^ 1 << 1)  # CRC8
        self.ping_packet.append(0x7F)
        self.battery_data = {
            'voltage': 0.0,
            'current': 0.0, 
            'capacity': 0,
            'remaining': 0
        }
        self.link_stats = {}
        self.radio_sync = {'interval': 0, 'phase': 0}

    def map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def handle_battery(self, data):
        """Parse battery telemetry data"""
        payload = data[3:-1]  # Skip address, length, type, and CRC

        voltage = int.from_bytes(payload[0:2], byteorder='big') / 10.0  # dV to V
        current = int.from_bytes(payload[2:4], byteorder='big') / 10.0  # dA to A
        capacity = int.from_bytes(payload[4:7], byteorder='big')        # mAh
        remaining = payload[7]                                          # %

        self.battery_data = {
            'voltage': voltage,
            'current': current,
            'capacity': capacity,
            'remaining': remaining
        }

        print(f"Battery: {voltage:.1f}V {current:.1f}A {capacity}mAh {remaining}%")

    def handle_link_stats(self, data):
        """Parse CRSF link statistics"""
        payload = data[3:-1]  # Skip address, length, type, and CRC
        
        self.link_stats = {
            'uplink_rssi_1': -payload[0],         # Convert to negative dBm
            'uplink_rssi_2': -payload[1],
            'uplink_link_quality': payload[2],     # Percentage
            'uplink_snr': payload[3],             # dB 
            'active_antenna': payload[4],          # 0=ant1, 1=ant2
            'rf_mode': payload[5],                # RF mode enum
            'uplink_tx_power': payload[6],        # TX power enum
            'downlink_rssi': -payload[7],         # Convert to negative dBm
            'downlink_link_quality': payload[8],   # Percentage
            'downlink_snr': payload[9]            # dB
        }
        
        print(f"Link Stats: RSSI:{-payload[0]}dBm LQ:{payload[2]}% SNR:{payload[3]}dB")

    def handle_radio_id(self, data):
        """Parse CRSF radio ID packet"""

        ### WARN ###
        # This is ignoring anything that's not CRSFShot
        # un-comment else to fix it if needed

        payload = data[3:-1]  # Skip address, length, type, and CRC
        
        subtype = payload[0]
        if subtype == 0x10:  # CRSF_FRAMETYPE_OPENTX_SYNC # CRSFShot
            interval = int.from_bytes(payload[1:5], byteorder='big') / 10  # us
            phase = int.from_bytes(payload[5:9], byteorder='big')
            
            self.radio_sync = {
                'interval': interval,
                'phase': phase
            }
            print(f"Radio Sync: {interval}us phase:{phase}")
        # else:
        #     print(f"Unhandled radio ID subtype: {subtype:02X}")




    def update_rc_channels(self) -> None:
        """Read and transmit RC channels in CRSF protocol format"""
        # Frame: [0xEE, length, type, payload..., crc8]
        # RC packet type = 0x16
        # 16 channels * 11 bits = 22 bytes of payload
        # Total frame length = 24 bytes (22 payload + 2 header)

        packet = bytearray([0xC8, 0x18, 0x16])  # Header: addr, length, type

        # Pack 16 channels of 11-bit values into 22 bytes
        # Each channel should be between 172 and 1811 for CRSF protocol
        #channels = [992] * 16  # Default to mid-position (172-1811 range)

        buffer = 0
        bits_written = 0
        bytes_written = 0

        # Get control values from RCInputController
        
        if self.steering_device:
            steering = handle_steering(self.steering_device)
            if not steering:
                self.steering_device = None
                self.steering_device = get_steering()
                return False
        else:
            self.steering_device = get_steering()
            return False
        
        if self.throttle_device:
            res = handle_pedals(self.throttle_device)
            if res[1] is None:
                return False
            throttle, brake = res
        else:
            print("No throttle device, searching...")
            self.throttle_device = get_pedals()
            return False

        #brake = self.controls.brake
        #print(f"Steering: {steering}, Throttle: {throttle}, Brake: {brake}")

        # Convert to CRSF values (172-1811 range)
        #  // Conversion of CRSF channel value <-> us
        # crsf = 992 + (8/5 * (us - 1500))
        # us = 1500 + (5/8 * (crsf - 992))
        steering_crsf = int(self.map(steering, 0, 2560, 172, 1811))
        throttle_crsf = int(self.map(throttle, 0, 256, 992, 1811))
        #steering_crsf = int(172 + (steering + 1) * 819.5)  # Map -1 to 1 to 172-1811
        #throttle_crsf = int(172 + throttle * 1639)  # Map 0 to 1 to 172-1811
        #brake_crsf = int(172 + brake * 1639)  # Map 0 to 1 to 172-1811

        # Set CRSF values
        self.RC_CHANNELS[0] = steering_crsf
        self.RC_CHANNELS[1] = throttle_crsf

        # Pack 11-bit channel values into bytes
        for ch_num, value in enumerate(self.RC_CHANNELS):
            buffer |= (value << bits_written)
            bits_written += 11

            # Write full bytes when we have them
            while bits_written >= 8:
                packet.append(buffer & 0xFF)
                buffer >>= 8
                bits_written -= 8
                bytes_written += 1

        # Write remaining bits if any
        if bits_written > 0:
            packet.append(buffer & 0xFF)

        # Add CRC
        packet.append(CRSFParser.crc8(packet))

        # Send frame
        self.serial.write(packet)
        self.last_tx = time.time()

        #print("TXRC:" + " ".join([f"{b:02X}" for b in packet]))


    def request_parameter(self, param_idx: int, chunk_idx: int = 0) -> None:
        """Request parameter from CRSF device"""
        if self.state != ConnectionState.PARAMETERS:
            return
        if chunk_idx < 0:
            print("Invalid chunk index: ", chunk_idx)
            chunk_idx = 0
        packet = bytearray([0xEE, 0x06, 0x2C, 0xEE, 0xEA, param_idx, chunk_idx])
        packet.append(CRSFParser.crc8(packet))
        self.serial.write(packet)
        #print(f"TX: Requesting param {param_idx} chunk {chunk_idx}: {' '.join([f'{b:02X}' for b in packet])}")

    def handle_parameter(self, param_data):
        """ Handle parameter data coming in """

        param = CRSFParser.parse_parameter(self, param_data)

        idx = param["index"]
        chunk = param["chunk"]
        chunk_index = param["chunk_index"]

        if param["parent"] == 0 and chunk["complete"] == 0 and idx not in self.param_buff:
            # Non-chunked parameter
            self.parameters[idx] = chunk["value"]
            print(f"Parameter {idx}: {chunk['name']} = {chunk['value']}")
            if self.state == ConnectionState.PARAMETERS:
                if idx + 1 < self.device_info["param_count"]:
                    self.request_parameter(idx + 1, 0)
            return

        if idx not in self.param_buff:
            total_chunks = chunk_index + 1
            self.param_buff[idx] = {
                'total_chunks': total_chunks,
                'chunks': [None] * total_chunks
            }

        param_entry = self.param_buff[idx]

        if chunk['value']:
            param_entry['chunks'][chunk_index] = chunk['value']

        # Check if all positions have data
        if all(chunk is not None for chunk in param_entry['chunks']):
            combined_data = bytearray()
            for chunk in reversed(param_entry['chunks']):
                combined_data.extend(chunk)

            self.parameters[idx] = combined_data
            del self.param_buff[idx]

            try:
                print(f"Parameter {idx}: {combined_data.decode().strip()}")
            except UnicodeDecodeError:
                print(f"Parameter {idx}: {combined_data}")

            if self.state == ConnectionState.PARAMETERS:
                if idx + 1 < self.device_info["param_count"]:
                    self.request_parameter(idx + 1, 0)
        else:
            # Request any missing chunk, but just one at a time
            for i, chunk in enumerate(reversed(param_entry['chunks'])):
                if chunk is None:
                    self.request_parameter(idx, i)
                    break

    def handle_rc_RX(self, data: bytearray) -> None:
        """ Handle RC channels packet """
        # Frame: [0xEE, length, type, payload..., crc8]
        # RC packet type = 0x16
        # 16 channels * 11 bits = 22 bytes of payload
        # Total frame length = 24 bytes (22 payload + 2 header)

        # Extract channels from payload
        channels = []
        for i in range(3, 25, 2):
            channels.append((data[i] << 8) | data[i + 1])

        print("RXRC:" + " ".join([f"{b:04X}" for b in channels]))


    def handle_rx(self) -> None:
        # Pkt format
        # [sync] [len] [type] [payload] [crc8]
        # Extended packet format
        # [sync] [len] [type] [[ext dest] [ext src] [payload]] [crc8]

        if self.serial.in_waiting < 5:
            return

        data = self.serial.read(self.serial.in_waiting)
        #print("RX:", " ".join([f"{b:02X}" for b in data]))

        if (len(data) != data[1] + 2) or len(data) > 64: # CRSF hard limit of 64 bytes
            # Truncate data to expected length
            if len(data) > data[1] + 2:
                data = data[:data[1] + 2]
            else:
                print(f"Invalid packet length for: {' '.join([f'{b:02X}' for b in data])}")
                return

        # Verify CRC
        frame_length = data[1]
        frame = data[:frame_length + 2]  # Include sync byte and length byte

        # CRC is calculated over all bytes except CRC itself
        crc = CRSFParser.crc8(frame[:-1])
        if crc != frame[-1]:
            print(f"CRC mismatch: {crc:02X} != {frame[-1]:02X}")
            return

        # Verify sync byte is device address or:
        # Serial sync byte: 0xC8; Broadcast device address: 0x00;
        # 0xEA Remote Control
        # 0xEC R/C Receiver / Crossfire Rx
        # 0xEE R/C Transmitter Module / Crossfire Tx
        if data[0] not in [0x00, 0xEA, 0x0C]:
            print(f"Unknown Sync type: {data[0]:02X}")
            return
        
        if data[2] == 0x08: # CRSF_FRAMETYPE_BATTERY_SENSOR
            self.handle_battery(data)
        elif data[2] == 0x14: # CRSF_FRAMETYPE_LINK_STATISTICS
            self.handle_link_stats(data)
        elif data[2] == 0x16: # RC_CHANNELS_PACKED
            self.handle_rc_RX(data)

        elif data[2] == 0x29:  # Device Info
            if self.state == ConnectionState.CONNECTING:
                self.state = ConnectionState.PARAMETERS
            self.device_info = CRSFParser.parse_device_info(data)
            print(f"Device Info: {self.device_info}")

        elif data[2] == 0x2B:  # Parameter
            # Payload format
            # [field index] [field chunks remaining] [parent] [type/hidden] [label] [value]
            self.handle_parameter(data)
        elif data[2] == 0x3A: #CRSF_FRAMETYPE_RADIO_ID 
            self.handle_radio_id(data)
        else:
            print(f"Unhandled frame type: {data[2]:02X}")


    def update(self) -> None:
        now = time.time()

        if now - self.last_tx > self.timeout:
            if self.state == ConnectionState.DISCONNECTED or self.state == ConnectionState.CONNECTING:
                self.serial.write(self.ping_packet)
                #print("TXPing:" + " ".join([f"{b:02X}" for b in self.ping_packet]))
                self.state = ConnectionState.CONNECTING
                self.last_tx = now

            elif self.state == ConnectionState.PARAMETERS:
                self.request_parameter(self.param_idx, self.current_chunk)
                self.last_tx = now

                # Check if parameter is complete
                if self.param_idx in self.parameters:
                    # Parameter complete, move to next parameter
                    self.param_idx += 1
                    self.current_chunk = 0
                    self.chunks_expected = 0

                if self.param_idx >= self.device_info.get("param_count", 0):
                    print("All parameters requested, connected")
                    self.state = ConnectionState.CONNECTED

            elif self.state == ConnectionState.CONNECTED:
                # print axis data
                # CRSF_FRAMETYPE_RC_CHANNELS_PACKED [sync] 0x18 0x16 [channel00:11] [channel01:11] ... [channel15:11] [crc8]
                #ExpressLRS: Adds a status byte to control the arm status when transmitting channels from the handset to the TX module. If the packet payload length is 0x18, the status byte is not present and ExpressLRS will use ch4 to trigger "armed" behavior. A payload length 0x19 indicates the last byte contains information to trigger armed behavior (0=disarmed, 1=armed). ExpressLRS >=4.0.0 / EdgeTX v2.11.
                self.update_rc_channels()

        self.handle_rx()
        time.sleep(0.001)  # 1ms loop time

    def run(self) -> None:
        try:
            while True:
                self.update()
                time.sleep(0.001)  # 1ms loop time
        except KeyboardInterrupt:
            self.serial.close()
            print("\nClosed CRSF connection")

if __name__ == "__main__":
    device = CRSFDevice()
    device.run()