import asyncio
import random
import aiohttp
import markdownify
import readabilipy
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Tuple,Literal,Optional
from langchain_community.utilities import SearxSearchWrapper
from pydantic import BaseModel,Field

from goose.toolkit.registry import register_tool
"""
SearxNG 搜索工具模块
该模块提供了基于 SearxNG 的网络搜索功能，支持多种搜索类别并发执行。
可以作为 LangChain Agent 的工具调用，用于获取实时网络信息。

功能特点：
1. 支持多种搜索类别：通用、图片、新闻、IT技术、科学研究等
2. 并发执行多个搜索任务，提高搜索效率
3. 提供同步和异步两种调用方式
4. 易于集成到 LangChain Agent 中作为工具使用
"""

class Document(BaseModel):
    page_content: str
    metadata: dict = Field(default_factory=dict)

# 搜索配置，定义了不同类别的搜索参数
SEARCH_CONFIG = {
    "general": {
        "categories": ['general'],
        "engines": ['baidu', 'bing', '360search', 'quark'],
    },
    "images": {
        "categories": ['images'],
        "engines": ['bing images', 'sogou images', 'quark images', 'baidu images'],
    },
    "news": {
        "categories": ['news'],
        "engines": ['bing news', 'sogou wechat'],
    },
    "it": {
        "categories": ['it', 'science'],
        "engines": ['github', 'arch linux wiki', 'gentoo', 'mdn'],
    },
    "science": {
        "categories": ['science'],
        "engines": ['pubmed', 'openairedatasets', 'openairepublications', 'pdbe', 'arxiv', 'semantic scholar', 'google scholar'],
    },
}


async def _asearch_category(searx_host: str, query: str, category: str, lang: str, num_results: int) -> tuple:
    """
    异步搜索单个分类
    
    Args:
        searx_host (str): SearxNG 服务地址
        query (str): 搜索查询词
        category (str): 搜索类别
        lang (str): 搜索语言，默认为 "zh"
        num_results (int): 返回结果数量，默认为 5
        
    Returns:
        tuple: (分类名称, 搜索结果列表)
    """
    search = SearxSearchWrapper(searx_host=searx_host)
    try:
        results = await search.aresults(
            query,
            language=lang,
            engines=SEARCH_CONFIG[category]['engines'],
            num_results=num_results
        )
        return category, results
    except Exception as e:
        # print(f"Error searching {category}: {e}")
        return category, []


async def asearch_web(query: str, categories: Optional[List[str]] = None, lang: str = "zh", num_results: int = 20) -> Dict[str, Any]:
    """
    并发搜索多个分类（异步版本）
    
    可以作为 LangChain Agent 的工具直接调用。
    
    Args:
        query (str): 搜索查询词
        categories (List[str], optional): 搜索类别列表。默认为 ['general']
            支持的类别包括：
            - "general": 通用搜索（百度、必应等）
            - "images": 图片搜索
            - "news": 新闻搜索
            - "it": IT技术搜索
            - "science": 科学研究搜索
        lang (str, optional): 搜索语言。默认为 "zh"
        num_results (int, optional): 每个类别返回的结果数量。默认为 5
        
    Returns:
        Dict[str, Any]: 按分类组织的搜索结果字典
        例如：
        {
            "general": [
                {"title": "结果1", "link": "http://example.com/1", "snippet": "摘要1","engines": ["baidu"], "category": "general"},
                {"title": "结果2", "link": "http://example.com/2", "snippet": "摘要2","engines": ["bing"], "category": "general"}
            ],
            "news": [
                {"title": "新闻1", "link": "http://news.com/1", "snippet": "新闻摘要1","engines": ["bing news"], "category": "news"}
            ]
        }
        
    Example:
        # 在 LangChain Agent 中使用
        from langchain.agents import AgentType, initialize_agent
        from langchain.tools import tool
        
        @tool
        async def web_search(query: str, categories: List[str] = ["general"]) -> Dict[str, Any]:
            "用于搜索网络信息的工具"
            return await asearch_web(query, categories)
            
        agent = initialize_agent([web_search], llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
    """
    if categories is None:
        categories = ['general']
    
    searx_host = "http://192.168.10.180:8888"
    
    # 创建所有搜索任务
    tasks = [
        _asearch_category(searx_host, query, category, lang, num_results)
        for category in categories
    ]
    
    # 并发执行所有任务
    results = await asyncio.gather(*tasks)
    
    # 整理结果
    all_result = {}
    for category, result in results:
        all_result[category] = result
        
    return all_result


