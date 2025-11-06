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

### 3.1 启动与生命周期（lifespan）

---
“我们项目在启动和关闭时要处理数据库和缓存连接。
为了避免资源没释放或启动失败，我们用 FastAPI 的 lifespan。
它在启动时集中建立连接，在退出时统一关闭。
这样能保证程序即使运行在容器里，也能稳定、安全地管理外部资源。”

---

---

# 关于 `lifespan`

在我们的 FastAPI 项目中，程序启动时要连接数据库、连接 Redis 缓存，关闭时要释放这些连接。
为了让整个过程更安全、可控，我们使用了 **`lifespan` 生命周期管理**。

`lifespan` 是 FastAPI 提供的一种“启动与关闭钩子机制”。
可以理解成：

> 程序启动前做准备工作，程序退出前做清理。

我们用 Python 的 `asynccontextmanager` 来实现它。

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时运行
    await Tortoise.init(...)
    redis = Redis(...)
    yield
    # 关闭时运行
    await Tortoise.close_connections()
    await redis.close()


lifespan 启动阶

1. **初始化数据库**

   * 调用 `Tortoise.init()` 连接 MySQL；
   * 把 ORM 模型（Python 类）和数据库表关联起来；

2. **初始化 Redis 缓存**

   * 创建 Redis 客户端并执行 `ping()` 测试；
   * 如果 Redis 可用，就启用缓存逻辑；
   * 如果不可用，不影响主程序，只是暂时不用缓存。

3. **设置标志变量**

   * 用 `redis_available = True/False` 标记 Redis 当前状态；
   * 让后续所有缓存操作知道是否能安全使用 Redis。


lifespan 关闭阶段

1. **关闭数据库连接**
   调用 `Tortoise.close_connections()`，安全断开所有数据库连接，防止资源泄露。

2. **关闭 Redis 连接**
   尝试兼容不同版本的 Redis 库，确保连接池安全关闭。




相比在 `import` 阶段（模块刚加载时）就创建连接
用 lifespan 可以：

* **延后连接时机**（只在程序启动时连接）；
* **集中管理资源**（启动时创建，退出时关闭）；
* **容器化部署更稳定**。

lifespan 代码块

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await Tortoise.init(db_url=DATABASE_URL, modules={"models": ["models"]})
    if GENERATE_SCHEMAS:
        await Tortoise.generate_schemas()
    # Redis init
    try:
        redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=REDIS_DECODE_RESPONSES)
        await redis.ping()
        redis_available = True
    except Exception:
        redis_available = False
        redis = None
    try:
        yield
    finally:
        await Tortoise.close_connections()
        if redis is not None:
            # 兼容不同客户端版本的关闭逻辑
            close_fn = getattr(redis, "close", None)
            if inspect.isawaitable(close_fn()):
                await close_fn()
```

说明：该模式避免在模块导入时连接外部服务，且在 Redis 不可用时应用仍能可用（降级）。



##  3.2 密码处理与认证（Password & Authentication）

**用户密码的安全存储**和**登录身份验证方式**。

###  一、密码保存

在我们的项目中，**不会把用户的真实密码直接保存到数据库**。
而是用 passlib 加密保存。登录时通过加密结果验证密码是否正确。



我们使用了一个加密库 **passlib**，它提供了安全的密码算法：`pbkdf2_sha256`。

当用户注册时：

```python
get_password_hash(password)
```

会先把密码转成字节（UTF-8 编码），再**截断到 72 字节以内**（这是为了兼容早期 bcrypt 的限制），
然后再进行加密（哈希）生成安全的密文保存。

当用户登录时：

```python
verify_password(plain_password, hashed_password)
```

程序会对输入的密码做**同样的截断和哈希**，再跟数据库中的密文比对。
这样能保证即使明文密码再长，也能安全、稳定地验证。

> “我们的项目不会存用户密码，而是存一串加密后的哈希值。
> 登录时只比对加密后的结果，不直接看密码。”

---

### 🔑 二、登录认证（JWT 令牌）
登录成功后，我们不会让浏览器记住用户名和密码，而是会得到一个叫 JWT 的通行证，用它识别用户身份。

> **JWT（JSON Web Token）**

这个令牌（Token）包含用户信息和过期时间，比如 30 分钟有效。
生成方式使用：

```python
SECRET_KEY + ALGORITHM = "HS256"
```

发给用户后，浏览器会自动把它放到 Cookie 中：

```
access_token = Bearer <token>
```

并且设置为：

* `httponly`: 前端脚本无法读取（防止 插入恶意的 HTML 或 JavaScript 代码）
* `samesite=lax`: 提高跨站安全性

这样，之后每次访问时浏览器会自动带上这个 token，后端用它验证用户身份。

 即
> “我们用 JWT 来判断用户是谁。
> 用户登录后拿到一个通行证（token），系统就能识别出他的身份。”

---

密码截断与哈希代码块

```python
def get_password_hash(password):
    # 截断到72字节以兼容历史限制
    password_bytes = password.encode('utf-8')[:72]
    truncated_password = password_bytes.decode('utf-8', errors='replace')
    return pwd_context.hash(truncated_password)

