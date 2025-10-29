import os
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime

from tortoise.contrib.fastapi import register_tortoise
from models import Message


# -------------------- 应用与配置 --------------------
app = FastAPI(title="简易留言板 - 数据库版")
templates = Jinja2Templates(directory="templates")

# Read DB config from environment (default to local sqlite for easy Docker smoke-test)
# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite://db.sqlite3")
# GENERATE_SCHEMAS = os.getenv("GENERATE_SCHEMAS", "true").lower() in ("1", "true", "yes")

# 硬编码的 MySQL 连接字符串
DATABASE_URL = "mysql://Wang:A19356756837@52.196.78.16:3306/messageboard"
GENERATE_SCHEMAS = True


# -------------------- 路由与逻辑 --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """显示留言板主页"""
    messages = await Message.all().order_by("-created_at")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "messages": messages
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
