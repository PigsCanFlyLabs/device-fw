import uasyncio


class Satellite():

    def __init__(self, uart_id,
                 new_msg_callback=None,
                 msg_acked_callback=None,
                 error_callback=None,
                 txing_callback=None,
                 done_txing_callback=None,
                 misc_callback=None,
                 tx_pin=None,
                 rx_pin=None,
                 uart_tx=26,
                 uart_rx=27,
                 ready_callback=None,
                 client_ready=None,
                 max_retries=-1,
                 myconn=None,
                 delay=30):
        """Initialize a connection to the satelite modem. Allows setting myconn for testing.
        uart_id is the ID of the uart controller to use
        new_msg_callback should take app_id (str) and data (str, base64 encoded)
        msg_acked_callback takes a str of msgid
        error_callback takes a str of error string
        txing_callback takes bool for active TX or false for TX finished
        tx_pin is a pin to monitor for TXing
        rx_pin is a pin to monitor for RXing
        uart_tx is the UART tx pin
        uart_rx is the UART rx pin
        ready_callback is a callback to indicate the modem can receive msgs
        client_ready is a ThreadSafeFlag of when the client is ready.
        max_retries the number of retries at each level of retrying.
        """
        print(f"Constructing connection to M138 w/ uart {uart_id} on {uart_tx} + {uart_rx}")
        self.lock = uasyncio.Lock()
        try:
            if myconn is None:
                from machine import UART
                self.conn = UART(uart_id, baudrate=115200, tx=uart_tx, rx=uart_rx)
            else:
                self.conn = myconn
        except Exception as e:
            print(f"Error creating uart {e}")
        print(f"Using uart {self.conn}")
        self.modem_started = False
        self.new_msg_callback = new_msg_callback
        self.msg_acked_callback = msg_acked_callback
        self.error_callback = error_callback
        self.last_date = None
        self.ready = False
        self.max_retries = max_retries
        self.ready_callback = ready_callback
        self.client_ready = client_ready
        self._device_id = None
        self.transmit_ready = False
        self.misc_callback = misc_callback
        self.delay = delay
        self.tx_pin = tx_pin
        self.txing_callback = txing_callback
        self.done_txing_callback = done_txing_callback
        print("Initilizing UART.")
        try:
            self.conn.init(baudrate=115200, tx=uart_tx, rx=uart_rx)
        except Exception as e:
            print(f"Error initializing uart {e}")
        print("Initialized, making stream r/w.")
        if myconn is None:
            self.swriter = uasyncio.StreamWriter(self.conn, {})
        else:
            self.swriter = myconn
        if myconn is None:
            self.sreader = uasyncio.StreamReader(self.conn)
        else:
            self.sreader = myconn
        print("Streams set up")

    def start(self):
        try:
            # For regulatory reasons only operate one radio at a time.
            if self.tx_pin is not None and self.txing_callback is not None:
                from machine import Pin
                pin = Pin(self.tx_pin, Pin.IN, Pin.PULL_UP)
                pin.irq(trigger=Pin.IRQ_RISING, handler=self.txing_callback)
                pin.irq(trigger=Pin.IRQ_FALLING, handler=self.done_txing_callback)
        except Exception as e:
            print(f"Error {e} trying to register TXING callback.")

        print("Seting up satelite msg handler...")
        self.satelite_task = uasyncio.create_task(self.main_loop())
        print(f"Task created for msg handles - {self.satelite_task}")

    async def main_loop(self):
        print("Waiting for satelite modem to boot, plz say hi soon!")
        async with self.lock:
            print("Modem locked until ready.")
            while not await self._modem_ready():
                print("Yielding...")
                await uasyncio.sleep(1)
        retries = 0
        print("Sat modem started, entering main loop.")
        while self.max_retries == -1 or retries < self.max_retries:
            print("Waiting for phone client to become ready...")
            # Temporary: Disable phone check.
            #  await self.client_ready.wait()
            print("Phone client ready!")
            self.ready = True
            if self.ready_callback is not None:
                self.ready_callback()
            try:
                print("ready callback done.")
                await self.read_all_msgs()
                print("all queued msgs read.")
                await self._enable_msg_watch()
                print("msg watch enabled.")
                print(f"Yeee-haw {retries} in.")
                await uasyncio.sleep(self.delay)
                line = None
                line_retries = 0
                # Seperate out reading from the satelite it's self
                while line is None and line_retries < 3:
                    try:
                        line = await self.sreader.readline()
                    except Exception as e:
                        print(f"Error reading from satelite device... {e} attempt {line_retries}")
                        line_retries = line_retries + 1
                        await uasyncio.sleep(self.delay * line_retries)
                        if line_retries >= 2:
                            print(f"Re-raising error {e}")
                            raise e
                await self._line_handle(line)
                await uasyncio.sleep(1)
            # Error processing a msg from the satelite modem.
            except Exception as e:
                # If we encounter an error validate that the client is still connected
                self.ready = False
                print(f"Error in main loop {e}")
                await self._disable_msg_watch()
                await uasyncio.sleep(self.delay * retries)
                retries = retries + 1
                print(f"Retries in main sat loop is now {retries}")
        print(f"Finishing main satelite loop with {retries} retries")

    async def _modem_ready(self):
        """Handle messages waiting for system to boot."""
        # Note the developer docs have incorrect checksums for the boot sequence
        # so (for now) we'll support both of them.
        print("Checking modem readiness.")
        if self.modem_started:
            print("Modem ready!")
            return True
        print("Modem not yet ready, checking serial port.")
        raw_message = None
        while raw_message is None:
            print("Waiting to get a message from modem.")
            print(f"Current conn {self.conn} reader {self.sreader}")
            try:
                raw_message = await uasyncio.wait_for(
                    self.sreader.readline(),
                    timeout=60.0)
                if hasattr(raw_message, "decode"):
                    raw_message = raw_message.decode("UTF-8")
                print(f"Read line {raw_message}")
            except uasyncio.TimeoutError:
                print("Took longer than 60s for modem to boot, query modem.")
                await self.send_command("$CS*10")
            except Exception as e:
                print(f"Error reading line during modem boot - {e} {self.conn}")
                await uasyncio.sleep(1)
        msg = self._validate_msg(raw_message)
        if raw_message == "$M138 BOOT,RUNNING*49":
            print("Modem enabled")
            self.modem_started = True
        elif raw_message == "$M138 DATETIME*35":
            print("t e")
            return True
        elif msg is not None:
            if msg == "$M138 BOOT,RUNNING":
                print("Modem enabled")
                self.modem_started = True
                return True
            elif msg == "$M138 DATETIME":
                print("t e")
                self.modem_started = True
                return True
            elif msg.startswith("$CS"):
                print("Modem provided valid command, missed boot seq.")
                self.modem_started = True
                return True
            elif msg.startswith("M138 BOOT,DEVICEID,DI="):
                _, id = msg.splti("=")[1]
                print("Modem almost ready _possible_ device id {id}")
        print("Nope :/")
        return False

    async def _line_handle(self, raw_msg):
        """Handle post boot messages from the M138 modem."""
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
            self.transmit_ready = True
        elif cmd == "$DT":
            self._update_dt(msg)
        elif cmd == "$RD":
            if self.new_msg_callback is not None:
                app_id, rssi, snr, fdev, msg_data = contents.split(",")
                # Wait until the msg call back succeeds before removing it from the modem.
                self.new_msg_callback(int(app_id), msg_data)
                # We don't have a msg id here, but for safety leave it to the client (phone)
                # to explicitily call delete msgs later.
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
        elif self.misc_callback is not None:
            self.misc_callback(msg)
        else:
            print(f"Unhandled msg {msg} with no misc callback.")

    async def _enable_msg_watch(self):
        await self.send_command("$MM N=E")

    async def _disable_msg_watch(self):
        await self.send_command("$MM N=D")

    def _update_rt_time(self, contents):
        """Update the last rt time."""
        elems = contents.split(",")
        for e in elems:
            if "TS" in e:
                self.last_date = e

    def _checksum(self, data) -> int:
        """Compute the checksum for a given message."""
        # Drop the trailing newline
        data.strip()
        # Drop the leading $ if present
        if len(data) > 1 and data[0] == '$':
            data = data[1:]
        # Drop the trailing *xx
        if len(data) > 3 and data[-3] == '*':
            data = data[:-3]
        calc_cksum = 0

        for s in data:
            calc_cksum ^= ord(s)
        return calc_cksum

    def _checksum_formatted(self, data) -> str:
        """Format the checksum as tw digit hex"""
        return f"{self._checksum(data):02X}"

    def _validate_msg(self, data):
        """Validate a msg matches the checksum."""
        if hasattr(data, "decode"):
            data = data.decode('UTF-8')
        if len(data) > 1 and data[-1] == '\n':
            data = data[0:-1]
        # Parse the trailing *xx
        if len(data) > 3 and data[-3] == '*':
            cksum = data[-2:]
            data = data[:-3]
        else:
            return None

        calc_cksum = self._checksum(data)

        if calc_cksum == int(cksum, 16):
            return data
        else:
            return None

    async def send_command(self, data):
        """Send a command to the modem. Calculates the checksum.
        Caller should hold the lock otherwise bad things may happen.
        """
        checksum = self._checksum_formatted(data)
        cmd = f"{data}*{checksum}"
        print(f"Sending command {cmd}")
        self.swriter.write(cmd)
        await self.swriter.drain()
        print(f"Sent command {cmd}")

    async def del_msg(self, mid: str) -> bool:
        """Delete a message from the modem."""
        # We don't care about the response so much so just yeet it
        await self.send_command(f"$MM D={mid}")

    async def check_for_msgs(self) -> int:
        """Check msgs, returns number of messages."""
        # We care about the response so disable the interrupt handler
        async with self.lock:
            await self.send_command("MM C=U")
            line = await self.sreader.readline()
            while not line.startswith("$MM") or self._validate_msg(line) is None:
                print(f"un-expected msg line {line}, creatig task to handle later.")
                uasyncio.create_task(self._line_handle(line))
                line = await self.sreader.readline()
            try:
                line = self._validate_msg(line)
                parsed = int(line.split(" ")[1])
                print(f"We have {parsed} messages.")
                return parsed
            except Exception as e:
                print(f"Error fetching msgs... {e}")
                return -1

    async def device_id(self) -> str:
        """Return the device id."""
        if self._device_id is not None:
            return self._device_id
        try:
            async with self.lock:
                await self.send_command("CS")
                line = await self.sreader.readline()
                while not line.startswith("$CS"):
                    print(f"Looping on modem line {line}")
                    uasyncio.create_task(self._line_handle(line))
                    line = await self.sreader.readline()
                    line = self._validate_msg(line)
                print(f"Desired line {line}")
                cmd_data = " ".join(line.split(" ")[1:])
                device_id, device_name = cmd_data.split(",")
                self._device_id = device_id
                return device_id
        except Exception as e:
            print(f"Error {e} reading device id trying again.")
            await uasyncio.sleep(5)
            return await self.device_id()

    async def read_msg(self, id=None) -> tuple[str, str, str]:
        """Read either a specific msg id or the most recent msg."""
        async with self.lock:
            if id is None:
                id = "N"
            await self.send_command(f"$MM R={id}")
            line = await self.sreader.readline()
            while not line.startswith("$MM"):
                print(f"looping {line}")
                uasyncio.create_task(self._line_handle(line))
                line = await self.sreader.readline()
            try:
                line = self._validate_msg(line)
                cmd_data = " ".join(line.split(" ")[1:])
                app_id, msg_data, msg_id, es = cmd_data.split(",")
                app_id = int(app_id)
                return (app_id, msg_data, msg_id)
            except Exception as e:
                print(f"Exception {e} while reading msg.")
                return None

    async def read_all_msgs(self):
        """Read all the msgs and delete as we go."""
        msg_count = await self.check_for_msgs()
        while msg_count > 0:
            print("Reading msg.")
            (app_id, msg_data, msg_id) = self.read_msg()
            if self.new_msg_callback is not None:
                self.new_msg_callback(app_id, msg_data)
                self.delete_msg(msg_id)
            msg_count = await self.check_for_msgs()
        print("Done reading all msgs")

    def is_ready(self) -> bool:
        """Returns if the modem is ready for msgs."""
        return self.modem_ready

    async def send_msg(self, app_id, data) -> str:
        """Send a message, returning the message ID.
        app_id is the application id.
        Data *must be* base64 encoded.
        """
        if not self.ready:
            raise Exception("satelite modem not ready.")
        async with self.lock:
            await self.send_command(f"$TD AI={app_id},{data}")
            line = await self.sreader.readline()
            while (not line.startswith("$TD")) and (not line.startswith("$TD SENT")):
                uasyncio.create_task(self._line_handle(line))
                line = await self.sreader.readline()
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
            except Exception as e:
                raise e

    def last_rt_time(self) -> str:
        """Last received test time (from swarm)."""
        return self.last_date

    def sleep_until_rx_watch(self):
        """Configure RX pin goes hi."""
        try:
            self.lock.acquire()
            uasyncio.create_task(self.send_command("GP 6"))
            line = await self.sreader.readline()
            while (not line.startswith("$GP")):
                uasyncio.create_task(self._line_handle(line))
                line = await self.sreader.readline()
        finally:
            self.lock.release()
