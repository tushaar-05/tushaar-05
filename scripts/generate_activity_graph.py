import os
import sys
import re
import urllib.request
import json
from xml.sax.saxutils import escape

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
TOKEN = os.environ.get("GITHUB_TOKEN")

API_URL = "https://api.github.com/graphql"

QUERY = """
query($username: String!) {
  user(login: $username) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
            weekday
          }
        }
      }
    }
  }
}
"""

def fetch_contributions_from_public(username):
    """Scrape contributions from the public profile page without requiring any API token."""
    url = f"https://github.com/users/{username}/contributions"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8")

    pattern = r'data-date="([\d-]+)"[^>]*id="(contribution-day-component-[^"]+)"'
    days = re.findall(pattern, html)
    tooltips = dict(re.findall(r'for="(contribution-day-component-[^"]+)"[^>]*>([^<]+)</tool-tip>', html))

    results = []
    for date, comp_id in days:
        tip = tooltips.get(comp_id, "")
        m = re.search(r'(\d+)\s+contribution', tip)
        count = int(m.group(1)) if m else 0
        results.append({"date": date, "contributionCount": count})

    results.sort(key=lambda x: x["date"])
    return results

def get_contribution_days(username, token):
    """Fetch contribution days using GraphQL if token is valid, otherwise fallback to public calendar."""
    if token:
        try:
            payload = json.dumps({
                "query": QUERY,
                "variables": {"username": username}
            }).encode("utf-8")

            request = urllib.request.Request(
                API_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "github-activity-graph"
                }
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read())

            if "data" in result and result["data"].get("user"):
                calendar = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]
                all_days = []
                for week in calendar["weeks"]:
                    for day in week["contributionDays"]:
                        all_days.append(day)
                print("Fetched contribution data via GitHub GraphQL API.")
                return all_days
            else:
                print("⚠️ GraphQL returned unexpected data or errors. Falling back to public profile...")
        except Exception as e:
            print(f"⚠️ GraphQL API request failed ({e}). Falling back to public profile...")

    print("Fetching contribution data via GitHub public contributions profile...")
    return fetch_contributions_from_public(username)

all_days = get_contribution_days(USERNAME, TOKEN)

# --------------------------------------------------
# Use the most recent 31 days
# --------------------------------------------------

days = all_days[-31:]

counts = [
    day["contributionCount"]
    for day in days
]

dates = [
    day["date"]
    for day in days
]

# --------------------------------------------------
# SVG configuration
# --------------------------------------------------

WIDTH = 1000
HEIGHT = 350

LEFT = 70
RIGHT = 30
TOP = 55
BOTTOM = 60

GRAPH_WIDTH = WIDTH - LEFT - RIGHT
GRAPH_HEIGHT = HEIGHT - TOP - BOTTOM

BG = "#0d1117"
GRID = "#21262d"
TEXT = "#8b949e"
TEXT_BRIGHT = "#c9d1d9"
GREEN = "#39d353"
GREEN_DARK = "#0e4429"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def scale_x(index):
    if len(days) == 1:
        return LEFT

    return LEFT + (
        index / (len(days) - 1)
    ) * GRAPH_WIDTH


max_value = max(counts) if counts else 1

# Give graph a little headroom
y_max = max(max_value, 1)

# Round Y axis nicely
if y_max <= 5:
    y_max = 5
elif y_max <= 10:
    y_max = 10
elif y_max <= 20:
    y_max = 20
elif y_max <= 50:
    y_max = 50
