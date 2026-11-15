from agents.dependency_analyzer import resolved_npm_version


def test_use_resolved_version_only_when_lock_matches_declarations():
    manifest = {"dependencies": {"vite": "^8.0.12"}}
    lock = {"packages": {"": manifest, "node_modules/vite": {"version": "8.0.16"}}}
    assert resolved_npm_version("vite", "^8.0.12", manifest, lock, "dependencies") == "8.0.16"
    assert resolved_npm_version("vite", "^8.0.12", manifest, {}, "dependencies") == "unknown"
    assert resolved_npm_version("vite", "8.0.12", manifest, {}, "dependencies") == "8.0.12"
    lock["packages"][""] = {"dependencies": {"vite": "^7.0.0"}}
    assert resolved_npm_version("vite", "^8.0.12", manifest, lock, "dependencies") == "unknown"
