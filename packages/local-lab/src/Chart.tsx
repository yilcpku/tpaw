export type Profile = {age: number; p5: number; p50: number; p95: number;months_summed?:number}

export default function Chart({rows,caption,footnote,partialEndLabel='100岁'}: {rows: Profile[];caption?: string;footnote?: string;partialEndLabel?:string}) {
  const partial=rows.filter(r=>r.months_summed!==undefined&&r.months_summed<12)
  const complete=rows.filter(r=>r.months_summed===undefined||r.months_summed===12)
  const partialNote=partial.map(r=><p className="small" key={r.age}>末段从 {r.age.toFixed(2)} 岁起仅 {r.months_summed} 个月，在{partialEndLabel}截断；实际累计支出5% /50% /95%为 {['p5','p50','p95'].map(k=>'¥'+Math.round(r[k as 'p5'|'p50'|'p95']).toLocaleString()).join(' / ')}，不作为完整年度点连接，也不外推终点以后。</p>)
  if(!complete.length)return <figure><figcaption>{caption||'剩余模拟不足一年：实际累计支出'}</figcaption>{partialNote}</figure>
  rows=complete
  const width=820,height=280,left=80,top=20,bottom=44,right=24
  const max=Math.max(1,...rows.map(r=>r.p95))*1.08
  const minAge=rows[0].age,maxAge=rows.at(-1)!.age
  const x=(age:number)=>left+(age-minAge)/Math.max(1,maxAge-minAge)*(width-left-right)
  const y=(value:number)=>height-bottom-value/max*(height-bottom-top)
  const path=(key:'p5'|'p50'|'p95')=>rows.map((r,i)=>`${i?'L':'M'}${x(r.age)},${y(r[key])}`).join(' ')
  return <figure><figcaption>{caption||'年度实际日常支出（含预算预提，准备金一次性支取另计）· 人民币'}</figcaption>
    <svg role="img" aria-label="按年龄显示支出的5%、50%、95%逐点分位数" viewBox={`0 0 ${width} ${height}`}>
      {[0,.25,.5,.75,1].map(v=><g key={v}><line x1={left} x2={width-right} y1={y(v*max)} y2={y(v*max)} className="gridline"/><text x={left-12} y={y(v*max)+4} textAnchor="end">{Math.round(v*max).toLocaleString()}</text></g>)}
      {[minAge,(minAge+maxAge)/2,maxAge].map(age=><text key={age} x={x(age)} y={height-14} textAnchor="middle">{age.toFixed(0)} 岁</text>)}
      <path d={path('p5')} className="range"/><path d={path('p95')} className="range"/><path d={path('p50')} className="median"/>
    </svg>{partialNote}<p className="small">{footnote||'实线：中位数；虚线：5% 和 95%。逐点分位数不代表一条连续人生路径。工作期仅记净储蓄，未把已扣除的工作生活费再次记为退休支出。'}</p></figure>
}
