"""
文件元数据管理器 (SQLite)。

接收 db_path 和 collection_name 参数，不再依赖全局 settings 单例。
"""

import sqlite3


class DatabaseManager:
    """文件元数据管理器 — 依赖注入版本。"""

    def __init__(self, db_path: str = "data/metadata.db", collection_name: str = "default"):
        self.db_path = db_path
        self.collection_name = collection_name
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """初始化数据库，包含 Schema 完整性检查。"""
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

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT collection_name FROM indexed_files LIMIT 1")
        except sqlite3.OperationalError:
            error_msg = (
                f"\n[Fatal Error] 数据库结构不匹配！\n"
                f"检测到旧版 '{self.db_path}'，缺少 'collection_name' 字段。\n"
                f"请手动删除 '{self.db_path}' 文件，然后重试。\n"
            )
            print(error_msg)
            raise SystemExit(error_msg)

    def add_file(self, filename: str):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO indexed_files (filename, collection_name) VALUES (?, ?)",
                    (filename, self.collection_name),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    print(f"[SQLite] 已记录: {filename} @ {self.collection_name}")
        except Exception as e:
            print(f"[SQLite] 添加失败: {e}")

    def remove_file(self, filename: str):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM indexed_files WHERE filename = ? AND collection_name = ?",
                    (filename, self.collection_name),
                )
                conn.commit()
                print(f"[SQLite] 已移除记录: {filename} @ {self.collection_name}")
        except Exception as e:
            print(f"[SQLite] 删除失败: {e}")

    def get_all_files(self) -> list[str]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT filename FROM indexed_files WHERE collection_name = ? ORDER BY indexed_at DESC",
                    (self.collection_name,),
                )
                rows = cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            print(f"[SQLite] 查询失败: {e}")
            return []
