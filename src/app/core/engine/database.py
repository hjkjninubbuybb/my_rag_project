import sqlite3
import os
from app.settings import settings

class DatabaseManager:
    """
    负责管理文件的元数据 (SQLite) - Phase 3 Safety Enhanced
    """
    DB_NAME = "metadata.db"

    def __init__(self):
        self._init_db()

    def _get_connection(self):
        # 🔴 Safety: 允许跨线程访问，防止 Gradio 多线程环境下报错
        return sqlite3.connect(self.DB_NAME, check_same_thread=False)

    def _init_db(self):
        """初始化数据库，包含 Schema 完整性检查"""
        # 1. 建表
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS indexed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(filename, collection_name)
                )
            ''')
            conn.commit()

        # 2. 🔴 Safety Check: 检查表结构是否匹配
        # 防止用户忘记删除旧 DB，导致运行时 crash
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 尝试查询 collection_name 字段
                cursor.execute("SELECT collection_name FROM indexed_files LIMIT 1")
        except sqlite3.OperationalError:
            # 如果报错 "no such column"，说明是旧的数据库文件
            error_msg = (
                "\n❌ [Fatal Error] 数据库结构不匹配！\n"
                "检测到旧版 'metadata.db'，缺少 'collection_name' 字段。\n"
                "👉 请手动删除项目根目录下的 'metadata.db' 文件，然后重试。\n"
            )
            print(error_msg)
            # 强制退出，防止后续产生脏数据
            raise SystemExit(error_msg)

    def add_file(self, filename: str):
        target_collection = settings.collection_name
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO indexed_files (filename, collection_name) VALUES (?, ?)",
                    (filename, target_collection)
                )
                conn.commit()
                # 仅当真正插入（rowcount > 0）时打印，避免 IGNORE 造成的误导
                if cursor.rowcount > 0:
                    print(f"📝 [SQLite] 已记录: {filename} @ {target_collection}")
        except Exception as e:
            print(f"❌ [SQLite] 添加失败: {e}")

    def remove_file(self, filename: str):
        target_collection = settings.collection_name
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM indexed_files WHERE filename = ? AND collection_name = ?",
                    (filename, target_collection)
                )
                conn.commit()
                print(f"🗑️ [SQLite] 已移除记录: {filename} @ {target_collection}")
        except Exception as e:
            print(f"❌ [SQLite] 删除失败: {e}")

    def get_all_files(self) -> list[str]:
        target_collection = settings.collection_name
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT filename FROM indexed_files WHERE collection_name = ? ORDER BY indexed_at DESC",
                    (target_collection,)
                )
                rows = cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            print(f"❌ [SQLite] 查询失败: {e}")
            return []