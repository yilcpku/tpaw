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
import NativeControl from './NativeControl'
import Diagnostics,{type DiagnosticsData} from './Diagnostics'

type Scenario = {name: string; initial_assets: number; reserve: number; annual_budget: number;
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
type Status = {engine: string; features: {name: string; state: string}[]; datasets: {id: string; name: string}[];diagnostics_id?:string;native_control_available?:boolean}
type Saved = {id: string; name: string}
type Results = {label: string; notes: string[]; profiles?: Profile[];
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
const example: Scenario = {name: '示例 · 尚未载入个人情景', initial_assets: 1000000, reserve: 0, annual_budget: 30000,
  current_age: 40, candidates: '2028-04,2029-04,2030-04', threshold_annual: 30000, notice_months: 3,
  horizon: 'rolling', margin: 5, defensive: 'deposit', term_years: 5, cash_multiple: 1.5,
  stock_return: 4, stock_volatility: 18, planning_defensive_return: 0, seed: 1234, runs: 100,
  dataset: '', risk_tolerance: 12, time_preference: 0, evaluation_month: '2026-11', monthly_savings: 0, use_forward_targets: true,
  initial_deposit_rate: .02, initial_government_yield: .02, demand_rate: .001,
  defensive_rate_mode: 'constant', cpi_publication_lag_months: 1, floor_trigger_fraction: 1,
  rate_persistence: 1, include_attribution: false,include_horizons:true,cashflow_rows:[],planning_cpi:.02,
  reserve_funding:'initial',reserve_basis:'real',reserve_cash_rate:.001,savings_mode:'constant',require_savings_coverage:false,risk_delta_at90:-2}

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
      <div><dt>境内现金底线未补足</dt><dd>{pct(d.sampling_path_fraction_any_cash_floor_short)}</dd></div><div><dt>准备金划分或等额支取存在缺口</dt><dd>{pct(d.sampling_path_fraction_any_reserve_short)}</dd></div></dl>
    {d.whole_retirement_budget_short_months_q5_q50_q95&&<p>完整退休路径中，日常支出低于当期预算的月数（5% /50% /95%）：{d.whole_retirement_budget_short_months_q5_q50_q95.map(v=>Math.round(v)).join(' / ')} 月。</p>}
    <p>100岁仍存活者的剩余资产（5% /50% /95%）：{d.assets_if_alive100_q5_q50_q95.map(v=>'¥'+Math.round(v).toLocaleString()).join(' / ')}。这部分没有被当作100岁前死亡资产。</p>
  </>
}

async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch('/api/' + path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || '本地请求失败')
  return data
}


