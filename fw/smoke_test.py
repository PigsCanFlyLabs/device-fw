import unittest
from UARTBluetooth import UARTBluetooth
from Satelite import Satelite
import uasyncio

class TestStringMethods(unittest.TestCase):

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

class FakeUART():
    def __init__(self):
        self.baudrate = None
        self.tx = None
        self.rx = None
        pass
    
    def init(self, baudrate=0, tx=None, rx=None):
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx

class SateliteSmokeTest(unittest.TestCase):

    def test_fake_start(self):
        conn = FakeUART()
        s = Satelite(1, myconn=conn)
        self.assertEqual(conn.baudrate, 115200)
        self.assertEqual(conn.tx, 11)
        self.assertEqual(conn.rx, 12)
