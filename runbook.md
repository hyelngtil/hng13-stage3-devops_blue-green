# Blue/Green Deployment Runbook

## Overview
This runbook provides operational procedures for responding to alerts from the Blue/Green deployment monitoring system. The alert watcher monitors Nginx logs and sends Slack notifications when issues are detected.

---

## Alert Types & Response Procedures

### 🚨 Alert: Failover Detected

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

3. **Look for common issues:**
   - Out of memory errors
   - Unhandled exceptions
   - Database connection failures
   - External service timeouts

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

### ⚠️ Alert: High Error Rate

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

### ✅ Alert: Recovery

**Example Message:**
```
✅ Recovery: Error rate back to 0% over last 200 requests
```

**What It Means:**
- System has recovered from previous error state
- All recent requests are successful
- No immediate action needed

**Follow-up Actions:**
1. **Document the incident:**
   - What triggered the alert
   - What actions were taken
   - Root cause if identified

2. **Review logs for patterns:**
   ```bash
   docker logs app_blue --since 1h > /tmp/blue_incident.log
   docker logs app_green --since 1h > /tmp/green_incident.log
   ```

3. **Update monitoring if needed:**
   - Adjust thresholds if false positive
   - Add additional health checks

---

## Planned Maintenance Procedures

### Deploying New Versions (Zero Downtime)

**Step 1: Enable Maintenance Mode**
```bash
# Edit .env
MAINTENANCE_MODE=true

# Restart watcher to apply
docker restart alert_watcher
```
This suppresses failover alerts during planned toggles.

**Step 2: Update One Pool**
```bash
# Ensure Blue is active, update Green
# Edit .env:
GREEN_IMAGE=yimikaade/wonderful:new-version

# Restart Green only
docker compose up -d --no-deps app_green

# Wait for Green to be healthy
curl http://localhost:8082/healthz
```

**Step 3: Switch Traffic to Updated Pool**
```bash
./toggle_pool.sh

# Verify new version is serving
curl -i http://localhost:8080/version
# Should show X-Release-Id for new version
```

**Step 4: Update Second Pool**
```bash
# Now update Blue (no longer serving traffic)
# Edit .env:
BLUE_IMAGE=yimikaade/wonderful:new-version

# Restart Blue
docker compose up -d --no-deps app_blue

# Verify both pools match
curl http://localhost:8081/version
curl http://localhost:8082/version
```

**Step 5: Disable Maintenance Mode**
```bash
# Edit .env
MAINTENANCE_MODE=false

# Restart watcher
docker restart alert_watcher
```

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

---

## Monitoring Commands Cheat Sheet

```bash
# View all container status
docker compose ps

# Follow watcher logs live
docker logs -f alert_watcher

# Check current active pool
curl -s http://localhost:8080/version | jq '.pool'

# View Nginx access logs
docker exec nginx tail -f /var/log/nginx/bluegreen_access.log

# Check error rate manually
docker exec nginx tail -200 /var/log/nginx/bluegreen_access.log | grep -c "status=5"

# Restart everything
docker compose restart

# Full cleanup and restart
docker compose down -v
./start.sh
```

---

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

**To apply changes:**
```bash
# Edit .env with new values
vim .env

# Restart watcher
docker restart alert_watcher
```

---

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

### Both Pools Down

**This is a critical failure. Immediate steps:**

1. **Check container status:**
   ```bash
   docker compose ps
   # All should be "Up"
   ```

2. **Check resource limits:**
   ```bash
   docker stats --no-stream
   # Look for memory/CPU exhaustion
   ```

3. **Restart entire stack:**
   ```bash
   docker compose restart
   ```

4. **If still failing, rebuild:**
   ```bash
   docker compose down -v
   docker compose pull
   ./start.sh
   ```

5. **Escalate immediately** - this means total service outage

---

## Contact & Escalation

- **DevOps Team**: [Your Slack channel / PagerDuty]
- **Database Team**: [Contact info]
- **Platform Team**: [Contact info]

**Severity Levels:**
- **SEV1 (Critical)**: Both pools down, >10% error rate
- **SEV2 (High)**: Single pool down, 5-10% error rate
- **SEV3 (Medium)**: Repeated failovers, 2-5% error rate
- **SEV4 (Low)**: Single failover, <2% error rate

---

## Appendix: Understanding the System

### How Failover Works
1. Nginx sends request to primary pool (e.g., Blue)
2. If Blue returns 5xx or times out, Nginx marks it as failed
3. After `max_fails=1` failure, Blue is marked down for `fail_timeout=2s`
4. Nginx immediately retries request to backup pool (Green)
5. Client receives response from Green (transparent failover)

### Log Format Fields
- `pool`: Which app pool served the request (blue/green)
- `release`: Release identifier from app
- `status`: HTTP status returned to client
- `upstream_status`: Actual status from upstream app
- `upstream_addr`: IP:port of upstream that handled request
- `request_time`: Total request time (including retries)
- `upstream_response_time`: Time spent in upstream app

### Alert Cooldown Logic
Prevents alert spam. Example:
- Failover detected at 14:00:00
- Alert sent to Slack
- Another failover at 14:02:00
- Alert suppressed (cooldown = 300s = 5 min)
- Next failover at 14:06:00
- Alert sent again