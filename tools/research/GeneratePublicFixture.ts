// Entirely generic example constructed from the repository defaults.
// Deliberately reads no user plan, export, holdings or personal configuration.
import fs from 'node:fs'
import { CalendarDayFns, getFullDatedDefaultPlanParams, normalizePlanParams, planParamsGuard } from '@tpaw/common'
import { getPlanParamsServer } from '../../packages/web/src/Simulator/SimulateOnServer/GetPlanParamsServer'
import { WireSimulationArgs } from '../../packages/web/src/Simulator/SimulateOnServer/Wire/wire_simulate_api'
const output = process.argv[2]
if (!output) throw Error('Output directory required')
const timestamp = Date.now()
const plan = getFullDatedDefaultPlanParams(timestamp, 'Etc/UTC')
plan.wealth.portfolioBalance = { isDatedPlan: true, updatedHere: true, amount: 1000000 }
planParamsGuard(plan).force()
const norm = normalizePlanParams(plan, { timestamp, calendarDay: CalendarDayFns.fromTimestamp(timestamp, 'Etc/UTC') })
const request: WireSimulationArgs = {
  currentPortfolioBalance: { $case: 'noEstimate', noEstimate: 1000000 },
  marketDailySeriesSrc: { $case: 'live', live: {} }, percentiles: [5, 50, 95],
  timestampForMarketDataMs: norm.datingInfo.timestampForMarketData,
  planParams: getPlanParamsServer(norm, 1000, 860336713),
}
fs.mkdirSync(output, { recursive: true })
fs.writeFileSync(output + '/generic-request.pb', WireSimulationArgs.encode(request).finish(), { flag: 'wx' })
fs.writeFileSync(output + '/generic-case.json', JSON.stringify({
  classification: 'nonpersonal-public-example',
  provenance: 'Constructed solely from upstream defaults and a round illustrative balance; no user exports read',
  plan, run: { seed: 860336713, simulation_count: 1000, evaluation_timestamp_ms: timestamp, timezone: 'Etc/UTC' },
}, null, 2), { flag: 'wx' })
console.log('Nonpersonal default example generated without reading any user plan')
