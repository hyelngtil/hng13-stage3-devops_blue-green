# Blue/Green Deployment Observability & Alerts (Log-Watcher + Slack) Runbook

## Overview
This runbook provides operational procedures for responding to alerts from the Blue/Green deployment monitoring system. The alert watcher monitors Nginx logs and sends Slack notifications when issues are detected.

---

## Alert Types & Response Procedures

### Alert: Failover Detected

**Example Message:**
```
🚨 Failover Detected: BLUE → GREEN at 2025-10-30 14:23:15
```

**What It Means:**
- The primary pool (Blue or Green) has failed health checks
- Nginx automatically switched traffic to the backup pool
- This is **automatic** and traffic is still flowing (zero downtime)

**Immediate Actions:**
1. **Verify traffic is flowing:**
   ```bash
   curl -i http://localhost:8080/version
   # Should return 200 OK with X-App-Pool matching backup pool
   ```

2. **Check failed pool logs:**
   ```bash
   # If Blue failed:
   docker logs app_blue --tail 50
   
   # If Green failed:
   docker logs app_green --tail 50
   ```

**Recovery Steps:**

**Option A: Restart Failed Container**
```bash
# Restart the failed app
docker restart app_blue  # or app_green

# Wait 5-10 seconds, then verify health
curl http://localhost:8081/healthz  # for Blue
curl http://localhost:8082/healthz  # for Green
```

**Option B: Manual Toggle Back (If Fixed)**
```bash
# Only after verifying the failed pool is healthy
./toggle_pool.sh

# Verify switch
curl -i http://localhost:8080/version
```

**When to Escalate:**
- Failover happens more than 3 times in 1 hour
- Both pools fail simultaneously
- Container restarts don't resolve the issue
- Logs show database or critical infrastructure issues

---

### Alert: High Error Rate

**Example Message:**
```
⚠️ High Error Rate: 5.2% (>2.0%) over last 200 requests. 11 errors detected.
```

**What It Means:**
- More than 2% of recent requests returned 5xx errors
- Both pools might be experiencing issues
- User experience is degraded

**Immediate Actions:**
1. **Check both pool logs immediately:**
   ```bash
   docker logs app_blue --tail 100 | grep -i error
   docker logs app_green --tail 100 | grep -i error
   ```

2. **Verify both pools are responding:**
   ```bash
   curl -i http://localhost:8081/healthz  # Blue
   curl -i http://localhost:8082/healthz  # Green
   curl -i http://localhost:8080/version  # Via Nginx
   ```

3. **Check Nginx logs for patterns:**
   ```bash
   docker exec nginx tail -50 /var/log/nginx/bluegreen_access.log
   # Look for: upstream_status=500, upstream_status=502, etc.
   ```

**Common Causes:**
- **Database issues**: Connection pool exhausted, slow queries
- **External API failures**: Downstream service is down
- **Resource exhaustion**: CPU/memory limits reached
- **Code bug**: Recent deployment introduced errors

**Recovery Steps:**

**Step 1: Identify Root Cause**
```bash
# Check resource usage
docker stats --no-stream

# Check for memory issues
docker inspect app_blue | grep -i memory
docker inspect app_green | grep -i memory
```

**Step 2: Immediate Mitigation**
```bash
# If one pool is worse, switch to the better one
./toggle_pool.sh

# Or restart both pools
docker restart app_blue app_green
```

**Step 3: Rollback if Needed**
```bash
# If recent deployment caused this, rollback
# Edit .env to previous image tags
BLUE_IMAGE=yimikaade/wonderful:previous-version
GREEN_IMAGE=yimikaade/wonderful:previous-version

# Restart stack
docker compose down
./start.sh
```

**When to Escalate:**
- Error rate exceeds 10%
- Both pools show critical errors
- Database or external dependencies are confirmed down
- Restarts and rollbacks don't resolve issue

---

###2 Alert: Recovery

**Example Message:**
```
✅ Recovery: Error rate back to 0% over last 200 requests
```

**What It Means:**
- System has recovered from previous error state
- All recent requests are successful
- No immediate action needed

### Manual Failover for Testing

```bash
# Trigger chaos on active pool
curl -X POST "http://localhost:8081/chaos/start?mode=error"  # if Blue is active

# Watch logs for failover
docker logs -f alert_watcher

# Expect to see: "🚨 Failover Detected: BLUE → GREEN"

# Stop chaos
curl -X POST "http://localhost:8081/chaos/stop"
```

## Alert Thresholds & Tuning

Current configuration (in `.env`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ERROR_RATE_THRESHOLD` | 2.0 | Error rate % that triggers alert |
| `WINDOW_SIZE` | 200 | Requests to track in sliding window |
| `ALERT_COOLDOWN_SEC` | 300 | Seconds between similar alerts |

**When to Adjust:**
- **Too many false positives**: Increase `ERROR_RATE_THRESHOLD` to 3-5%
- **Missing real issues**: Decrease `ERROR_RATE_THRESHOLD` to 1%
- **Alert spam**: Increase `ALERT_COOLDOWN_SEC` to 600 (10 min)
- **Need faster detection**: Decrease `WINDOW_SIZE` to 100

## Troubleshooting

### No Slack Alerts Received

**Check webhook configuration:**
```bash
# Verify webhook URL is set
docker exec alert_watcher env | grep SLACK_WEBHOOK_URL

# Test webhook manually
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test alert from runbook"}'
```

**Check watcher logs:**
```bash
docker logs alert_watcher | grep -i slack
# Look for: "Alert sent" or "Slack webhook failed"
```

### Watcher Not Detecting Failovers

**Verify log file exists:**
```bash
docker exec alert_watcher ls -la /var/log/nginx/
docker exec nginx ls -la /var/log/nginx/bluegreen_access.log
```

**Check log format:**
```bash
docker exec nginx tail -5 /var/log/nginx/bluegreen_access.log
# Should show: pool=blue release=... status=200
```

**Restart watcher:**
```bash
docker restart alert_watcher
docker logs -f alert_watcher
```
---

### How Failover Works
1. Nginx sends request to primary pool (e.g., Blue)
2. If Blue returns 5xx or times out, Nginx marks it as failed
3. After `max_fails=1` failure, Blue is marked down for `fail_timeout=2s`
4. Nginx immediately retries request to backup pool (Green)
5. Client receives response from Green (transparent failover)