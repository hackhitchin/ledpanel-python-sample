# Micropython LED panel driver

from machine import Pin
import rp2

from sys import exit
import _thread
from array import array

# GPIO pins for panel
# The pins below match the panel in the Hackspace window which displays
# the outdoor temperature
#
# Change them as needed for your panel

clk=Pin(19,Pin.OUT)

oe=Pin(27,Pin.OUT)
lat=Pin(28,Pin.OUT)

# D2 needs to be immediately after D1, or the PIO won't work
d1=Pin(14,Pin.OUT)
d2=Pin(15,Pin.OUT)

a0=Pin(20,Pin.OUT)
a1=Pin(21,Pin.OUT)                                                                    

# Three arrays of 64*16 pixels as bits, divided into bytes
# 64*16/8 = 128
red=bytearray(128)
green=bytearray(128)
blue=bytearray(128)

# Output data for each of the four address lines. 64*16 pixels *3 bits = 3072 bits
# divided by 4 lines (A0/A1) = 768 bits/address line (for D1 and D2)
# divided by 16 = 48 16-bit words
outline=[array('H',range(48)),array('H',range(48)),array('H',range(48)),array('H',range(48))]

# PIO code to write out anything put into its output FIFO, 2 bits at a time, and clock it
@rp2.asm_pio(out_init=(rp2.PIO.OUT_LOW,rp2.PIO.OUT_LOW), set_init=rp2.PIO.OUT_LOW, autopull=True)
def pioclk():
    # Discard the first 16 bits of the 32-bit word that comes in
    out(null, 16)
    # Output the next 16 bits as 8x2 bits
    set(x, 7)
    label("loop")
    out(pins, 2)
    set(pins, 1)
    set(pins, 0)
    jmp(x_dec, "loop")

# You might be wondering what's going on - why 16 bits instead of 32? Why not
# store the data as 24 x 32-bit words?
# The answer is Micropython's number handling. Any number that can fit into
# 30 bits (ie 0 to 0x3fffffff) is handled as a single 4-byte value. Anything
# larger requires a bigger integer object.
# In the code below which outputs the data from the line arrays into the
# PIO, if the value retrieved from the array is less than or equal to
# 0x3fffffff, it is handled efficiently. If it is larger, it causes an object
# to be created to hold the number, which is then immediately destroyed after
# being passed to sm.put(). This leads to a small amount of memory being
# consumed, which in turn leads to the garbage collector being called
# frequently. The garbage collector is a "stop the world" operation, which
# prevents the display updating while it's taking place.
# In practical terms, if certain pixels were set (such as the left hand pixel
# on the display), the display would flicker. The more that such pixels were
# on, the worse the flickering would get as the garbage collector was called
# more and more frequently.
# By limiting the output data to 16-bit words, this problem never arises, in
# exchange for a small performance hit.

# PIO state machine
sm = None

# Get the panel ready
def setup():
    # Output disable
    oe.value(1)

    # Set LAT and CLK to 0
    lat.value(0)
    clk.value(0)

    # Set address lines to 0
    a0.value(0)
    a1.value(0)

    # Clear LEDs
    d1.value(0)
    d2.value(0)
    for c in range(384*2):
        clk.toggle()
    
    # Latch
    lat.toggle()
    lat.toggle()

    # Set overall brightness
    dim(0)      # 12.5%. As low as it can be.
    # This can only be set before the PIO state machine is initialised,
    # as the state machine takes over the GPIO pins

    # Clear the display
    clear()

    global sm
    sm = rp2.StateMachine(0, pioclk, freq=10000000, out_base=d1, set_base=clk)

    # Enable PIO state machine
    sm.active(1)

    # Run the display-update loop on the second core
    _thread.start_new_thread(displayupdate, ())

# Set the brightness of the panels by configuring the driver chip
# Minimum brightness = 0
# Maximum brightness = 63
def dim(v):
    lat.value(0)
    clk.value(0)

    d1.value(0)
    d2.value(0)

    # Set LED driver chip to desired brightness
    # 0111000101xxxxxx where xxxxxx = brightness (from 12.5% to 200%)
    # See LED driver datasheet for explanation
    preamble = [ 0,1, 1,1, 0,0, 0,1,0,1]
    data = [ 1 if v&(2**x) else 0 for x in range(5,-1,-1)]

    # Do this 24 times. Once per driver chip. Otherwise only part of the
    # panel will be updated.
    for count in range(24):
        for c,x in enumerate(preamble+data):

            d1.value(x)
            d2.value(x)
            clk.toggle()
            clk.toggle()
            if(c==11):
                lat.value(1)

        lat.value(0)
    

