"""
ResSystemTools Implementation as standalone functions.
Standard Skill Format: Stateless function interface with module-level resource management.
"""

import asyncio
from typing import List, Optional, Dict, Any

# 尝试导入上下文类型，如果环境不支持则忽略（保持纯 Python 兼容性）
try:
    from assistant.skills.context import ServiceContext
    from assistant.conversation import CallToolResult
except ImportError:
    ServiceContext = Any

# -----------------------------------------------------------------------------
# 1. 内部导入 (Relative Imports)
# ⚠️ 注意：这依赖于 SkillLoader 必须将父目录加入 sys.path，并将此目录视为包加载
# -----------------------------------------------------------------------------
from .skill import AssetSearchConfig, AssetSearchSkill, APISearchConfig

# -----------------------------------------------------------------------------
# 2. 模块级状态管理 (Module-Level Singleton)
# 使用“惰性初始化”模式，避免在文件 import 时就创建网络连接
# -----------------------------------------------------------------------------
_WORKER_INSTANCE: Optional[AssetSearchSkill] = None

def _get_worker() -> AssetSearchSkill:
    """
    获取或创建全局工作实例。
    确保只初始化一次，复用 httpx 连接池。
    如果实例已关闭，会创建新实例。
    """
    global _WORKER_INSTANCE

    # 检查实例是否需要创建或重建
    if _WORKER_INSTANCE is None:
        return _create_worker()

    # 检查 httpx 客户端是否已关闭
    try:
        if hasattr(_WORKER_INSTANCE, 'http_client') and _WORKER_INSTANCE.http_client.is_closed:
            # 客户端已关闭，创建新实例
            return _create_worker()
    except Exception:
        # 如果检查时出错，创建新实例以确保安全
        return _create_worker()

    return _WORKER_INSTANCE


def _create_worker() -> AssetSearchSkill:
    """创建新的工作实例"""
    global _WORKER_INSTANCE

    # 配置初始化
    es_config = APISearchConfig(
        base_url="http://192.168.11.11:9980",
        default_router="/gzcapi/search/search_data_by_es?p=ai",
        timeout=10.0,
        proxy=None  # 显式设为 None，避免 httpx 版本兼容性问题
    )

    config = AssetSearchConfig(
        es_config=es_config,
        knowledge_api_url="http://192.168.11.11:9980/gzcapi/search/search_by_knowledge?p=w",
        statistic_api_url="http://192.168.11.11:9980/gzcapi/search/resource_statistic",
        kg_api_url="http://192.168.11.11:9980/gzcapi/stat/graph/overview?p=ai",
        doc_api_url="http://192.168.11.11:9980/gzcapi/search/get_file_content",
        
        exhibit_search_url="http://192.168.11.11:9980/gzclabelapi/agent/search_exhibit",
        resource_search_url="http://192.168.11.11:9980/gzclabelapi/agent/search_doc",
    )

    _WORKER_INSTANCE = AssetSearchSkill(config)
    return _WORKER_INSTANCE

# -----------------------------------------------------------------------------
# 3. 公开工具函数 (Public Tool Functions)
# 这些函数是无状态的入口，直接被 SkillLoader 扫描和注册
# -----------------------------------------------------------------------------

async def search_assets(
    query: str, 
    types: Optional[List[str]] = None, 
    resource_types: Optional[List[str]] = None, 
    # **kwargs 用于接收可能传入的 ctx 或其他由 Loader 注入的参数
    **kwargs 
) -> CallToolResult:
    """
    Search for internal assets using Enterprise Search.
    
    Args:
        query: The search keywords.
        types: Specific asset types to filter.
        resource_types: Specific resource categories.
    """
    worker = _get_worker()
    
    # 从 kwargs 中提取 Loader 可能注入的 ctx，如果没有则为 None
    ctx = kwargs.get('ctx')
    
    return await worker.search_assets(
        query, 
        search_types=types, 
        resource_types=resource_types, 
        ctx=ctx
    )

# ... (前面的导入和 _get_worker 保持不变) ...

