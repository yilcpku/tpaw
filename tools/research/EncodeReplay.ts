// Local file adapter: use the author's guard, normalizer, server conversion and
// generated protobuf encoder. No fetch, cloud client, telemetry or credentials.
import fs from 'node:fs'
import crypto from 'node:crypto'
import { privateDestination } from './PrivateDestination.cjs'
import { CalendarDayFns, normalizePlanParams, planParamsGuard } from '@tpaw/common'
import { getPlanParamsServer } from '../../packages/web/src/Simulator/SimulateOnServer/GetPlanParamsServer'
import { WireSimulationArgs } from '../../packages/web/src/Simulator/SimulateOnServer/Wire/wire_simulate_api'

let phase = 'arguments'
function main() {
  const [input, output] = process.argv.slice(2)
  if (!input || !output || process.argv.length !== 4) throw Error('usage')
  const dest = privateDestination(output)
  const scenario = JSON.parse(fs.readFileSync(input, 'utf8').replace(/^\uFEFF/, ''))
  phase = 'author plan guard'
  const plan = planParamsGuard(scenario.plan).force()
  phase = 'experiment controls'
  const run = scenario.run
  if (!Number.isSafeInteger(run.seed) || run.seed < 0 || !Number.isInteger(run.simulation_count) ||
      run.simulation_count < 1 || run.simulation_count > 10000 || !Number.isSafeInteger(run.evaluation_timestamp_ms) ||
      typeof run.timezone !== 'string') throw Error('invalid experiment controls')
  const balance = plan.wealth.portfolioBalance
  phase = 'explicit balance'
  if ((balance.isDatedPlan && !balance.updatedHere) || !('amount' in balance) ||
      !Number.isFinite(balance.amount) || balance.amount < 0) throw Error('explicit balance required')
  phase = 'author normalization'
  const norm = normalizePlanParams(plan, { timestamp: run.evaluation_timestamp_ms,
    calendarDay: plan.datingInfo.isDated ? CalendarDayFns.fromTimestamp(run.evaluation_timestamp_ms, run.timezone) : null })
  phase = 'server conversion'
  const request: WireSimulationArgs = {
    currentPortfolioBalance: { $case: 'noEstimate', noEstimate: balance.amount },
    marketDailySeriesSrc: { $case: 'live', live: {} },
    percentiles: [5, 50, 95],
    timestampForMarketDataMs: norm.datingInfo.timestampForMarketData,
    planParams: getPlanParamsServer(norm, run.simulation_count, run.seed),
  }
  phase = 'protobuf output'
  const bytes = WireSimulationArgs.encode(request).finish()
  fs.writeFileSync(dest, bytes, { flag: 'wx' })
  fs.writeFileSync(dest + '.sha256', crypto.createHash('sha256').update(bytes).digest('hex') + '\n', { flag: 'wx' })
  console.log('Author guard and normalization passed; local request encoded')
}
try { main() } catch { console.error('Request encoding failed at ' + phase + '; no plan data logged'); process.exitCode = 2 }
