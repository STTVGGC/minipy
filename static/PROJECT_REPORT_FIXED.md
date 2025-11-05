# 项目报告 — 简易留言板（minipy）

日期：2025-11-05

## 1 项目简介与功能概述

这是一个基于 FastAPI 的服务端渲染（Jinja2）示例应用，提供一个简易的留言板功能，主要支持：

- 访客/用户发布留言（带内容与昵称）
- 留言的回复（Comment）功能
- 点赞（likes）与删除留言/回复
- 用户注册、登录、登出（基于 JWT）
- 可选的 Redis 缓存用于加速按最新排序的留言列表
- 使用 Tortoise ORM 管理数据库模型，并带有 aerich 迁移支持

## 2 使用的技术栈

- Python 3.11（镜像基于 python:3.11-slim）
- FastAPI — HTTP 框架与路由
- Uvicorn — ASGI 运行器
- Jinja2 — 后端模板（位于 `templates/`）
- Tortoise ORM — 异步 ORM（模型定义在 `models.py`）
- aerich — Tortoise 的迁移工具（配置在 `pyproject.toml`）
- Redis（可选） — 缓存层（使用 redis.asyncio 客户端）
- MySQL（可选）/SQLite — 数据库后端（`tortoise_config.py` 支持通过 `DATABASE_URL` 切换）
- passlib（pbkdf2_sha256）— 密码哈希
- python-jose — JWT 编码与解码
- 其他：python-multipart、aiomysql、jinja2

依赖清单见 `requirements.txt`。

## 3 核心实现逻辑

以下列出本项目的主要实现要点、数据流与注意事项。

### 3.1 启动与生命周期（Lifespan）

我们的项目在启动和关闭时需要正确处理数据库和缓存连接。  
为了避免资源未释放或启动失败，我们使用了 **FastAPI 的 lifespan**。  
它在程序启动时统一建立连接，在退出时自动关闭，保证了服务在容器化或部署环境中稳定运行。

#### 什么是 Lifespan

`lifespan` 是 FastAPI 提供的生命周期钩子。  
你可以把它理解为：

> “程序启动前做准备工作，程序退出前做清理。”

我们使用 Python 的 `asynccontextmanager` 来定义这段生命周期逻辑。

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段
    await Tortoise.init(db_url=DATABASE_URL, modules={"models": ["models"]})
    if GENERATE_SCHEMAS:
        await Tortoise.generate_schemas()

    # 初始化 Redis
    try:
        redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        await redis.ping()
        redis_available = True
    except Exception:
        redis_available = False
        redis = None

    # 应用运行中
    try:
        yield
    finally:
        # 关闭数据库与缓存
        await Tortoise.close_connections()
        if redis is not None:
            close_fn = getattr(redis, "close", None)
            if inspect.isawaitable(close_fn()):
                await close_fn()
```

#### Lifespan 的好处

相比在模块导入时就连接外部服务，使用 lifespan 可以：

- ✅ 延迟初始化（只有程序启动时连接）  
- ✅ 集中管理资源（启动创建、退出释放）  
- ✅ 提升容器化稳定性与安全性

### 3.2 密码处理与认证（Password & Authentication）

#### 一、密码加密与验证

用户密码不会直接保存到数据库中，而是通过 **Passlib** 库的 `pbkdf2_sha256` 算法进行哈希加密。

```python
def get_password_hash(password):
    # 截断到72字节以兼容旧版bcrypt
    password_bytes = password.encode('utf-8')[:72]
    truncated = password_bytes.decode('utf-8', errors='replace')
    return pwd_context.hash(truncated)

def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode('utf-8')[:72]
    truncated = password_bytes.decode('utf-8', errors='replace')
    return pwd_context.verify(truncated, hashed_password)
