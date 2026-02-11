import os
import sys
import argparse
from pathlib import Path

# --- 1. 环境预设 (必须在任何 heavy import 之前执行) ---
# 强制不代理本地流量 (防止连接 Qdrant/Gradio 变慢或报错)
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

# 设置 HuggingFace 国内镜像 (保证 BGE-M3 能稳定下载)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 2. 导入核心模块 ---
# 注意：此时 settings 已经被 import，但还没加载 YAML，持有的是默认值
from app.settings import settings
from app.core.engine.factory import ModelFactory
from app.api.server import create_ui


def parse_args():
    """
    解析命令行参数
    支持通过 --config 指定实验配置文件
    """
    parser = argparse.ArgumentParser(description="Agentic RAG System 启动器")

    parser.add_argument(
        "--config",
        type=str,
        default="configs/default.yaml",
        help="指定实验配置文件路径 (YAML)，默认为 configs/default.yaml"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Gradio 服务端口，默认为 7860"
    )

    return parser.parse_args()


def print_experiment_banner():
    """
    [User Feedback] 打印启动横幅
    作用: 明确显示当前加载的实验参数，供科研记录和截图检查。
    """
    print("\n" + "=" * 80)
    print(f"🧪 Agentic RAG System | 实验启动确认")
    print("=" * 80)
    print(f"🆔 实验 ID     : {settings.experiment_id}")
    print(f"📝 实验描述    : {settings.experiment_description}")
    print("-" * 80)
    print(f"🗄️  向量集合    : {settings.collection_name} (多租户隔离)")
    print(f"🔪 切片策略    : {settings.chunking_strategy} (Strategy Pattern)")
    print(f"📏 切片参数    : Size={settings.chunk_size_child}, Overlap={settings.chunk_overlap}")
    print(f"🧠 LLM 模型    : {settings.llm_model}")
    print(f"📐 向量模型    : {settings.embedding_model}")
    print("=" * 80 + "\n")


def main():
    """程序主入口"""
    # 1. 解析命令行参数
    args = parse_args()

    # 2. [Critical] 加载实验配置
    # 必须在初始化任何业务逻辑之前完成配置加载，覆盖默认值
    try:
        settings.load_experiment_config(args.config)
    except Exception as e:
        print(f"❌ [Startup Error] 配置加载失败，程序中止: {e}")
        sys.exit(1)

    # 3. 打印当前实验参数 (这一步非常重要，截图留证用)
    print_experiment_banner()

    # 4. 预热核心模型 (BGE-M3)
    # Fail-fast 机制: 如果模型下载或加载失败，不要启动 UI，直接报错
    print("⏳ 正在预热核心模型 (BGE-M3)...")
    try:
        ModelFactory.warmup_sparse_model()
    except Exception:
        print("❌ [Startup Error] 模型加载失败，请检查网络或 HF_ENDPOINT 设置。")
        sys.exit(1)

    # 5. 构建 UI 应用
    # 此时 IngestionService 会初始化，它会通过 Factory 读取刚才加载的配置
    try:
        print("🎨 正在构建 Gradio 界面...")
        demo = create_ui()
    except Exception as e:
        print(f"❌ [Startup Error] 初始化 UI 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 6. 启动服务
    print(f"\n🚀 服务已启动! 请在浏览器访问: http://127.0.0.1:{args.port}")
    print("-" * 80)

    demo.launch(
        server_name="127.0.0.1",
        server_port=args.port,
        show_error=True,
        share=False,
        inbrowser=True
    )


if __name__ == "__main__":
    main()