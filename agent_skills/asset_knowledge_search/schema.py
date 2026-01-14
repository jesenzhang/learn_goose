import asyncio
from typing import List, Optional, Union, Any, Dict
from pydantic import BaseModel, Field, HttpUrl


# --- 数据模型 (保持原有业务字段，增强类型定义) ---
class FileItem(BaseModel):
    resource_file_id: int
    resource_id: int
    resource_type: Union[int, str]
    file_name: str
    content: str = ""
    content_fields: str = ""
    score: float = 0.0
    view_url: Optional[str] = None
    # Doc search specific fields
    file_content: Optional[str] = None
    face_content: Optional[str] = None
    every_thing_content: Optional[str] = None
    file_type: Optional[str] = None
    isCanDownload: Optional[bool] = None

class ResourceItem(BaseModel):
    resource_id: int
    resource_name: str
    resource_type: Union[int, str]
    image: Optional[str] = None
    desc: str = ""

class LibraryItem(BaseModel):
    library_id: int
    library_name: str
    desc: str = ""

class ExhibitItem(BaseModel):
    exhibit_id:int
    exhibit_name: str
    exhibit_register_num:Optional[str] = ''
    image: Optional[str] = None
    content:Optional[str] = ''
    score : Optional[float] =0
    content_fields : Optional[str] = None
    
class APISearchResultData(BaseModel):
    library_list: List[Any] = []
    resource_list: List[Any] = []
    resource_file_list: List[Any] = []
    exhibit_list: Optional[List[Any]] = []

class APISearchResult(BaseModel):
    status: int
    msg: str
    data: APISearchResultData

class Document(BaseModel):
    """文档通用接口"""
    page_content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- 统计相关数据模型 ---
class ResourceTypeStatistic(BaseModel):
    """资源类型统计"""
    name: str
    value: int

class ResourceTopItem(BaseModel):
    """资源 Top 排行项"""
    resource_id: int
    resource_name: str
    times: int

class ResourceLibraryCount(BaseModel):
    """资源库统计"""
    library_count: int
    resource_count: int
    resource_size: str

class ResourceTop(BaseModel):
    """资源 Top 统计"""
    apply_top: List[ResourceTopItem] = []
    download_top: List[ResourceTopItem] = []
    view_top: List[ResourceTopItem] = []

class ResourceStatisticData(BaseModel):
    """统计数据"""
    resource_count_by_type: Optional[List[ResourceTypeStatistic]] = None
    resource_file_count_by_type: Optional[List[ResourceTypeStatistic]] = None
    resource_file_count_by_ext: Optional[List[ResourceTypeStatistic]] = None
    resource_library_count: Optional[ResourceLibraryCount] = None
    resource_top: Optional[ResourceTop] = None
    apply_count: Optional[int] = None
    resource_download_count: Optional[int] = None
    everything_count: Optional[int] = None
    face_count: Optional[int] = None
    ocr_type: Optional[int] = None
    resource_growth: Optional[int] = None

# --- 知识图谱相关数据模型 ---
class KGNodeProperty(BaseModel):
    """图谱节点属性"""
    propertyName: str
    propertyObservations: int

class KGNode(BaseModel):
    """图谱节点"""
    entity: str
    entityType: str
    entityId: str

class KGTopNode(BaseModel):
    """Top 节点"""
    node: KGNode
    nodeAroundRelCount: int

class KGOverviewData(BaseModel):
    """知识图谱总览数据"""
    labelCount: int
    labels: Dict[str, int]
    relTypeCount: int
    relTypesCount: Dict[str, int]
    propertiesCount: int
    nodeProperties: List[KGNodeProperty]
    relProperties: List[KGNodeProperty]
    nodeCount: int
    relationCount: int
    updateNodeCount: int
    updateRelCount: int
    updateTime: str
    nodeAroundRelCountTop10: List[KGTopNode]

# --- 文档搜索相关数据模型 ---
class DocFileInfo(BaseModel):
    """文档文件信息"""
    resource_id: int
    resource_file_id: str
    file_name: str
    file_type: str
    file_content: Optional[str] = None
    face_content: Optional[str] = None
    every_thing_content: Optional[str] = None

class DocSearchData(BaseModel):
    """文档搜索数据"""
    status: int
    file_info: Optional[DocFileInfo] = None

class DocSearchResult(BaseModel):
    """文档搜索结果"""
    data: Union[List[DocSearchData], DocSearchData, None]

# --- 标签搜索相关数据模型 ---
class TagSearchItem(BaseModel):
    """标签搜索项"""
    resource_file_id: int
    file_name: str
    tags: List[str]

# ==================== V2 API 数据模型 ====================
# 新版本 API (asset-search) 用于藏品和文档的智能检索

class ExhibitItem(BaseModel):
    """藏品项 (V2 API)"""
    exhibit_id: Optional[int] = None
    exhibit_name: Optional[str] = None
    content: str = ""
    category: Optional[str] = None
    era: Optional[str] = None
    material: Optional[str] = None
    # 原始数据保留
    raw_data: Dict[str, Any] = Field(default_factory=dict)

class ResourceV2Item(BaseModel):
    """数字资源项 (V2 API) - 文档、研究资料"""
    resource_file_id: Optional[int] = None
    file_name: Optional[str] = None
    resource_id: Optional[str] = None
    content: str = ""
    llm_summary: Optional[str] = None
    original_text: Optional[str] = None
    tags: List[str] = []
    # 原始数据保留
    raw_data: Dict[str, Any] = Field(default_factory=dict)

class ExhibitSearchResult(BaseModel):
    """藏品搜索结果 (V2 API)"""
    output_list: List[ExhibitItem] = []
    source_list: List[Dict[str, Any]] = []
    total: int = 0

class ResourceSearchResult(BaseModel):
    """文档搜索结果 (V2 API)"""
    output_list: List[ResourceV2Item] = []
    source_list: List[Dict[str, Any]] = []
    total: int = 0

# --- 常量定义 ---
RESOURCE_TYPE_MAP = {
    1: '图片', 2: '视频', 3: '文档', 4: '音频', 5: '3D', 6: '其他'
}
ASSET_TYPE_MAP = {
    1: '资产', 2: '资产文件', 3: '专题库'
}