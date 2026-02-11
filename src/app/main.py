import os
import sys
import argparse
import logging
from pathlib import Path

# --- 0. [暴力调试] 开启全量日志 ---
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True
)
# 日志降噪
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("jieba").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.WARNING)

# --- 1. 环境预设 ---
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 2. 导入核心模块 ---
from app.settings import settings
from app.core.engine.factory import ModelFactory
from app.api.server import create_ui


def parse_args():
    parser = argparse.ArgumentParser(description="Agentic RAG System 启动器")
    parser.add_argument("--config", type=str, default="configs/default.yaml")
    parser.add_argument("--port", type=int, default=7860)
    return parser.parse_args()


def print_experiment_banner():
    print("\n" + "=" * 80)
    print(f"🧪 Agentic RAG System | 实验启动确认 (DEBUG MODE)")
    print("=" * 80)
    print(f"🆔 实验 ID     : {settings.experiment_id}")
    print(f"📝 实验描述    : {settings.experiment_description}")
    print("-" * 80)
    print(f"🗄️  向量集合    : {settings.collection_name}")
    print(f"🔪 切片策略    : {settings.chunking_strategy}")
    print("=" * 80 + "\n")


def main():
    """程序主入口"""
    args = parse_args()

    # 1. 加载配置
    try:
        settings.load_experiment_config(args.config)
    except Exception as e:
        print(f"❌ [Startup Error] 配置加载失败: {e}")
        sys.exit(1)

    # 2. 打印横幅
    print_experiment_banner()

    # 3. 预热模型
    print("⏳ 正在预热核心模型 (BGE-M3)...")
    try:
        ModelFactory.warmup_sparse_model()
    except Exception as e:
        logging.exception("❌ [Startup Error] 模型加载失败")
        sys.exit(1)

    # 4. 构建 UI
    try:
        print("🎨 正在构建 Gradio 界面...")
        demo = create_ui()
    except Exception as e:
        logging.exception(f"❌ [Startup Error] 初始化 UI 失败")
        sys.exit(1)

    # 5. 启动服务
    print(f"\n🚀 服务已启动! http://127.0.0.1:{args.port}")

    demo.launch(
        server_name="127.0.0.1",
        server_port=args.port,
        show_error=True,
        share=False,
        inbrowser=True
    )


if __name__ == "__main__":
    main()