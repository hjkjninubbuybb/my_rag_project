import os
import sys
from app.api.server import create_ui
from app.settings import settings


def main():
    """程序主入口"""

    # 1. 环境检查
    print("-" * 50)
    print("🚀 正在启动 Agentic RAG System...")
    print("-" * 50)

    if not settings.dashscope_api_key:
        print("❌ [错误] 未检测到 DASHSCOPE_API_KEY")
        print("请检查项目根目录下的 .env 文件，确保已配置阿里云百炼 API Key。")
        sys.exit(1)

    print(f"✅ 环境检查通过")
    print(f"🧠 LLM 模型:\t{settings.llm_model}")
    print(f"🗄️  向量库路径:\t{settings.qdrant_path}")
    print("-" * 50)

    # 2. 创建 UI 应用
    try:
        demo = create_ui()
    except Exception as e:
        print(f"❌ 初始化 UI 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 3. 启动服务
    print("\n🌐 服务启动成功! 请在浏览器访问以下地址:")
    print("👉 http://localhost:7860")
    print("-" * 50)

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False  # 如果需要生成公网链接，改为 True
    )


if __name__ == "__main__":
    main()