def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode('utf-8')[:72]
    truncated_password = password_bytes.decode('utf-8', errors='replace')
    return pwd_context.verify(truncated_password, hashed_password)
```

说明：截断逻辑必须保留以避免与历史密码哈希行为不一致导致用户无法登陆。


## 🚀 3.3 缓存策略（Caching Strategy）

留言数据会放到 Redis 缓存里，加快加载速度。内容更新时会清空缓存，保证最新。

### ⚙️ 一、缓存机制的工作流程

1. 当用户点击“按最新排序”查看留言时：
   程序会先从 **Redis 缓存** 读取留言数据（缓存名叫 `CACHE_KEY_MESSAGES`）。

   * 如果 Redis 里有缓存（命中），直接返回，**速度很快**；
   * 如果没有缓存，就去数据库查一次，并把结果存入 Redis。

2. 当用户新增留言、点赞、删除留言时：
   这些操作会让页面内容发生变化，因此程序会：

   ```python
   cache_delete(CACHE_KEY_MESSAGES)
   ```

   删除旧缓存，让下一次请求重新生成最新数据。

3. 如果 Redis 出现连接问题（比如宕机）：
   程序会自动把一个标志 `redis_available` 设为 `False`，
   后续请求就不会再尝试连接 Redis，而是直接查数据库，**保证服务不中断**。


> Redis 不可用也没关系，系统会自动降级。”

---

 redis缓存辅助函数

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

说明：读写缓存都使用类似的异常后降级策略，保证运行稳定性。


## 🧱 3.4 数据模型（Database Models）

数据库有留言、评论、用户三张表，每张表结构都清晰定义在 models.py 中

> “我们有三张主要的表：留言、评论和用户。
> ORM 让我们用 Python 类来操作数据库，不需要手写 SQL。”

（对应三张表）：

| 模型          | 作用      | 主要字段                                                   |
| ----------- | ------- | ------------------------------------------------------ |
| **Message** | 存放留言内容  | id, name, user(FK), content, likes, created_at         |
| **Comment** | 存放留言的回复 | id, message(FK), name, user(FK), content, created_at   |
| **User**    | 用户信息表   | id, username（唯一）, password_hash, is_active, created_at |

每个模型都继承自 **Tortoise ORM** 的 Model 类，并且在 `Meta.table` 中明确写了表名（如 `messages`, `comments`, `users`），
这样做的好处是：

* 不管项目更新还是数据库迁移，表名都保持一致；
* 方便维护、避免意外重命名或冲突。

---


## 🧭 3.5 路由与视图（`main.py`）

在这一部分，主要是定义网站对外提供的接口（也就是用户能访问的地址）。
可以理解成每个路由就是网站的一个“功能入口”。

### 🔹 路由功能总览

| 路由                             | 方法             | 作用说明                           |                                    |
| ------------------------------ | -------------- | ------------------------------ | ---------------------------------- |
| `/`                            | **GET**        | 留言板主页，支持排序（`sort=asc           | desc`），当使用 `desc` 时会优先读取缓存，加快加载速度。 |
| `/submit`                      | **POST**       | 提交留言。已登录用户自动使用用户名，匿名用户需手动填写姓名。 |                                    |
| `/like/{msg_id}`               | **GET**        | 点赞留言。会更新数据库并清除缓存。              |                                    |
| `/comment/{msg_id}`            | **POST**       | 对某条留言添加回复。                     |                                    |
| `/comments/{msg_id}`           | **GET**        | 获取某条留言的所有评论列表。                 |                                    |
| `/register`、`/login`、`/logout` | **POST / GET** | 用户注册、登录与退出功能。                  |                                    |

这些路由由 FastAPI 实现，并使用 **Jinja2 模板引擎** 来生成 HTML 页面。
部分交互（比如加载评论、点赞）使用了 **AJAX 异步请求**，不用整页刷新。

---

### 提交留言示例（核心逻辑）

这是用户提交留言时执行的主要函数。
它判断留言内容是否合法，并区分“登录用户”和“匿名用户”的写入方式。

```python
@app.post("/submit")
async def submit_message(request: Request, name: str = Form(None), content: str = Form(...)):
    # 防止空内容
    if not content.strip():
        return RedirectResponse("/", status_code=303)

    # 如果用户已登录，则使用登录用户名
    if current_user:
        await Message.create(
            name=current_user.username,
            user=current_user,
            content=content.strip(),
            created_at=datetime.now()
        )
    else:
        # 匿名用户需要填写名字
        if not name.strip():
            return RedirectResponse("/", status_code=303)
        await Message.create(
            name=name.strip(),
            content=content.strip(),
            created_at=datetime.now()
        )

    # 每次写入后立即清理缓存，防止读取到旧数据
    await cache_delete(CACHE_KEY_MESSAGES)
    return RedirectResponse("/", status_code=303)
