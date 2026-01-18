"""
文博助手主程序
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('museum_assistant.log', encoding='utf-8')
    ],
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

agent = None


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    from assistant.config.loader import ConfigLoader
    from assistant.db.factory import create_database
    from assistant.core.agent import MicroAgent
    from assistant.api.routes import create_router, set_agent
    from assistant.api.middleware import AuthContextMiddleware
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global agent

        logger.info("Starting Museum Assistant...")
        try:
            config_path = os.getenv('ASSISTANT_CONFIG', r'D:\WorkSpace\learn_goose\assistant\assistant_config.yaml')
            config = ConfigLoader(config_path)

            # 配置数据库（使用工厂方法）
            from assistant.db.factory import create_database

            try:
                db = await create_database(config.database)
                # 设置全局数据库实例（不使用 configure_db，因为已经初始化了）
                from assistant.db import set_db_instance
                set_db_instance(db)
                logger.info("Database initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}", exc_info=e)
                # 提供清晰的错误信息和解决建议
                if "health check failed" in str(e):
                    logger.error("\n" + "="*60)
                    logger.error("数据库健康检查失败！")
                    logger.error("="*60)
                    logger.error("解决方法：")
                    logger.error("1. 检查远程数据库是否可访问")
                    logger.error("2. 或设置环境变量切换到本地模式：")
                    logger.error("   export USE_REMOTE_DB=false")
                    logger.error("="*60)
                raise

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
    port = int(os.getenv('ASSISTANT_PORT', 8400))
    host = os.getenv('ASSISTANT_HOST', '0.0.0.0')

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "assistant.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
