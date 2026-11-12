import {Button} from '@astryxdesign/core/Button'
import {TextInput} from '@astryxdesign/core/TextInput'
import {Selector} from '@astryxdesign/core/Selector'
import DecimalInput from './DecimalInput'

export type CashflowRow={label?:string;kind:string;reference?:string;start:string|number;duration_months?:number;
  every_months?:number;amount:number;basis?:string;include_in_lifestyle?:boolean;source_id?:string}
const kinds=[{value:'net_savings',label:'日期净储蓄（已扣工作支出/税费）'},{value:'retirement_income',label:'退休收入'},
  {value:'essential',label:'必要额外费用'},{value:'discretionary',label:'可调整额外费用'},
  {value:'budget',label:'年度日常预算（替换目标）'},{value:'reserve_draw',label:'准备金支取'}]

export default function Cashflows({rows,onChange,evaluation}: {rows:CashflowRow[];onChange:(rows:CashflowRow[])=>void;evaluation:string}) {
  const change=(i:number,patch:Partial<CashflowRow>)=>onChange(rows.map((row,j)=>i===j?{...row,...patch}:row))
  return <section><h2>阶段现金流与一次性支取</h2><p className="small">日期净储蓄已扣当期生活费和税费，奖金与通知期工资只计一次。年度预算行替换比较目标和现金底线，不会新增一笔费用；额外费用只填写原有一般支出之外的增量。准备金支取不会再从核心资产扣一次。</p>
    <p>{rows.length} 条现金流 · 点击一行展开编辑</p>
    <div className="flow-list">{rows.map((row,i)=><details key={i}><summary>{row.label||kinds.find(k=>k.value===row.kind)?.label} · {row.reference==='retirement'?`退休${Number(row.start)>=0?'+':''}${row.start}月`:row.start} · ¥{Number(row.amount).toLocaleString()}</summary>
      <div className="fields"><TextInput label="项目说明" value={row.label||''} onChange={v=>change(i,{label:v})}/>
        <Selector label="现金流类别" value={row.kind} options={kinds} onChange={v=>change(i,{kind:v})} width="100%"/>
        <Selector label="日期基准" value={row.reference||'calendar'} options={[{value:'calendar',label:'固定日历月份'},{value:'retirement',label:'相对实际退休月'}]} onChange={v=>change(i,{reference:v,start:v==='calendar'?evaluation:0})} width="100%"/>
        {row.reference==='retirement'?<DecimalInput label="距退休月的月数（可为负）" value={Number(row.start)} integer onChange={start=>change(i,{start})}/>:<TextInput label="开始月份 / YYYY-MM" value={String(row.start)} onChange={start=>change(i,{start})}/>}
        <DecimalInput label={row.kind==='budget'?'年度目标金额 / 人民币':'每次金额 / 人民币'} value={row.amount} onChange={amount=>change(i,{amount})}/>
        <Selector label="金额口径" value={row.basis||'real'} options={[{value:'real',label:'基期实际人民币（随已知CPI调整）'},{value:'nominal',label:'固定名义人民币'}]} onChange={v=>change(i,{basis:v})} width="100%"/>
        <DecimalInput label="持续月数（一次性填1）" value={row.duration_months??1} integer onChange={duration_months=>change(i,{duration_months})}/>
        <DecimalInput label="每隔几个月发生" value={row.every_months??1} integer onChange={every_months=>change(i,{every_months})}/>
        {['essential','discretionary'].includes(row.kind)&&<Selector label="是否属于日常支出比较" value={row.include_in_lifestyle===false?'no':'yes'} options={[{value:'yes',label:'计入日常预算支出（增量）'},{value:'no',label:'一次性目标，单独计入总支出'}]} onChange={v=>change(i,{include_in_lifestyle:v==='yes'})} width="100%"/>}
      </div><Button label="删除此行" variant="ghost" onClick={()=>onChange(rows.filter((_,j)=>j!==i))}/></details>)}</div>
    <Button label="添加现金流" variant="secondary" onClick={()=>onChange([...rows,{label:'新增现金流',kind:'essential',reference:'calendar',start:evaluation,duration_months:1,every_months:1,amount:0,basis:'real',include_in_lifestyle:false}])}/>
  </section>
}
