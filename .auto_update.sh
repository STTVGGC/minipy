#!/bin/bash
cd /home/ubuntu/minipy || exit
echo "🔄 拉取最新代码..."
git fetch origin
git reset --hard origin/main
echo "✅ 更新完成，正在重启服务..."
sudo systemctl restart minipy
echo "🚀 服务已重启完成！"
