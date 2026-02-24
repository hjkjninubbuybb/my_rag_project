"""
清洗模块测试脚本 - 处理实际文件
测试 services/ingestion/app/parsing/cleaner.py 中的 PolicyCleaner
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.parsing.cleaner import PolicyCleaner


def main():
    # 输入目录: policy raw markdown 文件
    input_dir = Path(__file__).parent.parent.parent / "data" / "parsed" / "policy" / "raw"

    # 输出目录: 测试结果
    output_dir = Path(__file__).parent.parent / "datas" / "cleaner_test_results" / "policy"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        return

    # 获取所有 markdown 文件
    md_files = list(input_dir.glob("*.md"))
    if not md_files:
        return

    cleaner = PolicyCleaner()

    for md_file in md_files:
        # 读取原始内容
        with open(md_file, "r", encoding="utf-8") as f:
            original_text = f.read()

        # 清洗
        cleaned_text = cleaner.clean(original_text, md_file.name)

        # 保存清洗后的文件
        output_file = output_dir / f"{md_file.stem}_cleaned.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(cleaned_text)


if __name__ == "__main__":
    main()
