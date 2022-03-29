import micropython
import uasyncio

_BMS_MTU = 128


class UARTBluetooth():

    def __init__(self, name: str, display=None, msg_callback=None, ble=None,
                 client_ready_callback=None, set_phone_id=None,
                 get_device_id=None):
        """Initialize the UART BLE handler. For testing allows ble to be supplied."""

        self.name = name
        if ble is None:
            import ubluetooth
            self.ble = ubluetooth.BLE()
        else:
            self.ble = ble
        self.stop_advertise()
        self.enable()
        self.connected = False
        self.display = display
        self.target_length = 0
        self.mtu = 10
        self.client_ready_callback = client_ready_callback
        self.set_phone_id_callback = set_phone_id
        self.msg_buffer = bytearray(1000)
        self.mv_msg_buffer = memoryview(self.msg_buffer)
        self.msg_buffer_idx = 0
        self.ready = True
        self.get_device_id = get_device_id
        # Setup a call-back for ble msgs
        self.ble.irq(self.ble_irq)
        if ble is None:
            self.register()
        self.advertise()

    def enable(self):
        self.ble.config(gap_name=self.name)
        self.ble.active(True)
        self.ble.config(gap_name=self.name)

    def disable(self):
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
                self.ble.gattc_exchange_mtu(_BMS_MTU)
                uasyncio.create_task(self.client_ready_callback(True))
            elif event == 21:  # _IRQ_MTU_EXCHANGED:
                # ATT MTU exchange complete (either initiated by us or the remote device).
                conn_handle, self.mtu = data
            elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
                # Disconnected
                self.connected = False
                self.advertise()
                uasyncio.create_task(self.client_ready_callback(False))
            elif event == 3:  # _IRQ_GATTS_WRITE
                # msg received, note that BLE UART spec means msg data may be chunked
                buffer = self.ble.gatts_read(self.rx)
                if (self.target_length == 0):
                    # Little endian like x86
                    self.target_length = int.from_bytes(buffer, 'little')
                    print(f"Setting target length to {self.target_length}")
                    return
                # If we're still processing the last message ask the client to repeat it.
                if not self.ready:
                    self.send("REPEAT")
                self.target_length -= len(buffer)
                new_end = self.msg_buffer_idx + len(buffer)
                self.msg_buffer[self.msg_buffer_idx:new_end] = buffer
                if self.target_length == 0:
                    # Use mv_msg_buffer to avoid allocation
                    micropython.schedule(self._handle_phone_buffer, self.mv_msg_buffer[:new_end])
                elif self.target_length < 0:
                    self.msg_buffer_idx = 0
                    # Error
                    e = "ERROR: INVALID MSG LEN"
                    self.send(e)
                    self.target_length = 0
                else:
                    self.msg_buffer_idx = new_end
                    print(f"Waiting for {self.target_length} more chars.")

    def _handle_phone_buffer(self, buffer_veiw):
        try:
            if buffer_veiw[0] == 'M':
                # Two bytes for app ID
                app_id = int.from_bytes(buffer_veiw[1:3], 'little')
                msg_str = buffer_veiw[3:].decode('UTF-8').strip()
                uasyncio.create_task(self._msg_handle(app_id, msg_str))
            elif buffer_veiw[0] == 'P':
                buffer_veiw[1:].decode('UTF-8').strip()
                uasyncio.create_task(self.set_phone_id_callback(msg_str))
                self.msg = []
            elif buffer_veiw[0] == 'Q':
                uasyncio.create_task(self._get_phone_id())
            elif buffer_veiw[0] == 'D':
                uasyncio.create_task(self._get_device_id())
        finally:
            self.ready = True

    async def _get_phone_id(self):
        global phone_id
        if phone_id is None:
            self.send(f"ERROR: \"{await self.get_device_id()}\" not configured.")
        else:
            self.send(f"PHONEID: {phone_id}")

    async def _get_device_id(self):
        self.send(f"{await self.get_device_id()}")

    async def _msg_handle(self, completed_msg):
        if self.msg_callback is not None:
            try:
                id = await self.msg_callback(completed_msg)
                self.send(f"MSGID: {id}")
            except Exception as e:
                self.send(f"ERROR: sat modem error {e}")
            self.display.text(str("".join(self.msg)), 0, 40)
            self.display.show()

    def register(self):
        """Register nordic UART service."""

        import ubluetooth
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

    def send(self, data):
        # Send how many bytes were going to have, we always use 4 bytes to send this.
        self.ble.gatts_notify(0, self.tx, int.to_bytes(len(data), 4, 'little'))
        # Send all of the bytes
        idx = 0
        while (idx < len(data)):
            self.ble.gatts_notify(0, self.tx, data[idx:idx + self.mtu])
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
