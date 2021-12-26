import unittest
from UARTBluetooth import UARTBluetooth
from Satelite import Satelite
import uasyncio

class TestStringMethods(unittest.TestCase):

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

class FakeUART():
    def __init__(self, lines=[]):
        print(f"Making fake uart with lines {lines}")
        self.baudrate = None
        self.tx = None
        self.rx = None
        self.lines = lines
        self.sent_lines = []
        pass
    
    def init(self, baudrate=0, tx=None, rx=None):
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx

    def readline(self):
        l = self.lines.pop(0)
        print(f"Serving fake line {l}")
        return l

    def write(self, cmd):
        print(f"Sendig fake line {cmd}")
        self.sent_lines.append(cmd)

class SateliteSmokeTest(unittest.TestCase):

    def test_fake_start(self):
        conn = FakeUART()
        s = Satelite(1, myconn=conn)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)

    def test_fake_init_waits(self):
        conn = FakeUART(lines=["butts"])
        s = Satelite(1, myconn=conn)
        s._modem_ready()
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)
        self.assertEqual(s.ready, False)

    def test_fake_modem_ready(self):
        conn = FakeUART(lines=[
            "$M138 BOOT,RUNNING*49"])
        s = Satelite(1, myconn=conn)
        s._modem_ready()
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)
        self.assertEqual(s.ready, False)
        return True
        self.assertEqual(s.modem_started, True)

    def test_fake_modem_fully_ready(self):
        conn = FakeUART(lines=[
            "$M138 BOOT,RUNNING*49", "$M138 DATETIME*35"])
        client_ready = uasyncio.Event()
        s = Satelite(1, myconn=conn, client_ready=client_ready)
        self.assertEqual(s._modem_ready(), False)
        self.assertEqual(s._modem_ready(), True)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)
        self.assertEqual(s.modem_started, True)
        self.assertEqual(s.transmit_ready, True)

    def test_fake_satelite_fully_ready(self):
        conn = FakeUART(lines=[
            # Junk tp be ignored
            "hi",
            "",
            "butts",
            # Modem hello
            "$M138 BOOT,RUNNING*49",
            "$M138 DATETIME*35",
            # I have no msgs queued
            "$MM 0*10"]
        )
        print(f"Fake uart {conn}")
        client_ready = uasyncio.ThreadSafeFlag()
        client_ready.set()
        s = Satelite(1, myconn=conn, client_ready=client_ready, max_retries = 1)
        import time
        s.start()
        try:
            uasyncio.get_event_loop().run_until_complete(s.satelite_task)
        except Exception as e:
            print(f"error in main loop {e}")
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)
        prit("k....")
        self.assertEqual(s.modem_started, True)
        self.assertEqual(s.transmit_ready, True)
        # We're waiting on BT to signal ready
        self.assertEqual(s.ready, False)
        client_ready.set()
        self.assertEqual(s.ready, True)
