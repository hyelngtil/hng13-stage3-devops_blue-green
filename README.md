# Blue/Green Deployment with Observability & Alerts (Stage 3)

A production-ready Blue/Green deployment system using Nginx upstream load balancing with automatic failover, real-time monitoring, and Slack alerting capabilities.

## Architecture Overview

```
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Nginx    │ :8080 (Public)
                    │  (Primary/  │
                    │   Backup)   │
                    └──┬───────┬──┘
                       │       │
          ┌────────────┘       └────────────┐
          │                                  │
    ┌─────▼─────┐                     ┌─────▼─────┐
    │ App Blue  │ :8081               │ App Green │ :8082
    │ (Primary) │                     │  (Backup) │
    └───────────┘                     └───────────┘
          │                                  │
          └──────────┬───────────────────────┘
                     │
              ┌──────▼──────┐
              │ Log Watcher │ (Python)
              │   + Slack   │
              │   Alerts    │
              └─────────────┘
```

**Key Features:**
- **Automatic Failover**: Nginx detects failures and switches to backup within 2-3 seconds
- **Zero Failed Requests**: Retry mechanism ensures clients always receive 200 OK
- **Real-Time Monitoring**: Python watcher tails Nginx logs for failover detection
- **Slack Alerts**: Instant notifications for failovers and error rate spikes
- **Manual Toggle**: Switch active pool on-demand for deployments
- **Operational Runbook**: Clear procedures for incident response

## Prerequisites
- **Docker** >= 20.10.0
- **Docker Compose** (plugin version)
- **Bash** shell
- **curl** (for testing)
- **envsubst** (usually included with gettext-base)
- **Slack Incoming Webhook URL** (for alerts)

## Quick Start (Local Testing)

### 1. Initial Setup
```bash
# Clone the repository
git clone <your-repo-url>
cd <repo-directory>

# Copy and configure environment
cp .env.example .env

# IMPORTANT: Configure Slack webhook in .env
# Get your webhook from: https://api.slack.com/messaging/webhooks
vim .env  # Set SLACK_WEBHOOK_URL

# Make scripts executable
chmod +x start.sh verify.sh toggle_pool.sh
```

### 2. Start the Stack
```bash
./start.sh
```
**Expected Output:**
```
Rendered nginx/default.conf with PRIMARY=app_blue, SECONDARY=app_green, PORT=8080
Starting docker compose...
[+] Running 4/4
 ✔ Container app_blue      Started
 ✔ Container app_green     Started  
 ✔ Container nginx         Started
 ✔ Container alert_watcher Started
Waiting 1s for nginx to start...
Done. Nginx on http://localhost:8080
```

### 3. Verify Baseline (Blue Active)
```bash
curl -i http://localhost:8080/version
```
**Expected Response:**
```http
HTTP/1.1 200 OK
Server: nginx/1.24.0
X-App-Pool: blue
X-Release-Id: release-blue-001
Content-Type: application/json

{"version":"1.0.0","pool":"blue","release":"release-blue-001"}
```

### 4. Test Automatic Failover with Slack Alerts
**Step A: Watch Watcher Logs**
```bash
# In a separate terminal, follow the watcher
docker logs -f alert_watcher
```

**Step B: Trigger Chaos on Blue**
```bash
curl -X POST "http://localhost:8081/chaos/start?mode=error"
```

**Step C: Run Verification Script**
```bash
./verify.sh
```
**Expected Behavior:**
- First 1-2 requests show Blue (200 OK)
- Nginx detects Blue failures (500 errors)
- **Watcher detects failover and sends Slack alert** 🚨
- Automatically switches to Green within 2-3 seconds
- All subsequent requests show Green (200 OK)
- **Zero 5xx errors to clients** (Nginx retries to backup)

**Expected Slack Alert:**
```
🚨 Failover Detected: BLUE → GREEN at 2025-10-30 14:23:15
```

**Step D: Stop Chaos**
```bash
curl -X POST "http://localhost:8081/chaos/stop"
```

