-- ══════════════════════════════════════════════════════════════
-- RAG System Database Schema
-- Version: v3.0 (Microservices Architecture)
-- ══════════════════════════════════════════════════════════════

-- 父节点表 - 存储完整图片 + 上下文文本（多模态）
CREATE TABLE IF NOT EXISTS parent_nodes (
    id VARCHAR(255) PRIMARY KEY COMMENT '父节点 UUID',
    collection_name VARCHAR(255) NOT NULL COMMENT 'Qdrant collection 名称',
    file_name VARCHAR(255) NOT NULL COMMENT '源文件名',
    text LONGTEXT NOT NULL COMMENT '上下文文本 + base64 图片',
    metadata JSON COMMENT '元数据 (user_role, page, images, image_type)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_collection (collection_name),
    INDEX idx_file (file_name),
    INDEX idx_collection_file (collection_name, file_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='多模态父节点存储表';

-- Collection 元数据表
CREATE TABLE IF NOT EXISTS collections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE COMMENT 'Collection 名称（唯一）',
    description TEXT COMMENT 'Collection 描述',
    config JSON COMMENT '入库配置 (chunking_strategy, embedding_model, etc.)',
    document_count INT DEFAULT 0 COMMENT '文档数量',
    node_count INT DEFAULT 0 COMMENT '节点数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Collection 元数据表';

-- 文档元数据表
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(255) NOT NULL COMMENT 'Collection 名称',
    file_name VARCHAR(255) NOT NULL COMMENT '文件名',
    file_path VARCHAR(512) COMMENT 'MinIO 对象路径 (bucket/key)',
    file_size BIGINT COMMENT '文件大小（字节）',
    file_hash VARCHAR(64) COMMENT '文件 MD5 哈希',
    node_count INT DEFAULT 0 COMMENT '生成的节点数量',
    parent_node_count INT DEFAULT 0 COMMENT '父节点数量（多模态）',
    child_node_count INT DEFAULT 0 COMMENT '子节点数量（多模态）',
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    INDEX idx_collection (collection_name),
    INDEX idx_file (file_name),
    INDEX idx_hash (file_hash),
    INDEX idx_indexed (indexed_at),
    UNIQUE KEY uk_collection_file (collection_name, file_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='文档元数据表';

-- 测试运行记录表
CREATE TABLE IF NOT EXISTS test_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_suite VARCHAR(255) NOT NULL COMMENT '测试套件名称',
    test_name VARCHAR(255) NOT NULL COMMENT '测试名称',
    status ENUM('pending', 'running', 'passed', 'failed', 'skipped') DEFAULT 'pending' COMMENT '测试状态',
    config JSON COMMENT '测试配置',
    result JSON COMMENT '测试结果 (metrics, errors, logs)',
    duration_ms INT COMMENT '执行时长（毫秒）',
    error_message TEXT COMMENT '错误信息',
    started_at TIMESTAMP NULL COMMENT '开始时间',
    finished_at TIMESTAMP NULL COMMENT '结束时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_suite (test_suite),
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='测试运行记录表';

-- 插入初始数据（可选）
INSERT INTO collections (name, description, config) VALUES
('default', 'Default collection for testing', '{"chunking_strategy": "recursive", "chunk_size": 512}')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
