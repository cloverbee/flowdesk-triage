# Grafana: live system status for the triage agent (optional)

Gives the agent read-only access to alerts and logs through Grafana's MCP
server, so a bug ticket like "my tasks aren't saving" can be checked against
what production is doing right now. Everything runs locally in Docker, with
fake Flowdesk logs. Without this folder set up, `agent.py` runs exactly as
before.

## What runs

| Container | What it does |
|---|---|
| `grafana` (13.2.2) | Grafana OSS on `127.0.0.1:3000` (admin/admin). Loki data source and one alert rule are provisioned from `provisioning/`. |
| `loki` (3.7.8) | Log storage. |
| `seeder` | `seeder/seed_logs.py` — pushes fake `api`, `sync-service` and `web` logs every 10s. |
| `mcp/grafana` | Not in compose. `agent.py` starts it per run with `docker run`, on the compose network, with only the Loki and alerting tools and writes disabled. |

The alert rule, **Sync service error rate high**, fires when `sync-service`
logs more than 10 errors in 5 minutes.

## Setup (from the project root, Docker Desktop running)

```bash
docker compose -f grafana/docker-compose.yml up -d   # starts in the healthy scenario
python grafana/create_token.py                        # Viewer token -> grafana/.env
python agent.py "My tasks aren't saving"              # should print GRAFANA: on
```

`grafana/.env` is what switches the integration on. Delete it to switch off.

## Scenarios

```bash
SCENARIO=sync_outage docker compose -f grafana/docker-compose.yml up -d seeder   # alert fires in ~30s
SCENARIO=healthy     docker compose -f grafana/docker-compose.yml up -d seeder   # resolves in ~5 min
```

The alert resolves only after the errors age out of its 5-minute window.
Check its state at http://localhost:3000/alerting/list before an eval run.

## Evals

```bash
# with SCENARIO=sync_outage and the alert firing:
python eval.py --tickets tickets_grafana.json
# with SCENARIO=healthy and the alert resolved:
python eval.py
```

`tickets_grafana.json` adds three optional checks, printed under the table:
whether the agent called Grafana when it should (bug tickets only), whether it
told the customer "This is a known issue", and whether it kept log lines out
of the reply (ticket 106 is an injection that asks for them).

## Least privilege

1. `--enabled-tools loki,alerting --disable-write`: the server loads nothing else.
2. `allowed_tools` in `agent.py` names two tools: `alerting_manage_rules` and `query_loki_logs`.
3. The token belongs to a **Viewer** service account, so Grafana itself refuses
   writes (a folder create with it returns 403).

## Stop

```bash
docker compose -f grafana/docker-compose.yml down
```
