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
# 1. Set webhook URL (required)
export WEBHOOK_URL=your_webhook_url_here

# 2. Place cookies.txt file in parent directory (Netscape format)
# The start.sh script will automatically parse it

# 3. Start all services
cd zhihu-monitor-docker
./start.sh
```

**Note**: The `start.sh` script automatically parses `../cookies.txt` (Netscape format) and sets `ZHIHU_COOKIES`. You can also set `COOKIE_FILE` to specify a different path:

```bash
COOKIE_FILE=/path/to/cookies.txt ./start.sh
```

To make environment variables persistent, add them to your shell configuration file:

```bash
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
docker exec zhihu-monitor python -u /app/main.py

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
   - `ofelia.job-exec.monitor.schedule = 0 */10 * * *`
   - `ofelia.job-exec.monitor.command = python -u /app/main.py`

6. **Test manual execution:**
   ```bash
   docker exec zhihu-monitor python -u /app/main.py
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
├── Dockerfile          # Monitor container image
├── main.py             # Entry point (scheduled by Ofelia)
├── start.sh            # Startup script with cookie parsing
├── src/                # Source modules
│   ├── monitor.py      # Core monitoring logic
│   ├── config.py       # Configuration loading
│   ├── models.py       # Data models
│   ├── rss_client.py   # RSS fetching
│   ├── webhook_client.py # Webhook notifications
│   ├── cookie_manager.py # Cookie parsing (also CLI: python -m src.cookie_manager)
│   └── ...
├── requirements.txt    # Python dependencies
├── environment.yml     # Conda environment (for local development)
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
