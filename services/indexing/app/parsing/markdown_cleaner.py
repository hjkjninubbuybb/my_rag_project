"""PDF→Markdown 转换后的专用清洗器。"""

import re
from collections import Counter


class MarkdownCleaner:
    """PDF→Markdown 转换后的专用清洗器。

    处理 4 类脏数据：重复页眉、残留页码、目录内容、多余空行。
    同时合并被 PDF 换行截断的段落。
    """

    def clean(self, md_text: str) -> str:
        text = self._remove_repeated_headers(md_text)  # 依赖 --- 估算页数，须先执行
        text = self._remove_page_separators(text)
        text = self._remove_page_numbers(text)
        text = self._remove_toc_section(text)
        text = self._merge_broken_lines(text)
        text = self._normalize_whitespace(text)
        return text

    def _remove_repeated_headers(self, text: str) -> str:
        """自动检测并删除重复页眉。

        统计每行出现频率，行长 >=10 且出现次数 >= 总页数 50% 的行视为页眉。
        页数从 --- 分隔符数量 + 1 估算。
        保留第一次出现（作为文档标题），删除后续重复。
        不影响图片引用行和分隔符。
        """
        lines = text.split('\n')

        # 估算页数
        separator_count = sum(1 for line in lines if line.strip() == '---')
        estimated_pages = max(separator_count + 1, 2)
        threshold = estimated_pages * 0.5

        # 统计每行出现频率（跳过特殊行）
        line_counts: Counter[str] = Counter()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == '---':
                continue
            if stripped.startswith('!['):
                continue
            if len(stripped) >= 10:
                line_counts[stripped] += 1

        # 找出重复页眉
        header_patterns = {
            line for line, count in line_counts.items()
            if count >= threshold
        }

        if not header_patterns:
            return text

        # 删除重复页眉，保留首次出现
        seen: set[str] = set()
        cleaned_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in header_patterns:
                if stripped not in seen:
                    seen.add(stripped)
                    cleaned_lines.append(line)
                # else: skip duplicate
            else:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _remove_page_separators(self, text: str) -> str:
        """去除 PDF 页面拼接时插入的 --- 分隔符。"""
        lines = text.split('\n')
        cleaned_lines = [line for line in lines if line.strip() != '---']
        return '\n'.join(cleaned_lines)

    def _remove_page_numbers(self, text: str) -> str:
        """去除独立行页码。

        匹配：独立行纯数字 <=4 位、第 X 页、Page X of Y。
        """
        lines = text.split('\n')
        cleaned_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^(第\s*\d+\s*页|Page\s*\d+\s*of\s*\d+)$', stripped):
                continue
            if stripped.isdigit() and len(stripped) <= 4:
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def _remove_toc_section(self, text: str) -> str:
        """去除目录区域。

        检测 ## 目录 或 #### 目 录 标题，
        跳过后续带省略号的 TOC 行，直到遇到下一个正文标题。
        """
        lines = text.split('\n')
        cleaned_lines: list[str] = []

        i = 0
        n = len(lines)
        in_toc = False

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 检测目录标题
            if re.match(
                r'^#{1,6}\s*(目\s*录|目录|TOC|Table\s*of\s*Contents)',
                stripped,
                re.IGNORECASE,
            ):
                in_toc = True
                i += 1
                continue

            if in_toc:
                is_toc_item = False

                # 模式1: 数字+空格+文字+省略号（可能有页码）
                if re.match(r'^\d+\s+\S+.*\.{2,}\s*\d*$', stripped):
                    is_toc_item = True
                # 模式2: 缩进+数字+点
                if re.match(r'^\s+\d+\.+$', stripped):
                    is_toc_item = True
                # 模式3: 数字.数字 章节标题 + 省略号
                if re.match(r'^\d+(\.\d+)+\s+.*\.{2,}', stripped):
                    is_toc_item = True
                # 模式4: 含连续点号的行（通用 TOC 行）
                if re.search(r'\.{4,}', stripped):
                    is_toc_item = True

                # 空行在 TOC 中跳过
                if not stripped:
                    i += 1
                    continue

                # 非 TOC 项且非空 → 退出 TOC 区域
                if not is_toc_item:
                    in_toc = False

                if in_toc:
                    i += 1
                    continue

            cleaned_lines.append(line)
            i += 1

        return '\n'.join(cleaned_lines)

    def _merge_broken_lines(self, text: str) -> str:
        """合并被 PDF 换行截断的段落。

        中文句子未以句子结束符结尾 + 下一行非标题/列表/图片/空行/分隔符 → 合并。
        """
        lines = text.split('\n')
        merged: list[str] = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 特殊行直接保留
            if not stripped or self._is_protected_line(stripped):
                merged.append(line)
                i += 1
                continue

            # 尝试合并后续行
            buffer = stripped
            i += 1
            while i < n:
                next_stripped = lines[i].strip()
                # 当前行未以句末标点结尾，且下一行是可合并的普通文本
                if (
                    not self._ends_with_sentence(buffer)
                    and next_stripped
                    and not self._is_protected_line(next_stripped)
                ):
                    buffer += next_stripped
                    i += 1
                else:
                    break

            merged.append(buffer)

        return '\n'.join(merged)

    def _normalize_whitespace(self, text: str) -> str:
        """压缩 3+ 连续空行为 2 个。"""
        return re.sub(r'\n{3,}', '\n\n', text)

    def _is_protected_line(self, stripped: str) -> bool:
        """判断是否为不可合并的受保护行。"""
        return (
            stripped.startswith('#')              # 标题
            or stripped.startswith('![')           # 图片引用
            or stripped.startswith('- ')           # 无序列表
            or stripped.startswith('* ')           # 无序列表
            or stripped.startswith('|')            # 表格
            or stripped.startswith('>')            # 引用
            or bool(re.match(r'^\d+[.)\u3001]', stripped))  # 有序列表
        )

    @staticmethod
    def _ends_with_sentence(text: str) -> bool:
        """判断文本是否以句子结束符结尾。"""
        return bool(re.search(r'[。！？；:.!?;]$', text.strip()))
