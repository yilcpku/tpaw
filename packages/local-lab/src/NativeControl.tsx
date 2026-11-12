import {useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {Selector} from '@astryxdesign/core/Selector'
import Chart,{type Profile} from './Chart'

type Result={label:string;retirement_month:string;horizon:string;runs:number;profiles:Profile[];limits:string[];
  first_retirement_period_months:number;first_retirement_period_total_q5_q50_q95:number[];
  terminal_core_balance_q5_q50_q95:number[];input_sha256:string;sample_index_sha256:string;local_result_id:string;
  paired_replay:{pass:boolean;checks:number;max_absolute_money_error:number;max_allocation_error:number};
  history:{start:string;end:string;stocks:{target_sampler_annual_arithmetic_mean:number;
    source_rolling_statistics:{rolling_12m_arithmetic_mean:number;compound_annual_growth_rate:number;monthly_log_volatility_times_sqrt12_sample:number}}}}

export default function NativeControl({available,candidates,scenario,runApi}: {available:boolean;candidates:string;
  scenario:unknown;runApi:(body:unknown)=>Promise<Result>}) {
  const dates=candidates.split(',').map(x=>x.trim()).filter(Boolean)
  const [chosen,setChosen]=useState('');const retirement=dates.includes(chosen)?chosen:(dates[0]||'')
  const [horizon,setHorizon]=useState('fixed90');const [running,setRunning]=useState(false)
  const [result,setResult]=useState<Result>();const [error,setError]=useState('')
  const [inputAtRun,setInputAtRun]=useState('')
  async function run(){setRunning(true);setError('');try{
    const body={...(scenario as object),native_control:{retirement_month:retirement,horizon}}
    setResult(await runApi(body));setInputAtRun(JSON.stringify({scenario,retirement,horizon}))
  }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setRunning(false)}}
  const changed=result&&inputAtRun!==JSON.stringify({scenario,retirement,horizon})
  return <section><h2>用当前输入重跑原生模型</h2><p>使用表单中的资产、现金流、风险与规划参数，选择一个固定退休日及终点。原生美国实际收益和循环区块保留；人民币合约、现金底线和条件退休属于修改版，差异随结果列明。</p>
    {!available&&<p className="notice">服务未配置已固定的本地CUDA引擎；归档仍可查看。启动选项见本地工具说明。</p>}
    <div className="fields"><Selector label="原生对照固定退休月" value={retirement} options={dates.map(value=>({value,label:value}))} onChange={setChosen} width="100%"/>
    <Selector label="原生对照固定终点" value={horizon} options={[90].map(age=>({value:'fixed'+age,label:'固定'+age+'岁'}))} onChange={setHorizon} width="100%"/></div>
    <Button label="重跑当前输入的原生对照" isDisabled={!available||!retirement} isLoading={running} onClick={run}/>
    {error&&<p role="alert">{error}</p>}{result&&<><h3>{result.label}</h3>
      {changed&&<p className="notice">表单或原生对照选项已有修改。下方保留上次结果，请重跑后再比较。</p>}
      <p>退休月 {result.retirement_month} · 固定 {result.horizon.slice(5)} 岁（含生日当月） · {result.runs} 条路径。</p>
      <Chart rows={result.profiles} caption="核心总支出的年度路径总和分位数 · 等比例实际记账单位" partialEndLabel={result.horizon.slice(5)+'岁生日当月之后'} footnote="包含表单费用及核心一次性准备金目标；不是日常预算曲线，也没有把独立准备金余额计入核心终值。"/>
      <p>退休初段 {result.first_retirement_period_months} 个月核心总支出（5% /50% /95%）：{result.first_retirement_period_total_q5_q50_q95.map(x=>Math.round(x).toLocaleString()).join(' / ')}。</p>
      <p>规划终点核心资产（5% /50% /95%）：{result.terminal_core_balance_q5_q50_q95.map(x=>Math.round(x).toLocaleString()).join(' / ')}。这是固定终点余额，不是死亡资产分布。</p>
      <p className="small">同路径逐月核验通过：{result.paired_replay.checks.toLocaleString()} 项；最大金额误差 {result.paired_replay.max_absolute_money_error.toPrecision(4)}，最大配置比例误差 {result.paired_replay.max_allocation_error.toPrecision(4)}。</p>
      <p className="small">美国历史 {result.history.start} 至 {result.history.end}；原版采样年均值目标 {(100*result.history.stocks.target_sampler_annual_arithmetic_mean).toFixed(2)}%，调整后源序列滚动12月算术均值 {(100*result.history.stocks.source_rolling_statistics.rolling_12m_arithmetic_mean).toFixed(2)}%，复合年化 {(100*result.history.stocks.source_rolling_statistics.compound_annual_growth_rate).toFixed(2)}%。经验采样修正与源序列滚动统计口径不同。</p>
      {result.limits.map(note=><p className="small" key={note}>{note}</p>)}
      <p className="small">本地结果 {result.local_result_id}<br/>输入 <code>{result.input_sha256}</code><br/>抽样 <code>{result.sample_index_sha256}</code></p>
    </>}
  </section>
}
