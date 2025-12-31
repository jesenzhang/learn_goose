from contextlib import asynccontextmanager
from fastapi import FastAPI
from goose.system import boot, shutdown
from goose.config import SystemConfig
from goose.server import endpoints

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Boot System (Server Mode)
    # 通常从环境变量读取配置
    config = SystemConfig() 
    print(f"🚀 Goose Server starting with DB: {config.DB_URL}")
    
    await boot(config)
    
    yield
    
    print("👋 Goose Server shutting down...")
    await shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(endpoints.router)