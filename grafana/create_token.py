"""
create_token.py — Creates a Viewer-role Grafana service account for the
agent and writes its token to grafana/.env (gitignored).

Viewer is the least privilege that works: it can read alert rules and query
Loki, and nothing else. Even if the model were talked into it, Grafana
itself would refuse any write.

Usage (after `docker compose -f grafana/docker-compose.yml up -d`):
    python grafana/create_token.py
"""

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

GRAFANA_URL = "http://localhost:3000"
ADMIN_AUTH = base64.b64encode(b"admin:admin").decode()
SA_NAME = "flowdesk-triage-agent"
ENV_FILE = Path(__file__).parent / ".env"


def api(method: str, path: str, body: dict | None = None) -> dict | list:
    req = urllib.request.Request(
        f"{GRAFANA_URL}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {ADMIN_AUTH}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def find_or_create_service_account() -> int:
    found = api("GET", f"/api/serviceaccounts/search?query={SA_NAME}")
    for sa in found["serviceAccounts"]:
        if sa["name"] == SA_NAME:
            return sa["id"]
    return api("POST", "/api/serviceaccounts", {"name": SA_NAME, "role": "Viewer"})["id"]


def main() -> None:
    sa_id = find_or_create_service_account()
    token = api("POST", f"/api/serviceaccounts/{sa_id}/tokens", {"name": f"agent-{int(time.time())}"})

    # Read by `docker run --env-file` when agent.py starts mcp-grafana, which
    # runs on the compose network — hence grafana:3000, not localhost:3000.
    ENV_FILE.write_text(
        "GRAFANA_URL=http://grafana:3000\n"
        f"GRAFANA_SERVICE_ACCOUNT_TOKEN={token['key']}\n"
    )
    print(f"Viewer token for service account '{SA_NAME}' written to {ENV_FILE}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach Grafana at {GRAFANA_URL} ({exc}). Is the stack up?")
