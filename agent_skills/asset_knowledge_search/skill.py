import json
import httpx
import logging
import asyncio
from typing import List, Optional, Callable, Awaitable, Dict, Any,Union
from pydantic import BaseModel
from assistant.conversation import CallToolResult
from assistant.skills.context import ServiceContext 

# 假设这些模块在同一包下，根据实际情况调整 import
from .search import APISearch, EsQuery, APISearchConfig
from .schema import (
    APISearchResultData, FileItem, ResourceItem, LibraryItem, ASSET_TYPE_MAP, RESOURCE_TYPE_MAP, Document,
    ResourceStatisticData, KGOverviewData, DocSearchResult,
    ExhibitItem, ResourceV2Item, ExhibitSearchResult, ResourceSearchResult
)
from .formater import ResultFormatter

logger = logging.getLogger(__name__)

# --- 基础配置 ---
class AssetSearchConfig(BaseModel):
    # V1 API 配置 (原有 ES 搜索)
    es_config: Optional[APISearchConfig] = None
    knowledge_api_url: str = "http://192.168.11.11:9980/gzcapi/search/search_by_knowledge?p=w"
    statistic_api_url: str = "http://192.168.11.11:9980/gzclabelapi/search/resource_statistic"
    kg_api_url: str = "http://192.168.11.11:9980/gzclabelapi/stat/graph/overview?p=ai"
    doc_api_url: str = "http://192.168.11.11:9980/gzclabelapi/search/get_file_content"

    # V2 API 配置 (新增：藏品和文档智能检索)
    exhibit_search_url: str = "http://192.168.11.11:9980/gzclabelapi/agent/search_exhibit"
    resource_search_url: str = "http://192.168.11.11:9980/gzclabelapi/agent/search_doc"

    rerank_threshold: float = 0.4
    default_top_k: int = 10
    
