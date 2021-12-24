import machine
from machine import I2C, Pin, SoftI2C, UART
import uasyncio
import ssd1306
from UARTBluetooth import UARTBluetooth
from Satelite import Satelite

# Try and find a display if one is present
def find_display():
    pin16 = Pin(16, Pin.OUT)
    pin16.value(1)
    i2c = SoftI2C(scl=Pin(15), sda=Pin(4))
    if len(i2c.scan()) != 0:
        oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        oled.fill(0)
        oled.text('PigsCanFlyLabsLLC ProtoTypeDevice starting', 0, 0)
        oled.show()
        return oled
    return None

default_freq = machine.freq
def find_lowest_freq():
    import machine
    lowest = machine.freq()
    clock_speeds = [20000000, 40000000, 80000000, 1600000000, 2400000000]
    for x in clock_speeds:
        try:
            if x < lowest:
                machine.freq(x)
                lowest = x
        except:
            pass # We don't run at that speed I guess...
    return lowest

lowest_freq = find_lowest_freq()

# Go slow cause YOLO
machine.freq(lowest_freq)

display = find_display()
b = UARTBluetooth("PigsCanFlyLabsLLCProtoType", display)
s = Satelite(1)
