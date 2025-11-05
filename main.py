import json
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional
import inspect

#数据库相关
from tortoise import Tortoise
from models import Message
#Redis相关
from redis.asyncio import Redis

# -------------------- 应用与配置 --------------------
# 使用 lifespan 管理启动/关闭（替代已弃用的 @app.on_event）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 Tortoise ORM
    await Tortoise.init(db_url=DATABASE_URL, modules={"models": ["models"]})
    if GENERATE_SCHEMAS:
        await Tortoise.generate_schemas()
    print("✅ Tortoise ORM 已初始化")

    # 在启动时创建并探测 Redis 可用性（若不可用则降级为无缓存模式）
    global redis, redis_available
    try:
        redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=REDIS_DECODE_RESPONSES)
        await redis.ping()
        redis_available = True
        print("✅ Redis 可用，缓存已启用")
    except Exception as e:
        # 不抛出异常，允许应用继续以降级模式运行（不使用缓存）
        redis_available = False
        redis = None
        print(f"⚠️ 无法连接 Redis，缓存已禁用: {e}")

    print("✅ FastAPI 留言板已启动 (容器内)。访问: http://0.0.0.0:8000")
    try:
        yield
    finally:
        # 关闭 Tortoise
        try:
            await Tortoise.close_connections()
            print("✅ Tortoise ORM 连接已关闭")
        except Exception as e:
            print(f"⚠️ 关闭 Tortoise 连接时出错: {e}")

        # 关闭 redis 连接（如果创建了）
        if redis is not None:
            try:
                close_fn = getattr(redis, "close", None)
                if close_fn is not None:
                    res = close_fn()
                    if inspect.isawaitable(res):
                        await res
            except Exception:
                # some redis client versions may not require/allow await on close
                try:
                    close_fn = getattr(redis, "close", None)
                    if close_fn is not None:
                        close_fn()
                except Exception:
                    pass

            try:
                pool = getattr(redis, "connection_pool", None)
                if pool is not None:
                    disconnect_fn = getattr(pool, "disconnect", None)
                    if disconnect_fn is not None:
                        res = disconnect_fn()
                        if inspect.isawaitable(res):
                            await res
            except Exception:
                pass
            print("✅ Redis 连接已关闭")

