"""Single-owner hosted authentication; credentials never enter the source tree."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from .storage import private_root


def password_record(password:str)->dict:
    if not isinstance(password,str) or not 8<=len(password)<=256:
        raise ValueError('密码需为8至256个字符。')
    salt=secrets.token_bytes(16)
    value=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return {'algorithm':'scrypt-16384-8-1','salt':salt.hex(),'value':value.hex()}


def password_matches(password:str,record:dict)->bool:
    if not isinstance(password,str) or len(password)>256:return False
    if record['algorithm']!='scrypt-16384-8-1':raise ValueError('Unknown password hash')
    value=hashlib.scrypt(password.encode(),salt=bytes.fromhex(record['salt']),n=16384,r=8,p=1,dklen=32)
    return hmac.compare_digest(value.hex(),record['value'])


class AuthStore:
    def __init__(self,path:Path,clock=time.time):
        self.path=path.resolve(strict=True);private_root(self.path.parent)
        self.account=json.loads(self.path.read_text(encoding='utf-8'))
        self.clock=clock;self.sessions={};self.failures=[];self.lock=threading.RLock()

    @staticmethod
    def create(path:Path,username:str,password:str):
        if not username or len(username)>80:raise ValueError('Invalid username')
        private_root(path.parent)
        if path.is_symlink():raise ValueError('Credential file cannot be a link')
        with path.open('x',encoding='utf-8') as handle:
            os.chmod(path,0o600)
            json.dump({'username':username,'password':password_record(password),'must_change_password':True},handle)

    def _issue(self):
        now=self.clock()
        self.sessions={key:expiry for key,expiry in self.sessions.items() if expiry>now}
        # Bound memory and keep the most recent owner sessions.
        while len(self.sessions)>=16:self.sessions.pop(next(iter(self.sessions)))
        token=secrets.token_urlsafe(32);self.sessions[token]=now+8*3600
        return token

    def valid(self,token):
        with self.lock:return bool(token) and self.sessions.get(token,0)>self.clock()

    def login(self,username,password):
        with self.lock:
            now=self.clock();self.failures=[t for t in self.failures if t>now-300]
            if len(self.failures)>=8:raise ValueError('尝试次数过多，请5分钟后再试。')
            matched=password_matches(password,self.account['password'])
            if not isinstance(username,str) or not hmac.compare_digest(username.encode(),self.account['username'].encode()) or not matched:
                self.failures.append(now);raise ValueError('用户名或密码不正确。')
            self.failures=[];return self._issue()

    def logout(self,token):
        with self.lock:self.sessions.pop(token,None)

    def change_password(self,token,current,new):
        with self.lock:
            if not self.valid(token):raise ValueError('登录已过期。')
            if not password_matches(current,self.account['password']):raise ValueError('当前密码不正确。')
            if new==current:raise ValueError('请设置不同于临时密码的新密码。')
            updated={**self.account,'password':password_record(new),'must_change_password':False}
            private_root(self.path.parent)
            temp=self.path.with_name(self.path.name+'.'+secrets.token_hex(8)+'.tmp')
            with temp.open('x',encoding='utf-8') as handle:
                os.chmod(temp,0o600);json.dump(updated,handle);handle.flush();os.fsync(handle.fileno())
            os.replace(temp,self.path);self.account=updated;self.sessions.clear()
            return self._issue()
