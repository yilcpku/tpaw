import io
import json
from types import SimpleNamespace
from email.message import Message
import unittest
from unittest.mock import Mock
from serve_hosted import HostedHandler


def handler(path,token_valid=False,must_change=True,origin='https://unit-test.invalid'):
    h=object.__new__(HostedHandler);h.path=path;h.headers=Message()
    h.headers['Host']='unit-test.invalid';h.headers['Origin']=origin;h.headers['Content-Type']='application/json'
    h.server=SimpleNamespace(public_host='unit-test.invalid',origin='https://unit-test.invalid',path_prefix='/tpaw/',
        auth=SimpleNamespace(valid=lambda token:token_valid,account={'must_change_password':must_change}))
    h.auth_json=Mock();h.json=Mock();return h


class HostedAccessTests(unittest.TestCase):
    def test_private_reads_are_refused_before_login_or_password_change(self):
        for path in ('/api/scenarios','/api/baselines/native','/api/diagnostics','/api/data-audit/private'):
            h=handler(path);h.do_GET();self.assertEqual(h.auth_json.call_args.args[0],401)
            h=handler(path,token_valid=True);h.do_GET();self.assertEqual(h.auth_json.call_args.args[0],403)

    def test_public_auth_status_never_contains_identity_or_financial_records(self):
        h=handler('/api/auth/status');h.do_GET()
        self.assertEqual(h.auth_json.call_args.args,(200,{'authenticated':False,'password_change_required':False}))

    def test_cross_origin_password_change_is_rejected_without_reading_body(self):
        h=handler('/api/auth/password',token_valid=True,origin='https://another.invalid');h.rfile=Mock()
        h.do_POST();h.rfile.read.assert_not_called();self.assertEqual(h.auth_json.call_args.args[0],403)

    def test_expired_password_change_returns_login_challenge(self):
        h=handler('/api/auth/password');payload=b'{}'
        h.headers['Content-Length']=str(len(payload));h.rfile=io.BytesIO(payload)
        h.do_POST();self.assertEqual(h.auth_json.call_args.args[0],401)

    def test_run_limit_is_enforced_before_parent_simulation(self):
        h=handler('/api/run',token_valid=True,must_change=False);h.server.max_runs=200
        payload=json.dumps({'name':'generic test','runs':201}).encode();h.headers['Content-Length']=str(len(payload));h.rfile=io.BytesIO(payload)
        h.do_POST();self.assertEqual(h.auth_json.call_args.args[0],400)
