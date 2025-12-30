#!/bin/bash
# Script to check Ofelia scheduler status and configuration

echo "=========================================="
echo "Ofelia Scheduler Diagnostic Tool"
echo "=========================================="
echo ""

# Check if containers are running
echo "1. Checking container status..."
echo "-----------------------------------"
docker ps --filter "name=ofelia" --filter "name=zhihu-monitor" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
echo ""

# Check Ofelia logs (last 50 lines)
echo "2. Checking Ofelia scheduler logs (last 50 lines)..."
echo "-----------------------------------"
docker logs --tail 50 ofelia 2>&1 | grep -E "(job|schedule|exec|error|ERROR|WARN)" || echo "No relevant log entries found"
echo ""

# Check monitor container logs (last 30 lines)
echo "3. Checking monitor container logs (last 30 lines)..."
echo "-----------------------------------"
docker logs --tail 30 zhihu-monitor 2>&1 | tail -20
echo ""

# Check if Ofelia can see the job
echo "4. Checking Ofelia job configuration..."
echo "-----------------------------------"
docker inspect zhihu-monitor --format '{{range $k, $v := .Config.Labels}}{{printf "%s = %s\n" $k $v}}{{end}}' | grep ofelia
echo ""

# Check last execution time from state file
echo "5. Checking last execution time from state file..."
echo "-----------------------------------"
if [ -f "./data/state.json" ]; then
    echo "Last check time:"
    cat ./data/state.json | grep -o '"last_check": "[^"]*"' | head -1
    echo ""
    echo "Last notification time:"
    cat ./data/state.json | grep -o '"last_notification_time": "[^"]*"' | head -1
else
    echo "State file not found at ./data/state.json"
fi
echo ""

# Test manual execution
echo "6. Testing manual execution..."
echo "-----------------------------------"
echo "Running monitor script manually..."
docker exec zhihu-monitor python -u monitor.py
echo ""

echo "=========================================="
echo "Diagnostic complete!"
echo "=========================================="
echo ""
echo "To view real-time logs:"
echo "  docker logs -f ofelia"
echo "  docker logs -f zhihu-monitor"
echo ""
echo "To check if scheduler is working, wait 15 minutes and check logs again."

