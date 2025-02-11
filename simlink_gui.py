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
from simlink_csrf import CRSFDevice
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class SimLinkGUI:
    """ SimLink CRSF GUI """
    def __init__(self):
        self.root = None
        self.queue = queue.Queue()
        self.running = True
        self.gui_thread = threading.Thread(target=self.gui_loop)
        self.gui_thread.daemon = True
        self.gui_thread.start()
        self.crsf = None

        # Chart settings
        self.data_points = 4000
        self.time_data = list(range(self.data_points))

        self.steering_data = [992] * self.data_points
        self.throttle_data = [992] * self.data_points
        self.steering_line = None
        self.throttle_line = None

        self.canvas = None


    def init_ui(self):
        """ Initialize GUI elements """
        conn_frame = ttk.Frame(self.root)
        conn_frame.pack(fill='x', padx=5, pady=5)

        self.port_combo = ttk.Combobox(conn_frame)
        self.refresh_ports()
        self.port_combo.pack(side='left', expand=True, fill='x', padx=(0,5))

        self.last_draw = 0

        self.connect_btn = ttk.Button(conn_frame, text='Connect', command=self.toggle_connection)
        self.connect_btn.pack(side='right')

        # Status labels
        self.serial_status = tk.StringVar(value='USB: Disconnected')
        self.connection_status = tk.StringVar(value='Link: Disconnected')
        self.battery_var = tk.StringVar(value='Battery: --')
        self.link_var = tk.StringVar(value='Link: --')
        status_frame = ttk.LabelFrame(self.root, text="Status")
        status_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(status_frame, textvariable=self.serial_status).pack(pady=2)
        ttk.Label(status_frame, textvariable=self.connection_status).pack(pady=2)
        ttk.Label(status_frame, textvariable=self.battery_var).pack(pady=2)
        self.link_label = tk.Label(status_frame, textvariable=self.link_var, width=40)
        self.link_label.pack(pady=2, fill='x')
        # # Status labels
        # self.status_var = tk.StringVar(value='Disconnected')
        # self.battery_var = tk.StringVar(value='Battery: --')
        # self.link_var = tk.StringVar(value='Link: --')

        # ttk.Label(self.root, textvariable=self.status_var).pack(pady=2)
        # ttk.Label(self.root, textvariable=self.battery_var).pack(pady=2)

        # self.link_label = tk.Label(self.root, textvariable=self.link_var, width=40)
        # self.link_label.pack(pady=2, fill='x')

        # Control Frame
        control_frame = ttk.LabelFrame(self.root, text="Control Settings")
        control_frame.pack(fill='x', padx=5, pady=5)

        # Max Throttle Slider
        ttk.Label(control_frame, text="Max Throttle:").pack(side='left', padx=5)
        self.throttle_scale = ttk.Scale(
            control_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_throttle
        )
        self.throttle_scale.set(50)  # Default 50%
        self.throttle_scale.pack(side='left', fill='x', expand=True, padx=5)

        # Max Brake Slider
        ttk.Label(control_frame, text="Max Brake:").pack(side='left', padx=5)
        self.brake_scale = ttk.Scale(
            control_frame,
            from_=0,
            to=100,
            orient='horizontal',
            command=self.update_max_brake
        )
        self.brake_scale.set(50)  # Default 50%
        self.brake_scale.pack(side='left', fill='x', expand=True, padx=5)

        self.toggle_connection()


    def refresh_ports(self):
        """ Refresh available COM ports """
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])

    def check_serial_status(self):
        """ Check if device still connected"""
        if self.crsf and not self.crsf.serial.is_open:
            self.crsf = None
            self.connect_btn['text'] = 'Connect'
            self.serial_status.set('USB: Disconnected')

        # Refresh available ports
        self.refresh_ports()

        # Schedule next check
        if self.running:
            self.root.after(1000, self.check_serial_status)

    def toggle_connection(self):
        """ Connect or disconnect CRSF TX device """
        if not self.crsf:
            try:
                self.crsf = CRSFDevice(self.port_combo.get())
                self.connect_btn['text'] = 'Disconnect'
                self.serial_status.set('USB: Connected')
            except Exception as e:
                self.serial_status.set(f'USB Error: {str(e)}')
        else:
            self.crsf.serial.close()
            self.crsf = None
            self.connect_btn['text'] = 'Connect'
            self.serial_status.set('USB: Disconnected')

    def update_link_color(self, link_quality: int):
        """ Update link quality color """
        if link_quality > 100:
            link_quality = 100
        elif link_quality < 0:
            link_quality = 0

        red = int((100 - link_quality) * 2.55)
        green = int(link_quality * 2.55)
        color = f'#{red:02x}{green:02x}00'

        self.queue.put(('update_color', color))

    def update_max_throttle(self, value):
        """ Update max throttle value """
        if self.crsf:
            throttle_range = 1811 - 992
            self.crsf.max_throttle = int(992 + (throttle_range * float(value)/100))

    def update_max_brake(self, value):
        """ Update max brake value """
        if self.crsf:
            brake_range = 992 - 172
            self.crsf.max_brake = int(992 - (brake_range * float(value)/100))

    def setup_charts(self):
        """ Charts frame """
        chart_frame = ttk.Frame(self.root)
        chart_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Create figure with two subplots
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(6, 4))
        self.fig.patch.set_facecolor('#2b2b2b')  # Dark background

        # Setup steering plot
        self.ax1.set_title('Steering')
        self.ax1.set_ylim(172, 1811)
        self.ax1.set_facecolor('#1e1e1e')  # Dark plot background
        self.ax1.grid(True, color='#404040')
        for spine in self.ax1.spines.values():
            spine.set_color('white')
        self.steering_line, = self.ax1.plot(range(self.data_points), self.steering_data)

        # Setup throttle plot
        self.ax2.set_title('Throttle')
        self.ax2.set_ylim(172, 1811)
        self.ax2.set_facecolor('#1e1e1e')
        self.ax2.grid(True, color='#404040')
        self.ax2.tick_params(colors='white')
        for spine in self.ax2.spines.values():
            spine.set_color('white')
        self.throttle_line, = self.ax2.plot(range(self.data_points), self.throttle_data)

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.draw_idle()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

    def update_charts(self):
        """ Update steering and throttle charts """
        """WARN: PERFORMANCE ISSUE"""
        if self.crsf and hasattr(self.crsf, 'RC_CHANNELS'):
            # Update data arrays
            self.steering_data = self.steering_data[1:] + [self.crsf.RC_CHANNELS[0]]
            self.throttle_data = self.throttle_data[1:] + [self.crsf.RC_CHANNELS[1]]

            # Update plot data
            self.steering_line.set_xdata(self.steering_data)
            self.throttle_line.set_xdata(self.throttle_data)

            #self.canvas.draw_idle()
            #self.canvas.flush_events()

    def update_status(self):
        """ Update status labels """
        if self.crsf:
            self.crsf.update()
            self.connection_status.set(f'Link: {self.crsf.state.name}')
            #self.status_var.set(f'Status: {self.crsf.state.name}')

            batt = self.crsf.battery_data
            self.battery_var.set(
                    f'Battery: {batt["voltage"]:.1f}V {batt["current"]:.1f}A {batt["remaining"]}%'
                )

            stats = self.crsf.link_stats
            if stats:
                self.link_var.set(
                    f'Link: RSSI:{stats.get("uplink_rssi_1",0)}dBm LQ:{stats.get("uplink_link_quality",0)}%'
                )
        else:
            self.connection_status.set('Link: Disconnected')
            #self.status_var.set('Disconnected')
            self.battery_var.set('Battery: --')
            self.link_var.set('Link: --')

        # Always update charts
        self.update_charts()

    def gui_loop(self):
        """ Main GUI loop """
        self.root = tk.Tk()
        self.root.title('SimLink CRSF TX GUI')
        self.init_ui()
        self.setup_charts()
        self.check_serial_status()

        def check_queue():
            try:
                while True:
                    cmd, data = self.queue.get_nowait()
                    # if cmd == 'update_status':
                    #     self.status_var.set(data['status'])
                    #     self.battery_var.set(data['battery'])
                    #     self.link_var.set(data['link'])
                    if cmd == 'update_charts':
                        if self.crsf:
                            self.steering_data = self.steering_data[1:] + [self.crsf.RC_CHANNELS[0]]
                            self.throttle_data = self.throttle_data[1:] + [self.crsf.RC_CHANNELS[1]]
                            self.steering_line.set_ydata(self.steering_data)
                            self.throttle_line.set_ydata(self.throttle_data)
                            self.canvas.draw_idle()
                    elif cmd == 'update_color':
                        self.link_label.configure(bg=data)
                # while True:
                #     cmd, data = self.queue.get_nowait()
                #     if cmd == 'update':
                #         self.update_charts()
            except queue.Empty:
                pass
            if self.running:
                self.root.after(16, check_queue)

        check_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def update_loop(self):
        """ Update loop """
        while self.running:
            if self.crsf:
                self.crsf.update()
                self.queue.put(('update_status', {
                    'status': f'Status: {self.crsf.state.name}',
                    'battery': f'Battery: {self.crsf.battery_data["voltage"]:.1f}V',
                    'link': f'Link: RSSI:{self.crsf.link_stats.get("uplink_rssi_1",0)}dBm'
                }))
                lq = self.crsf.link_stats.get("uplink_link_quality", 0)
                self.update_link_color(lq)
            # Send chart updates
            self.queue.put(('update_charts', None))
            time.sleep(0.001)

    def run(self):
        """ Run main loop """
        update_thread = threading.Thread(target=self.update_loop)
        update_thread.daemon = True
        update_thread.start()

        while self.running:
            time.sleep(0.1)

    # def run(self):
    #     """ Run main loop """
    #     self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    #     def main():
    #         # Run tkinter main loop as a coroutine
    #         while True:
    #             self.update_status()
    #             time.sleep(0)
    #             self.root.update()

    #     main()

    def on_closing(self):
        """ Close window """
        if self.crsf:
            self.crsf.serial.close()
        self.root.quit()

if __name__ == '__main__':
    gui = SimLinkGUI()
    gui.run()
