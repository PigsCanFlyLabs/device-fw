import uasyncio

class Satelite():

    def __init__(self, uart_id,
                 new_msg_callback=None,
                 msg_acked_callback=None,
                 error_callback=None,
                 txing_callback=None,
                 txing_pin=None,
                 uart_tx=11,
                 uart_rx=12,
                 ready_callback=None,
                 myconn=None,
                 client_ready=None,
                 max_retries=-1):
        """Initialize a connection to the satelite modem. Allows setting myconn for testing.
        uart_id is the ID of the uart controller to use
        new_msg_callback should take app_id (str) and data (str, base64 encoded)
        msg_acked_callback takes a str of msgid
        error_callback takes a str of error string
        txing_callback takes bool for active TX or false for TX finished
        txing_pin is an optional int for a pin to monitor for TXing
        uart_tx is the UART tx pin
        uart_rx is the UART rx pin
        ready_callback is a callback to indicate the modem can receive msgs
        client_ready is a ThreadSafeFlag of when the client is ready.
        """
        print("Constructing connection to M138.")
        if myconn is None:
            from machine import UART
            self.conn = UART(uart_id)
        else:
            self.conn = myconn
        print(f"Using uart {self.conn}")
        self.modem_started = False
        self.transmit_ready = False
        self.new_msg_callback = new_msg_callback
        self.msg_acked_callback = msg_acked_callback
        self.error_callback = error_callback
        self.last_date = None
        self.lock = uasyncio.Lock()
        self.ready = False
        self.max_retries = max_retries
        self.ready_callback = ready_callback
        self.client_ready = client_ready
        print("Initilizing UART.")
        self.conn.init(baudrate=115200, tx=uart_tx, rx=uart_rx)
        print("Seting up satelite msg handler...")

    def start(self):
        self.satelite_task = uasyncio.create_task(self.main_loop())
        print(f"Task created for msg handles - {self.satelite_task}")

    async def main_loop(self):
        print("Waiting for satelite modem to boot.")
        while not self._modem_ready():
            await uasyncio.sleep(1)
        retries = 0
        print("Sat modem started, entering main loop.")
        while self.max_retries == -1 or retries < self.max_retries:
            print("Waiting for client to become ready...")
            await self.client_ready.wait()
            self.ready = True
            if self.ready_callback is not None:
                self.ready_callback()
            print("ready callback done.")
            await self.read_all_msgs()
            print("all queued msgs read.")
            self._enable_msg_watch()
            print("msg watch enabled.")
            try:
                while True:
                    line = self.conn.readline()
                    await self._line_handle(line)
                    await asyncio.sleep(1)
            except Exception as e:
                # If we encounter an error validate that the client is still connected
                self.ready = False
                print(f"Error in main loop {e}")
                self._disable_msg_watch()
                self.client_ready.wait()
                retries = retries + 1
        print(f"Finishing main loop with {retries}")

    def _modem_ready(self):
        """Handle messages waiting for system to boot."""
        # Note the developer docs have incorrect checksums for the boot sequence
        # so (for now) we'll support both of them.
        if self.transmit_ready and self.modem_started:
            return True
        raw_message = None
        while raw_message is None:
            try:
                raw_message = self.conn.readline()
                print(f"Read line {raw_message}")
            except Exception as e:
                print(f"Error reading line during modem boot - {e} {self.conn}")
                import time
                time.sleep(1)
        msg = self._validate_msg(raw_message)
        if raw_message == "$M138 BOOT,RUNNING*49":
            self.modem_started = True
        elif raw_message == "$M138 DATETIME*35":
            self.transmit_ready = True
            return True
        elif msg is not None:
            if msg == "$M138 BOOT,RUNNING":
                self.modem_started = True
            elif msg == "$M138 DATETIME":
                self.transmit_read = True
                return True
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
            self.transmit_read = True
        elif cmd == "$DT":
            self._update_dt(msg)
        elif cmd == "$RD":
            if self.new_msg_callback is not None:
                app_id, rssi, snr, fdev, msg_data = contents.split(",")
                # Wait until the msg call back succeeds before removing it from the modem.
                self.new_msg_callback(app_id, data)
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

    async def _enable_msg_watch(self):
        self.send("$MM N=E")

    async def _disable_msg_watch(self):
        self.send("$MM N=D")

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

        #Drop the leading $ if present
        if data[0] == '$':
            data = data[1:]

        # Drop the trailing *xx
        if data[-3] == '*':
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

    def send_command(self, data):
        """Send a command to the modem. Calculates the checksum.
        Caller should hold the lock otherwise bad things may happen.
        """
        checksum = self._checksum_formatted(data)
        cmd = f"{data}*{checksum}"
        self.conn.write(cmd)

    def del_msg(self, mid: str) -> bool:
        """Delete a message from the modem."""
        # We don't care about the response so much so just yeet it
        self.send_command(f"$MM D={mid}")

    def enable_msg_watch(self):
        """Enable msg watch."""

    async def check_for_msgs(self) -> int:
        """Check msgs, returns number of messages."""
        # We care about the response so disable the interrupt handler
        async with self.lock:
            self.send_command("MM C=U")
            line = self.conn.readline()
            while not line.startswith("$MM") or self._validate_msg(line) is None:
                print(f"un-expected msg line {line}, creatig task to handle later.")
                uasyncio.create_task(self._line_handle(line))
                line = self.conn.readline()
            try:
                line = self._validate_msg(line)
                parsed = int(line.split(" ")[1])
                print(f"We have {parsed} messages.")
                return parsed
            except Exception as e:
                print(f"Error fetching msgs... {e}")
                return -1

    async def read_msg(self, id=None) -> tuple[str, str]:
        """Read either a specific msg id or the most recent msg."""
        async with self.lock:
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

    async def read_all_msgs(self):
        """Read all the msgs and delete as we go."""
        msg_count = await self.check_for_msgs()
        while msg_count > 0:
            print("Reading msg.")
            (app_id, msg_data, msg_id) = self.read_msg()
            if self.new_msg_callback is not none:
                self.new_msg_callback(app_id, msg_data)
                self.delete_msg(msg_id)
            msg_count = await self.check_for_msgs()
        print("Done reading all msgs")

    def is_ready(self) -> bool:
        """Returns if the modem is ready for msgs."""
        return self.transmit_ready
    
    def send_msg(self, app_id, data) -> str:
        """Send a message, returning the message ID.
        app_id is the application id.
        Data *must be* base64 encoded.
        """
        if not self.ready:
            raise Exception("satelite modem not ready.")
        try:
            self.lock.acquire()
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
            self.lock.release()

    def last_rt_time(self) -> datetime:
        """Last received test time (from swarm)."""
        return self.last_date
