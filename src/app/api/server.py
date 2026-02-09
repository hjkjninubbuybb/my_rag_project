import os
import shutil
from pathlib import Path

import gradio as gr
from langchain_core.messages import HumanMessage

from app.core.engine.ingestion import IngestionService
from app.core.engine.store import VectorStoreManager
from app.core.engine.database import DatabaseManager
from app.core.graph.workflow import create_graph

# 定义上传目录
UPLOAD_DIR = Path("data/uploads/temp_batch")


def create_ui():
    """构建 Gradio 界面"""
    ingestion = IngestionService()
    store_manager = VectorStoreManager()
    db_manager = DatabaseManager()
    graph = create_graph()

    # --- 辅助函数 ---

    def list_staging_files():
        """列出【暂存区】文件 (读磁盘)"""
        if not UPLOAD_DIR.exists():
            return None
        files = [str(f) for f in UPLOAD_DIR.iterdir() if f.is_file()]
        return files if files else None

    def list_db_files():
        """列出【数据库】已索引文件 (读 SQLite)"""
        files = db_manager.get_all_files()

        # 👇【核心修复】
        # 必须返回组件对象并指定 choices，才能更新“选项列表”
        # 如果只返回 files 列表，Gradio 会以为你在设置“默认选中项”
        return gr.CheckboxGroup(choices=files, value=[], label=f"已索引文档列表 ({len(files)})")

    # --- 核心逻辑 ---

    async def process_query(message, history):
        """处理对话"""
        if not message: return "请输入问题"
        inputs = {"messages": [HumanMessage(content=message)]}
        config = {"configurable": {"thread_id": "1"}}
        try:
            response = await graph.ainvoke(inputs, config=config)
            if "messages" in response and response["messages"]:
                return response["messages"][-1].content
            return "❌ Agent 未生成有效回复。"
        except Exception as e:
            return f"❌ 处理出错: {str(e)}"

    def handle_upload(files):
        """上传到暂存区"""
        if not files: return None, "⚠️ 请先选择文件"
        if not UPLOAD_DIR.exists(): UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for file in files:
            file_path = Path(file.name)
            target_path = UPLOAD_DIR / file_path.name
            shutil.copy(file_path, target_path)
            saved_paths.append(str(target_path))
        return saved_paths, f"✅ 已上传 {len(saved_paths)} 个文件到暂存区，请点击“开始处理”。"

    async def start_ingestion():
        """执行处理 (入库 + 记账)"""
        if not UPLOAD_DIR.exists() or not any(UPLOAD_DIR.iterdir()):
            return "⚠️ 暂存区为空，请先上传文件。", list_db_files()

        # 1. 先记下我们要处理哪些文件名
        files_to_process = [f.name for f in UPLOAD_DIR.iterdir() if f.is_file()]

        try:
            # 2. 调用 LlamaIndex 进行处理
            await ingestion.process_directory(str(UPLOAD_DIR))

            # 3. 处理成功！开始记账
            for filename in files_to_process:
                db_manager.add_file(filename)

            # 4. 清空暂存区物理文件
            shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            return f"🎉 成功索引 {len(files_to_process)} 个文件！", None, list_db_files()
        except Exception as e:
            return f"❌ 处理失败: {str(e)}", list_staging_files(), list_db_files()

    def clear_staging():
        """清空暂存区"""
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return None, "🗑️ 暂存区已清空。"

    def delete_from_db(selected_files):
        """从数据库删除"""
        if not selected_files:
            return "⚠️ 请先在下方列表中勾选要删除的文件。", list_db_files()

        deleted_count = 0
        for file_name in selected_files:
            store_manager.delete_file(file_name)
            db_manager.remove_file(file_name)
            deleted_count += 1

        return f"🗑️ 已删除 {deleted_count} 个文件。", list_db_files()

    # --- UI 布局 ---
    with gr.Blocks(title="Agentic RAG 知识库助手", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🤖 Agentic RAG 知识库助手")

        with gr.Tab("💬 智能对话"):
            gr.ChatInterface(fn=process_query)

        with gr.Tab("📚 知识库管理"):
            with gr.Row():
                # 左侧：暂存区
                with gr.Column(scale=1):
                    gr.Markdown("### 1️⃣ 暂存区 (待处理)")
                    staging_file_output = gr.File(label="待处理文件", file_count="multiple", interactive=True)
                    with gr.Row():
                        upload_btn = gr.Button("📂 确认上传", variant="secondary")
                        clear_staging_btn = gr.Button("🗑️ 清空暂存", variant="stop")
                    ingest_btn = gr.Button("🚀 开始处理 (入库)", variant="primary")

                # 右侧：已入库
                with gr.Column(scale=1):
                    gr.Markdown("### 2️⃣ 已入库 (数据库)")
                    # 初始 choices 为空
                    db_file_list = gr.CheckboxGroup(label="已索引文档列表", choices=[], interactive=True)
                    with gr.Row():
                        refresh_db_btn = gr.Button("🔄 刷新列表")
                        delete_db_btn = gr.Button("❌ 删除选中", variant="stop")

            log_output = gr.Textbox(label="系统操作日志", interactive=False, lines=3)

            # 事件绑定
            demo.load(fn=list_staging_files, outputs=staging_file_output)
            # 这里的 list_db_files 返回了 gr.CheckboxGroup(...)，这会自动更新 db_file_list 的 choices
            demo.load(fn=list_db_files, outputs=db_file_list)

            upload_btn.click(fn=handle_upload, inputs=staging_file_output, outputs=[staging_file_output, log_output])
            clear_staging_btn.click(fn=clear_staging, inputs=None, outputs=[staging_file_output, log_output])
            ingest_btn.click(fn=start_ingestion, inputs=None, outputs=[log_output, staging_file_output, db_file_list])
            refresh_db_btn.click(fn=list_db_files, inputs=None, outputs=db_file_list)
            delete_db_btn.click(fn=delete_from_db, inputs=db_file_list, outputs=[log_output, db_file_list])

    return demo