```

> 项目中保留了截断逻辑，确保与历史哈希行为兼容，防止老用户登录失败。

#### 二、JWT 登录认证

登录成功后，系统使用 **JWT（JSON Web Token）** 生成一个访问令牌。  
令牌中包含用户信息与过期时间（默认 30 分钟）。

生成方式：

```python
SECRET_KEY = "your_secret"
ALGORITHM = "HS256"
```

发给客户端时存入 Cookie：

```
access_token = Bearer <token>
```

Cookie 属性：

- `httponly`: 防止 JS 读取（防 XSS）
- `samesite=lax`: 防跨站攻击

> ✅ “我们用 JWT 通行证识别用户身份，不保存密码，只验证令牌。”

### 3.3 缓存策略（Caching Strategy）

留言列表支持缓存，以加速加载“最新留言”时的响应速度。

#### 缓存工作流程

1. 用户打开留言主页时，后台优先尝试从 Redis 获取缓存数据：
   ```python
   await cache_get(CACHE_KEY_MESSAGES)
   ```
   - 命中缓存：直接返回，加载速度快；
   - 未命中：从数据库查询并写入缓存。

2. 当留言被新增、点赞或删除时：
   ```python
   await cache_delete(CACHE_KEY_MESSAGES)
   ```
   删除旧缓存，保证页面显示最新数据。

3. 若 Redis 连接失败，则自动关闭缓存功能：
   ```python
   redis_available = False
   ```
   之后直接读数据库，不影响主流程。

> 即便 Redis 崩溃，程序仍然能正常工作（降级机制）。

#### 示例代码（异常保护）

```python
async def cache_get(key: str):
    if not redis_available or redis is None:
        return None
    try:
        return await redis.get(key)
    except Exception:
        redis_available = False
        return None
```

### 3.4 数据模型（Database Models）

本项目包含三张主要数据表：留言、评论、用户。  
均由 **Tortoise ORM** 定义在 `models.py` 中。

| 模型 | 功能 | 主要字段 |
|------|------|-----------|
| **Message** | 存放留言 | id, name, user(FK), content, likes, created_at |
| **Comment** | 存放回复 | id, message(FK), name, user(FK), content, created_at |
| **User** | 存放用户 | id, username(unique), password_hash, is_active, created_at |

表名通过 `Meta.table` 显式定义（如 `messages`, `comments`, `users`），便于后期迁移或数据库兼容。

### 3.5 路由与视图（main.py）

#### 路由功能概览

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 留言主页（支持排序、读取缓存） |
| `/submit` | POST | 提交留言 |
| `/like/{msg_id}` | GET | 点赞留言 |
| `/comment/{msg_id}` | POST | 添加回复 |
| `/comments/{msg_id}` | GET | 获取某条留言的所有评论 |
| `/register`, `/login`, `/logout` | POST/GET | 用户相关功能 |

页面使用 **Jinja2 模板** 渲染，部分交互采用 **AJAX 异步提交**。

#### 提交留言示例

```python
@app.post("/submit")
async def submit_message(request: Request, name: str = Form(None), content: str = Form(...)):
    if not content.strip():
        return RedirectResponse("/", status_code=303)

    if current_user:
        await Message.create(
            name=current_user.username,
            user=current_user,
            content=content.strip(),
            created_at=datetime.now()
        )
    else:
        if not name.strip():
            return RedirectResponse("/", status_code=303)
        await Message.create(
            name=name.strip(),
            content=content.strip(),
            created_at=datetime.now()
        )

    await cache_delete(CACHE_KEY_MESSAGES)
    return RedirectResponse("/", status_code=303)
```

🗒️ 写操作后立即清除缓存，防止读取旧数据。

## 4 项目运行说明

### 4.1 本地运行（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问：
- 首页：[http://localhost:8000](http://localhost:8000)
- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)

> ⚠️ 请确保 `DATABASE_URL` 在环境变量或配置文件中已正确设置。

### 4.2 Docker 运行

```powershell
docker-compose up --build -d
docker-compose logs -f
```

`docker-compose.yml` 包含 `app`, `db`, `redis` 三个服务。  
如需自动创建表，请在环境变量中启用：

```
GENERATE_SCHEMAS=True
DATABASE_URL=mysql://appuser:secret@db:3306/messageboard
```

## 5 结语

本留言板项目是一个完整的异步 Web 应用示例，结合了 **FastAPI** 的高性能、**Tortoise ORM** 的易用性与 **Redis 缓存** 的高效特性。

**项目亮点：**
- 模块结构清晰、代码易读；
- 具备完整的用户认证与留言逻辑；
- 使用 Redis 缓存加速页面；
- 支持 Docker 一键部署。

### 项目信息

- 已部署地址： https://wzh730903.top
- GitHub： https://github.com/STTVGGC/minipy
- Docker Hub： sttvggc/messageboard

