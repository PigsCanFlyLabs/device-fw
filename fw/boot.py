# Import basic crypto stuff
import hashlib

try:
    from ufastecdsa import curve, ecdsa, keys, util
    get_bit_length = util.get_bit_length
except ImportError:
    from fastecdsa import curve, ecdsa, keys, util
    get_bit_length = int.bit_length

# Interactive testing hacks
class FakeUART():
    def __init__(self, lines=[]):
        print(f"Making fake uart with lines {lines}")
        self.baudrate = None
        self.tx = None
        self.rx = None
        self.lines = lines
        self.sent_lines = []
        pass

    def init(self, baudrate=0, tx=None, rx=None):
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx

    async def readline(self):
        line = self.lines.pop(0)
        print(f"Serving fake line {line}")
        return line

    def write(self, cmd):
        print(f"Sendig fake line {cmd}")
        self.sent_lines.append(cmd)

    async def flush(self):
        return True

f = FakeUART()
#from UARTBluetooth import UARTBluetooth
#from Satelite import Satelite

import machine
from machine import Pin, SoftI2C
import uasyncio
import ssd1306
import micropython

micropython.alloc_emergency_exception_buf(400)


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
        except Exception as e:
            print(f"We can't run at {x} because {e}")
            pass  # We don't run at that speed I guess...
    return lowest


lowest_freq = find_lowest_freq()

# Go slow cause YOLO
machine.freq(lowest_freq)

global s
global b
global phone_id

phone_id = None

try:
    with open("phone_id", "r") as p:
        phone_id = p.readline()
except Exception as e:
    print(f"Couldnt read phone id {e}")


async def set_phone_id(new_phone_id: str):
    global phone_id
    phone_id = new_phone_id
    with open("phone_id", "w") as p:
        p.write(phone_id)


async def copy_msg_to_sat_modem(msg: str) -> str:
    global s
    global phone_id
    if phone_id is None:
        raise Exception(f"Device {await s.device_id()} not configured")
    app_id, data = msg.split(",")
    return await s.send_msg(app_id, data)


def msg_acked(msgid: str):
    global b
    b.send_msg_acked(msgid)


def copy_msg_to_ble(msg: str) -> str:
    global b
    b.send_msg(msg)


def copy_error_to_ble(error: str) -> str:
    global b
    b.send_error(error)


def txing_callback(modem_active: bool):
    global b
    if (modem_active):
        b.disable()
    else:
        b.enable()


def modem_ready():
    global b
    b.send_ready()


display = find_display()
client_ready = uasyncio.ThreadSafeFlag()


def client_ready_callback(flag: bool):
    if flag:
        client_ready.set()
    else:
        client_ready.clear()


b = UARTBluetooth("PigsCanFlyLabsLLCProtoType", display, msg_callback=copy_msg_to_sat_modem,
                  client_ready_callback=client_ready_callback, set_phone_id=set_phone_id)
s = Satelite(1, new_msg_callback=copy_msg_to_ble, msg_acked_callback=msg_acked,
             error_callback=copy_error_to_ble, txing_callback=txing_callback,
             ready_callback=modem_ready, client_ready=client_ready, myconn=f)
s.start()
# uasyncio.get_event_loop().run_until_complete()
