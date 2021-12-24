import uasyncio
from machine import UART

class Satelite():

    def __init__(self, uart_id,
                 new_msg_callback=None,
                 msg_acked_callback=None,
                 error_callback=None,
                 txing_callback=None,
                 txing_pin=None,
                 uart_tx=11,
                 uart_rx=12,
                 myconn=None):
        """Initialize a connection to the satelite modem. Allows setting myconn for testing.
        uart_id is the ID of the uart controller to use
        new_msg_callback should take app_id (str) and data (str, base64 encoded)
        msg_acked_callback takes a str of msgid
        error_callback takes a str of error string
        txing_callback takes bool for active TX or false for TX finished
        txing_pin is an optional int for a pin to monitor for TXing
        uart_tx is the UART tx pin
        uart_rx is the UART rx pin
        """
        print("Constructing connection to M138.")
        if myuart is None:
            self.conn = UART(uart_id)
        else:
            self.conn = myconn
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
        """Update the last rt time."""
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
        """Send a command to the modem. Calculates the checksum."""
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
        """Check msgs, returns number of messages."""
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
        """Read either a specific msg id or the most recent msg."""
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
        app_id is the application id.
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
