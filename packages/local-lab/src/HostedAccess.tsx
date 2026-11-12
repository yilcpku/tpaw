import {useEffect,useState,type ReactNode} from 'react'
import {Theme} from '@astryxdesign/core/theme'
import {neutralTheme} from '@astryxdesign/theme-neutral/built'
import {Button} from '@astryxdesign/core/Button'
import {TextInput} from '@astryxdesign/core/TextInput'
import {api,hosted} from './api'

type Access={authenticated:boolean;password_change_required:boolean}
export default function HostedAccess({children}:{children:ReactNode}){
  const [access,setAccess]=useState<Access>();const [username,setUsername]=useState('')
  const [password,setPassword]=useState('');const [next,setNext]=useState('');const [confirm,setConfirm]=useState('')
  const [changing,setChanging]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('')
  useEffect(()=>{if(!hosted)return
    const expired=()=>{setAccess({authenticated:false,password_change_required:false});setChanging(false);setPassword('');setNext('');setConfirm('');setError('登录已过期，请重新登录。')}
    window.addEventListener('tpaw-session-expired',expired)
    api<Access>('auth/status').then(setAccess).catch(e=>setError(e.message))
    return()=>window.removeEventListener('tpaw-session-expired',expired)
  },[])
  if(!hosted)return children
  const needsChange=access?.password_change_required||changing
  async function submit(){
    setError('');if(needsChange&&next!==confirm){setError('两次输入的新密码不一致。');return}
    setBusy(true)
    try{setAccess(await api<Access>(needsChange?'auth/password':'auth/login',needsChange?{current:password,new:next}:{username,password}));setPassword('');setNext('');setConfirm('');setChanging(false)}
    catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  }
  if(access?.authenticated&&!needsChange)return <Theme theme={neutralTheme} mode="light">
    <div className="account-bar"><span>已登录 · 财务输入与结果保存在你的服务器</span><Button variant="ghost" label="修改密码" onClick={()=>{setChanging(true);setError('')}}/>
      <Button variant="ghost" label="退出登录" onClick={()=>api<Access>('auth/logout',{}).then(setAccess).catch(e=>setError(e.message))}/></div>{error&&<p role="alert">{error}</p>}{children}
  </Theme>
  return <Theme theme={neutralTheme} mode="light"><main className="auth-page"><section><span className="eyebrow">TPAW / PRIVATE PLANNING</span>
    <h1>{needsChange?'修改登录密码':'登录退休规划实验室'}</h1><p>{access?.password_change_required?'首次登录请先修改临时密码，再访问个人情景。':'仅授权账户可访问。财务输入与结果通过 HTTPS 保存在你的服务器。'}</p>
    {!access&&!error?<p>正在检查登录状态…</p>:<form onSubmit={e=>{e.preventDefault();void submit()}}>
      {!needsChange&&<TextInput label="用户名" value={username} autoComplete="username" onChange={setUsername}/>}
      <TextInput label={needsChange?'当前密码':'密码'} type="password" value={password} autoComplete="current-password" onChange={setPassword}/>
      {needsChange&&<><TextInput label="新密码" type="password" value={next} autoComplete="new-password" description="8至256个字符，并与临时密码不同。" onChange={setNext}/><TextInput label="再次输入新密码" type="password" value={confirm} autoComplete="new-password" onChange={setConfirm}/></>}
      {error&&<p role="alert">{error}</p>}<Button label={needsChange?'保存新密码':'登录'} variant="primary" isLoading={busy} onClick={submit}/>
      {changing&&!access?.password_change_required&&<Button label="返回规划" variant="ghost" onClick={()=>{setChanging(false);setPassword('');setNext('');setConfirm('')}}/>}
    </form>}
  </section></main></Theme>
}