async def recommend_assets(
    query: str,
    intent_targets: Optional[List[str]] = None,
    # V2 Exhibits parameters
    exhibit_ids: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    # V2 Resources parameters
    file_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    # V1 Assets parameters
    resource_types: Optional[List[str]] = None,
    top_k: int = 5,
    **kwargs
) -> CallToolResult:
    """
    [多路召回推荐] Recommend assets based on user intent analysis.
    Aggregates results from V2 Exhibits, V2 Resources, and V1 Assets.

    Args:
        query: The search query
        intent_targets: Optional intent target types for filtering
        exhibit_ids: Optional list of specific exhibit IDs for precise search (V2 Exhibits)
        filters: Optional filter conditions for exhibits, e.g., {"era": "战国", "material": "青铜"} (V2 Exhibits)
        file_ids: Optional list of specific file IDs for precise search (V2 Resources)
        tags: Optional list of tags to filter resource results (V2 Resources)
        resource_types: Optional resource type filter for V1 assets, e.g., ["图片", "视频"] (V1 Assets)
        top_k: Maximum number of results to return from each search source (default: 5)
    """
    from .schema import APISearchResultData

    worker = _get_worker()
    ctx = kwargs.get('ctx')

    # Path A: 藏品智能检索 (V2)
    task_exhibits = worker.search_exhibits_v2(
        query=query,
        exhibit_ids=exhibit_ids,
        filters=filters,
        top_k=top_k,
        ctx=ctx
    )

    # Path B: 文档/资源智能检索 (V2)
    task_resources = worker.search_resources_v2(
        query=query,
        file_ids=file_ids,
        tags=tags,
        top_k=top_k,
        ctx=ctx
    )

    # Path C: 资产/专题库精确检索 (V1)
    task_assets = worker.search_assets(
        query,
        search_types=["资产", "专题库"],
        resource_types=resource_types,
        ctx=ctx
    )

    # 并发执行
    results = await asyncio.gather(task_exhibits, task_resources, task_assets, return_exceptions=True)

    # 解包结果
    exhibits_res = results[0] if isinstance(results[0], CallToolResult) else None
    resources_res = results[1] if isinstance(results[1], CallToolResult) else None
    assets_res = results[2] if isinstance(results[2], CallToolResult) else None

    # 1. 提取原始数据到统一的候选列表（保留原始 item 用于最后返回）
    candidates = []  # 用于 rerank 的候选列表
    seen_ids = set()

    # 从 V2 Exhibits 提取
    if exhibits_res and exhibits_res.content:
        for item in exhibits_res.content:
            if item.data and isinstance(item.data, dict):
                exhibit_items = item.data.get('exhibit_list', [])
                for ex in exhibit_items:
                    uid = str(ex.get('exhibit_id') or ex.get('id'))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        candidates.append({
                            "content": ex.get('content', ''),
                            "target_list": "exhibit_list",
                            "original_item": ex
                        })

    # 从 V2 Resources 提取
    if resources_res and resources_res.content:
        for item in resources_res.content:
            if item.data and isinstance(item.data, dict):
                file_items = item.data.get('resource_file_list', [])
                for f in file_items:
                    uid = str(f.get('resource_file_id') or f.get('id'))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        candidates.append({
                            "content": f.get('content', ''),
                            "target_list": "resource_file_list",
                            "original_item": f
                        })

    # 从 V1 Assets 提取
    if assets_res and assets_res.content:
        for item in assets_res.content:
            if item.data and isinstance(item.data, dict):
                # resource_list
                for r in item.data.get('resource_list', []):
                    uid = str(r.get('resource_id') or r.get('id'))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        candidates.append({
                            "content": f"{r.get('resource_name', '')} {r.get('desc', '')}",
                            "target_list": "resource_list",
                            "original_item": r
                        })
                # library_list
                for lib in item.data.get('library_list', []):
                    uid = str(lib.get('library_id') or lib.get('id'))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        candidates.append({
                            "content": f"{lib.get('library_name', '')} {lib.get('desc', '')}",
                            "target_list": "library_list",
                            "original_item": lib
                        })
                # resource_file_list
                for rf in item.data.get('resource_file_list', []):
                    uid = str(rf.get('resource_file_id') or rf.get('id'))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        candidates.append({
                            "content": rf.get('content', ''),
                            "target_list": "resource_file_list",
                            "original_item": rf
                        })

    # 2. 混合重排序
    reranked_candidates = []
    if ctx and ctx.reranker and candidates:
        try:
            reranked_candidates = await ctx.reranker.rank_objects(
                query=query,
                items=candidates,
                key_func=lambda x: x['content'][:300],
                top_k=10
            )
        except Exception as e:
            logger.warning(f"Rerank failed: {e}, using original order")
            reranked_candidates = candidates[:10]
    else:
        reranked_candidates = candidates[:10]

    if not reranked_candidates:
        return CallToolResult.from_text(f"抱歉，没有找到与\"{query}\"相关的推荐资源。")

    # 3. 重新分配到 APISearchResultData 的四个列表
    final_data = APISearchResultData()

    for cand in reranked_candidates:
        target_list = cand['target_list']
        original_item = cand['original_item']
        if target_list == 'exhibit_list':
            final_data.exhibit_list.append(original_item)
        elif target_list == 'resource_list':
            final_data.resource_list.append(original_item)
        elif target_list == 'library_list':
            final_data.library_list.append(original_item)
        elif target_list == 'resource_file_list':
            final_data.resource_file_list.append(original_item)

    # 4. 构造视图文本
    view_lines = [f"为您精选了以下与\"{query}\"相关的内容：\n"]

    if final_data.exhibit_list:
        view_lines.append(f"\n🏛️ 藏品 ({len(final_data.exhibit_list)})")
        for ex in final_data.exhibit_list[:5]:
            name = ex.get('exhibit_name') or ex.get('name') or '未知'
            view_lines.append(f"  - {name}")

    if final_data.resource_list:
        view_lines.append(f"\n📦 资产 ({len(final_data.resource_list)})")
        for r in final_data.resource_list[:5]:
            name = r.get('resource_name') or '未知'
            view_lines.append(f"  - {name}")

    if final_data.library_list:
        view_lines.append(f"\n📚 专题库 ({len(final_data.library_list)})")
        for lib in final_data.library_list[:5]:
            name = lib.get('library_name') or '未知'
            view_lines.append(f"  - {name}")

    if final_data.resource_file_list:
        view_lines.append(f"\n📄 文档 ({len(final_data.resource_file_list)})")
        for f in final_data.resource_file_list[:5]:
            name = f.get('file_name') or '未知'
            view_lines.append(f"  - {name}")

    return CallToolResult.from_artifact(
        view="\n".join(view_lines),
        data=final_data.model_dump(),
        type="dataset"
    )

