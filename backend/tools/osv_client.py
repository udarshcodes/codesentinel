import httpx

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"


async def batch_query_osv(packages: list[dict]) -> dict:
    """
    packages: [{'name': str, 'version': str, 'ecosystem': str}, ...]
    Returns dict keyed by package name with list of CVEs
    """
    if not packages:
        return {}

    queries = [
        {
            "version": p["version"],
            "package": {"name": p["name"], "ecosystem": p["ecosystem"]},
        }
        for p in packages
    ]

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                OSV_BATCH_URL, json={"queries": queries}, timeout=15.0
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                # The length of results from querybatch matches the length of queries
                return {
                    packages[i]["name"]: results[i].get("vulns", [])
                    for i in range(min(len(packages), len(results)))
                }
    except Exception as e:
        print(f"[OSVClient] Error making batch request: {e}")

    return {}


async def fetch_vuln_details(vuln_ids: list[str]) -> dict:
    """Fetch full details for a list of vulnerability IDs."""
    import asyncio

    sem = asyncio.Semaphore(10)

    async def fetch_one(client, vid):
        async with sem:
            try:
                r = await client.get(
                    f"https://api.osv.dev/v1/vulns/{vid}", timeout=10.0
                )
                if r.status_code == 200:
                    return vid, r.json()
            except Exception as e:
                print(f"[OSVClient] Error fetching vuln {vid}: {e}")
            return vid, None

    async with httpx.AsyncClient() as client:
        pairs = await asyncio.gather(*(fetch_one(client, vid) for vid in vuln_ids))

    return {vid: data for vid, data in pairs if data is not None}
