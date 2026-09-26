"""
seed_logs.py — Pushes fake Flowdesk service logs into Loki every few seconds.

Runs inside the `seeder` container (see docker-compose.yml). Standard
library only. SCENARIO picks what the logs look like:

    healthy      normal traffic from api, sync-service and web
    sync_outage  the same, plus a steady stream of sync-service write failures
"""

import json
import os
import random
import time
import urllib.request

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
SCENARIO = os.environ.get("SCENARIO", "healthy")
INTERVAL_S = 10

HEALTHY_LINES = {
    "api": [
        "GET /v1/projects 200 42ms",
        "POST /v1/tasks 201 67ms",
        "GET /v1/users/me 200 18ms",
    ],
    "sync-service": [
        "sync batch committed changes=12 devices=3",
        "websocket connected client=ios",
        "sync batch committed changes=4 devices=2",
    ],
    "web": [
        "served /app/board 200",
        "served /app/calendar 200",
    ],
}

OUTAGE_LINES = [
    "sync write failed: upstream timeout after 30000ms (shard=us-east-2)",
    "sync write failed: connection reset by peer (shard=us-east-2)",
    "task save rejected: sync queue full, dropping client batch",
]


def push(streams: dict[tuple[str, str], list[str]]) -> None:
    now_ns = time.time_ns()
    body = {
        "streams": [
            {
                "stream": {"service": service, "level": level, "env": "prod"},
                "values": [[str(now_ns + i), line] for i, line in enumerate(lines)],
            }
            for (service, level), lines in streams.items()
        ]
    }
    req = urllib.request.Request(
        f"{LOKI_URL}/loki/api/v1/push",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=5).close()


def one_batch() -> dict[tuple[str, str], list[str]]:
    streams = {
        (service, "info"): random.sample(lines, k=2)
        for service, lines in HEALTHY_LINES.items()
    }
    if SCENARIO == "sync_outage":
        # ~5 errors per 10s: well over the alert's 10-per-5-minutes threshold
        streams[("sync-service", "error")] = random.choices(OUTAGE_LINES, k=5)
    return streams


def main() -> None:
    print(f"seeder: scenario={SCENARIO}, pushing to {LOKI_URL} every {INTERVAL_S}s")
    while True:
        try:
            push(one_batch())
        except OSError as exc:  # Loki still starting up, or restarting
            print(f"seeder: push failed ({exc}), retrying")
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
