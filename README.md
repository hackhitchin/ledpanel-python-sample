# ledpanel-python-sample
Example code to drive one of the MBI5034-based LED pixel panels that we
have loads of.

Requires Micropython installed on an RP2040 (eg, Raspberry Pi Pico). The
display panel should be connected as follows:

* A1	GPIO 20
* A2	GPIO 21
* D1	GPIO 14
* D2	GPIO 15
* OE	GPIO 27
* LAT	GPIO 28
* CLK	GPIO 19

These pins correspond to the temperature display panel in the Hackspace.
They can be changed to suit your panel connection. The only restriction
is that D1 and D2 must be on adjacent GPIO pins
