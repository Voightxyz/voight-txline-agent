#!/usr/bin/env python3
"""TxLINE data client: cryptographically verifiable sports data (TxODDS on Solana).

Auth model: a long-lived API token (env TXLINE_API_TOKEN, minted by an on-chain
subscription) + a short-lived guest JWT fetched automatically and cached; on 401
the JWT is renewed once and the request retried. No secrets are ever printed.

Usage (all output is JSON on stdout):
  txline_client.py fixtures                       # upcoming/current fixtures
  txline_client.py odds <fixtureId>               # odds snapshot for a fixture
  txline_client.py odds-updates <fixtureId>       # recent odds updates (live)
  txline_client.py scores <fixtureId>             # scores snapshot
  txline_client.py score-updates <fixtureId>      # live score updates
  txline_client.py historical <epochDay> <hour> <interval>   # historical odds hour-slice
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://txline.txodds.com"
JWT_CACHE = "/tmp/txline_jwt.json"
JWT_TTL_S = 20 * 60  # renew proactively; server enforces the real expiry


def _fail(msg: str, code: int = 1):
    print(json.dumps({"error": msg}))
    sys.exit(code)


def _api_token() -> str:
    tok = os.environ.get("TXLINE_API_TOKEN", "").strip()
    if not tok:
        _fail("TXLINE_API_TOKEN is not set: TxLINE access is unavailable in this environment")
    return tok


def _fresh_jwt() -> str:
    req = urllib.request.Request(f"{BASE}/auth/guest/start", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    jwt = d.get("token") if isinstance(d, dict) else d
    try:
        with open(JWT_CACHE, "w") as f:
            json.dump({"jwt": jwt, "at": time.time()}, f)
        os.chmod(JWT_CACHE, 0o600)
    except OSError:
        pass
    return jwt


def _jwt() -> str:
    try:
        with open(JWT_CACHE) as f:
            c = json.load(f)
        if time.time() - c.get("at", 0) < JWT_TTL_S and c.get("jwt"):
            return c["jwt"]
    except (OSError, ValueError):
        pass
    return _fresh_jwt()


def get(path: str):
    """GET an /api path with auth; renew the JWT once on 401."""
    token = _api_token()
    for attempt in (1, 2):
        req = urllib.request.Request(
            f"{BASE}/api{path}",
            headers={"Authorization": f"Bearer {_jwt() if attempt == 1 else _fresh_jwt()}",
                     "X-Api-Token": token},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                continue  # renew JWT and retry once
            _fail(f"TxLINE HTTP {e.code} on {path}: {e.read()[:200]!r}")
        except Exception as e:  # noqa: BLE001
            _fail(f"TxLINE request failed on {path}: {type(e).__name__}: {e}")
    return None  # unreachable


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        _fail(__doc__.strip(), 2)
    cmd = argv[1]
    if cmd == "fixtures":
        out = get("/fixtures/snapshot")
    elif cmd == "odds" and len(argv) == 3:
        out = get(f"/odds/snapshot/{int(argv[2])}")
    elif cmd == "odds-updates" and len(argv) == 3:
        out = get(f"/odds/updates/{int(argv[2])}")
    elif cmd == "scores" and len(argv) == 3:
        out = get(f"/scores/snapshot/{int(argv[2])}")
    elif cmd == "score-updates" and len(argv) == 3:
        out = get(f"/scores/updates/{int(argv[2])}")
    elif cmd == "historical" and len(argv) == 5:
        out = get(f"/odds/updates/{int(argv[2])}/{int(argv[3])}/{int(argv[4])}")
    else:
        _fail("unknown command: run with no args for usage", 2)
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv)