class AssetSearchSkill:
    name = "asset_knowledge_search"
    description = "用于在内部系统中搜索资产、文件和专题库知识"

    def __init__(self, config: AssetSearchConfig, http_client: httpx.AsyncClient = None):
        """
        :param config: 配置对象
        :param http_client: 可选的外部注入的 httpx client（用于复用连接池）
        """
        self.config = config
        self.es_search = APISearch(config=config.es_config)
        # 使用注入的 http_client，或者创建新的（用于兼容）
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)

    @classmethod
    def apply_config(cls, skill_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用外部配置覆盖默认配置。

        Args:
            skill_config: 来自 assistant_config.yaml 中 skills_config 下的 config 字段

        Returns:
            处理后的配置字典，用于创建 AssetSearchConfig 和 APISearchConfig

        配置结构示例:
            es_config:
              base_url: "http://192.168.11.11:9980"
              default_router: "/gzcapi/search/search_data_by_es?p=ai"
              timeout: 10.0
              proxy: None
            knowledge_api_url: "http://192.168.11.11:9980/gzcapi/search/search_by_knowledge?p=w"
            statistic_api_url: "http://192.168.11.11:9980/gzcapi/search/resource_statistic"
            kg_api_url: "http://192.168.11.11:9980/gzcapi/stat/graph/overview?p=ai"
            doc_api_url: "http://192.168.11.11:9980/gzcapi/search/get_file_content"
            exhibit_search_url: "http://192.168.11.11:9980/gzclabelapi/agent/search_exhibit"
            resource_search_url: "http://192.168.11.11:9980/gzclabelapi/agent/search_doc"
        """
        if not skill_config:
            return {}

        # 直接返回配置，由 impl.py 中的 _create_worker 使用
        return skill_config

    async def close(self):
        await self.es_search.close()
        await self.http_client.aclose()

    # --- 辅助方法 ---
    def _get_type_ids(self, type_names: List[str], mapping: Dict[str, int], default_all: List[int]) -> List[int]:
        if not type_names or 'None' in type_names:
            return default_all
        # 反转映射：名称 -> ID
        name_to_id = {v: k for k, v in mapping.items()}
        return [name_to_id[name] for name in type_names if name in name_to_id]

    async def _search_es_wrapper(self, text: str, search_type: int, resource_type: Optional[int] = None) -> Dict:
        """封装 ES 搜索调用"""
        try:
            api_query = EsQuery(text=text, search_type=search_type, resource_type=resource_type)
            response = await self.es_search.search_async(api_query.model_dump())
            if response.get('status') == 1:
                return response.get('data', {'total': 0, 'list': []})
        except Exception as e:
            logger.error(f"ES Search Error: {e}")
        return {'total': 0, 'list': []}

    async def _apply_rerank(self, query: str, data: APISearchResultData, ctx: ServiceContext) -> APISearchResultData:
        """
        统一的重排序逻辑处理
        利用 ServiceContext 中的 Reranker
        """
        if not ctx or not ctx.reranker:
            return data

        threshold = self.config.rerank_threshold

        try:
            # 1. 专题库重排
            if data.library_list:
                # 使用 BaseReranker 的 rank_objects 方法
                # 此方法会自动处理 Document 转换、Rerank 和 top_k 截断
                ranked_libs = await ctx.reranker.rank_objects(
                    query=query,
                    items=data.library_list,
                    key_func=lambda x: x.library_name,
                    threshold=threshold,
                    top_k=len(data.library_list) # 这里先全排，或者限制数量
                )
                data.library_list = ranked_libs

            # 2. 资产重排
            if data.resource_list:
                ranked_resources = await ctx.reranker.rank_objects(
                    query=query,
                    items=data.resource_list,
                    key_func=lambda x: x.resource_name,
                    threshold=threshold,
                    top_k=len(data.resource_list)
                )
                data.resource_list = ranked_resources

            # 3. 文件重排
            if data.resource_file_list:
                # 构造用于 rerank 的文本：文件名 + 内容摘要
                key_func = lambda x: f"{x.file_name}\n{x.content[:200]}"
                
                ranked_files = await ctx.reranker.rank_objects(
                    query=query,
                    items=data.resource_file_list,
                    key_func=key_func,
                    threshold=threshold,
                    top_k=len(data.resource_file_list)
                )
                data.resource_file_list = ranked_files

        except Exception as e:
            logger.error(f"Rerank failed: {e}. Returning original results.")
        
        return data

    # --- 核心功能：基础搜索 (Tool Implementation) ---
    async def search_assets(self, query: str, search_types: List[str] = None, resource_types: List[str] = None, ctx: ServiceContext = None) -> CallToolResult:
        """
        [Tool] 执行多维度资产搜索
        """
        logger.info(f"🔎 [AssetSearch] Searching assets: {query}, types={search_types}")
        
        search_type_ids = self._get_type_ids(search_types, ASSET_TYPE_MAP, [1, 2, 3])
        resource_type_ids = self._get_type_ids(resource_types, RESOURCE_TYPE_MAP, [1, 2, 3, 4, 5, 6])

        result_data = APISearchResultData()
        tasks = []

        # 构建并发任务
        if 2 in search_type_ids:  # 资产文件
            for rt in resource_type_ids:
                tasks.append(self._search_es_wrapper(query, 2, rt))
        if 1 in search_type_ids:  # 资产
            tasks.append(self._search_es_wrapper(query, 1))
        if 3 in search_type_ids:  # 专题库
            tasks.append(self._search_es_wrapper(query, 3))

        results = await asyncio.gather(*tasks)

        # 合并结果
        for res in results:
            data_list = res.get('list', [])
            if not data_list: continue
            
            sample = data_list[0]
            if 'resource_file_id' in sample:
                result_data.resource_file_list.extend([FileItem.model_validate(x) for x in data_list])
            elif 'resource_id' in sample:
                result_data.resource_list.extend([ResourceItem.model_validate(x) for x in data_list])
            elif 'library_id' in sample:
                result_data.library_list.extend([LibraryItem.model_validate(x) for x in data_list])

        # Rerank
        if ctx and ctx.reranker:
            result_data = await self._apply_rerank(query, result_data, ctx)

        # 格式化输出
        view_text = ResultFormatter.format_result(result_data, query)
        
        # 构造 CallToolResult
        return CallToolResult.from_artifact(
            view=view_text,
            data=result_data.model_dump(), # 传递完整数据供前端渲染
            type="dataset"
        )

    # --- 核心功能：推荐 (Tool Implementation) ---
    async def recommend_assets(self, query: str, intent_targets: List[str] = ['图片','视频','文档','音频','3D','其他','专题库','资产','藏品'], ctx: ServiceContext = None) -> CallToolResult:
        """
        [Tool] 资产推荐逻辑
        """
        logger.info(f"🔎 [AssetSearch] Recommending assets: {query}")
        
        # 清洗关键词
        clean_query = query.replace('推荐', '').replace('文件', '').replace('资产', '').strip()
        search_keywords = list(set(clean_query.replace(' ', ',').split(',')))
        final_query = ",".join([k for k in search_keywords if k and k not in (intent_targets or [])])

        # 确定搜索范围
        target_types = intent_targets if intent_targets else []
        if '文件' in target_types: 
            # 假设 intent_targets 是可变列表，如果它是 tuple 需要先转 list
            if isinstance(target_types, list):
                if '文件' in target_types: target_types.remove('文件')
            
        search_types_arg = []
        if not target_types or 'None' in target_types: search_types_arg = [] 
        elif '专题库' in target_types: search_types_arg = ['专题库']
        elif '资产' in target_types: search_types_arg = ['资产']
        else: search_types_arg = ['专题库', '资产']

        # 临时方案：直接复用代码逻辑
        search_type_ids = self._get_type_ids(search_types_arg, ASSET_TYPE_MAP, [1, 2, 3])
        resource_type_ids = self._get_type_ids(target_types, RESOURCE_TYPE_MAP, [1, 2, 3, 4, 5, 6])
        
        result_data = APISearchResultData()
        tasks = []
        
        if 2 in search_type_ids:
            for rt in resource_type_ids:
                tasks.append(self._search_es_wrapper(final_query, 2, rt))
        if 1 in search_type_ids:
            tasks.append(self._search_es_wrapper(final_query, 1))
        if 3 in search_type_ids:
            tasks.append(self._search_es_wrapper(final_query, 3))
            
        results = await asyncio.gather(*tasks)
        for res in results:
            data_list = res.get('list', [])
            if not data_list: continue
            sample = data_list[0]
            if 'resource_file_id' in sample:
                result_data.resource_file_list.extend([FileItem.model_validate(x) for x in data_list])
            elif 'resource_id' in sample:
                result_data.resource_list.extend([ResourceItem.model_validate(x) for x in data_list])
            elif 'library_id' in sample:
                result_data.library_list.extend([LibraryItem.model_validate(x) for x in data_list])
        
        # Rerank
        if ctx and ctx.reranker:
            result_data = await self._apply_rerank(final_query, result_data, ctx)

        view_text = ResultFormatter.format_result(result_data, final_query)
 
        return CallToolResult.from_artifact(
            view=view_text,
            data=result_data.model_dump(),
            type="dataset"
        )

    # --- 核心功能：知识检索 (Tool Implementation) ---
    async def retrieve_knowledge(self, query: str, ctx: ServiceContext = None) -> CallToolResult:
        """
        [Tool] 检索系统内部知识库
        """
        logger.info(f"🔎 [AssetSearch] Retrieving knowledge: {query}")
        
        try:
            resp = await self.http_client.post(self.config.knowledge_api_url, json={"keyword": query})
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            logger.error(f"Knowledge API Error: {e}")
            return CallToolResult.from_text(f"Error retrieving knowledge: {str(e)}")

        if result.get('status') != 1:
            return CallToolResult.from_text("未检索到相关知识")

        knowledge_data = result.get('data', {})
        file_list = knowledge_data.get('file_list', []) or []
        data_list = knowledge_data.get('data', []) or []

        # 建立文件索引
        file_map = {f['FileId']: f for f in file_list}
        merged_files: Dict[str, FileItem] = {}

        # 聚合分段内容
        for chunk in data_list:
            fid = chunk.get("resource_file_id")
            if not fid or fid not in file_map: continue
            
            file_info = file_map[fid]
            text = chunk.get("text", "")
            
            if fid not in merged_files:
                merged_files[fid] = FileItem(
                    resource_file_id=fid,
                    resource_id=file_info.get("ResourceId", ""),
                    resource_type=3, # 默认为文档
                    file_name=file_info.get("FileName", ""),
                    content=text,
                    score=0
                )
            else:
                merged_files[fid].content += "\n" + text

        final_data = APISearchResultData(resource_file_list=list(merged_files.values()))

        # Rerank
        if ctx and ctx.reranker:
            final_data = await self._apply_rerank(query, final_data, ctx)

        view_text = ResultFormatter.format_result(final_data, query)

        return CallToolResult.from_artifact(
            view=view_text,
            data=final_data.model_dump() or {},
            type="dataset"
        )
    
    
    async def search_resource_statistic(self, statistic_type: str = '', start_at='None', end_at='None') -> CallToolResult:
        """
        [Tool] 查询资源统计数据

        支持的统计类型:
            resource_count_by_type         按资产类型统计资产数
            resource_file_count_by_type   按资产类型统计资产文件数
            resource_file_count_by_ext     按文件格式统计资产文件数
            resource_library_count           资产、专题库总数
            resource_top                         资产访问、下载、申请 top5
            apply_count                          资产利用申请次数
            resource_download_count     资产下载次数
            everything_count                   图像训练库数量
            face_count                             人脸训练库数量
            ocr_type                                OCR识别中的文字类别
            resource_growth                 资产增长数
        """
        logger.info(f"📊 [AssetSearch] Querying resource statistics: type={statistic_type}, {start_at} to {end_at}")

        params = {'p': 'w', 'statistic_type': statistic_type, 'start_at': start_at, 'end_at': end_at}
        try:
            resp = await self.http_client.get(self.config.statistic_api_url, params=params)
            resp.raise_for_status()
            response = resp.json()
        except Exception as e:
            logger.error(f"Statistic API Error: {e}")
            return CallToolResult.from_text(f"查询统计数据时出错: {str(e)}")

        if response.get('status') != 1:
            return CallToolResult.from_text(f"未获取到统计数据: {response.get('msg', 'Unknown error')}")

        # 解析响应数据
        data_dict = response.get('data', {})
        try:
            statistic_data = ResourceStatisticData.model_validate(data_dict)
        except Exception as e:
            logger.error(f"Failed to parse statistic data: {e}")
            return CallToolResult.from_text(f"解析统计数据时出错: {str(e)}")

        # 格式化输出
        view_text = ResultFormatter.format_resource_statistic(statistic_data, statistic_type)

        return CallToolResult.from_artifact(
            view=view_text,
            data=statistic_data.model_dump() or {},
            type="dataset"
        )
    
    
    
    # --- 核心功能：知识图谱统计 (Tool Implementation) ---

    async def search_kg_overview(self) -> CallToolResult:
        """
        [Tool] 查询知识图谱数据统计总览
        """
        logger.info("🕸️ [AssetSearch] Querying knowledge graph overview")

        try:
            resp = await self.http_client.get(self.config.kg_api_url)
            resp.raise_for_status()
            response = resp.json()
        except Exception as e:
            logger.error(f"KG API Error: {e}")
            return CallToolResult.from_text(f"查询知识图谱数据时出错: {str(e)}")

        # 检查响应状态 (注意：原代码中status==0表示成功)
        if response.get('status') != 0:
            return CallToolResult.from_text("无法获取知识图谱数据统计总览数据")

        # 解析响应数据
        data_dict = response.get('data', {})
        try:
            kg_data = KGOverviewData.model_validate(data_dict)
        except Exception as e:
            logger.error(f"Failed to parse KG data: {e}")
            return CallToolResult.from_text(f"解析知识图谱数据时出错: {str(e)}")

        # 格式化输出
        view_text = ResultFormatter.format_kg_overview(kg_data)

        return CallToolResult.from_artifact(
            view=view_text,
            data=kg_data.model_dump(),
            type="dataset"
        )
    


    # --- 核心功能：文档内容查询 (Tool Implementation) ---

    async def lookup_doc_content(self, resource_file_ids: Union[str, List[str]], token: Optional[str] = None) -> CallToolResult:
        """
        [Tool] 查询文档内容

        :param resource_file_ids: 文件资源ID（单个ID字符串或ID列表）
        :param token: 认证令牌
        """
        logger.info(f"📄 [AssetSearch] Querying document content: ids={resource_file_ids}")

        # 处理输入参数
        if not resource_file_ids or resource_file_ids == 'None':
            return CallToolResult.from_text("未提供有效的文件资源ID")

        # 转换为ID列表
        if isinstance(resource_file_ids, list):
            ids = resource_file_ids
            ids_str = ','.join(resource_file_ids)
        else:
            ids_str = resource_file_ids
            ids = [resource_file_ids]

        # 构建请求参数
        params = {'p': 'w', 'resource_file_ids': ids_str}
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            resp = await self.http_client.post(self.config.doc_api_url, json=params, headers=headers)
            resp.raise_for_status()
            response = resp.json()
        except Exception as e:
            logger.error(f"Doc API Error: {e}")
            return CallToolResult.from_text(f"查询文档内容时出错: {str(e)}")

        if response.get('status') != 1:
            return CallToolResult.from_text(f"查询失败: {response.get('msg', 'Unknown error')}")

        # 解析响应数据
        try:
            doc_result = DocSearchResult.model_validate(response)
        except Exception as e:
            logger.error(f"Failed to parse doc result: {e}")
            return CallToolResult.from_text(f"解析文档数据时出错: {str(e)}")

        # 格式化输出
        view_text = ResultFormatter.format_doc_search_result(doc_result, ids)

        return CallToolResult.from_artifact(
            view=view_text,
            data=doc_result.model_dump(),
            type="dataset"
        )

    # ==================== V2 API: 藏品和文档智能检索 ====================

    async def search_exhibits_v2(
        self,
        query: str,
        exhibit_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        ctx: ServiceContext = None
    ) -> CallToolResult:
        """
        [Tool V2] 搜索藏品（实体文物）- 使用新的智能检索 API

        Args:
            query: 搜索关键词
            exhibit_ids: 可选的藏品ID列表，用于精确搜索
            filters: 可选的过滤条件（如年代、材质等）
            top_k: 返回结果数量
            ctx: 服务上下文（用于重排序）

        Returns:
            藏品搜索结果，包含藏品的基本信息和描述内容
        """
        logger.info(f"🏛️ [AssetSearch V2] Searching exhibits: {query}")

        payload = {
            "keyword": query,
            "exhibit_ids": exhibit_ids or [],
            "filter": filters or {}
        }
        params = {"p": "w"}

        try:
            resp = await self.http_client.post(
                self.config.exhibit_search_url,
                params=params,
                json=payload,
                timeout=10.0
            )
            resp.raise_for_status()
            response = resp.json()
        except Exception as e:
            logger.error(f"Exhibit Search API Error: {e}")
            return CallToolResult.from_text(f"搜索藏品时出错: {str(e)}")

        if response.get("status") != 1:
            return CallToolResult.from_text(f"搜索失败: {response.get('msg', 'Unknown error')}")

        # 解析响应数据
        data_outer = response.get("data", {}) or {}
        raw_results = data_outer.get("data", []) or []
        raw_file_list = data_outer.get("file_list", []) or []

        # 构造结果列表
        output_list = []
        for item in raw_results:
            content = item.get("content") or json.dumps(item, ensure_ascii=False)
            output_item = item.copy()
            output_item['content'] = content
            output_list.append(output_item)

        # Rerank 重排序
        if ctx and ctx.reranker and output_list:
            output_list = await ctx.reranker.rank_objects(
                query=query,
                items=output_list,
                key_func=lambda x: x.get('content', ''),
                threshold=self.config.rerank_threshold,
                top_k=top_k
            )

        if not output_list:
            return CallToolResult.from_text("未找到相关藏品")

        # 格式化输出
        view_text = "🏛️ 藏品搜索结果 (V2 API):\n\n"
        for idx, item in enumerate(output_list, 1):
            content = item.get('content', '')[:200]
            view_text += f"{idx}. {content}\n"

        recommand_content = APISearchResultData(library_list=[],resource_list=[],resource_file_list=[],exhibit_list = [])
        recommand_content.exhibit_list = output_list
        
        return CallToolResult.from_artifact(
            view=view_text,
            data= recommand_content.model_dump() or raw_file_list,
            type="dataset"
        )

    async def search_resources_v2(
        self,
        query: str,
        file_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 5,
        ctx: ServiceContext = None
    ) -> CallToolResult:
        """
        [Tool V2] 搜索数字资源（文档、研究资料）- 使用新的智能检索 API

        Args:
            query: 搜索关键词
            file_ids: 可选的文件ID列表，用于精确搜索
            tags: 可选的标签过滤
            top_k: 返回结果数量
            ctx: 服务上下文（用于重排序）

        Returns:
            数字资源搜索结果，包含文档内容（llm_summary 或 original_text）
        """
        logger.info(f"📚 [AssetSearch V2] Searching resources: {query}")

        payload = {
            "search_word": query,
            "file_ids": file_ids or [],
            "tags": tags or [],
            "original": True
        }
        params = {"p": "w"}

        try:
            resp = await self.http_client.post(
                self.config.resource_search_url,
                params=params,
                json=payload,
                timeout=10.0
            )
            resp.raise_for_status()
            response = resp.json()
        except Exception as e:
            logger.error(f"Resource Search API Error: {e}")
            return CallToolResult.from_text(f"搜索资源时出错: {str(e)}")

        if response.get("status") != 1:
            return CallToolResult.from_text(f"搜索失败: {response.get('msg', 'Unknown error')}")

        # 解析响应数据
        data_outer = response.get("data", {}) or {}
        raw_results = data_outer.get("data", []) or []
        raw_file_list = data_outer.get("file_list", []) or []

        # 构造结果列表
        output_list = []
        for item in raw_results:
            content = item.get("llm_summary") or item.get("original_text") or ""
            output_item = item.copy()
            output_item['content'] = content
            output_list.append(output_item)

        # Rerank 重排序
        if ctx and ctx.reranker and output_list:
            output_list = await ctx.reranker.rank_objects(
                query=query,
                items=output_list,
                key_func=lambda x: x.get('content', ''),
                threshold=self.config.rerank_threshold,
                top_k=top_k
            )

        if not output_list:
            return CallToolResult.from_text("未找到相关资源")

        # 关联文件信息
        resource_id_map = {
            item.get('resource_file_id'): item
            for item in output_list
            if item.get('resource_file_id')
        }
        
        final_resource_list = []
        if raw_file_list and isinstance(raw_file_list, list):
            for file_item in raw_file_list:
                file_id = file_item.get('FileId')
                if file_id in resource_id_map:
                    final_resource_list.append({
                        "resource_file_id": file_item.get('ResourceId', ''),
                        "file_name": file_item.get('FileName', ''),
                        "resource_id": file_id,
                        "content": resource_id_map[file_id]['content'],
                    })

        # 格式化输出
        view_text = "📚 资源文档搜索结果 (V2 API):\n\n"
        for idx, item in enumerate(output_list, 1):
            content = item.get('content', '')[:200]
            view_text += f"{idx}. {content}...\n"
        
        recommand_content = APISearchResultData(library_list=[],resource_list=[],resource_file_list=[],exhibit_list = [])
        recommand_content.resource_file_list = final_resource_list
        return CallToolResult.from_artifact(
            view=view_text,
            data=recommand_content.model_dump() or output_list,
            type="dataset"
        )
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    