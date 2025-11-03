# 简易留言板 — 代码导向说明

本仓库是一个使用 FastAPI + Tortoise ORM 实现的简易留言板示例。此文档以代码为中心，着重说明前端、数据库与后端代码结构；对 Docker / 部署部分做简短说明。

---

## 目标受众
- 想快速了解项目代码组织和动线的开发者。
- 准备在本地、云或 Docker 上部署并希望理解各部分如何协同工作的运维/开发人员。

## 目录结构（重要文件）
- `main.py` — 应用入口，创建 FastAPI 应用、路由注册与数据库初始化（当前项目中可能包含硬编码的 MySQL URL，见下文）。
- `models.py` — 使用 Tortoise ORM 定义的数据模型（例如 Message）。
- `tortoise_config.py` — Tortoise ORM 的配置（用于开发通常会默认 sqlite；生产/云上可改为 MySQL）。
- `templates/` — 后端渲染模板（HTML）。
- `static/` — 静态资源（CSS、JS）。
- `requirements.txt` — Python 依赖清单（若使用表单上传/解析，需包含 `python-multipart`）。
- `Dockerfile`, `docker-compose.yml`, `.env.example` — 容器化与部署相关配置（简要说明见下）。

---

## 后端（服务器端）—— 代码重点

目的：处理 HTTP 请求、校验、与数据库交互并返回 HTML/JSON。

主要职责划分建议（项目中已有的文件对应）：

- 路由层（`main.py`）
  - 负责接收请求、调用验证器（Pydantic）并把请求委托给业务层。
  - 返回模板或 JSON。若项目较小，路由与简单逻辑可放在 `main.py`；若增大建议拆分为 `routers/` 目录。

- 模型层（`models.py`）
  - 使用 Tortoise ORM 定义实体（如 Message）与索引、字段约束。
  - 所有数据库字段与关系都在此定义。

- 验证/序列化（建议）
  - 使用 Pydantic schema（可以在 `schemas.py` 中）来定义输入/输出结构，避免在路由中直接操作原始 dict。

- 业务层（可选，建议）
  - 将复杂的数据库操作或事务逻辑封装到 `services.py` 或同级模块，使路由层保持简洁。

- 初始化/生命周期
  - 在 `main.py` 中完成 Tortoise 的初始化（根据 `tortoise_config.py` 或直接在代码中设置 DATABASE_URL）。
  - 在应用退出时正确关闭连接（Tortoise 提供对应的关闭方法）。

注意事项：
- 表单处理依赖 `python-multipart`（FastAPI 在解析 Form 类型时会报错，容器启动日志中已有类似错误提示：Form data requires "python-multipart"）。请确保 `requirements.txt` 中包含该包并在镜像内安装。
- 若你保留硬编码的 MySQL URL（你提到旧版代码能连接云服务器上的 MySQL），请务必确认该字符串不会被误提交到公共仓库，或在 README 明确标注风险。

---

## 前端（模板与静态资源）

- 位置：`templates/`（HTML），`static/`（CSS/JS）。
- 功能：简洁的表单用于提交留言，AJAX/Fetch 用于获取/删除/分页留言（若实现）。
- 可替换性：模板为轻量级实现，便于未来用 React/Vue 替换前端但复用后端 API。

实现建议：
- 在前端对用户输入做基础校验（非空、长度限制），后端仍需再次验证。
- 异步提交（Fetch）时处理好错误提示与加载状态，保障用户体验。

---

## 数据库（Tortoise ORM）

- ORM：Tortoise ORM，支持 SQLite、MySQL 等。
- 开发模式：仓库中 `tortoise_config.py` 可能默认配置为 SQLite（方便本地开发）。
- 生产/云：你提到已经在云服务器上配置了 MySQL，并且想继续在 `main.py` 中使用硬编码 MySQL URL；常见格式为：

  mysql://username:password@host:3306/database

  如果你在 `main.py` 里直接写了该 URL，程序会优先使用它；若在 `tortoise_config.py` 里仍是 sqlite，请把 `tortoise_config.py` 或初始化逻辑中的 DATABASE_URL 改为你的 MySQL URL（或在 `main.py` 初始化时覆盖）。

- 迁移：Tortoise 常与 `aerich` 配合做数据库迁移，建议在多人或生产环境中加入迁移流程。

安全与运维提示：
- 避免在仓库中保留明文凭据。如果必须硬编码（如你当前要求），务必对仓库权限/私有化管理严格控制。

---

## 运行与快速测试

本地开发（在虚拟环境或 conda 下）：

```bash
pip install -r requirements.txt
# 确保 requirements 中包含 python-multipart
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问：
- 浏览器打开 http://localhost:8000（或项目里定义的默认路由）
- 若使用 FastAPI 自动文档，可访问 http://localhost:8000/docs

---

## Docker（简短）

用途：容器化使部署一致。仓库包含 `Dockerfile` 和可选的 `docker-compose.yml`（用于同时启动 MySQL 与 Web 服务）。

快速构建运行镜像：

```bash
# 在仓库根目录
docker build -t messageboard .
# 如果 main.py 中需要环境变量，可使用 --env-file .env
docker run -p 8000:8000 --env-file .env messageboard
```

使用 docker-compose（如果你已经将代码改为从环境读取 DATABASE_URL，并在 .env 填写 MySQL URL）：

```bash
docker-compose up --build
```

Docker 注意：
- 容器中也需安装 `python-multipart`（在 `requirements.txt` 中声明）。
- 若使用 MySQL，请确认容器与云 MySQL 的网络连通性与安全组设置。

---

## 常见问题（Troubleshooting）

- 启动时报错：Form data requires "python-multipart" — 在 `requirements.txt` 中添加 `python-multipart` 并重新构建镜像。
- 本地 git pull/merge 冲突：如果云服务器上 `git pull` 提示有本地修改会被覆盖，可以先把本地改动 commit 或 stash，或在确认安全后执行强制覆盖（谨慎）。

---

如果你希望我：
- 把 `main.py` 改为从 `.env` 读取 `DATABASE_URL`（更安全），并更新 `docker-compose.yml` 示例 —— 我可以修改并演示构建镜像与运行；
- 或者保留硬编码 MySQL 并把 `tortoise_config.py` 同步为 MySQL —— 我也可以直接替你修改并在本地测试问题（包括添加 `python-multipart` 到依赖）。

请告诉我你下一步想要我执行的动作（例如：把 README 再微调、修改 `main.py` 以用环境变量、或直接在代码里把 tortoise 改为 MySQL 并构建 Docker 镜像）。
