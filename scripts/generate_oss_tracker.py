import os
import sys
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CACHE_FILE = os.path.join(SCRIPT_DIR, ".oss_cache.json")

def _load_env_file(filepath):
    if not os.path.isfile(filepath):
        return False
    loaded_any = False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and k not in os.environ:
                    os.environ[k] = v
                    loaded_any = True
    except Exception:
        pass
    return loaded_any

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    load_dotenv()
except ImportError:
    pass

_load_env_file(os.path.join(SCRIPT_DIR, ".env"))
_load_env_file(os.path.join(PROJECT_ROOT, ".env"))
_load_env_file(os.path.join(os.getcwd(), ".env"))

USERNAME = os.environ.get("GITHUB_USERNAME", "tushaar-05")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")

# Repositories to exclude from open source tracking
IGNORED_REPOS = {
    "voltaraa06/voltaraa",
    "prabhav1437/sos-copy",
    "you-dont-need/you-dont-need-javascript",
    "firstcontributions/first-contributions",
    "madhav235/sync_music_player",
}

def load_cache():
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

def get_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.github.v3+json",
    }
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"
    return headers

def fetch_search(query):
    """Query GitHub Search API with fallback to unauthenticated search if token fails."""
    url = f"https://api.github.com/search/issues?q={urllib.parse.quote(query)}&per_page=100"
    headers = get_headers()
    
    if TOKEN:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8")).get("items", [])
        except urllib.error.HTTPError as e:
            if e.code == 401:
                pass  # Fall back to unauthenticated public search
            else:
                raise

    public_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.github.v3+json",
    }
    req = urllib.request.Request(url, headers=public_headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items", [])

def fetch_pr_diff_lines(pr_item, cache):
    """Fetch additions and deletions lines for a single pull request via public .diff (no rate limits)."""
    repo = "/".join(pr_item["repository_url"].split("/")[-2:])
    number = pr_item["number"]
    cache_key = f"{repo}#{number}"
    
    # Check cache first for merged/closed PRs
    state = pr_item.get("state", "open")
    if cache_key in cache and state != "open":
        add, rem = cache[cache_key]
        return repo, number, add, rem
        
    diff_url = f"https://github.com/{repo}/pull/{number}.diff"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        req = urllib.request.Request(diff_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            lines = content.split("\n")
            add = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            rem = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
            cache[cache_key] = [add, rem]
            return repo, number, add, rem
    except Exception:
        # If network error, use cached value or 0
        if cache_key in cache:
            add, rem = cache[cache_key]
            return repo, number, add, rem
        return repo, number, 0, 0

def format_count(num):
    """Format numbers with k suffix."""
    if num >= 1000:
        return f"{num / 1000:.1f}k"
    return str(num)

def generate_oss_markdown(username):
    print(f"Fetching open source pull requests for {username}...")
    cache = load_cache()
    
    base_filter = f"author:{username} type:pr -user:{username}"
    
    open_prs_raw = fetch_search(f"{base_filter} is:open")
    merged_prs_raw = fetch_search(f"{base_filter} is:merged")
    
    # Filter out ignored repos
    open_prs = [
        p for p in open_prs_raw 
        if "/".join(p["repository_url"].split("/")[-2:]).lower() not in IGNORED_REPOS
    ]
    merged_prs = [
        p for p in merged_prs_raw 
        if "/".join(p["repository_url"].split("/")[-2:]).lower() not in IGNORED_REPOS
    ]
    
    review_req_items = fetch_search(f"{base_filter} is:open review:required")
    changes_req_items = fetch_search(f"{base_filter} is:open review:changes_requested")
    approved_items = fetch_search(f"{base_filter} is:open review:approved")
    
    review_req_ids = {i["id"] for i in review_req_items}
    changes_req_ids = {i["id"] for i in changes_req_items}
    approved_ids = {i["id"] for i in approved_items}
    
    all_active_prs = open_prs + merged_prs
    print(f"Calculating lines contributed across {len(all_active_prs)} pull requests...")
    
    def worker(pr):
        return fetch_pr_diff_lines(pr, cache)

    with ThreadPoolExecutor(max_workers=8) as executor:
        stats_results = list(executor.map(worker, all_active_prs))
        
    save_cache(cache)

    pr_lines = {}
    for repo, number, add, rem in stats_results:
        pr_lines[(repo, number)] = (add, rem)

    repos = defaultdict(lambda: {
        "open": 0,
        "merged": 0,
        "review_required": 0,
        "changes_requested": 0,
        "approved": 0,
        "additions": 0,
        "deletions": 0,
    })

    total_additions = 0
    total_deletions = 0

    for pr in open_prs:
        repo = "/".join(pr["repository_url"].split("/")[-2:])
        repos[repo]["open"] += 1
        pid = pr["id"]
        if pid in approved_ids:
            repos[repo]["approved"] += 1
        elif pid in changes_req_ids:
            repos[repo]["changes_requested"] += 1
        elif pid in review_req_ids:
            repos[repo]["review_required"] += 1
        
        add, rem = pr_lines.get((repo, pr["number"]), (0, 0))
        repos[repo]["additions"] += add
        repos[repo]["deletions"] += rem
        total_additions += add
        total_deletions += rem

    for pr in merged_prs:
        repo = "/".join(pr["repository_url"].split("/")[-2:])
        repos[repo]["merged"] += 1
        
        add, rem = pr_lines.get((repo, pr["number"]), (0, 0))
        repos[repo]["additions"] += add
        repos[repo]["deletions"] += rem
        total_additions += add
        total_deletions += rem

    total_open = len(open_prs)
    total_merged = len(merged_prs)
    total_prs = total_open + total_merged
    total_in_review = sum(1 for pr in open_prs if pr["id"] in review_req_ids or pr["id"] in changes_req_ids)

    # Sort repositories by total PR count descending
    sorted_repos = sorted(
        repos.items(),
        key=lambda item: (item[1]["open"] + item[1]["merged"]),
        reverse=True
    )

    lines = []
    lines.append("## 🌐 Open Source Contributions")
    lines.append("")
    lines.append("<p align=\"center\">")
    lines.append(f"  <img src=\"https://img.shields.io/badge/Total%20PRs-{total_prs}-0C1117?style=for-the-badge&logo=git&logoColor=white\" alt=\"Total PRs\" />")
    lines.append(f"  <img src=\"https://img.shields.io/badge/Merged-{total_merged}-8957e5?style=for-the-badge&logo=gitmerge&logoColor=white\" alt=\"Merged PRs\" />")
    lines.append(f"  <img src=\"https://img.shields.io/badge/Open-{total_open}-238636?style=for-the-badge&logo=gitpullrequest&logoColor=white\" alt=\"Open PRs\" />")
    lines.append(f"  <img src=\"https://img.shields.io/badge/In%20Review-{total_in_review}-d29922?style=for-the-badge&logo=github&logoColor=white\" alt=\"In Review\" />")
    
    # Safe static/v1 Shields endpoint with URL encoded parameters
    lines_label = urllib.parse.quote("Lines Contributed")
    lines_val = urllib.parse.quote(f"+{format_count(total_additions)} / -{format_count(total_deletions)}")
    lines.append(f"  <img src=\"https://img.shields.io/static/v1?label={lines_label}&message={lines_val}&color=0969da&style=for-the-badge&logo=githubactions&logoColor=white\" alt=\"Lines Contributed\" />")
    lines.append("</p>")
    lines.append("")
    lines.append("| Organization / Repository | 🟢 Open | 🟡 Review Status | 🟣 Merged | Total PRs | 📝 Lines Contributed |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

    for repo, data in sorted_repos:
        repo_total = data["open"] + data["merged"]
        open_count = data["open"]
        merged_count = data["merged"]
        add = data["additions"]
        rem = data["deletions"]
        net_lines = add + rem

        open_url = f"https://github.com/{repo}/pulls?q=is%3Apr+author%3A{username}+is%3Aopen"
        merged_url = f"https://github.com/{repo}/pulls?q=is%3Apr+author%3A{username}+is%3Amerged"

        open_cell = f"[{open_count}]({open_url})" if open_count > 0 else "-"
        merged_cell = f"[{merged_count}]({merged_url})" if merged_count > 0 else "-"

        # Review status breakdown
        status_parts = []
        if data["review_required"] > 0:
            status_parts.append(f"{data['review_required']} awaiting review")
        if data["changes_requested"] > 0:
            status_parts.append(f"{data['changes_requested']} changes requested")
        if data["approved"] > 0:
            status_parts.append(f"{data['approved']} approved")

        review_cell = "<br>".join(status_parts) if status_parts else "-"
        lines_cell = f"`+{add:,} / -{rem:,}`<br><sub>({net_lines:,} total)</sub>"

        lines.append(f"| [**{repo}**](https://github.com/{repo}) | {open_cell} | {review_cell} | {merged_cell} | **{repo_total}** | {lines_cell} |")

    lines.append("")
    return "\n".join(lines)

def update_readme(new_content):
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    if not os.path.isfile(readme_path):
        print(f"Error: Could not find README at {readme_path}", file=sys.stderr)
        sys.exit(1)

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = "<!-- OSS-TRACKER:START -->"
    end_tag = "<!-- OSS-TRACKER:END -->"

    block = f"{start_tag}\n{new_content}\n{end_tag}"

    if start_tag in content and end_tag in content:
        before = content.split(start_tag)[0]
        after = content.split(end_tag)[1]
        updated = f"{before}{block}{after}"
    else:
        target = "## Tech Stack"
        if target in content:
            updated = content.replace(target, f"{block}\n\n---\n\n{target}")
        else:
            updated = content + f"\n\n---\n\n{block}\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)

    print("✅ Successfully updated README.md with filtered Open Source Contributions & lines tracking!")

def main():
    try:
        md = generate_oss_markdown(USERNAME)
        update_readme(md)
    except Exception as e:
        print(f"❌ Error generating OSS tracker: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
