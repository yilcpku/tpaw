import Chart,{type Profile} from './Chart'

export type NativeBaseline={name:string;profiles:Profile[];source_currency:string;fixed_import_fx:number;evaluation_month:string;
  retirement_month:string;runs:number;aggregation:string;first_month_general_annual_q5_q50_q95:number[];request_sha256:string;
  result_sha256:string;limits:string[];additional_input_changes?:string[];import_inputs_unchanged?:boolean;intended_changes?:string[];
  planning:{stock_return:number;bond_return:number;stock_annual_log_variance:number;risk_tolerance:number;time_preference:number}}

const fields:Record<string,string>={initial_assets:'初始资产',current_age:'年龄',evaluation_month:'评估月',candidates:'退休日',
  notice_months:'通知期',threshold_annual:'门槛',annual_budget:'年度预算',reserve:'准备金金额',reserve_basis:'准备金价格口径',
  reserve_funding:'准备金划分时点',cash_multiple:'现金底线',defensive:'防御资产',term_years:'期限',cashflow_rows:'阶段现金流',
  planning_cpi:'规划CPI',savings_mode:'储蓄模式',savings_coverage_end:'储蓄覆盖日期',risk_tolerance:'风险容忍度',policy_rra:'导入风险曲线',
  policy_variance_annual:'规划方差',time_preference:'时间偏好',additional_spending_tilt:'额外支出倾斜',stock_return:'预期收益',
  stock_volatility:'采样波动',planning_defensive_return:'防御规划收益',horizon:'规划终点',margin:'安全年数',dataset:'市场数据',
  use_forward_targets:'前瞻校准',seed:'种子',runs:'路径数'}
export default function NativeReference({baseline:b}: {baseline:NativeBaseline}) {
  return <section><h2>{b.name}</h2><p>评估月 {b.evaluation_month} · 退休月 {b.retirement_month} · {b.runs} 条原生路径。源单位 {b.source_currency}，按归档固定汇率 {b.fixed_import_fx} 等比例显示为人民币记账金额。</p>
    <p className="notice">原版归档结果保持不变。它沿用美国实际收益与原版抽样，不是当前编辑情景的重跑，也不能将两张图的差额单独归因于全球股票。</p>
    {b.additional_input_changes&&<p className={b.import_inputs_unchanged?'small':'notice'}>{b.import_inputs_unchanged?'当前输入与已登记的导入情景一致；有意改动如下。':'导入后另外修改了：'+b.additional_input_changes.map(key=>fields[key]||key).join('、')+'。归档结果没有跟随这些编辑重跑。'}</p>}
    {b.intended_changes?.map(note=><p className="small" key={note}>{note}</p>)}
    <Chart rows={b.profiles} caption={b.aggregation+' · 等比例人民币记账'} footnote="原版图严格使用已归档月度分位数；修改版主图为各条路径的年度日常支出总和分位数，聚合口径不同。"/>
    <p>退休当月一般支出年度化的5% /50% /95%：{b.first_month_general_annual_q5_q50_q95.map(v=>'¥'+Math.round(v).toLocaleString()).join(' / ')}。</p>
    <p className="small">规划股票收益 {b.planning.stock_return.toFixed(2)}% · 防御收益 {b.planning.bond_return.toFixed(2)}% · 年度对数方差 {b.planning.stock_annual_log_variance.toPrecision(5)} · 风险容忍度 {b.planning.risk_tolerance} · 时间偏好 {b.planning.time_preference}。</p>
    {b.limits.map(note=><p className="small" key={note}>{note}</p>)}<p className="small">原生请求 <code>{b.request_sha256}</code><br/>原生结果 <code>{b.result_sha256}</code></p>
  </section>
}
