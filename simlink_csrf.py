""" CRSF protocol implementation for ExpressLRS devices """

import time
from enum import Enum, auto
from typing import Dict, Any
import serial

class ConnectionState(Enum):
    """Connection state for CRSF device"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    DEVICE_INFO = auto()
    PARAMETERS = auto()
    CONNECTED = auto()

class paramType(Enum):
    UINT8 = 0  # deprecated
    INT8 = 1  # deprecated
    UINT16 = 2  # deprecated
    INT16 = 3  # deprecated
    UINT32 = 4  # deprecated
    INT32 = 5  # deprecated
    FLOAT = 8
    TEXT_SELECTION = 9
    STRING = 10
    FOLDER = 11
    INFO = 12
    COMMAND = 13
    OUT_OF_RANGE = 127

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
        """Device info"""
        idx = 0
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
    def parse_param_float(data: bytearray) -> Dict[str, Any]:
        """
        Parse the float type from a parameter packet
        """
        idx = 0
        value = int.from_bytes(data[idx:idx + 4], 'little', signed=True)
        idx += 4
        min_value = int.from_bytes(data[idx:idx + 4], 'little', signed=True)
        idx += 4
        max_value = int.from_bytes(data[idx:idx + 4], 'little', signed=True)
        idx += 4
        default_value = int.from_bytes(data[idx:idx + 4], 'little', signed=True)
        idx += 4
        decimal_point = data[idx]
        idx += 1
        step_size = int.from_bytes(data[idx:idx + 4], 'little', signed=True)
        idx += 4

        # Parse the null-terminated unit string
        unit = ""
        while data[idx] != 0:
            unit += chr(data[idx])
            idx += 1

        return {
            "value": value / (10 ** decimal_point),
            "min": min_value / (10 ** decimal_point),
            "max": max_value / (10 ** decimal_point),
            "default": default_value / (10 ** decimal_point),
            "decimal_point": decimal_point,
            "step_size": step_size / (10 ** decimal_point),
            "unit": unit
        }

    @staticmethod
    def parse_param_text_selection(data: bytearray) -> Dict[str, Any]:
        """
        Parse the text selection type from a parameter packet
        """
        options = ""
        value = 0
        min_value = 0
        max_value = 0
        default_value = 0
        unit = ""
        idx = 0

        if data[idx]:
            # Parse the null-terminated options string
            while idx-1 < len(data) and data[idx] and data[idx] != 0:
                options += chr(data[idx])
                idx += 1

            # Move past options, then parse value, min, max, default, and unit
            idx += 1
            value = data[idx]
            idx += 1
            min_value = data[idx]
            idx += 1
            max_value = data[idx]
            idx += 1
            default_value = data[idx]
            idx += 1
            unit = data[idx:].decode()

        return {
            "options": options.split(';'),
            "value": value,
            "min": min_value,
            "max": max_value,
            "default": default_value,
            "unit": unit
        }

    @staticmethod
    def parse_param_string(data: bytearray) -> Dict[str, Any]:
        """
        Parse the string type from a parameter packet
        """
        value = ""
        idx = 0
        while data[idx] != 0:
            value += chr(data[idx])
            idx += 1
        idx += 1
        string_max_length = data[idx]

        return {
            "value": value,
            "string_max_length": string_max_length
        }

    @staticmethod
    def parse_param_folder(data: bytearray) -> Dict[str, Any]:
        """
        Parse the folder type from a parameter packet
        """
        list_of_children = ""
        idx = 0
        while data[idx] != 0:
            list_of_children += chr(data[idx])
            idx += 1
        idx += 1

        return {
            "list_of_children": list_of_children.split(';')
        }
    
    @staticmethod
    def parse_param_info(data: bytearray) -> Dict[str, Any]:
        """
        Parse parameter info, just a null-term string
        """
        info = ""
        idx = 0
        while data[idx] != 0:
            info += chr(data[idx])
            idx += 1
        return info
    
    @staticmethod
    def parse_param_command(data: bytearray) -> Dict[str, Any]:
        """
        Parse parameter command, just a null-term string
        """
        status = data[0]
        timeout = data[1]
        info = ""
        idx = 2

        while data[idx] != 0:
            info += chr(data[idx])
            idx += 1

        return {
            "status": status,
            "timeout": timeout,
            "info": info
        }

    @staticmethod
    def parse_common_param_fields(data: bytearray) -> Dict[str, Any]:
        """
        Parse common parameter fields: parent_folder, data_type, and name
        """
        idx = 0
        parent_folder = data[idx]

        if parent_folder == '\t':
            parent_folder = 0

        idx += 1
        data_type = data[idx]
        idx += 1

        # Parse the null-terminated name string
        name = ""
        while data[idx] != 0:
            name += chr(data[idx])
            idx += 1

        idx += 1  # Move past the null terminator

        return {
            "parent_folder": parent_folder,
            "type": data_type,
            "name": name,
            "idx": idx  # Return the current index for further parsing
        }

    def parse_specific_param_fields(self, param_info: Dict[str, Any], payload: bytearray) -> Dict[str, Any]:
        """
        Parse parameter chunk data
        Follow the spec, start by type.
        Payload is ONLY the assembled chunk data, not the header
        """
        param_payload = payload[param_info["chunk_header"]["idx"]:]
        pkt_type = param_info["chunk_header"]["type"]

        if pkt_type < paramType.FLOAT.value:
            print(f"warn{param_info['parameter_number']}: depreciated param type: {paramType(pkt_type).name}")
            #pkt_type = paramType.FLOAT.value
            param_info["chunk"] = param_payload

        if pkt_type == paramType.FLOAT.value:
            param_info["chunk"] = CRSFParser.parse_param_float(param_payload)

        if pkt_type == paramType.TEXT_SELECTION.value:
            param_info["chunk"] = CRSFParser.parse_param_text_selection(param_payload)

        if pkt_type == paramType.STRING.value:
            param_info["chunk"] = CRSFParser.parse_param_string(param_payload)

        #if pkt_type == paramType.FOLDER.value:
            # Weird issue where the folder has no list of children
            #param_info["chunk"] = CRSFParser.parse_param_folder(param_payload)

        if pkt_type == paramType.OUT_OF_RANGE.value:
            print(f"Out of range parameter: {param_info['parameter_number']}")
            return param_info
        return param_info

class CRSFDevice:
    """CRSF device class"""
    # Note: ELRS TX defaults to 960000 baud, RX defaults to 420000/400000 baud
    def __init__(self, serial_obj: serial.Serial):
        self.tx_state= ConnectionState.DISCONNECTED
        self.rx_state= ConnectionState.DISCONNECTED
        self.serial = serial_obj
        self.last_tx = 0
        self.timeout = 0.005  # 50ms timeout
        self.device_info: Dict[str, Any] = {}
        self.parameters: Dict[int, Dict[str, Any]] = {}
        self.param_buff = {}
        self.param_idx = 1
        self.current_chunk = 0
        self.chunk_index = 0
        self.RC_CHANNELS = [0] * 16
        self.RC_CHANNELS[0] = 1300 # Steering turn so I know it's alive
        self.steering_device = None
        self.throttle_device = None
        self.max_throttle = int(1811 - (1811-992)*.5) # 100% throttle is 1811, 0% is 992 1811-992 = 819
        self.max_brake = int(992 - (992-172) * .5) # 100% brake is 172, 0% is 992
        # CRSF packets
        self.ping_packet = bytearray([0xEE, 0x04, 0x28, 0x00]) # CRSF_FRAMETYPE_DEVICE_PING [sync] [len] [type] [00 = broadcast] [crc8]
        self.ping_packet.append(CRSFParser.crc8(self.ping_packet) ^ 1 << 1)  # CRC8
        self.ping_packet.append(0x7F)
        self.battery_data = {
            'voltage': 0.0,
            'current': 0.0,
            'capacity': 0,
            'remaining': 0
        }
        self.link_stats = {
            'last_update': 0
        }
        self.radio_sync = {'interval': 0, 'phase': 0}
        self.filter_size = 5

        self.throttle_buffer = [992] * self.filter_size
        self.brake_buffer = [992] * self.filter_size
        self.steering_buffer = [992] * self.filter_size

        self.steering_value = 0
        self.throttle_value = 0
        self.brake_value = 0

    def map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def crsf_battery_sensor(self, data):
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

    def request_link_stats(self):
        """Request link quality stats from CRSF device"""
        self.request_parameter(0x14, 0)  # CRSF_FRAMETYPE_LINK_STATISTICS

        # packet = bytearray([0xEE, 0x06, 0x2C, 0xEE, 0xEA, 0x14, 0x00])  # CRSF_FRAMETYPE_LINK_STATISTICS [sync] [len] [type] [00 EA = extended] [crc8]
        # packet.append(CRSFParser.crc8(packet))
        # self.serial.write(packet)
        print("Requested link stats")

    def crsf_link_statistics(self, data):
        """Parse CRSF link statistics"""
        payload = data[3:-1]  # Skip address, length, type, and CRC

        self.link_stats = {
            'last_update': time.time(),
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

        if self.link_stats['uplink_link_quality'] > 0:
            self.rx_state= ConnectionState.CONNECTED
        elif self.link_stats['uplink_link_quality'] == 0:
            self.rx_state= ConnectionState.DISCONNECTED

        #print(f"Link Stats: RSSI:{-payload[0]}dBm LQ:{payload[2]}% SNR:{payload[3]}dB")

    def crsf_radio_id(self, data):
        """Parse CRSF radio ID packet"""

        ### WARN ###
        # This is ignoring anything that's not CRSFShot
        # un-comment else to fix it if needed

        payload = data[5:-1]  # Skip address, length, type, and CRC

        subtype = payload[0]
        if subtype == 0x10:  # CRSF_FRAMETYPE_OPENTX_SYNC # CRSFShot
            interval = int.from_bytes(payload[1:4], byteorder='big') / 10  # us
            phase = int.from_bytes(payload[5:-1], byteorder='big', signed=True)  # us
            #interval = payload[1:5]
            #phase = payload[5:-1]

            self.radio_sync = {
                'interval': interval,
                'phase': phase
            }
            #print(f"payload: {payload} Radio Sync: {interval}us phase:{phase}")
        else:
            print(f"Unhandled radio ID subtype: {subtype:02X}")

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

        # CRSF_FRAMETYPE_RC_CHANNELS_PACKED
        # [sync] 0x18 0x16 [channel00:11] [channel01:11] ... [channel15:11] [crc8]
        # ExpressLRS: Adds a status byte to control the arm status when transmitting channels
        # from the handset to the TX module. If the packet payload length is 0x18, the status
        # byte is not present and ExpressLRS will use ch4 to trigger "armed" behavior.
        # A payload length 0x19 indicates the last byte contains information to trigger
        # armed behavior (0=disarmed, 1=armed). ExpressLRS >=4.0.0 / EdgeTX v2.11.

        buffer = 0
        bits_written = 0
        bytes_written = 0

        # Early exit if serial is closed
        if not self.serial.is_open:
            return False

        # Set CRSF values
        self.RC_CHANNELS[0] = self.steering_value
        if self.brake_value < 992:
            self.RC_CHANNELS[1] = self.brake_value
        else:
            self.RC_CHANNELS[1] = self.throttle_value # - brake_crsf  # Throttle + Brake

        if not self.serial.is_open:
            # Don't bother going further if serial is closed
            return False

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
        """ Request parameter from CRSF device"""

        if chunk_idx < 0:
            print("Invalid chunk index: ", chunk_idx)
            chunk_idx = 0
        packet = bytearray([0xEE, 0x06, 0x2C, 0xEE, 0xEA, param_idx, chunk_idx])
        packet.append(CRSFParser.crc8(packet))
        self.serial.write(packet)
        #print(f"TX: Requesting param {param_idx} chunk {chunk_idx}:{' '.join([f'{b:02X}' for b in packet])}")

    def crsf_parameter_settings(self, raw_param_data):
        """ Handler for CRSF-spec parameter data coming in """
        # Parameters are special, they may be 'chunked', so it's a bit more complex

        # Extract parameter data and raw payload (may be chunked)
        #
        # sync = raw_param_data[0]
        # len = raw_param_data[1]
        # type = raw_param_data[2]
        # dest_addr = raw_param_data[3]
        # origin_addr = raw_param_data[4]
        param_num = raw_param_data[5]
        chunk_index = raw_param_data[6] # also chunks remaining
        payload_chunk = raw_param_data[7:-1] # Payload, skip CRC which is already verified

        # Check to see if we've got data in the buffer
        if param_num not in self.param_buff:
            self.param_buff[param_num] = {
                'total_chunks': chunk_index + 1,
                'chunks': [None] * (chunk_index + 1)
            }

        # Easy reference the current param's buffer slot,
        # and load the right chunk into it's own indexed slot
        chunk_store = self.param_buff[param_num]
        chunk_store['chunks'][chunk_index] = payload_chunk

        # Check if all positions have data
        if all(chunk is not None for chunk in chunk_store['chunks']):
            combined_data = bytearray()
            for chunk in reversed(chunk_store['chunks']):
                combined_data.extend(chunk)

            self.parameters[param_num] = combined_data

            try:
                print(f"Param {param_num} raw chunk: {self.parameters[param_num]}")
                print(f"Param {param_num} raw cbuff: {self.param_buff[param_num]['chunks']}")
                # Try and parse the parameter into it's own types, all types share first 3 fields
                # so you can identify them
                param_info = {}
                param_info["parameter_number"] = param_num
                param_info["parameter_chunks_remaining"] = chunk_index
                param_info["chunk_header"] = CRSFParser.parse_common_param_fields(combined_data)
                print(f"Param {param_num} header: {param_info['chunk_header']}")
                param_info = CRSFParser.parse_specific_param_fields(self, param_info, combined_data)
                self.parameters[param_num] = param_info

                print(f"Param {param_num} out: {self.parameters[param_num]}")
            except Exception as e:
                print(f"Error parsing parameter {param_num}: {e}")
                print(f"Raw buff: {self.param_buff[param_num]}")
                return

            # Remove the buffer for the next update of this one
            del self.param_buff[param_num]

            # Auto-request the next parameter if we're refreshing
            # if it's empty!!!
            if self.tx_state== ConnectionState.PARAMETERS:
                if (param_num + 1) in self.parameters.keys():
                    if param_num + 1 < self.device_info["param_count"]:
                        self.request_parameter(param_num + 1, 0)

        else:
            # Request any missing chunk, but just one at a time
            # (because they might not all be there or in order)
            for i, chunk in enumerate(reversed(chunk_store['chunks'])):
                if chunk is None:
                    self.request_parameter(param_num, i)
                    break

    def crsf_rc_channels_packed(self, data: bytearray) -> None:
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
        """Handle incoming CRSF data"""
        # Pkt format
        # [sync] [len] [type] [payload] [crc8]
        # Extended packet format
        # [sync] [len] [type] [[ext dest] [ext src] [payload]] [crc8]

        # This breaks a lot doing a read, hence try/catch
        try:
            if not self.serial or not self.serial.is_open:
                return

            if self.serial.in_waiting < 5:
                return

            raw_data = self.serial.read(self.serial.in_waiting)
            #print("RX:", " ".join([f"{b:02X}" for b in raw_data]))
            # Mutable copy
            data = bytearray(raw_data)

        except serial.SerialException as e:
            print(f"Serial error: {e}")
            return
        except OSError as e:
            print(f"OS error: {e}")
            return

        # Now that we're safe...

        rcvd_len = len(data) - 2 # Exclude sync byte and length byte
        if rcvd_len < 1: # Frame size must be at least 1 byte
            print("Invalid packet, no data")
            return

        # Verify sync byte is device address or:
        # Serial sync byte: 0xC8; Broadcast device address: 0x00;
        # 0xEA Remote Control
        # 0xEC R/C Receiver / Crossfire Rx
        # 0xEE R/C Transmitter Module / Crossfire Tx
        if data[0] not in [0x00, 0xEA, 0x0C, 0xC8]:
            print(f"Unknown Sync type: {data[0]:02X}, raw: {' '.join([f'{b:02X}' for b in data])}")
            return

        # Frame length:
        # number of bytes in the frame excluding Sync byte
        # and Frame Length (basically, entire frame size -2)

        expected_len = data[1] # Frame length
        if rcvd_len != expected_len or len(data) > 64: # CRSF hard limit of 64 bytes
            # Truncate data to expected length
            if len(data) > expected_len + 2:
                data = data[:expected_len + 2]
            else:
                #print(f"ERR: len[{len(data)}<{expected_len}]: {' '.join([f'{b:02X}' for b in data])}")
                return

        # CRC is calculated over all bytes except CRC itself
        crc = CRSFParser.crc8(data[:-1])
        if crc != data[-1]:
            #print(f"CRC mismatch: {crc:02X} != {data[-1]:02X}")
            return

        try:
            store = data[2]
        except IndexError:
            #print(f"Index error[2]: {data}")
            return
        
        # CRC, length, sync checks all done, now we can parse the packet

        if data[2] == 0x08: # CRSF_FRAMETYPE_BATTERY_SENSOR
            self.crsf_battery_sensor(data)
        elif data[2] == 0x14: # CRSF_FRAMETYPE_LINK_STATISTICS
            self.crsf_link_statistics(data)
        elif data[2] == 0x16: # RC_CHANNELS_PACKED
            self.crsf_rc_channels_packed(data)

        # Above 0x27 is extended frametype, different packet format!!!

        elif data[2] == 0x29:  # Device Info, also ping response
            # If we're in connecting state, a ping response means we're connected
            if self.tx_state== ConnectionState.CONNECTING:
                self.tx_state= ConnectionState.PARAMETERS
            self.device_info = CRSFParser.parse_device_info(data)
        elif data[2] == 0x2B:  # Parameter data
            self.crsf_parameter_settings(data)
        elif data[2] == 0x3A: #CRSF_FRAMETYPE_RADIO_ID
            self.crsf_radio_id(data)
        else:
            print(f"Unhandled frame type: {data[2]:02X}")


    def update(self) -> None:
        """

        Main update loop for CRSF device
        Handles TX and RX states

        """
        now = time.time()

        try:
            if self.tx_state == ConnectionState.CONNECTED and (not self.serial or not self.serial.is_open):
                self.tx_state= ConnectionState.DISCONNECTED
                print("Error: Serial disconnected while connected")
                return
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            return

        if now - self.last_tx > self.timeout:
            if (self.tx_state == ConnectionState.DISCONNECTED) or (self.tx_state == ConnectionState.CONNECTING):
                self.serial.write(self.ping_packet)
                #print("TXPing:" + " ".join([f"{b:02X}" for b in self.ping_packet]))
                self.tx_state = ConnectionState.CONNECTING
                self.last_tx = now

            elif self.tx_state == ConnectionState.PARAMETERS:
                self.request_parameter(self.param_idx, self.current_chunk)
                self.last_tx = now

                # Check if parameter is complete
                if self.param_idx in self.parameters:
                    # Parameter complete, move to next parameter
                    self.param_idx += 1
                    self.current_chunk = 0

                if self.param_idx >= self.device_info.get("param_count", 1):
                    print("All parameters requested, connected")
                    self.tx_state = ConnectionState.CONNECTED

            elif self.tx_state == ConnectionState.CONNECTED:
                # While TX is connected...

                #if self.rx_state == ConnectionState.CONNECTED:
                    # If we've got an RX connected too
                if now - self.link_stats['last_update'] > 5: # Haven't gotten an update in 5s
                    self.request_link_stats()
                    self.link_stats['last_update'] = now
                    self.link_stats['uplink_link_quality'] = 0
                    self.link_stats['uplink_rssi_1'] = 0
                    self.rx_state = ConnectionState.DISCONNECTED

                # Update channels to force server-style connection?
                if not self.update_rc_channels():
                    # If we return false, update the time anyway so we don't loop lag
                    self.last_tx = now

        if self.tx_state != ConnectionState.DISCONNECTED:
            self.handle_rx()

if __name__ == "__main__":
    print("Go run the GUI")
    exit()

