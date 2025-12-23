#!/usr/bin/env python3
"""
Export Grafana dashboard as images and HTML for static deployment.

This script:
1. Waits for Grafana to be ready
2. Exports dashboard panels as PNG images
3. Generates an HTML page displaying all panels
4. Saves everything to a docs/ directory for GitHub Pages
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


class GrafanaExporter:
    def __init__(
        self,
        grafana_url: str,
        username: str,
        password: str,
        output_dir: str = "docs",
    ):
        self.grafana_url = grafana_url.rstrip("/")
        self.auth = HTTPBasicAuth(username, password)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.output_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def wait_for_grafana(self, timeout: int = 120) -> bool:
        """Wait for Grafana to be ready."""
        print(f"Waiting for Grafana at {self.grafana_url}...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.grafana_url}/api/health", timeout=5
                )
                if response.status_code == 200:
                    print("✓ Grafana is ready")
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(5)
            print("  Still waiting...")
        print("✗ Grafana did not become ready in time")
        return False

    def get_dashboard_by_uid(self, uid: str) -> Optional[Dict]:
        """Get dashboard JSON by UID."""
        try:
            response = requests.get(
                f"{self.grafana_url}/api/dashboards/uid/{uid}",
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"✗ Error fetching dashboard {uid}: {e}")
            return None

    def search_dashboards(self) -> List[Dict]:
        """Search for all dashboards."""
        try:
            response = requests.get(
                f"{self.grafana_url}/api/search?type=dash-db",
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"✗ Error searching dashboards: {e}")
            return []

    def render_panel(
        self,
        dashboard_uid: str,
        panel_id: int,
        width: int = 1200,
        height: int = 400,
        time_from: str = "now-30d",
        time_to: str = "now",
    ) -> Optional[bytes]:
        """Render a panel as PNG image."""
        url = (
            f"{self.grafana_url}/render/d-solo/{dashboard_uid}/"
            f"?panelId={panel_id}&width={width}&height={height}"
            f"&from={time_from}&to={time_to}"
        )
        try:
            response = requests.get(url, auth=self.auth, timeout=60)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error rendering panel {panel_id}: {e}")
            return None

    def export_dashboard(
        self,
        dashboard_uid: str,
        time_from: str = "now-30d",
        time_to: str = "now",
    ) -> bool:
        """Export all panels from a dashboard."""
        print(f"\nExporting dashboard: {dashboard_uid}")

        # Get dashboard definition
        dashboard_data = self.get_dashboard_by_uid(dashboard_uid)
        if not dashboard_data:
            return False

        dashboard = dashboard_data.get("dashboard", {})
        title = dashboard.get("title", "Unknown Dashboard")
        panels = dashboard.get("panels", [])

        print(f"  Dashboard: {title}")
        print(f"  Found {len(panels)} panels")

        # Export each panel
        panel_images = []
        for panel in panels:
            panel_id = panel.get("id")
            panel_title = panel.get("title", f"Panel {panel_id}")
            panel_type = panel.get("type", "unknown")

            # Skip row panels (they're just layout containers)
            if panel_type == "row":
                continue

            print(f"  Rendering panel {panel_id}: {panel_title}")

            # Determine panel dimensions
            grid_pos = panel.get("gridPos", {})
            width = grid_pos.get("w", 12) * 100  # Grafana grid units to pixels
            height = grid_pos.get("h", 8) * 50

            # Render panel
            image_data = self.render_panel(
                dashboard_uid, panel_id, width, height, time_from, time_to
            )
            if image_data:
                # Save image
                image_filename = f"panel_{panel_id}.png"
                image_path = self.images_dir / image_filename
                image_path.write_bytes(image_data)
                print(f"    ✓ Saved to {image_path}")

                panel_images.append(
                    {
                        "id": panel_id,
                        "title": panel_title,
                        "filename": image_filename,
                        "width": width,
                        "height": height,
                    }
                )
            else:
                print(f"    ✗ Failed to render panel {panel_id}")

        # Generate HTML page
        if panel_images:
            html_path = self.output_dir / "index.html"
            self.generate_html(title, panel_images, time_from, time_to, html_path)
            print(f"\n✓ Generated {html_path}")
            return True

        return False

    def generate_html(
        self,
        dashboard_title: str,
        panels: List[Dict],
        time_from: str,
        time_to: str,
        output_path: Path,
    ):
        """Generate HTML page displaying all panels."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard_title} - Snapshot</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #0b0c0e;
            color: #d8d9da;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            background: #1a1b1e;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            border: 1px solid #2a2b2e;
        }}
        h1 {{
            color: #ffffff;
            font-size: 2em;
            margin-bottom: 10px;
        }}
        .meta {{
            color: #9fa1a4;
            font-size: 0.9em;
        }}
        .meta strong {{
            color: #d8d9da;
        }}
        .panel {{
            background: #1a1b1e;
            border: 1px solid #2a2b2e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .panel:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        .panel h2 {{
            color: #ffffff;
            font-size: 1.3em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #2a2b2e;
        }}
        .panel img {{
            width: 100%;
            height: auto;
            border-radius: 4px;
            background: #0b0c0e;
        }}
        .badge {{
            display: inline-block;
            background: #3d3e42;
            color: #ffffff;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 0.85em;
            margin-left: 10px;
        }}
        footer {{
            text-align: center;
            margin-top: 50px;
            padding: 20px;
            color: #9fa1a4;
            font-size: 0.9em;
        }}
        footer a {{
            color: #6e9ecf;
            text-decoration: none;
        }}
        footer a:hover {{
            text-decoration: underline;
        }}
        .warning {{
            background: #3d2e1e;
            border: 1px solid #5d4e3e;
            border-radius: 8px;
            padding: 15px 20px;
            margin-bottom: 30px;
            color: #f0c674;
        }}
        .warning strong {{
            color: #f0a020;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{dashboard_title}</h1>
            <div class="meta">
                <strong>Time Range:</strong> {time_from} to {time_to}<br>
                <strong>Generated:</strong> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}<br>
                <strong>Panels:</strong> {len(panels)}
            </div>
        </header>

        <div class="warning">
            <strong>⚠️ Static Snapshot:</strong> This is a static snapshot of the Grafana dashboard.
            For live, interactive dashboards with filtering and drill-down capabilities, 
            please visit the full Grafana instance.
        </div>
"""

        for panel in panels:
            html += f"""
        <div class="panel">
            <h2>
                {panel['title']}
                <span class="badge">Panel {panel['id']}</span>
            </h2>
            <img src="images/{panel['filename']}" 
                 alt="{panel['title']}" 
                 loading="lazy">
        </div>
"""

        html += f"""
    </div>
    <footer>
        <p>
            Generated by <a href="https://github.com/kibotu/git-panorama" target="_blank">Git Panorama</a>
            • Powered by <a href="https://grafana.com/" target="_blank">Grafana</a>
        </p>
    </footer>
</body>
</html>
"""
        output_path.write_text(html)


def main():
    parser = argparse.ArgumentParser(
        description="Export Grafana dashboard as static images and HTML"
    )
    parser.add_argument(
        "--grafana-url",
        default=os.getenv("GRAFANA_URL", "http://localhost:3000"),
        help="Grafana URL (default: http://localhost:3000)",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("GRAFANA_USER", "admin"),
        help="Grafana username (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("GRAFANA_PASSWORD", "admin"),
        help="Grafana password (default: admin)",
    )
    parser.add_argument(
        "--dashboard-uid",
        default="git-stats-repository",
        help="Dashboard UID to export (default: git-stats-repository)",
    )
    parser.add_argument(
        "--output-dir",
        default="docs",
        help="Output directory (default: docs)",
    )
    parser.add_argument(
        "--time-from",
        default="now-30d",
        help="Time range start (default: now-30d)",
    )
    parser.add_argument(
        "--time-to", default="now", help="Time range end (default: now)"
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=120,
        help="Seconds to wait for Grafana (default: 120)",
    )

    args = parser.parse_args()

    # Create exporter
    exporter = GrafanaExporter(
        grafana_url=args.grafana_url,
        username=args.username,
        password=args.password,
        output_dir=args.output_dir,
    )

    # Wait for Grafana to be ready
    if not exporter.wait_for_grafana(timeout=args.wait_timeout):
        print("\n✗ Grafana is not available. Exiting.")
        sys.exit(1)

    # Export dashboard
    success = exporter.export_dashboard(
        dashboard_uid=args.dashboard_uid,
        time_from=args.time_from,
        time_to=args.time_to,
    )

    if success:
        print("\n✓ Dashboard export completed successfully!")
        print(f"  Output: {args.output_dir}/index.html")
        sys.exit(0)
    else:
        print("\n✗ Dashboard export failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

