import {useEffect, useState} from 'react'
import {createRoot} from 'react-dom/client'
import {Theme} from '@astryxdesign/core/theme'
import {neutralTheme} from '@astryxdesign/theme-neutral/built'
import {Button} from '@astryxdesign/core/Button'
import {TextInput} from '@astryxdesign/core/TextInput'
import {Selector} from '@astryxdesign/core/Selector'
import '@astryxdesign/core/reset.css'
import '@astryxdesign/core/astryx.css'
import '@astryxdesign/theme-neutral/theme.css'
import './style.css'
import Chart,{type Profile} from './Chart'
import Cashflows,{type CashflowRow} from './Cashflows'
import NativeReference,{type NativeBaseline} from './NativeReference'
import Diagnostics,{type DiagnosticsData} from './Diagnostics'
import HostedAccess from './HostedAccess'
import {api,hosted} from './api'
import DecimalInput from './DecimalInput'
import {calculate,cancelCalculation,clearCalculation} from './browserCalculation'
import RetirementPlans,{type RetirementPlan} from './RetirementPlans'
import RetirementComparison,{type RetirementCase} from './RetirementComparison'

type Scenario = {retirement_plans:RetirementPlan[];retirement_withdrawal:number;name: string; initial_assets: number; reserve: number; annual_budget: number;
  current_age: number; candidates: string; threshold_annual: number; notice_months: number;
  horizon: string; margin: number; defensive: string; term_years: number; cash_multiple: number;
  stock_return: number; stock_volatility: number; planning_defensive_return: number;
  seed: number; runs: number; dataset: string; risk_tolerance: number; time_preference: number;
  evaluation_month: string; monthly_savings: number; use_forward_targets: boolean;
  initial_deposit_rate: number; initial_government_yield: number; demand_rate: number;
  defensive_rate_mode: string; cpi_publication_lag_months: number; floor_trigger_fraction: number;
  rate_persistence: number; include_attribution: boolean;include_horizons:boolean;
  cashflow_rows:CashflowRow[];planning_cpi:number;reserve_funding:string;reserve_basis:string;reserve_cash_rate:number;
  savings_mode:string;savings_coverage_end?:string;require_savings_coverage:boolean;source_note?:string;
  policy_variance_annual?:number;policy_rra?:number[];risk_delta_at90:number;additional_spending_tilt?:number}
type Status = {engine: string; features: {name: string; state: string}[]; datasets: {id: string; name: string}[];diagnostics_id?:string;native_control_available?:boolean;max_runs?:number}
type Saved = {id: string; name: string}
type Results = RetirementCase&{retirement_comparison?:{cases:Record<string,Results>;notes:string[]};label: string; notes: string[]; profiles?: Profile[];
  summary?: {name: string; value: string}[];
  provenance?: {history_kind: string; history_start: string; history_end: string; limitations: string[]; sources: string[];
    sample_index_sha256: string; local_dataset_id?: string; rate_zero_floor_clamps?: number};
  local_result_id?: string;
  native_baseline?:NativeBaseline;
  distributions?:{sampling_path_fraction_any_cash_floor_short:number;sampling_path_fraction_any_unfunded_consumption:number;
    sampling_path_fraction_any_reserve_short:number;whole_retirement_budget_short_months_q5_q50_q95:number[];assets_if_alive100_q5_q50_q95:number[]};
  equity_channel_comparison?: {cases: Record<string,{metrics: Record<string,number>;initial_spending_months_min_max:number[]}>;
    shapley_contributions: Record<string,Record<string,number>>; limits: string[]; return_mode: string};
  horizon_comparison?: {varied_fields: string[]; cases: Record<string, Results>}}
type ReturnStats = Record<string,number>
type Audit = {joined_start?: string; joined_end?: string; joined_months?: number;data_kind?:string;
  monthly_factor_correlation?: Record<string,Record<string,number|null>>; return_statistics?: ReturnStats;
  proxy_comparison?: {monthly_proxy_minus_vwrl: {start: string; end: string; months: number; a: ReturnStats; b: ReturnStats;
    monthly_simple_correlation: number; monthly_log_difference_std_times_sqrt12: number};
    monthly_vwra_minus_vwrl: {start: string; end: string; max_absolute_monthly_simple_difference: number};
    ftse_annual_oct_sep_windows: {start: string; end: string; developed_proxy: number; fund: number; benchmark: number}[]; limits: string[]}}
