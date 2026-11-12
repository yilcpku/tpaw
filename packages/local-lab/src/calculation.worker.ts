/// <reference lib="webworker" />
import type {PyodideInterface} from 'pyodide'

const scope=self as unknown as DedicatedWorkerGlobalScope
let engine:Promise<{python:PyodideInterface;sha256:string}>|undefined
async function load(runtime:string){
  const manifest=await fetch(new URL('manifest.json',runtime)).then(r=>{if(!r.ok)throw new Error('计算引擎下载失败');return r.json()})
  const indexURL=new URL(`pyodide/${manifest.pyodide}/`,runtime).href
  const {loadPyodide}=await import(/* @vite-ignore */new URL('pyodide.mjs',indexURL).href)
  const python:PyodideInterface=await loadPyodide({indexURL,packageBaseUrl:indexURL,stdout:()=>{},stderr:()=>{}})
  const response=await fetch(new URL(manifest.archive,runtime));if(!response.ok)throw new Error('模型下载失败')
  const bytes=await response.arrayBuffer()
  const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('')
  if(sha256!==manifest.sha256)throw new Error('模型完整性校验失败，请刷新页面')
  python.unpackArchive(bytes,'zip');await python.runPythonAsync('from tpaw_lab.browser import run_browser')
  return {python,sha256}
}
scope.onmessage=async event=>{
  try{
    scope.postMessage({kind:'progress',value:0,label:'正在准备浏览器引擎（首次下载约14 MB）…'})
    engine??=load(event.data.runtime)
    const {python,sha256}=await engine
    python.globals.set('payload_json',JSON.stringify({...event.data.payload,engine_sha256:sha256}))
    python.globals.set('report_progress',(value:number)=>scope.postMessage({kind:'progress',value,label:'正在浏览器计算…'}))
    try{const result=await python.runPythonAsync('run_browser(payload_json, report_progress)');scope.postMessage({kind:'done',result:JSON.parse(result)})}
    finally{python.globals.delete('payload_json');python.globals.delete('report_progress')}
  }catch(error){engine=undefined;const detail=error instanceof Error?error.message.split('\n').filter(Boolean).at(-1):'';scope.postMessage({kind:'error',message:'浏览器计算未完成。'+(detail||'请检查输入后重试。')})}
}