def search_web(query: str, categories: Optional[List[str]] = None, lang: str = "zh", num_results: int = 5) -> Dict[str, Any]:
    """
    并发搜索多个分类（同步版本）
    
    可以作为 LangChain Agent 的工具直接调用。
    
    Args:
        query (str): 搜索查询词
        categories (List[str], optional): 搜索类别列表。默认为 ['general']
            支持的类别包括：
            - "general": 通用搜索（百度、必应等）
            - "images": 图片搜索
            - "news": 新闻搜索
            - "it": IT技术搜索
            - "science": 科学研究搜索
        lang (str, optional): 搜索语言。默认为 "zh"
        num_results (int, optional): 每个类别返回的结果数量。默认为 5
        
    Returns:
        Dict[str, Any]: 按分类组织的搜索结果字典
        例如：
        {
            "general": [
                {"title": "结果1", "link": "http://example.com/1", "snippet": "摘要1","engines": ["baidu"], "category": "general"},
                {"title": "结果2", "link": "http://example.com/2", "snippet": "摘要2","engines": ["bing"], "category": "general"}
            ],
            "news": [
                {"title": "新闻1", "link": "http://news.com/1", "snippet": "新闻摘要1","engines": ["bing news"], "category": "news"}
            ]
        }
        
    Example:
        # 在 LangChain Agent 中使用
        from langchain.agents import AgentType, initialize_agent
        from langchain.tools import tool
        
        @tool
        def web_search(query: str, categories: List[str] = ["general"]) -> Dict[str, Any]:
            "用于搜索网络信息的工具"
            return search_web(query, categories)
            
        agent = initialize_agent([web_search], llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
        
        # 直接调用
        results = search_web("人工智能发展现状", ["general", "news"])
    """
    if categories is None:
        categories = ['general']
    
    # 运行异步函数
    return asyncio.run(asearch_web(query, categories, lang, num_results))


# 随机获取一个cookie
def get_random_cookie():
    cookies = [
        'PSTM=1645440125; BAIDUID=49D5966BB6F2D98A8378EC10151CE748:FG=1; BAIDUID_BFESS=49D5966BB6F2D98A8378EC10151CE748:FG=1; BIDUPSID=5C48EADF0E27C74CB11F290539E5EAA8; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; __yjs_duid=1_6b058121c11c500f39afbc042ec623711645440178604; delPer=0; PSINO=7; MCITY=-257%3A; BA_HECTOR=05a0ak0ga42525a5us1h18lb30r; BDRCVFR[C0p6oIjvx-c]=rJZwba6_rOCfAF9pywd; H_PS_PSSID=35105_35865_34584_35491_35872_35246_35319; ab_sr=1.0.1_ZGM2MTQ3YjE2NGE0ZmE2NWNhNGYzMDQ1Nzg1ZWYxYWFjZDllZjA1NzY0YWE3NjVjZmEyNjA4NmE5NTljZTEzOTFkNzViMWRlNTA4ZmQwYWIzYWZlYjQyMDYxZTcxNGI0NWVjYzU5ODk0ZDVmYmNkZDI4YzkyNGEwNTUwZjc4MWU3Y2Q0ZTUzOGExNjQwZTgzMzM4ZjQ2ZjkzMjE0OGNjZA==; BAIDU_WISE_UID=wapp_1645499858512_985',
        'BIDUPSID=0AB15879656FD166028DF65039BDFF15; PSTM=1641442191; BAIDUID=911EF71E90573B2693EC612910B1F7BE:FG=1; BCLID_BFESS=9239639223377566883; BDSFRCVID_BFESS=1T-OJeCmHxdstirHc7RXbo9jumKK0gOTHllnPXllHP8_1buVJeC6EG0Ptf8g0KubFTPRogKK0gOTH6KF_2uxOjjg8UtVJeC6EG0Ptf8g0M5; H_BDCLCKID_SF_BFESS=tJkD_I_hJKt3fP36q6_a2-F_2xQ0etJXf5Txbp7F5lOVO-ngKU613MkSjNOj5t482jTLahkM5h7xObR1hl3ih-An0a7dJ4jtQeQ-5KQN3KJmfbL9bT3v5tDz3b3N2-biWbRM2MbdJqvP_IoG2Mn8M4bb3qOpBtQmJeTxoUJ25DnJhhCGe6-MjT3-DG8jqbvEHDc-WJ3t-TrjDCvRhMjcy4LdjG5N0PJT5bv73K022boobJcGLqjW0R_X3-Aq54RMagQwLPJEytQTS-5VbtoMQfbQ0-cOqP-jWbnu-qTo2n7JOpkRbUnxy50vQRPH-Rv92DQMVU52QqcqEIQHQT3m5-5bbN3ht6IHJbCJoDD5tIvbfP0kjjQWMt_h-fuX5-CstGPL2hcH0b61JbbR5-rKy-JW0R7a25cBbCjiaKJjBMb1DbRk0h7ShMkrebPD5JQpWDTm_q5TtUJMeCnTDMRh-xK70b5yKMnitIv9-pPKWhQrh459XP68bTkA5bjZKxtq3mkjbPbDfn028DKu-n5jHj3WDG-J3q; __yjs_duid=1_ada3d0ac8d4be7042dd53d52221555631641452261829; BAIDUID_BFESS=911EF71E90573B2693EC612910B1F7BE:FG=1; BD_HOME=1; H_PS_PSSID=35104_31660_34584_35490_35841_35887_35542_35318_26350_35867_22158; BD_UPN=12314753; delPer=0; BD_CK_SAM=1; PSINO=7; H_PS_645EC=09c89Z6QKcJ4xzJZr1LUqxrp0qdbpltyn/ixDDrfq5R6r0cQWwLiJT3HLZY; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; BA_HECTOR=a424810gag04818hg31h15uop0q; baikeVisitId=492b5e23-3a27-4d6d-bf0a-ab5907361a87; BDSVRTM=643']
    cooke = random.choice(cookies).strip()
    return cooke

