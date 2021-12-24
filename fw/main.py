from machine import I2C, Pin, SoftI2C, UART
from time import sleep_ms
import ubluetooth
import ssd1306
from esp32 import raw_temperature
import datetime

class bluetooth():
    
    def __init__(self, name: str, display=None, msg_callback=None):
        
        self.name = name
        self.ble = ubluetooth.BLE()
        self.stop_advertise()
        self.ble.config(gap_name=name)
        self.ble.active(True)
        self.ble.config(gap_name=name)
        self.connected = False
        self.display = display
        self.msg = []
        self.target_length = 0
        self.mtu = 10
        # Setup a call-back for ble msgs
        self.ble.irq(self.ble_irq)
        self.register()
        self.advertise()

    def ble_irq(self, event: int, data):
        """Handle BlueTooth Event."""
        if self.display is not None:
            self.display.fill(0)
            self.display.text(str(event), 0, 5)
            self.display.text(str(data), 0, 20)
            print(str(event))
            print(str(data))
            # Handle bluetooth events
            if event == 1:
                # Paired
                self.connected = True
                # Negotiate MTU
                self.ble.gattc_exchange_mtu()
            elif event == _IRQ_MTU_EXCHANGED:
                # ATT MTU exchange complete (either initiated by us or the remote device).
                conn_handle, self.mtu = data
            elif event == 2:
                # Disconnected
                self.connected = False
                self.advertise()
            elif event == 3:
                # msg received, note that BLE UART spec means msg data may be chunked
                buffer = self.ble.gatts_read(self.rx)
                if (self.target_length == 0):
                    # Little endian like x86
                    self.target_length = int.from_bytes(buffer, 'little')
                    print(f"Setting target length to {self.target_length}")
                    return
                message = buffer.decode('UTF-8').strip()
                self.target_length -= len(buffer)
                self.msg += message
                print(str(message))
                if self.target_length == 0:
                    if msg_callback is not None:
                        msg_callback("".join(self.msg))
                    self.display.text(str("".join(self.msg)), 0, 40)
                    self.msg = []
                elif self.target_length < 0:
                    # Error
                    e = "ERROR: INVALID MSG LEN"
                    self.send(len(e))
                    self.send(e)
                
            self.display.show()

    def register(self):
        
        # Nordic UART Service (NUS)
        NUS_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
        RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'
        TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'
            
        BLE_NUS = ubluetooth.UUID(NUS_UUID)
        BLE_RX = (ubluetooth.UUID(RX_UUID), ubluetooth.FLAG_WRITE)
        BLE_TX = (ubluetooth.UUID(TX_UUID), ubluetooth.FLAG_NOTIFY)
            
        BLE_UART = (BLE_NUS, (BLE_TX, BLE_RX,))
        SERVICES = (BLE_UART, )
        ((self.tx, self.rx,), ) = self.ble.gatts_register_services(SERVICES)


    def send(self, data: ByteString):
        # Send how many bytes were going to have
        self.ble.gatts_notify(0, self.tx, int.to_bytes(len(data), 'little'))
        # Send all of the bytes
        idx = 0
        while (idx < len(data)):
            self.ble.gatts_notify(0, self.tx, data[idx:idx+self.mtu])
            idx = idx + self.mtu


    def stop_advertise(self):
        name = bytes(self.name, 'UTF-8')
        self.ble.gap_advertise(
            None,
            bytearray('\x02\x01\x02') + bytearray((len(name) + 1, 0x09)) + name,
            resp_data=bytearray('\x02\x01\x02') + bytearray((len(name) + 1, 0x09)) + name)
        
    def advertise(self):
        name = bytes(self.name, 'UTF-8')
        self.ble.gap_advertise(
            100,
            bytearray('\x02\x01\x02') + bytearray((len(name) + 1, 0x09)) + name,
            resp_data=bytearray('\x02\x01\x02') + bytearray((len(name) + 1, 0x09)) + name)


