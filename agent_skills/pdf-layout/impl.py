import os
from pydantic import BaseModel
from typing import List,Any,Dict,Optional,Union
import aiohttp
from loguru import logger
import aiofiles
import time
import json
import re
import asyncio

class LayoutConfig(BaseModel):
    api : str 

# layout api 的接口定义
class APIlayoutItemData(BaseModel):
    id : int
    text: str
    type : str 

class APILayoutData(BaseModel):
    cost_time : str
    result : List[APIlayoutItemData]
    
class APIlayoutResult(BaseModel):
    code : int
    message : str
    data: Optional[Union[APILayoutData,str]]=None


class HDResorceLayoutResult(BaseModel):
    status:int = 0
    msg:str
    layout_text : str


class HDResourceLayoutFields(BaseModel):
    fields : Optional[HDResorceLayoutResult] = None

from assistant.skills.context import ServiceContext
from assistant.skills.tool import CallToolResult, skill_tool

class HDLayout():
    def __init__(self,config:LayoutConfig|Dict,*args,**kwargs ) -> None:
        if isinstance(config,dict):
            config = LayoutConfig(**config)
        super().__init__()
        self.api = config.api.rstrip('/')
        self.api = 'http://192.168.10.236:8111'

    def build_show_text(self, *args, **kwargs) -> str:
        return'晓答正在为您全力解析文档...'
    
    async def submit(self,file_path: str):
        """
        异步请求PDF处理接口
        :param file_path: 本地PDF文件路径
        """
        form_data = aiohttp.FormData()
        # 异步读取文件
        async with aiofiles.open(file_path, "rb") as f:
            file_content = await f.read()
            form_data.add_field(
                name="file",
                value=file_content,
                filename=file_path.split("/")[-1],
                content_type="application/pdf"
            )

        # 创建异步Session并发送请求
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url=self.api +"/api/v1/process/pdf",
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)  # 设置30秒超时
                ) as response:
                    # 检查响应状态码
                    if response.status == 200:
                        # 解析JSON响应（接口返回任务ID/状态等）
                        result = await response.json()
                        print("请求成功，返回结果：", result)
                        return result
                    else:
                        print(f"请求失败，状态码：{response.status}，响应内容：{await response.text()}")
            except aiohttp.ClientError as e:
                print(f"网络请求异常：{str(e)}")
            except Exception as e:
                print(f"未知错误：{str(e)}")
         
    async def check_status(self,task_id:str):
        """
        异步检查任务状态接口
        :param task_id: 任务ID
        """
        # 创建异步Session并发送请求
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url=self.api +f"/api/v1/tasks/{task_id}",
                    timeout=aiohttp.ClientTimeout(total=10)  # 设置10秒超时
                ) as response:
                    # 检查响应状态码
                    if response.status == 200:
                        # 解析JSON响应（接口返回任务状态等）
                        result = await response.json()
                        print("请求成功，返回结果：", result)
                        return result
                    else:
                        print(f"请求失败，状态码：{response.status}，响应内容：{await response.text()}")
            except aiohttp.ClientError as e:
                print(f"网络请求异常：{str(e)}")
            except Exception as e:
                print(f"未知错误：{str(e)}")

    async def get_result(self,task_id:str):
        """
        异步获取任务结果接口
        :param task_id: 任务ID
        """
        # 创建异步Session并发送请求
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url=self.api +f"/api/v1/tasks/{task_id}/result",
                    timeout=aiohttp.ClientTimeout(total=10)  # 设置10秒超时
                ) as response:
                    # 检查响应状态码
                    if response.status == 200:
                        # 解析JSON响应（接口返回任务结果等）
                        result = await response.json()
                        print("请求成功，返回结果：", result)
                        return result
                    else:
                        print(f"请求失败，状态码：{response.status}，响应内容：{await response.text()}")
            except aiohttp.ClientError as e:
                print(f"网络请求异常：{str(e)}")
            except Exception as e:
                print(f"未知错误：{str(e)}")
    
    async def process_pdf_workflow(self, file_path: str, poll_interval=2, timeout=60):
        """
        全流程处理函数：提交 -> 轮询 -> 获取结果
        :param file_path: 文件路径
        :param poll_interval: 轮询间隔（秒）
        :param timeout: 最大等待时间（秒）
        """
        print(f"--- 开始处理文件: {file_path} ---")
        
        # 1. 提交任务
        submit_resp = await self.submit(file_path)
        if not submit_resp:
            print("提交任务失败，流程终止")
            return None
            
        # 假设接口返回格式为 {"code": 200, "data": {"task_id": "xxx"}}
        # 请根据实际情况修改取值逻辑
        task_id = submit_resp.get("task_id") 
        if not task_id:
            print("未能获取任务ID，流程终止")
            return None

        print(f"任务已提交，Task ID: {task_id}，开始轮询状态...")

        # 2. 轮询状态
        start_time = time.time()
        while True:
            # 检查超时
            if time.time() - start_time > timeout:
                print(f"任务处理超时（>{timeout}s）")
                return None

            # 查询状态
            status_resp = await self.check_status(task_id)
            if not status_resp:
                print("获取状态失败，稍后重试...")
                await asyncio.sleep(poll_interval)
                continue

            # 假设状态字段在 status_resp["data"]["status"]
            # 常见的状态值：PENDING, PROCESSING, SUCCESS, FAILED
            status = status_resp.get("status")
            cost_time = status_resp.get("cost_time")
            message = status_resp.get("message")
            
            if status == "completed":
                print("任务处理完成！")
                break
            elif status in ["failed",'error','cancelled']:
                print("任务处理失败，服务端返回错误。")
                return None
            elif status in ["pending", "processing"]:
                print(f"当前状态: {status}，等待 {poll_interval} 秒... ,用时：{cost_time} ,{message}")
                # 关键：释放控制权，让出事件循环，避免阻塞
                await asyncio.sleep(poll_interval)

        # 3. 获取结果
        final_result = await self.get_result(task_id)
        print("--- 流程结束 ---")
        return final_result
    
    def clean_document_content(self,doc_data: dict|str) -> str:
        """
        将文档解析的JSON结构转换为纯文本格式，用于LLM问答。
        
        Args:
            doc_data: 包含 'pages' 和 'start_page' 的字典结构
        
        Returns:
            清洗并格式化后的字符串
        """
        if doc_data and isinstance(doc_data, str):
            doc_data = json.loads(doc_data)
            
        if not doc_data or 'pages' not in doc_data:
            return ""

        formatted_lines = []
        
        # 1. 对页面进行排序 (page_1, page_2, ..., page_10)
        # 使用正则提取数字进行排序，防止 page_10 排在 page_2 前面
        page_keys = sorted(doc_data['pages'].keys(), 
                        key=lambda x: int(re.search(r'\d+', x).group()))

        for page_key in page_keys:
            page_num = re.search(r'\d+', page_key).group()
            page_items = doc_data['pages'][page_key]
            
            # 添加分页标记 (有助于RAG检索时定位页码)
            formatted_lines.append(f"\n\n--- 第 {page_num} 页 ---\n")
            
            # 按 id 排序，确保同一页内的阅读顺序正确 (通常 id 是按阅读顺序生成的)
            page_items.sort(key=lambda x: x.get('id', 0))

            for item in page_items:
                text = item.get('text', '')
                item_type = item.get('type', 'text')

                if not text:
                    continue
                
                text = text.strip()
                # 2. 根据类型进行格式化
                if item_type == 'title_level_1':
                    # 一级标题加 Markdown 标记
                    formatted_lines.append(f"\n# {text}\n")
                
                elif item_type == 'footnote':
                    # 脚注可以加个标记，或者放在方括号里
                    formatted_lines.append(f"\n[脚注: {text}]")
                
                elif item_type == 'text':
                    # 普通文本，处理可能存在的跨页断句问题（视情况而定，这里简单连接）
                    # 这里的text已经是段落了，直接添加
                    formatted_lines.append(text)
                
                else:
                    # 其他类型兜底
                    formatted_lines.append(text)

        # 3. 合并文本，处理多余换行
        full_text = "\n".join(formatted_lines)
        
        # 移除连续超过3个的换行符，保持紧凑
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        
        return full_text.strip()
    
    async def layout(self,query):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api,data=query) as resp:
                    response = await resp.json()
            
            if response['code']>0:
                response = APIlayoutResult.model_validate(response)

                if response.code:
                    logger.debug(f"{type(self).__name__} use {response.data.cost_time}")
                    return response.data.result
                else:
                    return f'文档解析失败'
            else:
                msg = response['message']
                logger.error(f'文档解析失败:{msg}')
                return f'文档解析失败'
            
        except Exception as e:
            logger.error(f'文档解析失败:{e}')
            return '文档解析失败'
        
    async def __call__(self,file_path:str, server_type:str, *args, **kwargs):
        if file_path : 
            try:
                full_path = file_path if file_path.startswith("/mnt") else os.path.join("/mnt", file_path.lstrip("/"))
                result = await self.process_pdf_workflow(full_path)
                clean_document_content = self.clean_document_content(result)
                if not clean_document_content:
                    return HDResorceLayoutResult(status=0,msg="文档解析失败",layout_text='')
                response = HDResorceLayoutResult(status=1,msg="文档解析成功",layout_text=clean_document_content)
                return response
            
            except Exception as e:
                logger.error(f"处理PDF文件失败: {e}")
                return HDResorceLayoutResult(status=0,msg="文档解析失败",layout_text='')
        else :
            response = None
        return response

