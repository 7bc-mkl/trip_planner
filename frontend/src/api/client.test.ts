import { afterEach, describe, expect, it, vi } from 'vitest'

import { request } from './client'

/**
 * The typed fetch client's own guarantees — the ones every caller inherits and
 * none of them restates.
 */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function stubFetch(response: Response = json(200, { ok: true })) {
  const spy = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(response),
  )
  vi.stubGlobal('fetch', spy)
  return spy
}

const initOf = (spy: ReturnType<typeof stubFetch>) => spy.mock.calls[0]?.[1]

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('request', () => {
  it('never reads an API response from the HTTP cache', async () => {
    // QA found this the hard way: the API sends no `Cache-Control`, so a plain
    // GET was open to heuristic caching. Deleting a trip's destination
    // succeeded on the server and the refetch came back from the cache still
    // carrying it, leaving the base on screen. Every one of these responses is
    // private, mutable state the app re-reads *because* it just changed it.
    const spy = stubFetch()

    await request('/trips/trip-1')

    expect(initOf(spy)?.cache).toBe('no-store')
  })

  it('sends the same directive on a write', async () => {
    const spy = stubFetch(new Response(null, { status: 204 }))

    await request('/trips/trip-1/stages/stage-1', { method: 'DELETE' })

    expect(initOf(spy)?.cache).toBe('no-store')
  })

  it('carries the session cookie', async () => {
    const spy = stubFetch()

    await request('/trips')

    expect(initOf(spy)?.credentials).toBe('same-origin')
  })
})
