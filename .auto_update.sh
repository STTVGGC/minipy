#!/bin/bash
cd /home/ubuntu/minipy || exit
echo "拉取最新代码..."
git fetch origin
git reset --hard origin/main
git clean -fd -e messages.json
echo "更新完成，重启服务..."
sudo systemctl restart minipy