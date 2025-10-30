import os
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone

from tortoise.contrib.fastapi import register_tortoise
from models import Message


# -------------------- 应用与配置 --------------------
app = FastAPI(title="简易留言板 - 数据库版")
templates = Jinja2Templates(directory="templates")

# 硬编码的 MySQL 连接字符串
DATABASE_URL = "mysql://Wang:A19356756837@52.196.78.16:3306/messageboard"
GENERATE_SCHEMAS = True


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
    if sort == "asc":
        messages = await Message.all().order_by("created_at")
    else:
        messages = await Message.all().order_by("-created_at")
    # 添加可读时间格式
    for m in messages:
        m.time_display = time_ago(m.created_at)

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
    return RedirectResponse("/", status_code=303)


@app.get("/delete/{msg_id}")
async def delete_message(msg_id: int):
    """删除留言"""
    msg = await Message.filter(id=msg_id).first()
    if msg:
        await msg.delete()
    return RedirectResponse("/", status_code=303)


@app.get("/clear")
async def clear_messages():
    """清空留言"""
    await Message.all().delete()
    return RedirectResponse("/", status_code=303)


# -------------------- 静态资源 --------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------- 数据库连接 --------------------
print("DB_URL =", DATABASE_URL)

register_tortoise(
    app,
    db_url=DATABASE_URL,
    modules={"models": ["models"]},
    generate_schemas=GENERATE_SCHEMAS,
    add_exception_handlers=True,
)


# -------------------- 启动提示 --------------------
@app.on_event("startup")
def startup_event():
    print("✅ FastAPI 留言板已启动 (容器内)。访问: http://0.0.0.0:8000")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
