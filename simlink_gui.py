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
        self.data_points = 100
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
        self.status_var = tk.StringVar(value='Disconnected')
        self.battery_var = tk.StringVar(value='Battery: --')
        self.link_var = tk.StringVar(value='Link: --')

        ttk.Label(self.root, textvariable=self.status_var).pack(pady=2)
        ttk.Label(self.root, textvariable=self.battery_var).pack(pady=2)
        ttk.Label(self.root, textvariable=self.link_var).pack(pady=2)

        self.link_label = tk.Label(self.root, textvariable=self.link_var, width=40)
        self.link_label.pack(pady=2, fill='x')

        self.toggle_connection()


    def refresh_ports(self):
        """ Refresh available COM ports """
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])

    def toggle_connection(self):
        """ Connect or disconnect CRSF TX device """
        if not self.crsf:
            try:
                self.crsf = CRSFDevice(self.port_combo.get())
                self.connect_btn['text'] = 'Disconnect'
            except Exception as e:
                self.status_var.set(f'Error: {str(e)}')
        else:
            self.crsf.serial.close()
            self.crsf = None
            self.connect_btn['text'] = 'Connect'
            self.status_var.set('Disconnected')

    def update_link_color(self, link_quality: int):
        if link_quality > 100:
            link_quality = 100
        elif link_quality < 0:
            link_quality = 0
            
        red = int((100 - link_quality) * 2.55)
        green = int(link_quality * 2.55)
        color = f'#{red:02x}{green:02x}00'
        
        self.queue.put(('update_color', color))

    def setup_charts(self):
        """ Charts frame """
        chart_frame = ttk.Frame(self.root)
        chart_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Create figure with two subplots
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(6, 4))

        # Setup steering plot
        self.ax1.set_title('Steering')
        self.ax1.set_ylim(172, 1811)
        self.steering_line, = self.ax1.plot(range(self.data_points), self.steering_data)

        # Setup throttle plot
        self.ax2.set_title('Throttle')
        self.ax2.set_ylim(172, 1811)
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
            if self.status_var.get() != f'Status: {self.crsf.state.name}':
                self.status_var.set(f'Status: {self.crsf.state.name}')

            batt = self.crsf.battery_data
            if self.battery_var.get() != f'Battery: {batt["voltage"]:.1f}V {batt["current"]:.1f}A {batt["remaining"]}%':
                self.battery_var.set(
                    f'Battery: {batt["voltage"]:.1f}V {batt["current"]:.1f}A {batt["remaining"]}%'
                )

            stats = self.crsf.link_stats
            if stats:
                self.link_var.set(
                    f'Link: RSSI:{stats.get("uplink_rssi_1",0)}dBm LQ:{stats.get("uplink_link_quality",0)}%'
                )
        else:
            self.status_var.set('Disconnected')
            self.battery_var.set('Battery: --')
            self.link_var.set('Link: --')
        
        # Always update charts
        self.update_charts()

    def gui_loop(self):
        self.root = tk.Tk()
        self.root.title('SimLink CRSF TX GUI')
        self.init_ui()
        self.setup_charts()
        
        def check_queue():
            try:
                while True:
                    cmd, data = self.queue.get_nowait()
                    if cmd == 'update_status':
                        self.status_var.set(data['status'])
                        self.battery_var.set(data['battery'])
                        self.link_var.set(data['link'])
                    elif cmd == 'update_charts':
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
