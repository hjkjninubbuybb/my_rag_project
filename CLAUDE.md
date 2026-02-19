# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Enterprise-grade Agentic RAG (Retrieval-Augmented Generation) system with full-dimension ablation experiment support. Built with LlamaIndex, LangGraph, and Qdrant. Uses a **ComponentRegistry + Abstract Base Classes** architecture for extensibility. Supports DashScope (Qwen-Plus, text-embedding-v4) for LLM/embeddings and jieba-based lightweight sparse vectors for hybrid search.

## Commands

```bash
# Install dependencies
poetry install

# Run with default config
python src/rag/main.py

# Run with specific experiment config
python src/rag/main.py --config configs/default.yaml --port 7860

# Run retrieval evaluation (single config)
python scripts/evaluate_retrieval.py --config configs/default.yaml --limit 10

# Run ablation grid evaluation
python scripts/evaluate_retrieval.py --grid configs/ablation_grid.yaml --limit 10

# Run tests
pytest
```

Requires a `.env` file with `DASHSCOPE_API_KEY` set. See `.env.example` for template.

## Architecture

### Directory Structure

```
src/rag/                     # Main package
├── config/                  # Configuration management
│   ├── settings.py          # Global Settings (Pydantic BaseSettings, .env + YAML)
│   └── experiment.py        # ExperimentConfig (frozen dataclass) + ExperimentGrid
├── core/                    # Core abstractions (no concrete implementations)
│   ├── types.py             # ABC: BaseChunker, BaseLLMProvider, BaseEmbeddingProvider, BaseRerankerProvider
│   └── registry.py          # ComponentRegistry (decorator-based registration)
├── components/              # Pluggable component implementations
│   ├── chunkers/            # fixed.py, recursive.py, sentence.py
│   └── providers/           # dashscope.py (LLM/Embedding/Reranker), bgem3.py (jieba sparse vectors)
├── pipeline/                # Data processing pipelines
│   ├── ingestion.py         # IngestionService(config) — file → chunk → embed → Qdrant
│   └── retrieval.py         # RetrievalService(config) — hybrid/auto-merge/rerank + debug tool
├── storage/                 # Persistence layer
│   ├── vectordb.py          # VectorStoreManager(config) — Qdrant client management
│   └── metadata.py          # DatabaseManager(db_path, collection) — SQLite file tracking
├── agent/                   # LangGraph workflow
│   ├── workflow.py          # create_graph(config) — state graph with ReAct agent
│   ├── state.py             # State (main graph) + AgentState (subgraph), includes debug_retrieved_chunks
│   ├── nodes.py             # Graph nodes: summarize, rewrite, agent, extract, aggregate
│   ├── tools.py             # Tool factory: get_tools(config) → debug-enabled LangChain tools
│   └── prompts.py           # System prompts
├── experiment/              # Batch experiment management
│   ├── runner.py            # BatchExperimentRunner — smart ingestion + evaluation
│   └── results.py           # ResultsCollector — CSV/JSON persistence
├── ui/                      # Gradio interface (5 tabs)
│   └── app.py               # Config → Run → Results → Chat → KB Management
└── main.py                  # Entry point
```

### Key Design Patterns

- **ComponentRegistry + Decorators** (`core/registry.py`): Register components with `@ComponentRegistry.chunker("fixed")`. Look up by name at runtime. No if/elif routing.
- **Abstract Base Classes** (`core/types.py`): `BaseChunker`, `BaseLLMProvider`, `BaseEmbeddingProvider`, `BaseRerankerProvider`. Implement + register to add new components — zero changes to existing code. `BaseLLMProvider` provides dual LLM creation: `create_llm()` for LlamaIndex (retrieval pipeline) and `create_chat_model()` for LangChain (agent workflow).
- **ExperimentConfig** (`config/experiment.py`): Frozen dataclass holding all experiment dimensions. Passed via dependency injection to all pipeline components. `ingestion_fingerprint` property determines Qdrant collection sharing.
- **ExperimentGrid**: Cartesian product of all dimension lists. `generate_configs()` produces the full experiment matrix.
- **Dependency Injection**: All services (`IngestionService`, `RetrievalService`, `VectorStoreManager`, `create_graph`) accept `ExperimentConfig` instead of reading global `settings`.

### Chunking Strategies (Chinese-Optimized)

Three differentiated strategies, all optimized for Chinese text:

| Strategy | Implementation | Behavior |
|----------|---------------|----------|
| `fixed` | `TokenTextSplitter` | Hard cut by token count, ignores boundaries. Baseline. |
| `recursive` | LangChain `RecursiveCharacterTextSplitter` via `LangchainNodeParser` | Hierarchical Chinese separator fallback: `\n\n` → `\n` → `。` → `？` → `！` → `；` → `，` → ` ` → `""`. Cuts by character count. |
| `sentence` | LlamaIndex `SentenceSplitter` with Chinese regex | Sentence-boundary-aware splitting. Custom `secondary_chunking_regex` covers `。？！，、；：` etc. `paragraph_separator="\n\n"`. |

