import json
import uvicorn
from fastapi import FastAPI, Form, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional
import inspect
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

#数据库相关
from tortoise import Tortoise
from models import Message, Comment
#Redis相关
from redis.asyncio import Redis

# -------------------- 密码与认证配置 --------------------
# 密码加密上下文 - 使用pbkdf2_sha256避免bcrypt的72字节密码长度限制
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# JWT配置
SECRET_KEY = "your-secret-key-change-in-production"  # 生产环境中应该使用环境变量设置
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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


# -------------------- 认证相关工具函数 --------------------
def verify_password(plain_password, hashed_password):
    """验证密码，自动截断超过72字节的密码"""
    try:
        # 确保密码是字符串
        if not isinstance(plain_password, str):
            plain_password = str(plain_password)
        
        # 强制截断密码到72字节
        password_bytes = plain_password.encode('utf-8')[:72]
        truncated_password = password_bytes.decode('utf-8', errors='replace')
        
        # 记录详细的调试信息
        original_len = len(plain_password.encode('utf-8'))
        truncated_len = len(truncated_password.encode('utf-8'))
        print(f"📝 密码验证: 原始长度={original_len}字节, 截断后长度={truncated_len}字节")
        
        # 确保截断后的值不会导致bcrypt错误
        if truncated_len > 72:
            print(f"⚠️ 警告: 即使截断后，密码长度仍然是{truncated_len}字节")
            # 再次截断以确保安全
            truncated_password = truncated_password.encode('utf-8')[:72].decode('utf-8', errors='replace')
            print(f"🔒 再次截断后长度={len(truncated_password.encode('utf-8'))}字节")
        
        # 使用截断后的密码进行验证
        return pwd_context.verify(truncated_password, hashed_password)
    except Exception as e:
        print(f"❌ 密码验证错误: {str(e)}")
        # 打印更详细的错误信息，包括堆栈跟踪
        import traceback
        traceback.print_exc()
        raise

def get_password_hash(password):
    """获取密码哈希值，自动截断超过72字节的密码"""
    try:
        # 确保密码是字符串
        if not isinstance(password, str):
            password = str(password)
        
        # 强制截断密码到72字节
        password_bytes = password.encode('utf-8')[:72]
        truncated_password = password_bytes.decode('utf-8', errors='replace')
        
        # 记录详细的调试信息
        original_len = len(password.encode('utf-8'))
        truncated_len = len(truncated_password.encode('utf-8'))
        print(f"📝 密码处理: 原始长度={original_len}字节, 截断后长度={truncated_len}字节")
        
        # 确保截断后的值不会导致bcrypt错误
        if truncated_len > 72:
            print(f"⚠️ 警告: 即使截断后，密码长度仍然是{truncated_len}字节")
            # 再次截断以确保安全
            truncated_password = truncated_password.encode('utf-8')[:72].decode('utf-8', errors='replace')
            print(f"🔒 再次截断后长度={len(truncated_password.encode('utf-8'))}字节")
        
        # 使用截断后的密码获取哈希
        return pwd_context.hash(truncated_password)
    except Exception as e:
        print(f"❌ 密码哈希错误: {str(e)}")
        # 打印更详细的错误信息，包括堆栈跟踪
        import traceback
        traceback.print_exc()
        raise

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await User.filter(username=username).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user = Depends(get_current_user)):
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

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
    current_user = None
    token = request.cookies.get("access_token")
    
    # 尝试解析令牌获取当前用户
    if token:
        try:
            token = token.replace("Bearer ", "")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            current_user = await User.filter(username=username).first()
        except:
            # 令牌无效时忽略错误
            pass

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
                "likes": msg.likes,
                "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "time_display": time_ago(msg.created_at),
                # 评论将通过AJAX加载
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
        "sort": sort,
        "current_user": current_user
    })


@app.post("/submit")
async def submit_message(request: Request, name: str = Form(None), content: str = Form(...)):
    """提交新留言"""
    # 检查是否有登录用户
    token = request.cookies.get("access_token")
    current_user = None
    
    if token:
        try:
            token = token.replace("Bearer ", "")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            current_user = await User.filter(username=username).first()
        except:
            pass
    
    # 验证内容
    if not content.strip():
        return RedirectResponse("/", status_code=303)
    
    # 如果有登录用户，使用用户信息
    if current_user:
        await Message.create(
            name=current_user.username,
            user=current_user,
            content=content.strip(),
            created_at=datetime.now()
        )
    else:
        # 否则使用表单提交的名称
        if not name.strip():
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