def get_random_user_agent():
    user_agents = [
        # 现代浏览器User-Agent（2023-2024主流版本）
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/119.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/49.0.2623.108 Chrome/49.0.2623.108 Safari/537.36',
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/49.0.2623.108 Chrome/49.0.2623.108 Safari/537.36",
        "Mozilla/5.0 (Windows; U; Windows NT 5.1; pt-BR) AppleWebKit/533.3 (KHTML, like Gecko) QtWeb Internet Browser/3.7 http://www.QtWeb.net",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36",
        "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/532.2 (KHTML, like Gecko) ChromePlus/4.0.222.3 Chrome/4.0.222.3 Safari/532.2",
        "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.8.1.4pre) Gecko/20070404 K-Ninja/2.1.3",
        "Mozilla/5.0 (Future Star Technologies Corp.; Star-Blade OS; x86_64; U; en-US) iNet Browser 4.7",
        "Mozilla/5.0 (Windows; U; Windows NT 6.1; rv:2.2) Gecko/20110201",
        "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.8.1.13) Gecko/20080414 Firefox/2.0.0.13 Pogo/2.0.0.13.6866",
        # 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'
    ]
    user_agent = random.choice(user_agents).strip()
    return user_agent

def get_random_header(referer:str|None=None):
    headers = {
            "User-Agent": get_random_user_agent(),
            "Cookie": get_random_cookie(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Connection": "keep-alive",
            "Sec-Fetch-Mode": "navigate",  
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    if referer:
        headers["Referer"] = referer
    return headers


def extract_content_from_html(html: str,mode:Literal['md','bs','raw'] = 'md') -> str:
    """Extract and convert HTML content to Markdown format.

    Args:
        html: Raw HTML content to process

    Returns:
        Simplified markdown version of the content
    """
    # ret2= readabilipy.simple_tree_from_html_string(html)
    if mode =='md':
        article = readabilipy.simple_json_from_html_string(
        html, use_readability=True
        )
        if not article ["content"]:
            return "<error>Page failed to be simplified from HTML</error>"
        content = markdownify.markdownify(
            article ["content"],
            heading_style=markdownify.ATX,
        )
    elif mode =='bs':
        content = BeautifulSoup(html, "lxml").get_text(strip = True)
    else:
        content = html
    return content
    

async def afetch_url(
    url: str, headers: dict={}, parse_mode: Literal['md','bs','raw'] = 'bs', proxy_url: str | None = None
) -> Tuple[str, str]:
    """
    Fetch the URL and return the content in a form ready for the LLM, as well as a prefix string with status information.
    """
    async with aiohttp.ClientSession(proxy=proxy_url) as session:
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True
            ) as response:
                page_raw = await response.text()
                status_code = response.status

                if status_code >= 400:
                    raise aiohttp.ClientError(
                        f"Failed to fetch {url} - status code {status_code}"
                    )
        except aiohttp.ClientError as e:
            raise aiohttp.ClientError(f"Failed to fetch {url}: {e!r}")

    content_type = response.headers.get("content-type", "")
    is_page_html = (
        "<html" in page_raw[:100] or "text/html" in content_type or not content_type
    )
    if is_page_html and parse_mode != 'raw':
        return extract_content_from_html(page_raw, parse_mode), ""

    return (
        page_raw,
        f"Content type {content_type} cannot be simplified to markdown, but here is the raw content:\n",
    )

async def afetch_batch(
    results: List[Dict],
    max_parallel: int = 5,
    parse_mode: Literal['md', 'bs', 'raw'] = 'bs',
    proxy_url: str | None = None
) -> List[Document]:
    """异步获取所有URL内容，保持与 results 一一对应"""
    urls = [site.get('url') for site in results]  # 保持顺序，允许 None
    semaphore = asyncio.Semaphore(max_parallel)

    async def fetch_page(url: str | None) -> str | None:
        if not url:
            return None
        async with semaphore:
            try:
                content, prefix = await afetch_url(
                    url,
                    get_random_header(),
                    parse_mode,
                    proxy_url
                )
                return content.strip() if content else None
            except Exception as e:
                # print(f"Failed to fetch {url}: {e}")
                return None  # 保留位置，返回 None 表示失败

    # 创建异步任务列表（保持与 results 顺序一致）
    tasks = [fetch_page(url) for url in urls]
    contents = await asyncio.gather(*tasks, return_exceptions=True)

    # 构建 Document 列表，与 results 一一对应
    documents = []
    for i, (content, site) in enumerate(zip(contents, results)):
        if isinstance(content, Exception) or content is None:
            # 失败或无内容，插入空 Document 或 None（根据你的下游需求）
            doc = Document(
                page_content="",
                metadata={
                    "error": str(content) if isinstance(content, Exception) else "Empty or fetch failed",
                    "index": i,  # 可选：标记原始索引
                    "rank":site.get('rank',""),
                    "abstract": site.get('abstract',""),
                    "title": site.get('title',""),
                    "url": site.get('url',""),
                    "source": site.get('source',"")
                }
            )
        else:
            doc = Document(
                page_content=content,
                metadata={
                    "index": i,
                    "rank":site.get('rank',""),
                    "abstract": site.get('abstract',""),
                    "title": site.get('title',""),
                    "url": site.get('url',""),
                    "source": site.get('source',"")
                }
            )
        documents.append(doc)
    return documents



def bad_links(link: str) -> bool:
    """Filter links from searXNG search results"""
    ## 存在zhihu、wenku、sogou等特殊字符，过滤
    bad_keys = ["zhihu","wenku","sogou","zhidao.baidu"]
    if any(key in link for key in bad_keys):
        return True
    return False   

# 注册为系统工具
@register_tool(
    group="Search",
    name="SearXNG Search",
    description="是一个免费的互联网元搜索引擎",
    args_model=List[Document]
)
async def searxng_search(query: str = Field(..., description="搜索关键词"), max_results: int = Field(10, description="搜索结果数量")) -> list[Document]:
    """执行 SearXNG 搜索"""
    try:
        results = await asearch_web(query, ["general", "news"],num_results=max_results)    
        flatten_results = []
        for category in results:
            flatten_results.extend(results[category])
        # 过滤掉特殊字符
        results = [i for i in flatten_results if not bad_links(i["link"])]
        # print("========================")
        # print(f"searXNG_links {query} 原始结果数量: {len(flatten_results)} 过滤后数量: {len(results)}")
        # print("========================")
        for res in results:
            res["url"] = res["link"]
            res["abstract"] = res["snippet"]
            res["source"] = res["link"]
        documents = await afetch_batch(results)
        return documents
    except Exception as e:
        return []
