import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.chat import router as chat_router
from server.api.graph import router as graph_router
from server.api.task import router as task_router  # 引入拆分好的 task 模块
from server.api.config import router as config_router  # 引入刚刚创建的 config_router

app = FastAPI(title="PurrCat API System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(graph_router)
app.include_router(task_router)  # 挂载子路由
app.include_router(config_router)  # 挂载配置路由

@app.get("/")
def ping():
    return {"message": "Meow! PurrCat Backend is running."}

if __name__ == "__main__":
    uvicorn.run("server.backend:app", host="0.0.0.0", port=8000, reload=True)