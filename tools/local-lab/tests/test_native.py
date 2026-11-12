import ctypes
import unittest
from tpaw_lab.native import verify_abi,Params,Arrays,Advanced


class NativeLayoutTests(unittest.TestCase):
    def test_bridge_matches_pinned_bindgen_layout(self):
        verify_abi()
        self.assertEqual(ctypes.sizeof(Params),136)
        self.assertEqual(ctypes.sizeof(Arrays),88)
        self.assertEqual(Advanced.strategy.offset,48)
