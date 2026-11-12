import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tpaw_lab.auth import AuthStore,password_record,password_matches
from test_storage import local_temp


class AuthTests(unittest.TestCase):
    def test_credentials_are_salted_and_not_stored_as_plaintext(self):
        a=password_record('generic-unit-test-password');b=password_record('generic-unit-test-password')
        self.assertNotEqual(a['salt'],b['salt'])
        self.assertTrue(password_matches('generic-unit-test-password',a));self.assertFalse(password_matches('incorrect',a))
        self.assertFalse(password_matches(None,a))

    def test_initial_password_change_revokes_old_sessions_and_persists(self):
        with local_temp() as tmp:
            path=Path(tmp)/'account.json';AuthStore.create(path,'test-owner','generic-initial-password')
            auth=AuthStore(path);a=auth.login('test-owner','generic-initial-password');b=auth.login('test-owner','generic-initial-password')
            self.assertTrue(auth.account['must_change_password'])
            new=auth.change_password(a,'generic-initial-password','generic-replacement-password')
            self.assertFalse(auth.valid(a));self.assertFalse(auth.valid(b));self.assertTrue(auth.valid(new))
            self.assertFalse(AuthStore(path).account['must_change_password'])
            self.assertNotIn('generic-initial-password',path.read_text())
            with self.assertRaises(ValueError):auth.login('test-owner','generic-initial-password')

    def test_session_expiry_logout_and_bad_password_do_not_unlock_account(self):
        with local_temp() as tmp:
            path=Path(tmp)/'account.json';AuthStore.create(path,'test-owner','generic-initial-password')
            now=[1000];auth=AuthStore(path,clock=lambda:now[0])
            a=auth.login('test-owner','generic-initial-password');auth.logout(a);self.assertFalse(auth.valid(a))
            a=auth.login('test-owner','generic-initial-password')
            with self.assertRaises(ValueError):auth.change_password(a,'wrong','generic-replacement-password')
            self.assertTrue(auth.account['must_change_password'])
            now[0]+=8*3600;self.assertFalse(auth.valid(a))
            with self.assertRaises(ValueError):auth.change_password(a,'generic-initial-password','generic-replacement-password')

    def test_login_throttle_is_bounded_and_expires(self):
        with local_temp() as tmp:
            path=Path(tmp)/'account.json';AuthStore.create(path,'test-owner','generic-initial-password')
            now=[1000];auth=AuthStore(path,clock=lambda:now[0])
            for _ in range(8):
                with self.assertRaises(ValueError):auth.login('test-owner','wrong')
            with self.assertRaisesRegex(ValueError,'5分钟'):auth.login('test-owner','generic-initial-password')
            now[0]+=301;self.assertTrue(auth.valid(auth.login('test-owner','generic-initial-password')))
