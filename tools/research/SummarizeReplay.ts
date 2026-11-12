// Percentile-only comparison. Never infer pathwise hardship from marginal arrays.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { privateDestination } from './PrivateDestination.cjs'
import { WireSimulationArgs, WireSimulationResult } from '../../packages/web/src/Simulator/SimulateOnServer/Wire/wire_simulate_api'

try {
  const [root, outputArgument] = process.argv.slice(2)
  if (!root || !outputArgument) throw Error('arguments')
  const output = privateDestination(outputArgument)
  const summaries: any[] = []
  const csv: any[][] = [['case', 'retirement_month', 'risk_at20', 'time_preference', 'years_after_retirement', 'percentile', 'general_monthly_real_hkd', 'total_monthly_real_hkd', 'balance_start_real_hkd', 'stocks_fraction_savings_portfolio']]
  const hash = (x: any) => crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex')
  for (const name of fs.readdirSync(root).filter(x => x.endsWith('-result.pb')).sort()) {
    const stem = name.slice(0, -'-result.pb'.length)
    const scenario = JSON.parse(fs.readFileSync(path.join(root, stem + '-case.json'), 'utf8'))
    const request = WireSimulationArgs.decode(fs.readFileSync(path.join(root, stem + '-request.pb')))
    const result = WireSimulationResult.decode(fs.readFileSync(path.join(root, name)))
    const months = request.planParams!.ages!.simulationMonths!.numMonths
    const start = request.planParams!.ages!.simulationMonths!.withdrawalStartMonth
    const a = result.arrays!
    const points: any[] = []
    for (const years of [0, 5, 10, 20, 30]) {
      const m = start + years * 12
      if (m >= months) continue
      const values = request.percentiles.map((p, pi) => {
        const i = pi * months + m
        const row = { percentile: p, general_monthly_real_hkd: a.byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100[i] / 100,
          total_monthly_real_hkd: a.byPercentileByMfnSimulatedPercentileMajorWithdrawalsTotalX100[i] / 100,
          balance_start_real_hkd: a.byPercentileByMfnSimulatedPercentileMajorBalanceStartX100[i] / 100,
          stocks_fraction_savings_portfolio: a.byPercentileByMfnSimulatedPercentileMajorAfterWithdrawalsAllocationSavingsPortfolioX10000[i] / 10000 }
        if (Object.values(row).some(x => !Number.isFinite(x))) throw Error('invalid result')
        csv.push([scenario.id, scenario.retirement_month ?? 'saved_original', scenario.plan.risk.tpaw.riskTolerance.at20,
          scenario.plan.risk.tpaw.timePreference, years, ...Object.values(row)])
        return row
      })
      points.push({ years_after_retirement: years, values })
    }
    const history = result.planParamsProcessed!.historicalReturns!
    summaries.push({ id: scenario.id, retirement_month: scenario.retirement_month ?? null,
      preferences: scenario.plan.risk.tpaw, run: scenario.run, months, withdrawal_start_month_index: start,
      sample_generator_inputs_sha256: hash({ sampling: request.planParams!.advanced!.sampling, months, history }),
      sample_matrix_exported: false, points, ending_balance_percentiles: a.byPercentileEndingBalance,
      engine_num_runs_with_insufficient_funds: result.numRunsWithInsufficientFunds,
      processed_presets: result.planParamsProcessed!.marketDataForPresets,
      request_sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, stem + '-request.pb'))).digest('hex'),
      result_sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex') })
  }
  if (!summaries.length) throw Error('no results')
  fs.mkdirSync(output, { recursive: true })
  fs.writeFileSync(path.join(output, 'comparison.json'), JSON.stringify({
    status: 'local_empirical_benchmark_website_parity_unconfirmed', summaries,
    sample_generator_inputs_equal: new Set(summaries.map(x => x.sample_generator_inputs_sha256)).size === 1,
    caveats: ['Pointwise percentiles are different paths at different dates, not coherent percentile trajectories.',
      'No pathwise ever-below-budget probability, cut duration, mortality-weighted consumption or strategy ranking is available from these arrays.',
      'Same sample generator inputs on the same binary/toolchain imply common random paths by source design; the realized index matrix is not exported.',
      'HKD in the saved plan purchasing-power base; fixed FX conversion is not RMB inflation/FX simulation.',
      'Essential-expense insufficiency is not the probability of falling below a preferred ongoing budget.',
      'Whole TPAW strategy changes allocation with preferences; this is not a withdrawal-only matched-allocation comparison.'] }, null, 2), { flag: 'wx' })
  const quote = (v: any) => '"' + String(v).replace(/"/g, '""') + '"'
  fs.writeFileSync(path.join(output, 'comparison.csv'), csv.map(r => r.map(quote).join(',')).join('\n') + '\n', { flag: 'wx' })
  console.log('Private percentile comparison JSON and CSV written; no pathwise probability inferred')
} catch { console.error('Summary failed; no financial values logged'); process.exitCode = 2 }
