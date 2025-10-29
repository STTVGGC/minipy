# 简易留言板 - Docker 配置说明

本仓库是一个使用 FastAPI + Tortoise ORM 的简易留言板示例。以下说明展示如何用 Docker 或 Docker Compose 运行它。

重要说明：当前 `main.py` 中使用了硬编码的 MySQL 连接字符串（直接写在源码中），因此容器/运行时会优先使用该硬编码 URL。若你希望使用环境变量来切换数据库，我可以把行为改回环境变量模式（更安全）。

快速开始（使用 sqlite，开发时最简单）：

1. 复制 `.env.example` 为 `.env`：

   ```bash
   copy .env.example .env
   ```

2. 使用 Docker 构建并运行：

   ```bash
   docker build -t messageboard .
   docker run -p 8000:8000 --env-file .env messageboard
   ```

可选：使用 Docker Compose 启动带 MySQL 的环境（替代 sqlite）：

1. 复制 `.env.example` 并修改（仅在你将源码改为从环境读取 `DATABASE_URL` 时才会生效）：

   - 将 `DATABASE_URL` 改为：
     `mysql://appuser:secret@db:3306/messageboard`

2. 启动 Compose：

   ```bash
   docker-compose up --build
   ```

安全提醒：
- 目前源码中包含明文数据库凭据（位于 `main.py`），请尽量避免将含有真实密码的源码推送到远程仓库或公共平台。推荐的做法是：
  - 使用 `.env` 文件保存敏感信息，并将 `.env` 加入 `.gitignore`；或
  - 使用云提供商的 Secrets 管理服务。

Notes:
- 若使用 MySQL 并需要在容器内安装 MySQL client 库，Dockerfile 中已加入常用系统依赖 `default-libmysqlclient-dev`。
- 若遇到 MySQL Python 依赖安装失败，请考虑更换基础镜像或在宿主机上预先安装系统包。

Troubleshooting:
- 若你需要我把连接方式改回使用 `DATABASE_URL` 环境变量并演示如何在 Docker Compose 中安全配置，我可以帮你完成并验证运行。
