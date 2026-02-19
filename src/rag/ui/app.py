"""
Gradio UI — 全新 All-in-One 现代化中控台 (100% 完整版)。

集成三大核心工作区：
1. 🗄️ 知识库管线 (基础资产管理: 增删改查)
2. 🔬 消融实验大盘 (策略生成 -> 批量入库 -> 批量评测 -> 可视化)
3. 🤖 Agent 调试舱 (动态对话与内部状态白盒透视)
"""

import asyncio
import json
import shutil
import traceback
from pathlib import Path
from typing import List

import gradio as gr
import pandas as pd
from langchain_core.messages import HumanMessage, BaseMessage

from rag.config.experiment import ExperimentConfig, ExperimentGrid
from rag.config.settings import settings
from rag.pipeline.ingestion import IngestionService
from rag.storage.vectordb import VectorStoreManager
from rag.storage.metadata import DatabaseManager
from rag.agent.workflow import create_graph
from rag.experiment.runner import BatchExperimentRunner
from rag.experiment.results import ResultsCollector

# 暂存区路径
UPLOAD_DIR = Path("data/uploads/temp_batch")

def _get_default_config() -> ExperimentConfig:
    return settings.to_experiment_config()

def _get_kb_config(collection_name: str) -> ExperimentConfig:
    """根据 collection 名称构建一个动态的 ExperimentConfig。"""
    cfg = _get_default_config()
    # 绕过 dataclass 的 frozen 限制创建新实例
    return ExperimentConfig(
        **{**cfg.to_full_dict(), "collection_name_override": collection_name}
    )

def _get_managers(collection_name: str):
    """获取指定 Collection 的向量库和关系型数据库管理器。"""
    cfg = _get_kb_config(collection_name)
    store = VectorStoreManager(cfg)
    # 处理 SQLite 路径
    db_path_str = cfg.qdrant_path.replace("vectordb", "metadata.db").replace("data/data/", "data/")
    db = DatabaseManager(db_path=db_path_str, collection_name=collection_name)
    return cfg, store, db


def _sanitize_state_for_json(state: dict) -> dict:
    """将 LangGraph State 转换为 JSON 可序列化的字典。

    messages 中的 BaseMessage 对象无法直接序列化，需要提取 role + content。
    """
    safe = {}
    for key, value in state.items():
        if key == "messages":
            safe[key] = [
                {
                    "role": type(m).__name__,
                    "content": str(m.content)[:500] if hasattr(m, "content") else str(m)[:500],
                }
                for m in value
            ]
        else:
            try:
                json.dumps(value)
                safe[key] = value
            except (TypeError, ValueError):
                safe[key] = str(value)
    return safe

def _extract_content(chunk) -> str:
    """从 AIMessageChunk 提取文本 content（兼容 str 和 list 两种格式）。"""
    if chunk is None:
        return ""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def _build_chunks_df(chunks_data: list) -> pd.DataFrame:
    """将 debug_retrieved_chunks 转为 DataFrame，按 score 降序排列。"""
    if not chunks_data:
        return pd.DataFrame(columns=["score", "source_file", "text"])
    df = pd.DataFrame(chunks_data)
    if {"score", "source_file", "text"}.issubset(df.columns):
        return df.sort_values("score", ascending=False)[["score", "source_file", "text"]]
    return pd.DataFrame(columns=["score", "source_file", "text"])


def format_citations(chunks: list) -> str:
    """将检索块列表格式化为 Markdown 引用来源段落。同一文件保留最高分的块。"""
    if not chunks:
        return ""
    seen: dict = {}
    for chunk in chunks:
        fname = chunk.get("source_file", "未知文件")
        score = float(chunk.get("score", 0.0))
        if fname not in seen or score > seen[fname]["score"]:
            seen[fname] = {"score": score, "text": chunk.get("text", "")}

    lines = ["\n\n---\n**参考来源**\n"]
    for i, (fname, info) in enumerate(seen.items(), 1):
        excerpt = info["text"][:150].replace("\n", " ").strip()
        lines.append(f"{i}. 📄 **{fname}** (相关度: {info['score']:.3f})")
        lines.append(f"   > {excerpt}…")
    return "\n".join(lines)


