"""日志配置模块"""
import sys
from pathlib import Path
from typing import Optional
from loguru import logger
from src.utils.config import get_settings


def setup_logger(profile: Optional[str] = None):
    """
    配置日志（控制台 + 文件）。

    Args:
        profile: 可选 "api" | "batch"。api 使用 logging.api_file，batch 使用 logging.batch_file；
                 未传则使用 logging.file。
    """
    settings = get_settings()
    log_config = settings.logging

    if profile == "api":
        log_file_path = log_config.api_file
    elif profile == "batch":
        log_file_path = log_config.batch_file
    else:
        log_file_path = log_config.file

    # 移除默认处理器
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_config.level,
        colorize=True,
    )

    # 添加文件输出
    log_file = Path(log_file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_config.level,
        rotation=log_config.rotation,
        retention=log_config.retention,
        encoding="utf-8",
    )

    return logger
