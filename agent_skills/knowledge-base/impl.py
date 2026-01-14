import json
import os
import difflib
import aiohttp
import asyncio
from typing import List, Dict, Any,Optional
from pydantic import BaseModel,Field

from assistant.skills.context import ServiceContext
# --- 配置 ---
# --- 路径定义 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "assets", "config.json")

class KBConfig:
    """配置加载类：负责读取 assets/config.json"""
    def __init__(self):
        self._config = self._load_config()

    def _load_config(self) -> Dict:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading config.json: {e}")
        return {}

    @property
    def local_enabled(self) -> bool:
        return self._config.get("local", {}).get("enabled", True)

    @property
    def local_file_path(self) -> str:
        filename = self._config.get("local", {}).get("filename", "local_kb.json")
        return os.path.join(BASE_DIR, "assets", filename)

    @property
    def remote_enabled(self) -> bool:
        return self._config.get("remote", {}).get("enabled", False)

    @property
    def remote_url(self) -> str:
        return self._config.get("remote", {}).get("url", "")

    @property
    def remote_method(self) -> str:
        return self._config.get("remote", {}).get("method", "GET").upper()
    
    @property
    def remote_timeout(self) -> int:
        return self._config.get("remote", {}).get("timeout", 5)

    @property
    def remote_params(self) -> Dict:
        # GET请求的参数
        return self._config.get("remote", {}).get("params", {})
    
    @property
    def remote_body(self) -> Any:
        # POST请求的Body
        return self._config.get("remote", {}).get("body", {})

    @property
    def remote_headers(self) -> Dict:
        return self._config.get("remote", {}).get("headers", {})


class KnowledgeBaseEngine:
    def __init__(self):
        self.config = KBConfig() # 初始化配置类
        self.data_store = []
        self.lock = asyncio.Lock()
        self.is_loaded = False

    async def initialize(self):
        """初始化：并行加载本地和远程数据"""
        if self.is_loaded: return
        
        async with self.lock:
            tasks = []
            
            # 1. 本地加载任务
            if self.config.local_enabled:
                tasks.append(asyncio.to_thread(self._load_local))
            
            # 2. 远程加载任务
            if self.config.remote_enabled and self.config.remote_url:
                tasks.append(self._fetch_remote())
            
            # 并发执行
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 合并结果
            combined_data = []
            for res in results:
                if isinstance(res, list):
                    combined_data.extend(res)
                elif isinstance(res, Exception):
                    print(f"⚠️ Init error: {res}")
            
            self.data_store = combined_data
            self.is_loaded = True
            
            local_count = len(results[0]) if len(results) > 0 and isinstance(results[0], list) else 0
            remote_count = len(results[1]) if len(results) > 1 and isinstance(results[1], list) else 0
            print(f"📚 KB Loaded: {len(self.data_store)} items (Local~{local_count}, Remote~{remote_count})")

    def _load_local(self) -> List[Dict]:
        path = self.config.local_file_path
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Load local KB failed: {e}")
        return []

    async def _fetch_remote(self) -> List[Dict]:
        """
        远程拉取：Config(URL/Method/Params) + Env(Token)
        """
        # 1. 基础配置从 Config 文件读取
        url = self.config.remote_url
        method = self.config.remote_method
        headers = self.config.remote_headers.copy() # 复制一份，避免修改配置源
        
        # 2. 敏感信息从环境变量读取
        api_token = os.getenv("KB_REMOTE_TOKEN")
        basic_user = os.getenv("KB_REMOTE_USER")
        basic_pass = os.getenv("KB_REMOTE_PASS")
        
        auth = None
        if api_token:
            headers["Authorization"] = f"{api_token}"
        elif basic_user and basic_pass:
            auth = aiohttp.BasicAuth(login=basic_user, password=basic_pass)

        # 3. 准备请求参数
        kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": self.config.remote_timeout
        }
        if auth:
            kwargs['auth'] = auth

        # 区分 Params (URL Query) 和 JSON Body
        if method == 'POST':
            # 如果配置里有 body 优先用 body，没有则尝试用 params
            kwargs['json'] = self.config.remote_body or self.config.remote_params
        else:
            kwargs['params'] = self.config.remote_params

        # 4. 执行请求
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(**kwargs) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if isinstance(res, list):
                            return res
                        return res.get("data", [])
                    elif resp.status in [401, 403]:
                        print(f"⚠️ Fetch remote KB Auth Failed: {resp.status}")
                    else:
                        print(f"⚠️ Fetch remote KB Error: {resp.status}")
        except Exception as e:
            print(f"⚠️ Fetch remote KB Exception: {e}")
        
        return []

    def find_match(self, query: str, threshold=0.6):
        """查找最佳匹配项"""
        best_item = None
        best_score = 0
        if  self.data_store == None or len(self.data_store)==0:
            return '知识库是空的'
        
        for item in self.data_store:
            for q in item.get('questions', []):
                score = difflib.SequenceMatcher(None, query, q).ratio()
                if score > best_score:
                    best_score = score
                    best_item = item
        
        if best_score >= threshold:
            return best_item
        return None

    def _resolve_env_vars(self, data: Any) -> Any:
        """递归解析字典或字符串中的 {env.VAR} 占位符"""
        if isinstance(data, str):
            if "{env." in data:
                # 简单替换逻辑，支持 {env.API_KEY}
                try:
                    import re
                    def replace_env(match):
                        var_name = match.group(1)
                        return os.getenv(var_name, "")
                    
                    return re.sub(r'\{env\.([A-Z0-9_]+)\}', replace_env, data)
                except:
                    return data
            return data
        elif isinstance(data, dict):
            return {k: self._resolve_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_env_vars(i) for i in data]
        return data
    
    async def execute_dynamic(self, item: Dict) -> str:
        """执行动态请求"""
        meta = item.get('metadata', {})
        
        # 1. 深度解析环境变量占位符 (Key Step)
        meta = self._resolve_env_vars(meta)
        
        url = meta.get('url')
        method = meta.get('method', 'GET').upper()
        headers = meta.get('headers', {})
        
        # 处理 payload (params for GET, json for POST)
        payload = meta.get('params') or meta.get('body') or {}

        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"headers": headers, "timeout": meta.get('timeout', 5)}
                
                if method == 'GET':
                    kwargs['params'] = payload
                else:
                    kwargs['json'] = payload

                async with session.request(method, url, **kwargs) as resp:
                    if resp.status != 200:
                        return f"Error: Remote API returned {resp.status}"
                    
                    api_result = await resp.json() # 假设返回的是 data 字典
                    
                    # --- 渲染逻辑 ---
                    template = item.get('answer', '')
                    
                    # 特殊处理：如果是列表渲染指令
                    if template == "format_list":
                        if isinstance(api_result, list):
                            return "\n".join([f"- {str(x)}" for x in api_result])
                        return str(api_result)
                    
                    # 默认处理：字符串格式化 (Python f-string style)
                    # 例如 answer="{cpu}%", api_result={"cpu": 90}
                    if isinstance(api_result, dict):
                        try:
                            # 使用 safe_format 避免 key 不存在报错
                            return template.format(**api_result)
                        except KeyError:
                            return f"Data: {json.dumps(api_result, ensure_ascii=False)}"
                    
                    return str(api_result)

        except Exception as e:
            return f"Dynamic execution failed: {e}"

