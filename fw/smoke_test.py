import unittest
from Satellite import Satellite
from UARTBluetooth import UARTBluetooth
import uasyncio
from test_utils import FakeUART


class TestStringMethods(unittest.TestCase):

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')


class SatelliteSmokeTest(unittest.TestCase):

    def test_fake_start(self):
        conn = FakeUART()
        s = Satellite(1, myconn=conn)
        self.assertEqual(s.conn, conn)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)

    def test_fake_init_waits(self):
        conn = FakeUART(lines=["butts"])
        s = Satellite(1, myconn=conn, delay=0)
        uasyncio.run(s._modem_ready())
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)
        self.assertEqual(s.ready, False)

    def test_fake_modem_ready(self):
        conn = FakeUART(lines=[
            "$M138 BOOT,RUNNING*49"])
        s = Satellite(1, myconn=conn, delay=0)
        uasyncio.run(s._modem_ready())
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)
        self.assertEqual(s.ready, False)
        self.assertEqual(s.modem_started, True)

    def test_fake_modem_fully_ready(self):
        conn = FakeUART(lines=[
            "$M138 BOOT,RUNNING*49", "$M138 DATETIME*35"])
        s = Satellite(1, myconn=conn, delay=0)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)
        uasyncio.run(s._modem_ready())
        self.assertEqual(s.modem_started, True)
        uasyncio.run(s._modem_ready())
        self.assertEqual(uasyncio.run(s._modem_ready()), True)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)
        self.assertEqual(s.modem_started, True)

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
        s = Satellite(1, myconn=conn, delay=0, client_ready=client_ready, max_retries=1)
        s.start()
        try:
            uasyncio.get_event_loop().run_until_complete(s.satelite_task)
        except Exception as e:
            print(f"error in main loop {e}")
        print("pandas")
        self.assertEqual(conn.baudrate, 115200)
        print("buad")
        self.assertEqual(conn.tx, 26)
        self.assertEqual(conn.rx, 27)
        print(f"k.... {s.modem_started}")
        self.assertEqual(s.modem_started, True)
        print("k2")
        print("k3")

    def test_read_msg(self):
        conn = FakeUART(lines=[
            "butts",
            "$M138 DATETIME*35",
            "$MM 120,1337DEADBEEF,1,1*39"])
        s = Satellite(1, myconn=conn, delay=0, max_retries=1)
        app_id, msg_data, msg_id = uasyncio.run(s.read_msg())
        self.assertEqual(app_id, 120)
        self.assertEqual(msg_data, "1337DEADBEEF")
        self.assertEqual(msg_id, "1")


class FakeBLE():
    def __init__(self):
        self.hanlder = None
        self.services = None
        self.name = None
        self._active = None

    def irq(self, handler):
        self.hanlder = handler

    def gatts_register_services(self, services):
        self.services = services
        return ((None, None), None)

    def gatts_notify(self, conn_handle, value_handle, data):
        return

    def gap_advertise(self, interval, param, resp_data=None):
        return

    def active(self, act):
        self._active = act

    def config(self, gap_name=None):
        self.name = gap_name

    def gatts_set_buffer(self, handle, rxbuf, b):
        return


class UARTSmokeTest(unittest.TestCase):

    def test_construct(self):
        print("Starting test.")
        f = FakeBLE()
        print(f"Made fake ble {f}")
        try:
            b = UARTBluetooth("test", ble=f)
        except Exception as e:
            print("meeps :/")
            print("Error")
            print(e)
            raise e
        print(f"Created {b}")