app = FastAPI(title="简易留言板 - 数据库版", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# 硬编码的 MySQL 连接字符串
DATABASE_URL = "mysql://Wang:A19356756837@52.196.78.16:3306/messageboard"
GENERATE_SCHEMAS = False  # 表已存在，设置为False避免重复创建表结构

import os

# Redis 配置支持从环境变量读取，适应开发和Docker环境
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_DECODE_RESPONSES = os.getenv("REDIS_DECODE_RESPONSES", "True").lower() == "true"

# Redis 客户端会在 lifespan 中创建以避免在模块导入时触发连接错误
redis: Optional[Redis] = None
CACHE_KEY_MESSAGES = "messages_cache"  # 缓存key
CACHE_EXPIRE_SECONDS = 60  # 缓存有效期(秒)，可改

# Redis 可用性标志（如果连接失败，我们会降级为不使用缓存）
redis_available = True

async def cache_get(key: str):
    """尝试从 Redis 获取值，若 Redis 不可用或取值失败则返回 None。"""
    global redis_available
    if not redis_available or redis is None:
        return None
    try:
        local_redis = redis
        return await local_redis.get(key)
    except Exception as e:
        # 标记不可用以避免每次都抛异常，稍后可在日志中调查
        print(f"⚠️ Redis get 失败，禁用缓存: {e}")
        redis_available = False
        return None

async def cache_setex(key: str, seconds: int, value: str):
    """尝试写入 Redis（设置过期），失败则静默返回 False。"""
    global redis_available
    if not redis_available or redis is None:
        return False
    try:
        local_redis = redis
        await local_redis.setex(key, seconds, value)
        return True
    except Exception as e:
        print(f"⚠️ Redis setex 失败，禁用缓存: {e}")
        redis_available = False
        return False

async def cache_delete(key: str):
    """尝试删除缓存键，失败则静默返回 False。"""
    global redis_available
    if not redis_available or redis is None:
        return False
    try:
        local_redis = redis
        await local_redis.delete(key)
        return True
    except Exception as e:
        print(f"⚠️ Redis delete 失败，禁用缓存: {e}")
        redis_available = False
        return False


# -------------------- 工具函数 --------------------
def time_ago(dt: datetime) -> str:
    """把时间转为‘几分钟前’格式"""
    now = datetime.now(timezone.utc)  # 带时区的当前时间
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # 补上时区
    delta = now - dt
    if delta < timedelta(minutes=1):
        return "刚刚"
    elif delta < timedelta(hours=1):
        return f"{int(delta.seconds / 60)}分钟前"
    elif delta < timedelta(days=1):
        return f"{int(delta.seconds / 3600)}小时前"
    elif delta < timedelta(days=7):
        return f"{delta.days}天前"
    else:
        return dt.strftime("%Y-%m-%d %H:%M")


# -------------------- 路由与逻辑 --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, sort: str = "desc"):
    """显示留言板主页"""
    messages = None

    # 如果是按最新排序，先尝试从缓存读取（缓存以最新优先存储）
    if sort == "desc":
        cached_data = await cache_get(CACHE_KEY_MESSAGES)
        if cached_data:
            try:
                messages = json.loads(cached_data)
                print("✅ 从 Redis 加载留言")
            except Exception:
                messages = None

    # 如果缓存未命中，或请求升序排序，则直接从数据库读取
    if messages is None:
        if sort == "asc":
            db_messages = await Message.all().order_by("created_at")
        else:
            db_messages = await Message.all().order_by("-created_at")

        # 转成可在模板中直接使用的字典（也包含展示用的时间字符串）
        messages = [
            {
                "id": msg.id,
                "name": msg.name,
                "content": msg.content,
                "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "time_display": time_ago(msg.created_at),
            }
            for msg in db_messages
        ]

        # 仅对 desc 排序写入缓存
        if sort == "desc":
            ok = await cache_setex(CACHE_KEY_MESSAGES, CACHE_EXPIRE_SECONDS, json.dumps(messages))
            if ok:
                print("💾 从数据库加载并写入 Redis")

    return templates.TemplateResponse("index.html", {
        "request": request,
        "messages": messages,
        "sort": sort
    })


@app.post("/submit")
async def submit_message(name: str = Form(...), content: str = Form(...)):
    """提交新留言"""
    if not name.strip() or not content.strip():
        return RedirectResponse("/", status_code=303)

    await Message.create(
        name=name.strip(),
        content=content.strip(),
        created_at=datetime.now()
    )

    # ✅ 新留言 → 清空缓存（同步 redis 客户端）
    deleted = await cache_delete(CACHE_KEY_MESSAGES)
    if deleted:
        print("🧹 清空缓存（新增留言）")

    return RedirectResponse("/", status_code=303)


@app.get("/delete/{msg_id}")
async def delete_message(msg_id: int):
    """删除留言"""
    msg = await Message.filter(id=msg_id).first()
    if msg:
        await msg.delete()
        # 删除缓存
        await cache_delete(CACHE_KEY_MESSAGES)
    return RedirectResponse("/", status_code=303)


@app.get("/clear")
async def clear_messages():
    """清空留言"""
    await Message.all().delete()

    deleted = await cache_delete(CACHE_KEY_MESSAGES)  # 清除缓存
    if deleted:
        print("🧹 清空缓存（删除所有留言）")
    return RedirectResponse("/", status_code=303)


# -------------------- 静态资源 --------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------- 数据库连接 --------------------
print("DB_URL =", DATABASE_URL)

# 已通过 lifespan 管理 Tortoise 初始化与关闭（参见文件顶部 lifespan）


# -------------------- 启动提示 --------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
