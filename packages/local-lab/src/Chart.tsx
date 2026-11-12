import {useEffect,useRef,useState,type PointerEvent} from 'react'
export type Profile={age:number;p5:number;p50:number;p95:number;months_summed?:number}
const keys=['p5','p50','p95'] as const
const money=(n:number)=>'¥'+Math.round(n).toLocaleString()
export default function Chart({rows,caption,footnote,partialEndLabel='100岁'}:{rows:Profile[];caption?:string;footnote?:string;partialEndLabel?:string}){
  const complete=rows.filter(r=>r.months_summed===undefined||r.months_summed===12)
  const partial=rows.filter(r=>r.months_summed!==undefined&&r.months_summed<12)
  const [selected,setSelected]=useState(0),[zoom,setZoom]=useState<[number,number]|null>(null),[drag,setDrag]=useState<[number,number]|null>(null)
  const start=useRef<number|null>(null)
  const figure=useRef<HTMLElement>(null),[width,setWidth]=useState(820)
  useEffect(()=>{const observer=new ResizeObserver(entries=>setWidth(Math.max(280,Math.min(1100,entries[0].contentRect.width))));if(figure.current)observer.observe(figure.current);return()=>observer.disconnect()},[])
  useEffect(()=>{start.current=null;setSelected(0);setZoom(null);setDrag(null)},[rows])
  const visible=complete.filter((_,i)=>!zoom||(i>=zoom[0]&&i<=zoom[1]))
  const height=300,left=85,right=24,top=20,bottom=45
  const max=Math.max(1,...visible.map(r=>r.p95))*1.08
  const minAge=visible[0]?.age??0,maxAge=visible.at(-1)?.age??1
  const x=(age:number)=>left+(age-minAge)/Math.max(1,maxAge-minAge)*(width-left-right)
  const y=(value:number)=>height-bottom-value/max*(height-bottom-top)
  function indexAt(e:PointerEvent<SVGSVGElement>){
    const rect=e.currentTarget.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*width
    const age=minAge+Math.max(0,Math.min(1,(px-left)/(width-left-right)))*Math.max(1,maxAge-minAge)
    return complete.reduce((best,r,i)=>(!zoom||(i>=zoom[0]&&i<=zoom[1]))&&Math.abs(r.age-age)<Math.abs(complete[best].age-age)?i:best,zoom?.[0]??0)
  }
  const active=complete[selected]??visible[0]
  const path=(key:typeof keys[number])=>visible.map((r,i)=>`${i?'L':'M'}${x(r.age)},${y(r[key])}`).join(' ')
  const partialNote=partial.map(r=><p className="small" key={r.age}>末段从 {r.age.toFixed(2)} 岁起仅 {r.months_summed} 个月，在{partialEndLabel}截断；实际累计支出5% /50% /95%为 {keys.map(k=>money(r[k])).join(' / ')}，不作为完整年度点连接，也不外推终点以后。</p>)
  return <figure ref={figure} className="interactive-chart"><figcaption>{caption||'年度实际日常支出（含预算预提，准备金一次性支取另计）· 人民币'}</figcaption>
    {visible.length>0&&<><div className="chart-toolbar"><span className="small">悬停或触摸查看 · 拖动选择年龄区间放大</span><button type="button" disabled={!zoom} onClick={()=>{setZoom(null);setSelected(0)}}>重置缩放</button></div>
    <svg role="img" aria-label="交互式支出图：下方年龄滑块可用方向键查看分位数" viewBox={`0 0 ${width} ${height}`}
      onPointerDown={e=>{if(e.button!==0)return;const i=indexAt(e);start.current=i;setSelected(i);setDrag([i,i]);e.currentTarget.setPointerCapture(e.pointerId)}}
      onPointerMove={e=>{const i=indexAt(e);setSelected(i);if(start.current!==null)setDrag([start.current,i])}}
      onPointerUp={e=>{const i=indexAt(e);if(start.current!==null&&Math.abs(i-start.current)>=2){const range:[number,number]=[Math.min(i,start.current),Math.max(i,start.current)];setZoom(range);setSelected(range[0])}start.current=null;setDrag(null)}}
      onPointerCancel={()=>{start.current=null;setDrag(null)}}>
      {[0,.25,.5,.75,1].map(v=><g key={v}><line x1={left} x2={width-right} y1={y(v*max)} y2={y(v*max)} className="gridline"/><text x={left-12} y={y(v*max)+4} textAnchor="end">{Math.round(v*max).toLocaleString()}</text></g>)}
      {[...new Set([minAge,(minAge+maxAge)/2,maxAge])].map(age=><text key={age} x={x(age)} y={height-14} textAnchor="middle">{age.toFixed(1)} 岁</text>)}
      {keys.map(k=><path key={k} d={path(k)} className={k==='p50'?'median':'range'}/>)}
      {drag&&complete[drag[0]]&&complete[drag[1]]&&<rect x={x(complete[Math.min(...drag)].age)} width={Math.max(1,Math.abs(x(complete[drag[0]].age)-x(complete[drag[1]].age)))} y={top} height={height-bottom-top} className="chart-selection"/>}
      {active&&<g><line x1={x(active.age)} x2={x(active.age)} y1={top} y2={height-bottom} className="chart-crosshair"/>{keys.map(k=><circle key={k} cx={x(active.age)} cy={y(active[k])} r="4" className="chart-point"/>)}</g>}
    </svg>
    {active&&<div className="chart-values" aria-live="polite"><strong>{active.age.toFixed(2)} 岁</strong><span>5%：{money(active.p5)}</span><span>50%：{money(active.p50)}</span><span>95%：{money(active.p95)}</span></div>}
    <label className="chart-slider">查看年龄<input aria-label="查看年龄" type="range" min={zoom?.[0]??0} max={zoom?.[1]??complete.length-1} step="1" value={selected} onChange={e=>setSelected(Number(e.target.value))}/></label></>}
    {partialNote}<p className="small">{footnote||'实线：中位数；虚线：5% 和 95%。逐点分位数不代表一条连续人生路径。工作期仅记净储蓄，未把已扣除的工作生活费再次记为退休支出。'}</p></figure>
}