### 5. View Logs and Monitoring
**Check Nginx Logs (Structured Format):**
```bash
docker exec nginx tail -20 /var/log/nginx/bluegreen_access.log
```
**Sample Log Line:**
```
[2025-10-30T14:23:15+00:00] pool=green release=release-green-001 status=200 upstream_status=200 upstream_addr=172.18.0.3:8080 request_time=0.012 upstream_response_time=0.010 method=GET uri=/version client=172.18.0.1
```

**Check Watcher Output:**
```bash
docker logs alert_watcher --tail 50
```

## Configuration Files

### Environment Variables (.env)
```bash
# Core Configuration
ACTIVE_POOL=blue                # Initial active pool (blue/green)
BLUE_IMAGE=yimikaade/wonderful:devops-stage-two
GREEN_IMAGE=yimikaade/wonderful:devops-stage-two

# Observability Configuration (Stage 3)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
ERROR_RATE_THRESHOLD=2.0        # Alert when error rate exceeds this %
WINDOW_SIZE=200                 # Track last N requests
ALERT_COOLDOWN_SEC=300          # Seconds between similar alerts
MAINTENANCE_MODE=false          # Set true to suppress failover alerts
```

### Nginx Configuration (nginx/nginx.conf.template)
Key directives:
- **Custom log format**: Captures pool, release, upstream status
- **Upstream health checks**: `max_fails=1 fail_timeout=2s`
- **Retry logic**: `proxy_next_upstream error timeout http_500 ...`
- **Fast timeouts**: `proxy_read_timeout 4s`

### Python Watcher (watcher.py)
Features:
- **Log tailing**: Monitors Nginx logs in real-time
- **Sliding window**: Tracks last N requests for error rate calculation
- **Failover detection**: Compares current pool vs previous pool
- **Alert deduplication**: Cooldown prevents spam
- **Maintenance mode**: Suppress alerts during planned work

## Testing & Verification

### Available Endpoints
**Via Nginx (Public):**
- `GET http://localhost:8080/version` - Version info with routing headers
- `GET http://localhost:8080/healthz` - Health check endpoint

**Direct Access (For Chaos Testing):**
- `GET http://localhost:8081/version` - Blue app direct
- `POST http://localhost:8081/chaos/start?mode=error` - Trigger 500 errors
- `POST http://localhost:8081/chaos/start?mode=timeout` - Trigger timeouts
- `POST http://localhost:8081/chaos/stop` - Stop chaos
- `GET http://localhost:8082/version` - Green app direct

### Chaos Testing Scenarios

**1. Failover Detection Test**
```bash
# Start monitoring
docker logs -f alert_watcher &

# Trigger chaos
curl -X POST "http://localhost:8081/chaos/start?mode=error"

# Generate traffic
for i in {1..20}; do curl -s http://localhost:8080/version | jq -r '.pool'; sleep 0.3; done

# Expected: Slack alert "Failover Detected: BLUE → GREEN"
# Stop chaos
curl -X POST "http://localhost:8081/chaos/stop"
```

**2. High Error Rate Test**
```bash
# Trigger chaos on BOTH pools (simulates backend issues)
curl -X POST "http://localhost:8081/chaos/start?mode=error"
curl -X POST "http://localhost:8082/chaos/start?mode=error"

# Generate traffic
for i in {1..50}; do curl -s http://localhost:8080/version; sleep 0.1; done

# Expected: Slack alert "High Error Rate: X% (>2.0%)"
# Stop chaos
curl -X POST "http://localhost:8081/chaos/stop"
curl -X POST "http://localhost:8082/chaos/stop"
```

**3. Recovery Test**
```bash
# After error rate alert, stop chaos and wait
# Expected: Slack alert "Recovery: Error rate back to 0%"
```

### Validation Checklist (Stage 3)
- [ ] All containers running: `docker compose ps`
- [ ] Blue responds: `curl http://localhost:8081/version` → 200 OK
- [ ] Green responds: `curl http://localhost:8082/version` → 200 OK
- [ ] Nginx routes correctly: `curl http://localhost:8080/version` → 200 OK
- [ ] Headers preserved: `X-App-Pool` and `X-Release-Id` present
- [ ] **Nginx logs show structured format** with pool, release, status
- [ ] **Watcher container running**: `docker compose ps alert_watcher`
- [ ] **Failover triggers Slack alert** within 5 seconds
- [ ] **Error rate alert fires** when threshold exceeded
- [ ] **Alert cooldown working** (no spam)
- [ ] Manual toggle switches pool successfully
- [ ] CI pipeline passes all checks

