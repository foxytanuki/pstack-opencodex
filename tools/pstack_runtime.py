"""Read-only checks for the catalog and active collaboration surface."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib


def read_object(path: Path, *, toml: bool = False) -> dict:
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text()) if toml else json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object")
    return data


def configured_catalog(config: dict, codex_home: Path, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    value = config.get("model_catalog_json")
    if value is None:
        return codex_home / "models_cache.json"
    if not isinstance(value, str) or not value:
        raise ValueError("model_catalog_json must be a nonempty path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("catalog path must be absolute; pass --catalog with an absolute path")
    return path


def select_profile(config: dict, name: str | None) -> dict:
    if name is None:
        return config
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict) or not isinstance(profiles.get(name), dict):
        raise ValueError("selected Codex profile is missing or is not a table")
    selected = profiles[name]
    result = {**config, **selected}
    if "features" in selected:
        base, override = config.get("features", {}), selected["features"]
        if not isinstance(base, dict) or not isinstance(override, dict):
            raise ValueError("Codex features must be a table")
        result["features"] = {**base, **override}
    return result


def catalog_records(path: Path) -> dict[str, dict]:
    data = read_object(path)
    models = data.get("models")
    if not isinstance(models, list):
        raise ValueError(f"{path}: expected a models array")
    records = {}
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("slug"), str):
            raise ValueError(f"{path}: expected model objects with string slugs")
        records[model["slug"]] = model
    return records


def model_route(model: dict) -> str:
    if model.get("use_responses_lite") is True:
        return "native"
    if model.get("opencodex_catalog_kind") == "combo-native-alias-v1":
        return "routed"
    slug = model.get("slug", "")
    if "/" in slug and not slug.startswith("openai-codex/"):
        return "routed"
    return "unknown"


def diagnose(
    parent: str,
    children: dict[str, list[str]],
    records: dict[str, dict],
    codex_config: dict,
    opencodex_config: dict,
    surface: str,
) -> dict:
    issues = []

    def issue(level: str, code: str, message: str):
        issues.append({"level": level, "code": code, "message": message})

    def describe(slug: str):
        record = records[slug]
        return {"model": slug, "route": model_route(record), "catalog_surface": record.get("multi_agent_version")}

    parent_info = describe(parent)
    child_info = [{**describe(slug), "roles": roles} for slug, roles in children.items()]
    features = codex_config.get("features", {})
    if not isinstance(features, dict):
        raise ValueError("Codex features must be a table")
    flag = features.get("multi_agent_v2", False)
    if isinstance(flag, dict):
        flag = flag.get("enabled", True)
    if not isinstance(flag, bool):
        raise ValueError("features.multi_agent_v2 must be a boolean or table with a boolean enabled")
    mode = opencodex_config.get("multiAgentMode", "default")
    if mode not in ("v1", "default", "v2"):
        raise ValueError("multiAgentMode must be v1, default, or v2")
    keep_native = opencodex_config.get("keepNativeChatGptOnV1") is True
    plaintext = opencodex_config.get("plaintextV2AgentMessages") is True
    recovery = opencodex_config.get("agentTaskRecovery", {})
    if not isinstance(recovery, dict):
        raise ValueError("agentTaskRecovery must be an object")
    recovery_enabled = recovery.get("enabled") is True

    for child in child_info:
        if child["catalog_surface"] == "disabled":
            issue("error", "child_disabled", f"{child['model']} is disabled for collaboration in the catalog.")
    if parent_info["catalog_surface"] == "disabled":
        issue("error", "parent_disabled", f"{parent} is disabled for collaboration in the catalog.")
    if surface == "unknown":
        issue("warning", "session_surface_unknown", "The active session surface is unknown. Disk settings cannot prove an existing session is V1; confirm it from live client evidence or use a fresh session after catalog synchronization.")
    elif parent_info["catalog_surface"] in ("v1", "v2") and surface != parent_info["catalog_surface"]:
        issue("warning", "session_catalog_mismatch", "The observed session surface differs from the current parent catalog pin. The existing session may retain an older catalog.")
    if flag and (keep_native and mode == "v2" or parent_info["catalog_surface"] == "v1"):
        issue("warning", "global_v2_override", "The global V2 feature can override a native V1 catalog pin for new sessions. Resolve the configuration conflict before starting another session.")

    if surface == "v2":
        routed = [child["model"] for child in child_info if child["route"] == "routed"]
        unknown = [child["model"] for child in child_info if child["route"] == "unknown"]
        if parent_info["route"] == "native" and routed:
            if plaintext or recovery_enabled:
                issue("warning", "experimental_v2_mitigation", "An experimental V2 mitigation is configured. Verify plaintext delivery or successful recovery with a minimal live delegation; configuration alone is not proof.")
            else:
                issue("error", "encrypted_v2_task", "A native V2 parent can send backend-encrypted tasks that routed children cannot read. Use a verified V1 session or an explicitly configured supported delivery path; do not retry the same provider family in this session.")
        if parent_info["route"] == "unknown" or parent_info["route"] == "native" and unknown:
            issue("warning", "route_unknown", "Catalog metadata does not establish all relevant native/routed routes; compatibility is unverified.")

    status = "BLOCKED" if any(i["level"] == "error" for i in issues) else "INCONCLUSIVE" if issues else "CONFIGURATION_OK"
    return {
        "status": status,
        "session_surface": surface,
        "live_delegation_verified": False,
        "configured": {"multi_agent_mode": mode, "global_v2": flag, "keep_native_v1": keep_native, "plaintext_v2": plaintext, "task_recovery": recovery_enabled},
        "parent": parent_info,
        "children": child_info,
        "issues": issues,
    }
