"""
文博助手主程序
"""

import os
import sys
import logging
import argparse
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('museum_assistant.log', encoding='utf-8')
    ],
    encoding='utf-8'
)

# 将 httpx 的日志级别设置为 WARNING（仅警告和错误才打印）
logging.getLogger("httpx").setLevel(logging.WARNING)

# 建议同时屏蔽 httpcore（httpx 的底层库），它有时也会打印大量日志
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

load_dotenv(override=True)

agent = None


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    from assistant.config.loader import ConfigLoader
    from assistant.db import configure_db
    from assistant.core import MicroAgent
    from assistant.api.routes import create_router, set_agent
    from assistant.api.middleware import AuthContextMiddleware
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global agent

        logger.info("Starting Museum Assistant...")
        try:
            config_path = os.getenv('ASSISTANT_CONFIG', 'assistant_config.yaml')
            config = ConfigLoader(config_path)

            # 配置数据库
            db = configure_db(
                local_db_path=config.database.local_db_path,
                remote_db_url=config.database.remote_db_url,
                remote_db_api_key=config.database.remote_db_api_key,
                use_remote=config.database.use_remote
            )

            # 初始化数据库连接
            await db.initialize()
            logger.info("Database initialized successfully")

            # 认证服务是可选的，仅在启用时初始化
            if os.getenv('ENABLE_AUTH', 'false').lower() == 'true':
                try:
                    from assistant.auth import get_auth_service
                    _ = get_auth_service()
                    logger.info("Authentication service initialized (optional)")
                except ImportError as e:
                    logger.warning(f"Auth module not available: {e}")

            agent = MicroAgent(config_path=config_path)
            set_agent(agent)
            logger.info("Museum Assistant initialized successfully")

            yield

        except Exception as e:
            logger.error(f"Failed to initialize application: {e}", exc_info=e)
            raise

        logger.info("Shutting down Museum Assistant...")
        if agent:
            try:
                await agent.shutdown_async()
            except Exception as e:
                logger.error(f"Error during agent shutdown: {e}", exc_info=e)

        # 关闭数据库连接
        from assistant.db import shutdown_db
        await shutdown_db()
        logger.info("Shutdown complete")

    app = FastAPI(
        title="Museum Assistant",
        description="文博助手 - 基于智能代理的博物馆问答服务",
        version="1.0.0",
        lifespan=lifespan
    )
    
    app.add_middleware(AuthContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Log 422 details to pinpoint which parameter failed validation.
        logger.warning(
            "422 ValidationError: %s %s | query=%s | errors=%s",
            request.method,
            request.url.path,
            dict(request.query_params),
            exc.errors(),
        )
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    # 主路由
    router = create_router()
    app.include_router(router)
    logger.info("Main routes registered")

    # 认证路由（可选，仅在启用时加载）
    if os.getenv('ENABLE_AUTH', 'false').lower() == 'true':
        try:
            from assistant.api.auth_routes import create_auth_router
            auth_router = create_auth_router()
            app.include_router(auth_router)
            logger.info("Authentication routes registered")
        except ImportError as e:
            logger.warning(f"Auth routes not available: {e}")

    @app.get("/")
    async def root():
        features = [
            "会话恢复",
            "事件驱动",
            "事件回放",
            "断线重连",
            "远端数据库",
            "多用户支持"
        ]

        response = {
            "name": "Museum Assistant",
            "version": "1.0.0",
            "status": "running",
            "features": features
        }

        # 仅在启用认证时显示认证端点
        if os.getenv('ENABLE_AUTH', 'false').lower() == 'true':
            response["authentication"] = {
                "enabled": True,
                "register": "POST /api/v1/auth/register",
                "login": "POST /api/v1/auth/login",
                "refresh": "POST /api/v1/auth/refresh",
                "user_info": "GET /api/v1/auth/me"
            }
        else:
            response["authentication"] = {
                "enabled": False,
                "note": "Authentication is handled externally. Set ENABLE_AUTH=true to enable built-in auth."
            }

        return response

    return app


app = create_app()


def main():
    """运行应用"""
    parser = argparse.ArgumentParser(description="Museum Assistant Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8400, help="Port to bind (default: 8400)")
    parser.add_argument("--config", type=str, default="assistant_config.yaml", help="Config file path (default: assistant_config.yaml)")
    
    args = parser.parse_args()
    
    # 更新全局配置路径
    os.environ['ASSISTANT_CONFIG'] = args.config
    os.environ['ASSISTANT_PORT'] = str(args.port)
    os.environ['ASSISTANT_HOST'] = args.host

    logger.info(f"Starting server on {args.host}:{args.port} with config {args.config}")
    uvicorn.run(
        "assistant.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info"
    )


def run_with_args(host="0.0.0.0", port=8400, config="assistant_config.yaml"):
    """使用指定参数运行应用，用于模块导入场景"""
    # 更新全局配置路径
    os.environ['ASSISTANT_CONFIG'] = config
    os.environ['ASSISTANT_PORT'] = str(port)
    os.environ['ASSISTANT_HOST'] = host

    logger.info(f"Starting server on {host}:{port} with config {config}")
    uvicorn.run(
        "assistant.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