const example: Scenario = {retirement_plans:[{id:'fixed-1',name:'固定退休',kind:'fixed',date:'2028-04'},{id:'window-1',name:'区间达标退休',kind:'window',start:'2028-04',end:'2029-04',target_annual:30000}],retirement_withdrawal:2500000,name: '示例 · 尚未载入个人情景', initial_assets: 5000000, reserve: 0, annual_budget: 30000,
  current_age: 40, candidates: '2028-04,2029-04,2030-04', threshold_annual: 30000, notice_months: 3,
  horizon: 'rolling', margin: 5, defensive: 'deposit', term_years: 5, cash_multiple: 1.5,
  stock_return: 4, stock_volatility: 18, planning_defensive_return: 0, seed: 1234, runs: 100,
  dataset: '', risk_tolerance: 12, time_preference: 0, evaluation_month: '2026-11', monthly_savings: 0, use_forward_targets: true,
  initial_deposit_rate: .02, initial_government_yield: .02, demand_rate: .001,
  defensive_rate_mode: 'constant', cpi_publication_lag_months: 1, floor_trigger_fraction: 1,
  rate_persistence: 1, include_attribution: false,include_horizons:true,cashflow_rows:[],planning_cpi:.02,
  reserve_funding:'initial',reserve_basis:'real',reserve_cash_rate:.001,savings_mode:'constant',require_savings_coverage:false,risk_delta_at90:-2}

function normalizeScenario(data:Partial<Scenario>):Scenario{
  const next={...example,...data,horizon:['rolling','fixed90'].includes(data.horizon||'')?data.horizon!:'rolling'}
  next.retirement_plans=data.retirement_plans||((data.candidates||'').split(',').filter(Boolean).map((date,i)=>({id:`fixed-${i}`,name:`固定 ${date.trim()}`,kind:'fixed' as const,date:date.trim()})))
  if(!next.retirement_plans.length)next.retirement_plans=example.retirement_plans
  next.reserve=0;next.reserve_cash_rate=0;next.cpi_publication_lag_months=0
  next.retirement_withdrawal=data.retirement_withdrawal??2500000
  const evaluation=next.evaluation_month.split('-').map(Number),base=evaluation[0]*12+evaluation[1]-1
  next.cashflow_rows=(data.cashflow_rows||[]).filter(row=>['net_savings','retirement_income'].includes(row.kind)).flatMap(row=>{
    if(row.basis!=='nominal'||row.reference==='retirement')return [{...row,basis:row.basis||'real'}]
    const [year,month]=String(row.start).split('-').map(Number),start=year*12+month-1
    return Array.from({length:Math.ceil((row.duration_months||1)/(row.every_months||1))},(_,i)=>{
      const m=start+i*(row.every_months||1),offset=m-base
      return {...row,label:(row.label||'现金流')+'（旧名义金额已折算）',basis:'real',start:`${Math.floor(m/12)}-${String(m%12+1).padStart(2,'0')}`,duration_months:1,every_months:1,amount:row.amount/(1+next.planning_cpi)**(offset/12)}
    })
  })
  return next
}

const horizonNames: Record<string, string> = {fixed90:'固定 90 岁',fixed95:'固定 95 岁',fixed100:'固定 100 岁',rolling:'滚动寿命'}

function Comparison({results}: {results: Results}) {
  if (!results.horizon_comparison) return null
  return <><h3>相同市场路径，只改变规划终点</h3><div className="comparison"><table>
    <thead><tr><th>方案</th>{results.summary?.map(x=><th key={x.name}>{x.name}</th>)}</tr></thead>
    <tbody>{Object.entries(results.horizon_comparison.cases).map(([mode,caseResult])=><tr key={mode}>
      <th>{horizonNames[mode]}</th>{caseResult.summary?.map(x=><td key={x.name}>{x.value}</td>)}</tr>)}</tbody>
  </table></div></>
}

function Provenance({results}: {results: Results}) {
  if (!results.provenance) return null
  const p = results.provenance
  return <><h3>这次运行的数据与假设</h3><p>来源区间：{p.history_start} 至 {p.history_end} · {p.history_kind==='observed'?'观测历史代理':'合成/前瞻调整情景'}</p>
    <p className="small">数据版本：{p.local_dataset_id||'当前对照'} · 结果：{results.local_result_id||'随主结果保存'}</p>
    <p className="small">市场抽样校验：<code>{p.sample_index_sha256}</code></p>
    {!!p.rate_zero_floor_clamps&&<p className="notice">本组路径共发生 {p.rate_zero_floor_clamps} 次利率零下限截断。请比较利率持续性假设，截断会改变联合关系。</p>}
    {p.limitations.map(note=><p className="small" key={note}>{note}</p>)}
    <p className="small">{p.sources.map((url,i)=><span key={url}><a href={url} target="_blank" rel="noreferrer">来源 {i+1}</a>{' '}</span>)}</p></>
}

