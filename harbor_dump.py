#!/usr/bin/env python3

import sys
import requests
from datetime import datetime
from tabulate import tabulate

requests.packages.urllib3.disable_warnings()


def get_json(url, params=None):
    try:
        r = requests.get(url, params=params, verify=False, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[!] Request failed: {url} -> {e}")
        return []


def parse_time(t):
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except:
        return None


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} https://harbor.example.com")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    page_size = 100
    project_page = 1

    while True:
        projects = get_json(
            f"{base}/api/v2.0/projects",
            {"public": "true", "page": project_page, "page_size": page_size}
        )

        if not projects:
            break

        for p in projects:
            project = p["name"]
            print(f"\n========== Project: {project} ==========")

            repo_page = 1
            table = []
            repo_count = 0
            total_artifacts = 0
            total_pulls = 0
            latest_update = None

            while True:
                repos = get_json(
                    f"{base}/api/v2.0/projects/{project}/repositories",
                    {"page": repo_page, "page_size": page_size}
                )

                if not repos:
                    break

                for r in repos:
                    repo_count += 1

                    full_name = r["name"]

                    # 去掉 project 前缀
                    if full_name.startswith(project + "/"):
                        repo_name = full_name[len(project) + 1:]
                    else:
                        repo_name = full_name

                    artifact_count = r.get("artifact_count", 0)
                    pull_count = r.get("pull_count", 0)
                    created_at = r.get("creation_time")
                    updated_at = r.get("update_time")

                    total_artifacts += artifact_count
                    total_pulls += pull_count

                    update_dt = parse_time(updated_at)
                    if update_dt and (not latest_update or update_dt > latest_update):
                        latest_update = update_dt

                    table.append([
                        repo_name,
                        artifact_count,
                        pull_count,
                        created_at,
                        updated_at
                    ])

                repo_page += 1

            if table:
                print(tabulate(
                    table,
                    headers=["Repo", "Artifacts", "Pulls", "Created", "Updated"],
                    tablefmt="grid"
                ))

            print("\n----- Project Summary -----")
            print(f"Total repos     : {repo_count}")
            print(f"Total artifacts : {total_artifacts}")
            print(f"Total pulls     : {total_pulls}")
            print(f"Latest updated  : {latest_update}")
            print("=====================================")

        project_page += 1


if __name__ == "__main__":
    main()
