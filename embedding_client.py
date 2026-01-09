from typing import Dict, List, Tuple,Any, Union, Optional, Any  
from pydantic import BaseModel
from loguru import logger
import aiohttp
import requests
import asyncio
from dataclasses import dataclass


@dataclass  
class TEIEmbeddingConfig:  
    """Text Embeddings Inference配置"""  
    base_url: Optional[str] = 'http://192.168.10.137:8002'  
    api_key: Optional[str] = None  
    timeout: int = 60  


class TEIEmbedding():  
    """异步Text Embeddings Inference客户端"""  
      
    def __init__(self, config:Union[TEIEmbeddingConfig,dict,None] = None):  
        """  
        初始化异步TEI客户端  
          
        Args:  
            config: TEI配置，如果为None则使用默认配置  
        """
        if config and isinstance(config, dict):
            config = TEIEmbeddingConfig(**config)
        elif config and isinstance(config, TEIEmbeddingConfig):
            pass
        else:
            config = TEIEmbeddingConfig() 
        self.config = config
        self.http_base_url = self.config.base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}  
          
        if self.config.api_key:  
            self.headers["Authorization"] = f"Bearer {self.config.api_key}"  
              
        # 会话将在第一次调用时创建  
        self._session = None

    async def __aenter__(self):
        """进入with上下文时自动调用"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出with上下文时自动调用"""
        await self.close()
        if exc_type is not None:
            logger.error(f"TEIClient上下文发生异常: {exc_type}, {exc_val}")
        return False  # 不抑制异常
    
    def _get_session(self):  
        """获取或创建aiohttp会话"""  
        if self._session is None or self._session.closed:  
            self._session = aiohttp.ClientSession(headers=self.headers)  
        return self._session  
      
    async def close(self):  
        """关闭客户端连接"""  
        if self._session is not None and not self._session.closed:  
            await self._session.close()  
            self._session = None 
          

    def embed(self,   
                   inputs: Union[str, List[str]],   
                   truncate: bool = True,   
                   normalize: bool = True,  
                   truncation_direction: str = "Right") -> List[List[float]]:  
        """通过HTTP API获取嵌入向量"""  
        payload = {  
            "inputs": inputs,  
            "truncate": truncate,  
            "normalize": normalize,  
            "truncation_direction": truncation_direction  
        }  
          
        response = requests.post(  
            f"{self.http_base_url}/embed",  
            headers=self.headers,  
            json=payload,  
            timeout=self.config.timeout  
        )  
          
        if response.status_code != 200:  
            raise Exception(f"Embedding请求失败: {response.status_code}, {response.text}")  
          
        return response.json()  
   
    def rerank(self,   
                    query: str,   
                    texts: List[str],   
                    truncate: bool = True,  
                    raw_scores: bool = False,  
                    return_text: bool = True,  
                    truncation_direction: str = "Right") -> List[Dict[str, Any]]:  
        """通过HTTP API进行文本重排序"""  
        payload = {  
            "query": query,  
            "texts": texts,  
            "truncate": truncate,  
            "raw_scores": raw_scores,  
            "return_text": return_text,  
            "truncation_direction": truncation_direction  
        }  
          
        response = requests.post(  
            f"{self.http_base_url}/rerank",  
            headers=self.headers,  
            json=payload,  
            timeout=self.config.timeout  
        )  
          
        if response.status_code != 200:  
            raise Exception(f"Rerank请求失败: {response.status_code}, {response.text}")  
          
        return response.json()  


    async def aembed(self,   
                         inputs: Union[str, List[str]],   
                         truncate: bool = True,   
                         normalize: bool = True,  
                         truncation_direction: str = "Right") -> List[List[float]]:  
        """通过HTTP API异步获取嵌入向量"""  
        payload = {  
            "inputs": inputs,  
            "truncate": truncate,  
            "normalize": normalize,  
            "truncation_direction": truncation_direction  
        }  
          
        session = self._get_session()  
        async with session.post(  
            f"{self.http_base_url}/embed",  
            json=payload,  
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)  
        ) as response:  
            if response.status != 200:  
                error_text = await response.text()  
                raise Exception(f"Embedding请求失败: {response.status}, {error_text}")  
              
            return await response.json()  
     

    async def arerank(self,   
                          query: str,   
                          texts: List[str],   
                          truncate: bool = True,  
                          raw_scores: bool = False,  
                          return_text: bool = True,  
                          truncation_direction: str = "Right") -> List[Dict[str, Any]]:  
        """通过HTTP API异步进行文本重排序"""  
        payload = {  
            "query": query,  
            "texts": texts,  
            "truncate": truncate,  
            "raw_scores": raw_scores,  
            "return_text": return_text,  
            "truncation_direction": truncation_direction  
        }  
          
        session = self._get_session()  
        async with session.post(  
            f"{self.http_base_url}/rerank",  
            json=payload,  
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)  
        ) as response:  
            if response.status != 200:  
                error_text = await response.text()  
                raise Exception(f"Rerank请求失败: {response.status}, {error_text}")  
              
            return await response.json()  


    #region 兼容langchain_core Embedding接口
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """
        return self.embed(inputs=texts)
    
    def embed_query(self, text: str) -> list[float]:
        """Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """
        embeddings =  self.embed(inputs=text)
        return embeddings[0]
    
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Asynchronous Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """
        return await self.aembed(inputs=texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Asynchronous Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """
        embeddings =  await self.aembed(inputs=text)
        return embeddings[0]
    #endregion


class TextEmbedding:
          
    def __init__(self, config:Union[TEIEmbeddingConfig,dict,None] = None):  
        """  
        初始化异步TEI客户端  
          
        Args:  
            config: TEI配置，如果为None则使用默认配置  
        """
        if config and isinstance(config, dict):
            config = TEIEmbeddingConfig(**config)
        elif config and isinstance(config, TEIEmbeddingConfig):
            pass
        else:
            config = TEIConfig() 
        self.config = config
        self.http_base_url = self.config.base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}  
          
        if self.config.api_key:  
            self.headers["Authorization"] = f"Bearer {self.config.api_key}"  
              
        # 会话将在第一次调用时创建  
        self._session = None

    async def __aenter__(self):
        """进入with上下文时自动调用"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出with上下文时自动调用"""
        await self.close()
        if exc_type is not None:
            logger.error(f"TEIClient上下文发生异常: {exc_type}, {exc_val}")
        return False  # 不抑制异常
    
    def _get_session(self):  
        """获取或创建aiohttp会话"""  
        if self._session is None or self._session.closed:  
            self._session = aiohttp.ClientSession(headers=self.headers)  
        return self._session  
      
    async def close(self):  
        """关闭客户端连接"""  
        if self._session is not None and not self._session.closed:  
            await self._session.close()  
            self._session = None 
          

    def embed(self,inputs: Union[str, List[str]]) -> List[List[float]]:  
        """通过HTTP API获取嵌入向量"""  
        if isinstance(inputs,str):
            inputs = [inputs]
        
        results = []
        for i,d in enumerate(inputs):
            payload = {  
                "data": 
                    {
                        "id": str(i),
                        "text": d
                    } 
            }  
            response = requests.post(  
                f"{self.http_base_url}",  
                headers=self.headers,  
                json=payload,  
                timeout=self.config.timeout  
            )
            if response.status_code != 200:  
                raise Exception(f"Embedding请求失败: {response.status_code}, {response.text}")  
          
            results.append(response.json()['data']['fields']['TextVectors'])
        
        return results
   
    async def aembed(self, inputs: Union[str, List[str]]) -> List[List[float]]:
        """通过HTTP API异步获取嵌入向量"""
        if isinstance(inputs, str):
            inputs = [inputs]

        tasks = []
        session = self._get_session()  # 复用 session，不要在循环里反复获取

        for i, text in enumerate(inputs):
            payload = {
                "data": {
                    "id": str(i),
                    "text": text
                }
            }
            task = session.post(
                self.http_base_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
            tasks.append(task)

        # 并发执行所有请求
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                print(f"❌ 请求失败 (索引 {i}): {resp}")
                # 可选：填充空向量、跳过、或抛出异常
                results.append([])  # 或 raise resp
                continue

            try:
                data = await resp.json()  # 👈 关键：必须 await 读取响应体
                # print(data)
                # 根据你的 API 返回结构调整下面这行 👇
                # 示例：假设返回 {"embedding": [0.1, 0.2, ...]}
                embedding = data.get("data", {}).get("fields", {}).get('TextVectors',[])
                
                if not isinstance(embedding, list) or len(embedding) == 0:
                    print(f"⚠️ 无效向量 (索引 {i}): {data}")
                    embedding = []
                results.append(embedding)
            except Exception as e:
                print(f"❌ 解析失败 (索引 {i}): {e}")
                results.append([])

        return results
     

   


    #region 兼容langchain_core Embedding接口
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """
        return self.embed(inputs=texts)
    
    def embed_query(self, text: str) -> list[float]:
        """Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """
        return self.embed(inputs=text)[0]
    
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Asynchronous Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """
        return await self.aembed(inputs=texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Asynchronous Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """
        embeddings =await self.aembed(inputs=text)
        return embeddings[0]
    #endregion


async def main():
    async with  TEIEmbedding(TEIEmbeddingConfig(base_url="http://192.168.10.137:8002")) as client:
        embeddings = await client.aembed("为这个句子生成表示以用于检索相关文章：军博")  
        print(f"Embedding维度: {len(embeddings[0])}")   
        batch_embeddings = await client.aembed(["What is deep learning?", "What is machine learning?"])  
        print(f"批量Embedding结果数量: {len(batch_embeddings)}")  
      
if __name__ == "__main__":
    # 创建客户端  
    asyncio.run(main())
    