const pct = (n: number) => (100*n).toFixed(2)+'%'
const outcomeNames: Record<string,string> = {initial_period_spending_median:'退休初段累计支出中位数 / 元',death_before100_estate_median:'死亡资产中位数 / 元',
  late_max_budget_cut_fraction_median:'晚年最大削减中位数 / 百分点',late_longest_cut_months_median:'晚年最长削减中位数 / 月',
  assets_alive100_median:'存活至100岁资产中位数 / 元',unfunded_consumption_path_fraction:'支出资金不足路径 / 百分点'}
function ChannelComparison({results}: {results: Results}) {
  const c=results.equity_channel_comparison
  if (!c) return null
  const format=(key: string,n: number)=>key.includes('fraction')?(100*n).toFixed(2):n.toLocaleString(undefined,{maximumFractionDigits:0})
  return <><h3>股票、汇率与两国通胀对支出结果的贡献</h3><p className="small">8 组共用市场抽样的反事实，按 6 种引入顺序平均分摊差异。规划假设与人民币账户规则相同；这里使用原始收益，不会把各组重新校准到同一均值。</p>
    <p className="small">退休初段累计最多12个月，在100岁截断。{Object.entries(c.cases).filter(([,value])=>value.initial_spending_months_min_max[0]<12).map(([key,value])=><span key={key}>控制组 {key} 仅 {value.initial_spending_months_min_max.join('至')} 个月；</span>)}不足12个月时，金额差异同时包含观察时长差异，不作为完整首年消费比较。</p>
    <div className="comparison"><table><thead><tr><th>结果</th><th>美股 / 美国CPI</th><th>全球 × 汇率 / 中国CPI</th><th>股票市场贡献</th><th>汇率贡献</th><th>两国通胀口径贡献</th></tr></thead>
    <tbody>{Object.entries(outcomeNames).map(([key,label])=><tr key={key}><th>{label}</th><td>{format(key,c.cases['0'].metrics[key])}</td><td>{format(key,c.cases['7'].metrics[key])}</td>
      {['global_equity','fx','china_inflation'].map(channel=><td key={channel}>{format(key,c.shapley_contributions[channel][key])}</td>)}</tr>)}</tbody></table></div>
    {c.limits.map(note=><p key={note} className="small">{note}</p>)}</>
}

function DataAudit({audit}: {audit?: Audit}) {
  if (!audit) return <p>选择数据集后，可查看这份数据的口径和重叠比较。</p>
  const p=audit.proxy_comparison, stats=audit.return_statistics
  const metrics: [string,string][]=[['arithmetic_monthly_mean_times_12','月算术平均 ×12'],['compound_annual_growth_rate','复合年化收益'],
    ['rolling_12m_arithmetic_mean','滚动12月算术平均'],['rolling_12m_simple_volatility_sample','滚动12月简单收益标准差'],
    ['monthly_log_volatility_times_sqrt12_sample','月对数收益标准差 ×√12']]
  return <>{stats&&<><h3>当前数据集的人民币实际股票收益</h3><p>{audit.joined_start} 至 {audit.joined_end} · {audit.joined_months} 个月 · {audit.data_kind==='observed'?'观测历史及代理':'合成压力数据；不是历史人民币观测'}</p><p className="small">以下统计描述所选源数据，尚未应用表单中的前瞻调整；调整可能改变相关性。</p><dl className="metrics">{metrics.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{pct(stats[key])}</dd></div>)}</dl></>}
    {p&&<><h3>发达市场代理与官方 VWRL 总收益</h3><p>{p.monthly_proxy_minus_vwrl.start} 至 {p.monthly_proxy_minus_vwrl.end} · {p.monthly_proxy_minus_vwrl.months} 个月 · 月收益相关系数 {p.monthly_proxy_minus_vwrl.monthly_simple_correlation.toFixed(4)}</p>
    <div className="comparison"><table><thead><tr><th>口径</th><th>French 发达市场代理</th><th>VWRL 官方 NAV 总收益</th></tr></thead><tbody>{metrics.map(([key,label])=><tr key={key}><th>{label}</th><td>{pct(p.monthly_proxy_minus_vwrl.a[key])}</td><td>{pct(p.monthly_proxy_minus_vwrl.b[key])}</td></tr>)}</tbody></table></div>
    <p className="small">月对数差异波动 ×√12：{pct(p.monthly_proxy_minus_vwrl.monthly_log_difference_std_times_sqrt12)}。VWRA/VWRL 重叠期 {p.monthly_vwra_minus_vwrl.start} 至 {p.monthly_vwra_minus_vwrl.end}，最大单月简单收益差 {(p.monthly_vwra_minus_vwrl.max_absolute_monthly_simple_difference*10000).toFixed(3)} 基点。</p>
    <h3>与 FTSE All-World 的官方年度窗口比较</h3><p className="small">每行均为10月至翌年9月，互不重叠。基金月收益复合结果已与官方事实表核对；未取得完整月度指数序列。</p>
    <div className="comparison"><table><thead><tr><th>区间</th><th>代理</th><th>VWRL（费后）</th><th>FTSE总收益</th></tr></thead><tbody>{p.ftse_annual_oct_sep_windows.map(row=><tr key={row.end}><th>{row.start} – {row.end}</th><td>{pct(row.developed_proxy)}</td><td>{pct(row.fund)}</td><td>{pct(row.benchmark)}</td></tr>)}</tbody></table></div>
    {p.limits.map(note=><p key={note} className="small">{note}</p>)}</>}
    {audit.monthly_factor_correlation&&<><h3>同期月度相关性</h3><p className="small">股票、汇率和CPI为对数变化，利率为月末绝对变化。样本相关性会随制度与区间改变。</p><div className="comparison"><table><thead><tr><th>因子</th>{Object.keys(audit.monthly_factor_correlation).map(key=><th key={key}>{key}</th>)}</tr></thead><tbody>{Object.entries(audit.monthly_factor_correlation).map(([key,row])=><tr key={key}><th>{key}</th>{Object.entries(row).map(([col,value])=><td key={col}>{value===null?'—':value.toFixed(2)}</td>)}</tr>)}</tbody></table></div></>}
  </>
}

