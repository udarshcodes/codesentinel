import httpx
import asyncio
import json

async def run_test():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post('http://localhost:8000/api/v1/analyze', json={'repository_urls': ['https://github.com/udarshcodes/portfolio']})
        data = res.json()
        print("Response:", json.dumps(data, indent=2))
        
if __name__ == "__main__":
    asyncio.run(run_test())