# The micropython.native decorator causes it to emit machine code
# rather than python bytecode. It's faster, but can't do everything
# that python can do
# micropython.viper is even faster, but less compatible, and doesn't
# work here
@micropython.native()
# This code is a bit of a mess, but essentially marshalls the pixel
# data into a bitstream of alternating bits for D1 and D2, by reading
# the pixel data 8 bits at a time for blue, green then red.
def blit():
    line = 0
    i = 0

    def blitbytes(b1:int,b2:int):
        nonlocal line, i
        word = 0
        for bit in range(7,-1,-1):
            word = word << 2
            if b1 & (2 ** bit):
                word +=1
            if b2 & (2 ** bit):
                word += 2

        outline[line][i] = word
        i += 1

    for line in range(4):
        start = line * 8
        i = 0

        for count in range(8):
            blitbytes(blue[start + 0], blue[start + 64])
            blitbytes(blue[start + 32], blue[start + 96])
            blitbytes(green[start + 0], green[start+64])
            blitbytes(green[start + 32], green[start + 96])
            blitbytes(red[start + 0], red[start+64])
            blitbytes(red[start + 32], red[start+96])
            start += 1


# This code outputs data into the panel, one address-line (1/4 of the
# panel) per loop.
@micropython.native()
def displayupdate():
    linenum:int = 0

    while True:
        linenum = (linenum + 1) & 3

        for x in range(0,len(outline[linenum])):
            # Send 32 bits into the PIO state machine's TX FIFO
            sm.put(outline[linenum][x])

        # Latch the data.
        # Theoretically, we don't know that the PIO has clocked out all the
        # data before we do this. In practise, the PIO is so much faster than
        # this python code that by the time we get to toggling LAT, it's done 

        # Display off
        oe.value(1)
        # Set address line
        a0.value(linenum & 1)
        a1.value(linenum >> 1)
        # Toggle LAT to latch the data from the shift register to the LEDs
        lat.toggle()
        lat.toggle()
        # Turn on display
        oe.value(0)


# Clear the screen, and (optionally) blit the display
def clear(autoblit = True):
    for x in [red,green,blue]:
        for y in range(len(x)):
            x[y] = 0
    if autoblit:
        blit()


# Read in a .draw file of font data
# Doesn't work with .yaff files
# https://github.com/robhagemans/hoard-of-bitfonts
def readfont(filename):
    f = open(filename, "r")

    font = {}

    currentchar = None

    for line in f:
        if line.startswith('#'):
            continue
        l = line.strip()
        if len(l) == 0:
            continue

        if l.count(':'):
            (ch,line) = line.split(':', 1)
            l = line.strip()
            currentchar = int(ch, 16)
        
        f = font.get(currentchar)
        if f is None:
            f = []
            font[currentchar] = f

        f.append(l)

    return font


# Write text to display buffer(s) at x,y using the font specified
def write(buffer, x, y, font, text):
    # buffer can be a list of buffers (eg, [red, green, blue])
    if type(buffer) is bytearray:
        buffer = [buffer]

    for ch in text:
        char = ord(ch)
        f = font.get(char)
        if f is None:
            # Ignore missing chars
            continue
        
        y1 = y
        for fline in f:
            x1 = x
            for fchar in fline:
                # Buffer is a set of 1bpp bytes representing 8 pixels
                # at a time. MSB is leftmost pixel
                bit = 1<<(7-(x1 & 7))
                byte = (x1 >> 3)+y1*8
                for b in buffer:
                    if x1>63 or y1>15:
                        continue

                    if fchar == '-':
                        b[byte] = b[byte] & (bit^255)
                    elif fchar == '#':
                        b[byte] = b[byte] | bit
                x1 += 1
            y1 += 1
        x=x1


def main():
    # If GPIO 26 is connected to GND (there's a button on the back of the
    # Hackspace panel), stop now before starting up any loops, second cores
    # etc.
    stop = Pin(26, Pin.IN, Pin.PULL_UP)

    if stop.value()==0:
        exit(0)

    setup()

    af = readfont('acorn_bbc_ascii.draw')
    
    write([red,green,blue], 0,0, af, "LEDPanel")

    for c,v in enumerate("Python"):
        colour = c+1
        cols = []
        if colour & 1:
            cols.append(red)
        if colour & 2:
            cols.append(green)
        if colour & 4:
            cols.append(blue)

        write(cols, c*8 + 8, 8, af, v)

    # Display doesn't change until blit() is called
    blit()

# Uncomment this to auto-start on import. If this file is called main.py
# it will auto-run on panel boot.

#main()