function App() {
  const [s,setS] = useState<Scenario>(example)
  const [status,setStatus] = useState<Status>()
  const [saved,setSaved] = useState<Saved[]>([])
  const [chosen,setChosen] = useState('')
  const [message,setMessage] = useState('')
  const [running,setRunning] = useState(false)
  const [results,setResults] = useState<Results>()
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
  const number = (key: keyof Scenario, label: string, description?: string, scale = 1) => <TextInput key={key} label={label} description={description} inputMode="decimal" value={typeof s[key] === 'number' ? String(Number(s[key]) * scale) : String(s[key] ?? '')} onChange={v=>update(key, v === '' ? '' as never : Number(v) / scale as never)}/>
  const select = (key: keyof Scenario, label: string, options: {value: string; label: string}[], description?: string) => <Selector label={label} description={description} value={String(s[key])} options={options} onChange={v=>update(key,v as never)} width="100%"/>
  async function run() {setRunning(true);setMessage('');try {setResults(await api<Results>('run',s));setTab('results')}catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setRunning(false)}}
  return <Theme theme={neutralTheme} mode="light"><div className="app">
    <header><div><span className="eyebrow">TPAW / LOCAL RESEARCH</span><h1>把退休计划放回生活里</h1><p>比较消费路径、晚年削减与剩余资产。情景和结果只保存在本机。</p></div><span className="local">本地运行</span></header>
    <nav aria-label="规划视图">{[{value:'plan',label:'情景与参数'},{value:'results',label:'路径与比较'},{value:'native',label:'原版基准'},{value:'sources',label:'数据与方法'}].map(t=><Button key={t.value} variant={tab===t.value?'secondary':'ghost'} label={t.label} onClick={()=>setTab(t.value)}/>)}</nav>
    <div className="toolbar"><div className="scenario-name"><TextInput label="当前情景" value={s.name} onChange={v=>update('name',v)}/></div><div className="saved"><Selector label="本地保存的情景" value={chosen} options={saved.map(x=>({value:x.id,label:x.name}))} placeholder="选择已保存的情景" onChange={id=>{setChosen(id);api<Scenario>('scenarios/'+id).then(data=>setS({...example,...data})).then(()=>setResults(undefined)).catch(e=>setMessage(e.message))}} width="100%"/></div>
    <Button label="保存情景" onClick={()=>{api<{id:string}>('scenarios',s).then(async x=>{setChosen(x.id);await refresh();setMessage('情景已保存到本地。')}).catch(e=>setMessage(e.message))}}/>
    <Button label="运行模拟" variant="primary" isLoading={running} onClick={run}/></div>
    {message&&<p role="status" className="notice">{message}</p>}
    {tab==='plan'&&<main className="planning"><div className="inputs"><section><h2>资产与生活目标</h2><p className="small">首次打开使用示例金额；不会自动将归档金额当成最新资产。</p>{s.source_note&&<p className="notice">{s.source_note}</p>}<div className="fields">{number('initial_assets','初始总资产 / 人民币')}{number('reserve','独立准备金目标 / 人民币','从已有资产划出，不是新增财富。')}{select('reserve_funding','准备金划分时点',[{value:'initial',label:'评估时即划出'},{value:'retirement',label:'实际退休月从核心划出'}])}{select('reserve_basis','准备金目标金额口径',[{value:'real',label:'评估月实际购买力'},{value:'nominal',label:'划分时固定名义金额'}])}{number('reserve_cash_rate','准备金现金部分名义年收益 / %','独立于核心现金底线；固定情景假设，不是MMF产品报价。',100)}{number('annual_budget','年度目标消费 / 实际人民币')}{number('current_age','当前年龄 / 岁')}</div></section>
    <section><h2>规划寿命</h2><div className="fields">{select('horizon','规划终点',[{value:'rolling',label:'每年更新：年龄 + 剩余预期寿命 + 安全年数'},{value:'fixed90',label:'固定至 90 岁'},{value:'fixed95',label:'固定至 95 岁'},{value:'fixed100',label:'固定至 100 岁'}])}{number('margin','滚动安全年数','5 年是可调整的规则，不对应确定安全概率。')}</div></section>
    <section><h2>退休时点</h2><div className="fields"><TextInput label="评估月份 / YYYY-MM" value={s.evaluation_month||'2026-11'} onChange={v=>update('evaluation_month',v)}/><TextInput label="候选退休月份（YYYY-MM，逗号分隔）" value={s.candidates} description="最后一项为最迟退休日期；分别记录被迫退休与门槛未达标。" onChange={v=>update('candidates',v)}/>{select('savings_mode','退休前净储蓄',[{value:'constant',label:'固定实际月储蓄（忽略日期储蓄行）'},{value:'dated',label:'下方日期净储蓄（替换固定月储蓄）'}])}{number('monthly_savings','固定净月储蓄 / 实际人民币','已扣工作生活费与税费；通知期工资已在其中时不再叠加。')}<TextInput label="已知日期储蓄覆盖截止月 / YYYY-MM" value={s.savings_coverage_end||''} description="历史导入不自动外推工资。日期模式的最后退休日前一个月应在覆盖范围内。" onChange={v=>update('savings_coverage_end',v)}/><Selector label="日期储蓄的缺失月份" value={s.require_savings_coverage?'strict':'zero'} options={[{value:'strict',label:'要求工作期每个月明确列出（包括零）'},{value:'zero',label:'未列月份假设零储蓄'}]} onChange={v=>update('require_savings_coverage',v==='strict')} width="100%"/>{number('threshold_annual','退休门槛 / 年度实际日常支出','含被标记为日常的额外费用，准备金一次性支取不参与门槛。')}{number('notice_months','不可逆通知期 / 月','通知期内未来市场表现不参与离职决定。')}</div></section>
    <section><h2>人民币防御资产与现金</h2><div className="fields">{select('defensive','防御资产',[{value:'deposit',label:'人民币定期存款'},{value:'government_bond',label:'人民币名义国债'},{value:'cash',label:'人民币活期现金'}])}{number('term_years','期限 / 年')}{number('initial_deposit_rate','存款合同名义年利率 / %','示例假设，不是产品报价；到期前合同利率固定。',100)}{number('initial_government_yield','初始国债名义到期收益率 / %','以代表性平价合约建模：7年及以内年付息，更长期半年付息；剩余期限曲线用于卖出定价。',100)}{number('demand_rate','活期及存款提前支取年利率 / %','提前支取的已计合同利息损失单独记录。',100)}{select('defensive_rate_mode','未来防御利率',[{value:'constant',label:'用户设定名义利率保持不变'},{value:'history',label:'同步抽取官方曲线与挂牌利率变化'}],'仅真实联合数据支持；初始水平由你设定，抽样月度变化不在区块交界重置为历史水平。')}{number('rate_persistence','利率持续性 / 0–1','1：累积实际变化并设零下限；低于1：额外向抽样历史水平回归。请比较不同假设。')}{number('cash_multiple','境内现金底线 / 年支出倍数','默认 1.5 倍；准备金不用于满足该底线。')}{number('floor_trigger_fraction','现金补充触发线 / 目标的倍数','低于该比例时，补足现金目标；先用防御资产，再出售股票。')}{number('cpi_publication_lag_months','CPI 公布滞后 / 月','名义支出依据已公布价格指数；实际消费按真实价格指数计算。')}{number('planning_cpi','规划CPI年变化 / %','只用于名义未来目标的规划折算；实际路径仍使用抽样CPI。',100)}{number('planning_defensive_return','规划防御资产实际年收益 / %','名义合约利息会单独按模拟中国通胀折算。')}</div></section>
    <section><h2>市场与前瞻假设</h2><div className="fields">{select('dataset','历史与压力情景',status?.datasets.map(d=>({value:d.id,label:d.name+' · '+d.id}))||[],'真实历史与合成压力数据会分别标识。')}<Selector label="收益序列调整" value={s.use_forward_targets===false?'raw':'forward'} options={[{value:'raw',label:'原始观测收益；规划假设单独保留'},{value:'forward',label:'替换为绝对前瞻收益与波动目标'}]} onChange={v=>update('use_forward_targets',v==='forward')} width="100%"/>{number('stock_return','前瞻股票滚动12月算术平均 / %','绝对目标，替换一次；不是复合年化收益，也不再叠加估值扣减。')}{number('stock_volatility','股票月对数波动 × √12 / %')}{number('risk_tolerance','TPAW 风险容忍度（0–24）','导入曲线可保留；修改风险、年龄或评估月后按固定90岁锚重新生成。')}{number('risk_delta_at90','到90岁的风险容忍度变化（−24至0）')}<TextInput label="规划股票年对数波动 / %" value={String(100*Math.sqrt(s.policy_variance_annual??(s.stock_volatility/100)**2))} description="原版年度规划方差单独保留；上方月波动×√12是采样校准目标，两种口径不会自动混用。" inputMode="decimal" onChange={v=>update('policy_variance_annual',(Number(v)/100)**2)}/>{number('time_preference','年度时间偏好')}<Selector label="股票/汇率/通胀结果归因" value={s.include_attribution?'yes':'no'} options={[{value:'no',label:'仅运行四种规划寿命'},{value:'yes',label:'另加8组配对归因（原始收益）'}]} onChange={v=>update('include_attribution',v==='yes')} width="100%"/><Selector label="规划寿命对照" value={s.include_horizons?'all':'selected'} options={[{value:'all',label:'同时比较固定90/95/100与滚动寿命'},{value:'selected',label:'只运行选中的规划终点'}]} onChange={v=>update('include_horizons',v==='all')} width="100%"/>{number('runs','模拟路径数')}{number('seed','随机种子')}</div></section><Cashflows rows={s.cashflow_rows||[]} onChange={rows=>update('cashflow_rows',rows)} evaluation={s.evaluation_month}/></div>
    <aside><h2>这次比较关注什么</h2><ol><li>退休初期消费能否达到目标。</li><li>80 岁之后的消费下降、削减幅度和持续时间。</li><li>死亡前的剩余资产，以及 100 岁仍存活者的独立结果。</li><li>现金不足、准备金缺口与基本支出不足，分别记录。</li></ol><hr/><h3>可复查的对照</h3><p>固定 90、95、100 岁与滚动寿命共享同一组市场抽样。每一组比较会列明改变的变量。</p><h3>运行边界</h3><p>数据源日期、前瞻收益口径、期限和流动性假设随结果一起保存。短历史重抽样不能证明未来几十年的安全概率。</p></aside></main>}
    {tab==='results'&&<main><section><h2>消费与晚年风险</h2>{results?<><h3>{results.label}</h3>{results.profiles&&results.profiles.length>0&&<Chart rows={results.profiles}/>}<dl className="metrics">{results.summary?.map(x=><div key={x.name}><dt>{x.name}</dt><dd>{x.value}</dd></div>)}</dl>{results.notes.map(note=><p key={note} className="small">{note}</p>)}<RiskDetails results={results}/><Comparison results={results}/><ChannelComparison results={results}/><Provenance results={results}/>{results.native_baseline&&<NativeReference baseline={results.native_baseline}/>}</>:<p>设置并运行情景后，这里会展示消费路径、支出削减和资产结果。</p>}</section></main>}
    {tab==='native'&&<main><NativeControl available={!!status?.native_control_available} candidates={s.candidates} scenario={s} runApi={body=>api('run-native',body)}/><section><h2>保留的原版基准</h2><p>归档结果与请求保持原样。选择历史导入情景后，可以在运行结果中查看预期改动与后续额外编辑；参数变化不会被误说成原版已跟随重跑。</p><Selector label="原生基准快照" value={nativeId} options={baselines.map(b=>({value:b.id,label:b.name}))} onChange={id=>{setNativeId(id);api<NativeBaseline>('baselines/'+id).then(setNative).catch(e=>setMessage(e.message))}} placeholder="选择原版快照" width="100%"/>{baselines.length===0&&<p>尚未导入原生基准。可使用本地归档导入命令建立私有快照。</p>}</section>{native&&<NativeReference baseline={native}/>}</main>}
    {tab==='sources'&&<main><section><h2>数据与实现状态</h2><p>行情采集与模拟分离；运行已保存情景不会自动访问互联网。</p><ul className="status-list">{status?.features.map(f=><li key={f.name}><span>{f.name}</span><strong>{f.state}</strong></li>)}</ul><DataAudit audit={audit}/><Diagnostics data={diagnostics}/><h3>收益口径</h3><p>人民币实际总收益 = 美元股票总收益 × 人民币/美元汇率变化 ÷ 中国 CPI 变化。基金 NAV 总收益已包含的分红再投资和费用不再重复调整。</p><h3>估值与前瞻收益</h3><p>原版的回归、保守估计及1/CAPE预设已包含估值信息；本地前瞻目标为绝对替换值，不再追加一次估值扣减。美国CAPE也不能直接充当全球股票的估值。</p><p className="small">Vanguard在2026年10月21日发布的9月底模型中，给出美股未来10年美元名义复合年化4.8%–6.8%，发达市场非美股5.3%–7.3%。这些预测支持测试较低收益情景，不能直接作为人民币实际滚动12月算术均值。应分别设置汇率、中国通胀和收益口径，并比较目标敏感性。<a href="https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/vemo-return-forecasts.html" target="_blank" rel="noreferrer">官方模型说明及日期</a></p><h3>历史代理</h3><p>Fama/French 发达市场组合可延伸到 1990 年，包含股息与资本利得；它与覆盖新兴市场的 FTSE All-World 存在口径差异。2012年6月起可接官方VWRL总收益。下方分别展示月度ETF差异和FTSE官方年度窗口；代理段与基金段的费用口径变化会保留标注。</p><p><a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5developed.html" target="_blank" rel="noreferrer">French 原始说明</a> · <a href="https://github.com/meta/astryx" target="_blank" rel="noreferrer">Meta Astryx</a></p></section></main>}
    <footer>TPAW 本地研究扩展 · Astryx 0.7.14 · 保留原版引擎与归档基准</footer>
  </div></Theme>
}

createRoot(document.getElementById('root')!).render(<App/> )