class Satelite():

    def __init__(self, new_msg_callback=None, msg_acked_callback=None, error_callback=None):
        self.conn = UART.init(baudrate=115200, tx=11, rx=12)
        self.modem_started = False
        self.transmit_ready = False
        self.new_msg_callback = new_msg_callback
        self.msg_acked_callback = msg_acked_callback
        self.error_callback = error_callback
        try:
            self.conn.irq(handler=self._init_handle)
        except:
            # TODO make a new thread & handle polling

    def _init_irq(self):
        """Handle messages waiting for system to boot."""
        raw_message = UART.readline()
        if raw_message == "$M138 BOOT,RUNNING*49":
            self.modem_started = True
        elif raw_message == "$M138 DATETIME*35":
            self.transmit_read = True
            self.conn.irq(handler=self._prod_handle)
        else:
            print(raw_message)

    def _prod_irq(self):
        """Handle messages after modem bootup."""
        msg = UART.readline()
        _msg_handle(msg)

    def _msg_handle(self, raw_msg):
        msg = self._validate_msg(raw_msg):
        if msg is None:
            print(f"Invalid msg {raw_msg}")
            return
        
        print(f"Valid msg {msg}")
        cmd = msg.split(" ")[0][1:]
        contents = " ".join(msg.split(" ")[1:])
        if msg == "$M138 BOOT,RUNNING*49":
            self.modem_started = True
        elif msg == "$M138 DATETIME*35":
            self.transmit_read = True
        elif cmd == "DT":
            self._update_dt(msg)
        elif cmd == "RD":
            if new_msg_callback is not None:
                new_msg_callback(contents)
        elif cmd == "RT":
            self._update_rt_time(contents)
        elif cmd == "TD":
            if "SENT" in contents:
                self._msg_acked_callback(contents)
            elif "ERR" in contents:
                self.error_callback(raw_msg)
    def _update_rt_time(self, contents):
        elems = contents.split(",")
        for e in elems:
            if "TS" in e:
                self.last_date = date_time.strftime("%Y-%m-%dT%H:%M:%S")
            
        
    def checksum(self, data):
        data.strip()
        if "*" in sentence:
            data, cksum = re.split('\*', data)

        calc_cksum = 0
        for s in adata:
            calc_cksum ^= ord(s)

        return calc_cksum

    def _validate_msg(self, data):
        if "*" not in data:
            return False
        data, cksum = re.split('\*', data)

        calc_cksum = self.checksum(data)
        
        if calc_cksum == int(cksum):
            return data
        else:
            return None


    def is_swam_subscribed(self) -> bool:
        """Return if the user has an active swarm subscription."""
        return True

    def is_pcf_subscribed(self) -> bool:
        """Return if the user has an active PCFLabs subscription."""

    def is_ready(self) -> bool:
        """Returns if the modem is ready for msgs."""
        return self.transmit_ready
    
    def is_suspended(self) -> bool:
        """Is the user suspended in some way."""

    def get_date(self) -> datetime:
        """Get the date."""

    def send_msg(self, num, data) -> bool:

    def suspend_device(self) -> bool:
        """Mark the device as suspended and clear any msgs in queue.
        Intended for misbehaving devices."""

    def last_rt_time(self) -> datetime:
        """Last received test time (from swarm)."""

    
# Try and find a display if one is present

def find_display():
    import machine
    pin16 = machine.Pin(16, machine.Pin.OUT)
    pin16.value(1)
    import machine, ssd1306
    i2c = SoftI2C(scl=machine.Pin(15), sda=machine.Pin(4))
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

running = 0

@wraps(fn)
def wakeup_go_sleep(*args, **kwargs):
    global running
    running += 1
    try:
        if machine.freq() < default_freq:
            machine.freq(default_freq)
    except:
        pass # meh
    try:
        fn(*args, **kwargs)
    finally:
        running -= 1
        if running < 1:
            machine.freq(lowest)


display = find_display()
b = bluetooth("PigsCanFlyLabsLLCProtoType", display)
