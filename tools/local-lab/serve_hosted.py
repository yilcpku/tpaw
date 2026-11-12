"""Single-owner HTTPS-proxied deployment. Bind loopback behind the configured host."""
import argparse
from http.cookies import SimpleCookie,CookieError
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from serve import Handler
from tpaw_lab.auth import AuthStore
from tpaw_lab.storage import Store


class HostedServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,static,auth,origin,path_prefix,diagnostics_id=None,max_runs=200):
        super().__init__(address,HostedHandler)
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or not parsed.netloc or parsed.path:
            raise ValueError('Hosted origin must be an HTTPS origin without a path')
        if not path_prefix.startswith('/') or not path_prefix.endswith('/') or ';' in path_prefix:
            raise ValueError('Path prefix must start/end with slash')
        self.store=store;self.static=static.resolve();self.auth=auth;self.origin=origin
        if store.root.is_relative_to(self.static) or self.static.is_relative_to(store.root) or auth.path.is_relative_to(self.static):
            raise ValueError('Private data and credentials must be outside static files')
        self.public_host=parsed.netloc;self.path_prefix=path_prefix;self.diagnostics_id=diagnostics_id
        self.run_lock=threading.Lock();self.native_runner=None;self.max_runs=max_runs


class HostedHandler(Handler):
    server:HostedServer

    def allowed(self,static=False):
        if self.headers.get('Host')!=self.server.public_host:return False
        if static:return True
        return (self.headers.get('Origin') in (None,self.server.origin)
                and self.headers.get('Sec-Fetch-Site') not in ('cross-site','same-site'))

    def token(self):
        cookies=SimpleCookie()
        try:cookies.load(self.headers.get('Cookie',''))
        except CookieError:return None
        return cookies['tpaw_session'].value if 'tpaw_session' in cookies else None

    def auth_json(self,status,body,token=None,clear=False):
        encoded=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.headers_common()
        if token is not None or clear:
            value=token or ''
            self.send_header('Set-Cookie',f'tpaw_session={value}; Path={self.server.path_prefix}; Max-Age={0 if clear else 28800}; Secure; HttpOnly; SameSite=Strict')
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)

    def authorized(self):
        if not self.server.auth.valid(self.token()):
            self.auth_json(401,{'error':'请先登录。'});return False
        if self.server.auth.account['must_change_password']:
            self.auth_json(403,{'error':'请先修改临时密码。','password_change_required':True});return False
        return True

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/auth/status':
            if not self.allowed():self.auth_json(403,{'error':'Same origin required'});return
            valid=self.server.auth.valid(self.token())
            self.auth_json(200,{'authenticated':valid,'password_change_required':valid and self.server.auth.account['must_change_password']});return
        if path.startswith('/api/') and not self.authorized():return
        if path=='/api/status':
            if not self.allowed():self.auth_json(403,{'error':'Same origin required'});return
            from serve import FEATURES
            features=[dict(row) for row in FEATURES]
            for row in features:
                if row['name']=='本地情景保存与载入':row.update(name='服务器情景保存与载入',state='登录后访问；输入和结果保存在私有服务器目录')
                if row['name']=='原版 TPAW':row['state']='已迁移的原生快照可查看；Windows/CUDA原生重跑继续使用本机版本'
            self.json(200,{'engine':'Authenticated private server','features':features,
                'datasets':[d for d in self.server.store.list('data') if d['id']!='hk-male-period-2025'],
                'diagnostics_id':self.server.diagnostics_id,'native_control_available':False,'max_runs':self.server.max_runs});return
        super().do_GET()

    def do_POST(self):
        path=urlsplit(self.path).path
        if not self.allowed() or self.headers.get('Origin')!=self.server.origin or self.headers.get('Content-Type','').split(';')[0]!='application/json':
            self.auth_json(403,{'error':'Same-origin JSON request required'});return
        if path.startswith('/api/auth/'):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:raise ValueError('登录请求无效。')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('登录请求无效。')
                if path=='/api/auth/login':
                    token=self.server.auth.login(data.get('username'),data.get('password'))
                    self.auth_json(200,{'authenticated':True,'password_change_required':self.server.auth.account['must_change_password']},token);return
                if path=='/api/auth/logout':
                    self.server.auth.logout(self.token());self.auth_json(200,{'authenticated':False},clear=True);return
                if path=='/api/auth/password':
                    if not self.server.auth.valid(self.token()):
                        self.auth_json(401,{'error':'登录已过期，请重新登录。'});return
                    token=self.server.auth.change_password(self.token(),data.get('current'),data.get('new'))
                    self.auth_json(200,{'authenticated':True,'password_change_required':False},token);return
                self.auth_json(404,{'error':'Unknown authentication action'})
            except (ValueError,TypeError,KeyError):
                self.auth_json(400,{'error':'登录或密码更新未成功。请检查用户名、当前密码及新密码（8至256个字符），过多尝试后需等待5分钟。'})
            return
        if not self.authorized():return
        # Read/validate the bound before the parent's parser without consuming it.
        if path=='/api/run':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2*1024*1024:raise ValueError('Request size')
                body=self.rfile.read(length);scenario=json.loads(body)
                if type(scenario.get('runs')) is not int or not 1<=scenario['runs']<=self.server.max_runs:
                    raise ValueError('Path count')
            except (ValueError,TypeError,AttributeError):
                self.auth_json(400,{'error':f'服务器每次支持1至{self.server.max_runs}条路径。'});return
            # Parent handler reads the original body from this bounded in-memory view.
            import io
            original=self.rfile;self.rfile=io.BytesIO(body)
            try:super().do_POST()
            finally:self.rfile=original
            return
        super().do_POST()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--static-dir',type=Path,required=True)
    p.add_argument('--auth-file',type=Path,required=True);p.add_argument('--origin',required=True)
    p.add_argument('--path-prefix',default='/tpaw/');p.add_argument('--port',type=int,default=8766)
    p.add_argument('--diagnostics-id');p.add_argument('--max-runs',type=int,default=200);a=p.parse_args()
    server=HostedServer(('127.0.0.1',a.port),Store(a.data_dir),a.static_dir,AuthStore(a.auth_file),a.origin,a.path_prefix,a.diagnostics_id,a.max_runs)
    print('TPAW authenticated backend ready on loopback',flush=True);server.serve_forever()
