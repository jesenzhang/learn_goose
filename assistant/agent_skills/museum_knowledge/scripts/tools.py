"""
博物馆知识和文物信息查询工具
"""

from typing import Dict, Any, Optional, List


async def search_artifact(
    query: str,
    era: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    _ctx=None
) -> str:
    """
    搜索文物信息

    Args:
        query: 搜索关键词
        era: 历史朝代（可选）
        category: 文物类别（可选）
        limit: 返回结果数量限制

    Returns:
        搜索结果列表
    """
    artifacts = [
        {
            "id": "A001",
            "name": "唐三彩骆驼载乐俑",
            "era": "唐代",
            "category": "陶俑",
            "material": "陶器",
            "location": "陕西历史博物馆",
            "description": "这件唐三彩骆驼载乐俑是唐代艺术的杰出代表，骆驼昂首嘶鸣，驼背上载着五位乐舞艺人。"
        },
        {
            "id": "A002",
            "name": "青花瓷缠枝莲纹瓶",
            "era": "明代",
            "category": "瓷器",
            "material": "陶瓷",
            "location": "故宫博物院",
            "description": "明代青花瓷的精品，瓶身绘有精美的缠枝莲纹，体现了明代青花瓷的高超工艺。"
        },
        {
            "id": "A003",
            "name": "青铜四羊方尊",
            "era": "商代",
            "category": "青铜器",
            "material": "青铜",
            "location": "中国国家博物馆",
            "description": "商代晚期青铜器珍品，四角各有一只羊头，造型独特，是商代青铜礼器的代表作品。"
        }
    ]

    filtered = artifacts
    if era:
        filtered = [a for a in filtered if a["era"] == era]
    if category:
        filtered = [a for a in filtered if a["category"] == category]
    if query:
        filtered = [a for a in filtered if query in a["name"] or query in a["description"]]

    result = f"找到 {len(filtered)} 件相关文物：\n\n"
    for artifact in filtered[:limit]:
        result += f"**{artifact['name']}** ({artifact['era']})\n"
        result += f"类别：{artifact['category']} | 材质：{artifact['material']}\n"
        result += f"收藏地：{artifact['location']}\n"
        result += f"简介：{artifact['description']}\n\n"

    return result


async def get_artifact_detail(artifact_id: str, _ctx=None) -> str:
    """
    获取文物详细信息

    Args:
        artifact_id: 文物 ID

    Returns:
        文物详细信息
    """
    artifact_db = {
        "A001": {
            "name": "唐三彩骆驼载乐俑",
            "era": "唐代（公元 618-907 年）",
            "category": "陶俑",
            "material": "三彩釉陶",
            "height": "56.2cm",
            "width": "48.8cm",
            "discovery": "1957年陕西省西安市唐墓出土",
            "location": "陕西历史博物馆",
            "description": "这件唐三彩骆驼载乐俑是唐代艺术的杰出代表。骆驼昂首嘶鸣，四肢强健有力，驼背上载着五位乐舞艺人，其中一位乐师在弹奏琵琶，其他四位在舞蹈。整件作品色彩鲜艳，造型生动，充分展现了唐代丝绸之路的文化交流盛况和当时社会的繁荣景象。",
            "significance": "唐代三彩陶器的代表作品，体现了唐代开放包容的文化特征和精湛的制陶工艺。"
        },
        "A002": {
            "name": "青花瓷缠枝莲纹瓶",
            "era": "明代永乐时期（公元 1403-1424 年）",
            "category": "瓷器",
            "material": "青花瓷",
            "height": "32cm",
            "width": "18cm",
            "discovery": "景德镇窑烧制",
            "location": "故宫博物院",
            "description": "明代永乐青花瓷的精品之作。瓶身采用典型的明代青花绘画技法，缠枝莲纹线条流畅，色彩浓艳。瓶口微撇，颈部修长，腹部饱满，整体造型优美端庄。青花发色浓艳，有铁锈斑，是永乐青花瓷的典型特征。",
            "significance": "代表了明代永乐时期青花瓷制作工艺的最高水平，是中国陶瓷史上的经典作品。"
        }
    }

    if artifact_id not in artifact_db:
        return f"未找到 ID 为 {artifact_id} 的文物"

    art = artifact_db[artifact_id]
    return f"""
**{art['name']}**

**历史时期：** {art['era']}
**类别：** {art['category']}
**材质：** {art['material']}
**尺寸：** 高 {art['height']}，宽 {art['width']}

**出土地点/烧制地：** {art['discovery']}
**收藏地：** {art['location']}

**详细介绍：**
{art['description']}

**历史价值：**
{art['significance']}
"""


