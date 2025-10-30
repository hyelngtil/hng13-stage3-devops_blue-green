#!/usr/bin/env python3
"""
Nginx Log Watcher for Blue/Green Deployment
Monitors access logs for failovers and error rate spikes
Sends alerts to Slack when thresholds are breached
"""

import os
import re
import time
import requests
from collections import deque
from datetime import datetime

# Configuration from environment variables
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', '2.0'))  # percentage
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '200'))  # requests
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))  # 5 minutes
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
LOG_FILE = '/var/log/nginx/bluegreen_access.log'

# State tracking
last_pool = None
request_window = deque(maxlen=WINDOW_SIZE)
last_alert_time = {
    'failover': 0,
    'error_rate': 0,
    'recovery': 0
}

def send_slack_alert(message, alert_type='info'):
    """Send alert to Slack webhook"""
    if not SLACK_WEBHOOK_URL:
        print(f"[WARN] No Slack webhook configured. Alert: {message}")
        return
    
    if MAINTENANCE_MODE and alert_type == 'failover':
        print(f"[INFO] Maintenance mode - suppressing failover alert: {message}")
        return
    
    # Check cooldown
    now = time.time()
    if now - last_alert_time.get(alert_type, 0) < ALERT_COOLDOWN_SEC:
        print(f"[COOLDOWN] Skipping {alert_type} alert (cooldown active)")
        return
    
    # Emoji mapping
    emoji_map = {
        'failover': '🚨',
        'error_rate': '⚠️',
        'recovery': '✅',
        'info': 'ℹ️'
    }
    
    emoji = emoji_map.get(alert_type, 'ℹ️')
    payload = {
        "text": f"{emoji} {message}",
        "username": "BlueGreen Monitor",
        "icon_emoji": ":chart_with_upwards_trend:"
    }
    
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=5
        )
        if response.status_code == 200:
            print(f"[SLACK] Alert sent: {message}")
            last_alert_time[alert_type] = now
        else:
            print(f"[ERROR] Slack webhook failed: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to send Slack alert: {e}")

def parse_log_line(line):
    """Parse Nginx log line and extract relevant fields"""
   
    data = {}
    
    # Extract timestamp
    timestamp_match = re.search(r'\[(.*?)\]', line)
    if timestamp_match:
        data['timestamp'] = timestamp_match.group(1)
    
    # Extract key-value pairs
    patterns = {
        'pool': r'pool=(\S+)',
        'release': r'release=(\S+)',
        'status': r'status=(\d+)',
        'upstream_status': r'upstream_status=(\S+)',
        'upstream_addr': r'upstream_addr=(\S+)',
        'request_time': r'request_time=(\S+)',
        'method': r'method=(\S+)',
        'uri': r'uri=(\S+)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, line)
        if match:
            data[key] = match.group(1)
    
    return data

def check_failover(current_pool):
    """Detect pool changes (failover events)"""
    global last_pool
    
    if last_pool is None:
        last_pool = current_pool
        print(f"[INIT] Initial pool detected: {current_pool}")
        return
    
    if current_pool != last_pool and current_pool in ['blue', 'green']:
        message = f"Failover Detected: {last_pool.upper()} → {current_pool.upper()} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        print(f"[FAILOVER] {message}")
        send_slack_alert(message, alert_type='failover')
        last_pool = current_pool

def check_error_rate():
    """Calculate error rate over sliding window"""
    if len(request_window) < 50:  # Wait for enough samples
        return
    
    error_count = sum(1 for status in request_window if status >= 500)
    total_count = len(request_window)
    error_rate = (error_count / total_count) * 100
    
    if error_rate > ERROR_RATE_THRESHOLD:
        message = f"High Error Rate: {error_rate:.1f}% (>{ERROR_RATE_THRESHOLD}%) over last {total_count} requests. {error_count} errors detected."
        print(f"[ERROR_RATE] {message}")
        send_slack_alert(message, alert_type='error_rate')
    elif error_rate == 0 and len(request_window) == WINDOW_SIZE:
        # Check if we were previously in error state
        if time.time() - last_alert_time.get('error_rate', 0) < ALERT_COOLDOWN_SEC * 2:
            message = f"Recovery: Error rate back to 0% over last {total_count} requests"
            print(f"[RECOVERY] {message}")
            send_slack_alert(message, alert_type='recovery')

def tail_file(filename):
    """Tail a file like 'tail -f'"""
    try:
        with open(filename, 'r') as f:
            # Go to end of file
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                yield line
    except Exception as e:
        print(f"[ERROR] Failed to tail file: {e}")
        raise

def main():
    print(f"[START] BlueGreen Log Watcher starting...")
    print(f"[CONFIG] Error threshold: {ERROR_RATE_THRESHOLD}%")
    print(f"[CONFIG] Window size: {WINDOW_SIZE} requests")
    print(f"[CONFIG] Alert cooldown: {ALERT_COOLDOWN_SEC}s")
    print(f"[CONFIG] Maintenance mode: {MAINTENANCE_MODE}")
    print(f"[CONFIG] Slack webhook: {'Configured' if SLACK_WEBHOOK_URL else 'NOT CONFIGURED'}")
    print(f"[INFO] Monitoring: {LOG_FILE}")
    
    # Wait for log file to exist
    retries = 0
    max_retries = 30
    while not os.path.exists(LOG_FILE):
        retries += 1
        if retries > max_retries:
            print(f"[ERROR] Log file not created after {max_retries} seconds. Check Nginx container.")
            print(f"[INFO] Continuing anyway - will start monitoring once file appears...")
            break
        print(f"[WAIT] Waiting for log file to be created... ({retries}/{max_retries})")
        time.sleep(1)
    
    if os.path.exists(LOG_FILE):
        print(f"[INFO] Log file found, starting monitoring...")
    
    # Send startup notification
    send_slack_alert(
        f"BlueGreen Monitor started. Watching for failovers and error rates >{ERROR_RATE_THRESHOLD}%",
        alert_type='info'
    )
    
    try:
        # Keep trying to tail the file even if it doesn't exist yet
        while True:
            try:
                if not os.path.exists(LOG_FILE):
                    print(f"[WAIT] Log file not found, waiting...")
                    time.sleep(2)
                    continue
                    
                for line in tail_file(LOG_FILE):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse log line
                    data = parse_log_line(line)
                    
                    if not data:
                        continue
                    
                    # Track pool for failover detection
                    pool = data.get('pool', '')
                    if pool in ['blue', 'green']:
                        check_failover(pool)
                    
                    # Track status for error rate
                    try:
                        status = int(data.get('status', '0'))
                        if status > 0:
                            request_window.append(status)
                            check_error_rate()
                    except ValueError:
                        pass
                    
                    # Debug output every 50 requests
                    if len(request_window) % 50 == 0 and len(request_window) > 0:
                        error_count = sum(1 for s in request_window if s >= 500)
                        error_rate = (error_count / len(request_window)) * 100
                        print(f"[STATS] Processed {len(request_window)} requests, "
                              f"current pool: {pool}, error rate: {error_rate:.1f}%")
            except FileNotFoundError:
                print(f"[WARN] Log file disappeared, waiting for it to reappear...")
                time.sleep(2)
            except Exception as e:
                print(f"[ERROR] Error in monitoring loop: {e}")
                time.sleep(5)
    
    except KeyboardInterrupt:
        print("\n[STOP] Watcher stopped by user")
    except Exception as e:
        print(f"[ERROR] Watcher crashed: {e}")
        import traceback
        traceback.print_exc()
        send_slack_alert(f"Watcher crashed: {e}", alert_type='error_rate')

if __name__ == '__main__':
    main()