from UARTBluetooth import UARTBluetooth
from Satellite import Satellite
import uasyncio
import machine
from machine import Pin, SoftI2C
import ssd1306
import micropython
import time
import os
import select
import sys


go_slow = False
micropython.alloc_emergency_exception_buf(200)
print("Allocated buffer for ISR failure.")
time.sleep(1)
print("Waiting to allow debugger to attach....")
time.sleep(1)
print("Continuing pandas :D")


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


if go_slow:
    print("Finding target machine frequency.")
    default_freq = machine.freq

    lowest_freq = find_lowest_freq()

    # Go slow cause YOLO
    machine.freq(lowest_freq)


# Try and find a display if one is present
def find_display():
    pin16 = Pin(16, Pin.OUT)
    pin16.value(1)
    i2c = SoftI2C(scl=Pin(15), sda=Pin(4))
    if len(i2c.scan()) != 0:
        oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        oled.fill(0)
        oled.text('SpaceBeaver', 0, 0)
        oled.show()
        return oled
    return None


print("Created globals...")
global s
global b
global phone_id

print("Getting ready to read phone id.")
phone_id = None

try:
    print("System directories:")
    print(os.listdir())
    if "phone_id" in os.listdir():
        print("Phone id found.")
        with open("phone_id", "r") as p:
            phone_id = p.read()
            print(f"Loaded phone id {phone_id}")
    else:
        print("Phone id not yet stored.")
except Exception as e:
    print(f"Error reading phone id: {e}")


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
    print(f"Getting device id on {s}")
    return await s.device_id()


async def copy_msg_to_sat_modem(app_id, msg: str) -> str:
    global s
    global phone_id
    print("Copying message to sat modem.")
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


display = None
# display = find_display()
client_ready = uasyncio.ThreadSafeFlag()


def client_ready_callback(flag: bool):
    print(f"Called for client ready with flag {flag}")
    if flag:
        client_ready.set()
        print("Set client to ready :)")


print("Creating bluetooth and satelite.")

try:
    b = UARTBluetooth("SpaceBeaver (PCFL LLC)", display, msg_callback=copy_msg_to_sat_modem,
                      client_ready_callback=client_ready_callback, set_phone_id=set_phone_id,
                      get_device_id=get_device_id, get_phone_id=get_phone_id)
except Exception as e:
    print("BTLE error.")
    print(f"Couldnt create btle {e}")

print("Creating satellite connection.")
try:
    global s
    s = Satellite(uart_id=1,
                  # Testing hack
                  new_msg_callback=copy_msg_to_ble, msg_acked_callback=msg_acked,
                  error_callback=copy_error_to_ble, txing_callback=txing_callback,
                  done_txing_callback=done_txing_callback, ready_callback=modem_ready,
                  client_ready=client_ready,
                  uart_tx=19,
                  uart_rx=18)
    print(f"Set sat device to {s}")
except Exception as e:
    print(f"Couldnt create satelite UART {e}")
    raise e


print("Hi!")
print("Running!")

try:
    s.start()
except Exception as e:
    print(f"Couldnt start satelite comm {e}")


start_magic = "MODEM"
end_magic = "TIMBITLOVESYOU"
max_buff = 100


# See the discussion in https://github.com/micropython/micropython/issues/6415
async def always_busy():
    # poll interface to see if we've got anything from the serial port to handle.
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    buff = ""
    while True:
        c = poll.poll(1)
        print(f"Looping in always busy -- checking for any cmd buffer is {c}")
        # Pass serial port commands along to the modem iff they have the right magic
        while len(c) > 0:
            buff += sys.stdin.read(1)
            c = poll.poll(1)
            print(f"stdin buffer: {buff}")
            if len(buff) > len(start_magic):
                buff = buff[1:len(start_magic)]
                print(f"truncated to {buff}")
            if buff == start_magic:
                buff = ""
                async with s.lock:
                    while not buff.endswith(end_magic):
                        buff += sys.stdin.read(1)
                        if len(buff) > max_buff:
                            s.send_raw(buff[:-len(end_magic)])
                            buff = buff[-len(end_magic):]
        await uasyncio.sleep(10)

uasyncio.create_task(always_busy())

while True:
    try:
        print("Starting event loop...")
        event_loop = uasyncio.get_event_loop()
        event_loop.run_forever()
        print("Event loop complete?")
        time.sleep(5)
    except Exception as e:
        print(f"Error {e} running event loop.")
