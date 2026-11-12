import {useEffect,useMemo,useRef,useState,type PointerEvent} from 'react'
export type Profile={age:number;p5:number;p25?:number;p50:number;p75?:number;p95:number;months_summed?:number;retired_path_count?:number;total_path_count?:number}
export type DecadeMinimum={start_age:number;end_age:number;age:number;p5:number;covered_start:number;covered_end:number;points:number}
type Series={id:string;label:string;rows:Profile[];minima?:DecadeMinimum[]}
const colors=['#315d9b','#b05f24','#238171','#8054a3','#b24669','#607c26','#397e9c','#8b624c']
const money=(n:number)=>'¥'+Math.round(n).toLocaleString()
const shortMoney=(n:number)=>n>=10000?`¥${(n/10000).toFixed(1)}万`:money(n)
export default function Chart({rows,series,caption,footnote,partialEndLabel='100岁'}:{rows:Profile[];series?:Series[];caption?:string;footnote?:string;partialEndLabel?:string}){
  const sources=useMemo(()=>series||[{id:'current',label:'当前方案',rows}],[rows,series])
  const [hidden,setHidden]=useState<string[]>([]),[selected,setSelected]=useState(0),[zoom,setZoom]=useState<[number,number]|null>(null),[drag,setDrag]=useState<[number,number]|null>(null)
  const start=useRef<number|null>(null),figure=useRef<HTMLElement>(null),[width,setWidth]=useState(820)
  useEffect(()=>{const observer=new ResizeObserver(entries=>setWidth(Math.max(280,Math.min(1100,entries[0].contentRect.width))));if(figure.current)observer.observe(figure.current);return()=>observer.disconnect()},[])
  useEffect(()=>{start.current=null;setSelected(0);setZoom(null);setDrag(null);setHidden([])},[sources])
  const curves=sources.map((s,i)=>({...s,color:colors[i%colors.length],complete:s.rows.filter(r=>r.months_summed===undefined||r.months_summed===12)})).filter(s=>!hidden.includes(s.id))
  const ages=[...new Set(sources.flatMap(s=>s.rows.filter(r=>r.months_summed===undefined||r.months_summed===12).map(r=>r.age)))].sort((a,b)=>a-b)
  const visibleAges=ages.filter((_,i)=>!zoom||(i>=zoom[0]&&i<=zoom[1]))
  const height=300,left=85,right=24,top=20,bottom=45
  const minAge=visibleAges[0]??0,maxAge=visibleAges.at(-1)??1
  const inside=(r:{age:number})=>r.age>=minAge&&r.age<=maxAge
  const max=Math.max(1,...curves.flatMap(s=>s.complete.filter(inside).map(r=>r.p95)))*1.08
  const x=(age:number)=>left+(age-minAge)/Math.max(1,maxAge-minAge)*(width-left-right)
  const y=(value:number)=>height-bottom-value/max*(height-bottom-top)
  function indexAt(e:PointerEvent<SVGSVGElement>){
    const rect=e.currentTarget.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*width
    const age=minAge+Math.max(0,Math.min(1,(px-left)/(width-left-right)))*Math.max(1,maxAge-minAge)
    return ages.reduce((best,a,i)=>(!zoom||(i>=zoom[0]&&i<=zoom[1]))&&Math.abs(a-age)<Math.abs(ages[best]-age)?i:best,zoom?.[0]??0)
  }
  const activeAge=ages[selected]??visibleAges[0]
  const path=(data:Profile[],key:'p5'|'p50'|'p95')=>data.map((r,i)=>`${i?'L':'M'}${x(r.age)},${y(r[key])}`).join(' ')
  const band=(data:Profile[])=>data.every(r=>r.p25!==undefined&&r.p75!==undefined)?data.map((r,i)=>`${i?'L':'M'}${x(r.age)},${y(r.p75!)}`).join(' ')+[...data].reverse().map(r=>`L${x(r.age)},${y(r.p25!)}`).join(' ')+'Z':''
  const partial=rows.filter(r=>r.months_summed!==undefined&&r.months_summed<12)
  const groups=[...new Set(curves.flatMap(s=>(s.minima||[]).map(m=>m.start_age)))].sort((a,b)=>a-b)
  return <figure ref={figure} className="interactive-chart"><figcaption>{caption||'年度实际日常支出 · 人民币'}</figcaption>
    {series&&<div className="chart-legend">{sources.map((s,i)=><button type="button" key={s.id} aria-pressed={!hidden.includes(s.id)} disabled={curves.length===1&&!hidden.includes(s.id)} onClick={()=>setHidden(old=>old.includes(s.id)?old.filter(id=>id!==s.id):[...old,s.id])}><i style={{background:colors[i%colors.length]}}/>{s.label}</button>)}</div>}
    {visibleAges.length>0&&<><div className="chart-toolbar"><span className="small">悬停或触摸查看 · 拖动区间放大</span><button type="button" disabled={!zoom} onClick={()=>{setZoom(null);setSelected(0)}}>重置缩放</button></div>
    <svg role="img" aria-label="交互式取钱曲线，25%至75%阴影，下方年龄滑块可用方向键查看" viewBox={`0 0 ${width} ${height}`}
      onPointerDown={e=>{if(e.button!==0)return;const i=indexAt(e);start.current=i;setSelected(i);setDrag([i,i]);e.currentTarget.setPointerCapture(e.pointerId)}}
      onPointerMove={e=>{const i=indexAt(e);setSelected(i);if(start.current!==null)setDrag([start.current,i])}}
      onPointerUp={e=>{const i=indexAt(e);if(start.current!==null&&Math.abs(i-start.current)>=2){const range:[number,number]=[Math.min(i,start.current),Math.max(i,start.current)];setZoom(range);setSelected(range[0])}start.current=null;setDrag(null)}}
      onPointerCancel={()=>{start.current=null;setDrag(null)}}>
      {[0,.25,.5,.75,1].map(v=><g key={v}><line x1={left} x2={width-right} y1={y(v*max)} y2={y(v*max)} className="gridline"/><text x={left-12} y={y(v*max)+4} textAnchor="end">{Math.round(v*max).toLocaleString()}</text></g>)}
      {[...new Set([minAge,(minAge+maxAge)/2,maxAge])].map(age=><text key={age} x={x(age)} y={height-14} textAnchor="middle">{age.toFixed(1)} 岁</text>)}
      {curves.map((s,i)=>{const data=s.complete.filter(inside);const at=s.complete.find(r=>r.age===activeAge);return <g key={s.id}>
        {data.length>0&&<><path className="quartile-band" d={band(data)} fill={s.color} opacity=".13"/>
          <path d={path(data,'p5')} className="range" style={{stroke:s.color}}/><path d={path(data,'p95')} className="range" style={{stroke:s.color,strokeOpacity:series ? .45 : 1}}/><path d={path(data,'p50')} className="median" style={{stroke:s.color}}/></>}
        {(s.minima||[]).filter(inside).map(m=><g key={m.start_age}><circle cx={x(m.age)} cy={y(m.p5)} r="4" fill={s.color}><title>{s.label}：{m.start_age}–{m.end_age}岁最低5%分位 {money(m.p5)}，在{m.age.toFixed(2)}岁</title></circle><text className="decade-label" x={Math.min(width-right-68,Math.max(left+68,x(m.age)))} y={Math.max(top+12,y(m.p5)-10-i*12)} textAnchor="middle" style={{fill:s.color}}>{m.start_age}–{m.end_age}：{shortMoney(m.p5)}</text></g>)}
        {at&&['p5','p50','p95'].map(k=><circle key={k} cx={x(at.age)} cy={y(at[k as 'p5'|'p50'|'p95'])} r="3" className="chart-point" style={{stroke:s.color}}/>)}
      </g>})}
      {drag&&ages[drag[0]]!==undefined&&ages[drag[1]]!==undefined&&<rect x={x(ages[Math.min(...drag)])} width={Math.max(1,Math.abs(x(ages[drag[0]])-x(ages[drag[1]])))} y={top} height={height-bottom-top} className="chart-selection"/>}
      {activeAge!==undefined&&<line x1={x(activeAge)} x2={x(activeAge)} y1={top} y2={height-bottom} className="chart-crosshair"/>}
    </svg>
    <div className="chart-values" aria-live="polite"><strong>{activeAge?.toFixed(2)} 岁</strong>{curves.map(s=>{const r=s.complete.find(r=>r.age===activeAge);return <div key={s.id} className="series-values" style={{borderColor:s.color}}><strong>{s.label}</strong>{r?<><span>5%：{money(r.p5)}</span>{r.p25!==undefined&&<span>25%：{money(r.p25)}</span>}<span>50%：{money(r.p50)}</span>{r.p75!==undefined&&<span>75%：{money(r.p75)}</span>}<span>95%：{money(r.p95)}</span>{r.retired_path_count!==undefined&&<small>已退休路径 {r.retired_path_count}/{r.total_path_count}</small>}</>:<span>此年龄尚无完整退休年度</span>}</div>})}</div>
    <label className="chart-slider">查看年龄<input aria-label="查看年龄" type="range" min={zoom?.[0]??0} max={zoom?.[1]??ages.length-1} step="1" value={selected} onChange={e=>setSelected(Number(e.target.value))}/></label></>}
    {!visibleAges.length&&<p className="small">尚无完整退休年度；首段不足12个月的实际累计金额见结果指标。</p>}
    {partial.map(r=><p className="small" key={r.age}>从{r.age.toFixed(2)}岁起的末段仅{r.months_summed}个月，在{partialEndLabel}截断。实际累计5% /50% /95%：{['p5','p50','p95'].map(k=>money(r[k as 'p5'|'p50'|'p95'])).join(' / ')}；不作为完整年度连接。</p>)}
    <p className="small">{footnote||'实线：中位数；虚线：5%和95%；有数据时阴影为25%–75%。逐点分位数不代表一条连续人生路径。'}</p>
    {groups.length>0&&<details className="detail decade-minima" open><summary>每十年：5%分位曲线的最低值</summary><div className="decade-grid">{groups.map(start=><div key={start}><h4>{start}–{start+9} 岁</h4>{curves.map(s=>{const m=s.minima?.find(m=>m.start_age===start);return m&&<p key={s.id}><strong style={{color:s.color}}>{s.label}：{money(m.p5)}/年</strong><br/><small>最低点 {m.age.toFixed(2)} 岁；覆盖年度起始年龄 {m.covered_start.toFixed(1)}–{m.covered_end.toFixed(1)} 岁</small></p>})}</div>)}</div></details>}
  </figure>
}
