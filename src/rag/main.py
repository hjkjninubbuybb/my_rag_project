import os
import sys
import argparse
from pathlib import Path

# --- 1. 环境预设 (必须在任何 heavy import 之前执行) ---
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 2. 导入核心模块 ---
from rag.config.settings import settings
from rag.components.providers.bgem3 import SparseModelManager
from rag.ui.app import create_ui

# 触发组件自动注册
import rag.components  # noqa: F401


def parse_args():
    parser = argparse.ArgumentParser(description="Agentic RAG 消融实验平台")
    parser.add_argument(
        "--config", type=str, default="configs/default.yaml",
        help="实验配置文件路径 (YAML)",
    )
    parser.add_argument(
        "--port", type=int, default=7860,
        help="Gradio 服务端口",
    )
    return parser.parse_args()


def print_experiment_banner():
    print("\n" + "=" * 80)
    print(f"Agentic RAG System | 实验启动确认")
    print("=" * 80)
    print(f"  实验 ID     : {settings.experiment_id}")
    print(f"  实验描述    : {settings.experiment_description}")
    print("-" * 80)
    print(f"  向量集合    : {settings.collection_name}")
    print(f"  切片策略    : {settings.chunking_strategy}")
    print(f"  切片参数    : Size={settings.chunk_size_child}, Overlap={settings.chunk_overlap}")
    print(f"  LLM 供应商  : {settings.llm_provider} / {settings.llm_model}")
    print(f"  Embedding   : {settings.embedding_provider} / {settings.embedding_model}")
    print(f"  Reranker    : {settings.reranker_provider} / {settings.reranker_model}")
    print(f"  混合检索    : {settings.enable_hybrid}")
    print(f"  自动合并    : {settings.enable_auto_merge}")
    print(f"  重排序      : {settings.enable_rerank}")
    print("=" * 80 + "\n")


def main():
    args = parse_args()

    # 加载实验配置 (YAML -> settings 全局单例)
    try:
        settings.load_experiment_config(args.config)
    except Exception as e:
        print(f"[Startup Error] 配置加载失败: {e}")
        sys.exit(1)

    print_experiment_banner()

    # 预热稀疏向量分词器
    if settings.enable_hybrid:
        print("正在初始化中文分词器...")
        SparseModelManager.warmup()

    # 构建 UI
    try:
        print("正在构建 Gradio 界面...")
        demo = create_ui()
    except Exception as e:
        print(f"[Startup Error] UI 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 启动服务
    print(f"\n服务已启动: http://127.0.0.1:{args.port}")
    print("-" * 80)

    demo.launch(
        server_name="127.0.0.1",
        server_port=args.port,
        show_error=True,
        share=False,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
