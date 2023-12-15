# ledpanel-python-sample
Example code to drive one of the MBI5034-based LED pixel panels that we
have loads of.

Requires Micropython installed on an RP2040 (eg, Raspberry Pi Pico). The
display panel should be connected as follows:

* A1	GPIO 8
* A2	GPIO 9
* D1	GPIO 0
* D2	GPIO 1
* LAT	GPIO 10
* OE	GPIO 11
* CLK	GPIO 12

These pins correspond to the board built by Luis.
They can be changed to suit your panel connection. The only restriction
is that D1 and D2 must be on adjacent GPIO pins
