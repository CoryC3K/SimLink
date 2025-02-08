# SimLink
Use a car sim rig or other inputs via python to drive an RC car or other ELRS converted device.

Requires python 3, pyserial, and hidapi.

My goal here was to use my sim rig to drive an RC car around. It's phase 1 of my long-term "start an online remote-in FPV RC park at the old go-kart track" plan. I need to control cars from a computer, and I like python. Notably, this should work for up to 16 inputs with a little creative modification. So if you wanted to fly an RC plane with your flight sim, or drive an RC crawler with your Xbox controller, that should all be easy through the librarires with just a serial adapter and 2x ELRC RX's. Gotta love Python! There's not much that would require changing for a linux or raspberry pi install. I do plan to go remote at some point, and there's no real need for a laptop.

I did some expirements before this with websockets and various SBC's over my home wifi. That worked well and I was able to drive around the neighbors house but I wanted the long-range ability of ELRS. Not wanting to buy a transmitter (it gets here in 2 days) I decided to repurpose one of my receivers as a TX, which you can do through the ELRS Configurator. I didn't realize no one had the code to just use that from windows.

Serial baud rate on my Radiomaster RP3 unit is: 921600 baud

YOURS MAY (probably) BE DIFFERENT!!! Common bauds are 400k, 420k, 420600, and a half dozen others. Pray for autonegotiation to work or ask your TX MFG.

Currently it's setup for a Simagic Alpha wheel and Fanatec pedal set. If you've got a different set of inputs (you will), play around with the python "hid" library. It's pretty easy to list out the found devices and addresses (helpfully commented out in simlink_input's get_pedals()) and from there you can pull your own targets and replace the hex values. Or, bug me/gpt and we'll write a gui using tkinter, it'll take a day. 

TODO: Most things.
_______
1. Input selection, programming, limits
2. Testing
3. Figure out brakes
4. Clean up this bash-fest of a codebase
5. Write a GUI
6. store reciver ID and settings so the controller can remember zeros and whatnot
7. ???


Handy links:
6. https://github.com/ExpressLRS/ExpressLRS
7. https://github.com/crsf-wg/crsf/wiki
8. https://github.com/tbs-fpv/tbs-crsf-spec/blob/create-Pdf-Export/crsf.md#frame-construction
9. https://github.com/apmorton/pyhidapi

10. If you want me to work on it, you'll have to tell me. :) coryconger@gmail.com
