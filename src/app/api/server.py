import gradio as gr
import shutil
import asyncio
from pathlib import Path
from langchain_core.messages import HumanMessage

# 导入核心服务
from app.core.engine.ingestion import IngestionService
from app.core.graph.workflow import create_graph
from app.settings import settings


def create_ui():
    """构建 Gradio 界面"""

    # 1. 初始化系统核心组件
    # 注意：这里使用了单例模式或缓存，不用担心重复加载
    print("🔄 正在初始化系统组件 (LangGraph + LlamaIndex)...")
    graph = create_graph()
    ingestion = IngestionService()
    print("✅ 系统初始化完成")

    # 定义临时上传目录 (用于存放用户上传的原始文件)
    # 使用 settings 中定义的存储路径的同级目录 data/uploads
    # 比如: 项目根目录/data/uploads
    UPLOAD_DIR = Path("data/uploads")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # --- 事件处理函数 (Async) ---

    async def chat_handler(message, history):
        """处理对话请求"""
        if not message.strip():
            return ""

        # 模拟用户会话 ID (实际项目中应从 Request 获取)
        config = {"configurable": {"thread_id": "demo_user"}}

        # 调用 LangGraph
        # ainvoke 是异步调用，适合 IO 密集型任务
        response = await graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config
        )

        # 提取最后一条 AI 的回复内容
        return response["messages"][-1].content

    async def upload_handler(files):
        """处理文件上传请求"""
        if not files:
            return "⚠️ 请先选择文件。"

        try:
            # 1. 创建批次目录 (每次上传都放在一个新文件夹或清空旧文件夹)
            # 这里为了演示简单，我们使用固定目录并每次清空
            batch_dir = UPLOAD_DIR / "temp_batch"
            if batch_dir.exists():
                shutil.rmtree(batch_dir)
            batch_dir.mkdir(parents=True, exist_ok=True)

            # 2. 将 Gradio 的临时文件移动到我们的处理目录
            saved_files = []
            for file_obj in files:
                src_path = Path(file_obj.name)
                dst_path = batch_dir / src_path.name
                shutil.copy(src_path, dst_path)
                saved_files.append(src_path.name)

            # 3. 调用 IngestionService 进行处理 (切片 -> 存向量库)
            # 这一步是耗时操作，使用 await
            await ingestion.process_directory(str(batch_dir))

            return f"✅ 成功处理 {len(saved_files)} 个文件:\n" + "\n".join(saved_files)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"❌ 处理失败: {str(e)}"

    # --- 构建 UI 布局 ---
    with gr.Blocks(title="Agentic RAG System", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🤖 Agentic RAG 知识库助手")

        with gr.Tab("💬 智能对话 (Chat)"):
            gr.ChatInterface(
                fn=chat_handler,
                chatbot=gr.Chatbot(height=600, show_label=False),
                textbox=gr.Textbox(placeholder="请输入您的问题...", container=False, scale=7),
                description="基于 LangGraph + LlamaIndex 构建的企业级问答系统",
            )

        with gr.Tab("📚 知识库管理 (Knowledge Base)"):
            gr.Markdown("### 📄 上传文档")
            gr.Markdown("支持 PDF, Markdown, TXT 格式。上传后系统会自动切片并建立索引。")

            with gr.Row():
                file_input = gr.File(
                    file_count="multiple",
                    label="选择文件",
                    file_types=[".pdf", ".md", ".txt"],
                    height=200
                )

            with gr.Row():
                upload_btn = gr.Button("🚀 开始处理 (Ingest)", variant="primary", scale=1)
                # clear_btn = gr.Button("🗑️ 清空知识库", variant="stop", scale=1) # 预留功能

            output_status = gr.Textbox(label="系统日志", interactive=False, lines=5)

            # 绑定上传按钮事件
            upload_btn.click(
                fn=upload_handler,
                inputs=file_input,
                outputs=output_status
            )

    return demo