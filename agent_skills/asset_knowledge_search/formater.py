import asyncio
from typing import List, Optional, Union, Any, Dict
from pydantic import BaseModel, Field, HttpUrl
from .schema import (
    LibraryItem, ResourceItem, FileItem, APISearchResultData, RESOURCE_TYPE_MAP,
    ResourceStatisticData, KGOverviewData, DocSearchResult, TagSearchItem,
    ResourceTypeStatistic, ResourceTopItem, DocFileInfo,ResourceLibraryCount,ResourceTop
)

class ResultFormatter:
    """负责将结构化数据转换为 LLM 易读的文本格式"""

    # ==================== 基础格式化方法 ====================

    @staticmethod
    def get_resource_type_text(type_id: Union[int, str]) -> str:
        return RESOURCE_TYPE_MAP.get(int(type_id), "未知")

    @staticmethod
    def get_asset_type_text(type_id: Union[int, str]) -> str:
        """获取资产类型文本"""
        ASSET_TYPE_MAP = {1: '资产', 2: '资产文件', 3: '专题库'}
        return ASSET_TYPE_MAP.get(int(type_id), "未知")

    @staticmethod
    def format_library(items: List[LibraryItem]) -> str:
        if not items: return ""
        lines = ["\n专题库列表如下："]
        for idx, item in enumerate(items, 1):
            lines.append(f"{idx}、专题库ID为：{item.library_id}，专题库名称为：{item.library_name}")
        lines.append(f"专题库总数为{len(items)}\n")
        return "\n".join(lines)

    @staticmethod
    def format_resource(items: List[ResourceItem]) -> str:
        if not items: return ""
        lines = ["\n数字资产列表如下："]
        for idx, item in enumerate(items, 1):
            type_text = ResultFormatter.get_resource_type_text(item.resource_type)
            lines.append(f"{idx}、数字资产ID为：{item.resource_id}，数字资产类型为：{type_text}，数字资产名称为：{item.resource_name}")
        lines.append(f"数字资产总数为{len(items)}\n")
        return "\n".join(lines)

    @staticmethod
    def format_file(items: List[FileItem]) -> str:
        if not items: return ""
        lines = ["\n文件列表如下："]
        for idx, item in enumerate(items, 1):
            type_text = ResultFormatter.get_resource_type_text(item.resource_type)
            content_preview = (item.content + item.content_fields)[:200].replace('\n', ' ')
            lines.append(
                f"{idx}、文件ID为：{item.resource_file_id}，文件类型为：{type_text}，"
                f"文件名为：{item.file_name}，文件内容摘要：{content_preview}，所属资产ID：{item.resource_id}"
            )
        lines.append(f"文件总数为{len(items)}\n")
        return "\n".join(lines)

    @classmethod
    def format_result(cls, data: APISearchResultData, query: str = "") -> str:
        parts = []
        if query:
            parts.append(f"搜索得到的数字系统内与 {query} 有关的数据如下：")

        parts.append(cls.format_resource(data.resource_list))
        parts.append(cls.format_file(data.resource_file_list))
        parts.append(cls.format_library(data.library_list))

        return "\n".join([p for p in parts if p])

    # ==================== 推荐格式化方法 ====================

    @staticmethod
    def format_recommend_file(items: List[FileItem]) -> str:
        """格式化推荐文件列表"""
        if not items: return ""
        lines = []
        for idx, item in enumerate(items, 1):
            lines.append(
                f"{idx}、文件名：{item.file_name}，"
                f"文件类型：{ResultFormatter.get_resource_type_text(item.resource_type)}，"
                f"文件内容：{item.content_fields}"
            )
        return "\n".join(lines)

    @classmethod
    def format_recommend_result(cls, data: APISearchResultData, query: str) -> tuple[str, bool]:
        """格式化推荐结果，返回 (文本, 是否有结果)"""
        parts = []
        has_result = False

        if data.library_list:
            parts.append(f"与{query}相关的专题库列表如下：\n")
            parts.append(cls.format_library(data.library_list))
            has_result = True
        else:
            parts.append(f"没有找到与{query}相关的专题库\n")

        if data.resource_list:
            parts.append(f"与{query}相关的数字资产列表如下：\n")
            parts.append(cls.format_resource(data.resource_list))
            has_result = True
        else:
            parts.append(f"没有找到与{query}相关的数字资产\n")

        if data.resource_file_list:
            parts.append(f"与{query}相关的文件列表如下：\n")
            parts.append(cls.format_recommend_file(data.resource_file_list))
            has_result = True
        else:
            parts.append(f"没有找到与{query}相关的文件\n")

        if not has_result:
            parts.append(f"因为没有找到任何相关的资源，所以没有可以推荐的内容。\n")

        return "\n".join(parts), has_result

    # ==================== 统计数据格式化方法 ====================

    @staticmethod
    def format_resource_library_count(data: ResourceLibraryCount) -> str:
        """格式化资源库统计"""
        res_info = ""
        res_info += f'系统中专题库总数：{data.library_count}\n'
        res_info += f'系统中数字资产总数：{data.resource_count}\n'
        res_info += f'系统中数字资产总计文件大小为：{data.resource_size}\n'
        return res_info

    @staticmethod
    def format_resource_top(data: ResourceTop) -> str:
        """格式化资源 Top 统计"""
        res_info = ""

        res_info += '申请次数最多的资产Top5：\n'
        for i, res in enumerate(data.apply_top):
            res_info += f'{i+1}、名称：{res.resource_name}，申请次数：{res.times}\n'

        res_info += '访问次数最多的资产Top5：\n'
        for i, res in enumerate(data.view_top):
            res_info += f'{i+1}、名称：{res.resource_name}，访问次数：{res.times}\n'

        res_info += '下载次数最多的资产Top5：\n'
        for i, res in enumerate(data.download_top):
            res_info += f'{i+1}、名称：{res.resource_name}，下载次数：{res.times}\n'

        return res_info

    @staticmethod
    def format_resource_type_statistic(items: List[ResourceTypeStatistic], title: str, type_key: str) -> str:
        """格式化资源类型统计"""
        if not items: return ""
        res_info = f'{title}:'
        total = 0
        for item in items:
            total += item.value
            res_info += f'\n{item.name}{type_key}总数为{item.value}'
        res_info += f'\n总数为：{total}\n'
        return res_info

    @classmethod
    def format_resource_statistic(cls, data: ResourceStatisticData, statistic_type: str) -> str:
        """格式化资源统计数据"""
        # 特殊类型的统计
        if statistic_type == 'resource_top' and data.resource_top:
            return cls.format_resource_top(data.resource_top)
        if statistic_type == 'resource_library_count' and data.resource_library_count:
            return cls.format_resource_library_count(data.resource_library_count)
        if statistic_type == 'apply_count' and data.apply_count is not None:
            return f'系统中资产利用申请次数:{data.apply_count}\n'
        if statistic_type == 'resource_download_count' and data.resource_download_count is not None:
            return f'系统中资产下载次数:{data.resource_download_count}\n'
        if statistic_type == 'everything_count' and data.everything_count is not None:
            return f'系统中图像训练库数量:{data.everything_count}\n'
        if statistic_type == 'face_count' and data.face_count is not None:
            return f'系统中人脸训练库数量:{data.face_count}\n'
        if statistic_type == 'ocr_type' and data.ocr_type is not None:
            return f'系统中OCR识别中的文字类别数:{data.ocr_type}\n'
        if statistic_type == 'resource_growth' and data.resource_growth is not None:
            return f'资产增长数:{data.resource_growth}\n'

        # 列表类型的统计
        if statistic_type == 'resource_count_by_type' and data.resource_count_by_type:
            return cls.format_resource_type_statistic(data.resource_count_by_type, '按资产类型统计资产数:', '类型数字资产')
        if statistic_type == 'resource_file_count_by_type' and data.resource_file_count_by_type:
            return cls.format_resource_type_statistic(data.resource_file_count_by_type, '按资产类型统计资产文件数:', '文件')
        if statistic_type == 'resource_file_count_by_ext' and data.resource_file_count_by_ext:
            return cls.format_resource_type_statistic(data.resource_file_count_by_ext, '按文件格式统计资产文件数:', '类型文件')

        return ""

    # ==================== 知识图谱格式化方法 ====================

    @classmethod
    def format_kg_overview(cls, data: KGOverviewData) -> str:
        """格式化知识图谱总览数据"""
        doc = f'知识图谱数据统计总览：\n'

        doc += f'知识图谱中的实体类型共有：{data.labelCount} 种，其中各类实体类型的实体数量为：\n'
        for k, v in data.labels.items():
            doc += f"实体类型为 {k} 的实体有 {v} 个\n"

        doc += f'知识图谱中的关系类型共有：{data.relTypeCount} 种，其中各类关系类型的关系数量为：\n'
        for k, v in data.relTypesCount.items():
            doc += f"关系类型为 {k} 的关系有 {v} 个\n"

        doc += f'知识图谱中的属性共有：{data.propertiesCount} 种\n'
        doc += f'其中各类实体属性数量为：\n'
        for np in data.nodeProperties:
            property_name = cls._translate_property_name(np.propertyName)
            doc += f'实体属性类型为 {property_name} 的属性有 {np.propertyObservations} 个\n'

        doc += f'其中各类关系属性数量为：\n'
        for np in data.relProperties:
            property_name = cls._translate_property_name(np.propertyName)
            doc += f'关系属性类型为 {property_name} 的属性有 {np.propertyObservations} 个\n'

        doc += f'实体总数为：{data.nodeCount}\n'
        doc += f'关系总数为：{data.relationCount}\n'
        doc += f"最后一次更新的时间为 {data.updateTime}，增加的实体数量为 {data.updateNodeCount}，增加的关系数量为 {data.updateRelCount}\n"

        doc += '按提及次数或关联关系最多实体列表为：\n'
        for i, anode in enumerate(data.nodeAroundRelCountTop10):
            node = anode.node
            doc += f'{i+1}、{node.entity}，按提及或关联关系数：{anode.nodeAroundRelCount}，类型：{node.entityType}\n'

        return doc + '\n'

    @staticmethod
    def _translate_property_name(name: str) -> str:
        """翻译属性名称"""
        translations = {
            'resource_id': '数字资产id',
            'graphName': '图谱名称',
            'entity_id': '实体id',
            'version': '版本',
            'entity': '实体',
            'resource_file_id': '资源文件id'
        }
        return translations.get(name, name)

    # ==================== 文档搜索格式化方法 ====================

    @staticmethod
    def format_doc_search_result(result: DocSearchResult, resource_file_ids: List[str]) -> str:
        """格式化文档搜索结果"""
        data = result.data
        if not data:
            return ""

        info = '通过查询得到的文档内容如下：\n'

        # 处理列表或单个数据
        items = data if isinstance(data, list) else [data]

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            status = item.get('status')
            if status != 1:
                # 未授权的文档
                idx = index if index < len(resource_file_ids) else 0
                file_id = resource_file_ids[idx] if resource_file_ids else "unknown"
                info += f'{index + 1}. 文件资源id：{file_id}，因该资源尚未申请利用，无法查看详情内容，要获取详情内容，需要申请文档权限。\n\n'
                continue

            # 已授权的文档
            file_info = item.get('file_info', {})
            if isinstance(file_info, dict):
                resource_id = file_info.get('resource_id', '')
                resource_file_id = file_info.get('resource_file_id', '')
                file_name = file_info.get('file_name', '')
                file_type = file_info.get('file_type', '')
                file_content = file_info.get('file_content', '')
                face_content = file_info.get('face_content', '')
                every_thing_content = file_info.get('every_thing_content', '')

                info += f'{index + 1}. 数字资产id：{resource_id}，文件资源id：{resource_file_id}，isCanDownload:True，名称为：{file_name}，类型为：{file_type}，内容为：{file_content}\n\n'

        return info

    @staticmethod
    def format_tag_search_result(items: List[TagSearchItem]) -> str:
        """格式化标签搜索结果"""
        if not items:
            return ""
        infos = ''
        for item in items:
            tags_txt = ','.join(item.tags) if item.tags else ''
            infos += f'资源id：{item.resource_file_id}，文档名称为：{item.file_name}，标签为：{tags_txt}\n'
        return infos

    # ==================== 列表页面格式化方法 ====================

    @staticmethod
    def format_asset_list(assets: List[Dict[str, Any]]) -> str:
        """格式化资产列表"""
        info = '当前页面包含的资产列表如下：'
        for i, res in enumerate(assets):
            res_info = f"{i + 1}. "
            for k, v in res.items():
                res_info = res_info + k + ":" + str(v) + '，'
            res_info = res_info[:-1] + '。 \n'
            info = info + res_info
        return info

    @staticmethod
    def format_page_list(assets: List[Dict[str, Any]], title: Optional[str] = None) -> str:
        """格式化页面列表"""
        info = ''
        if title:
            info = title
        for i, res in enumerate(assets):
            res_info = f"{i + 1}. "
            for k, v in res.items():
                if k in ('id', 'ID'):
                    continue
                res_info = res_info + k + ":" + str(v) + '，'
            res_info = res_info[:-1] + '。 \n'
            info = info + res_info
        info += f'共有{len(assets)}个数据'
        return info

    # ==================== 辅助工具方法 ====================

    @staticmethod
    def convert_docs_to_prompt_context(docs: List[Any]) -> str:
        """将文档列表转换为提示上下文"""
        context = []
        for i, doc in enumerate(docs):
            # 处理不同类型的文档对象
            if hasattr(doc, 'page_content'):
                text = doc.page_content.replace("\n", ",").replace("\\n", ",").replace("\r", "")
            elif isinstance(doc, dict):
                text = str(doc)
            else:
                text = str(doc)
            text = f"{i + 1}. {text}"
            context.append(text)
        return "\n".join(context)

    @staticmethod
    def safe_get(data: Dict[str, Any], key: str, default: Any = None) -> Any:
        """安全获取字典值"""
        if isinstance(data, dict):
            return data.get(key, default)
        return default