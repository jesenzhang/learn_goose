import json
import os
import random
import copy
import aiohttp
import asyncio
import time
from typing import Optional, List, Dict
import logging
from assistant.conversation import CallToolResult, RawContent

logger = logging.getLogger(__name__)

# ================= 配置区 =================
# 假设这是你的统计接口地址
STATS_API_URL = "http://192.168.11.11:9980/gzclabelapi/search/statistic?p=w" 

# 获取 assets/faq.json 的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAQ_FILE = os.path.join(BASE_DIR, "assets", "faq.json")

# 缓存加载的数据
_FAQ_DATA_CACHE = None

def _load_faq_data():
    """懒加载 FAQ 数据"""
    global _FAQ_DATA_CACHE
    if _FAQ_DATA_CACHE is None:
        if os.path.exists(FAQ_FILE):
            with open(FAQ_FILE, 'r', encoding='utf-8') as f:
                _FAQ_DATA_CACHE = json.load(f)
        else:
            print(f"⚠️ FAQ file not found at {FAQ_FILE}")
            _FAQ_DATA_CACHE = []
    return _FAQ_DATA_CACHE

async def _fetch_dynamic_stats(url=STATS_API_URL,params=None, token=None,time_out = 10):
    """模拟原代码中的 APISearch.get_async()"""
    timeout = aiohttp.ClientTimeout(total=time_out)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tstart = time.time()
            headers = {}
            if token:
                headers['Authorization'] = f'{token}'  # 假设使用 Bearer Token 认证方式
            async with session.get(url, params=params, headers=headers) as resp:
                response = await resp.json()
            logger.info(f"get {url} 用时 {time.time() - tstart}")
        return response
    except asyncio.TimeoutError:
        logger.error(f"Request to {url} timed out.")
        return {"status":0,"error": "Request timed out."}
    except aiohttp.ClientError as e:
        logger.error(f"Client error occurred while making a request to {url}: {e}")
        return {"status":0,"error": f"Client error: {str(e)}"}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response from {url}: {e}")
        return {"status":0,"error": f"JSON decoding error: {str(e)}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred while making a request to {url}: {e}")
        return {"status":0,"error": f"Unexpected error: {str(e)}"}

def fuzzy_match(query: str, faq_data: List[Dict],threshold=0.4) -> List[Dict]:
    import difflib
    match_items = []
    for item in faq_data:
        text = item.get('text','')
        if text:
            score = difflib.SequenceMatcher(None, query, text).ratio()
            if score > threshold:
                match_items.append({'item': item,
                                    'score': score})
                
    if match_items:
        match_items.sort(key=lambda x: x['score'], reverse=True)        
        return match_items
    else:
        return None

def faq_match(query: str, faq_data: List[Dict],type='text'):
        answer_list = []
        if type == "text":
            for item in faq_data:
                if query == item['text']:
                    answer_list.append(item)
        if type == "file":
            for item in faq_data:
                if query == item['id']:
                    answer_list.append(item)
        return answer_list
    
async def query_faq(query: str, ctx=None) -> str:
    """
    Search for a predefined answer in the FAQ knowledge base.
    Returns the answer string if found, or 'None' if not matched.

    Args:
        query: The user's query text
        ctx: Optional ServiceContext for accessing shared state
    """
    # 检查是否已被 Hook 查询过
    if ctx and hasattr(ctx, 'state') and ctx.state.shared_memory.get("_faq_already_queried"):
        logger.info("FAQ already queried by Hook, skipping tool execution")
        return "None"

    faq_data = _load_faq_data()
    
    # 1. 查找匹配项 (Exact Match)
    matched_items = fuzzy_match(query, faq_data)
    
    if not matched_items:
        return "None"

    # 2. 随机选择一条回答
    faq_item = copy.deepcopy(matched_items[0]['item'])
    
    # 3. 处理普通静态回答
    # 假设 faq.json 结构: {"id": "...", "fields": {"response": "..."}}
    response_text = faq_item.get('fields', {}).get('response', "")
    recommend = faq_item.get('fields', {}).get('recommend')
    item_id = faq_item.get('id')

    text = ''
    # 4. 处理 "fun" 类型的动态数据
    if item_id == "fun":
        # 这里的 response_text 是一个 key，例如 'top_ten_resource'
        stats_key = response_text
        api_data = await _fetch_dynamic_stats()
        answer = api_data.get('data', {}).get(stats_key)
        
        if isinstance(answer,str):
            text = answer
        if stats_key == 'top_ten_resource':
            text = "最常被访问或使用的前十大数字资产是："
            recommend['resource_list'] = answer
        elif stats_key == 'no_view_resource':
            text = "以下是未被访问时间最长的前10个数字资产："
            recommend['resource_list'] = answer
        if stats_key== 'top_ten_exhibit':
            text = "最常被访问或使用的前十个藏品："
            recommend['resource_list'] = answer
        elif stats_key == 'no_view_exhibit':
            text = "不常被访问或使用的前十个藏品："
            recommend['resource_list'] = answer

    if recommend:
        return CallToolResult.from_artifact(
            view=text,
            data=recommend,
            type="dataset"
        )
    else:
        return CallToolResult.from_text(text)
