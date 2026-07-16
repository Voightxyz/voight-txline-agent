# TxLINE API — feedback from building this project

Honest notes from integrating TxLINE end-to-end (on-chain subscription →
activation → snapshots → live SSE → historical replay), 15-18 July 2026.

## What worked really well
- **`llms.txt` docs index** — being able to point tooling at a machine-readable
  docs map made discovery fast. More APIs should do this.
- **`Pct[]` demargined implied probabilities** — shipping 3-decimal, vig-free
  probabilities directly in the feed removed a whole class of consumer-side
  math (and consumer-side bugs). This is the single best feature of the feed.
- **Free World Cup tier with real-time level (12)** — zero-cost onboarding with
  production-grade latency is exactly how you get hackathon projects to ship.
- **The example repo (`tx-on-chain`)** — `setupUser` doing wallet → subscribe →
  sign → activate in one call saved us hours.
- **SSE streams** — plain, standard, easy to record and replay.

## Friction we hit (with suggestions)
1. **Examples are devnet-only.** `config.ts` hardcodes devnet hosts and the IDL
   ships with the devnet program address; mainnet values exist only in the docs
   pages. A `--network mainnet` switch (or a mainnet config file) would have
   saved us the manual patching.
2. **Activation is single-use per transaction, and the error doesn't say what
   to do next.** We lost our first API token (didn't persist it) and
   re-activation returned `403 "This transaction has already been used"`. Fair
   security choice — but the error could hint *"subscribe again to mint a new
   token"*, and a `GET /api/token/status` (is my token still valid? which
   level?) would help operators.
3. **Odds schema lives only in the OpenAPI YAML.** The human docs describe the
   feeds narratively; field-level meaning (`SuperOddsType` values,
   `MarketParameters` grammar, `Prices[]` scaling vs `Pct[]`) required reading
   `docs.yaml` + observing live data. A "field reference" page would close that gap.
4. **Fixtures snapshot rotates finished fixtures out quickly.** Minutes after a
   match ends it disappears from `/fixtures/snapshot`; for post-match analysis
   you must already know the FixtureId. A `?includeFinished=true` flag (even
   24h) would help replay/analysis workflows.
5. **Guest JWT lifetime is undocumented.** We renew proactively every 20
   minutes and on 401 — works fine, but a documented TTL (or an `expiresAt` in
   the response) would remove the guesswork.

## Would we build on it again?
Yes. The on-chain subscription flow sounds exotic and turned out to be the
easiest "API key" issuance we've used — one transaction, one signature, done.
The data itself (demargined, timestamped, verifiable) is production-grade.
