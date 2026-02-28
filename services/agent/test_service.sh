#!/bin/bash

# Test script for Agent Service

echo "=== Agent Service Test ==="
echo ""

# Check if service is running
echo "1. Health Check..."
curl -s http://localhost:8002/api/v1/health | python -m json.tool
echo ""

# Test VLM analyze endpoint
echo "2. VLM Analyze Test..."
curl -s -X POST http://localhost:8002/api/v1/vlm/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "test_base64_string",
    "image_type": "screenshot",
    "surrounding_text": "测试上下文"
  }' | python -m json.tool
echo ""

# Test chat endpoint (requires Indexing Service)
echo "3. Chat Test (SSE)..."
curl -N -X POST http://localhost:8002/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "测试消息",
    "config": {
      "collection_name": "test",
      "llm_model": "qwen-plus"
    }
  }'
echo ""

echo "=== Test Complete ==="
