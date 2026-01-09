import json
# import requests  # 实际对接时需要用到

# 模拟数据库 (实际使用时，请替换为你的真实 API 调用)
MOCK_DB = [
    {"id": "A001", "name": "青花缠枝莲纹瓶", "era": "清朝", "category": "瓷器", "desc": "瓶直口，长颈，圆腹，圈足。通体绘青花缠枝莲纹..."},
    {"id": "A002", "name": "翠玉白菜", "era": "清朝", "category": "玉器", "desc": "利用翡翠天然的色泽雕琢出白菜的形状..."},
    {"id": "A003", "name": "毛公鼎", "era": "西周", "category": "青铜器", "desc": "腹内铸有铭文32行，共499字..."},
    {"id": "A004", "name": "富春山居图", "era": "元朝", "category": "书画", "desc": "黄公望为无用师所绘，以浙江富春江为背景..."},
]

def search_artifacts(keyword: str = None, era: str = None, category: str = None):
    """
    根据关键词、朝代或类别搜索藏品。用于推荐或查找列表。
    """
    # === 真实环境请替换为类似代码 ===
    # params = {"keyword": keyword, "era": era, "category": category}
    # res = requests.get("http://api.museum.com/search", params=params)
    # return res.json()
    # ==============================

    results = []
    for item in MOCK_DB:
        match = True
        if keyword and keyword not in item["name"]: match = False
        if era and era != item["era"]: match = False
        if category and category != item["category"]: match = False
        
        if match:
            # 搜索列表通常只返回摘要信息，节省 Token
            results.append({"id": item["id"], "name": item["name"], "era": item["era"]})
    
    if not results:
        return "未找到符合条件的藏品。"
    
    return json.dumps(results, ensure_ascii=False)

def get_artifact_detail(artifact_id: str):
    """
    根据藏品ID获取详细信息（包含详细描述、历史背景等）。
    """
    # === 真实环境请替换为类似代码 ===
    # res = requests.get(f"http://api.museum.com/detail/{artifact_id}")
    # return res.json()
    # ==============================

    for item in MOCK_DB:
        if item["id"] == artifact_id:
            return json.dumps(item, ensure_ascii=False)
    
    return "错误：未找到指定ID的藏品。"