@app.get("/like/{msg_id}")
async def like_message(msg_id: int):
    """点赞留言"""
    msg = await Message.filter(id=msg_id).first()
    if msg:
        msg.likes += 1
        await msg.save()
        # 清除缓存，确保下次加载最新数据
        await cache_delete(CACHE_KEY_MESSAGES)
        return {"success": True, "likes": msg.likes}
    return {"success": False, "error": "Message not found"}

@app.post("/comment/{msg_id}")
async def add_comment(request: Request, msg_id: int, name: str = Form(None), content: str = Form(...)):
    """添加回复"""
    # 检查是否有登录用户
    token = request.cookies.get("access_token")
    current_user = None
    
    if token:
        try:
            token = token.replace("Bearer ", "")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            current_user = await User.filter(username=username).first()
        except:
            pass
    
    # 验证内容
    if not content.strip():
        return {"success": False, "error": "Content is required"}
    
    # 如果有登录用户，使用用户信息
    if current_user:
        comment_name = current_user.username
        user = current_user
    else:
        # 否则使用表单提交的名称
        if not name or not name.strip():
            return {"success": False, "error": "Name is required"}
        comment_name = name.strip()
        user = None
    
    msg = await Message.filter(id=msg_id).first()
    if msg:
        comment = await Comment.create(
            message=msg,
            name=comment_name,
            user=user,
            content=content.strip()
        )
        return {
            "success": True,
            "comment": {
                "id": comment.id,
                "name": comment.name,
                "content": comment.content,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "time_display": time_ago(comment.created_at)
            }
        }
    return {"success": False, "error": "Message not found"}

@app.get("/comments/{msg_id}")
async def get_comments(msg_id: int):
    """获取留言的回复列表"""
    comments = await Comment.filter(message_id=msg_id).order_by("created_at").all()
    return {
        "comments": [
            {
                "id": comment.id,
                "name": comment.name,
                "content": comment.content,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "time_display": time_ago(comment.created_at)
            }
            for comment in comments
        ]
    }

@app.get("/delete-comment/{comment_id}")
async def delete_comment(comment_id: int):
    """删除回复"""
    comment = await Comment.filter(id=comment_id).first()
    if comment:
        await comment.delete()
        return {"success": True}
    return {"success": False, "error": "Comment not found"}

# -------------------- 用户认证路由 --------------------
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    """用户注册"""
    # 检查用户名是否已存在
    existing_user = await User.filter(username=username).first()
    if existing_user:
        return RedirectResponse(f"/register?message=用户名已存在，请使用其他用户名&message_type=error", status_code=303)
    
    # 创建新用户
    hashed_password = get_password_hash(password)
    await User.create(
        username=username,
        password_hash=hashed_password
    )
    
    return RedirectResponse(f"/login?message=注册成功，请登录&message_type=success", status_code=303)

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """用户登录"""
    # 查找用户
    user = await User.filter(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(f"/login?message=用户名或密码错误&message_type=error", status_code=303)
    
    # 创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # 设置cookie并重定向到主页
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response

@app.get("/logout")
async def logout():
    """用户登出"""
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, message: Optional[str] = None, message_type: Optional[str] = None):
    """登录页面"""
    return templates.TemplateResponse("login.html", {"request": request, "message": message, "message_type": message_type})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, message: Optional[str] = None, message_type: Optional[str] = None):
    """注册页面"""
    return templates.TemplateResponse("register.html", {"request": request, "message": message, "message_type": message_type})

@app.get("/clear")
async def clear_messages():
    """清空留言"""
    await Message.all().delete()
    await Comment.all().delete()  # 同时清空所有回复

    deleted = await cache_delete(CACHE_KEY_MESSAGES)  # 清除缓存
    if deleted:
        print("🧹 清空缓存（删除所有留言）")
    return RedirectResponse("/", status_code=303)


# -------------------- 静态资源 --------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------- 导入模型 --------------------
from models import Message, Comment, User

# -------------------- 数据库连接 --------------------
print("DB_URL =", DATABASE_URL)

# 已通过 lifespan 管理 Tortoise 初始化与关闭（参见文件顶部 lifespan）


# -------------------- 启动提示 --------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
