import sys
from loguru import logger

# 移除默认 handler
logger.remove()

# 添加新的 handler，格式更清晰
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)