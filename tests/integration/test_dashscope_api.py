import os
import pytest
from llama_index.embeddings.dashscope import DashScopeEmbedding


# 这是一个 Pytest 的 Fixture，用于在测试前准备数据
@pytest.fixture
def api_key():
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        pytest.skip("跳过测试: 未找到 DASHSCOPE_API_KEY")
    return key


@pytest.mark.integration
def test_embedding_connection(api_key):
    """
    集成测试: 验证能否成功连接阿里云 Embedding 接口并返回向量
    """
    # Arrange
    model_name = "text-embedding-v1"
    embed_model = DashScopeEmbedding(model_name=model_name, api_key=api_key)
    test_text = "Software Engineering"

    # Act
    result = embed_model.get_text_embedding(test_text)

    # Assert
    assert result is not None, "API 返回了 None"
    assert isinstance(result, list), "返回类型应该是 List"
    assert len(result) > 0, "返回的向量列表为空"
    assert isinstance(result[0], float), "向量内部元素应该是 float 类型"

    print(f"\n✅ 集成测试通过: 成功生成 {len(result)} 维向量")