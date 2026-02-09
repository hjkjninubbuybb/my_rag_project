import os
import sys
from dotenv import load_dotenv
from llama_index.embeddings.dashscope import DashScopeEmbedding

# 0. 设置: 加载环境变量
print("🔍 [诊断开始] 正在加载环境配置...")
load_dotenv()


def check_embedding():
    """
    专门诊断 Embedding 服务
    """
    print("-" * 50)
    print("🧪 正在测试模块: Embedding (文本向量化)")

    # 1. 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ [严重错误] 未找到 DASHSCOPE_API_KEY！")
        print("   -> 请检查项目根目录下的 .env 文件")
        return False

    print(f"✅ API Key 格式检查通过: {api_key[:6]}******")

    # 2. 检查网络代理 (解决 localhost/VPN 问题)
    proxy_setting = os.getenv("no_proxy") or os.getenv("NO_PROXY")
    print(f"ℹ️  当前 no_proxy 设置: {proxy_setting}")

    # 3. 核心测试: 调用阿里云
    model_name = "text-embedding-v1"
    print(f"📡 正在发起 API 请求...")
    print(f"   -> 模型: {model_name}")
    print(f"   -> 测试文本: 'Hello Agentic RAG'")

    try:
        # 初始化 LlamaIndex 的 DashScope 组件
        embed_model = DashScopeEmbedding(
            model_name=model_name,
            api_key=api_key
        )

        # 尝试获取向量
        embeddings = embed_model.get_text_embedding("Hello Agentic RAG")

        # 4. 验证结果
        if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
            print(f"✅ [测试通过] Embedding 服务工作正常！")
            print(f"📊 向量维度: {len(embeddings)} 维")
            print(f"👍 结论: 你的网络通畅，Key 有权限，模型名称正确。")
            return True
        else:
            print(f"❌ [测试失败] API 返回了空数据或格式错误。")
            print(f"   -> 返回值: {embeddings}")
            return False

    except Exception as e:
        print(f"\n❌ [异常捕获] 调用过程中发生错误:")
        print(f"   -> 错误类型: {type(e).__name__}")
        print(f"   -> 错误信息: {e}")

        # 智能建议
        err_str = str(e).lower()
        if "401" in err_str or "invalidapikey" in err_str:
            print("💡 建议: API Key 过期或错误。")
        elif "400" in err_str or "invalidparameter" in err_str:
            print("💡 建议: 请去阿里云百炼控制台检查是否开通了 'text-embedding-v1' 模型。")
        elif "connection" in err_str or "timeout" in err_str:
            print("💡 建议: 网络连接超时。请检查 VPN/代理设置 (尝试在 .env 配置 HTTP_PROXY)。")

        return False


if __name__ == "__main__":
    success = check_embedding()
    if not success:
        sys.exit(1)