else:
    y_max = ((y_max // 10) + 1) * 10


def scale_y(value):
    return TOP + GRAPH_HEIGHT - (
        value / y_max
    ) * GRAPH_HEIGHT


# --------------------------------------------------
# SVG
# --------------------------------------------------

svg = []

svg.append(
    f'''<svg xmlns="http://www.w3.org/2000/svg"
        width="{WIDTH}"
        height="{HEIGHT}"
        viewBox="0 0 {WIDTH} {HEIGHT}">'''
)

# Background

svg.append(
    f'''
    <rect
        x="0"
        y="0"
        width="{WIDTH}"
        height="{HEIGHT}"
        rx="18"
        fill="{BG}"
    />
    '''
)

# --------------------------------------------------
# Title
# --------------------------------------------------

svg.append(
    f'''
    <text
        x="{WIDTH / 2}"
        y="30"
        text-anchor="middle"
        font-family="Arial, Helvetica, sans-serif"
        font-size="15"
        font-weight="600"
        fill="{TEXT_BRIGHT}">
        {escape(USERNAME)}'s Contribution Graph
    </text>
    '''
)

# --------------------------------------------------
# Horizontal grid + Y axis
# --------------------------------------------------

GRID_LINES = 5

for i in range(GRID_LINES + 1):

    value = round(
        y_max * i / GRID_LINES
    )

    y = scale_y(value)

    svg.append(
        f'''
        <line
            x1="{LEFT}"
            y1="{y}"
            x2="{WIDTH - RIGHT}"
            y2="{y}"
            stroke="{GRID}"
            stroke-width="1"
        />
        '''
    )

    svg.append(
        f'''
        <text
            x="{LEFT - 15}"
            y="{y + 4}"
            text-anchor="end"
            font-family="Arial, Helvetica, sans-serif"
            font-size="10"
            fill="{TEXT}">
            {value}
        </text>
        '''
    )

# --------------------------------------------------
# Vertical grid lines
# --------------------------------------------------

for i in range(len(days)):

    x = scale_x(i)

    svg.append(
        f'''
        <line
            x1="{x}"
            y1="{TOP}"
            x2="{x}"
            y2="{TOP + GRAPH_HEIGHT}"
            stroke="{GRID}"
            stroke-width="1"
            opacity="0.65"
        />
        '''
    )

# --------------------------------------------------
# Axis labels
# --------------------------------------------------

svg.append(
    f'''
    <text
        x="{WIDTH / 2}"
        y="{HEIGHT - 12}"
        text-anchor="middle"
        font-family="Arial, Helvetica, sans-serif"
        font-size="10"
        fill="{TEXT}">
        Days
    </text>
    '''
)

svg.append(
    f'''
    <text
        x="15"
        y="{TOP + GRAPH_HEIGHT / 2}"
        text-anchor="middle"
        transform="rotate(-90 15 {TOP + GRAPH_HEIGHT / 2})"
        font-family="Arial, Helvetica, sans-serif"
        font-size="10"
        fill="{TEXT}">
        Contributions
    </text>
    '''
)

# --------------------------------------------------
# Build graph points
# --------------------------------------------------

points = []

for i, count in enumerate(counts):

    x = scale_x(i)
    y = scale_y(count)

    points.append((x, y))

# --------------------------------------------------
# Smooth curve using cubic Bezier
# --------------------------------------------------

def create_smooth_path(points):

    if len(points) < 2:
        return ""

    path = f"M {points[0][0]} {points[0][1]}"

    for i in range(1, len(points)):

        x0, y0 = points[i - 1]
        x1, y1 = points[i]

        midpoint = (x0 + x1) / 2

        path += (
            f" C {midpoint} {y0}, "
            f"{midpoint} {y1}, "
            f"{x1} {y1}"
        )

    return path


line_path = create_smooth_path(points)

# --------------------------------------------------
# Area under graph
# --------------------------------------------------

area_path = line_path

first_x = points[0][0]
last_x = points[-1][0]
bottom_y = TOP + GRAPH_HEIGHT

area_path += (
    f" L {last_x} {bottom_y}"
    f" L {first_x} {bottom_y}"
    f" Z"
)

svg.append(
    f'''
    <path
        d="{area_path}"
        fill="{GREEN}"
        opacity="0.12"
    />
    '''
)

# --------------------------------------------------
# Graph line
# --------------------------------------------------

svg.append(
    f'''
    <path
        d="{line_path}"
        fill="none"
        stroke="{GREEN}"
        stroke-width="3"
        stroke-linecap="round"
        stroke-linejoin="round"
    />
    '''
)

# --------------------------------------------------
# Data points
# --------------------------------------------------

for i, (x, y) in enumerate(points):

    count = counts[i]
    date = dates[i]

    svg.append(
        f'''
        <circle
            cx="{x}"
            cy="{y}"
            r="4"
            fill="{GREEN}"
            stroke="{TEXT_BRIGHT}"
            stroke-width="1.5">
            <title>{escape(date)}: {count} contributions</title>
        </circle>
        '''
    )

# --------------------------------------------------
# X-axis date labels
# --------------------------------------------------

# Show roughly 10 labels instead of all 31
label_indices = list(range(0, len(days), 3))

if (len(days) - 1) not in label_indices:
    label_indices.append(len(days) - 1)

for i in label_indices:

    x = scale_x(i)

    # Convert YYYY-MM-DD -> day number
    day_number = dates[i].split("-")[2].lstrip("0")

    svg.append(
        f'''
        <text
            x="{x}"
            y="{TOP + GRAPH_HEIGHT + 22}"
            text-anchor="middle"
            font-family="Arial, Helvetica, sans-serif"
            font-size="9"
            fill="{TEXT}">
            {day_number}
        </text>
        '''
    )

# --------------------------------------------------
# Close SVG
# --------------------------------------------------

svg.append("</svg>")

output_dir = os.path.join(PROJECT_ROOT, "assets")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "activity-graph.svg")

with open(
    output_path,
    "w",
    encoding="utf-8"
) as file:
    file.write("\n".join(svg))

print(
    f"Generated contribution graph for {USERNAME}"
)

print(
    f"Showing {len(days)} days"
)

print(
    f"Maximum daily contributions: {max(counts) if counts else 0}"
)

print(
    f"Saved to {output_path}"
)