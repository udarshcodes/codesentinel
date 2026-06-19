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
    pom_path = os.path.join(repo_local_path, "pom.xml")
    
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
                
    if os.path.exists(pom_path):
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ns = ""
            if "}" in root.tag:
                ns = root.tag.split("}")[0] + "}"
                
            deps_node = root.find(f"{ns}dependencies")
            if deps_node is not None:
                for dep_node in deps_node.findall(f"{ns}dependency"):
                    grp = dep_node.find(f"{ns}groupId")
                    art = dep_node.find(f"{ns}artifactId")
                    ver = dep_node.find(f"{ns}version")
                    
                    if grp is not None and art is not None and ver is not None:
                        version_text = ver.text
                        if version_text and not version_text.startswith("${"):
                            dependencies.append({
                                "name": f"{grp.text}:{art.text}",
                                "version": version_text,
                                "ecosystem": "Maven"
                            })
        except Exception as e:
            print(f"[DependencyAnalyzer] Failed to parse pom.xml: {e}")

    # Parse go.mod for Go dependencies
    gomod_path = os.path.join(repo_local_path, "go.mod")
    if os.path.exists(gomod_path):
        try:
            with open(gomod_path, "r") as f:
                in_require_block = False
                for line in f:
                    line = line.strip()
                    if line.startswith("require ("):
                        in_require_block = True
                        continue
                    if in_require_block and line == ")":
                        in_require_block = False
                        continue
                    # Handle single-line require: require github.com/pkg v1.2.3
                    if line.startswith("require ") and "(" not in line:
                        parts = line.replace("require ", "").strip().split()
                        if len(parts) >= 2:
                            dependencies.append({
                                "name": parts[0],
                                "version": parts[1].lstrip("v"),
                                "ecosystem": "Go"
                            })
                    elif in_require_block and line and not line.startswith("//"):
                        # Inside require block: github.com/pkg v1.2.3
                        parts = line.split()
                        if len(parts) >= 2 and not parts[0].startswith("//"):
                            dependencies.append({
                                "name": parts[0],
                                "version": parts[1].lstrip("v"),
                                "ecosystem": "Go"
                            })
        except Exception as e:
            print(f"[DependencyAnalyzer] Failed to parse go.mod: {e}")

    def is_outdated(current: str, latest: str) -> bool:
        if current == latest: return False
        try:
            c_parts = [int(x) for x in current.split('.') if x.isdigit()]
            l_parts = [int(x) for x in latest.split('.') if x.isdigit()]
            if c_parts and l_parts:
                return l_parts > c_parts
        except Exception:
            pass
        return latest != current

    # Check for outdated packages against public registries
    async def check_outdated(dep):
        try:
            async with httpx.AsyncClient() as client:
                if dep["ecosystem"] == "PyPI":
                    res = await client.get(f"https://pypi.org/pypi/{dep['name']}/json", timeout=5)
                    if res.status_code == 200:
                        latest = res.json().get("info", {}).get("version")
                        if latest and is_outdated(dep["version"], latest):
                            return latest
                elif dep["ecosystem"] == "npm":
                    res = await client.get(f"https://registry.npmjs.org/{dep['name']}/latest", timeout=5)
                    if res.status_code == 200:
                        latest = res.json().get("version")
                        if latest and is_outdated(dep["version"], latest):
                            return latest
                elif dep["ecosystem"] == "Maven":
                    grp, art = dep['name'].split(":")
                    url = f"https://search.maven.org/solrsearch/select?q=g:{grp}+AND+a:{art}&rows=1&wt=json"
                    res = await client.get(url, timeout=5)
                    if res.status_code == 200:
                        docs = res.json().get("response", {}).get("docs", [])
                        if docs:
                            latest = docs[0].get("latestVersion")
                            if latest and is_outdated(dep["version"], latest):
                                return latest
                elif dep["ecosystem"] == "Go":
                    res = await client.get(f"https://proxy.golang.org/{dep['name']}/@latest", timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        latest = data.get("Version", "").lstrip("v")
                        if latest and is_outdated(dep["version"], latest):
                            return latest
        except Exception as e:
            print(f"[DependencyAnalyzer] Registry check failed for {dep['name']}: {e}")
        return None

    import asyncio
    outdated_results = await asyncio.gather(*(check_outdated(d) for d in dependencies))
    
    for dep, latest in zip(dependencies, outdated_results):
        if latest:
            file_name = "requirements.txt"
            if dep["ecosystem"] == "npm":
                file_name = "package.json"
            elif dep["ecosystem"] == "Maven":
                file_name = "pom.xml"
            elif dep["ecosystem"] == "Go":
                file_name = "go.mod"
                
            findings.append({
                "file": file_name,
                "issue": f"Outdated dependency: {dep['name']} is at {dep['version']}, but latest is {latest}.",
                "cve": "N/A",
                "package": dep["name"],
                "severity": "LOW"
            })

    # Hit OSV API using batch query
    from tools.osv_client import batch_query_osv, fetch_vuln_details
    
    cves_map = await batch_query_osv(dependencies)
    
    # Collect all unique vuln IDs to fetch details
    all_vuln_ids = set()
    for dep_cves in cves_map.values():
        for vuln in dep_cves:
            all_vuln_ids.add(vuln.get('id'))
            
    vuln_details = await fetch_vuln_details(list(all_vuln_ids))
    
    for dep in dependencies:
        cves = cves_map.get(dep["name"], [])
        for vuln in cves:
            vid = vuln.get('id', 'Unknown')
            # Extract severity from full details
            severity = "HIGH"
            full_vuln = vuln_details.get(vid, {})
            # Look in severity array (e.g. CVSS_V3) or database_specific
            severity_arr = full_vuln.get('severity', [])
            if severity_arr:
                for sev_entry in severity_arr:
                    if isinstance(sev_entry, dict) and sev_entry.get('type') == 'CVSS_V3':
                        score_str = sev_entry.get('score', '')
                        # Extract base score from CVSS vector if present
                        if ':' in score_str:
                            # Parse CVSS vector — not a numeric score, keep default
                            pass
                        elif score_str:
                            try:
                                cvss_score = float(score_str)
                                if cvss_score >= 9.0:
                                    severity = "CRITICAL"
                                elif cvss_score >= 7.0:
                                    severity = "HIGH"
                                elif cvss_score >= 4.0:
                                    severity = "MEDIUM"
                                else:
                                    severity = "LOW"
                            except ValueError:
                                pass
                        break
            
            db_spec = full_vuln.get("database_specific", {})
            if db_spec and db_spec.get("severity"):
                severity = db_spec.get("severity").upper()
            
            file_name = "requirements.txt"
            if dep["ecosystem"] == "npm":
                file_name = "package.json"
            elif dep["ecosystem"] == "Maven":
                file_name = "pom.xml"
            elif dep["ecosystem"] == "Go":
                file_name = "go.mod"

            findings.append({
                "file": file_name,
                "issue": f"Vulnerable dependency: {dep['name']} {dep['version']}. CVE: {vuln.get('id', 'Unknown')}. Update to a secure version.",
                "cve": vuln.get("id", "Unknown"),
                "package": dep["name"],
                "severity": severity
            })
            
    return {"dependency_findings": findings}