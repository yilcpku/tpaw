import ctypes
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tpaw_lab.native import verify_abi,Params,Arrays,Advanced,export_paths


class NativeLayoutTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Pinned DLL is Windows-only')
    def test_archived_export_refuses_dangling_output_link_before_financial_decoding(self):
        payload=b'unit-test-dll-hash-only'
        with patch.object(Path,'read_bytes',return_value=payload),patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'symbolic link'):
                export_paths({}, {},0,Path('not-loaded.dll'),hashlib.sha256(payload).hexdigest(),Path('.'),Path('.'),Path('paths.csv'))

    def test_bridge_matches_pinned_bindgen_layout(self):
        verify_abi()
        self.assertEqual(ctypes.sizeof(Params),136)
        self.assertEqual(ctypes.sizeof(Arrays),88)
        self.assertEqual(Advanced.strategy.offset,48)
