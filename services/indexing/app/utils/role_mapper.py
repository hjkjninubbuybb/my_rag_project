"""角色映射工具。

从文件名自动识别用户角色，用于多模态 RAG 的权限过滤。
"""

from typing import Optional


# 文件名关键词 → 角色标识
ROLE_MAPPING = {
    "指导老师": "teacher",
    "教师": "teacher",
    "学生": "student",
    "评阅专家": "reviewer",
    "评阅": "reviewer",
    "答辩组": "defense_committee",
    "答辩": "defense_committee",
}

# 角色中文名称
ROLE_DISPLAY_NAMES = {
    "teacher": "指导老师",
    "student": "学生",
    "reviewer": "评阅专家",
    "defense_committee": "答辩组成员",
    "common": "通用",
}


def extract_role_from_filename(filename: str) -> str:
    """从文件名提取角色标识。

    Args:
        filename: 文件名（如 "4-1 郑州大学毕业论文系统指导老师操作手册.pdf"）

    Returns:
        角色标识（如 "teacher"），未匹配则返回 "common"（通用文档，所有角色可见）

    Examples:
        >>> extract_role_from_filename("4-1 郑州大学毕业论文系统指导老师操作手册.pdf")
        'teacher'
        >>> extract_role_from_filename("0 关于做好2026届本科生毕业论文设计工作的通知教务部.pdf")
        'common'
    """
    for keyword, role in ROLE_MAPPING.items():
        if keyword in filename:
            return role
    return "common"


def get_role_display_name(role: str) -> str:
    """获取角色的中文显示名称。

    Args:
        role: 角色标识（如 "teacher"）

    Returns:
        中文名称（如 "指导老师"）
    """
    return ROLE_DISPLAY_NAMES.get(role, "未知角色")


def validate_role(role: Optional[str]) -> bool:
    """验证角色标识是否有效。

    Args:
        role: 角色标识

    Returns:
        True 如果有效（包括 None 表示管理员），False 否则
    """
    if role is None:
        return True  # None 表示管理员，可以查看所有
    return role in ROLE_DISPLAY_NAMES