async def retrieve_knowledge(
    query: str,
    **kwargs
) -> CallToolResult:
    """
    Retrieve associated knowledge graph data.

    Args:
        query: The knowledge query to search for.
    """
    worker = _get_worker()
    ctx = kwargs.get('ctx')

    return await worker.retrieve_knowledge(query, ctx=ctx)

async def search_resource_statistic(
    statistic_type: str,
    start_at: str = 'None',
    end_at: str = 'None',
    **kwargs
) -> CallToolResult:
    """
    Query resource statistics from the digital asset system.

    Args:
        statistic_type: The type of statistic to query. Valid values:
            - 'resource_count_by_type': Asset count by type
            - 'resource_file_count_by_type': File count by type
            - 'resource_file_count_by_ext': File count by format
            - 'resource_library_count': Total assets and libraries
            - 'resource_top': Top 5 accessed/downloaded/applied assets
            - 'apply_count': Total application count
            - 'resource_download_count': Total download count
            - 'everything_count': Image training library count
            - 'face_count': Face training library count
            - 'ocr_type': OCR text category count
            - 'resource_growth': Asset growth count
        start_at: Start date for statistics (format: YYYY-MM-DD)
        end_at: End date for statistics (format: YYYY-MM-DD)

    Examples:
        Get total asset count: search_resource_statistic(statistic_type='resource_library_count')
        Get top assets: search_resource_statistic(statistic_type='resource_top')
        Get file count by format: search_resource_statistic(statistic_type='resource_file_count_by_ext')
    """
    worker = _get_worker()
    return await worker.search_resource_statistic(
        statistic_type=statistic_type,
        start_at=start_at,
        end_at=end_at
    )