## Success Metrics
### Failover Performance
- **Detection Time**: < 2 seconds
- **Switch Time**: < 1 second (first retry)
- **Total Failover**: < 3 seconds
- **Failed Requests**: 0 (100% success rate)
- **Alert Delivery**: < 5 seconds to Slack

### Observability Metrics
- **Log Latency**: Real-time (< 100ms)
- **Alert Accuracy**: Zero false negatives
- **False Positive Rate**: < 1% (with proper thresholds)

## Monitoring & Debugging

### Container Status
```bash
# Check all containers
docker compose ps

# View logs
docker compose logs -f
docker compose logs nginx
docker compose logs app_blue
docker compose logs app_green
docker compose logs alert_watcher

# View Nginx access logs with structured format
docker exec nginx tail -f /var/log/nginx/bluegreen_access.log

# Check watcher statistics
docker logs alert_watcher | grep STATS
```

### Debugging Alerts

**No Slack alerts received:**
```bash
# Check watcher logs
docker logs alert_watcher | grep -i slack

# Verify webhook URL
docker exec alert_watcher env | grep SLACK_WEBHOOK_URL

# Test webhook manually
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test alert"}'
```

**Watcher not detecting failovers:**
```bash
# Check log file exists
docker exec alert_watcher ls -la /var/log/nginx/

# Verify log format
docker exec nginx tail -5 /var/log/nginx/bluegreen_access.log

# Restart watcher
docker restart alert_watcher
```

## Operational Procedures

See [runbook.md](./runbook.md) for detailed procedures:
- Responding to failover alerts
- Handling high error rate alerts
- Planned maintenance workflows
- Troubleshooting guide
- Escalation procedures

**Quick Reference:**
- **Failover Alert**: Check failed pool logs, restart container if needed
- **Error Rate Alert**: Check both pools, look for resource/backend issues
- **Planned Deployment**: Enable `MAINTENANCE_MODE=true` before toggling

## CI/CD Pipeline
### GitHub Actions Workflow
The `.github/workflows/ci.yml` automatically:
1. ✅ Starts the full stack (including watcher)
2. ✅ Verifies baseline (Blue active)
3. ✅ Triggers chaos on Blue
4. ✅ Validates automatic failover
5. ✅ Ensures zero 5xx errors
6. ✅ Confirms Green takes over
7. ✅ Verifies logs show structured format
8. ✅ Stops chaos and cleans up

**Trigger Events:**
- Push to any branch
- Pull requests

**Success Criteria:**
- All 20 requests return HTTP 200
- Headers switch from Blue to Green after chaos
- No failed requests during failover
- Watcher container stays healthy

## Project Structure
```bash
.
├── .env.example              # Environment template (with Stage 3 vars)
├── .gitignore               # Git ignore rules
├── docker-compose.yml       # Container orchestration (4 services)
├── README.md                # This file
├── runbook.md               # Operational procedures (NEW)
├── start.sh                 # Start stack with config rendering
├── toggle_pool.sh           # Manual pool switching
├── verify.sh                # Automated failover testing
├── watcher.py               # Log monitoring script (NEW)
├── requirements.txt         # Python dependencies (NEW)
├── nginx/
│   └── nginx.conf.template  # Nginx config with custom logging
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions CI pipeline
```

## Failure Scenarios Handled
| Scenario | Detection | Recovery | Downtime | Alert Sent |
| :-------- | :---------: | :--------: | --------: | ---------: |
| App crashes | Health check fails | Switch to backup | < 3s | ✅ Failover |
| App hangs | Read timeout | Retry to backup | < 5s | ✅ Failover |
| App returns 500 | HTTP status check | Retry to backup | < 1s | ✅ Failover |
| Network partition | Connection timeout | Switch to backup | < 2s | ✅ Failover |
| Planned maintenance | Manual toggle | Graceful switch | 0s | ❌ (Maintenance mode) |
| High backend errors | Error rate tracking | Alert operator | N/A | ✅ Error rate |

