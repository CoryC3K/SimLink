#!/usr/bin/env python3
#*-* coding: utf-8 *-*

"""
SimLink CRSF GUI
"""

import time
import threading
import queue
import tkinter as tk
from tkinter import ttk
from simlink_csrf import CRSFDevice, ConnectionState
from simlink_input_HID import InputController, FanatecPedals, SimagicWheel, RadiomasterJoystick
from simlink_serial import SerialManager
import hid
import json
import os

class SimLinkGUI:
    """ SimLink CRSF GUI """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('SimLink CRSF TX GUI')
        self.queue = queue.Queue()
        self.param_queue = queue.Queue()
        self.running = True
        self.crsf_tx = None
        self.serial_manager = SerialManager()
        self.tx_queue = queue.Queue()  # Queue for passing values to the thread

        # Initialize InputController
        self.input_controller = InputController()
        #self.init_input_devices()

        self.init_ui()
        self.load_settings()  # Load settings after UI is initialized

        # Start background data update thread
        self.update_thread = threading.Thread(target=self.controller_loop)
        self.update_thread.daemon = True
        self.update_thread.start()

        # Start periodic serial status check
        self.check_serial_status()

        # Start GUI loop in main thread
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_gui()
        self.root.mainloop()

    def init_ui(self):
        """ Initialize GUI elements """
        conn_frame = ttk.Frame(self.root)
        conn_frame.pack(fill='x', padx=5, pady=5)

        # Parameters frame
        self.params_frame = ttk.LabelFrame(self.root, text="Parameters")
        self.params_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)

        self.params_text = tk.Text(
            self.params_frame,
            width=40,
            height=10,
            state='disabled',
            wrap='word')
        self.params_text.pack(fill='both', expand=True, padx=5, pady=5)

        self.update_params_btn = ttk.Button(self.params_frame, text='Update Parameters', command=self.update_parameters)
        self.update_params_btn.pack(pady=5)

        # Serial connection frame
        self.port_combo = ttk.Combobox(conn_frame)
        self.refresh_ports()
        self.port_combo.pack(side='left', expand=True, fill='x', padx=(0,5))

        self.connect_btn = ttk.Button(conn_frame, text='Connect', command=self.toggle_connection)
        self.connect_btn.pack(side='right')

        # HID Device selectors
        hid_frame = ttk.LabelFrame(self.root, text="HID Device Selection")
        hid_frame.pack(fill='x', padx=5, pady=5)

        # Steering device selector (label above)
        ttk.Label(hid_frame, text="Steering Device:").pack(anchor='w', padx=5)
        self.steering_device_combo = ttk.Combobox(hid_frame, state="readonly")
        self.steering_device_combo.pack(fill='x', padx=5, pady=(0, 5))

        # Throttle/Brake device selector (label above)
        ttk.Label(hid_frame, text="Throttle/Brake Device:").pack(anchor='w', padx=5)
        self.throttle_device_combo = ttk.Combobox(hid_frame, state="readonly")
        self.throttle_device_combo.pack(fill='x', padx=5, pady=(0, 5))

        self.refresh_hid_devices()
        self.steering_device_combo.bind("<<ComboboxSelected>>", self.on_hid_selection)
        self.throttle_device_combo.bind("<<ComboboxSelected>>", self.on_hid_selection)

        # Status labels
        self.serial_status = tk.StringVar(value='TX USB: Disconnected')
        self.connection_status = tk.StringVar(value='RX Link: N/A')
        self.battery_var = tk.StringVar(value='Battery: --')
        self.link_var = tk.StringVar(value='Link: --')
        self.radio_sync_var = tk.StringVar(value='CRSFShot: --')
        status_frame = ttk.LabelFrame(self.root, text="Status")
        status_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(status_frame, textvariable=self.serial_status, anchor='w').pack(pady=2, fill='x')
        ttk.Label(status_frame, textvariable=self.connection_status, anchor='w').pack(pady=2, fill='x')
        ttk.Label(status_frame, textvariable=self.battery_var, anchor='w').pack(pady=2, fill='x')
        self.link_label = tk.Label(status_frame, textvariable=self.link_var, width=40, anchor='w')
        self.link_label.pack(pady=2, fill='x')
        ttk.Label(status_frame, textvariable=self.radio_sync_var, anchor='w').pack(pady=2, fill='x')

        # Control Frame
        control_frame = ttk.LabelFrame(self.root, text="Control Settings")
        control_frame.pack(fill='x', padx=5, pady=5)

        # Max Throttle Frame
        throttle_frame = ttk.Frame(control_frame)
        throttle_frame.pack(fill='x', padx=5)
        ttk.Label(throttle_frame, text="Max Throttle:").pack(side='left', padx=5)
        self.throttle_value_label = ttk.Label(throttle_frame, text="50%")
        self.throttle_value_label.pack(side='right', padx=5)
        self.throttle_scale = ttk.Scale(
            throttle_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_throttle
        )
        self.throttle_scale.set(50)  # Default 50%
        self.throttle_scale.pack(fill='x', expand=True, padx=5)

        # Max Brake Frame
        brake_frame = ttk.Frame(control_frame)
        brake_frame.pack(fill='x', padx=5)
        ttk.Label(brake_frame, text="Max Brake:  ").pack(side='left', padx=5) # Padded to match 'throttle'
        self.brake_value_label = ttk.Label(brake_frame, text="50%")
        self.brake_value_label.pack(side='right', padx=5)
        self.brake_scale = ttk.Scale(
            brake_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_brake
        )
        self.brake_scale.set(50)  # Default 50%
        self.brake_scale.pack(fill='x', expand=True, padx=5)

        # Max Steering Frame
        max_steer_frame = ttk.Frame(control_frame)
        max_steer_frame.pack(fill='x', padx=5)
        ttk.Label(max_steer_frame, text="Max Steer:  ").pack(side='left', padx=5) # Padded to match 'throttle'
        self.max_steer_label = ttk.Label(max_steer_frame, text="50%")
        self.max_steer_label.pack(side='right', padx=5)
        self.max_steer_scale = ttk.Scale(
            max_steer_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_steer
        )
        self.max_steer_scale.set(50)  # Default 50%
        self.max_steer_scale.pack(fill='x', expand=True, padx=5)

        # Channel values display
        self.steer_val_disp = tk.StringVar(value='Steering: --')
        self.throttle_val_disp = tk.StringVar(value='Throttle: --')
        self.brake_val_disp = tk.StringVar(value='   Brake: --')

        values_frame = ttk.LabelFrame(self.root, text="Channel Values")
        values_frame.pack(side='left', fill='x', padx=5, pady=5)

        # # Add steering row with center button
        #steering_frame = ttk.Frame(values_frame)
        #steering_frame.pack(fill='x', pady=2)
        # self.center_btn = ttk.Button(steering_frame, text="Center", command=self.center_steering, width=8)
        # self.center_btn.pack(side='left', padx=5)

        # Create a new frame for throttle and brake labels to stack them vertically
        values_inner_frame = ttk.Frame(values_frame)
        values_inner_frame.pack(fill='x', pady=2)
        ttk.Label(values_inner_frame, textvariable=self.steer_val_disp).pack(fill='x', pady=2)
        ttk.Label(values_inner_frame, textvariable=self.throttle_val_disp).pack(fill='x', pady=2)
        ttk.Label(values_inner_frame, textvariable=self.brake_val_disp).pack(fill='x', pady=2)

        # Add charts frame
        charts_frame = ttk.LabelFrame(self.root, text="Input Charts")
        charts_frame.pack(fill='x', padx=5, pady=5)

        label_width = 10  # Adjust as needed for your font

        # Throttle chart
        throttle_frame = ttk.Frame(charts_frame)
        throttle_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(throttle_frame, text="Throttle:", width=label_width, anchor='e').pack(side='left')
        self.throttle_chart = tk.Canvas(throttle_frame, width=200, height=20, bg='white')
        self.throttle_chart.pack(side='left', fill='x', expand=True, padx=5)
        


        # Brake chart
        brake_frame = ttk.Frame(charts_frame)
        brake_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(brake_frame, text="Brake:", width=label_width, anchor='e').pack(side='left')
        self.brake_chart = tk.Canvas(brake_frame, width=200, height=20, bg='white')
        self.brake_chart.pack(side='left', fill='x', expand=True, padx=5)

        # Steering chart
        steering_frame = ttk.Frame(charts_frame)
        steering_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(steering_frame, text="Steering:", width=label_width, anchor='e').pack(side='left')
        self.steering_chart = tk.Canvas(steering_frame, width=200, height=20, bg='white')
        self.steering_chart.pack(side='left', fill='x', expand=True, padx=5)

    def refresh_ports(self):
        """Refresh available COM ports with descriptions"""
        # Get list of (port, description) tuples from serial_manager
        ports = self.serial_manager.get_available_ports()
        # Try to get descriptions if available
        try:
            # If your SerialManager returns a list of serial.tools.list_ports.ListPortInfo objects:
            import serial.tools.list_ports
            port_list = list(serial.tools.list_ports.comports())
            port_display = [f"{p.device} - {p.description}" for p in port_list]
            port_values = [p.device for p in port_list]
            self.port_combo['values'] = port_display
            if port_display:
                self.port_combo.set(port_display[0])
            self._port_map = dict(zip(port_display, port_values))  # Save mapping for later use
        except Exception:
            # Fallback: just show port names
            self.port_combo['values'] = ports
            if ports:
                self.port_combo.set(ports[0])
            self._port_map = {p: p for p in ports}

    def check_serial_status(self):
        """Check if device still connected"""
        if self.serial_manager.has_new_ports():
            self.refresh_ports()

        if self.crsf_tx and not self.serial_manager.is_connected():
            self.crsf_tx = None
            self.connect_btn['text'] = 'Connect'
            self.serial_status.set('TX USB: Disconnected')

        self.root.after(1000, self.check_serial_status)

    def toggle_connection(self):
        """Connect or disconnect CRSF TX device"""
        if not self.crsf_tx:
            try:
                port_display = self.port_combo.get()
                # Use the mapping to get the actual port name
                port = self._port_map.get(port_display, port_display)
                print(f"USB Connecting to {port}")
                if self.serial_manager.connect(port):
                    print(f"USB Connected to {port}")
                    self.crsf_tx = CRSFDevice(self.serial_manager.serial)
                    self.crsf_tx.tx_state = ConnectionState.CONNECTING
                    self.connect_btn['text'] = 'Disconnect'
                    self.serial_status.set('USB TX: Connecting')
            except Exception as e:
                self.serial_status.set(f'USB TX Error: {str(e)}')
                print(f"USB Error: {e}")
        else:
            self.serial_manager.disconnect()
            self.crsf_tx = None
            self.connect_btn['text'] = 'Connect'
            self.serial_status.set('USB TX: Disconnected')

    #def center_steering(self):
        # """Handle center steering button click"""
        # if self.input_controller:
        #     if self.input_controller.center_steering():
        #         print("Steering centered successfully")
        #     else:
        #         print("Failed to center steering - no device connected")

    def update_link_color(self, link_quality: int):
        """ Update link quality color """
        if link_quality > 100:
            link_quality = 100
        elif link_quality < 0:
            link_quality = 0

        red = int((100 - link_quality) * 2.55)
        green = int(link_quality * 2.55)
        color = f'#{red:02x}{green:02x}00'

        self.link_label.config(bg=color)

    def update_parameters_display(self, param):
        """ Update parameters display """

        self.params_text.config(state='normal')

        # Check if the parameter data is valid
        if not isinstance(param, dict):
            print(f"Invalid parameter data: {param}")
            return
        if "parameter_number" not in param or param["parameter_number"] is None:
            print(f"Invalid parameter number: {param}")
            return
        if 'chunk_header' not in param or "name" not in param["chunk_header"]:
            print(f"Invalid parameter name: {param}")
            return
        if 'chunk' not in param:
            print(f"Invalid parameter chunk: {param}")
            return
        
        out_str = f'{param["parameter_number"]}:{param["chunk_header"]["name"]} = '
        #print(f"Param: {param['parameter_number']} = {val_idx}\n{param['chunk']['options']}")
        #print(f"Param: {param['parameter_number']} = {param['chunk']['options'][val_idx]}")
        if 'options' in param["chunk"] and 'value' in param["chunk"]:
            val_idx = int(param["chunk"]["value"])
            out_str += f"\t{param['chunk']['options'][val_idx]}\n"

        # Clear the text box if this is the first parameter

        if param["parameter_number"] == 1:
            self.params_text.delete(1.0, tk.END)

        self.params_text.insert(tk.END, out_str)
        self.params_text.config(state='disabled')

    def update_parameters(self):
        """ Request parameters update """
        if self.crsf_tx:
            self.crsf_tx.parameters = {}
            self.crsf_tx.param_idx = 0
            self.crsf_tx.current_chunk = 0
            self.crsf_tx.tx_state = ConnectionState.PARAMETERS
            self.crsf_tx.request_parameter(0)

    def update_max_throttle(self, value):
        """ Update max throttle value """
        """ NOTE: This only caps the OUTPUT value, to scale the input controller's full range """
        if self.crsf_tx:
            throttle_range = 1811 - 992 # Max to Min
            self.crsf_tx.max_throttle = int(992 + (throttle_range * float(value)/100))
            print(f"Set max throttle to {self.crsf_tx.max_throttle}")
        self.throttle_value_label.config(text=f"{int(float(value))}%")

    def update_max_brake(self, value):
        """ Update max brake value """
        """ NOTE: This only caps the OUTPUT value, to scale the input controller's full range """
        if self.crsf_tx:
            brake_range = 992 - 172
            self.crsf_tx.max_brake = int(992 - (brake_range * float(value)/100))
            print(f"Set max brake to {self.crsf_tx.max_brake}")
        self.brake_value_label.config(text=f"{int(float(value))}%")

    def update_max_steer(self, value):
        """ Update max steering value """
        """ NOTE: This only caps the OUTPUT value, to scale the input controller's full range """
        if self.input_controller:
            steer_range = 2560 // 2
            self.input_controller.steer_range = int(steer_range * float(value)/100)
            print(f"Set max steer to {self.input_controller.steer_range}")
        self.max_steer_label.config(text=f"{int(float(value))}%")


    def update_gui(self):
        """
        Main UI update loop runs in foreground, calls itself every 100ms
        """

        # Check for new data in queue
        try:
            q_data = self.queue.get(block=False)
            if q_data and 'update_status' in q_data:
                self.connection_status.set(q_data[1]['status'])
                self.battery_var.set(q_data[1]['battery'])
                self.link_var.set(q_data[1]['link'])
        except queue.Empty:
            pass

        try:
            p_data = self.param_queue.get(block=False)
            if p_data:
                for p in p_data:
                    if p is not None:
                        self.update_parameters_display(p)
        except queue.Empty:
            pass

        # Update channel values
        self.update_input_display()

        # Update RX Status
        if self.crsf_tx is not None:
            # Update TX Status
            self.serial_status.set(f"TX Link: {self.crsf_tx.tx_state.name}")

            # Update RX Status
            self.connection_status.set(f'RX Link: {self.crsf_tx.rx_state.name}')

            # Update battery
            batt = self.crsf_tx.battery_data
            self.battery_var.set(
                    f'Battery: {batt["voltage"]:.1f}V {batt["current"]:.1f}A {batt["remaining"]}%'
                )

            # Update link quality
            stats = self.crsf_tx.link_stats
            if stats:
                self.link_var.set(
                    f'Link: RSSI:{stats.get("uplink_rssi_1",0)}dBm LQ:{stats.get("uplink_link_quality",0)}%'
                )
                # Update link quality color
                lq = stats.get("uplink_link_quality", 0)
                self.update_link_color(lq)

            # Update CRSFShot data
            radio_data = self.crsf_tx.radio_sync
            if radio_data:
                self.radio_sync_var.set(f'CRSFShot:{radio_data["interval"]}us phase:{radio_data["phase"]}')

            # Update inputs display
            self.update_input_display()

        else:
            self.serial_status.set('USB TX: Disconnected')
            self.connection_status.set('RX Link: N/A')
            self.battery_var.set('Battery: --')
            self.link_var.set('Link: --')
            self.update_link_color(0)

        self.root.after(10, self.update_gui) # Update every 1ms

    def update_input_display(self):
        """ Update input display """
        if self.crsf_tx is not None:
            self.steer_val_disp.set(f'Steering: {self.crsf_tx.steering_value}')
            self.throttle_val_disp.set(f'Throttle: {self.crsf_tx.throttle_value}')
            self.brake_val_disp.set(f'Brake: {self.crsf_tx.brake_value}')

        # Update throttle chart
        self.throttle_chart.delete('all')
        throttle_val = self.input_controller.throttle_value / 256  # Normalize to 0-1
        if throttle_val > 0:
            width = self.throttle_chart.winfo_width() * throttle_val
            self.throttle_chart.create_rectangle(
                0, 0, width, self.throttle_chart.winfo_height(),
                fill='green', outline='')
        # Draw value at end of bar
        self.throttle_chart.create_text(
            self.throttle_chart.winfo_width() - 5, self.throttle_chart.winfo_height() // 2,
            anchor='e',
            text=f"{self.input_controller.throttle_value:.0f}",
            fill='black'
        )

        # Update brake chart
        self.brake_chart.delete('all')
        brake_val = self.input_controller.brake_value / 256  # Normalize to 0-1
        if brake_val > 0:
            width = self.brake_chart.winfo_width() * brake_val
            self.brake_chart.create_rectangle(
                0, 0, width, self.brake_chart.winfo_height(),
                fill='red', outline='')
        # Draw value at end of bar
        self.brake_chart.create_text(
            self.brake_chart.winfo_width() - 5, self.brake_chart.winfo_height() // 2,
            anchor='e',
            text=f"{self.input_controller.brake_value:.0f}",
            fill='black'
        )
        
        # Update steering chart
        self.steering_chart.delete('all')
        steer_val = self.input_controller.steering_value / 2560  # Normalize to 0-1
        # Draw center line
        center_x = self.steering_chart.winfo_width() / 2 - (self.input_controller.steering_center_offset * self.steering_chart.winfo_width())
        self.steering_chart.create_line(
            center_x, 0, center_x, self.steering_chart.winfo_height(),
            fill='black', dash=(2, 4))
        if steer_val > 0:
            width = self.steering_chart.winfo_width() * steer_val
            self.steering_chart.create_rectangle(
                center_x, 0, width, self.steering_chart.winfo_height(),
                fill='blue', outline='')
        # Draw value at end of bar
        self.steering_chart.create_text(
            self.steering_chart.winfo_width() - 5, self.steering_chart.winfo_height() // 2,
            anchor='e',
            text=f"{self.input_controller.steering_value:.0f}",
            fill='black'
        )

    def refresh_hid_devices(self):
        """Scan and list all HID devices for selection."""
        devices = hid.enumerate()
        device_list = []
        self.hid_device_map = {}
        for d in devices:
            desc = f"{d['product_string']} (VID: {hex(d['vendor_id'])}, PID: {hex(d['product_id'])})"
            device_list.append(desc)
            self.hid_device_map[desc] = (d['vendor_id'], d['product_id'])
        self.steering_device_combo['values'] = device_list
        self.throttle_device_combo['values'] = device_list
        if device_list:
            self.steering_device_combo.current(0)
            self.throttle_device_combo.current(0)

    def on_hid_selection(self, event=None):
        """Register selected HID devices for steering and throttle/brake."""
        # Remove all devices first
        self.input_controller.devices = []

        # Steering device
        steering_desc = self.steering_device_combo.get()
        if steering_desc in self.hid_device_map:
            vid, pid = self.hid_device_map[steering_desc]
            print(f"Registering steering device VID: {vid}, PID: {pid}")
            self.input_controller.register_device(vid, pid)

        # Throttle/Brake device
        throttle_desc = self.throttle_device_combo.get()
        if throttle_desc in self.hid_device_map and throttle_desc != steering_desc:
            vid, pid = self.hid_device_map[throttle_desc]
            print(f"Registering throttle/brake device VID: {vid}, PID: {pid}")
            self.input_controller.register_device(vid, pid)

    def controller_loop(self):
        """
        Update loop runs in background, main GUI thread is in foreground

        Warn: Don't do UI updates here, do them above
        """

        while self.running:
            # Tell the input controller to get new values
            # Always run it when connected to allow UI updates
            if self.input_controller is not None:
                self.input_controller.update_inputs()

            if self.crsf_tx is not None:
                try:
                    # Update the CRSF device with the new values
                    if self.input_controller is not None:
                        # Map input_controller values to CRSF ranges
                        steer = self.input_controller.steering_value
                        throttle = self.input_controller.throttle_value
                        brake = self.input_controller.brake_value

                        # Map to CRSF ranges
                        # 172-1811 is steering with 992 center
                        steer_crsf = int(self.input_controller.map(steer,\
                             0, 2560, 992 - self.input_controller.steer_range, 992 + self.input_controller.steer_range))
                        
                        throttle_crsf = int(self.input_controller.map(throttle, 0, 255, 992, self.crsf_tx.max_throttle))
                        brake_crsf = int(self.input_controller.map(brake, 0, 255, 992, self.crsf_tx.max_brake))

                        self.crsf_tx.steering_value = steer_crsf
                        self.crsf_tx.throttle_value = throttle_crsf
                        self.crsf_tx.brake_value = brake_crsf

                    # Call a read/write/update of the serial device
                    self.crsf_tx.update()
                    # Decode the parameters
                    decoded_params = []
                    for param in self.crsf_tx.parameters.values():
                        decoded_param = self.decode_param(param)
                        decoded_params.append(decoded_param)

                    # Put parameter updates into the queue
                    while self.param_queue.qsize() > 1:
                        try:
                            self.param_queue.get_nowait()
                        except queue.Empty:
                            break

                    self.param_queue.put(decoded_params, block=False)
                    #print(f"tx Param Queue: {self.param_queue.qsize()}")

                except Exception as e:
                    self.crsf_tx = None
                    self.serial_status.set('USB: Disconnected')
                    self.queue.put(('update_status', {
                        'status': f'USB Error: {str(e)}',
                        'battery': 'Battery: --',
                        'link': 'Link: --'
                    }))

                except queue.Full:
                    print("Queue full, skipping update")

            else:
                if time.time() % 1 < 1e-3: # Refresh every second
                    self.queue.empty()
                    self.queue.put(('update_status', {
                        'status': 'TX Disconnected',
                        'battery': 'Battery: --',
                        'link': 'Link: --'
                    }))
                    print("No CRSF TX connected")
            time.sleep(0.001)

    def decode_param(self, param):
        """ Decode a single parameter """
        # Assuming param is a dictionary with the necessary fields
        if not isinstance(param, dict):
            return None
        if "parameter_number" not in param or param["parameter_number"] is None:
            return None
        if 'chunk_header' not in param or "name" not in param["chunk_header"]:
            return None
        if 'chunk' not in param:
            return None
        if 'options' not in param["chunk"] or 'value' not in param["chunk"]:
            return None

        return param

    def save_settings(self):
        """Save GUI settings to simlink.json"""
        settings = {
            "steering_device": self.steering_device_combo.get(),
            "throttle_device": self.throttle_device_combo.get(),
            "com_port": self.port_combo.get(),
            "throttle_scale": self.throttle_scale.get(),
            "brake_scale": self.brake_scale.get(),
            "max_steer_scale": self.max_steer_scale.get()
        }
        with open("simlink.json", "w") as f:
            json.dump(settings, f, indent=2)
        print("Settings saved to simlink.json")

    def load_settings(self):
        """Load GUI settings from simlink.json"""
        if not os.path.exists("simlink.json"):
            return
        try:
            with open("simlink.json", "r") as f:
                settings = json.load(f)
            # Set values if present
            if "steering_device" in settings and settings["steering_device"] in self.steering_device_combo['values']:
                self.steering_device_combo.set(settings["steering_device"])
            if "throttle_device" in settings and settings["throttle_device"] in self.throttle_device_combo['values']:
                self.throttle_device_combo.set(settings["throttle_device"])
            if "com_port" in settings and settings["com_port"] in self.port_combo['values']:
                self.port_combo.set(settings["com_port"])
            if "throttle_scale" in settings:
                self.throttle_scale.set(settings["throttle_scale"])
            if "brake_scale" in settings:
                self.brake_scale.set(settings["brake_scale"])
            if "max_steer_scale" in settings:
                self.max_steer_scale.set(settings["max_steer_scale"])
            print("Settings loaded from simlink.json")
        except Exception as e:
            print(f"Failed to load settings: {e}")

    def on_closing(self):
        """ Close window """
        self.save_settings()
        self.running = False
        if self.crsf_tx:
            self.crsf_tx.serial.close()
        self.root.quit()

if __name__ == '__main__':
    gui = SimLinkGUI()
