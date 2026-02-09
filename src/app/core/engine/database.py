import sqlite3
import os
from datetime import datetime

class DatabaseManager:
    """
    负责管理文件的元数据 (SQLite)
    """
    DB_NAME = "metadata.db"

    def __init__(self):
        # 自动初始化数据库表
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.DB_NAME)

    def _init_db(self):
        """如果表不存在，则创建"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS indexed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_file(self, filename: str):
        """[记账] 添加一个已索引的文件"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO indexed_files (filename) VALUES (?)",
                    (filename,)
                )
                conn.commit()
                print(f"📝 [SQLite] 已记录文件: {filename}")
        except Exception as e:
            print(f"❌ [SQLite] 添加失败: {e}")

    def remove_file(self, filename: str):
        """[销账] 删除文件记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM indexed_files WHERE filename = ?",
                    (filename,)
                )
                conn.commit()
                print(f"🗑️ [SQLite] 已移除记录: {filename}")
        except Exception as e:
            print(f"❌ [SQLite] 删除失败: {e}")

    def get_all_files(self) -> list[str]:
        """[查账] 获取所有已索引的文件名"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT filename FROM indexed_files ORDER BY indexed_at DESC")
                rows = cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            print(f"❌ [SQLite] 查询失败: {e}")
            return []