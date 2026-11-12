export const hosted=import.meta.env.VITE_TPAW_HOSTED==='1'
export async function api<T>(path:string,body?:unknown):Promise<T>{
  const r=await fetch(import.meta.env.BASE_URL+'api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const data=await r.json()
  if(!r.ok){if(r.status===401&&hosted)window.dispatchEvent(new Event('tpaw-session-expired'));throw new Error(data.error||'请求失败')}
  return data
}
