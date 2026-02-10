import os
import sys
from pathlib import Path

# 👇【关键配置 1】强制不代理本地流量
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

# 👇【关键配置 2】设置 HuggingFace 国内镜像
# BGE-M3 需要从这里下载模型
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 路径修复
current_file_path = Path(__file__).resolve()
src_path = current_file_path.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from app.api.server import create_ui
from app.settings import settings
from app.core.engine.factory import ModelFactory


def main():
    """程序主入口"""
    print("-" * 50)
    print("🚀 正在启动 Agentic RAG System...")
    print("-" * 50)

    # 1. 检查 Key
    if not settings.dashscope_api_key:
        print("❌ [错误] 未检测到 DASHSCOPE_API_KEY")
        print("请检查项目根目录下的 .env 文件，确保已配置阿里云百炼 API Key。")
        sys.exit(1)

    print(f"✅ 环境检查通过")
    print(f"🧠 LLM 模型:\t{settings.llm_model}")
    print(f"🗄️  向量库路径:\t{settings.qdrant_path}")
    print(f"⚡ 稀疏模型:\tBGE-M3 (中文增强版, 无 NLTK 依赖)")
    print("-" * 50)

    # 2. 预热 BGE-M3 模型 (这是最耗时的一步)
    # 只有这一步跑完了，才会往下执行
    try:
        ModelFactory.warmup_sparse_model()
    except Exception:
        # 如果报错，通常是因为没装 FlagEmbedding 或网络问题
        sys.exit(1)

    print("-" * 50)

    # 3. 创建 UI 应用
    try:
        print("🎨 正在构建 UI...")
        demo = create_ui()
    except Exception as e:
        print(f"❌ 初始化 UI 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 4. 启动服务
    print("\n🌐 服务启动成功! 请在浏览器访问以下地址:")
    print("👉 http://127.0.0.1:7860")
    print("-" * 50)

    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        share=False,
        inbrowser=True
    )


if __name__ == "__main__":
    main()