import os
import sys
import re
import urllib.parse
import urllib.request
import urllib.error

# --------------------------------------------------
# Environment Variable Loading (.env support)
# --------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

def _load_env_file(filepath):
    """Load key-value pairs from a .env file into os.environ if not already set."""
    if not os.path.isfile(filepath):
        return False
    loaded_any = False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded_any = True
    except Exception:
        pass
    return loaded_any

# Try python-dotenv first if available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    load_dotenv()
except ImportError:
    pass

# Fallback parser so it works without requiring external packages
_load_env_file(os.path.join(SCRIPT_DIR, ".env"))
_load_env_file(os.path.join(PROJECT_ROOT, ".env"))
_load_env_file(os.path.join(os.getcwd(), ".env"))

USERNAME = os.environ.get("GITHUB_USERNAME", "tushaar-05")

# --------------------------------------------------
# Streak Stats Configuration
# --------------------------------------------------
PARAMS = {
    "user": USERNAME,
    "theme": os.environ.get("STREAK_THEME", "dark"),
    "hide_border": "true",
    "background": "0C1117",
    "stroke": "0C1117",
    "ring": "FFFFFF",
    "fire": "FFFFFF",
    "currStreakLabel": "FFFFFF",
    "sideLabels": "E0E0E0",
    "currStreakNum": "FFFFFF",
    "sideNums": "FFFFFF",
    "dates": "808080",
}

query_string = urllib.parse.urlencode(PARAMS)

# Primary and fallback mirrors for GitHub Readme Streak Stats
SERVICE_MIRRORS = [
    f"https://streak-stats.demolab.com/?{query_string}",
    f"https://github-readme-streak-stats.herokuapp.com/?{query_string}",
]

def fetch_streak_svg():
    """Fetch streak stats SVG from available service endpoints."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/svg+xml,image/*,*/*;q=0.8",
    }
    
    last_error = None
    for url in SERVICE_MIRRORS:
        endpoint_host = urllib.parse.urlparse(url).netloc
        print(f"Fetching streak stats from {endpoint_host}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
                
                # Check for valid SVG content
                if "<svg" in content and "</svg>" in content:
                    return content
                else:
                    print(f"⚠️ Response from {endpoint_host} did not contain valid SVG content.")
        except (urllib.error.URLError, TimeoutError, Exception) as e:
            print(f"⚠️ Failed to reach {endpoint_host}: {e}")
            last_error = e

    raise RuntimeError(f"Could not fetch streak stats SVG from any mirror. Last error: {last_error}")

def parse_stats_summary(svg_content):
    """Extract highlights from the SVG for console display."""
    texts = re.findall(r'<text[^>]*>\s*([^<]+?)\s*</text>', svg_content)
    # Expected order in SVG:
    # [total_num, 'Total Contributions', total_dates, 'Current Streak', curr_dates, curr_num, longest_num, 'Longest Streak', longest_dates]
    summary = {}
    try:
        if "Total Contributions" in texts:
            idx = texts.index("Total Contributions")
            summary["total"] = texts[idx - 1] if idx > 0 else "N/A"
            summary["total_range"] = texts[idx + 1] if idx + 1 < len(texts) else ""
        if "Current Streak" in texts:
            idx = texts.index("Current Streak")
            summary["curr_range"] = texts[idx + 1] if idx + 1 < len(texts) else ""
            summary["current"] = texts[idx + 2] if idx + 2 < len(texts) else "N/A"
        if "Longest Streak" in texts:
            idx = texts.index("Longest Streak")
            summary["longest"] = texts[idx - 1] if idx > 0 else "N/A"
            summary["longest_range"] = texts[idx + 1] if idx + 1 < len(texts) else ""
    except Exception:
        pass
    return summary

def main():
    try:
        svg_content = fetch_streak_svg()
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.join(PROJECT_ROOT, "assets")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "streak-stats.svg")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"\n✅ Successfully generated streak stats for {USERNAME}")
    
    summary = parse_stats_summary(svg_content)
    if summary:
        if "total" in summary:
            print(f"   • Total Contributions: {summary['total']} ({summary.get('total_range', '')})")
        if "current" in summary:
            print(f"   • Current Streak:      {summary['current']} days ({summary.get('curr_range', '')})")
        if "longest" in summary:
            print(f"   • Longest Streak:      {summary['longest']} days ({summary.get('longest_range', '')})")
    
    print(f"   • Saved to: {output_path}")

if __name__ == "__main__":
    main()