async def search_kg_overview(
    **kwargs
) -> CallToolResult:
    """
    Query knowledge graph overview statistics.

    Returns comprehensive statistics about the knowledge graph including:
    - Entity types and counts
    - Relationship types and counts
    - Node and relationship properties
    - Total node and relationship counts
    - Top entities by mention/association count
    - Last update information

    Examples:
        Get KG overview: search_kg_overview()
    """
    worker = _get_worker()
    return await worker.search_kg_overview()

async def search_doc(
    resource_file_ids,
    token: Optional[str] = None,
    **kwargs
) -> CallToolResult:
    """
    Query document content by resource file IDs.

    Args:
        resource_file_ids: Single file ID string or list of file IDs to query
        token: Optional authentication token for accessing restricted content

    Returns:
        Document content including file information and content text.
        Unauthorized documents will show a message requesting permission.

    Examples:
        Single file: search_doc(resource_file_ids='file123')
        Multiple files: search_doc(resource_file_ids=['file123', 'file456'])
        With auth: search_doc(resource_file_ids='file123', token='user_token')
    """
    worker = _get_worker()
    return await worker.search_doc(
        resource_file_ids=resource_file_ids,
        token=token
    )

# -----------------------------------------------------------------------------
# V2 API: 藏品和文档智能检索接口
# -----------------------------------------------------------------------------

async def search_exhibits_v2(
    query: str,
    exhibit_ids: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    **kwargs
) -> CallToolResult:
    """
    [V2 API] Search for museum exhibits (physical artifacts) using intelligent retrieval.

    This is the NEW version API that provides better search results for physical artifacts,
    exhibit metadata, and object descriptions.

    Args:
        query: The search keyword for exhibits
        exhibit_ids: Optional list of specific exhibit IDs for precise search
        filters: Optional filter conditions (e.g., era, material, category)
        top_k: Maximum number of results to return (default: 5)

    When to use V2 vs V1:
        - Use this V2 API when searching for PHYSICAL ARTIFACTS, exhibits, museum objects
        - Use V1 API (search_assets with types=["资产"]) for general digital asset management

    Examples:
        Basic search: search_exhibits_v2(query="青铜器")
        With filters: search_exhibits_v2(query="剑", filters={"era": "战国"})
        Multiple IDs: search_exhibits_v2(query="玉器", exhibit_ids=["id1", "id2"])
    """
    worker = _get_worker()
    ctx = kwargs.get('ctx')

    return await worker.search_exhibits_v2(
        query=query,
        exhibit_ids=exhibit_ids,
        filters=filters,
        top_k=top_k,
        ctx=ctx
    )

async def search_resources_v2(
    query: str,
    file_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    top_k: int = 5,
    **kwargs
) -> CallToolResult:
    """
    [V2 API] Search for digital resources and documents using intelligent retrieval.

    This is the NEW version API that provides better search results for documents,
    research papers, and detailed textual content with LLM-generated summaries.

    Args:
        query: The search keyword for resources
        file_ids: Optional list of specific file IDs for precise search
        tags: Optional list of tags to filter results
        top_k: Maximum number of results to return (default: 5)

    When to use V2 vs V1:
        - Use this V2 API when searching for DOCUMENT CONTENT, research papers, knowledge
        - Use V1 API (retrieve_knowledge) for knowledge graph-based question answering
        - Use V1 API (search_assets) for structured asset file management

    Examples:
        Basic search: search_resources_v2(query="青铜器铸造工艺")
        With tags: search_resources_v2(query="汉代", tags=["历史", "考古"])
        Specific files: search_resources_v2(query="马蹄金", file_ids=["file1", "file2"])
    """
    worker = _get_worker()
    ctx = kwargs.get('ctx')

    return await worker.search_resources_v2(
        query=query,
        file_ids=file_ids,
        tags=tags,
        top_k=top_k,
        ctx=ctx
    )

# -----------------------------------------------------------------------------
# 4. 可选：清理钩子
# 如果 Loader 支持在卸载时调用特定函数，可以定义此函数
# -----------------------------------------------------------------------------
async def _shutdown():
    """Internal cleanup hook."""
    global _WORKER_INSTANCE
    if _WORKER_INSTANCE and hasattr(_WORKER_INSTANCE, 'close'):
        await _WORKER_INSTANCE.close()
    _WORKER_INSTANCE = None