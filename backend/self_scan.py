import asyncio
from agents.static_analysis import agent_static_analysis


async def run():
    state = {
        "repo_local_path": r"x:\home\udarsh\codesentinel_fresh",
        "dependency_graph": {"cycles": []},
    }
    result = await agent_static_analysis(state)
    import json

    with open("self_scan_results.json", "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    asyncio.run(run())