function RiskDetails({results}: {results:Results}) {
  const d=results.distributions
  if(!d)return null
  return <><h3>把预算削减与资金缺口分开看</h3><p className="small">TPAW可能主动下调支出，所以“请求支出能付清”仍可能远低于生活预算。下列为重抽样路径占比，不能视为未来安全概率。</p>
    <dl className="metrics"><div><dt>核心请求支出存在资金缺口</dt><dd>{pct(d.sampling_path_fraction_any_unfunded_consumption)}</dd></div>
      <div><dt>境内现金底线未补足</dt><dd>{pct(d.sampling_path_fraction_any_cash_floor_short)}</dd></div></dl>
    {d.whole_retirement_budget_short_months_q5_q50_q95&&<p>完整退休路径中，日常支出低于当期预算的月数（5% /50% /95%）：{d.whole_retirement_budget_short_months_q5_q50_q95.map(v=>Math.round(v)).join(' / ')} 月。</p>}
    <p>100岁仍存活者的剩余资产（5% /50% /95%）：{d.assets_if_alive100_q5_q50_q95.map(v=>'¥'+Math.round(v).toLocaleString()).join(' / ')}。这部分没有被当作100岁前死亡资产。</p>
  </>
}

function App() {
  const [s,setS] = useState<Scenario>(example)
  const [status,setStatus] = useState<Status>()
  const [saved,setSaved] = useState<Saved[]>([])
  const [chosen,setChosen] = useState('')
  const [loadingScenario,setLoadingScenario]=useState(false)
  const [message,setMessage] = useState('')
  const [running,setRunning] = useState(false)
  const [progress,setProgress]=useState(0),[progressLabel,setProgressLabel]=useState('')
  useEffect(()=>()=>clearCalculation(),[])
  const [results,setResults] = useState<Results>()
  const [resultScenario,setResultScenario]=useState<Scenario>()
  const [resultPlan,setResultPlan]=useState('')
  const selectedCase=results?.retirement_comparison?.cases[resultPlan]
  const view=selectedCase?{...selectedCase,local_result_id:results?.local_result_id}:results
  const [audit,setAudit] = useState<Audit>()
  const [baselines,setBaselines]=useState<Saved[]>([])
  const [nativeId,setNativeId]=useState('')
  const [native,setNative]=useState<NativeBaseline>()
  const [diagnostics,setDiagnostics]=useState<DiagnosticsData>()
  const [tab,setTab] = useState('plan')
  const refresh = async () => {setSaved(await api<Saved[]>('scenarios'))}
  useEffect(() => {Promise.all([api<Status>('status').then(setStatus),refresh(),api<Saved[]>('baselines').then(setBaselines)]).catch(e=>setMessage(String(e.message)))},[])
  useEffect(() => {let current=true;setAudit(undefined);if(s.dataset) api<Audit>('data-audit/'+s.dataset).then(data=>{if(current)setAudit(data)}).catch(e=>{if(current)setMessage(e.message)});return()=>{current=false}},[s.dataset])
  useEffect(()=>{if(status?.diagnostics_id)api<DiagnosticsData>('diagnostics').then(setDiagnostics).catch(e=>setMessage(e.message))},[status?.diagnostics_id])
  const update = <K extends keyof Scenario>(key: K, value: Scenario[K]) => {setS(old=>{const next={...old,[key]:value};if(['risk_tolerance','risk_delta_at90','current_age','evaluation_month'].includes(key))next.policy_rra=undefined;return next});setResults(undefined)}
  const number = (key:keyof Scenario,label:string,description?:string,scale=1) => <DecimalInput key={key} label={label} description={description} value={Number(s[key])} scale={scale} onChange={value=>update(key,value as never)}/>
  const select = (key: keyof Scenario, label: string, options: {value: string; label: string}[], description?: string) => <Selector label={label} description={description} value={String(s[key])} options={options} onChange={v=>update(key,v as never)} width="100%"/>
  async function run() {
    if(loadingScenario)return
    setRunning(true);setMessage('');setProgress(0)
    // The immutable run snapshot stays separate from later form edits.
    const snapshot={...s}
    try {
      const result=await calculate<Results>(snapshot,(value,label)=>{setProgress(value);setProgressLabel(label)})
      setResults(result);setResultPlan(Object.keys(result.retirement_comparison?.cases||{})[0]||'');setResultScenario(snapshot);setTab('results')
      try {const saved=await api<{id:string;native_baseline?:NativeBaseline}>('results',{name:snapshot.name,scenario:snapshot,result});setResults({...result,local_result_id:saved.id,native_baseline:saved.native_baseline})}
      catch {setMessage('计算已完成，结果尚未保存。请保持此页面打开，点击“重试保存结果”。')}
    }catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setRunning(false)}
  }
  return <Theme theme={neutralTheme} mode="light"><div className="app">
    <header><div><span className="eyebrow">TPAW / PLANNING</span><h1>退休规划</h1><p>看清退休后的消费、晚年风险与剩余资产。{hosted?'情景和结果保存在你的服务器，登录后可访问。':'情景和结果只保存在本机。'}</p></div><span className="local">浏览器计算</span></header>
    <p className="compute-note">浏览器后台计算 · 可随时取消 · {hosted?'登录保护与服务器保存':'数据保存在本机'}</p>
    <nav aria-label="规划视图">{[{value:'plan',label:'情景与参数'},{value:'results',label:'路径与比较'},{value:'native',label:'原版基准'},{value:'sources',label:'数据与方法'}].map(t=><Button key={t.value} variant={tab===t.value?'secondary':'ghost'} label={t.label} onClick={()=>setTab(t.value)}/>)}</nav>
    <div className="toolbar"><div className="scenario-name" inert={loadingScenario||undefined}><TextInput label="当前情景" value={s.name} onChange={v=>update('name',v)}/></div><div className="saved" inert={loadingScenario||undefined}><Selector label={hosted?'服务器保存的情景':'本地保存的情景'} value={chosen} options={saved.map(x=>({value:x.id,label:x.name}))} placeholder="选择已保存的情景" onChange={async id=>{setLoadingScenario(true);setChosen(id);try{const data=await api<Scenario>('scenarios/'+id);setS(normalizeScenario(data));setResults(undefined);if(!data.retirement_plans)setMessage('旧候选日期已转为独立固定方案；旧准备金和预设费用已替换为退休当月一次性支取250万元（实际购买力）。')}catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setLoadingScenario(false)}}} width="100%"/></div>
    <Button label="保存情景" isDisabled={loadingScenario} onClick={()=>{api<{id:string}>('scenarios',s).then(async x=>{setChosen(x.id);await refresh();setMessage(hosted?'情景已保存到服务器。':'情景已保存到本地。')}).catch(e=>setMessage(e.message))}}/>
    <Button label="运行模拟" variant="primary" isLoading={running} isDisabled={loadingScenario} onClick={run}/>{running&&<Button label="取消计算" onClick={cancelCalculation}/>}</div>
    {loadingScenario&&<p className="small" role="status">正在载入情景…</p>}
    {running&&<div className="run-progress" role="status"><progress max={1} value={progress}/><span>{progressLabel} {Math.round(progress*100)}%</span></div>}
    {results&&!results.local_result_id&&resultScenario&&<Button label="重试保存结果" onClick={()=>api<{id:string;native_baseline?:NativeBaseline}>('results',{name:resultScenario.name,scenario:resultScenario,result:results}).then(saved=>{setResults(current=>current===results?{...current,local_result_id:saved.id,native_baseline:saved.native_baseline}:current);setMessage('结果已保存。')}).catch(e=>setMessage(e.message))}/>}
    {message&&<p role="status" className="notice">{message}</p>}
    {tab==='plan'&&<main className="planning"><div className="inputs" inert={loadingScenario||undefined}><section className="overview-section"><div className="section-heading"><span className="step">01</span><div><h2>资产与生活目标</h2><p className="small">所有金额按评估月购买力填写，模拟时随通胀调整。</p></div></div>{s.source_note?<details className="detail"><summary>这份情景的旧版归档说明（历史设置）</summary><p>{s.source_note}</p></details>:s.name===example.name&&<p className="small">当前为示例金额，选择保存的情景后再调整。</p>}
    <div className="fields key-fields">{number('initial_assets','初始总资产 / 人民币')}{number('annual_budget','生活预算基准 / 年度实际人民币','用于现金底线与预算不足统计；达标目标在各时间段方案中另设。')}{number('current_age','当前年龄 / 岁')}{number('retirement_withdrawal','退休当月一次性支取 / 实际人民币','预设250万元；从核心资产支取一次，不计入日常取钱曲线。')}</div>
    <p className="small">退休一次性支取按评估月购买力随通胀调整。新版不再划分独立准备金，也不加载旧预设退休后费用。</p></section>
    <section><div className="section-heading"><span className="step">02</span><div><h2>规划寿命</h2><p className="small">始终提供固定 90 岁对照。</p></div></div><div className="fields">{select('horizon','规划终点',[{value:'rolling',label:'每年更新：年龄 + 剩余预期寿命 + 安全年数'},{value:'fixed90',label:'固定至 90 岁'}])}{s.horizon==='rolling'&&number('margin','滚动安全年数','5 年是可调整的规则，不对应确定安全概率。')}</div></section>
    <section><div className="section-heading"><span className="step">03</span><div><h2>退休安排 · 多方案比较</h2><p className="small">固定时间，或进入时间段后按目标消费触发。</p></div></div><div className="fields"><TextInput label="评估月份 / YYYY-MM" value={s.evaluation_month} onChange={v=>update('evaluation_month',v)}/>{number('notice_months','不可逆通知期 / 月','区间达标后经过通知期退休，但不晚于区间末月。')}</div><RetirementPlans plans={s.retirement_plans} onChange={plans=>update('retirement_plans',plans)} evaluation={s.evaluation_month} budget={s.annual_budget}/></section>
    <section><div className="section-heading"><span className="step">储蓄</span><div><h2>退休前净储蓄</h2><p className="small">各方案从实际退休当月起，自动停止工作净储蓄。</p></div></div><div className="fields">{select('savings_mode','储蓄方式',[{value:'constant',label:'固定实际月储蓄'},{value:'dated',label:'逐月净储蓄表'}])}{s.savings_mode==='constant'&&number('monthly_savings','固定净月储蓄 / 实际人民币','已扣税和工作生活费，通知期内计入，退休月起为零。')}</div>{s.savings_mode==='dated'&&<p className="coverage">逐月储蓄覆盖至 <strong>{s.savings_coverage_end||'未填写'}</strong> · {s.require_savings_coverage?'缺失月份会阻止运行':'未列月份按零储蓄'}</p>}<details className="detail"><summary>净储蓄来源与覆盖范围</summary><p className="small">净储蓄＝税后工资＋奖金－工作期生活支出。导入值是历史假设，不按BigLaw职级重新生成工资，不重复扣税或叠加通知期工资。所有新金额为评估月实际人民币；旧名义净储蓄按规划CPI折回评估月购买力。改变退休方案后仍保留完整储蓄表，但每条路径只使用退休前的部分。</p>{s.savings_mode==='dated'&&<TextInput label="已知日期储蓄覆盖截止月 / YYYY-MM" value={s.savings_coverage_end||''} description="请补全最迟退休月之前的每月净储蓄，再延长覆盖截止月。" onChange={v=>update('savings_coverage_end',v)}/>}</details></section>
    <section><div className="section-heading"><span className="step">04</span><div><h2>投资与现金</h2><p className="small">选择防御资产，预留生活现金。</p></div></div><div className="fields">{select('defensive','防御资产',[{value:'deposit',label:'人民币定期存款'},{value:'government_bond',label:'人民币名义国债'},{value:'cash',label:'人民币活期现金'}])}{s.defensive!=='cash'&&number('term_years','期限 / 年')}{s.defensive==='deposit'&&number('initial_deposit_rate','存款合同名义年利率 / %','示例假设，不是产品报价；到期前合同利率固定。',100)}{s.defensive==='government_bond'&&number('initial_government_yield','初始国债名义到期收益率 / %','以代表性平价合约建模：7年及以内年付息，更长期半年付息；剩余期限曲线用于卖出定价。',100)}{number('cash_multiple','境内现金底线 / 年支出倍数','按生活预算基准设定现金目标。')}</div><details className="detail"><summary>利率与通胀假设</summary><div className="fields">{number('demand_rate','活期及存款提前支取年利率 / %','提前支取的已计合同利息损失单独记录。',100)}{select('defensive_rate_mode','未来防御利率',[{value:'constant',label:'用户设定名义利率保持不变'},{value:'history',label:'同步抽取官方曲线与挂牌利率变化'}],'仅真实联合数据支持；初始水平由你设定，抽样月度变化不在区块交界重置为历史水平。')}{number('planning_cpi','规划CPI年变化 / %','只用于名义未来目标的规划折算；实际路径仍使用抽样CPI。',100)}{number('planning_defensive_return','规划防御资产实际年收益 / %','名义合约利息会单独按模拟中国通胀折算。')}</div></details></section>
    <section><div className="section-heading"><span className="step">05</span><div><h2>市场假设</h2><p className="small">收益与波动会影响可支持的消费。</p></div></div><div className="fields">{select('dataset','历史与压力情景',status?.datasets.map(d=>({value:d.id,label:d.name+' · '+d.id}))||[],'真实历史与合成压力数据会分别标识。')}{number('stock_return','前瞻股票滚动12月算术平均 / %','绝对目标，替换一次；不是复合年化收益，也不再叠加估值扣减。')}{number('stock_volatility','股票月对数波动 × √12 / %')}{number('risk_tolerance','TPAW 风险容忍度（0–24）','导入曲线可保留；修改风险、年龄或评估月后按固定90岁锚重新生成。')}</div><details className="detail"><summary>模拟精度与收益序列</summary><div className="fields">{number('runs','模拟路径数','1 至 1,000 条；越多越耗时。')}<Selector label="收益序列调整" value={s.use_forward_targets===false?'raw':'forward'} options={[{value:'raw',label:'原始观测收益；规划假设单独保留'},{value:'forward',label:'替换为绝对前瞻收益与波动目标'}]} onChange={v=>update('use_forward_targets',v==='forward')} width="100%"/></div></details></section><details className="detail cashflow-details"><summary>储蓄与收入明细 <span>{s.cashflow_rows.length} 项</span></summary><Cashflows rows={s.cashflow_rows||[]} onChange={rows=>update('cashflow_rows',rows)} evaluation={s.evaluation_month}/></details></div>
    <aside><span className="eyebrow">本次计划</span><h2>{s.horizon==='rolling'?'滚动寿命':'固定 90 岁'}</h2><p>与{ s.horizon==='rolling'?'固定 90 岁':'滚动寿命'}共享市场路径比较。</p><div className="aside-fact"><span>生活预算基准</span><strong>¥{Number.isFinite(s.annual_budget)?Math.round(s.annual_budget).toLocaleString():'—'}</strong></div><div className="aside-fact"><span>模拟路径</span><strong>{s.runs} 条 × {s.retirement_plans.length} 个退休安排 × 2 种寿命</strong></div><hr/><h3>重点看三件事</h3><ol><li>退休初期能消费多少。</li><li>晚年消费会削减多少、持续多久。</li><li>一次性支取或现金底线是否有缺口。</li></ol><p className="small">历史重抽样用于比较情景，不能证明未来安全概率。</p></aside></main>}
    {tab==='results'&&<main><section className="results-section"><div className="section-heading"><span className="step">结果</span><div><h2>消费路径与晚年风险</h2><p className="small">{view?.retirement_plan?.name||results?.label||'运行后查看你的消费路径'}</p></div></div>{results&&view?<>
    {resultScenario&&JSON.stringify(s)!==JSON.stringify(resultScenario)&&<p role="status" className="notice">下方结果对应上次运行的输入快照。当前参数已修改，请重新运行后再比较。</p>}
    <dl className="metrics primary-metrics">{[0,3,2].map(i=>view.summary?.[i]).filter(x=>!!x).map(x=><div key={x.name}><dt>{x.name}</dt><dd>{x.value}</dd></div>)}</dl>
    {view.distributions&&(view.distributions.sampling_path_fraction_any_unfunded_consumption>0||view.distributions.sampling_path_fraction_any_cash_floor_short>0)&&<p className="notice">资金不足路径占比：核心支出 {pct(view.distributions.sampling_path_fraction_any_unfunded_consumption)} · 现金底线 {pct(view.distributions.sampling_path_fraction_any_cash_floor_short)}。展开下方风险明细查看。</p>}
    {view.retirement_timing&&<p className={view.retirement_timing.withdrawal_short_path_fraction>0?'notice':'small'}>本方案退休当月一次性支取实际金额中位数：¥{Math.round(view.retirement_timing.withdrawal_paid_real_median).toLocaleString()}；支取不足路径 {(100*view.retirement_timing.withdrawal_short_path_fraction).toFixed(1)}%。此笔不计入下方日常曲线。</p>}
    {results.retirement_comparison&&<RetirementComparison cases={results.retirement_comparison.cases} evaluation={resultScenario?.evaluation_month||s.evaluation_month} selected={resultPlan} onSelect={setResultPlan}/>}
    {!results.retirement_comparison&&view.profiles&&<Chart rows={view.profiles}/>}
    {results.retirement_comparison?.notes.map(note=><p className="small" key={note}>{note}</p>)}
    <p className="small">逐点分位数用于比较消费范围；重抽样路径占比不是未来安全概率。</p>
    <details className="detail"><summary>风险与资金缺口明细</summary><RiskDetails results={view}/><dl className="metrics">{view.summary?.filter((_,i)=>![0,3,2].includes(i)).map(x=><div key={x.name}><dt>{x.name}</dt><dd>{x.value}</dd></div>)}</dl></details>
    <details className="detail" open><summary>滚动寿命与固定 90 岁对照</summary><Comparison results={view}/></details>
    <details className="detail"><summary>数据来源与本次运行记录</summary><Provenance results={view}/>{results.notes.map(note=><p key={note} className="small">{note}</p>)}<ChannelComparison results={view}/></details>
    {results.native_baseline&&<details className="detail"><summary>与归档原生基准核对</summary><NativeReference baseline={results.native_baseline}/></details>}
    </>:<div className="empty-state"><span>∿</span><h3>先设定计划，再看看未来的消费</h3><p>填写资产、消费目标和退休时间，点击“运行模拟”。</p><Button label="设置情景" onClick={()=>setTab('plan')}/></div>}</section></main>}
    {tab==='native'&&<main><section><h2>保留的原版基准</h2><p>归档结果与请求保持原样。选择历史导入情景后，可以在运行结果中查看预期改动与后续额外编辑；参数变化不会被误说成原版已跟随重跑。</p><Selector label="原生基准快照" value={nativeId} options={baselines.map(b=>({value:b.id,label:b.name}))} onChange={id=>{setNativeId(id);api<NativeBaseline>('baselines/'+id).then(setNative).catch(e=>setMessage(e.message))}} placeholder="选择原版快照" width="100%"/>{baselines.length===0&&<p>尚未导入原生基准。可使用本地归档导入命令建立私有快照。</p>}</section>{native&&<NativeReference baseline={native}/>}</main>}
    {tab==='sources'&&<main><section><h2>数据与实现状态</h2><p>行情采集与模拟分离；运行已保存情景不会自动访问互联网。</p><ul className="status-list">{status?.features.map(f=><li key={f.name}><span>{f.name}</span><strong>{f.state}</strong></li>)}</ul><details className="detail"><summary>历史数据审计与代理差异</summary><DataAudit audit={audit}/></details><details className="detail"><summary>模型敏感性诊断</summary><Diagnostics data={diagnostics}/></details><details className="detail"><summary>模型约定、收益口径与历史代理</summary><h3>保留的模型约定</h3><p className="small">所有现金流统一为评估月实际人民币，按当时CPI支付。旧名义净储蓄先按规划CPI折算；不再设置CPI公布滞后。现金补充触发比例 {s.floor_trigger_fraction}；利率持续性 {s.rate_persistence}；年度时间偏好 {s.time_preference}；随机种子 {s.seed}。这些值沿用已载入情景，精简界面不会改写它们。规划方差与导入风险曲线也继续保留。</p><h3>收益口径</h3><p>人民币实际总收益 = 美元股票总收益 × 人民币/美元汇率变化 ÷ 中国 CPI 变化。基金 NAV 总收益已包含的分红再投资和费用不再重复调整。</p><h3>估值与前瞻收益</h3><p>原版的回归、保守估计及1/CAPE预设已包含估值信息；本地前瞻目标为绝对替换值，不再追加一次估值扣减。美国CAPE也不能直接充当全球股票的估值。</p><p className="small">Vanguard在2026年10月21日发布的9月底模型中，给出美股未来10年美元名义复合年化4.8%–6.8%，发达市场非美股5.3%–7.3%。这些预测支持测试较低收益情景，不能直接作为人民币实际滚动12月算术均值。应分别设置汇率、中国通胀和收益口径，并比较目标敏感性。<a href="https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/vemo-return-forecasts.html" target="_blank" rel="noreferrer">官方模型说明及日期</a></p><h3>历史代理</h3><p>Fama/French 发达市场组合可延伸到 1990 年，包含股息与资本利得；它与覆盖新兴市场的 FTSE All-World 存在口径差异。2012年6月起可接官方VWRL总收益。下方分别展示月度ETF差异和FTSE官方年度窗口；代理段与基金段的费用口径变化会保留标注。</p><p><a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5developed.html" target="_blank" rel="noreferrer">French 原始说明</a> · <a href="https://github.com/meta/astryx" target="_blank" rel="noreferrer">Meta Astryx</a></p></details></section></main>}
    <footer>TPAW 研究扩展 · Astryx 0.7.14 · 保留原版引擎与归档基准<br/>Required Notice: Copyright (c) 2020–2026 Benjamin Mathew and Jacob Mathew. <a href="https://polyformproject.org/licenses/noncommercial/1.0.0" target="_blank" rel="noreferrer">PolyForm Noncommercial 1.0.0</a></footer>
  </div></Theme>
}

createRoot(document.getElementById('root')!).render(<HostedAccess><App/></HostedAccess>)
