
# SimLink  
## Use PC inputs via python to drive an ELRS converted RC

With any 2x ELRS receivers and a serial adapter, you can use any computer to control your RC projects very easily. This bridges the gap between the ELRS/CRSF outputs and the HID inputs. 

If you want me to work on it, you'll have to tell me. :) coryconger@gmail.com

![SimLink](https://github.com/CoryC3K/SimLink/blob/main/SimLink.png?raw=true )

# Requirements
## Software
Tested on Linux and Windows. Raspbian & Win10 specifically.

### To run the app
1. `python 3`  
2. `pyserial`  
3. `hidapi` (OS-level, non-python)  
    -windows: is built-in IIRC  
    -linux: "`apt install libhidapi-hidraw0 libhidapi-dev`" will do both  
5. -python `hid` library to link python to hidapi  
    -"`pip install hid`"

Assuming you've got your permissions and dependencies and whatnot, you just run `sudo python3 ./simlink_gui.py`

Sudo because USB devices in raspbian are root and I'm too lazy to google the fix. alias please="sudo". Bang bang !!.

Windows: Just run it with python. It's developed on Windows. 

### To configure the RX's
ExpressLRS Configurator. One time to setup the TX by checking the "is TX" box.  
https://github.com/ExpressLRS/ExpressLRS-Configurator/releases

![ELRS TX Setting Bigger](https://github.com/user-attachments/assets/c9906572-2416-4d81-8db2-3e22d3c37947)

## Hardware
  1. 2x ELRS modules.  
     -The TX needs 5v, gnd, tx, rx available to connect to the serial adapter.  
     -The RX can be any ELRS receiver, but for cars I recommend you spend the extra on one with servo pinouts. Adding a flight controller because your RX only has serial output suuuucks. 
    
  2. 1x USB->Serial adapter. $8 for shipping  
     -CP2101, FTDI, anything made since 2000 would work. Arduino even if you wanted to get fancy.
    
# And that's it to drive your RC car with your computer on long-range ELRS

My goal here was to use my sim rig to drive an RC car around. Notably, this should work for up to 16 inputs with the CRSF packet, but currently only supports the inputs I personally need. :)

So if you ever wanted to fly your RC plane with your flight sim, or drive your RC crawler with your Xbox controller, that should all made easy through the librarires with very minor hardware. I've also enabled the function that prints out what index into the data is the input you just pressed, and what value changed. Hook that up to whatever you want and your sim wheel buttons work too! (PTZ is on my list)

I did some expirements before this using websockets and various SBC's over my home wifi to control the servos. That worked well and I was able to drive around the neighbors house but I wanted the long-range ability of ELRS. Not wanting to buy a transmitter I decided to repurpose one of my receivers as a TX, which you can do through the ELRS Configurator.

Serial baud rate on my Radiomaster RP3 unit is: 921600 baud, but yours will be in the Configurator.

Currently it's setup for a Simagic Alpha wheel and Fanatec pedal set. If you've got a different set of inputs (you will), play around with the python "hid" library. From there you can pull your own targets and replace the hex values.

linux: `lsusb` and use the vid and pid of your set.  
windows (powershell): `Get-PnpDevice -Class 'USB' -Status 'OK' | Format-Table -AutoSize`  
In windows, the `InstanceID` has your VID & PID, be smart and find it: USB\\**VID_2109**&**PID_0813**\6&31B0529A&0&4

# TODO: Most things.
_______
1. Support for other wheel/pedal/inputs/etc  
2. Testing  
... 
7. Other inputs  
8. Figure out that buzzer I wanted to add

I'm guessing I'm just remaking betaflight or openTX or something that's out there already.

Handy links:  
6. https://github.com/ExpressLRS/ExpressLRS  
7. https://github.com/crsf-wg/crsf/wiki  
8. https://github.com/tbs-fpv/tbs-crsf-spec/blob/create-Pdf-Export/crsf.md#frame-construction  
9. https://github.com/apmorton/pyhidapi  



