#/usr/bin/env python3
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
from simlink_serial import SerialManager
from simlink_input import RCInputController

class SimLinkGUI:
    """ SimLink CRSF GUI """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('SimLink CRSF TX GUI')
        self.queue = queue.Queue()
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

        self.params_text = tk.Text(self.params_frame, height=10, state='disabled', wrap='word')
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

        # Max Throttle Slider
        ttk.Label(control_frame, text="Max Throttle:").pack(padx=5)
        self.throttle_scale = ttk.Scale(
            control_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_throttle
        )
        self.throttle_scale.set(50)  # Default 50%
        self.throttle_scale.pack(fill='x', expand=True, padx=5)

        # Max Brake Slider
        ttk.Label(control_frame, text="Max Brake:").pack(padx=5)
        self.brake_scale = ttk.Scale(
            control_frame,
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

        ttk.Label(values_frame, textvariable=self.steering_value).pack(pady=2)
        ttk.Label(values_frame, textvariable=self.throttle_value).pack(pady=2)
        ttk.Label(values_frame, textvariable=self.brake_value).pack(pady=2)

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

    def update_parameters_display(self):
        """ Update parameters display """
        if self.crsf_tx:
            self.params_text.config(state='normal')
            self.params_text.delete(1.0, tk.END)
            for idx, param in self.crsf_tx.parameters.items():
                if param.get("parameter_number") is None:
                    continue
                if param.get("chunk") is None:
                    continue

                out_str = f'{param["parameter_number"]}:{param["chunk_header"]["name"]} = '
                option = param["chunk"]["options"][param["chunk"]["value"]] # option list at value address
                out_str += f"\t{option}\n"
                self.params_text.insert(tk.END, out_str)
            self.params_text.config(state='disabled')

    def update_parameters(self):
        """ Request parameters update """
        if self.crsf_tx:
            self.crsf_tx.request_parameter(0)

    def update_max_throttle(self, value):
        """ Update max throttle value """
        if self.crsf_tx:
            throttle_range = 1811 - 992
            self.crsf_tx.max_throttle = int(992 + (throttle_range * float(value)/100))

    def update_max_brake(self, value):
        """ Update max brake value """
        if self.crsf_tx:
            brake_range = 992 - 172
            self.crsf_tx.max_brake = int(992 - (brake_range * float(value)/100))

    def update_gui(self):
        """
        Main UI update loop runs in foreground, calls itself every 100ms
        """

        # Check for new data in queue
        try:
            q_data = self.queue.get_nowait()
            if q_data:
                if q_data[0] == 'update_status':
                    self.connection_status.set(q_data[1]['status'])
                    self.battery_var.set(q_data[1]['battery'])
                    self.link_var.set(q_data[1]['link'])
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

            # Update parameters display
            try:
                self.update_parameters_display()
            except Exception as e:
                print(f"Param update error: {e}")


        else:
            self.serial_status.set('USB TX: Disconnected')
            self.connection_status.set('RX Link: N/A')
            self.battery_var.set('Battery: --')
            self.link_var.set('Link: --')
            self.update_link_color(0)

        self.root.after(30, self.update_gui) # Update every 30ms

    def update_input_display(self):
        """ Update control inputs """
        self.steering_value.set(f'Steering: {self.input_controller.steering_value}')
        self.throttle_value.set(f'Throttle: {self.input_controller.throttle_value}')
        self.brake_value.set(f'Brake: {self.input_controller.brake_value}')

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

                except serial.SerialException as e:
                    self.crsf_tx = None
                    self.serial_status.set('USB: Disconnected')
                    self.queue.put(('update_status', {
                        'status': f'USB Error: {str(e)}',
                        'battery': 'Battery: --',
                        'link': 'Link: --'
                    }))

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

    def on_closing(self):
        """ Close window """
        self.running = False
        if self.crsf_tx:
            self.crsf_tx.serial.close()
        self.root.quit()

if __name__ == '__main__':
    gui = SimLinkGUI()
