class FakeUART():
    def __init__(self, lines=None):
        print(f"Making fake uart with lines {lines}")
        self.baudrate = None
        self.tx = None
        self.rx = None
        if lines is None:
            lines = []
        self.lines = lines
        self.sent_lines = []
        pass

    def init(self, baudrate=0, tx=None, rx=None):
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx

    async def readline(self):
        line = self.lines.pop(0)
        print(f"Serving fake line {line}")
        return line

    def len(self):
        return len(self.lines)

    def write(self, cmd):
        print(f"Sendig fake line {cmd}")
        self.sent_lines.append(cmd)

    async def drain(self, *args):
        return True

    async def flush(self):
        return True
