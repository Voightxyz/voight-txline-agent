# Technical documentation — Sharp Movement Detector on Voight

## Architecture

```
TxLINE (Solana mainnet)                       Voight platform (production)
┌──────────────────────┐                     ┌──────────────────────────────────┐
│ on-chain subscription │  API token          │ per-agent container (Cloud Run,  │
│ (program 9ExbZ…KaA,   ├────────────────────▶│ private, scale-to-zero)          │
│ level 12, real-time)  │                     │  ├─ hermes runtime + LLM         │
└──────────────────────┘                     │  ├─ skill: txline                 │
┌──────────────────────┐   REST + SSE        │  │   ├─ txline_client.py (auth)  │
│ /api/fixtures|odds|   ├────────────────────▶│  │   └─ sharp_detect.py (DETERM.)│
│ scores + /stream      │                     │  └─ skill: sports-odds (ledger)  │
└──────────────────────┘                     └───────────────┬──────────────────┘
                                              scheduled task │ alerts
                                              (Voight tasks  ▼
                                              scheduler)   Telegram + market card
```

- **Detection is deterministic** (`sharp_detect.py`) — the LLM never does market
  math. The agent narrates alerts and adds context via web research (Tavily).
- **Identity on-chain**: the agent is registered in the Metaplex MPL Agent
  Registry on Solana mainnet, paid by the same wallet as the TxLINE
  subscription.
- **Track record**: every pick is logged to a persistent ledger
  (`odds_math.py ledger add/settle/report`) with timestamps and Brier scoring.

## Exact TxLINE endpoints used

| Endpoint | Use |
|---|---|
| `POST /auth/guest/start` | guest JWT (auto-renewed on 401 / every 20 min) |
| on-chain `subscribe(12, 4)` + `POST /api/token/activate` | API token (signature: `txSig::jwt`) |
| `GET /api/fixtures/snapshot` | discover active fixtures |
| `GET /api/odds/snapshot/{fixtureId}` | current odds state |
| `GET /api/odds/updates/{fixtureId}` | live updates for detection scans |
| `GET /api/odds/updates/{epochDay}/{hour}/{interval}` | historical replay/backtests |
| `GET /api/scores/snapshot|updates/{fixtureId}` | score context for alerts |
| `GET /api/odds/stream`, `/api/scores/stream` (SSE) | live capture (calibration recordings) |

Network: mainnet (`txline.txodds.com`), program `9ExbZjAapQww1vfcisDmrngPinHTEfpjYRWMunJgcKaA`.

## Detection math (the judged part)

For each series *(FixtureId, SuperOddsType, MarketParameters, outcome)* built
from `Pct[]` (demargined implied probability, percentage points):

1. **Jump**: `Δ = |Pct(t) − Pct(t − W)|` with `W = 120 s`.
2. **Noise baseline**: `σ` = stdev of successive `|ΔPct|` over the 600 s
   preceding the jump window (≥ 5 samples required).
3. **Alert** ⇔ `Δ ≥ 5 pts` **AND** `Δ ≥ 3σ` — an absolute floor so tiny markets
   can't alert on noise, and a relative test so calm markets alert on genuinely
   abnormal moves.
4. **Debounce**: a series stays quiet 300 s after alerting.
5. Watched market types: `1X2_PARTICIPANT_RESULT`, `OVERUNDER_PARTICIPANT_GOALS`,
   `ASIANHANDICAP_PARTICIPANT_GOALS` (derivative/period markets excluded as noise).

### Calibration on real data
Recorded the live SSE feed during England vs Argentina (2026 WC semifinal,
fixture 18241006): 1,773 odds events, 32 series. The detector fired **exactly
2 alerts** — the `under/over 3.5 goals` repricing (±10.7 pts, z ≈ 18) as
regulation ended 1-1 — and nothing else. Reproduce:

```bash
python3 detector/sharp_detect.py replay captures/sample-odds-stream.jsonl
python3 detector/sharp_detect.py params
```

## Ops notes
- Credentials: `TXLINE_API_TOKEN` env in the agent container; JWTs are
  ephemeral and cached in `/tmp`.
- The scheduled task runs every few minutes during match windows; "no alerts"
  produces no message (silence is a feature).
- Detector state (debounce) persists at `/opt/data/memories/` (GCS-backed, so
  it survives container restarts).
