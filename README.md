# voight-txline-agent: Sharp Movement Detector on Voight

**TxLINE World Cup Hackathon 2026 submission.** An autonomous [Voight](https://agent.voight.xyz)
agent that watches TxLINE's Solana-anchored World Cup odds in real time, detects
sharp market movements with a fully deterministic algorithm, explains them with
live research, and alerts its owner over Telegram, with every pick logged to an
auditable calibration ledger.

> We didn't build a bot for this hackathon. We plugged TxLINE into a platform
> where anyone can deploy an agent like this one in two minutes.

## What's in this repo

| Path | What it is |
|---|---|
| `detector/sharp_detect.py` | The deterministic Sharp Movement Detector (documented math: rolling window + z-score vs the market's own noise + debounce). No LLM in the loop. |
| `detector/txline_client.py` | Minimal TxLINE API client (guest-JWT auto-renewal + API token from the on-chain subscription). |
| `docs/SKILL.md` | The hermes skill file the deployed agent loads (data-faucet style). |
| `docs/TECHNICAL.md` | Architecture, exact TxLINE endpoints used, detection math, calibration data. |
| `docs/API-FEEDBACK.md` | Our feedback on the TxLINE API from building this. |
| `captures/` | The full real SSE capture (755 KB, 1,773 events) from the England vs Argentina semifinal used for calibration. |

## The detector in 20 seconds

For every market series (fixture × market type × outcome), using TxLINE's
demargined `Pct[]` implied probabilities:

```
alert  ⇔  |ΔPct| over 120s ≥ 5 pts  AND  |ΔPct| ≥ 3σ of the series' own recent noise
          (then a 5-minute per-series debounce)
```

Calibrated on the real England vs Argentina 2026 semifinal, it fired exactly
twice (the violent repricing of *under 3.5 goals*, +10.7 pts, z≈18, as
regulation ended 1-1) and stayed silent through normal drift. Run it yourself:

```bash
python3 detector/sharp_detect.py replay captures/odds-stream-semifinal-20260715.jsonl
```

## Verify it yourself (2 minutes, no keys needed)

The calibration backtest runs locally on the real semifinal capture with the
Python standard library only (3.10+):

```bash
git clone https://github.com/Voightxyz/voight-txline-agent
cd voight-txline-agent
python3 detector/sharp_detect.py replay captures/odds-stream-semifinal-20260715.jsonl
python3 detector/sharp_detect.py params
```

To run the detector against live TxLINE data, mint your own API token with the
free World Cup tier (one on-chain transaction; see [TxLINE's quickstart](https://txline.txodds.com/documentation/quickstart))
and set `TXLINE_API_TOKEN`:

```bash
export TXLINE_API_TOKEN=<your token>
python3 detector/txline_client.py fixtures
python3 detector/sharp_detect.py scan <fixtureId>
```

Our on-chain subscription: [`21jNAk2y…C5su4`](https://solscan.io/tx/21jNAk2yYp7u7Ua1wTSRNMh9Mhw239cjAdLLkth4YHSr9pKpwsdr5aN8Whmhynnk2FcFufwcBbMsE6pMx8rC5su4)
(Service Level 12, paid by the same wallet that registers our agents on-chain).

## Live deployment

The detector runs inside a production Voight agent (Google Cloud Run, private,
scale-to-zero) with a scheduled task scanning active fixtures. Alerts arrive on
Telegram with a market card; every pick is logged with a timestamp into a
persistent ledger (Brier-scored: the agent's track record is auditable, not
claimed). Agent identity is registered on-chain (Metaplex MPL Agent Registry,
Solana mainnet): the same wallet that pays our TxLINE subscription.

## Track record

**Development run (July 9-15, 2026): 7 for 7.** During development, our
prediction agent called seven consecutive winners across World Cup knockouts
and MLB moneylines, including **Spain over France against a 28.5% market
price** (the referee factor it flagged decided the opening goal).

## Team

Built by [Voight](https://voight.xyz): autonomous agents, deployed in minutes.
