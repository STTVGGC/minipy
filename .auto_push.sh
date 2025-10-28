#!/bin/bash

# =========================================
# 自动推送 + 服务器更新脚本
# =========================================

# 本地仓库路径
LOCAL_REPO_DIR="/home/ubuntu/minipy"

# 服务器信息
REMOTE_USER="ubuntu"
REMOTE_HOST="43.207.3.211"
REMOTE_DIR="/home/ubuntu/minipy"

# Git 提交信息
COMMIT_MSG="自动提交 $(date '+%Y-%m-%d %H:%M:%S')"

# -----------------------------------------
# Step 1: 进入本地仓库
# -----------------------------------------
cd "$LOCAL_REPO_DIR" || { echo "❌ 本地仓库目录不存在"; exit 1; }

# Step 2: 检查变更
git status

# Step 3: 添加所有修改、删除、新增的文件
git add -A

# Step 4: 提交（如果没有改动，跳过 commit）
git diff --cached --quiet || git commit -m "$COMMIT_MSG"

# Step 5: 推送到远程
git push origin main
if [ $? -ne 0 ]; then
    echo "❌ Git push 失败，请检查远程仓库或冲突"
    exit 1
fi

# -----------------------------------------
# Step 6: SSH 登录服务器更新
# -----------------------------------------
ssh "$REMOTE_USER@$REMOTE_HOST" << EOF
cd "$REMOTE_DIR" || { echo "❌ 服务器目录不存在"; exit 1; }

# 拉取最新代码
git pull origin main

# 可选：重启服务（根据你的实际服务修改）
# 例如：使用 systemctl
# sudo systemctl restart minipy

EOF

echo "✅ 自动推送和服务器更新完成"
