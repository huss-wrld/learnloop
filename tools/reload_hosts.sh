#!/usr/bin/env bash
# Reload learnloop's dashboard API (the cards' and panes' routes) in ONE profile by stopping that profile's
# plugin host; Hermes restarts it on next use. Default: the test profile.
#   tools/reload_hosts.sh [profile]      e.g. tools/reload_hosts.sh learnloop-test
# Never run this against the profile Desktop launched with (usually "default"): that host belongs to Desktop's
# own backend and is NOT restarted until Desktop is fully quit and reopened (10 Nov: Learn page 502 for hours).
set -euo pipefail
profile="${1:-learnloop-test}"
[ "$profile" = "default" ] && home="$HOME/.hermes" || home="$HOME/.hermes/profiles/$profile"
pids=""
for p in $(pgrep -f '[h]ermes_cli.plugin_host_child' || true); do
  if tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qx "HERMES_HOME=$home"; then pids="$pids $p"; fi
done
[ -z "$pids" ] && { echo "no plugin host running for $profile"; exit 0; }
if [ "$profile" = "default" ] && [ "${FORCE:-}" != 1 ]; then
  echo "refusing: the default profile's host only comes back after a full Desktop restart (FORCE=1 to override)"; exit 1
fi
kill $pids && echo "stopped $profile plugin host:$pids (Hermes restarts it on next use)"
