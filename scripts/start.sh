#!/bin/bash
# Start everything for a live demo: AgentField control plane, agent node, web app, optional public tunnel.
#   scripts/start.sh            local only
#   scripts/start.sh --tunnel   also open a Cloudflare quick tunnel so the QR code works on phones
#   scripts/start.sh --stop     stop what this script started
# Add --rehearsal to any start to reuse saved research for a URL and market that already ran
# (no Tavily credits; the run logs "CACHED RESEARCH"). Leave it off for the judged demo.
# PIDs go to /tmp/launchlocal-pids; logs to /tmp/launchlocal-*.log.
set -u
cd "$(dirname "$0")/.."
export PATH="$HOME/.agentfield/bin:$HOME/.codeaf/bin:$PATH"
PIDS=/tmp/launchlocal-pids

stop() {
  [ -f "$PIDS" ] || return 0
  while read -r pid name; do kill "$pid" 2>/dev/null && echo "stopped $name ($pid)"; done < "$PIDS"
  : > "$PIDS"
}

if [ "${1:-}" = "--stop" ]; then stop; exit 0; fi
stop
TUNNEL=0
for arg in "$@"; do
  [ "$arg" = "--tunnel" ] && TUNNEL=1
  [ "$arg" = "--rehearsal" ] && export LAUNCHLOCAL_RESEARCH_CACHE=1 && echo "rehearsal mode: saved research is reused"
done

if ! curl -s -o /dev/null --max-time 2 http://localhost:8080/ui/; then
  nohup af server --open=false > /tmp/launchlocal-af.log 2>&1 &
  echo "$! af-server" >> "$PIDS"
  sleep 3
fi

# an agent node or web app started outside this script would hold the ports
for port in 8001 8787; do
  old=$(lsof -ti tcp:$port -sTCP:LISTEN 2>/dev/null | head -1)
  [ -n "$old" ] && kill "$old" && echo "stopped the process on port $port ($old)" && sleep 1
done

nohup .venv/bin/python -m launchlocal.agents > /tmp/launchlocal-agent.log 2>&1 &
echo "$! agent-node" >> "$PIDS"

PUBLIC=""
if [ "$TUNNEL" = "1" ]; then
  nohup cloudflared tunnel --url http://127.0.0.1:8787 > /tmp/launchlocal-tunnel.log 2>&1 &
  echo "$! tunnel" >> "$PIDS"
  for _ in $(seq 1 30); do
    PUBLIC=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/launchlocal-tunnel.log | head -1)
    [ -n "$PUBLIC" ] && break
    sleep 1
  done
fi

PUBLIC_BASE_URL="$PUBLIC" nohup .venv/bin/python -m launchlocal.server > /tmp/launchlocal-server.log 2>&1 &
echo "$! web-app" >> "$PIDS"
sleep 4

echo "web app:        http://127.0.0.1:8787/"
echo "workflow graph: http://localhost:8080/ui/"
[ -n "$PUBLIC" ] && echo "public URL:     $PUBLIC/"
curl -s -o /dev/null -w "web app status: %{http_code}\n" http://127.0.0.1:8787/
curl -s http://localhost:8080/api/v1/nodes | grep -q '"launchlocal"' && echo "agent node: registered" || echo "agent node: NOT registered yet, wait a few seconds"
