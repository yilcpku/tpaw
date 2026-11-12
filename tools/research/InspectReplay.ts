import fs from 'node:fs'
import crypto from 'node:crypto'
import { privateDestination } from './PrivateDestination.cjs'
import { WireSimulationArgs, WireSimulationResult } from '../../packages/web/src/Simulator/SimulateOnServer/Wire/wire_simulate_api'

try {
  const [requestFile, resultFile, outputArgument, repeatFile] = process.argv.slice(2)
  if (!requestFile || !resultFile || !outputArgument) throw Error('usage')
  const outputFile = privateDestination(outputArgument)
  const request = WireSimulationArgs.decode(fs.readFileSync(requestFile))
  const result = WireSimulationResult.decode(fs.readFileSync(resultFile))
  const sampling = request.planParams?.advanced?.sampling
  if (sampling?.$case !== 'monteCarlo' || result.numRuns !== sampling.monteCarlo.numRuns || !result.arrays) throw Error('run count')
  const months = request.planParams?.ages?.simulationMonths?.numMonths
  if (!months || request.percentiles.length !== 3) throw Error('dimensions')
  let arraysChecked = 0
  for (const [name, values] of Object.entries(result.arrays)) {
    if (!Array.isArray(values) || values.some(x => !Number.isFinite(x))) throw Error('invalid array')
    if (values.length !== (name === 'byPercentileEndingBalance' ? 3 : 3 * months)) throw Error('array dimensions')
    arraysChecked++
  }
  if (!result.arrays.byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100.some(x => x > 0)) throw Error('no positive retirement consumption')
  // Rust HashMaps are serialized as id-keyed repeated records in arbitrary order.
  // Normalize only that non-semantic order, retaining all numeric time/path arrays.
  const ordered = (value: any): any => {
    if (Array.isArray(value)) {
      const copy = value.map(ordered)
      return copy.length && copy.every(x => x && typeof x === 'object' && typeof x.id === 'string')
        ? copy.sort((a, b) => a.id.localeCompare(b.id)) : copy
    }
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])]))
    return value
  }
  const canonical = (value: typeof result) => JSON.stringify(ordered({ ...value, performance: undefined }))
  const comparableHash = crypto.createHash('sha256').update(canonical(result)).digest('hex')
  const repeatedIdentical = repeatFile ? canonical(WireSimulationResult.decode(fs.readFileSync(repeatFile))) === canonical(result) : null
  if (repeatFile && !repeatedIdentical) throw Error('determinism mismatch')
  fs.writeFileSync(outputFile, JSON.stringify({ status: 'computed_with_supplied_snapshot',
    original_website_result_reproduced: false, arrays_checked: arraysChecked,
    request_sha256: crypto.createHash('sha256').update(fs.readFileSync(requestFile)).digest('hex'),
    result_sha256: crypto.createHash('sha256').update(fs.readFileSync(resultFile)).digest('hex'),
    result_without_performance_sha256: comparableHash,
    repeat_identical_excluding_performance_and_id_record_order: repeatedIdentical, result }, null, 2), { flag: 'wx' })
  console.log('Replay dimensions, finite arrays, positive consumption and requested repeat check passed; private JSON saved')
} catch (error) {
  const reason = error instanceof Error && ['usage', 'private output inside Git', 'run count', 'dimensions',
    'invalid array', 'array dimensions', 'no positive retirement consumption', 'determinism mismatch'].includes(error.message)
    ? error.message : 'input/output error'
  console.error('Replay inspection failed: ' + reason + '; no financial data logged'); process.exitCode = 2
}
