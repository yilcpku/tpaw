import tempfile
from pathlib import Path
import unittest
from tpaw_lab.storage import Store


def local_temp():
    workspace=Path(__file__).resolve().parents[1]
    parent=(workspace/".private"/"test-temp").resolve()
    if not parent.is_relative_to(workspace) or parent==workspace:
        raise ValueError("Test cleanup target escapes the workspace")
    parent.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


class StorageTests(unittest.TestCase):
    def test_original_native_reference_is_immutable(self):
        with local_temp() as tmp:
            store=Store(Path(tmp));store.put('baselines',{'name':'Pinned native','request_sha256':'original'},'native-v1')
            with self.assertRaises(ValueError):
                store.put('baselines',{'name':'Edited native','request_sha256':'new'},'native-v1')
    def test_frozen_data_cannot_change_under_saved_scenario(self):
        with local_temp() as tmp:
            store=Store(Path(tmp))
            store.put("data",{"source_sha256":"original","rows":[1,2,3]},"history-v1")
            store.put("scenarios",{"name":"unit test","dataset":"history-v1"},"test")
            with self.assertRaises(ValueError):
                store.put("data",{"source_sha256":"new","rows":[4,5,6]},"history-v1")
            self.assertEqual(store.get("data","history-v1")["rows"],[1,2,3])
            self.assertEqual(store.put("data",{"source_sha256":"original","rows":[1,2,3]},"history-v1"),"history-v1")

    def test_record_identifier_cannot_escape_private_root(self):
        with local_temp() as tmp:
            store=Store(Path(tmp))
            for key in ("../escape","a/b","a\\b","C:\\escape","a%2fb"):
                with self.assertRaises(ValueError):
                    store.put("scenarios",{"name":"test"},key)


if __name__=="__main__":
    unittest.main()
