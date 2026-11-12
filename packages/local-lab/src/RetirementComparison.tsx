import {useMemo} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {Selector} from '@astryxdesign/core/Selector'
import Chart,{type Profile,type DecadeMinimum} from './Chart'
import {addMonths,type RetirementPlan} from './RetirementPlans'
export type RetirementCase={post_retirement_profiles?:Profile[];decade_minima?:DecadeMinimum[];retirement_plan?:RetirementPlan;
  retirement_timing?:{retirement_month_counts:Record<string,number>;forced_fraction:number;initial_spending_median:number;initial_spending_months_min_max:number[];withdrawal_paid_real_median:number;withdrawal_short_path_fraction:number}}
export default function RetirementComparison({cases,evaluation,selected,onSelect}:{cases:Record<string,RetirementCase>;evaluation:string;selected:string;onSelect:(id:string)=>void}){
  const entries=Object.entries(cases)
  const series=useMemo(()=>Object.entries(cases).map(([id,value])=>({id,label:value.retirement_plan?.name||id,rows:value.post_retirement_profiles||[],minima:value.decade_minima||[]})),[cases])
  function timing(value:RetirementCase){
    const counts=Object.entries(value.retirement_timing?.retirement_month_counts||{}).map(([month,n])=>[Number(month),n]).sort((a,b)=>a[0]-b[0])
    const total=counts.reduce((sum,[,n])=>sum+n,0);let cumulative=0,median=counts.at(-1)?.[0]??0
    for(const [m,n] of counts){cumulative+=n;if(cumulative>=total/2){median=m;break}}
    return {median:addMonths(evaluation,median),first:addMonths(evaluation,counts[0]?.[0]??0),last:addMonths(evaluation,counts.at(-1)?.[0]??0)}
  }
  return <div className="retirement-comparison"><h3>不同退休安排，退休后能取多少钱</h3>
    <Chart rows={series[0]?.rows||[]} series={series} caption="退休后日常取钱曲线 · 年度实际人民币" footnote="实线为中位数，虚线为5%和95%分位（95%更淡），阴影为25%–75%。只统计完整退休年度，未退休路径不按零计入；部分年龄样本只含已经退休的人数，可在选点处查看。退休一次性支取不计入本图。每十年标注的是该组年度点中最低的5%分位，不是逐路径最低值的分位数。"/>
    <div className="comparison"><table><thead><tr><th>方案</th><th>退休规则</th><th>实际退休月中位数</th><th>实际退休月范围</th><th>末月未达标退休</th><th>退休初段累计日常取钱中位数</th><th>一次性支取不足路径</th></tr></thead><tbody>
    {entries.map(([id,value])=>{const p=value.retirement_plan,t=timing(value),r=value.retirement_timing,period=r?.initial_spending_months_min_max||[12,12];return <tr key={id} className={id===selected?'selected-plan':''}><th><Button label={p?.name||id} variant="ghost" onClick={()=>onSelect(id)}/></th><td>{p?.kind==='fixed'?p.date:<>{p?.start} 至 {p?.end}<br/>目标 ¥{Math.round(p?.target_annual||0).toLocaleString()}/年</>}</td><td>{t.median}</td><td>{t.first} 至 {t.last}</td><td>{p?.kind==='fixed'?'—':((r?.forced_fraction||0)*100).toFixed(1)+'%'}</td><td>¥{Math.round(r?.initial_spending_median||0).toLocaleString()}<br/><small>{period[0]===12?'首12个月':`${period[0]}–${period[1]}个月（100岁截断，非完整首年）`}</small></td><td>{((r?.withdrawal_short_path_fraction||0)*100).toFixed(1)}%</td></tr>})}
    </tbody></table></div>
    <Selector label="查看单个方案的详细指标" value={selected} options={entries.map(([id,value])=>({value:id,label:value.retirement_plan?.name||id}))} onChange={onSelect} width="100%"/>
  </div>
}
