#!/usr/bin/env python3

import sys
import requests
from datetime import datetime
from tabulate import tabulate

requests.packages.urllib3.disable_warnings()


def get(url, params=None):
    return requests.get(url, params=params, verify=False, timeout=20)


def get_json(url, params=None, silent=False):
    try:
        r = get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if not silent:
            print(f"[!] Request failed: {url} -> {e}")
        return None


def parse_time(t):
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def detect_api_version(base):
    # 先试 v2
    v2_url = f"{base}/api/v2.0/projects"
    data = get_json(v2_url, {"page": 1, "page_size": 1}, silent=True)
    if isinstance(data, list):
        return "v2"

    # 再试 v1
    v1_url = f"{base}/api/projects"
    data = get_json(v1_url, {"page": 1, "page_size": 1}, silent=True)
    if isinstance(data, list):
        return "v1"

    return None


def iter_projects_v2(base, page_size=100):
    page = 1
    while True:
        projects = get_json(
            f"{base}/api/v2.0/projects",
            {"public": "true", "page": page, "page_size": page_size}
        )
        if not projects:
            break
        for p in projects:
            yield p
        page += 1


def iter_projects_v1(base, page_size=100):
    page = 1
    while True:
        projects = get_json(
            f"{base}/api/projects",
            {"public": "true", "page": page, "page_size": page_size}
        )
        if not projects:
            break
        for p in projects:
            yield p
        page += 1


def iter_repos_v2(base, project_name, page_size=100):
    page = 1
    while True:
        repos = get_json(
            f"{base}/api/v2.0/projects/{project_name}/repositories",
            {"page": page, "page_size": page_size}
        )
        if not repos:
            break
        for r in repos:
            yield r
        page += 1


def iter_repos_v1(base, project_id, page_size=100):
    page = 1
    while True:
        repos = get_json(
            f"{base}/api/repositories",
            {"project_id": project_id, "page": page, "page_size": page_size}
        )
        if not repos:
            break
        for r in repos:
            yield r
        page += 1


def summarize_project(base, api_version, project):
    table = []
    repo_count = 0
    total_items = 0
    total_pulls = 0
    latest_update = None

    if api_version == "v2":
        project_name = project.get("name", "<unknown>")
        repos = iter_repos_v2(base, project_name)

        for r in repos:
            repo_count += 1

            full_name = r.get("name", "")
            if full_name.startswith(project_name + "/"):
                repo_name = full_name[len(project_name) + 1:]
            else:
                repo_name = full_name

            item_count = r.get("artifact_count", 0)
            pull_count = r.get("pull_count", 0)
            created_at = r.get("creation_time")
            updated_at = r.get("update_time")

            total_items += item_count
            total_pulls += pull_count

            update_dt = parse_time(updated_at)
            if update_dt and (not latest_update or update_dt > latest_update):
                latest_update = update_dt

            table.append([
                repo_name,
                item_count,
                "artifact",
                pull_count,
                created_at,
                updated_at
            ])

        return {
            "project_name": project_name,
            "project_id": project.get("project_id"),
            "table": table,
            "repo_count": repo_count,
            "total_items": total_items,
            "item_label": "artifacts",
            "total_pulls": total_pulls,
            "latest_update": latest_update,
        }

    elif api_version == "v1":
        project_id = project.get("project_id")
        project_name = project.get("name", f"<unknown:{project_id}>")
        repos = iter_repos_v1(base, project_id)

        for r in repos:
            repo_count += 1

            full_name = r.get("name", "")
            if full_name.startswith(project_name + "/"):
                repo_name = full_name[len(project_name) + 1:]
            else:
                repo_name = full_name

            item_count = r.get("tags_count", 0)
            pull_count = r.get("pull_count", 0)
            created_at = r.get("creation_time")
            updated_at = r.get("update_time")

            total_items += item_count
            total_pulls += pull_count

            update_dt = parse_time(updated_at)
            if update_dt and (not latest_update or update_dt > latest_update):
                latest_update = update_dt

            table.append([
                repo_name,
                item_count,
                "tag",
                pull_count,
                created_at,
                updated_at
            ])

        return {
            "project_name": project_name,
            "project_id": project_id,
            "table": table,
            "repo_count": repo_count,
            "total_items": total_items,
            "item_label": "tags",
            "total_pulls": total_pulls,
            "latest_update": latest_update,
        }

    else:
        raise ValueError(f"Unsupported api_version: {api_version}")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} https://harbor.example.com")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    api_version = detect_api_version(base)

    if not api_version:
        print("[!] Could not detect Harbor API version (v1 or v2).")
        print("[!] Please verify the URL, network connectivity, and whether anonymous API access is allowed.")
        sys.exit(2)

    print(f"[*] Detected Harbor API version: {api_version}")

    if api_version == "v2":
        projects = iter_projects_v2(base)
    else:
        projects = iter_projects_v1(base)

    found_any_project = False

    for p in projects:
        found_any_project = True
        result = summarize_project(base, api_version, p)

        print(f"\n========== Project: {result['project_name']} ==========")

        if result["table"]:
            print(tabulate(
                result["table"],
                headers=["Repo", "Items", "Type", "Pulls", "Created", "Updated"],
                tablefmt="grid"
            ))
        else:
            print("[*] No repositories found.")

        print("\n----- Project Summary -----")
        print(f"Total repos     : {result['repo_count']}")
        print(f"Total {result['item_label']:<9}: {result['total_items']}")
        print(f"Total pulls     : {result['total_pulls']}")
        print(f"Latest updated  : {result['latest_update']}")
        print("=====================================")

    if not found_any_project:
        print("[*] No public projects found.")


if __name__ == "__main__":
    main()