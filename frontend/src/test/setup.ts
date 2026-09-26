import { configure } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

/**
 * `waitFor` and every `findBy*` built on it get 5s instead of the default 1s.
 *
 * Not because anything here is slow: the suite's screens settle in a few
 * milliseconds when a file runs alone. The default becomes a problem when the
 * whole suite runs in parallel — two dozen jsdom workers on one machine, each
 * advancing real timers between `userEvent` keystrokes — and a render that
 * normally lands in 20ms occasionally crosses one second. The failure that
 * produces is indistinguishable from a real one and always in a different
 * test, which is the worst kind of red build: it teaches people to re-run.
 *
 * Nothing is asserting a wall-clock budget, so the only thing the old ceiling
 * measured was how busy the machine was. A genuine hang still fails, five
 * seconds later.
 */
configure({ asyncUtilTimeout: 5_000 })
