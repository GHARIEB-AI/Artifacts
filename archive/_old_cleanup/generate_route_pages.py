"""
Generate split mobile pages by route

Creates:
- mobile_index.html (route selector page ~50KB)
- routes/{ROUTE}.html (individual route pages)
"""

import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths - use absolute paths
BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "AirCairo-Report"
# Use archive file as source (has full content with CSS)
SOURCE_FILE = REPORTS_DIR / "archive" / "report_2026_01_01_08-01_mobile.html"
ROUTES_DIR = REPORTS_DIR / "routes"
OUTPUT_INDEX = REPORTS_DIR / "mobile_split.html"

# SharePoint download link
SHAREPOINT_LINK = "https://flyaircairo-my.sharepoint.com/:f:/g/personal/dammam_to_aircairo_com/IgDvjscVb3zPQ63E6oVxGyViAencC8ryBmR137Me_icPPRs?e=oNiSIH"

# Online URLs
DASHBOARD_URL = "https://gharieb-ai.github.io/AirCairo/"
ARCHIVE_URL = "https://gharieb-ai.github.io/AirCairo/archive/"


def get_index_template():
    """Return the index page template."""
    return '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Threat Alert Report - Routes</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f5f3f9 0%, #ebe7f3 100%);
            color: #462B73;
            min-height: 100vh;
            padding-bottom: 100px;
        }}

        .header {{
            background: linear-gradient(135deg, #462B73 0%, #5a3d8a 100%);
            padding: 20px 15px;
            text-align: center;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }}
        .header h1 {{ font-size: 1.4em; color: white; margin-bottom: 5px; }}
        .header .subtitle {{ color: rgba(255,255,255,0.8); font-size: 0.9em; }}

        .nav-bar {{
            display: flex;
            justify-content: center;
            gap: 10px;
            padding: 15px;
            background: rgba(70, 43, 115, 0.1);
            flex-wrap: wrap;
        }}
        .nav-btn {{
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 10px 20px;
            background: linear-gradient(135deg, #462B73 0%, #5a3d8a 100%);
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 0.9em;
            text-decoration: none;
            cursor: pointer;
        }}
        .nav-btn:hover {{ opacity: 0.9; }}
        .nav-btn.download {{ background: linear-gradient(135deg, #F7941D 0%, #ff6b00 100%); }}

        .stats-summary {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            padding: 15px;
            background: white;
            margin: 10px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .stat-box {{ text-align: center; padding: 10px; }}
        .stat-box .value {{ font-size: 1.8em; font-weight: bold; }}
        .stat-box .label {{ font-size: 0.75em; color: #666; }}
        .stat-box.high .value {{ color: #dc2626; }}
        .stat-box.medium .value {{ color: #f59e0b; }}
        .stat-box.low .value {{ color: #10b981; }}

        .routes-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            padding: 10px;
        }}

        .route-card {{
            background: white;
            border-radius: 12px;
            padding: 15px;
            text-decoration: none;
            color: inherit;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .route-card:active {{ transform: scale(0.98); }}

        .route-name {{
            font-size: 1.1em;
            font-weight: bold;
            color: #462B73;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .route-name::before {{ content: "✈️"; }}

        .route-stats {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8em;
        }}
        .route-stats .high {{ color: #dc2626; }}
        .route-stats .medium {{ color: #f59e0b; }}
        .route-stats .low {{ color: #10b981; }}

        .route-flights {{
            font-size: 0.75em;
            color: #666;
            margin-top: 5px;
        }}

        .search-box {{
            padding: 10px 15px;
            background: white;
            margin: 10px;
            border-radius: 25px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .search-box input {{
            flex: 1;
            border: none;
            outline: none;
            font-size: 1em;
            padding: 8px;
        }}
        .search-box::before {{ content: "🔍"; }}

        .direction-filter {{
            display: flex;
            justify-content: center;
            gap: 10px;
            padding: 10px;
        }}
        .direction-btn {{
            padding: 8px 20px;
            border: 2px solid #462B73;
            background: white;
            color: #462B73;
            border-radius: 20px;
            font-size: 0.85em;
            cursor: pointer;
        }}
        .direction-btn.active {{
            background: #462B73;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛫 Threat Alert Report</h1>
        <div class="subtitle">{range_info}</div>
        <div class="subtitle" style="margin-top:5px; font-size:0.8em;">Generated: {generated_at}</div>
    </div>

    <div class="nav-bar">
        <a href="{dashboard_url}" class="nav-btn">🌐 Dashboard</a>
        <a href="{archive_url}" class="nav-btn">📁 Archive</a>
        <a href="{sharepoint_link}" target="_blank" class="nav-btn download">📥 Download Excel</a>
    </div>

    <div class="stats-summary">
        <div class="stat-box high">
            <div class="value">{total_high}</div>
            <div class="label">HIGH</div>
        </div>
        <div class="stat-box medium">
            <div class="value">{total_medium}</div>
            <div class="label">MEDIUM</div>
        </div>
        <div class="stat-box low">
            <div class="value">{total_low}</div>
            <div class="label">LOW</div>
        </div>
    </div>

    <div class="search-box">
        <input type="text" id="searchInput" placeholder="Search route (e.g. CAI-JED)..." oninput="filterRoutes()">
    </div>

    <div class="direction-filter">
        <button class="direction-btn active" onclick="filterDirection('all', this)">All</button>
        <button class="direction-btn" onclick="filterDirection('ksa-egy', this)">KSA → EGY</button>
        <button class="direction-btn" onclick="filterDirection('egy-ksa', this)">EGY → KSA</button>
    </div>

    <div class="routes-grid" id="routesGrid">
        {route_cards}
    </div>

    <script>
        const ksaCities = ['JED', 'RUH', 'DMM', 'MED', 'AHB', 'TUU', 'GIZ', 'AJF', 'ELQ', 'YNB'];
        const egyCities = ['CAI', 'HBE', 'ATZ', 'LXR', 'ASW', 'SSH'];

        function getDirection(route) {{
            const [from, to] = route.split('-');
            if (ksaCities.includes(from) && egyCities.includes(to)) return 'ksa-egy';
            if (egyCities.includes(from) && ksaCities.includes(to)) return 'egy-ksa';
            return 'other';
        }}

        function filterRoutes() {{
            const search = document.getElementById('searchInput').value.toUpperCase();
            const cards = document.querySelectorAll('.route-card');
            cards.forEach(card => {{
                const route = card.dataset.route.toUpperCase();
                const matchSearch = route.includes(search);
                const currentDir = document.querySelector('.direction-btn.active').textContent;
                let matchDir = true;
                if (currentDir.includes('KSA')) matchDir = getDirection(card.dataset.route) === 'ksa-egy';
                else if (currentDir.includes('EGY')) matchDir = getDirection(card.dataset.route) === 'egy-ksa';
                card.style.display = (matchSearch && matchDir) ? 'block' : 'none';
            }});
        }}

        function filterDirection(dir, btn) {{
            document.querySelectorAll('.direction-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterRoutes();
        }}
    </script>
</body>
</html>'''


def extract_css_from_source(html_content):
    """Extract CSS from source HTML file."""
    import re
    style_match = re.search(r'<style>(.*?)</style>', html_content, re.DOTALL)
    if style_match:
        return style_match.group(1)
    return ""


def get_route_page_template(css_content):
    """Return the individual route page template with full CSS."""
    # Escape curly braces for format string
    css_escaped = css_content.replace('{', '{{').replace('}', '}}')

    return '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>{route} - Threat Alert</title>
    <style>
''' + css_escaped + '''
        /* Additional styles for route pages */
        .sticky-header {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: linear-gradient(135deg, #462B73 0%, #5a3d8a 100%);
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }}
        .header-main {{
            padding: 15px;
            text-align: center;
        }}
        .route-title {{
            font-size: 1.5em;
            font-weight: bold;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }}
        .route-title::before {{ content: "✈️"; }}
        .header-stats {{
            display: flex;
            justify-content: center;
            gap: 20px;
            padding: 5px 0 10px;
        }}
        .header-stat {{
            color: white;
            font-size: 0.85em;
        }}
        .header-stat.high {{ color: #fca5a5; }}
        .header-stat.medium {{ color: #fcd34d; }}
        .header-stat.low {{ color: #6ee7b7; }}
        .nav-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: rgba(0,0,0,0.2);
        }}
        .nav-btn {{
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 8px 15px;
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 0.8em;
            text-decoration: none;
            cursor: pointer;
        }}
        .nav-btn:hover {{ background: rgba(255,255,255,0.3); }}
        .nav-btn.download {{ background: linear-gradient(135deg, #F7941D 0%, #ff6b00 100%); }}
        .route-selector {{
            position: relative;
        }}
        .route-selector select {{
            appearance: none;
            padding: 8px 30px 8px 15px;
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 0.85em;
            cursor: pointer;
        }}
        .route-selector::after {{
            content: "▼";
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: white;
            font-size: 0.7em;
            pointer-events: none;
        }}
        .route-selector select option {{
            background: #462B73;
            color: white;
        }}
        .scroll-controls {{
            position: fixed;
            right: 15px;
            bottom: 100px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 90;
        }}
        .position-indicator {{
            position: fixed;
            right: 5px;
            top: 50%;
            transform: translateY(-50%);
            width: 4px;
            height: 100px;
            background: rgba(70, 43, 115, 0.2);
            border-radius: 2px;
            z-index: 80;
        }}
        .position-bar {{
            width: 100%;
            background: #462B73;
            border-radius: 2px;
            transition: height 0.1s, top 0.1s;
            position: absolute;
        }}
    </style>
</head>
<body>
    <div class="sticky-header">
        <div class="header-main">
            <div class="route-title">{route}</div>
            <div class="header-stats">
                <span class="header-stat high">🔴 {high_count} High</span>
                <span class="header-stat medium">🟡 {medium_count} Medium</span>
                <span class="header-stat low">🟢 {low_count} Low</span>
            </div>
        </div>
        <div class="nav-row">
            <a href="{dashboard_url}" class="nav-btn">🌐 Dashboard</a>
            <div class="route-selector">
                <select onchange="if(this.value) window.location.href=this.value">
                    <option value="">Change Route...</option>
                    {route_options}
                </select>
            </div>
            <a href="{sharepoint_link}" target="_blank" class="nav-btn download">📥 Download</a>
        </div>
    </div>

    <div class="stats-bar">
        <div class="stat-item high">
            <div class="count">{high_count}</div>
            <div class="label">HIGH</div>
        </div>
        <div class="stat-item medium">
            <div class="count">{medium_count}</div>
            <div class="label">MEDIUM</div>
        </div>
        <div class="stat-item low">
            <div class="count">{low_count}</div>
            <div class="label">LOW</div>
        </div>
    </div>

    <div class="content">
        {threat_cards}
    </div>

    <!-- Scroll Controls -->
    <div class="scroll-controls">
        <button class="scroll-btn" id="scrollUp">⬆</button>
        <button class="scroll-btn" id="scrollDown">⬇</button>
    </div>

    <!-- Position Indicator -->
    <div class="position-indicator">
        <div class="position-bar" id="positionBar"></div>
    </div>

    <script>
        // Dual-function scroll buttons
        // Tap = Fast scroll, Hold = Jump to top/bottom

        let holdTimer = null;
        let isHolding = false;
        let scrollInterval = null;

        function setupScrollButton(btn, direction) {{
            const scrollAmount = direction === 'up' ? -800 : 800;
            const jumpTo = direction === 'up' ? 0 : document.documentElement.scrollHeight;

            // Start - detect hold vs tap
            const startHandler = (e) => {{
                e.preventDefault();
                isHolding = false;

                // Start fast scrolling immediately (tap behavior)
                scrollInterval = setInterval(() => {{
                    window.scrollBy({{ top: scrollAmount, behavior: 'auto' }});
                }}, 50);

                // If held for 500ms, jump to top/bottom
                holdTimer = setTimeout(() => {{
                    isHolding = true;
                    clearInterval(scrollInterval);
                    window.scrollTo({{ top: jumpTo, behavior: 'smooth' }});
                }}, 500);
            }};

            // End - stop scrolling
            const endHandler = (e) => {{
                e.preventDefault();
                clearTimeout(holdTimer);
                clearInterval(scrollInterval);
            }};

            btn.addEventListener('touchstart', startHandler, {{ passive: false }});
            btn.addEventListener('touchend', endHandler);
            btn.addEventListener('mousedown', startHandler);
            btn.addEventListener('mouseup', endHandler);
            btn.addEventListener('mouseleave', endHandler);
        }}

        setupScrollButton(document.getElementById('scrollUp'), 'up');
        setupScrollButton(document.getElementById('scrollDown'), 'down');

        // Position indicator
        let ticking = false;
        function updatePositionIndicator() {{
            if (!ticking) {{
                requestAnimationFrame(() => {{
                    const scrollTop = window.scrollY;
                    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
                    const scrollPercent = docHeight > 0 ? (scrollTop / docHeight) : 0;
                    const bar = document.getElementById('positionBar');
                    const barHeight = 20;
                    const maxTop = 100 - barHeight;
                    bar.style.height = barHeight + 'px';
                    bar.style.top = (scrollPercent * maxTop) + 'px';
                    ticking = false;
                }});
                ticking = true;
            }}
        }}

        window.addEventListener('scroll', updatePositionIndicator, {{ passive: true }});
        updatePositionIndicator();

        // Language toggle
        function toggleLang() {{
            document.body.classList.toggle('en');
        }}
    </script>
</body>
</html>'''


def extract_routes_from_html(html_content):
    """Extract route data from the source HTML."""
    routes_data = {}

    # Find all route sections: <div data-route="XXX-YYY">
    route_pattern = r'<div data-route="([A-Z]{3}-[A-Z]{3})">'
    routes_found = set(re.findall(route_pattern, html_content))

    print(f"Found {len(routes_found)} routes: {sorted(routes_found)}")

    # For each route, find its section and count threat cards
    for route in routes_found:
        routes_data[route] = {
            'high': 0,
            'medium': 0,
            'low': 0,
            'content': ''
        }

        # Extract the route section content
        # Pattern: <div data-route="ROUTE">...content...</div></div><div data-route=" (next route)
        section_pattern = rf'<div data-route="{route}">(.*?)(?=<div data-route="|<!-- Scroll|$)'
        section_match = re.search(section_pattern, html_content, re.DOTALL)

        if section_match:
            section_content = section_match.group(1)
            routes_data[route]['content'] = section_content

            # Count threats by level within this section
            routes_data[route]['high'] = len(re.findall(r'class="threat-card[^"]*\bhigh\b', section_content))
            routes_data[route]['medium'] = len(re.findall(r'class="threat-card[^"]*\bmedium\b', section_content))
            routes_data[route]['low'] = len(re.findall(r'class="threat-card[^"]*\blow\b', section_content))

    return routes_data


def extract_threat_cards_for_route(html_content, route, routes_data):
    """Get the content for a specific route."""
    if route in routes_data and routes_data[route]['content']:
        return routes_data[route]['content']
    return '<p style="text-align:center;padding:20px;">No data found for this route.</p>'


def generate_route_card(route, data):
    """Generate HTML for a route card in the index."""
    total = data['high'] + data['medium'] + data['low']
    return f'''
        <a href="routes/{route}.html" class="route-card" data-route="{route}">
            <div class="route-name">{route}</div>
            <div class="route-stats">
                <span class="high">🔴 {data['high']}</span>
                <span class="medium">🟡 {data['medium']}</span>
                <span class="low">🟢 {data['low']}</span>
            </div>
            <div class="route-flights">{total} threats</div>
        </a>'''


def generate_route_options(all_routes, current_route):
    """Generate option tags for route selector."""
    options = []
    for route in sorted(all_routes):
        selected = 'selected' if route == current_route else ''
        options.append(f'<option value="{route}.html" {selected}>{route}</option>')
    return '\n'.join(options)


def main():
    print("=" * 60)
    print("GENERATING SPLIT MOBILE PAGES BY ROUTE")
    print("=" * 60)

    # Read source file
    if not SOURCE_FILE.exists():
        print(f"ERROR: Source file not found: {SOURCE_FILE}")
        return

    print(f"\nReading source: {SOURCE_FILE}")
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()

    print(f"Source size: {len(html_content) / 1024 / 1024:.2f} MB")

    # Extract CSS from source
    print("\nExtracting CSS from source...")
    css_content = extract_css_from_source(html_content)
    print(f"CSS size: {len(css_content) / 1024:.1f} KB")

    # Extract routes data
    print("\nExtracting routes data...")
    routes_data = extract_routes_from_html(html_content)

    # Calculate totals
    total_high = sum(r['high'] for r in routes_data.values())
    total_medium = sum(r['medium'] for r in routes_data.values())
    total_low = sum(r['low'] for r in routes_data.values())

    print(f"Total: {total_high} High, {total_medium} Medium, {total_low} Low")

    # Create routes directory
    ROUTES_DIR.mkdir(exist_ok=True)
    print(f"\nCreated directory: {ROUTES_DIR}")

    # Generate index page
    print("\nGenerating index page...")
    route_cards = ''.join(generate_route_card(r, routes_data[r]) for r in sorted(routes_data.keys()))

    index_html = get_index_template().format(
        range_info="17 DEC 2025 - 31 MAR 2026",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        dashboard_url=DASHBOARD_URL,
        archive_url=ARCHIVE_URL,
        sharepoint_link=SHAREPOINT_LINK,
        total_high=total_high,
        total_medium=total_medium,
        total_low=total_low,
        route_cards=route_cards
    )

    with open(OUTPUT_INDEX, 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f"  -> {OUTPUT_INDEX} ({len(index_html) / 1024:.1f} KB)")

    # Generate individual route pages
    print("\nGenerating route pages...")
    all_routes = sorted(routes_data.keys())

    for route in all_routes:
        data = routes_data[route]

        # Get content for this route
        cards_html = extract_threat_cards_for_route(html_content, route, routes_data)

        # Generate route options for selector
        route_options = generate_route_options(all_routes, route)

        # Generate page
        page_html = get_route_page_template(css_content).format(
            route=route,
            high_count=data['high'],
            medium_count=data['medium'],
            low_count=data['low'],
            dashboard_url=DASHBOARD_URL,
            sharepoint_link=SHAREPOINT_LINK,
            route_options=route_options,
            threat_cards=cards_html
        )

        route_file = ROUTES_DIR / f"{route}.html"
        with open(route_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

        print(f"  -> {route_file} ({len(page_html) / 1024:.1f} KB)")

    print("\n" + "=" * 60)
    print("DONE!")
    print(f"Index: {OUTPUT_INDEX}")
    print(f"Routes: {ROUTES_DIR}/ ({len(all_routes)} files)")
    print("=" * 60)


if __name__ == "__main__":
    main()
