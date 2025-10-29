#!/bin/bash
cd /home/ubuntu/minipy || exit
echo "拉取最新代码..."
git stash push -m "自动保存本地修改"
git fetch origin
git reset --hard origin/main
git stash pop
echo "更新完成，重启服务..."
sudo systemctl restart minipy
