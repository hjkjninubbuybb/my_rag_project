"""
[Architecture Role: Orchestrator (指挥官)]
此模块是系统的 "大脑" 和 "UI 控制层"。它负责协调 "三权分立" 架构中的所有组件。

核心职责:
1. [Coordination] 组装 IngestionService (工人), DatabaseManager (会计), VectorStoreManager (库管)。
2. [Atomic Transaction] 确保 "入库" 操作的原子性：
   (物理文件处理 -> 向量入库 -> SQLite记账 -> 物理文件清理 -> UI刷新)。
3. [UI Logic] 处理 Gradio 的交互逻辑，特别是复杂的组件状态更新。

关键交互:
- 读取 Staging Area (磁盘) 显示待处理文件。
- 读取 Ledger (SQLite) 显示已索引文件 (Source of Truth)。
- 调用 Memory (Qdrant) 进行检索和物理删除。
"""

import shutil
import traceback  # 👇 新增，用于打印详细堆栈
from pathlib import Path

import gradio as gr
from langchain_core.messages import HumanMessage

from app.core.engine.ingestion import IngestionService
from app.core.engine.store import VectorStoreManager
from app.core.engine.database import DatabaseManager
from app.core.graph.workflow import create_graph

# [Staging Area] 定义暂存区路径
# 规则: 仅作为临时中转站，处理完成后必须清空
UPLOAD_DIR = Path("data/uploads/temp_batch")


