import json
import os
import httpx
import asyncio
from typing import Dict, List
from assistant.conversation import CallToolResult
from assistant.core.agent import AgentContext

import logging
logger = logging.getLogger(__name__)

# ================= 配置区域 =================
# 在实际生产中，这些应该从环境变量或 _state 中读取
SEARCH_RESOURCE_URL = os.getenv("SEARCH_RESOURCE_URL", "http://192.168.11.11:9980/gzclabelapi/agent/search_doc")
SEARCH_EXHIBIT_URL = os.getenv("SEARCH_EXHIBIT_URL", "http://192.168.11.11:9980/gzclabelapi/agent/search_exhibit")
API_TOKEN = os.getenv("MUSEUM_API_TOKEN", "")

async def _call_search_api_async(client: httpx.AsyncClient, url: str, payload: Dict, params) -> Dict:
    """
    内部异步请求函数
    """
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
        
    try:
        resp = await client.post(url, params=params, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
    
async def _call_search_api(search_type: str, search_word: str,filter:Dict = None, tags: List[str] = None, param_p: str = 'w') -> Dict:
    """
    底层 API 调用逻辑 (原 search_asset_exhibit 的简化版)
    """
    url = None
    # 构造 Payload
    payload = {}
    if search_type == "exhibit":
        url = SEARCH_EXHIBIT_URL
        payload = {
            "keyword": search_word,
            "exhibit_ids": [],
            "filter":filter or {},
        }
    elif search_type == "resource":
        url = SEARCH_RESOURCE_URL
        payload = {
            "search_word": search_word,
            "file_ids": [],
            "tags": tags or [],
            "original": True
        }
    params = {"p": param_p}
    
    if not url:
        return {"outputList": [], "sourceList": []}
    
    try:
        async with httpx.AsyncClient() as client:
            api_resp = await _call_search_api_async(client, url, payload,params)
        
        if api_resp.get("status") != 1:
            return {"error": api_resp.get("msg")}

        data_outer = api_resp.get("data", {}) or {}
        raw_results = data_outer.get("data", []) or []
        raw_file_list = data_outer.get("file_list", []) or []

        # 构造标准输出
        output_list = []
        for item in raw_results:
            # 统一提取内容逻辑
            content = ""
            if search_type == "resource":
                content = item.get("llm_summary") or item.get("original_text") or ""
            else:
                content = item.get("content") or json.dumps(item, ensure_ascii=False)
            
            # 结构化
            output_item = item.copy()
            output_item['content'] = content # 确保 content 字段存在
            output_list.append(output_item)

        return {
            "outputList": output_list,
            "sourceList": raw_file_list
        }

    except Exception as e:
        return {"error": str(e)}

# ================= 公开工具函数 =================

async def search_exhibits(query: str, top_k: int = 5, ctx: ServiceContext = None):
    """
    Search for museum exhibits (physical artifacts).
    """
    logger.info(f"🔎 Searching exhibits for: {query}")
    try:
        result = await _call_search_api("exhibit", query)
    except Exception as e:
        return CallToolResult.from_text(f"Search Error: {e}")
    
    if "error" in result:
        return CallToolResult.from_text(f"Search Error: {result['error']}")
    
    exhibit_list = []
    
    exhibit_list = result.get("outputList", [])
    if not exhibit_list:
        return CallToolResult.from_text("No exhibits found.")
    
    if ctx.reranker:
        exhibit_list = await ctx.reranker.rank_objects(query,exhibit_list,key_func=lambda x: x['content'],top_k=top_k)
        
    if not exhibit_list:
        return CallToolResult.from_text("No exhibits found.")
    
    return CallToolResult.from_artifact(
        view='\n\n藏品搜索结果：\n\n' + '\n\n'.join([json.dumps(item,ensure_ascii=False) for item in exhibit_list]),
        data=exhibit_list,
        type="dataset"
    )

async def search_resources(query: str, top_k: int = 5,ctx: ServiceContext = None):
    """
    Search for digital assets and documents (e.g., papers, descriptions).
    """
    logger.info(f"🔎 Searching resources for: {query}")
    result =await _call_search_api("resource", query)
    
    if "error" in result:
        return CallToolResult.from_text(f"Search Error: {result['error']}")

    resource_list = result.get("outputList", [])
    sourceList = result.get("sourceList", [])
    
    if not resource_list:
        return CallToolResult.from_text("No resources found.")
    
    if ctx.reranker:
        resource_list = await ctx.reranker.rank_objects(query,resource_list,key_func=lambda x: x['content'],top_k=top_k)
    
    resource_id_list = {item.get('resource_file_id'): item for item in resource_list if item.get('resource_file_id')}
    
    output_resource_list = []
    if sourceList and isinstance(sourceList,list):
        for item in sourceList:
            if item['FileId'] in resource_id_list:
                output_resource_list.append({
                    "resource_file_id": item['ResourceId'],
                    "file_name": item['FileName'],
                    "resource_id": item['FileId'],
                    "content": resource_id_list[item['FileId']]['content'],
                })
                        
    return CallToolResult.from_artifact(
        view='\n\n资产文档搜索结果：\n\n' + '\n\n'.join([json.dumps(item,ensure_ascii=False) for item in resource_list]),
        data=output_resource_list,
        type="dataset"
    )
    