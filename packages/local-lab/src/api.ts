export const hosted=import.meta.env.VITE_TPAW_HOSTED==='1'
export function encodeJson(body:unknown){return JSON.stringify(body,(_key,value)=>{
  if(typeof value==='number'&&!Number.isFinite(value))throw new Error('请填写有效数字，再运行或保存情景。')
  return value
})}
export async function api<T>(path:string,body?:unknown):Promise<T>{
  const r=await fetch(import.meta.env.BASE_URL+'api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:encodeJson(body)})
  if(r.status===401&&hosted)window.dispatchEvent(new Event('tpaw-session-expired'))
  if(!r.headers.get('content-type')?.includes('application/json'))throw new Error(`服务器返回了网页响应（HTTP ${r.status}），请刷新或重新登录后重试。`)
  const data=await r.json().catch(()=>{throw new Error('服务器响应不完整，请重试。')})
  if(!r.ok){if(r.status===401&&hosted)window.dispatchEvent(new Event('tpaw-session-expired'));throw new Error(data.error||'请求失败')}
  return data
}
