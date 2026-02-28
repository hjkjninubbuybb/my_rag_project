#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Infrastructure Verification Script
# Version: v3.0
# ══════════════════════════════════════════════════════════════

set -e

echo "🔍 Verifying RAG System Infrastructure..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check_service() {
    local name=$1
    local url=$2
    local expected=$3

    echo -n "Checking $name... "

    if curl -s -f "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Check MySQL
check_mysql() {
    echo -n "Checking MySQL... "

    if docker exec rag_mysql mysql -u rag_user -prag_password -e "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"

        # Check tables
        echo -n "  - Checking tables... "
        tables=$(docker exec rag_mysql mysql -u rag_user -prag_password rag_db -e "SHOW TABLES" 2>/dev/null | grep -v "Tables_in" | wc -l)
        if [ "$tables" -ge 4 ]; then
            echo -e "${GREEN}✓ $tables tables found${NC}"
        else
            echo -e "${YELLOW}⚠ Only $tables tables found (expected 4+)${NC}"
        fi
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Check MinIO buckets
check_minio() {
    echo -n "Checking MinIO... "

    if curl -s -f "http://localhost:9000/minio/health/live" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"

        # Check buckets (requires mc client)
        if command -v mc &> /dev/null; then
            echo -n "  - Checking buckets... "
            mc alias set local http://localhost:9000 minioadmin minioadmin > /dev/null 2>&1
            buckets=$(mc ls local 2>/dev/null | wc -l)
            if [ "$buckets" -ge 2 ]; then
                echo -e "${GREEN}✓ $buckets buckets found${NC}"
            else
                echo -e "${YELLOW}⚠ Only $buckets buckets found (expected 2+)${NC}"
            fi
        fi
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "External Storage Layer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_service "Qdrant" "http://localhost:6333/health"
check_mysql
check_minio

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "Access URLs:"
echo "  - Qdrant Dashboard: http://localhost:6333/dashboard"
echo "  - MinIO Console:    http://localhost:9001 (minioadmin/minioadmin)"
echo "  - MySQL:            localhost:3306 (rag_user/rag_password)"
echo ""
echo -e "${GREEN}✓ Infrastructure verification complete!${NC}"
