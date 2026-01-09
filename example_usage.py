import asyncio
from api_client import ApiClient

async def main():
    # 初始化客户端
    client = ApiClient("api_config_example.yaml")

    # 使用 Context Manager 自动管理 Session 关闭
    async with client:
        
        # 1. 异步调用 POST (带 Body 和 Token)
        print("--- Async Search ---")
        res = await client.request("search_doc", json={"search_word": "澳门"})
        print(res)

        # 2. 异步调用 POST (带 Body 和 Token)
        print("\n--- Async Create ---")
        payload = {"product_id": 123, "amount": 1}
        try:
            res = await client.request("create_order", json=payload, token="secret_token_abc")
            print(res)
        except Exception as e:
            print(f"Create failed: {e}")

        # 3. 异步调用 GET (带 Path Params)
        # 即使 user_id 包含特殊字符，Client 也会自动编码
        print("\n--- Async Path Params ---")
        res = await client.request("get_user_detail", path_params={"user_id": "user@domain.com"}) 
        print(res)

def sync_usage():
    print("\n=== Sync Usage Mode ===")
    client = ApiClient("api_config.yaml")
    
    # 同步调用 (底层使用 requests)
    res = client.request_sync("search_users", params={"q": "java"})
    print(res)

if __name__ == "__main__":
    # 运行异步示例
    asyncio.run(main())
    
    # 运行同步示例
    sync_usage()