async def get_exhibition_info(
    exhibition_type: Optional[str] = None,
    _ctx=None
) -> str:
    """
    获取展览信息

    Args:
        exhibition_type: 展览类型（常展/特展）

    Returns:
        展览信息列表
    """
    exhibitions = {
        "常展": [
            {
                "name": "中国古代文明展",
                "location": "第一展厅",
                "period": "长期展出",
                "highlights": ["三星堆青铜器", "秦兵马俑", "唐三彩"]
            },
            {
                "name": "丝绸之路文物展",
                "location": "第二展厅",
                "period": "长期展出",
                "highlights": ["丝绸残片", "波斯金币", "佛教造像"]
            }
        ],
        "特展": [
            {
                "name": "千年瓷韵 - 中国陶瓷艺术展",
                "location": "特展厅 A",
                "period": "2025年1月 - 2025年6月",
                "highlights": ["宋代汝窑", "元青花", "明清官窑"],
                "tickets": "成人票 50 元，优惠票 25 元"
            },
            {
                "name": "丝路遗珍 - 丝绸之路文物精品展",
                "location": "特展厅 B",
                "period": "2025年2月 - 2025年5月",
                "highlights": ["敦煌壁画摹本", "新疆出土文物", "西域佛教艺术"],
                "tickets": "成人票 80 元，优惠票 40 元"
            }
        ]
    }

    result = ""
    if exhibition_type:
        if exhibition_type in exhibitions:
            result = f"**{exhibition_type}列表：**\n\n"
            for ex in exhibitions[exhibition_type]:
                result += f"**{ex['name']}**\n"
                result += f"展厅：{ex['location']}\n"
                result += f"展期：{ex['period']}\n"
                result += f"重点展品：{', '.join(ex['highlights'])}\n"
                if 'tickets' in ex:
                    result += f"票价：{ex['tickets']}\n"
                result += "\n"
        else:
            result = f"未找到类型为 '{exhibition_type}' 的展览"
    else:
        for ex_type, ex_list in exhibitions.items():
            result += f"**{ex_type}列表：**\n\n"
            for ex in ex_list:
                result += f"• {ex['name']}（{ex['location']}）\n"
            result += "\n"

    return result


async def explain_era(era_name: str, _ctx=None) -> str:
    """
    讲解历史时期

    Args:
        era_name: 历史朝代或时期名称

    Returns:
        该历史时期的详细介绍
    """
    era_db = {
        "唐代": {
            "time": "公元 618 - 907 年",
            "duration": "约 290 年",
            "founding_emperor": "唐高祖李渊",
            "capital": "长安（今西安）",
            "characteristics": [
                "中国历史上的鼎盛时期之一",
                "政治清明，经济繁荣，文化昌盛",
                "开放包容，对外交流频繁",
                "诗歌艺术达到高峰（唐诗）",
                "制陶工艺发达（唐三彩）"
            ],
            "major_events": [
                "贞观之治（唐太宗）",
                "开元盛世（唐玄宗）",
                "安史之乱（转折点）",
                "与周边国家的和平交往"
            ]
        },
        "明代": {
            "time": "公元 1368 - 1644 年",
            "duration": "约 276 年",
            "founding_emperor": "明太祖朱元璋",
            "capital": "北京",
            "characteristics": [
                "中国历史上最后一个由汉族建立的大一统王朝",
                "中央集权制度高度发展",
                "郑和下西洋，对外交流活跃",
                "建筑艺术达到高峰（故宫）",
                "青花瓷制作工艺成熟"
            ],
            "major_events": [
                "推翻元朝统治",
                "靖难之役",
                "郑和七下西洋",
                "土木堡之变",
                "万历三大征"
            ]
        }
    }

    if era_name not in era_db:
        era_key = next((k for k in era_db.keys() if era_name in k), None)
        if era_key:
            era_name = era_key
        else:
            return f"暂无 '{era_name}' 的详细介绍"

    era = era_db[era_name]
    return f"""
**{era_name}（{era['time']}）**

**延续时间：** {era['duration']}
**开国皇帝：** {era['founding_emperor']}
**都城：** {era['capital']}

**时代特征：**
{chr(10).join(f'• {c}' for c in era['characteristics'])}

**重大事件：**
{chr(10).join(f'• {e}' for e in era['major_events'])}
"""


async def compare_artifacts(
    artifact_ids: List[str],
    _ctx=None
) -> str:
    """
    对比多个文物

    Args:
        artifact_ids: 文物 ID 列表

    Returns:
        对比分析结果
    """
    artifact_db = {
        "A001": {"name": "唐三彩骆驼载乐俑", "era": "唐代", "category": "陶俑", "material": "三彩釉陶"},
        "A002": {"name": "青花瓷缠枝莲纹瓶", "era": "明代", "category": "瓷器", "material": "青花瓷"},
        "A003": {"name": "青铜四羊方尊", "era": "商代", "category": "青铜器", "material": "青铜"}
    }

    artifacts_to_compare = []
    for aid in artifact_ids:
        if aid in artifact_db:
            artifacts_to_compare.append(artifact_db[aid])

    if len(artifacts_to_compare) < 2:
        return "请至少选择两件文物进行对比"

    result = "**文物对比分析：**\n\n"

    result += "| 文物名称 | 历史时期 | 类别 | 材质 |\n"
    result += "|---------|---------|------|------|\n"
    for art in artifacts_to_compare:
        result += f"| {art['name']} | {art['era']} | {art['category']} | {art['material']} |\n"

    result += "\n**分析：**\n\n"

    eras = [art['era'] for art in artifacts_to_compare]
    materials = [art['material'] for art in artifacts_to_compare]
    categories = [art['category'] for art in artifacts_to_compare]

    result += f"**历史跨度：** 从 {min(eras)} 到 {max(eras)}，跨越了约 {len(set(eras))} 个主要历史时期。\n\n"
    result += f"**材质对比：** 包括 {', '.join(set(materials))}，反映了中国古代工艺技术的发展历程。\n\n"
    result += f"**功能分类：** {', '.join(set(categories))}，展示了不同时期的社会功能和文化特征。\n\n"

    return result
