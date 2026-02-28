"""文档清洗器（合并自 services/mineru-parser）。"""

import re


class PolicyCleaner:
    """政策规范类文档清洗器。"""

    def clean(self, md_text: str, filename: str) -> str:
        # 步骤1: 去除页码和页眉页脚
        text = self._remove_page_numbers(md_text)
        text = self._remove_headers_footers(text)

        # 步骤1.5: 去除目录（TOC）
        text = self._remove_toc(text)

        # 步骤2: 规范化空白（先压缩连续空行）
        text = self._normalize_whitespace(text)

        # 步骤3: 合并段落（核心改进）
        text = self._merge_paragraphs(text)

        return text

    def _remove_toc(self, text: str) -> str:
        """去除目录（Table of Contents）

        检测规则：
        1. 目录标题：#### 目 录 或 ## 目录 或 # 目录
        2. 目录项格式：
           - 数字 标题 ............（数字+空格+标题+省略号+可能空格+页码）
           - 数字. 标题（数字+点+标题）
           - 缩进+数字. 页码
        """
        lines = text.split('\n')
        cleaned_lines = []

        i = 0
        n = len(lines)
        in_toc = False  # 是否在目录区域内

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 检测目录标题
            if re.match(r'^#{1,6}\s*(目\s*录|目录|TOC|Table\s*of\s*Contents)', stripped, re.IGNORECASE):
                in_toc = True
                i += 1
                continue

            if in_toc:
                # 检测目录项结束：遇到非目录项格式
                # 目录项模式：数字+空格+文字+省略号 或 数字+点+数字
                is_toc_item = False

                # 模式1: "1 标题内容 ........." (数字+空格+非空+省略号，可能有页码)
                if re.match(r'^\d+\s+\S+.*\.+\s*\d*$', stripped):
                    is_toc_item = True

                # 模式2: " 12." 或 " 22." (缩进+数字+点)
                if re.match(r'^\s+\d+\.+$', stripped):
                    is_toc_item = True

                # 模式3: "1. 12" 或 "1) 22" (数字+.+空格+数字)
                if re.match(r'^\d+[\.\)]\s*\d+$', stripped):
                    is_toc_item = True

                # 模式4: "2.1 第七学期工作" (数字.数字 章节)
                if re.match(r'^\d+(\.\d+)+\s+', stripped):
                    is_toc_item = True

                # 如果不是目录项，退出目录区域
                if not is_toc_item and stripped:
                    in_toc = False

                # 如果是目录项，跳过
                if in_toc:
                    i += 1
                    continue

            cleaned_lines.append(line)
            i += 1

        return '\n'.join(cleaned_lines)

    def _normalize_whitespace(self, text: str) -> str:
        """压缩3个或更多连续换行为2个"""
        return re.sub(r'\n{3,}', '\n\n', text)

    def _remove_headers_footers(self, text: str) -> str:
        """去除页眉页脚"""
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 10 and stripped.isdigit() or "第" in stripped and "页" in stripped:
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def _remove_page_numbers(self, text: str) -> str:
        """去除页码"""
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^(第\s*\d+\s*页|Page\s*\d+\s*of\s*\d+)$', stripped):
                continue
            if stripped.isdigit() and len(stripped) <= 4:
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def _merge_paragraphs(self, text: str) -> str:
        """合并段落 + 智能空行插入（Chunking 优化）

        核心逻辑：
        - 遇到标题，单独成行 + 标题后添加空行
        - 列表项和普通文本：如果不以句子结束符结尾，继续合并
        - 独立段落之间添加空行（除非是连续列表项）
        - 为 Recursive Text Splitter 提供清晰的 \n\n 分隔符
        """
        lines = text.split('\n')
        merged_lines = []
        buffer = ""
        prev_is_list = False  # 上一行是否为列表项

        for line in lines:
            stripped = line.strip()

            # 空行：跳过
            if not stripped:
                continue

            # 标题行：结束当前段落，添加标题 + 空行
            if stripped.startswith('#'):
                if buffer:
                    merged_lines.append(buffer)
                    # 非列表段落后添加空行
                    if not prev_is_list:
                        merged_lines.append("")
                    buffer = ""
                merged_lines.append(line)
                merged_lines.append("")  # 标题后空行（Chunking 边界）
                prev_is_list = False
                continue

            # 判断当前行是否为列表项
            curr_is_list = self._is_list_item(stripped)

            # 合并或分段
            if buffer:
                if self._ends_with_sentence(buffer):
                    # 上一行句子结束，输出当前 buffer
                    merged_lines.append(buffer)

                    # 判断是否添加空行
                    # 规则：列表项之间不加空行，其他情况加空行
                    if not (prev_is_list and curr_is_list):
                        merged_lines.append("")  # 段落分隔

                    buffer = stripped
                    prev_is_list = curr_is_list
                else:
                    # 上一行未结束，合并到 buffer
                    buffer += stripped
            else:
                buffer = stripped
                prev_is_list = curr_is_list

        # 处理最后的缓冲区
        if buffer:
            merged_lines.append(buffer)

        # 清理尾部多余空行
        while merged_lines and merged_lines[-1] == "":
            merged_lines.pop()

        return '\n'.join(merged_lines)

    def _is_structural_line(self, line: str) -> bool:
        """判断是否为 Markdown 结构行（标题、列表、表格、引用）"""
        return (
            line.startswith('#') or  # 标题
            bool(re.match(r'^\d+[\.\)、]\s*[^0-9]', line)) or  # 有序列表
            line.startswith('- ') or  # 无序列表
            line.startswith('* ') or  # 无序列表
            line.startswith('|') or  # 表格
            line.startswith('>')  # 引用
        )

    def _ends_with_sentence(self, text: str) -> bool:
        """判断文本是否以句子结束符结尾（中英文）"""
        return bool(re.search(r'[。！？；:.!?;]$', text.strip()))

    def _is_list_item(self, text: str) -> bool:
        """判断是否为列表项（有序列表）

        识别模式：
        - 1. 内容
        - 1) 内容
        - 1、内容
        - （一）内容
        """
        text = text.strip()
        return bool(
            re.match(r'^\d+[\.\)、]', text) or  # 1. 或 1) 或 1、
            re.match(r'^（[一二三四五六七八九十]+）', text)  # （一）
        )


class ManualCleaner:
    """系统操作手册类文档清洗器 — 暂留空。"""

    def clean(self, md_text: str, filename: str) -> str:
        return md_text


# ── Cleaner 自动路由工厂函数 ──

def get_cleaner_for_file(file_path, settings) -> PolicyCleaner | ManualCleaner:
    """根据文件路径自动选择 Cleaner

    Args:
        file_path: Path object，文件路径
        settings: ServiceSettings object，服务配置

    Returns:
        PolicyCleaner | ManualCleaner
    """
    from pathlib import Path

    abs_path = Path(file_path).resolve()

    # 检查文件是否在 policy_data_dir 下
    policy_dir = settings.policy_data_dir.resolve()
    if policy_dir in abs_path.parents or abs_path.parent == policy_dir:
        return PolicyCleaner()

    # 检查文件是否在 manual_data_dir 下
    manual_dir = settings.manual_data_dir.resolve()
    if manual_dir in abs_path.parents or abs_path.parent == manual_dir:
        return ManualCleaner()

    # 默认使用 PolicyCleaner（向后兼容）
    return PolicyCleaner()
