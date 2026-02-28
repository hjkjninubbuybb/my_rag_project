-- MySQL Schema Migration: 添加多模态支持
-- 执行方式: mysql -u rag_user -p rag_db < scripts/migrate_multimodal_schema.sql

-- 扩展 parent_nodes 表，支持多模态节点
ALTER TABLE parent_nodes
ADD COLUMN IF NOT EXISTS collection_type VARCHAR(50) DEFAULT 'text' COMMENT 'text | multimodal' AFTER collection_name;

ALTER TABLE parent_nodes
ADD COLUMN IF NOT EXISTS node_format VARCHAR(20) DEFAULT 'text' COMMENT 'text | image | mixed' AFTER collection_type;

-- Phase 2: 添加图片类型和摘要字段（用于多向量检索架构）
ALTER TABLE parent_nodes
ADD COLUMN IF NOT EXISTS image_type VARCHAR(50) COMMENT 'screenshot | flowchart | table | diagram | other' AFTER node_format;

ALTER TABLE parent_nodes
ADD COLUMN IF NOT EXISTS summary TEXT COMMENT 'VLM 生成的图像摘要（备份）' AFTER image_type;

-- 为多模态查询优化索引
CREATE INDEX IF NOT EXISTS idx_collection_type ON parent_nodes(collection_name, collection_type);
CREATE INDEX IF NOT EXISTS idx_node_format ON parent_nodes(collection_name, node_format);
CREATE INDEX IF NOT EXISTS idx_image_type ON parent_nodes(collection_name, image_type);

-- 验证迁移
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'rag_db'
  AND TABLE_NAME = 'parent_nodes'
  AND COLUMN_NAME IN ('collection_type', 'node_format', 'image_type', 'summary');
