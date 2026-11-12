const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { test, after } = require('node:test')
const assert = require('node:assert/strict')
const { privateDestination } = require('./PrivateDestination.cjs')

const base = fs.realpathSync(process.env.TPAW_PRIVATE_TEST_TMP || os.tmpdir())
const fixture = fs.mkdtempSync(path.join(base, 'tpaw-private-path-'))
after(() => {
  const resolved = fs.realpathSync(fixture)
  if (path.dirname(resolved) !== base || !path.basename(resolved).startsWith('tpaw-private-path-')) {
    throw Error('Refusing test cleanup outside the verified temporary target')
  }
  fs.rmSync(resolved, { recursive: true })
})
const repo = path.join(fixture, 'repo')
const nested = path.join(repo, 'subdirectory')
fs.mkdirSync(path.join(repo, '.git'), { recursive: true })
fs.mkdirSync(nested)
const link = path.join(fixture, 'outside-link')
fs.symlinkSync(nested, link, process.platform === 'win32' ? 'junction' : 'dir')

test('plain private destination canonicalizes new nested components', () => {
  const expected = path.join(fixture, 'private', 'new', 'result.json')
  assert.equal(privateDestination(expected), expected)
})
test('direct checkout output is refused', () => {
  assert.throws(() => privateDestination(path.join(nested, 'result.json')), /inside Git/)
})
test('outside directory link into a checkout subdirectory is refused', () => {
  assert.throws(() => privateDestination(path.join(link, 'new', 'result.json')), /inside Git/)
})
