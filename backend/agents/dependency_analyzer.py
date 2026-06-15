import os
import json
import httpx
from models.pipeline_state import PipelineState

async def agent_dependency_analyzer(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    findings = []
    
    if not repo_local_path:
        return {"dependency_findings": findings}
        
    req_path = os.path.join(repo_local_path, "requirements.txt")
    pkg_path = os.path.join(repo_local_path, "package.json")
    
    dependencies = []
    
    if os.path.exists(req_path):
        with open(req_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" in line:
                    try:
                        parts = line.split("==", 1)  # Split on first == only
                        pkg = parts[0].strip()
                        ver = parts[1].strip()
                        if pkg and ver:
                            dependencies.append({"name": pkg, "version": ver, "ecosystem": "PyPI"})
                    except (ValueError, IndexError) as e:
                        print(f"[DependencyAnalyzer] Skipping malformed line: {line!r} ({e})")
                    
    if os.path.exists(pkg_path):
        with open(pkg_path, "r") as f:
            try:
                data = json.load(f)
                deps = data.get("dependencies", {})
                for pkg, ver in deps.items():
                    ver = ver.replace("^", "").replace("~", "")
                    dependencies.append({"name": pkg, "version": ver, "ecosystem": "npm"})
            except Exception as e:
                print(f"[DependencyAnalyzer] Failed to parse package.json: {e}")
                
    # Check for outdated packages against public registries
    async def check_outdated(dep):
        try:
            async with httpx.AsyncClient() as client:
                if dep["ecosystem"] == "PyPI":
                    res = await client.get(f"https://pypi.org/pypi/{dep['name']}/json", timeout=5)
                    if res.status_code == 200:
                        latest = res.json().get("info", {}).get("version")
                        # Basic string inequality for version check
                        if latest and latest != dep["version"]:
                            return latest
                elif dep["ecosystem"] == "npm":
                    res = await client.get(f"https://registry.npmjs.org/{dep['name']}/latest", timeout=5)
                    if res.status_code == 200:
                        latest = res.json().get("version")
                        if latest and latest != dep["version"]:
                            return latest
        except Exception as e:
            print(f"[DependencyAnalyzer] Registry check failed for {dep['name']}: {e}")
        return None

    import asyncio
    outdated_results = await asyncio.gather(*(check_outdated(d) for d in dependencies))
    
    for dep, latest in zip(dependencies, outdated_results):
        if latest:
            findings.append({
                "file": "requirements.txt" if dep["ecosystem"] == "PyPI" else "package.json",
                "issue": f"Outdated dependency: {dep['name']} is at {dep['version']}, but latest is {latest}.",
                "cve": "N/A",
                "package": dep["name"],
                "severity": "LOW"
            })

    # Hit OSV API using batch query
    from tools.osv_client import batch_query_osv
    
    cves_map = await batch_query_osv(dependencies)
    
    for dep in dependencies:
        cves = cves_map.get(dep["name"], [])
        for vuln in cves:
            # Extract severity from OSV response if available
            severity = "HIGH"
            vuln_severity = vuln.get("database_specific", {}).get("severity", "")
            if vuln_severity:
                severity = vuln_severity.upper()
            
            findings.append({
                "file": "requirements.txt" if dep["ecosystem"] == "PyPI" else "package.json",
                "issue": f"Vulnerable dependency: {dep['name']} {dep['version']}. CVE: {vuln.get('id', 'Unknown')}. Update to a secure version.",
                "cve": vuln.get("id", "Unknown"),
                "package": dep["name"],
                "severity": severity
            })
            
    return {"dependency_findings": findings}