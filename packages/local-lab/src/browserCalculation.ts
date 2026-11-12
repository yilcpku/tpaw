import {api,encodeJson} from './api'
let worker:Worker|undefined
let pending:((reason:Error)=>void)|undefined
let generation=0
const inputs=new Map<string,unknown>()
export function cancelCalculation(){generation++;worker?.terminate();worker=undefined;pending?.(new Error('已取消计算。'));pending=undefined}
export function clearCalculation(){cancelCalculation();inputs.clear()}
export async function calculate<T>(scenario:{dataset:string},progress:(value:number,label:string)=>void):Promise<T>{
  encodeJson(scenario)
  if(!scenario.dataset)throw new Error('请选择已核验的历史数据。')
  if(pending)throw new Error('请等待当前计算或先取消。')
  progress(0,'正在读取已登录账户的数据…')
  const current=generation
  const data=inputs.get(scenario.dataset)??await api('browser-inputs/'+scenario.dataset)
  if(current!==generation)throw new Error('已取消计算。')
  inputs.set(scenario.dataset,data)
  worker??=new Worker(new URL('./calculation.worker.ts',import.meta.url),{type:'module'})
  return new Promise<T>((resolve,reject)=>{
    pending=reject
    worker!.onmessage=event=>{
      const m=event.data
      if(m.kind==='progress')progress(m.value,m.label)
      else {pending=undefined;if(m.kind==='done')resolve(m.result);else{worker?.terminate();worker=undefined;reject(new Error(m.message))}}
    }
    worker!.onerror=()=>{pending=undefined;worker?.terminate();worker=undefined;reject(new Error('浏览器计算引擎无法启动，请刷新页面后重试。'))}
    worker!.postMessage({runtime:new URL(import.meta.env.BASE_URL+'runtime/',location.origin).href,payload:{scenario,inputs:data,model_version:'retirement-plans-real-cny-v1'}})
  })
}
