import machine
from machine import I2C, Pin, SoftI2C, UART
from time import sleep_ms
import uasyncio
import ubluetooth
import ssd1306
from esp32 import raw_temperature

class UARTBluetooth():
    
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
                    completed_msg = "".join(self.msg)
                    uasyncio.create_task(self._msg_handle(completed_msg))
                    self.msg = []
                elif self.target_length < 0:
                    # Error
                    e = "ERROR: INVALID MSG LEN"
                    self.send(len(e))
                    self.send(e)
                    self.target_length = 0
                    self.msg = []
                else:
                    print(f"Waiting for {self.target_length} more chars.")


    async def _msg_handle(completed_msg):
        if self.msg_callback is not None:
            self.msg_callback(completed_msg)
            self.display.text(str("".join(self.msg)), 0, 40)
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

    def __init__(self, uart_id, new_msg_callback=None, msg_acked_callback=None, error_callback=None, tx=11, rx=12):
        print("Constructing connection to M138.")
        self.conn = UART(uart_id)
        self.modem_started = False
        self.transmit_ready = False
        self.new_msg_callback = new_msg_callback
        self.msg_acked_callback = msg_acked_callback
        self.error_callback = error_callback
        self.last_date = None
        self.lock = uasyncio.Lock()
        self.ready = False
        # Not supported by all micropython
        print("Seting up satelite msg handler...")
        self.satelite_task = uasyncio.create_task(self.main_loop())

    async def main_loop(self):
        print("Initilizing UART.")
        self.conn.init(baudrate=115200, tx=tx, rx=rx)
        print("Initialized UART")
        print("Waiting for satelite modem to boot.")
        self._boot_handle()
        print("Modem started!")
        while (True):
            line = self.conn.readline()
            await self._line_handle(line)

    def _boot_handle(self):
        """Handle messages waiting for system to boot."""
        raw_message = self.conn.readline()
        if raw_message == "$M138 BOOT,RUNNING*49":
            self.modem_started = True
        elif raw_message == "$M138 DATETIME*35":
            self.transmit_ready = True
            # Read all queued msgs from the modem
            self.read_all_msgs()
            self.ready = True
            return True
        else:
            print(raw_message)

    async def _line_handle(self, raw_msg):
        msg = self._validate_msg(raw_msg)
        if msg is None:
            print(f"Invalid msg {raw_msg}")
            return
        
        print(f"Valid msg {msg}")
        cmd = msg.split(" ")[0][1:]
        contents = " ".join(msg.split(" ")[1:])
        if msg == "$M138 BOOT,RUNNING":
            self.modem_started = True
        elif msg == "$M138 DATETIME":
            self.transmit_read = True
        elif cmd == "$DT":
            self._update_dt(msg)
        elif cmd == "$RD":
            if self.new_msg_callback is not None:
                app_id, rssi, snr, fdev, msg_data = contents.split(",")
                self.new_msg_callback(app_id, data)
                # We don't get a msg ID so we just delete all msgs
                # all queued msgs should have already been processed.
                self.delete_msg("*")
        elif cmd == "$RT":
            self._update_rt_time(contents)
        elif cmd == "$TD":
            if contents.starts_with("SENT"):
                msg_id = contents.split(",")[-1]
                if self.msg_acked_callback is not None:
                    self.msg_acked_callback(msg_id)
            elif "ERR" in contents:
                if self.error_callback is not None:
                    self.error_callback(raw_msg)


    def _update_rt_time(self, contents):
        elems = contents.split(",")
        for e in elems:
            if "TS" in e:
                self.last_date = e
            
        
    def _checksum(self, data) -> int:
        """Compute the checksum for a given message."""
        data.strip()
        if "*" in sentence:
            data, cksum = re.split('\*', data)

        calc_cksum = 0
        for s in adata:
            calc_cksum ^= ord(s)

        return calc_cksum

    def _checksum_formatted(self, data) -> str:
        """Format the checksum as tw digit hex"""
        return f"{_checksum(data):02x}"

    def _validate_msg(self, data):
        """Validate a msg matches the checksum."""
        if "*" not in data:
            return False
        data, cksum = re.split('\*', data)

        calc_cksum = self._checksum(data)
        
        if calc_cksum == int(cksum):
            return data
        else:
            return None

    def send_command(self, data):
        """Send a command to the modem."""
        # Acquire the lock if not already acquired.
        l_acquired = self.lock.acquired()
        try:
            self.lock.acquire()
            checksum = self._checksum_formatted(data)
            cmd = f"{data}*{checksum}"
        finally:
            if not l_acquired:
                self.lock.release()

    def del_msg(self, mid: str) -> bool:
        """Delete a message from the modem."""
        # We don't care about the response so much so just yeet it
        self.send_command(f"$MM D={mid}")

    def check_for_msgs(self) -> int:
        """Check msgs, returns number of messages"""
        # We care about the response so disable the interrupt handler
        try:
            self.lock.acquire()
            self.conn.irq(handler=None)
            self.send_command("MM C=U")
            line = self.conn.readline()
            while not line.startswith("$MM"):
                uasyncio.create_task(_line_handle(line))
                line = self.conn.readline()
            try:
                line = self._validate_msg(line)
                int(line.split(" ")[1])
            except:
                return -1
        finally:
            self.conn.irq(handler=self._prod_handle)
            self.lock.release()

    def read_msg(self, id=None) -> tuple[str, str]:
        try:
            self.lock.acquire()
            self.conn.irq(handler=None)
            if id is None:
                id = "N"
            self.send_command(f"$MM R={id}")
            line = self.conn.readline()
            while not line.startswith("$MM"):
                uasyncio.create_task(self._line_handle(line))
                line = self.conn.readline()
            try:
                line = self._validate_msg(line)
                cmd_data = " ".join(line.split(" ")[1:])
                app_id, msg_data, msg_id, es = cmd_data.split(",")
                return (app_id, msg_data, msg_id)
            except:
                return -1
        finally:
            self.conn.irq(handler=self._current_handle)
            self.lock.release()

    def read_all_msgs(self):
        """Read all the msgs and delete as we go."""
        while self.check_for_msgs > 0:
            (app_id, msg_data, msg_id) = self.read_msg()
            if self.new_msg_callback is not none:
                self.new_msg_callback(app_id, msg_data)
            self.delete_msg(msg_id)

    def is_ready(self) -> bool:
        """Returns if the modem is ready for msgs."""
        return self.transmit_ready
    
    def send_msg(self, app_id, data) -> str:
        """Send a message, returning the message ID.
        Data *must be* base64 encoded.
        """
        try:
            self.lock.acquire()
            self.conn.irq(handler=None)
            self.send_command(f"$TD AI={app_id},{data}")
            line = self.conn.readline()
            while (not line.startswith("$TD")) and (not line.startswith("$TD SENT")):
                uasyncio.create_task(self._line_handle(line))
                line = self.conn.readline()
            try:
                line = self._validate_msg(line)
                cmd_data = " ".join(line.split(" ")[1:])
                if cmd_data.startswith("OK"):
                    status, msg_id = cmd_data.split(",")
                    return msg_id
                else:
                    if self.error_callback is not None:
                        self.error_callback(line)
                    return ""
            except:
                raise
        finally:
            self.conn.irq(handler=self._current_handle)
            self.lock.release()

    def last_rt_time(self) -> datetime:
        """Last received test time (from swarm)."""
        return self.last_date

    
# Try and find a display if one is present

def find_display():
    import machine
    pin16 = Pin(16, Pin.OUT)
    pin16.value(1)
    import machine, ssd1306
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
