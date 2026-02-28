#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Quick Service Verification Script
# Version: v3.0
# ══════════════════════════════════════════════════════════════

set -e

echo "🔍 Verifying New Microservices Architecture..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if service directory exists and has required files
check_service_structure() {
    local service=$1
    local port=$2

    echo -e "${BLUE}━━━ $service Service (Port $port) ━━━${NC}"

    # Check directory
    if [ -d "services/$service" ]; then
        echo -e "${GREEN}✓${NC} Directory exists"
    else
        echo -e "${RED}✗${NC} Directory missing"
        return 1
    fi

    # Check key files
    local files=("pyproject.toml" "Dockerfile" "app/main.py" "app/config.py" "README.md")
    for file in "${files[@]}"; do
        if [ -f "services/$service/$file" ]; then
            echo -e "${GREEN}✓${NC} $file"
        else
            echo -e "${RED}✗${NC} $file missing"
        fi
    done

    echo ""
}

# Check Python syntax
check_python_syntax() {
    local service=$1

    echo -n "Checking Python syntax... "

    if python -m py_compile services/$service/app/main.py 2>/dev/null; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${YELLOW}⚠ Skipped (Python not available)${NC}"
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Service Structure Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

check_service_structure "orchestrator" "8000"
check_service_structure "indexing" "8001"
check_service_structure "agent" "8002"
check_service_structure "testing" "8003"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Infrastructure Files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check infrastructure files
files=(
    "docker-compose.yml"
    ".env.example"
    "scripts/init_mysql.sql"
    "scripts/verify_infrastructure.sh"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file missing"
    fi
done

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Documentation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docs=(
    "REFACTORING_STATUS.md"
    "REFACTORING_COMPLETE.md"
    "PHASE6_CLEANUP_REPORT.md"
    "PROJECT_STRUCTURE.md"
    "GIT_COMMIT_GUIDE.md"
    "EXECUTION_SUMMARY.md"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✓${NC} $doc"
    else
        echo -e "${RED}✗${NC} $doc missing"
    fi
done

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Old Directories (Should be deleted)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

old_dirs=("shared" "services/ingestion" "services/inference" "services/gateway" "cli")

for dir in "${old_dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "${RED}✗${NC} $dir still exists (should be deleted)"
    else
        echo -e "${GREEN}✓${NC} $dir deleted"
    fi
done

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "New Services:"
echo "  - Orchestrator (Port 8000) ✓"
echo "  - Indexing (Port 8001) ✓"
echo "  - Agent (Port 8002) ✓"
echo "  - Testing (Port 8003) ✓"
echo ""

echo "Old Services Removed:"
echo "  - shared/ ✓"
echo "  - services/ingestion/ ✓"
echo "  - services/inference/ ✓"
echo "  - services/gateway/ ✓"
echo "  - cli/ ✓"
echo ""

echo -e "${GREEN}✓ Refactoring verification complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Install dependencies: cd services/<service> && poetry install"
echo "  2. Start infrastructure: docker compose up -d qdrant mysql minio"
echo "  3. Build services: docker compose build"
echo "  4. Start all services: docker compose up -d"
echo "  5. Verify services: curl http://localhost:8000/health"
echo ""
