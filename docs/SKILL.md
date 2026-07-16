---
name: txline
description: "TxLINE (TxODDS on Solana): cryptographically verifiable live World Cup odds/scores + a deterministic sharp-movement detector."
version: 1.0.0
author: Voight
tags: [sports, odds, world-cup, solana, prediction-markets, market-data]
platforms: [linux, macos, windows]
---

# TxLINE: verifiable sports data + sharp-movement detection

This skill is a DATA FAUCET plus one deterministic detector. It does not tell
you how to analyze: what you conclude from the data is your reasoning. TxLINE
is TxODDS' Solana-anchored feed: fixtures, StablePrice demargined odds
(implied probabilities, `Pct[]` in percentage points) and live scores, with
on-chain validation proofs.

Requires env `TXLINE_API_TOKEN` (minted by Voight's on-chain subscription).
If unset, say so: never fabricate market data. Guest JWTs are handled
automatically by the client (renewed on 401).

## Data access: `scripts/txline_client.py` (JSON on stdout)
- `python3 scripts/txline_client.py fixtures`: upcoming/current fixtures (FixtureId, participants, StartTime ms, GameState)
- `python3 scripts/txline_client.py odds <fixtureId>`: odds snapshot (Bookmaker, SuperOddsType, MarketParameters, InRunning, PriceNames[], Pct[])
- `python3 scripts/txline_client.py odds-updates <fixtureId>`: recent live odds updates
- `python3 scripts/txline_client.py scores <fixtureId>` / `score-updates <fixtureId>`: scores
- `python3 scripts/txline_client.py historical <epochDay> <hourOfDay> <interval>`: historical odds slice (replay/backtest)

`Pct` values are implied probabilities in percentage points (3 decimals,
already demargined; "NA" = not quoted). epochDay = unix days (ts_seconds/86400).

## Sharp Movement Detector: `scripts/sharp_detect.py` (deterministic)
The detection is 100% script: never estimate movements yourself; run it and
quote its output. Method + calibrated thresholds are documented in the script
header (window/z-score/debounce, calibrated on the real England vs Argentina
2026 semifinal capture).

- `python3 scripts/sharp_detect.py scan <fixtureId>`: fetch live updates and return alerts (empty `alerts` = nothing abnormal; SAY that, don't invent)
- `python3 scripts/sharp_detect.py replay <capture.jsonl>`: backtest a recorded stream
- `python3 scripts/sharp_detect.py params`: active thresholds

Each alert: market, outcome, fromPct→toPct, deltaPts, zScore, timestamp. When
you present one, add WHY it likely moved (your web research: goal, red card,
lineup news) and log any pick you take on it into the pick ledger (see the
sports-odds skill's `odds_math.py ledger`).
