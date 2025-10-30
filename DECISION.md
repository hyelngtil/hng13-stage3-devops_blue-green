# Implementation Decisions

## Architecture Choice: Primary/Backup Pattern
**Decision:** I used Nginx's `backup` directive instead of round-robin load balancing.

**Rationale:**
- The task said "all traffic should go to Blue" in normal state
- `backup` makes sure Green only receives traffic when Blue fails
- It's more simple than writing custom health check scripts
- Native Nginx feature = more reliable

## Failover Configuration

### Timeout Values
```nginx
proxy_connect_timeout 1s;
proxy_read_timeout 4s;
max_fails=1 fail_timeout=2s;
```

**Rationale:**
- **1s connect timeout**: It detects network failures quickly
- **4s read timeout**: It allows the app to process but fails fast when it hangs
- **max_fails=1**: Single failure will trigger failover (aggressive but safe with backup)
- **fail_timeout=2s**: Short window to mark server as down
- **Total failover time**: Around 2-3 seconds (it meets the <10s requirement)

**Trade-off:** Aggressive timeouts may cause false positives under load, but the task wants fast failover over tolerance.

### Retry Strategy
```nginx
proxy_next_upstream error timeout http_500 http_502 http_503 http_504;
proxy_next_upstream_tries 2;
```

**Rationale:**
- It retries on errors AND specific 5xx codes (comprehensive coverage)
- Max 2 tries = one attempt to backup (prevents infinite loops)
- Client doesn't see errors