def create_ui():
    # 运行时全局状态
    current_config: List[ExperimentConfig] = []
    results_collector = ResultsCollector()

    # 预加载 configs/ 目录下的命名配置文件 (best_retrieval.yaml 等)
    _preset_dir = Path("configs")
    _preset_files = ["best_retrieval.yaml"]
    for _fname in _preset_files:
        _fpath = _preset_dir / _fname
        if _fpath.exists():
            try:
                _cfg = ExperimentConfig.from_yaml(str(_fpath), api_key=settings.dashscope_api_key or "")
                current_config.append(_cfg)
                print(f"✅ [UI] 预设配置已加载: {_cfg.experiment_id}")
            except Exception as _e:
                print(f"⚠️ [UI] 预设配置加载失败 ({_fname}): {_e}")

    _initial_dropdown_choices = ["default"] + [c.experiment_id for c in current_config]

    with gr.Blocks(title="Agentic RAG 中控台", theme=gr.themes.Soft(), fill_width=True) as demo:

        with gr.Row():
            # ==========================================
            # ⬅️ 左侧：全局侧边栏 (Global Sidebar)
            # ==========================================
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### ⚙️ 全局控制面板")

                global_config_selector = gr.Dropdown(
                    choices=_initial_dropdown_choices,
                    value="default",
                    label="🟢 当前激活的实验配置 (Agent 使用)",
                    interactive=True
                )

                gr.Markdown("---")
                gr.Markdown("#### 🗃️ 知识库全局状态")
                kb_collection_name = gr.Textbox(
                    value=settings.collection_name,
                    label="主控 Collection 名称",
                    interactive=False
                )
                kb_status_md = gr.Markdown("**暂存区文件:** 0 个\n**需前往右侧 [知识库管线] 刷新详细数据**")

                gr.Markdown("---")
                global_log = gr.Textbox(label="系统实时日志", lines=15, interactive=False, text_align="left")

            # ==========================================
            # ➡️ 右侧：核心工作区 (Main Workspaces)
            # ==========================================
            with gr.Column(scale=4):
                with gr.Tabs():

                    # ---------------- 工作区 1：知识库管线 (日常资产管理) ----------------
                    with gr.Tab("🗄️ 知识库管线", id="tab_kb"):
                        gr.Markdown("### 基础知识库管理 (增删改查)")
                        gr.Markdown("此处用于管理主集合（Default Collection）的文档资产。实验集合的数据在[消融大盘]中自动生成。")

                        with gr.Row():
                            with gr.Column(scale=1):
                                gr.Markdown("#### 1. 待处理暂存区")
                                staging_files = gr.File(label="拖拽 PDF/MD 到此处", file_count="multiple")
                                with gr.Row():
                                    upload_btn = gr.Button("上传至暂存区", variant="secondary")
                                    clear_staging_btn = gr.Button("清空暂存区", variant="stop")
                                run_single_ingest_btn = gr.Button("🚀 处理暂存区 (单库入库)", variant="primary")

                            with gr.Column(scale=1):
                                gr.Markdown("#### 2. 已入库资产 (Qdrant & SQLite)")
                                db_file_list = gr.CheckboxGroup(label="已索引文档列表", choices=[], interactive=True)
                                with gr.Row():
                                    refresh_db_btn = gr.Button("🔄 刷新列表")
                                    delete_db_btn = gr.Button("🗑️ 删除选中", variant="stop")

                        kb_action_log = gr.Textbox(label="资产操作日志", lines=3, interactive=False)

                    # ---------------- 工作区 2：消融实验大盘 (核心评测) ----------------
                    with gr.Tab("🔬 消融实验大盘", id="tab_eval"):
                        gr.Markdown("### 策略矩阵生成与批量基准测试")

                        with gr.Row():
                            with gr.Column(scale=1):
                                gr.Markdown("#### 1. 生成实验矩阵")
                                chunk_strategies = gr.CheckboxGroup(choices=["fixed", "recursive", "sentence"], value=["fixed", "recursive"], label="切片策略")
                                chunk_sizes = gr.CheckboxGroup(choices=["128", "256", "512"], value=["256"], label="Chunk Size")
                                chunk_overlaps = gr.CheckboxGroup(choices=["25", "50"], value=["50"], label="Overlap")
                                hybrid_opts = gr.CheckboxGroup(choices=["True", "False"], value=["True", "False"], label="Hybrid Search")
                                merge_opts = gr.CheckboxGroup(choices=["True", "False"], value=["True", "False"], label="Auto Merge")
                                rerank_opts = gr.CheckboxGroup(choices=["True", "False"], value=["True", "False"], label="Rerank")
                                generate_grid_btn = gr.Button("生成实验矩阵 ⬇️")
                                config_preview = gr.Dataframe(label="执行队列预览", interactive=False, max_height=200)

                            with gr.Column(scale=2):
                                gr.Markdown("#### 2. 执行批量管线")
                                with gr.Row():
                                    run_batch_ingest_btn = gr.Button("📦 1. 智能入库 (按矩阵构建多库)", variant="secondary")
                                    run_batch_eval_btn = gr.Button("▶️ 2. 运行评测", variant="primary")

                                with gr.Row():
                                    dataset_path = gr.Textbox(value="tests/data/test_dataset.csv", label="评测集路径", scale=2)
                                    dataset_limit = gr.Slider(minimum=0, maximum=100, step=1, value=10, label="最大测试条数(0=全量)", scale=1)

                                gr.Markdown("#### 3. 实验洞察")
                                refresh_plot_btn = gr.Button("🔄 刷新可视化图表")
                                eval_plot = gr.ScatterPlot(
                                    x="avg_latency_ms", y="hit_rate", color="experiment_id",
                                    title="性能 vs 质量散点图 (帕累托分布)",
                                    tooltip=["experiment_id", "hit_rate", "ndcg", "avg_latency_ms"],
                                    width=600, height=300
                                )
                                eval_table = gr.Dataframe(label="核心指标对比榜单", interactive=False)

                    # ---------------- 工作区 3：Agent 调试舱 (白盒测试) ----------------
                    with gr.Tab("🤖 Agent 调试舱", id="tab_agent"):
                        gr.Markdown("### 深度白盒透视与交互诊断")

                        with gr.Row():
                            with gr.Column(scale=5):
                                chatbot = gr.Chatbot(label="Agent 会话窗口", height=500, avatar_images=(None, "🤖"))
                                with gr.Row():
                                    msg_input = gr.Textbox(label="输入问题", placeholder="询问关于知识库的内容，按 Enter 发送...", scale=4)
                                    send_btn = gr.Button("发送", variant="primary", scale=1)
                                clear_chat_btn = gr.Button("清空上下文", size="sm")

                            with gr.Column(scale=4):
                                gr.Markdown("#### 🔍 内部链路追踪 (Tracing)")

                                with gr.Accordion("1. 意图改写 (Query Rewrite)", open=True):
                                    debug_rewrites = gr.JSON(label="解析出的检索词 (rewrittenQuestions)")

                                with gr.Accordion("2. 物理召回探针 (Retrieved Chunks)", open=True):
                                    debug_chunks = gr.Dataframe(
                                        label="底层引擎实际召回分块 (按 Score 降序)",
                                        headers=["score", "source_file", "text"],
                                        wrap=True
                                    )

                                with gr.Accordion("3. LangGraph 完整状态", open=False):
                                    debug_full_state = gr.JSON(label="State 字典快照")

        # ==========================================
        # 逻辑绑定 (Event Handlers)
        # ==========================================

        # --- 通用功能 ---
        def _update_staging_files():
            if not UPLOAD_DIR.exists(): return None
            files = [str(f) for f in UPLOAD_DIR.iterdir() if f.is_file()]
            return files if files else None

        # --- 工作区 1：知识库管线 ---
        def list_db_files(collection_name):
            try:
                _, _, db = _get_managers(collection_name)
                files = db.get_all_files()
                return gr.update(choices=files, label=f"已索引文档列表 ({len(files)})")
            except Exception:
                return gr.update(choices=[], label="无法加载列表")

        def handle_upload(files):
            if not files: return None, "请先选择文件"
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            saved = []
            for file in files:
                target = UPLOAD_DIR / Path(file.name).name
                shutil.copy(file.name, target)
                saved.append(str(target))
            return saved, f"成功上传 {len(saved)} 个文件到暂存区。"

        def clear_staging():
            if UPLOAD_DIR.exists():
                shutil.rmtree(UPLOAD_DIR)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            return None, "暂存区已清空。"

        async def start_single_ingestion(collection_name):
            if not UPLOAD_DIR.exists() or not any(UPLOAD_DIR.iterdir()):
                return "暂存区为空，无需入库。", list_db_files(collection_name)

            cfg, store, db = _get_managers(collection_name)
            files_to_process = [f.name for f in UPLOAD_DIR.iterdir() if f.is_file()]

            try:
                ingestion = IngestionService(cfg)
                await ingestion.process_directory(str(UPLOAD_DIR))

                # 更新元数据 SQLite
                for filename in files_to_process:
                    db.add_file(filename)

                # 清理暂存区
                shutil.rmtree(UPLOAD_DIR)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

                return f"✅ 成功索引 {len(files_to_process)} 个文件到 {collection_name}。", list_db_files(collection_name)
            except Exception as e:
                traceback.print_exc()
                return f"❌ 处理失败: {e}", list_db_files(collection_name)

        def delete_from_db(selected_files, collection_name):
            if not selected_files: return "请先勾选要删除的文件", list_db_files(collection_name)
            cfg, store, db = _get_managers(collection_name)
            for fname in selected_files:
                store.delete_file(fname)
                db.remove_file(fname)
            return f"🗑️ 已成功删除 {len(selected_files)} 个文件。", list_db_files(collection_name)

        # 绑定 Tab 1 事件
        demo.load(fn=_update_staging_files, outputs=staging_files)
        demo.load(fn=list_db_files, inputs=[kb_collection_name], outputs=[db_file_list])

        upload_btn.click(fn=handle_upload, inputs=staging_files, outputs=[staging_files, kb_action_log])
        clear_staging_btn.click(fn=clear_staging, outputs=[staging_files, kb_action_log])
        refresh_db_btn.click(fn=list_db_files, inputs=[kb_collection_name], outputs=[db_file_list])
        delete_db_btn.click(fn=delete_from_db, inputs=[db_file_list, kb_collection_name], outputs=[kb_action_log, db_file_list])
        run_single_ingest_btn.click(fn=start_single_ingestion, inputs=[kb_collection_name], outputs=[kb_action_log, db_file_list]).then(fn=_update_staging_files, outputs=staging_files)


        # --- 工作区 2：消融实验大盘 ---
        def generate_matrix(strats, sizes, overlaps, hybrid, merge, rerank):
            if not all([strats, sizes, overlaps, hybrid, merge, rerank]):
                return pd.DataFrame(), gr.update(), "请确保每个维度至少选择一个选项。"

            grid = ExperimentGrid(
                chunking_strategies=strats,
                chunk_sizes_child=[int(s) for s in sizes],
                chunk_overlaps=[int(o) for o in overlaps],
                enable_hybrid=[v == "True" for v in hybrid],
                enable_auto_merge=[v == "True" for v in merge],
                enable_rerank=[v == "True" for v in rerank],
            )
            configs = grid.generate_configs(api_key=settings.dashscope_api_key or "")
            # 保留 presets，仅替换消融实验配置 (ID 以 "ablation_" 开头)
            current_config[:] = [c for c in current_config if not c.experiment_id.startswith("ablation_")]
            current_config.extend(configs)

            dropdown_choices = ["default"] + [c.experiment_id for c in current_config]
            rows = [{
                "ID": c.experiment_id,
                "策略": c.chunking_strategy,
                "Size": c.chunk_size_child,
                "Hybrid": c.enable_hybrid,
                "Merge": c.enable_auto_merge,
                "Rerank": c.enable_rerank,
            } for c in configs]

            return (
                pd.DataFrame(rows),
                gr.update(choices=dropdown_choices, value=dropdown_choices[1] if len(dropdown_choices) > 1 else "default"),
                f"生成了 {len(configs)} 组实验配置。",
            )

        generate_grid_btn.click(fn=generate_matrix, inputs=[chunk_strategies, chunk_sizes, chunk_overlaps, hybrid_opts, merge_opts, rerank_opts], outputs=[config_preview, global_config_selector, global_log])

        async def run_batch_ingestion():
            if not current_config:
                return "请先在左侧生成配置矩阵。"
            if not UPLOAD_DIR.exists() or not any(UPLOAD_DIR.iterdir()):
                return "暂存区为空，请先在 [知识库管线] 上传文档。"
            logs = ["开始执行批量实验入库..."]
            runner = BatchExperimentRunner(
                configs=current_config,
                dataset_path="",
                input_dir=str(UPLOAD_DIR),
                progress_callback=lambda m: logs.append(m),
            )
            try:
                await runner.run_ingestion()
                logs.append("批量入库完毕。")
            except Exception as e:
                traceback.print_exc()
                logs.append(f"入库出错: {e}")
            return "\n".join(logs)

        run_batch_ingest_btn.click(fn=run_batch_ingestion, outputs=[global_log])

        def run_batch_eval(ds_path, limit):
            if not current_config:
                return "配置队列为空，请先生成矩阵。", pd.DataFrame(), pd.DataFrame()
            logs = ["开始批量评测..."]
            runner = BatchExperimentRunner(
                configs=current_config,
                dataset_path=ds_path,
                input_dir="",
                progress_callback=lambda m: logs.append(m),
            )
            try:
                summaries, details = runner.run_evaluation(limit=int(limit) if limit > 0 else None)
                if summaries:
                    results_collector.save_batch(summaries, details, tag="ablation")
            except Exception as e:
                traceback.print_exc()
                logs.append(f"评测出错: {e}")

            df = results_collector.get_comparison_dataframe()
            if df.empty:
                return "\n".join(logs) + "\n评测完成，但未产生有效数据。", pd.DataFrame(), pd.DataFrame()
            logs.append("评测报告生成完毕。")
            return "\n".join(logs), df, df

        run_batch_eval_btn.click(fn=run_batch_eval, inputs=[dataset_path, dataset_limit], outputs=[global_log, eval_plot, eval_table])
        refresh_plot_btn.click(fn=lambda: (results_collector.get_comparison_dataframe(), results_collector.get_comparison_dataframe()), outputs=[eval_plot, eval_table])


        # --- 工作区 3：Agent 调试舱 ---
        chat_state = {"graph": None, "config_id": None}

        _empty_chunks_df = pd.DataFrame(columns=["score", "source_file", "text"])

        async def process_chat(user_msg, chat_history, config_id):
            """流式聊天处理器 (async generator)。每次 yield 驱动 Gradio 实时更新。"""
            if not user_msg:
                yield chat_history, "", [], _empty_chunks_df, {}
                return

            # 1. 挂载 LangGraph（缓存复用，避免重复初始化）
            if chat_state["config_id"] != config_id or chat_state["graph"] is None:
                cfg = next((c for c in current_config if c.experiment_id == config_id), _get_default_config())
                chat_state["graph"] = create_graph(cfg)
                chat_state["config_id"] = config_id

            graph = chat_state["graph"]
            inputs = {"messages": [HumanMessage(content=user_msg)]}
            lc_config = {"configurable": {"thread_id": "debugger_1"}, "recursion_limit": 25}

            current_text = ""
            agent_buffer = ""
            aggregate_started = False

            # 2. 即时反馈：清空输入框，显示光标指示符
            yield chat_history + [[user_msg, "▌"]], "", [], _empty_chunks_df, {}

            try:
                # 3. 流式执行 LangGraph
                async for event in graph.astream_events(inputs, config=lc_config, version="v2"):
                    kind = event.get("event", "")
                    node = event.get("metadata", {}).get("langgraph_node", "")
                    data = event.get("data", {})

                    if kind == "on_chat_model_stream":
                        content = _extract_content(data.get("chunk"))

                        if node == "aggregate" and content:
                            # 多问题路径：追加聚合 LLM 的每个 token
                            current_text += content
                            yield chat_history + [[user_msg, current_text + "▌"]], "", [], _empty_chunks_df, {}

                        elif node == "agent" and content and not aggregate_started:
                            # 单问题路径：Agent 最终文本回复（工具调用轮次 content 为空，自然过滤）
                            agent_buffer += content
                            current_text = agent_buffer
                            yield chat_history + [[user_msg, current_text + "▌"]], "", [], _empty_chunks_df, {}

                    elif kind == "on_chat_model_start":
                        if node == "agent":
                            # ReAct 新轮次开始，重置 agent 候选缓冲
                            agent_buffer = ""
                        elif node == "aggregate":
                            # 确认为多问题路径：在聚合 LLM 启动时立即清空被各子 Agent 污染的中间输出
                            aggregate_started = True
                            current_text = ""

                # 4. 流结束：从 MemorySaver checkpointer 拉取完整最终状态
                final_snapshot = await graph.aget_state(lc_config)
                state_values = final_snapshot.values

                debug_chunks = state_values.get("debug_retrieved_chunks", [])
                rewrites = state_values.get("rewrittenQuestions", ["(未触发意图改写)"])

                # 5. 格式化引用来源并追加到答案末尾
                # 安全兜底：若流式未捕获到任何 token，从 State 消息列表中提取最终答案
                if not current_text:
                    messages = state_values.get("messages", [])
                    if messages:
                        current_text = getattr(messages[-1], "content", "") or ""

                citations = format_citations(debug_chunks)
                final_text = current_text + citations if citations else current_text

                new_history = chat_history + [[user_msg, final_text]]
                yield new_history, "", rewrites, _build_chunks_df(debug_chunks), _sanitize_state_for_json(state_values)

            except Exception as e:
                traceback.print_exc()
                yield chat_history + [[user_msg, f"处理出错: {e}"]], "", [], _empty_chunks_df, {"error": str(e)}

        # 绑定对话事件
        for trigger in [msg_input.submit, send_btn.click]:
            trigger(
                fn=process_chat,
                inputs=[msg_input, chatbot, global_config_selector],
                outputs=[chatbot, msg_input, debug_rewrites, debug_chunks, debug_full_state]
            )

        def _clear_chat():
            chat_state["graph"] = None
            chat_state["config_id"] = None
            return [], "", [], pd.DataFrame(columns=["score", "source_file", "text"]), {}

        clear_chat_btn.click(fn=_clear_chat, outputs=[chatbot, msg_input, debug_rewrites, debug_chunks, debug_full_state])

    return demo

if __name__ == "__main__":
    app = create_ui()
    app.launch(server_name="127.0.0.1", server_port=7860)