layout_service = HDLayout(LayoutConfig(api="http://192.168.10.236:8111"))

@skill_tool(
    description="Parse a PDF file to extract text.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string", 
                "description": "Path to PDF. Check user input first, then shared_memory['_current_file_path']."
            },
            "server_type": {"type": "string", "default": "show"}
        },
        "required": []  # file_path 设为非必填，允许代码层兜底
    }
)
async def process_pdf_parser(file_path: str = None,server_type:str = 'show',ctx:ServiceContext=None):
    """
    PDF 解析工具，包含多级路径查找策略。
    """
    try:
        # 1. 尝试从参数获取 (LLM 传入)
        final_path = file_path
        # 2. 尝试从 Shared Memory 获取 (如果 LLM 没传)
        if not final_path and ctx:
            final_path = ctx.get_state_value("_current_file_path")
        # 3. 尝试从 Request Context 透传获取 (如果 Shared Memory 也没存)
        if not final_path and ctx and ctx.request:
            final_path = ctx.request.file_path
            
        # 4. 最终检查
        if not final_path:
            return "无法获取文件路径：请提供文件路径或确保已上传文件。"
        
        layoutResult = await layout_service(file_path=final_path,server_type=server_type)
        if layoutResult:
            if layoutResult.status == 1:
                doc_content=layoutResult.layout_text
        else:
            doc_content = f'无法获取上传的文档的内容。'
                 
        return doc_content      

    except Exception as e:
        logger.error(str(e))

