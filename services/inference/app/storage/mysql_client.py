"""MySQL 客户端（用于查询父节点）。

在多模态架构中，父节点存储在 MySQL，包含原始图片数据。
Inference 服务通过此客户端批量查询父节点，用于 VLM 生成。
"""

import json
from typing import List, Dict, Any, Optional
import mysql.connector
from mysql.connector import Error

from rag_shared.utils.logger import get_logger

logger = get_logger(__name__)


class MySQLClient:
    """MySQL 客户端，用于查询父节点。"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "rag_user",
        password: str = "rag_password",
        database: str = "rag_db"
    ):
        """初始化 MySQL 客户端。

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 用户名
            password: 密码
            database: 数据库名
        """
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }
        self.connection = None
        logger.info(f"MySQL 客户端初始化: {host}:{port}/{database}")

    def connect(self):
        """建立数据库连接。"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            if self.connection.is_connected():
                logger.info("MySQL 连接成功")
        except Error as e:
            logger.error(f"MySQL 连接失败: {e}")
            raise

    def close(self):
        """关闭数据库连接。"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("MySQL 连接已关闭")

    def get_nodes_by_ids(
        self,
        node_ids: List[str],
        collection_name: str
    ) -> List[Dict[str, Any]]:
        """批量查询父节点。

        Args:
            node_ids: 节点 ID 列表
            collection_name: 集合名称

        Returns:
            父节点列表，每个节点包含：
            {
                "node_id": str,
                "text": str,
                "metadata": dict,  # 包含 images 字段（base64 编码的图片）
                "collection_name": str,
                "node_type": str,
                "node_format": str
            }
        """
        if not node_ids:
            return []

        if not self.connection or not self.connection.is_connected():
            self.connect()

        try:
            cursor = self.connection.cursor(dictionary=True)

            # 构建 IN 查询
            placeholders = ",".join(["%s"] * len(node_ids))
            query = f"""
                SELECT
                    node_id,
                    text,
                    metadata,
                    collection_name,
                    node_type,
                    node_format,
                    image_type,
                    summary
                FROM parent_nodes
                WHERE collection_name = %s
                  AND node_id IN ({placeholders})
            """

            params = [collection_name] + node_ids
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 解析 metadata（JSON 字符串 → dict）
            nodes = []
            for row in rows:
                if row["metadata"]:
                    try:
                        row["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        logger.warning(
                            f"节点 {row['node_id']} 的 metadata 解析失败，使用空字典"
                        )
                        row["metadata"] = {}
                else:
                    row["metadata"] = {}

                nodes.append(row)

            cursor.close()

            logger.debug(
                f"批量查询父节点成功: {len(nodes)}/{len(node_ids)} 个节点"
            )

            return nodes

        except Error as e:
            logger.error(f"批量查询父节点失败: {e}")
            raise

    def get_node_by_id(
        self,
        node_id: str,
        collection_name: str
    ) -> Optional[Dict[str, Any]]:
        """查询单个父节点。

        Args:
            node_id: 节点 ID
            collection_name: 集合名称

        Returns:
            父节点字典，如果不存在则返回 None
        """
        nodes = self.get_nodes_by_ids([node_id], collection_name)
        return nodes[0] if nodes else None

    def __enter__(self):
        """上下文管理器：进入。"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：退出。"""
        self.close()