### Debug Data Interception (Tool Artifact)

The retrieval tool uses LangChain's **Tool Artifact** feature (`response_format="content_and_artifact"`) to capture retrieval metadata without polluting LLM input:

- `RetrievalService.as_debug_langchain_tool()` in `pipeline/retrieval.py`: calls `query_engine.query()`, extracts `source_nodes` (text, score, file_name), returns `(str_response, debug_chunks_list)`.
- `ToolNode` stores the artifact in `ToolMessage.artifact`.
- `extract_final_answer` in `nodes.py` collects all `ToolMessage.artifact` data into `debug_retrieved_chunks`.
- `State.debug_retrieved_chunks: Annotated[list[dict], operator.add]` accumulates chunks across parallel Map-Reduce agents.
- After `graph.ainvoke()`, the final state dict contains `debug_retrieved_chunks` for frontend rendering.

Each chunk dict: `{"text": str, "score": float, "source_file": str}`.

### Adding a New LLM Provider

1. Create `src/rag/components/providers/openai.py`
2. Implement `BaseLLMProvider` with both methods:
   - `create_llm()` → LlamaIndex LLM (for retrieval pipeline)
   - `create_chat_model()` → LangChain ChatModel (for agent workflow)
3. Decorate with `@ComponentRegistry.llm_provider("openai")`
4. Import in `components/providers/__init__.py`
5. Set `llm_provider: "openai"` in YAML config

### LangGraph Workflow

```
START → summarize → analyze_rewrite → route → [process_question x N] → aggregate → END
```

- **summarize**: Compresses conversation history (last 6 messages) into 1-2 sentence summary. Skips if < 4 messages.
- **analyze_rewrite**: LLM-powered question decomposition. Simple questions pass through; complex questions are split into 2-4 sub-questions. Outputs strict JSON, falls back to passthrough on parse failure.
- **route**: `Send()` dispatches each sub-question to a parallel `process_question` (ReAct agent subgraph).
- **process_question** (subgraph): `agent → [tools → agent]* → extract_answer`. ReAct loop with `knowledge_base_search` tool. `extract_final_answer` collects `ToolMessage.artifact` debug data.
- **aggregate**: Single-answer passthrough (skips LLM call); multi-answer LLM aggregation.

LLM created via `ComponentRegistry.get_llm_provider(config.llm_provider).create_chat_model(...)` — no hardcoded provider. `recursion_limit=25` prevents infinite ReAct loops.

### Retrieval Pipeline

Configurable via `ExperimentConfig`:
- `enable_hybrid`: Dense + jieba sparse vector search (alpha configurable)
- `enable_auto_merge`: AutoMergingRetriever wrapper (requires hierarchical node structure to be effective)
- `enable_rerank`: DashScope GTE Rerank post-processing

### Smart Ingestion

`BatchExperimentRunner.run_ingestion()` groups configs by `ingestion_fingerprint`. Same fingerprint (same chunking + embedding) shares one Qdrant collection. Already-populated collections are skipped.

### Evaluation Metrics

`BatchExperimentRunner.run_evaluation()` computes per-query:
- **Hit Rate**: Binary — did any top-K result match the ground truth?
- **MRR**: 1/rank of first hit (0 if no hit).
- **NDCG@K**: Normalized Discounted Cumulative Gain.

Hit detection via `SemanticJudge.is_hit()`: substring match OR cosine similarity > 0.85.

## Startup Sequence

Environment presets (`no_proxy`, `HF_ENDPOINT`) → load YAML config → trigger component auto-registration (`import rag.components`) → warmup jieba tokenizer (if hybrid enabled) → build Gradio UI → launch.

## Important Notes

- Sparse vectors in `components/providers/bgem3.py` use jieba tokenization + MD5 hash → `(List[int], List[float])` tuples for Qdrant. Lightweight (~15MB) alternative to BGE-M3 (~2GB).
- `metadata.db` requires `collection_name` column. Old schema DBs must be deleted.
- `HF_ENDPOINT=hf-mirror.com` for China-region model downloads.
- Runtime data lives in `data/` (gitignored): `vectordb/`, `metadata.db`, `reports/`, `uploads/`.
- `as_langchain_tool()` (original, no debug) is preserved in `RetrievalService` for non-debug use cases.
- Auto-Merge currently has no effect because ingestion creates flat nodes (no hierarchical parent-child structure). `HierarchicalNodeParser` would be needed for it to work.
