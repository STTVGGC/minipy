import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
from datetime import datetime
from typing import List, Dict



# -------------------- 应用与配置 --------------------
app = FastAPI(title="简易留言板")

templates = Jinja2Templates(directory="templates")
DATA_FILE = "messages.json"

# -------------------- 数据存取函数 --------------------
def load_messages() -> List[Dict]:
    """读取留言列表"""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_messages(messages: List[Dict]):
    """保存留言列表"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


# -------------------- 路由与逻辑 --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """显示留言板主页"""
    messages = load_messages()
    messages = sorted(messages, key=lambda m: m["time"], reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "messages": messages})


@app.post("/submit")
async def submit_message(name: str = Form(...), content: str = Form(...)):
    """提交新留言"""
    if not name.strip() or not content.strip():
        return RedirectResponse("/", status_code=303)

    messages = load_messages()
    messages.append({
        "name": name.strip(),
        "content": content.strip(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_messages(messages)
    return RedirectResponse("/", status_code=303)


@app.get("/clear")
async def clear_messages():
    """清空留言"""
    save_messages([])
    return RedirectResponse("/", status_code=303)


# -------------------- 静态资源 --------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------- 启动提示 --------------------
@app.on_event("startup")
def startup_event():
    print("✅ FastAPI 简易留言板已启动：http://127.0.0.1:8000")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000,reload=True)