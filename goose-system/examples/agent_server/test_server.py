"""
Simple test script for Goose Agent Server

Tests basic server functionality.
"""

import asyncio
import aiohttp
import json

BASE_URL = "http://127.0.0.1:8080/api/v1"
API_URL = "http://127.0.0.1:8080"


async def test_register(username: str, password: str):
    """Test user registration"""
    print(f"Testing user registration for {username}...")
    async with aiohttp.ClientSession() as session:
        data = {
            "username": username,
            "password": password,
            "email": f"{username}@test.com"
        }
        async with session.post(f"{BASE_URL}/auth/register", json=data) as response:
            print(f"  Status: {response.status}")
            result = await response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            return response.status in (200, 201), result.get("success", False)


async def test_login(username: str, password: str):
    """Test user login"""
    print(f"Testing login for {username}...")
    async with aiohttp.ClientSession() as session:
        data = {
            "username": username,
            "password": password
        }
        async with session.post(f"{BASE_URL}/auth/login", json=data) as response:
            print(f"  Status: {response.status}")
            result = await response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            if result.get("success"):
                return result.get("session_id")
            return None


async def test_profile(session_id: str):
    """Test user profile"""
    print(f"Testing profile with session {session_id}...")
    async with aiohttp.ClientSession() as session:
        params = {"session_id": session_id}
        async with session.get(f"{BASE_URL}/auth/profile", params=params) as response:
            print(f"  Status: {response.status}")
            result = await response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            return response.status == 200


async def test_logout(session_id: str):
    """Test logout"""
    print(f"Testing logout with session {session_id}...")
    async with aiohttp.ClientSession() as session:
        data = {"session_id": session_id}
        async with session.post(f"{BASE_URL}/auth/logout", json=data) as response:
            print(f"  Status: {response.status}")
            result = await response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            return response.status == 200


async def main():
    """Run all tests"""
    print("=" * 50)
    print("Goose Agent Server - Integration Tests")
    print("=" * 50)

    # Test 1: Register user
    username = "testuser"
    password = "testpass123"

    success, _ = await test_register(username, password)
    if not success:
        print("\n[X] User registration failed.")
        return

    print("\n[OK] User registration passed!")

    # Test 2: Login
    session_id = await test_login(username, password)
    if not session_id:
        print("\n[X] Login failed.")
        return

    print(f"\n[OK] Login passed! Session ID: {session_id}")

    # Test 3: Get profile
    if not await test_profile(session_id):
        print("\n[X] Profile fetch failed.")
        return

    print("\n[OK] Profile fetch passed!")

    # Test 4: Logout
    if not await test_logout(session_id):
        print("\n[X] Logout failed.")
        return

    print("\n[OK] Logout passed!")

    print("\n" + "=" * 50)
    print("[OK] All tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTests interrupted.")
    except Exception as e:
        print(f"\n\n[X] Error: {e}")
        import traceback
        traceback.print_exc()