```

**说明**：
这段代码的重点在于两点：

1. **验证输入**：确保留言内容不为空；
2. **保持数据最新**：每次写入成功后立即清除 Redis 缓存，下次访问时重新加载数据库中的最新留言。

---

## ⚙️ 4 项目运行说明

项目既可以在本地环境直接运行，也可以通过 Docker 进行容器化部署。

---

### 💻 4.1 本地运行（PowerShell）

1. **创建虚拟环境并安装依赖**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. **启动项目服务**

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3. **访问应用**

* 网站主页： [http://localhost:8000](http://localhost:8000)
* 自动生成的 API 文档（FastAPI 自带）： [http://localhost:8000/docs](http://localhost:8000/docs)

> ⚠️ 注意：
> 如果使用 MySQL，请在环境变量或 `tortoise_config.py` 中正确设置 `DATABASE_URL`。
> 示例：
>
> ```
> DATABASE_URL=mysql://user:password@localhost:3306/messageboard（不建议直接写入真实的数据库地址）
> ```
>

---

### 🐳 4.2 使用 Docker / docker-compose 运行

项目提供了现成的 `Dockerfile` 和 `docker-compose.yml` 文件，可以快速一键部署。

```powershell
# 构建并后台运行所有服务
docker-compose up --build -d

# 查看实时日志
docker-compose logs -f
```

`docker-compose.yml` 中定义了以下几个容器服务：

| 服务名     | 说明           |
| ------- | ------------ |
| `app`   | FastAPI 应用服务 |
| `db`    | MySQL 数据库    |
| `redis` | Redis 缓存服务   |

首次运行若希望自动创建数据库表结构，请在 `.env` 文件或系统环境变量中添加：

```
GENERATE_SCHEMAS=True
DATABASE_URL=mysql://appuser:secret@db:3306/messageboard
```

---


5 结语

本留言板项目基于 FastAPI + Tortoise ORM + MySQL + Redis 技术栈开发，实现了一个轻量但功能完善的全栈示例。
项目的主要特征包括：

模块化设计： 清晰区分模型层、路由层与模板视图，结构易扩展；

缓存机制： 使用 Redis 提升热门留言读取效率，写操作时自动清除缓存，避免脏数据；

用户体系： 实现注册、登录、登出功能，密码以哈希方式安全存储；

异步框架优势： FastAPI + async ORM 提升了高并发下的响应性能；

容器化部署： 通过 Docker Compose 一键启动应用、数据库与缓存服务，便于跨环境复现与交付。

项目已成功部署到：
🔗 https://wzh730903.top

开源仓库地址：
📦 GitHub： https://github.com/STTVGGC/minipy

🐳 Docker Hub： sttvggc/messageboard
