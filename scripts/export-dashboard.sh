#!/bin/bash
#
# Export Grafana dashboard as static HTML/images
#
# Usage:
#   ./scripts/export-dashboard.sh [time-from] [time-to]
#
# Examples:
#   ./scripts/export-dashboard.sh                    # Last 30 days
#   ./scripts/export-dashboard.sh now-90d now        # Last 90 days
#   ./scripts/export-dashboard.sh now-1y now         # Last year
#   ./scripts/export-dashboard.sh 2024-01-01 now     # From specific date
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
DASHBOARD_UID="${DASHBOARD_UID:-git-repository-overview}"
OUTPUT_DIR="${OUTPUT_DIR:-docs}"
TIME_FROM="${1:-now-30d}"
TIME_TO="${2:-now}"

echo -e "${GREEN}=== Grafana Dashboard Exporter ===${NC}"
echo ""
echo "Configuration:"
echo "  Grafana URL: $GRAFANA_URL"
echo "  Dashboard UID: $DASHBOARD_UID"
echo "  Time Range: $TIME_FROM to $TIME_TO"
echo "  Output Directory: $OUTPUT_DIR"
echo ""

# Check if Grafana is running
echo -e "${YELLOW}Checking Grafana availability...${NC}"
if ! curl -s "$GRAFANA_URL/api/health" > /dev/null; then
    echo -e "${RED}✗ Grafana is not available at $GRAFANA_URL${NC}"
    echo ""
    echo "Please ensure Grafana is running:"
    echo "  docker compose up -d"
    echo ""
    exit 1
fi
echo -e "${GREEN}✓ Grafana is available${NC}"
echo ""

# Check if data exists in Elasticsearch
echo -e "${YELLOW}Checking for data in Elasticsearch...${NC}"
COMMIT_COUNT=$(curl -s "http://localhost:9200/git-commits/_count" 2>/dev/null | jq -r '.count' 2>/dev/null || echo "0")
echo "  Found $COMMIT_COUNT commits in Elasticsearch"

if [ "$COMMIT_COUNT" = "0" ]; then
    echo -e "${YELLOW}⚠ Warning: No data found. Dashboard will be empty.${NC}"
    echo ""
    echo "To populate data, run:"
    echo "  ./run.sh"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Run the export script
echo -e "${YELLOW}Exporting dashboard...${NC}"
python3 scripts/export-grafana-dashboard.py \
    --grafana-url "$GRAFANA_URL" \
    --username "$GRAFANA_USER" \
    --password "$GRAFANA_PASSWORD" \
    --dashboard-uid "$DASHBOARD_UID" \
    --output-dir "$OUTPUT_DIR" \
    --time-from "$TIME_FROM" \
    --time-to "$TIME_TO"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=== Export Complete ===${NC}"
    echo ""
    echo "Output files:"
    echo "  HTML: $OUTPUT_DIR/index.html"
    echo "  Images: $OUTPUT_DIR/images/"
    echo ""
    echo "To view locally:"
    echo "  open $OUTPUT_DIR/index.html"
    echo ""
    echo "To deploy to GitHub Pages:"
    echo "  1. Commit the $OUTPUT_DIR directory"
    echo "  2. Push to GitHub"
    echo "  3. Enable GitHub Pages in repository settings (source: gh-pages branch)"
    echo "  4. Or use the automated workflow: .github/workflows/deploy-dashboard.yml"
    echo ""
else
    echo -e "${RED}✗ Export failed${NC}"
    exit 1
fi