## Screenshots (For Submission)

Ensure you capture the following for your Stage 3 submission:

### Required Screenshots:
1. **Slack Failover Alert**
   - Shows: "🚨 Failover Detected: BLUE → GREEN" message
   - Include: Timestamp, alert details

2. **Slack Error Rate Alert**
   - Shows: "⚠️ High Error Rate: X% (>2.0%)" message
   - Include: Error count, threshold

3. **Nginx Structured Logs**
   - Command: `docker exec nginx tail -20 /var/log/nginx/bluegreen_access.log`
   - Shows: `pool=`, `release=`, `status=`, `upstream_status=` fields

4. **Watcher Logs**
   - Command: `docker logs alert_watcher --tail 50`
   - Shows: Failover detection, stats output

5. **Container Status**
   - Command: `docker compose ps`
   - Shows: All 4 containers running (nginx, app_blue, app_green, alert_watcher)

### How to Capture:
```bash
# Generate failover event
curl -X POST "http://localhost:8081/chaos/start?mode=error"
for i in {1..20}; do curl -s http://localhost:8080/version | jq -r '.pool'; sleep 0.3; done

# Wait for Slack alerts (check your Slack channel)
# Screenshot 1: Failover alert in Slack

# Screenshot 2: Nginx logs
docker exec nginx tail -20 /var/log/nginx/bluegreen_access.log

# Screenshot 3: Watcher logs
docker logs alert_watcher --tail 50

# Generate error rate alert
curl -X POST "http://localhost:8081/chaos/start?mode=error"
curl -X POST "http://localhost:8082/chaos/start?mode=error"
for i in {1..50}; do curl -s http://localhost:8080/version; sleep 0.1; done

# Screenshot 4: Error rate alert in Slack

# Screenshot 5: Container status
docker compose ps
```

## Cleanup
```bash
# Stop all containers
docker compose down

# Remove volumes and networks
docker compose down -v

# Remove generated configs
rm -f nginx/default.conf

# Full cleanup (removes images)
docker compose down -v --rmi all
```

## Troubleshooting

### Common Issues

**Issue: Watcher crashes on startup**
```bash
# Check logs
docker logs alert_watcher

# Common cause: Missing requirements.txt
# Solution: Ensure requirements.txt exists with "requests==2.31.0"

# Restart watcher
docker restart alert_watcher
```

**Issue: No Slack alerts**
```bash
# Verify webhook URL is set
grep SLACK_WEBHOOK_URL .env

# Test webhook manually
curl -X POST YOUR_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test from troubleshooting"}'

# Check watcher sees the webhook
docker exec alert_watcher env | grep SLACK
```

**Issue: Logs not appearing**
```bash
# Check volume mount
docker inspect nginx | grep -A 5 Mounts

# Verify log file exists
docker exec nginx ls -la /var/log/nginx/

# Check Nginx config has log directive
docker exec nginx grep -i "access_log" /etc/nginx/conf.d/default.conf
```

## Resources & References
- [Nginx Upstream Documentation](http://nginx.org/en/docs/http/ngx_http_upstream_module.html)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [Docker Compose Volumes](https://docs.docker.com/compose/compose-file/05-services/#volumes)
- [Blue/Green Deployment Strategy](https://martinfowler.com/bliki/BlueGreenDeployment.html)

## ✅ Stage 3 Validation Results
Expected output when all checks pass:
```
✓ Containers started successfully (4/4 running)
✓ Baseline check: Blue active (200 OK)
✓ Nginx logs show structured format
✓ Watcher container healthy
✓ Chaos triggered on Blue
✓ 20/20 requests successful (100% pass rate)
✓ Failover detected: Green became active
✓ Slack alert sent: Failover notification
✓ Headers preserved correctly
✓ Zero failed requests during chaos
✓ Error rate alert triggered (if applicable)
✓ All tests passed!
```

---

**Stage 2 Complete**: Auto-failover + Manual toggle  
**Stage 3 Complete**: Observability + Slack alerts + Operational runbook

Ready for production! 🚀