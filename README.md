# Zhihu Monitor

监控知乎用户动态（回答、想法），通过 webhook 发送通知。

## 快速开始

```bash
# 设置 webhook URL（必需）
export WEBHOOK_URL=your_webhook_url

# 放置 cookies.txt 到上级目录（Netscape 格式），然后启动
./start.sh
```

## 常用命令

```bash
docker compose ps              # 查看容器状态
docker compose logs -f         # 查看日志
docker compose down            # 停止服务

# 手动触发一次监控
docker exec zhihu-monitor python -u /app/main.py
```

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `WEBHOOK_URL` | ✓ | - | Webhook 通知地址 |
| `ZHIHU_USER_ID` | | `shui-qian-xiao-xi` | 监控的用户 ID |
| `ZHIHU_USER_NAME` | | `马前卒official` | 用户显示名称 |
| `COOKIE_FILE` | | `../cookies.txt` | Cookie 文件路径 |

## 测试部署

```bash
# 检查容器状态（应有 rsshub, zhihu-monitor, ofelia 三个）
docker compose ps

# 测试 RSSHub（应返回 JSON）
curl http://localhost:1200/zhihu/people/answers/shui-qian-xiao-xi

# 手动执行一次监控
docker exec zhihu-monitor python -u /app/main.py

# 强制发送测试通知（即使没有新内容）
docker exec -e DEBUG_MODE=true zhihu-monitor python -u /app/main.py
```

## 调度配置

修改 `docker-compose.yml` 中的调度间隔：

```yaml
ofelia.job-exec.monitor.schedule: "0 */10 * * *"  # 每 10 小时
```

修改后执行 `docker compose restart`。
