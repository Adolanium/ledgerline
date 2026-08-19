import assert from 'node:assert/strict'
import test from 'node:test'
import { loadPure } from './helpers/pure.mjs'
import { failedTerminal, writeFile } from './fixtures/messages.mjs'

const pure = loadPure()

test('scanSummary and sortWorst rank scanned sessions by failures, suspected optional', () => {
  const a = pure.scanSummary(pure.analyzeMessages(failedTerminal))
  const b = pure.scanSummary(pure.analyzeMessages(writeFile))
  assert.deepEqual(a, { failed: 1, suspected: 0, writes: 0, subagents: 0 })
  assert.deepEqual(b, { failed: 0, suspected: 2, writes: 1, subagents: 0 })
  const s1 = { id: 'a', messageCount: 6, lastActive: 1 }
  const s2 = { id: 'b', messageCount: 10, lastActive: 2 }
  const s3 = { id: 'c', messageCount: 3, lastActive: 3 }
  const scans = { [pure.scanKey(s1)]: a, [pure.scanKey(s2)]: b }
  assert.deepEqual(pure.sortWorst([s3, s2, s1], scans, false).map(x => x.id), ['a', 'b', 'c'], 'unscanned last, ties by recency')
  assert.deepEqual(pure.sortWorst([s1, s2, s3], scans, true).map(x => x.id), ['a', 'b', 'c'])
  const onlySuspected = { [pure.scanKey(s2)]: b, [pure.scanKey(s1)]: { failed: 0, suspected: 0, writes: 0, subagents: 0 } }
  assert.deepEqual(pure.sortWorst([s1, s2], onlySuspected, true).map(x => x.id), ['b', 'a'])
  assert.deepEqual(pure.sortWorst([s1, s2], onlySuspected, false).map(x => x.id), ['b', 'a'], 'both score zero, recency decides')
})

test('searchSessions maps hits and swaps snippet markers for quotes', async () => {
  const d = pure.createDataLayer({
    host: {},
    bridge: { api: async req => ({ results: [{ id: 's1', title: 'T', source: 'tui', model: 'm', started_at: 5, snippet: 'a >>>hit<<< b' }] }) }
  })
  const hits = await d.searchSessions('hit')
  assert.equal(hits.length, 1)
  assert.equal(hits[0].id, 's1')
  assert.equal(hits[0].snippet, 'a “hit” b')
  assert.deepEqual(await d.searchSessions('   '), [])
})
