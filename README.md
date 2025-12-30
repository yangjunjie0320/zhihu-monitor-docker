# Zhihu Monitor Docker Version (Ofelia Scheduler)

Use Ofelia (Docker-specific scheduled task runner) to trigger the monitoring script on schedule, which is more reliable than Python sleep.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                     Docker                           │
├──────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌───────────────┐    ┌───────────┐  │
│  │ Ofelia  │───▶│ zhihu-monitor │───▶│  RSSHub   │  │
│  │ Scheduler│   │  Monitor Script│   │ RSS Service│  │
│  └─────────┘    └───────────────┘    └───────────┘  │
│   Triggers every 15min      │                        │
│                        ▼                            │
│                   ┌─────────┐                       │
│                   │ Webhook │ ──────────▶ Notification│
│                   └─────────┘                       │
└──────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Set environment variables (required)
export ZHIHU_COOKIES=your_zhihu_cookies_here
export WEBHOOK_URL=your_webhook_url_here

# Optional: Set user configuration
export ZHIHU_USER_ID=shui-qian-xiao-xi
export ZHIHU_USER_NAME=马前卒official

# 2. Start all services
cd zhihu-monitor-docker
docker compose up -d --build
```

**Note**: To make environment variables persistent, add them to your shell configuration file (e.g., `~/.bashrc` or `~/.zshrc`):

```bash
echo 'export ZHIHU_COOKIES=your_cookies' >> ~/.bashrc
echo 'export WEBHOOK_URL=your_webhook_url' >> ~/.bashrc
source ~/.bashrc
```

## Common Commands

```bash
# View all container status
docker compose ps

# View logs from all services
docker compose logs -f

# View scheduler logs
docker logs -f ofelia

# View monitor container logs
docker logs -f zhihu-monitor

# Manually trigger monitoring once
docker exec zhihu-monitor python -u /app/monitor.py

# Restart all services
docker compose restart

# Stop all services
docker compose down

# Check scheduler status and diagnose issues
./check_scheduler.sh
```

## Troubleshooting Scheduler Issues

If the scheduled tasks are not running:

1. **Check if containers are running:**
   ```bash
   docker compose ps
   ```
   All three containers (rsshub, zhihu-monitor, ofelia) should be running.

2. **Check Ofelia scheduler logs:**
   ```bash
   docker logs -f ofelia
   ```
   You should see logs like:
   - `job-exec.monitor` registered
   - Execution logs every 15 minutes

3. **Check monitor container logs:**
   ```bash
   docker logs -f zhihu-monitor
   ```
   You should see execution logs with timestamps every 15 minutes.

4. **Run diagnostic script:**
   ```bash
   ./check_scheduler.sh
   ```
   This will check container status, logs, and configuration.

5. **Verify Ofelia can see the job:**
   ```bash
   docker inspect zhihu-monitor --format '{{range $k, $v := .Config.Labels}}{{printf "%s = %s\n" $k $v}}{{end}}' | grep ofelia
   ```
   Should show:
   - `ofelia.enabled = true`
   - `ofelia.job-exec.monitor.schedule = @every 15m`
   - `ofelia.job-exec.monitor.command = python -u /app/monitor.py`

6. **Test manual execution:**
   ```bash
   docker exec zhihu-monitor python -u /app/monitor.py
   ```
   If this works but scheduled tasks don't, the issue is with Ofelia configuration.

7. **Restart services if needed:**
   ```bash
   docker compose restart
   ```

8. **Check if Ofelia has access to Docker socket:**
   ```bash
   docker exec ofelia ls -la /var/run/docker.sock
   ```
   Should show the socket file exists.

## Modify Check Interval

Edit `docker-compose.yml`, modify this line:

```yaml
ofelia.job-exec.monitor.schedule: "@every 15m"
```

Supported formats:
- `@every 10m` - Every 10 minutes
- `@every 1h` - Every hour
- `@hourly` - Every hour
- `0 */30 * * * *` - Every 30 minutes (cron format)

After modification, restart:
```bash
docker compose restart
```

## File Structure

```
zhihu-monitor-docker/
├── docker-compose.yml  # Service orchestration
├── Dockerfile          # Monitor script image
├── monitor.py          # Monitor script
├── requirements.txt    # Python dependencies
├── environment.yml     # Conda environment (for local development)
├── .gitignore          # Git ignore rules
└── data/               # State file directory (gitignored)
    └── state.json      # Record of pushed content
```

## Environment Variables

Required environment variables:
- `ZHIHU_COOKIES` - Zhihu cookies (optional, but recommended for better rate limits)
- `WEBHOOK_URL` - Webhook URL for notifications

Optional environment variables:
- `ZHIHU_USER_ID` - Default: `shui-qian-xiao-xi`
- `ZHIHU_USER_NAME` - Default: `马前卒official`
- `RSSHUB_BASE` - Default: `http://rsshub:1200`

## Security Notes

- Environment variables are used to keep sensitive information secure
- Never commit sensitive information (cookies, webhook URLs) to version control
- Always keep your `ZHIHU_COOKIES` and `WEBHOOK_URL` secure and never share them publicly
- Consider using a secrets management system for production deployments
