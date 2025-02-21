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
import serial.tools.list_ports
from simlink_csrf import CRSFDevice, ConnectionState
from simlink_input import RCInputController
from simlink_serial import SerialManager

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
        self.input_controller = RCInputController()

        self.init_ui()

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

        # Status labels
        self.serial_status = tk.StringVar(value='TX USB: Disconnected')
        self.connection_status = tk.StringVar(value='RX Link: N/A')
        self.battery_var = tk.StringVar(value='Battery: --')
        self.link_var = tk.StringVar(value='Link: --')
        self.radio_sync_var = tk.StringVar(value='CRSFShot: --')
        status_frame = ttk.LabelFrame(self.root, text="Status")
        status_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(status_frame, textvariable=self.serial_status).pack(pady=2)
        ttk.Label(status_frame, textvariable=self.connection_status).pack(pady=2)
        ttk.Label(status_frame, textvariable=self.battery_var).pack(pady=2)
        self.link_label = tk.Label(status_frame, textvariable=self.link_var, width=40)
        self.link_label.pack(pady=2, fill='x')
        ttk.Label(status_frame, textvariable=self.radio_sync_var).pack(pady=2)

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
        ttk.Label(brake_frame, text="Max Brake:").pack(side='left', padx=5)
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

        # Channel values display
        self.steering_value = tk.StringVar(value='Steering: --')
        self.throttle_value = tk.StringVar(value='Throttle: --')
        self.brake_value = tk.StringVar(value='Brake: --')

        values_frame = ttk.LabelFrame(self.root, text="Channel Values")
        values_frame.pack(fill='x', padx=5, pady=5)

        # Add steering row with center button
        steering_frame = ttk.Frame(values_frame)
        steering_frame.pack(fill='x', pady=2)
        self.center_btn = ttk.Button(steering_frame, text="Center", command=self.center_steering, width=8)
        self.center_btn.pack(side='left', padx=5)

        ttk.Label(steering_frame, textvariable=self.steering_value).pack(side='left', pady=2)
        ttk.Label(values_frame, textvariable=self.throttle_value).pack(pady=2)
        ttk.Label(values_frame, textvariable=self.brake_value).pack(pady=2)

        # Add charts frame
        charts_frame = ttk.LabelFrame(self.root, text="Input Charts")
        charts_frame.pack(fill='x', padx=5, pady=5)

        # Create throttle chart
        throttle_frame = ttk.Frame(charts_frame)
        throttle_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(throttle_frame, text="Throttle:").pack(side='left', padx=5)
        self.throttle_chart = tk.Canvas(throttle_frame, width=200, height=20, bg='white')
        self.throttle_chart.pack(side='left', fill='x', expand=True, padx=5)

        # Create brake chart
        brake_frame = ttk.Frame(charts_frame)
        brake_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(brake_frame, text="Brake:").pack(side='left', padx=5)
        self.brake_chart = tk.Canvas(brake_frame, width=200, height=20, bg='white')
        self.brake_chart.pack(side='left', fill='x', expand=True, padx=5)

    def refresh_ports(self):
        """Refresh available COM ports"""
        ports = self.serial_manager.get_available_ports()
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])

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
                port = self.port_combo.get()
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

    def center_steering(self):
        """Handle center steering button click"""
        if self.input_controller:
            if self.input_controller.center_steering():
                print("Steering centered successfully")
            else:
                print("Failed to center steering - no device connected")

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
        if self.crsf_tx:
            throttle_range = 1811 - 992
            self.crsf_tx.max_throttle = int(992 + (throttle_range * float(value)/100))
        
        if self.input_controller:
            self.input_controller.max_throttle = self.crsf_tx.max_throttle
        
        self.throttle_value_label.config(text=f"{int(float(value))}%")

    def update_max_brake(self, value):
        """ Update max brake value """
        if self.crsf_tx:
            brake_range = 992 - 172
            self.crsf_tx.max_brake = int(992 - (brake_range * float(value)/100))

        if self.input_controller:
            self.input_controller.max_brake = self.crsf_tx.max_brake
        
        self.brake_value_label.config(text=f"{int(float(value))}%")

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
            else:
                print("No param data")
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
        self.steering_value.set(f'Steering: {self.input_controller.steering_value}')
        self.throttle_value.set(f'Throttle: {self.input_controller.throttle_value}')
        self.brake_value.set(f'Brake: {self.input_controller.brake_value}')

        # Update throttle chart
        self.throttle_chart.delete('all')
        throttle_val = (self.input_controller.throttle_value - 992) / (1811 - 992)  # Normalize to 0-1
        if throttle_val > 0:
            width = self.throttle_chart.winfo_width() * throttle_val
            self.throttle_chart.create_rectangle(
                0, 0, width, self.throttle_chart.winfo_height(),
                fill='green', outline='')

        # Update brake chart
        self.brake_chart.delete('all')
        brake_val = (992 - self.input_controller.brake_value) / (992 - 172)  # Normalize to 0-1
        if brake_val > 0:
            width = self.brake_chart.winfo_width() * brake_val
            self.brake_chart.create_rectangle(
                0, 0, width, self.brake_chart.winfo_height(),
                fill='red', outline='')
        
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
                        self.crsf_tx.steering_value = self.input_controller.steering_value
                        self.crsf_tx.throttle_value = self.input_controller.throttle_value
                        self.crsf_tx.brake_value = self.input_controller.brake_value

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

                except serial.SerialException as e:
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
            time.sleep(0.001) # 1ms sleep to prevent CPU hogging

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
    def on_closing(self):
        """ Close window """
        self.running = False
        if self.crsf_tx:
            self.crsf_tx.serial.close()
        self.root.quit()

if __name__ == '__main__':
    gui = SimLinkGUI()
