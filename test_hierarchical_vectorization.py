"""Test hierarchical node vectorization"""
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "services" / "ingestion"))

import asyncio
from shared.rag_shared.config.experiment import ExperimentConfig
from services.ingestion.app.services.ingestion import IngestionService

async def test_hierarchical_vectorization():
    print("="*50)
    print("Testing Hierarchical Node Vectorization")
    print("="*50)

    # 1. Load config
    config_path = project_root / "configs" / "hierarchical_markdown.yaml"
    print(f"\n[1] Loading config: {config_path}")
    config = ExperimentConfig.from_yaml(str(config_path))
    print(f"  - Collection: {config.collection_name}")
    print(f"  - Chunking: {config.chunking_strategy}")

    # 2. Create service
    print(f"\n[2] Creating IngestionService")
    service = IngestionService(config)

    # 3. Process test document
    input_dir = project_root / "data" / "uploads" / "documents"
    print(f"\n[3] Processing directory: {input_dir}")

    result = await service.process_directory(str(input_dir))

    # 4. Show result
    print(f"\n[4] Result:")
    if isinstance(result, dict):
        print("  - Hierarchical mode")
        print(f"  - Parent nodes: {result['parent_count']}")
        print(f"  - Child nodes: {result['child_count']}")
        print(f"  - Vectorized: {result['vectorized_count']}")
        print(f"  - Collection: {result['collection_name']}")
    else:
        print(f"  - Flat mode: {result}")

    print("\n" + "="*50)
    print("Test completed!")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_hierarchical_vectorization())
