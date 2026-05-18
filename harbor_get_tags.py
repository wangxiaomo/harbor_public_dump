#!/usr/bin/env python3

import sys
from datetime import datetime
from urllib.parse import quote

import requests
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
    v2_url = f"{base}/api/v2.0/projects"
    data = get_json(v2_url, {"page": 1, "page_size": 1}, silent=True)
    if isinstance(data, list):
        return "v2"

    v1_url = f"{base}/api/projects"
    data = get_json(v1_url, {"page": 1, "page_size": 1}, silent=True)
    if isinstance(data, list):
        return "v1"

    return None


def split_repo_name(repo_name):
    repo_name = repo_name.strip("/")
    if "/" not in repo_name:
        raise ValueError("repo_name must include project and repository, e.g. rk-iep/srv-iep-gateway")
    project_name, repository_name = repo_name.split("/", 1)
    if not project_name or not repository_name:
        raise ValueError("repo_name must include project and repository, e.g. rk-iep/srv-iep-gateway")
    return project_name, repository_name


def v2_repository_path(repository_name):
    # Harbor v2 path parameters commonly need a second encode for nested repo names.
    return quote(quote(repository_name, safe=""), safe="")


def v1_repo_candidates(repo_name):
    encoded = quote(repo_name, safe="")
    candidates = [repo_name]
    if encoded != repo_name:
        candidates.append(encoded)
    return candidates


def iter_tags_v1(base, repo_name):
    for repo_path in v1_repo_candidates(repo_name):
        tags = get_json(
            f"{base}/api/repositories/{repo_path}/tags",
            silent=True,
        )
        if not tags or not isinstance(tags, list):
            continue

        for tag in tags:
            yield {
                "tag": tag.get("name"),
                "created_time": tag.get("created") or tag.get("creation_time"),
                "push_time": tag.get("push_time"),
                "pull_time": tag.get("pull_time"),
            }

        return


def iter_tags_v2(base, project_name, repository_name, page_size=100):
    project_path = quote(project_name, safe="")
    repo_path = v2_repository_path(repository_name)
    page = 1

    while True:
        artifacts = get_json(
            f"{base}/api/v2.0/projects/{project_path}/repositories/{repo_path}/artifacts",
            {
                "with_tag": "true",
                "with_label": "false",
                "with_scan_overview": "false",
                "with_signature": "false",
                "with_immutable_status": "false",
                "page": page,
                "page_size": page_size,
            },
        )
        if not artifacts:
            break
        if not isinstance(artifacts, list):
            break

        for artifact in artifacts:
            artifact_created = artifact.get("creation_time")
            artifact_push = artifact.get("push_time")
            artifact_pull = artifact.get("pull_time")

            for tag in artifact.get("tags") or []:
                yield {
                    "tag": tag.get("name"),
                    "created_time": tag.get("creation_time") or artifact_created,
                    "push_time": tag.get("push_time") or artifact_push,
                    "pull_time": tag.get("pull_time") or artifact_pull,
                }

        page += 1


def latest_by_push_time(tags, limit=5):
    valid_tags = [t for t in tags if t.get("tag")]
    return sorted(
        valid_tags,
        key=lambda t: parse_time(t.get("push_time")) or datetime.min,
        reverse=True,
    )[:limit]


def print_tags(repo_name, tags):
    table = [
        [
            f"{repo_name}:{tag['tag']}",
            tag.get("created_time"),
            tag.get("push_time"),
            tag.get("pull_time"),
        ]
        for tag in tags
    ]

    if not table:
        print("[*] No tags found.")
        return

    print(tabulate(
        table,
        headers=["Repo:Tag", "Created Time", "Push Time", "Pull Time"],
        tablefmt="grid",
    ))


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} https://harbor.example.com project/repository")
        print(f"Example: {sys.argv[0]} https://wjloa.rockontrol.com rk-iep/srv-iep-gateway")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    repo_name = sys.argv[2].strip("/")

    try:
        project_name, repository_name = split_repo_name(repo_name)
    except ValueError as e:
        print(f"[!] {e}")
        sys.exit(1)

    api_version = detect_api_version(base)
    if not api_version:
        print("[!] Could not detect Harbor API version (v1 or v2).")
        print("[!] Please verify the URL, network connectivity, and whether anonymous API access is allowed.")
        sys.exit(2)

    print(f"[*] Detected Harbor API version: {api_version}")

    if api_version == "v2":
        tags = iter_tags_v2(base, project_name, repository_name)
    else:
        tags = iter_tags_v1(base, repo_name)

    print_tags(repo_name, latest_by_push_time(tags, limit=5))


if __name__ == "__main__":
    main()
