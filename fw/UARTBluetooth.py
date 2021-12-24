import uasyncio
import ubluetooth

class UARTBluetooth():
    
    def __init__(self, name: str, display=None, msg_callback=None, ble=None):
        """Initialize the UART BLE handler. For testing allows ble to be supplied."""
        
        self.name = name
        if ble is None:
            self.ble = ubluetooth.BLE()
        else:
            self.ble = ble
        self.stop_advertise()
        self.enable()
        self.connected = False
        self.display = display
        self.msg = []
        self.target_length = 0
        self.mtu = 10
        # Setup a call-back for ble msgs
        self.ble.irq(self.ble_irq)
        self.register()
        self.advertise()

    def enable():
        self.ble.config(gap_name=self.name)
        self.ble.active(True)
        self.ble.config(gap_name=self.name)

    def disable():
        self.ble.config(gap_name=self.name)
        self.ble.active(False)
        self.ble.config(gap_name=self.name)
        
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
                self._handle_received_buffer(buffer)
                
    def _handle_received_buffer(self, buffer):
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
                    self.send(e)
                    self.target_length = 0
                    self.msg = []
                else:
                    print(f"Waiting for {self.target_length} more chars.")


    async def _msg_handle(self, completed_msg):
        if self.msg_callback is not None:
            try:
                id = self.msg_callback(completed_msg)
                self.send(f"MSGID: {id}")
            except Exception as e:
                self.send("ERROR: sat modem error {e}")
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

    def send_msg(self, app_id: str, msg: str):
        self.send(f"MSG {app_id} {msg}")

    def send_error(self, error):
        self.send(f"ERROR {error}")

    def send_ready(self):
        self.send("READY")

    def send_msg_acked(self, msgid: str):
        self.send(f"ACK {msgid}")

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