def create_ui():
    """构建 Gradio 界面并初始化所有服务"""

    # --- 初始化三大架构组件 ---
    ingestion = IngestionService()  # 负责: 读取文件 -> Embedding -> 存入 Qdrant
    store_manager = VectorStoreManager()  # 负责: Qdrant 物理删除
    db_manager = DatabaseManager()  # 负责: SQLite 记账 (UI 唯一数据源)

    # 初始化 LangGraph 工作流
    graph = create_graph()

    # --- 辅助函数 ---

    def list_staging_files():
        """
        [读暂存区] 列出磁盘上的待处理文件
        Side Effect: 读取磁盘 IO
        """
        if not UPLOAD_DIR.exists():
            return None
        files = [str(f) for f in UPLOAD_DIR.iterdir() if f.is_file()]
        return files if files else None

    def list_db_files():
        """
        [读账本] 列出已索引文件

        Critical Logic (Gradio Trick):
        这里不仅返回文件列表，还必须返回一个 gr.CheckboxGroup 组件对象。
        原因: Gradio 的 update 机制要求，如果要更新组件的 `choices` (选项列表)，
        必须返回组件本身。如果只返回 list，Gradio 会误以为是设置 `value` (选中项)。
        """
        files = db_manager.get_all_files()

        # 👇 返回组件对象以触发 choices 更新
        return gr.CheckboxGroup(choices=files, value=[], label=f"已索引文档列表 ({len(files)})")

    # --- 核心逻辑 ---

    async def process_query(message, history):
        """
        [Async Agent] 处理对话
        Architecture Note: 使用全异步 (async/await) 调用 Graph，
        防止在等待 LLM 响应时阻塞整个 UI 线程。
        """
        if not message: return "请输入问题"
        inputs = {"messages": [HumanMessage(content=message)]}
        config = {"configurable": {"thread_id": "1"}}
        try:
            # 异步调用 LangGraph
            response = await graph.ainvoke(inputs, config=config)
            if "messages" in response and response["messages"]:
                return response["messages"][-1].content
            return "❌ Agent 未生成有效回复。"
        except Exception as e:
            return f"❌ 处理出错: {str(e)}"

    def handle_upload(files):
        """
        [写暂存区] 用户上传文件
        Action: 将文件从 Gradio 临时目录 复制到 系统暂存区 (data/uploads/temp_batch)
        """
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
        """
        [Atomic Ingestion Flow] 执行原子化入库流程
        这是本系统最关键的事务逻辑，步骤必须严格按顺序执行：

        1. Check: 检查暂存区是否有文件。
        2. Ingest: 调用 LlamaIndex 处理文件，存入 Qdrant (耗时操作)。
        3. Write Ledger: 只有 Qdrant 成功后，才在 SQLite 记一笔。
        4. Cleanup: 立即清空物理暂存区，防止数据滞留。
        5. Refresh UI: 更新前端列表。
        """
        # 👇【Bug 修复】确保这里返回 3 个值 (None)，否则 Gradio 会报 unpacking error
        if not UPLOAD_DIR.exists() or not any(UPLOAD_DIR.iterdir()):
            return "⚠️ 暂存区为空，请先上传文件。", list_db_files(), None

        # 1. Snapshot: 先记下我们要处理哪些文件名
        files_to_process = [f.name for f in UPLOAD_DIR.iterdir() if f.is_file()]

        try:
            # 2. Ingest (Memory Layer)
            await ingestion.process_directory(str(UPLOAD_DIR))

            # 3. Write Ledger (Database Layer)
            for filename in files_to_process:
                db_manager.add_file(filename)

            # 4. Cleanup (Staging Layer)
            # [架构规则] 处理完必须清空，不仅为了节省空间，更为了逻辑闭环
            shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            return f"🎉 成功索引 {len(files_to_process)} 个文件！", None, list_db_files()
        except Exception as e:
            # 失败处理：保留暂存区文件，方便重试
            # 👇 打印堆栈以便调试
            traceback.print_exc()
            return f"❌ 处理失败: {str(e)}", list_staging_files(), list_db_files()

    def clear_staging():
        """[清理暂存区] 手动清空待处理文件"""
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return None, "🗑️ 暂存区已清空。"

    def delete_from_db(selected_files):
        """
        [Dual Deletion] 双重删除操作
        当用户删除文件时，必须同时清理：
        1. Memory (Qdrant): 删除向量数据 (物理删除)。
        2. Ledger (SQLite): 删除元数据记录 (逻辑删除)。
        """
        if not selected_files:
            return "⚠️ 请先在下方列表中勾选要删除的文件。", list_db_files()

        deleted_count = 0
        for file_name in selected_files:
            store_manager.delete_file(file_name)  # Call Memory
            db_manager.remove_file(file_name)  # Call Ledger
            deleted_count += 1

        return f"🗑️ 已删除 {deleted_count} 个文件。", list_db_files()

    # --- UI 布局 ---
    with gr.Blocks(title="Agentic RAG 知识库助手", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🤖 Agentic RAG 知识库助手")

        with gr.Tab("💬 智能对话"):
            gr.ChatInterface(fn=process_query)

        with gr.Tab("📚 知识库管理"):
            with gr.Row():
                # === 左侧：暂存区 (Staging Branch) ===
                with gr.Column(scale=1):
                    gr.Markdown("### 1️⃣ 暂存区 (待处理)")
                    staging_file_output = gr.File(label="待处理文件", file_count="multiple", interactive=True)
                    with gr.Row():
                        upload_btn = gr.Button("📂 确认上传", variant="secondary")
                        clear_staging_btn = gr.Button("🗑️ 清空暂存", variant="stop")
                    ingest_btn = gr.Button("🚀 开始处理 (入库)", variant="primary")

                # === 右侧：已入库 (Ledger Branch) ===
                with gr.Column(scale=1):
                    gr.Markdown("### 2️⃣ 已入库 (数据库)")
                    # 初始 choices 为空，由 load 事件填充
                    db_file_list = gr.CheckboxGroup(label="已索引文档列表", choices=[], interactive=True)
                    with gr.Row():
                        refresh_db_btn = gr.Button("🔄 刷新列表")
                        delete_db_btn = gr.Button("❌ 删除选中", variant="stop")

            log_output = gr.Textbox(label="系统操作日志", interactive=False, lines=3)

            # --- 事件绑定 ---

            # 页面加载时：分别从磁盘和SQLite加载数据
            demo.load(fn=list_staging_files, outputs=staging_file_output)
            # list_db_files 返回的是 CheckboxGroup 对象，会自动更新 db_file_list
            demo.load(fn=list_db_files, outputs=db_file_list)

            upload_btn.click(fn=handle_upload, inputs=staging_file_output, outputs=[staging_file_output, log_output])
            clear_staging_btn.click(fn=clear_staging, inputs=None, outputs=[staging_file_output, log_output])

            # 入库操作：完成后更新日志、清空暂存区显示、刷新右侧数据库列表
            # 👇 注意：这里定义了 3 个 outputs，所以 fn 必须返回 3 个值
            ingest_btn.click(fn=start_ingestion, inputs=None, outputs=[log_output, staging_file_output, db_file_list])

            refresh_db_btn.click(fn=list_db_files, inputs=None, outputs=db_file_list)
            delete_db_btn.click(fn=delete_from_db, inputs=db_file_list, outputs=[log_output, db_file_list])

    return demo