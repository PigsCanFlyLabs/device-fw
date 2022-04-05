import micropython


class DisplayWrapper():
    def __init__(self, display=None):
        self.display = display
        # Make a wrapper so as to avoid alloc.
        self._write_ref = self.write
        self._do_write_ref = self.do_write
        self.length = 15
        self.space = 10

    def write(self, txt):
        if self.display is None:
            print("No display, skipping")
            print(txt)
            return
        else:
            print("Scheduling display update")
            micropython.schedule(self._do_write_ref, txt)

    def do_write(self, txt):
        print("Doing write for:")
        print(txt)
        self.display.fill(0)
        i = 0
        while i < len(txt):
            self.display.text(txt[i:(i + self.length)], 0, int((i * self.space / self.length)))
            i = i + self.length
        self.display.show()
