import micropython
import uasyncio
from display_wrapper import DisplayWrapper

_BMS_MTU = 128


class UARTBluetooth():

    def __init__(self, name: str, display=None, msg_callback=None, ble=None,
                 client_ready_callback=None, set_phone_id=None,
                 get_phone_id=None,
                 get_device_id=None):
        """Initialize the UART BLE handler. For testing allows ble to be supplied."""

        self.name = name
        if ble is None:
            try:
                import mac_setup
                mac_bits = 1
                print(dir(mac_setup))
                mac_setup.setup(mac_bits)
            except Exception as e:
                print(help('modules'))
                print(f"Weird error {e} trying to configure MAC prefix, will use ESP32 prefix")
            # NRF and ESP have different libraries
            try:
                import ubluetooth
                self.ble = ubluetooth.BLE()
                self.lib_type = "ubluetooth"
            except ImportError:
                from ubluepy import Peripheral
                self.ble = Peripheral()
                self.lib_type = "ubluepy"
        else:
            self.lib_type = "simulated"
            self.ble = ble
        self.stop_advertise()
        self.services = ()
        self.conn_handle = 0
        self.enable()
        self.connected = False
        self.display = DisplayWrapper(display)
        self.target_length = 0
        self.mtu = 10
        self.client_ready_callback = client_ready_callback
        self.set_phone_id_callback_ref = set_phone_id
        self.msg_buffer = bytearray(1000)
        self.mv_msg_buffer = memoryview(self.msg_buffer)
        self.msg_buffer_idx = 0
        self.ready = True
        self.get_phone_id = get_phone_id
        self.get_device_id = get_device_id
        # We need to avoid allocs in the IRQ
        # (see https://docs.micropython.org/en/latest/reference/isr_rules.html?highlight=isr)
        self._get_phone_id_ref = self._get_phone_id
        self._get_device_id_ref = self._get_device_id
        self._msg_handle_ref = self._msg_handle
        # Setup a call-back for ble msgs
        if self.lib_type == "ubluetooth":
            self.ble.irq(self.ble_irq)
        elif self.lib_type == "ubluepy":
            def merge_handle(event, handle, data):
                """Merge the handle into the data to match the ESP32 lib."""
                self.ble_irq(event, (handle, data))
            self.ble.setConnectionHandler(merge_handle)
        if ble is None:
            self.register()
        self.advertise()

    def enable(self):
        if self.lib_type == "ubluetooth":
            self.ble.config(gap_name=self.name)
            self.ble.active(True)
            print(f"BLE MAC address is {self.ble.config('mac')}")
            self.ble.config(gap_name=self.name)

    def disable(self):
        if self.lib_type == "ubluetooth":
            self.ble.config(gap_name=self.name)
            self.ble.active(False)
            self.ble.config(gap_name=self.name)
        elif self.lib_type == "ubluepy":
            self.ble.advertise_stop()

    def ble_irq(self, event: int, data):
        """Handle BlueTooth Event."""
        print(f"Handling {event} {data}")
        print(f"DEBUG: Current event loop task is {uasyncio.current_task()}")
        print(f"DEBUG: state: {uasyncio.current_task().state}")
        print(str(event))
        print(str(data))
        # Handle bluetooth events
        if event == 1:
            # Paired
            self.display.write("Connected!")
            self.connected = True
            conn_handle, _, _ = data
            self.conn_handle = conn_handle
            # Negotiate MTU
            try:
                self.ble.gattc_exchange_mtu(_BMS_MTU)
            except Exception as e:
                print(f"Error negotiating MTU {e}")
                try:
                    self.ble.gattc_exchange_mtu(int(_BMS_MTU / 2))
                except Exception as e:
                    print(f"Error negotiating MTU {e}")

            self.client_ready_callback(True)
        elif event == 21:  # _IRQ_MTU_EXCHANGED:
            # ATT MTU exchange complete (either initiated by us or the remote device).
            conn_handle, self.mtu = data
        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            # Disconnected
            if self.display is not None:
                self.display.write("Phone disconnected, turn off if done :)")
            self.connected = False
            self.advertise()
            self.client_ready_callback(False)
        elif event == 3:  # _IRQ_GATTS_WRITE
            # msg received, note that BLE UART spec means msg data may be chunked
            buffer = self.ble.gatts_read(self.rx)
            if (self.target_length == 0):
                # Little endian like x86
                self.target_length = int.from_bytes(buffer, 'little')
                # Wrap the buffer if needed.
                if self.target_length + self.msg_buffer_idx >= len(buffer):
                    self.msg_buffer_idx = 0
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
                self.msg_buffer_idx = new_end + 1
            return True

    def _handle_phone_buffer(self, buffer_veiw):
        try:
            command = chr(buffer_veiw[0])
            print(f"Handling command {command}")
            if command == 'M':
                self.display.write("Sending msg to modem")
                # Two bytes for app ID
                app_id = int.from_bytes(buffer_veiw[1:3], 'little')
                msg_str = str(buffer_veiw[3:], 'utf8').strip()
                uasyncio.create_task(self._msg_handle_ref(app_id, msg_str))
            elif command == 'P':
                self.display.write("Configuring modem profile.")
                msg_str = str(buffer_veiw[1:], 'utf8').strip()
                print(f"Setting phone id to {msg_str}")
                uasyncio.create_task(self.set_phone_id_callback_ref(msg_str))
                print("Task created :)")
            elif command == 'Q':
                self.display.write("Fetching phone id")
                uasyncio.create_task(self._get_phone_id_ref())
            elif command == 'D':
                self.display.write("Fetching device id")
                uasyncio.create_task(self._get_device_id_ref())
            else:
                print(f"IDK what to do with {command}")
            print("Done!")
        finally:
            self.ready = True

    async def _get_phone_id(self):
        phone_id = await self.get_phone_id()
        print(f"Got phone id {phone_id}")
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
            self.display.write(str("".join(self.msg)))
            self.display.show()

    def register(self):
        """Register nordic UART service."""

        # Nordic UART Service (NUS)
        NUS_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
        RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'
        TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'

        if self.lib_type == "ubluetooth":
            import ubluetooth
            BLE_NUS = ubluetooth.UUID(NUS_UUID)
            BLE_RX = (ubluetooth.UUID(RX_UUID), ubluetooth.FLAG_WRITE)
            BLE_TX = (ubluetooth.UUID(TX_UUID), ubluetooth.FLAG_NOTIFY)
            BLE_UART = (BLE_NUS, (BLE_TX, BLE_RX,))
            SERVICES = (BLE_UART, )
            self.services = SERVICES
            ((self.tx, self.rx,), ) = self.ble.gatts_register_services(SERVICES)
            rxbuf = 500
            self.ble.gatts_set_buffer(self.rx, rxbuf, True)
        elif self.lib_type == "ubluepy":
            from ubluepy import Characteristic, Service, UUID
            self.services = Service(UUID(NUS_UUID))
            self.rx = Characteristic(
                UUID(RX_UUID),
                props=Characteristic.PROP_WRITE | Characteristic.PROP_WRITE_WO_RESP)
            self.tx = Characteristic(
                UUID(TX_UUID),
                props=Characteristic.PROP_READ | Characteristic.PROP_NOTIFY,
                attrs=Characteristic.ATTR_CCCD)
            self.services.addCharacteristic(self.rx)
            self.services.addCharacteristic(self.tx)
            # We use this to construct the advertising packet.
            self.service_uuids = [UUID(NUS_UUID), UUID(RX_UUID), UUID(TX_UUID)]
            self.ble.addService(self.services)

    def _raw_write(self, raw_data):
        if self.lib_type == "ubluetooth":
            self.ble.gatts_notify(self.conn_handle, self.tx, raw_data)
        else:
            self.tx.write(raw_data)

    def send(self, data):
        print(f"Preparing to send {data} to UART BTLE.")
        # Send how many bytes were going to have, we always use 4 bytes to send this.
        self._raw_write(int.to_bytes(len(data), 4, 'little'))
        # Send all of the bytes
        idx = 0
        while (idx < len(data)):
            self._raw_write(data[idx:idx + self.mtu])
            idx = idx + self.mtu

    def send_msg(self, app_id: str, msg: str):
        self.display("Loading msg from satelites")
        self.send(f"MSG {app_id} {msg}")

    def send_error(self, error):
        self.send(f"ERROR {error}")

    def send_ready(self):
        self.send("READY")

    def send_msg_acked(self, msgid: str):
        self.send(f"ACK {msgid}")

    def stop_advertise(self):
        if self.lib_type == "ubluetooth":
            self.ble.gap_advertise(None, b'')
        elif self.lib_type == "ubluepy":
            self.ble.advertise_stop()

    def advertise(self):
        print(f"Advertising {self.name}")
        from micropython import const
        import struct
        device_type = 5184  # Generic outdoor
        # Generate a payload to be passed to gap_advertise(adv_data=...).
        # From:
        # https://github.com/micropython/micropython/blob/master/examples/bluetooth/
        # This is MIT licensed.

        def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None,
                                appearance=0):
            _ADV_TYPE_FLAGS = const(0x01)
            _ADV_TYPE_NAME = const(0x09)
            _ADV_TYPE_UUID16_COMPLETE = const(0x3)
            _ADV_TYPE_UUID32_COMPLETE = const(0x5)
            _ADV_TYPE_UUID128_COMPLETE = const(0x7)
            _ADV_TYPE_APPEARANCE = const(0x19)

            payload = bytearray()

            def _append(adv_type, value):
                nonlocal payload
                payload += struct.pack("BB", len(value) + 1, adv_type) + value

            _append(
                _ADV_TYPE_FLAGS,
                struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)),
            )

            if name:
                _append(_ADV_TYPE_NAME, name)

            if services:
                for uuid in services:
                    print(f"Services {uuid} in {services}")
                    # Return here and fix the cast issue.
                    b = bytes(uuid)
                    if len(b) == 2:
                        _append(_ADV_TYPE_UUID16_COMPLETE, b)
                    elif len(b) == 4:
                        _append(_ADV_TYPE_UUID32_COMPLETE, b)
                    elif len(b) == 16:
                        _append(_ADV_TYPE_UUID128_COMPLETE, b)

            # See org.bluetooth.characteristic.gap.appearance.xml
            if appearance:
                _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))

            return payload

        print("Creating advertise payload")
        print(self.name)
        print("Services")
        print(self.services)
        print("Device type")
        print(device_type)
        if self.lib_type == "ubluetooth":
            _payload = advertising_payload(
                name=self.name,
                services=self.services,
                appearance=device_type)
            self.ble.gap_advertise(
                100,
                _payload,
                resp_data=_payload)
        elif self.lib_type == "ubluepy":
            _payload = advertising_payload(
                name=self.name,
                services=self.service_uuids,
                appearance=device_type)
            self.ble.advertise(device_name=self.name, data=_payload)
