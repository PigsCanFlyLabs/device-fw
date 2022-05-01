from UARTBluetooth import UARTBluetooth
from Satelite import Satelite
import uasyncio
import machine
from machine import Pin, SoftI2C
import micropython
from test_utils import FakeUART

print("Allocating buffer for ISR failure..")
micropython.alloc_emergency_exception_buf(100)


def go_slow():
    print("Finding target machine frequency.")

    def find_lowest_freq():
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


try:
    go_slow()
except Exception as e:
    print(f"Error setting slow mode (likely non-scaleable CPU) {e}")

# Do stuff
micropython.alloc_emergency_exception_buf(400)


# Try and find a display if one is present
def find_display():
    try:
        pin16 = Pin(16, Pin.OUT)
        pin16.value(1)
        i2c = SoftI2C(scl=Pin(15), sda=Pin(4))
        if len(i2c.scan()) != 0:
            import ssd1306
            oled = ssd1306.SSD1306_I2C(128, 64, i2c)
            oled.fill(0)
            oled.text('SpaceBeaver', 0, 0)
            oled.show()
            return oled
    except Exception as e:
        print(f"Error initializing display. {e}")
    return None


global s
global b
global phone_id

phone_id = None

try:
    with open("phone_id", "r") as p:
        phone_id = p.read()
        print(f"Loaded phone id {phone_id}")
except Exception as e:
    print(f"Couldnt read phone id {e}")


async def set_phone_id(new_phone_id: str):
    print("Setting phone id.")
    global phone_id
    phone_id = new_phone_id
    try:
        with open("phone_id", "w") as p:
            p.write(phone_id)
            print(f"Set phone id to {phone_id}")
    except Exception as e:
        print(f"Error persisting phone id {e}")
    return new_phone_id


async def get_phone_id():
    global phone_id
    if phone_id is None:
        try:
            with open("phone_id", "r") as p:
                phone_id = p.readline()
        except Exception as e:
            print(f"Couldnt read phone id {e}")
    return phone_id


async def get_device_id():
    global s
    return s.device_id()


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


def txing_callback():
    global b
    b.disable()


def done_txing_callback():
    global b
    b.enable()


def modem_ready():
    global b
    b.send_ready()


display = find_display()

# ThreadSafeFlag for multi-threaded or fall through to event for single
# threaded.
try:
    client_ready = uasyncio.ThreadSafeFlag()
except Exception:
    client_ready = uasyncio.Event()


def client_ready_callback(flag: bool):
    print(f"Called for client ready with flag {flag}")
    if flag:
        client_ready.set()
        print("Set client to ready :)")


print("Creating bluetooth and satelite.")

b = UARTBluetooth("SpaceBeaver (PCFL LLC)", display, msg_callback=copy_msg_to_sat_modem,
                  client_ready_callback=client_ready_callback, set_phone_id=set_phone_id,
                  get_device_id=get_device_id, get_phone_id=get_phone_id)


conn = FakeUART(lines=[
    "butts",
    "$M138 DATETIME*35",
    "$MM 120,1337DEADBEEF,1,1*39"])

try:
    s = Satelite(1,
                 # Testing hack
                 myconn=conn,
                 new_msg_callback=copy_msg_to_ble, msg_acked_callback=msg_acked,
                 error_callback=copy_error_to_ble, txing_callback=txing_callback,
                 done_txing_callback=done_txing_callback, ready_callback=modem_ready,
                 client_ready=client_ready)
except Exception as e:
    print(f"Couldnt create satelite UART {e}")


print("Hi!")
print("Running!")

try:
    s.start()
except Exception as e:
    print(f"Couldnt start satelite comm {e}")


# See the discussion in https://github.com/micropython/micropython/issues/6415
async def always_busy():
    while True:
        await uasyncio.sleep(0.1)


# uasyncio.create_task(always_busy())

while True:
    try:
        print("Starting event loop...")
        event_loop = uasyncio.get_event_loop()
        event_loop.run_forever()
        print("Event loop complete?")
        import time
        time.sleep(5)
    except Exception as e:
        print(f"Error {e} running event loop.")
