// Resolve existing ancestors through junctions/symlinks before enforcing the
// research tools' stricter outside-every-Git-checkout private-output contract.
const fs = require('node:fs')
const path = require('node:path')

function privateDestination(destination) {
  let existing = path.resolve(destination)
  const missing = []
  while (!fs.existsSync(existing)) {
    const parent = path.dirname(existing)
    if (parent === existing) throw Error('private output parent unavailable')
    missing.unshift(path.basename(existing))
    existing = parent
  }
  const resolved = path.join(fs.realpathSync(existing), ...missing)
  for (let parent = resolved; ; parent = path.dirname(parent)) {
    if (fs.existsSync(path.join(parent, '.git'))) throw Error('private output inside Git')
    if (parent === path.dirname(parent)) break
  }
  return resolved
}

module.exports = { privateDestination }
if (require.main === module) {
  try {
    if (process.argv.length !== 3) throw Error('arguments')
    process.stdout.write(privateDestination(process.argv[2]))
  } catch {
    console.error('Private destination validation failed; no files written')
    process.exitCode = 2
  }
}
