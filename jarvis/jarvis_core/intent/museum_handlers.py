"""
Museum Intent Handlers - Example implementations for museum scenarios.

This module demonstrates how to define intent handlers for the museum assistant.
Each handler connects an intent to actual business logic.
"""

import logging
from typing import List, Dict, Any

from intent import IntentRouter
from ..skills.context import ServiceContext

logger = logging.getLogger(__name__)

# Create the router instance
router = IntentRouter()


# =============================================================================
# 意图1：推荐文物藏品
# =============================================================================

@router.register(
    "recommend_exhibits",
    allowed_tools=["search_resources", "get_asset_details"],
    description="根据用户兴趣推荐文物藏品"
)
async def handle_recommend_exhibits(
    keywords: str,
    features: List[str],
    count: int,
    category: str,
    ctx: ServiceContext
) -> str:
    """
    推荐文物藏品

    根据用户输入的关键词和特征，搜索并推荐相关文物。
    """
    # 构建搜索查询
    query_parts = [keywords]
    query_parts.extend(features)
    search_query = " ".join(query_parts)

    # 使用 AI 服务搜索
    try:
        ai = ctx.ai_services
        results = await ai.search_resources(search_query, limit=count)

        if not results:
            return f"抱歉，没有找到与'{keywords}'相关的{category}。"

        # 格式化结果
        response = f"为您推荐以下{len(results)}个{category}：\n"
        for i, item in enumerate(results, 1):
            name = item.get("name", "未知")
            desc = item.get("description", "")[:50]
            response += f"{i}. {name} - {desc}...\n"

        return response

    except Exception as e:
        logger.error(f"Failed to recommend exhibits: {e}")
        return f"搜索失败：{str(e)}"


# =============================================================================
# 意图2：推荐文档资料
# =============================================================================

@router.register(
    "recommend_documents",
    allowed_tools=["search_documents"],
    description="推荐文档资料"
)
async def handle_recommend_documents(
    keywords: str,
    doc_type: str,
    count: int,
    ctx: ServiceContext
) -> str:
    """
    推荐文档资料
    """
    # 这里可以连接到文档搜索服务
    # 示例实现
    return f"正在搜索'{keywords}'相关的{doc_type}文档，返回前{count}个结果..."


# =============================================================================
# 意图3：查找服务设施
# =============================================================================

@router.register(
    "find_service",
    allowed_tools=["query_facilities"],
    description="查找服务设施"
)
async def handle_find_service(
    facility_type: str,
    floor: int,
    location: str,
    ctx: ServiceContext
) -> str:
    """
    查找服务设施
    """
    # 示例：返回设施位置
    facility_names = {
        "toilet": "卫生间",
        "elevator": "电梯",
        "restaurant": "餐厅",
        "rest_area": "休息区"
    }

    name = facility_names.get(facility_type, facility_type)
    floor_info = f"{floor}楼" if floor else "各楼层"
    location_info = f"靠近{location}" if location else ""

    return f"为您找到：{name}（{floor_info}{location_info}）"


# =============================================================================
# 意图4：查看统计数据
# =============================================================================

@router.register(
    "view_statistics",
    allowed_tools=["get_statistics"],
    description="查看统计数据"
)
async def handle_view_statistics(
    stat_type: str,
    time_range: str,
    ctx: ServiceContext
) -> str:
    """
    查看统计数据
    """
    # 示例统计
    stats_map = {
        "visitor_flow": "今日人流量：1,234人次",
        "popular_exhibits": "热门展品：青铜器、瓷器、书画",
        "dwell_time": "平均停留时间：45分钟"
    }

    result = stats_map.get(stat_type, "暂无数据")
    return f"{time_range}的{result}"


# =============================================================================
# 意图5：查询展览信息
# =============================================================================

@router.register(
    "query_exhibition",
    allowed_tools=["get_exhibition_info", "get_exhibition_artifacts"],
    description="查询展览信息"
)
async def handle_query_exhibition(
    exhibition_name: str,
    detail_type: str,
    ctx: ServiceContext
) -> str:
    """
    查询展览信息
    """
    return f"正在为您查询'{exhibition_name}'的{detail_type}信息..."


# =============================================================================
# 意图6：路线规划
# =============================================================================

@router.register(
    "plan_route",
    allowed_tools=["get_route_suggestions"],
    description="规划参观路线"
)
async def handle_plan_route(
    duration: int,
    interests: List[str],
    accessibility: bool,
    start_point: str,
    ctx: ServiceContext
) -> str:
    """
    规划参观路线
    """
    interest_str = "、".join(interests) if interests else "综合"
    access_note = "无障碍" if accessibility else "常规"

    return f"""为您规划了一条{access_note}参观路线：
- 预计时长：{duration}分钟
- 主题：{interest_str}
- 起点：{start_point}
- 路线：入口→青铜器馆→瓷器馆→书画馆→出口
"""


# =============================================================================
# 意图7：通用闲聊
# =============================================================================

@router.register(
    "general_chat",
    allowed_tools=[],
    description="通用闲聊"
)
async def handle_general_chat(
    question: str,
    emotion: str,
    ctx: ServiceContext
) -> str:
    """
    通用闲聊
    """
    responses = {
        "positive": "很高兴为您服务！有什么我可以帮助您的吗？",
        "neutral": "您好，我是晓达，请问有什么可以帮您的？",
        "negative": "我理解您的困扰，请告诉我遇到了什么问题，我来帮您解决。",
        "curious": "这是个很好的问题！让我来为您解答。"
    }

    # 简单的情感响应
    response = responses.get(emotion, responses["neutral"])

    # 可以使用知识库回答
    if ctx.ai_services:
        try:
            kb_result = await ctx.ai_services.query_knowledge_base(question)
            if kb_result:
                return kb_result
        except:
            pass

    return response


# =============================================================================
# 导出路由器
# =============================================================================

def get_museum_router() -> IntentRouter:
    """获取配置好的博物馆意图路由器。"""
    return router
