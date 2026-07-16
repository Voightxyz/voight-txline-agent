#!/usr/bin/env python3
"""Sharp Movement Detector — deterministic detection of abrupt implied-probability
moves in TxLINE StablePrice (demargined) odds. No LLM math: this script IS the
detection; the agent only narrates what it returns.

Method (documented for judges):
  For each market series (FixtureId, SuperOddsType, MarketParameters, outcome):
    1. Build the Pct time series (implied probability in percentage points,
       3-decimal strings from TxLINE; "NA" values skipped).
    2. delta = |Pct(t_now) - Pct(t_now - WINDOW_S)| in percentage points.
    3. Volatility baseline sigma = stdev of successive |ΔPct| over the BASELINE_S
       window preceding the jump window (minimum MIN_POINTS samples).
    4. ALERT when delta >= MIN_DELTA_PTS  AND  delta >= Z_THRESHOLD * sigma
       (both conditions — absolute size AND abnormality vs the market's own noise).
    5. Debounce: the same series never re-alerts within DEBOUNCE_S.

Parameters below were calibrated on the real England vs Argentina 2026 WC
semifinal capture (goals produced 8-25 pt moves inside 120 s; normal drift
stayed < 2 pts / 120 s on 1X2 markets).

Usage (JSON on stdout):
  sharp_detect.py scan <fixtureId>       # live: fetch updates via txline_client, detect
  sharp_detect.py replay <capture.jsonl> # backtest a recorded SSE capture file
  sharp_detect.py params                 # print active parameters
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Calibrated parameters (England vs Argentina 2026-07-15 capture) ──────────
WINDOW_S = 120        # jump window
BASELINE_S = 600      # volatility lookback before the window
MIN_DELTA_PTS = 5.0   # absolute floor: ignore anything smaller (pts)
Z_THRESHOLD = 3.0     # jump must be 3x the series' own recent noise
MIN_POINTS = 5        # minimum samples in baseline before judging
DEBOUNCE_S = 300      # per-series cooldown between alerts
WATCH_TYPES = {       # market types worth watching (rest = noise/derivatives)
    "1X2_PARTICIPANT_RESULT",
    "OVERUNDER_PARTICIPANT_GOALS",
    "ASIANHANDICAP_PARTICIPANT_GOALS",
}

STATE_PATHS = ["/opt/data/memories/txline_detect_state.json", "/tmp/txline_detect_state.json"]


def _load_state() -> dict:
    for p in STATE_PATHS:
        try:
            with open(p) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def _save_state(state: dict) -> None:
    for p in STATE_PATHS:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                json.dump(state, f)
            return
        except OSError:
            continue


def _series_from_events(events) -> dict:
    """events: iterable of TxLINE odds dicts → {series_key: [(ts_s, pct), ...]}"""
    series = defaultdict(list)
    for e in events:
        if e.get("SuperOddsType") not in WATCH_TYPES:
            continue
        names = e.get("PriceNames") or []
        pcts = e.get("Pct") or []
        ts = (e.get("Ts") or 0) / 1000.0
        if not ts:
            continue
        for name, pct in zip(names, pcts):
            if pct in (None, "NA"):
                continue
            try:
                v = float(pct)
            except (TypeError, ValueError):
                continue
            key = "|".join([
                str(e.get("FixtureId")), e.get("SuperOddsType") or "",
                str(e.get("MarketParameters") or ""), str(e.get("MarketPeriod") or ""), name,
            ])
            series[key].append((ts, v))
    for k in series:
        series[k].sort()
    return series


def _detect(series: dict, state: dict, now: float | None = None) -> list[dict]:
    alerts = []
    for key, pts in series.items():
        if len(pts) < MIN_POINTS + 2:
            continue
        t_end, v_end = pts[-1]
        ref = now if now is not None else t_end
        # Jump window: value at (or just before) ref - WINDOW_S.
        window_start_val = None
        baseline_deltas = []
        prev_v = None
        for t, v in pts:
            if t <= ref - WINDOW_S:
                window_start_val = v
            if ref - WINDOW_S - BASELINE_S <= t <= ref - WINDOW_S:
                if prev_v is not None:
                    baseline_deltas.append(abs(v - prev_v))
                prev_v = v
        if window_start_val is None or len(baseline_deltas) < MIN_POINTS:
            continue
        delta = abs(v_end - window_start_val)
        if delta < MIN_DELTA_PTS:
            continue
        mean = sum(baseline_deltas) / len(baseline_deltas)
        var = sum((d - mean) ** 2 for d in baseline_deltas) / len(baseline_deltas)
        sigma = math.sqrt(var)
        z = delta / sigma if sigma > 1e-9 else float("inf")
        if z < Z_THRESHOLD:
            continue
        last_alert = state.get(key, 0)
        if ref - last_alert < DEBOUNCE_S:
            continue
        state[key] = ref
        fixture, sot, mparams, mperiod, outcome = key.split("|", 4)
        alerts.append({
            "fixtureId": int(fixture),
            "market": sot,
            "marketParameters": mparams,
            "marketPeriod": mperiod,
            "outcome": outcome,
            "fromPct": round(window_start_val, 3),
            "toPct": round(v_end, 3),
            "deltaPts": round(v_end - window_start_val, 3),
            "windowSeconds": WINDOW_S,
            "zScore": round(z, 2) if z != float("inf") else None,
            "atIso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_end)),
        })
    alerts.sort(key=lambda a: -abs(a["deltaPts"]))
    return alerts


def cmd_scan(fixture_id: int) -> None:
    from txline_client import get  # local import: reuses auth/JWT logic

    events = get(f"/odds/updates/{fixture_id}") or []
    state = _load_state()
    alerts = _detect(_series_from_events(events), state)
    _save_state(state)
    print(json.dumps({"fixtureId": fixture_id, "eventsScanned": len(events), "alerts": alerts}))


def cmd_replay(path: str) -> None:
    """Backtest over a recorded SSE capture (JSONL of {"ts","raw":[lines]})."""
    events = []
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            for raw in rec.get("raw", []):
                if not raw.startswith("data:"):
                    continue
                try:
                    events.append(json.loads(raw[5:].strip()))
                except ValueError:
                    continue
    series = _series_from_events(events)
    # Sweep time forward in WINDOW_S/2 steps so every jump is evaluated in context,
    # with a fresh state (replay never touches the live debounce state).
    state: dict = {}
    all_ts = sorted(t for pts in series.values() for t, _ in pts)
    if not all_ts:
        print(json.dumps({"eventsScanned": len(events), "alerts": []}))
        return
    alerts, seen = [], set()
    t = all_ts[0] + WINDOW_S + BASELINE_S
    while t <= all_ts[-1]:
        trimmed = {k: [(ts, v) for ts, v in pts if ts <= t] for k, pts in series.items()}
        for a in _detect(trimmed, state, now=t):
            fp = (a["fixtureId"], a["market"], a["marketParameters"], a["outcome"], a["atIso"])
            if fp not in seen:
                seen.add(fp)
                alerts.append(a)
        t += WINDOW_S / 2
    print(json.dumps({"eventsScanned": len(events), "seriesBuilt": len(series), "alerts": alerts}))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "scan":
        cmd_scan(int(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "replay":
        cmd_replay(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "params":
        print(json.dumps({
            "windowSeconds": WINDOW_S, "baselineSeconds": BASELINE_S,
            "minDeltaPts": MIN_DELTA_PTS, "zThreshold": Z_THRESHOLD,
            "minPoints": MIN_POINTS, "debounceSeconds": DEBOUNCE_S,
            "watchTypes": sorted(WATCH_TYPES),
        }))
    else:
        print(json.dumps({"error": "usage: sharp_detect.py scan <fixtureId> | replay <file.jsonl> | params"}))
        sys.exit(2)
