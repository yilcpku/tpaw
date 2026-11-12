import {Button} from '@astryxdesign/core/Button'
import {TextInput} from '@astryxdesign/core/TextInput'
import {Selector} from '@astryxdesign/core/Selector'
import DecimalInput from './DecimalInput'

export type CashflowRow={label?:string;kind:string;reference?:string;start:string|number;duration_months?:number;
  every_months?:number;amount:number;basis?:string;include_in_lifestyle?:boolean;source_id?:string}
const kinds=[{value:'net_savings',label:'工作净储蓄'},{value:'retirement_income',label:'另填退休收入'}]

export default function Cashflows({rows,onChange,evaluation}: {rows:CashflowRow[];onChange:(rows:CashflowRow[])=>void;evaluation:string}) {
  const change=(i:number,patch:Partial<CashflowRow>)=>onChange(rows.map((row,j)=>i===j?{...row,...patch}:row))
  return <section><h2>储蓄与收入明细</h2><p className="small">金额统一为评估月购买力的实际人民币，模拟中随CPI调整。工作净储蓄已扣税与工作生活费，实际退休月起停止；另外填写的退休收入只在退休后生效。</p>
    <p>{rows.length} 条现金流 · 点击一行展开编辑</p>
    <div className="flow-list">{rows.map((row,i)=><details key={i}><summary>{row.label||kinds.find(k=>k.value===row.kind)?.label} · {row.reference==='retirement'?`退休${Number(row.start)>=0?'+':''}${row.start}月`:row.start} · ¥{Number(row.amount).toLocaleString()}</summary>
      <div className="fields"><TextInput label="项目说明" value={row.label||''} onChange={v=>change(i,{label:v})}/>
        <Selector label="现金流类别" value={row.kind} options={kinds} onChange={v=>change(i,{kind:v})} width="100%"/>
        <Selector label="日期基准" value={row.reference||'calendar'} options={[{value:'calendar',label:'固定日历月份'},{value:'retirement',label:'相对实际退休月'}]} onChange={v=>change(i,{reference:v,start:v==='calendar'?evaluation:0})} width="100%"/>
        {row.reference==='retirement'?<DecimalInput label="距退休月的月数（可为负）" value={Number(row.start)} integer onChange={start=>change(i,{start})}/>:<TextInput label="开始月份 / YYYY-MM" value={String(row.start)} onChange={start=>change(i,{start})}/>}
        <DecimalInput label={row.basis==='nominal'?'旧名义金额 / 人民币（运行时折算）':'每次金额 / 实际人民币'} value={row.amount} onChange={amount=>change(i,{amount,basis:'real'})}/>
        <DecimalInput label="持续月数（一次性填1）" value={row.duration_months??1} integer onChange={duration_months=>change(i,{duration_months})}/>
        <DecimalInput label="每隔几个月发生" value={row.every_months??1} integer onChange={every_months=>change(i,{every_months})}/>

      </div><Button label="删除此行" variant="ghost" onClick={()=>onChange(rows.filter((_,j)=>j!==i))}/></details>)}</div>
    <Button label="添加现金流" variant="secondary" onClick={()=>onChange([...rows,{label:'新增净储蓄',kind:'net_savings',reference:'calendar',start:evaluation,duration_months:1,every_months:1,amount:0,basis:'real',include_in_lifestyle:false}])}/>
  </section>
}
