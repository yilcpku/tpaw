import {Button} from '@astryxdesign/core/Button'
import {TextInput} from '@astryxdesign/core/TextInput'
import {Selector} from '@astryxdesign/core/Selector'
import DecimalInput from './DecimalInput'

export type RetirementPlan={id:string;name:string;kind:'fixed'|'window';date?:string;start?:string;end?:string;target_annual?:number}
export function addMonths(month:string,count:number){
  const [year,m]=month.split('-').map(Number);const total=year*12+m-1+count
  return `${Math.floor(total/12)}-${String(total%12+1).padStart(2,'0')}`
}
export default function RetirementPlans({plans,onChange,evaluation,budget}:{plans:RetirementPlan[];onChange:(plans:RetirementPlan[])=>void;evaluation:string;budget:number}){
  const change=(id:string,patch:Partial<RetirementPlan>)=>onChange(plans.map(p=>p.id===id?{...p,...patch}:p))
  return <div className="retirement-plans"><p className="small">各方案独立运行并共享市场抽样，最多比较8个。区间从开始月起每月检查，达标后进入通知期；最迟在区间末月退休。</p>
    {plans.map((p,i)=><div className="retirement-plan" key={p.id}><div className="plan-heading"><strong>方案 {i+1}</strong><Button label={`删除方案 ${i+1}`} variant="ghost" isDisabled={plans.length===1} onClick={()=>onChange(plans.filter(x=>x.id!==p.id))}/></div><div className="fields">
      <TextInput label={`方案 ${i+1} 名称`} value={p.name} onChange={name=>change(p.id,{name})}/>
      <Selector label={`方案 ${i+1} 类型`} value={p.kind} options={[{value:'fixed',label:'固定退休时间'},{value:'window',label:'时间段＋目标消费'}]} onChange={kind=>change(p.id,{kind:kind as RetirementPlan['kind'],date:p.date||addMonths(evaluation,24),start:p.start||addMonths(evaluation,12),end:p.end||addMonths(evaluation,36),target_annual:p.target_annual??budget})} width="100%"/>
      {p.kind==='fixed'?<TextInput label={`方案 ${i+1} 固定退休月 / YYYY-MM`} value={p.date||''} onChange={date=>change(p.id,{date})}/>:<>
        <TextInput label={`方案 ${i+1} 开始月 / YYYY-MM`} value={p.start||''} onChange={start=>change(p.id,{start})}/>
        <TextInput label={`方案 ${i+1} 结束月 / YYYY-MM`} value={p.end||''} onChange={end=>change(p.id,{end})}/>
        <DecimalInput label={`方案 ${i+1} 目标年消费 / 实际人民币`} value={p.target_annual??budget} description="扣除退休一次性支取后，预测退休首月日常消费×12达到此数即触发。" onChange={target_annual=>change(p.id,{target_annual})}/>
      </>}
    </div></div>)}
    <Button label="添加退休方案" variant="secondary" isDisabled={plans.length>=8} onClick={()=>onChange([...plans,{id:crypto.randomUUID(),name:`方案 ${plans.length+1}`,kind:'fixed',date:addMonths(evaluation,24)}])}/>
  </div>
}
