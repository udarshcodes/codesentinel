import asyncio
import json
from agents.repair_planner import agent_repair_planner

async def main():
    state = {
        "investigated_issues": [
            {
                "id": 0,
                "description": "Insufficient input validation in 'Flask'",
                "root_cause": "The Flask package has a known vulnerability...",
                "severity": "high",
                "affected_files": []
            }
        ]
    }
    
    result = await agent_repair_planner(state)
    print("Repair Planner Result:", json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