# 单例
engine = KnowledgeBaseEngine()

class APIQuery(BaseModel):
    text: str|None = None
    vector_list: List|None = None
    robot_id: Optional[int]
# --- Tool ---
class FAQQuery(APIQuery):
    faq_id:Any
    
class ExhibitItem(BaseModel):
    exhibit_id: Optional[int] = 0
    exhibit_name: Optional[str] = None
    exhibition_name: Optional[str] = None
    content: Optional[str] = None
    museum: Optional[str] = None
    exhibit_img: Optional[str] = None

class FAQItem(BaseModel):
    id: Optional[int]=0
    question: Optional[str]= None
    answer: Optional[str]= None
    museum: Optional[str]= None
    score: Optional[float]= 0
    exhibit: Optional[ExhibitItem] = None
    is_autoplay: Optional[int] = 0
    instruction: Optional[str] = None
    has_service : Optional[int] = 0

class FAQSearchResult(BaseModel):
    status: int
    msg: str
    data: List[FAQItem] = []
    
class Document(BaseModel):
    page_content: str
    metadata: dict = Field(default_factory=dict)
     
from request_tool import APITool,APIToolConfig
faq_search = APITool.from_config(APIToolConfig(base_url=engine.config.remote_url))
    
async def query_knowledge_base(query: str, ctx:ServiceContext=None) -> str:
    """
    [PRIORITY: HIGH] Always call this tool FIRST before any other action.

    语义搜索知识库。
    
    Args:
        query: 用户的问题
        _ai: [Injected] 系统自动注入的 AI 服务实例
    
    Returns:
        - The exact answer/statistic if found.
        - "None" if no match is found (signal to proceed with other tools).
    """
    # 确保初始化 (Lazy Init)
    if not engine.is_loaded:
        await engine.initialize()

    # 1. 匹配
    # 短查询降低阈值
    if not ctx.embedding:
        return "System Error: Embedding Service not injected."
    
    q_embed = await ctx.embedding.aembed_query(query)
    faq_q = FAQQuery(text=query,vector_list=q_embed,robot_id=0,faq_id=0)
    faq_result = await faq_search.post_async(faq_q.model_dump())
    faq_docs = []
    faq_result = FAQSearchResult.model_validate(faq_result) if faq_result else FAQSearchResult(status=0, msg="error", data=[])
    for doc in faq_result.data:
            if not doc.answer:
                continue
            if doc.score >1.9:
                faq_docs.append(
                    Document(
                        page_content=(
                            f"问：{doc.question} 答：{doc.answer}\n"
                            # if doc.museum in doc.question
                            # else f"场馆：{doc.museum}\n问题：{doc.question}\n答案：{doc.answer}\n\n"
                        ),
                        metadata={
                            "museum": doc.museum,
                            "question": doc.question,
                            "answer": doc.answer,
                            "score": doc.score,
                            "source": "FAQ",
                            "artifact":None
                        },
                    )
                )
    
    if faq_docs:
        return faq_docs
    
    threshold = 0.4 if len(query) < 4 else 0.6
    match = engine.find_match(query, threshold)

    if match == '知识库是空的':
        return '知识库是空的'
    
    if not match:
        return "None"

    # 2. 执行
    item_type = match.get('type', 'static')
    
    if item_type == 'static':
        return match.get('answer', '')
    
    elif item_type == 'dynamic':
        return await engine.execute_dynamic(match)
    
    return "Unknown item type"

async def refresh_knowledge_base():
    """Force refresh remote data."""
    engine.is_loaded = False
    await engine.initialize()
    return "Knowledge base refreshed."