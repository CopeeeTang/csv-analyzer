"""全局上下文管理器

存储DataFrame元数据和项目概述等全局信息，
这些信息在每次LLM调用时都会包含，且不会被会话压缩器压缩
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime


class GlobalContext:
    """
    全局上下文管理器

    存储不应被压缩的核心信息：
    1. DataFrame元数据（列名、类型、shape、统计信息）
    2. 项目概述（CSV文件信息、分析目标）
    3. Sandbox环境配置
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # DataFrame元数据
        self._df_metadata: Optional[Dict[str, Any]] = None

        # CSV文件信息
        self._csv_info: Optional[Dict[str, Any]] = None

        # Sandbox环境配置
        self._sandbox_config: Optional[str] = None

        # 初始化时间
        self._init_time = datetime.now()

        self.logger.debug("全局上下文管理器初始化完成")

    def set_dataframe_metadata(self, df_info: Dict[str, Any], csv_path: str = None):
        """
        设置DataFrame元数据

        Args:
            df_info: DataFrame信息字典（来自CSVHandler.get_info()）
            csv_path: CSV文件路径
        """
        self._df_metadata = df_info

        # 提取关键信息
        self._csv_info = {
            'path': csv_path,
            'shape': df_info.get('shape'),
            'columns': df_info.get('columns', []),
            'dtypes': df_info.get('dtypes', {}),
            'loaded_at': self._init_time.isoformat()
        }

        self.logger.info(f"DataFrame元数据已设置: {df_info['shape'][0]}行 × {df_info['shape'][1]}列")

    def set_sandbox_config(self, config: str):
        """
        设置Sandbox环境配置说明

        Args:
            config: Sandbox环境配置的文本描述
        """
        self._sandbox_config = config
        self.logger.debug("Sandbox配置已设置")

    def get_global_context_prompt(self) -> str:
        """
        生成全局上下文的prompt文本

        Returns:
            包含所有全局上下文信息的格式化文本
        """
        parts = []

        # 1. DataFrame元数据
        if self._df_metadata:
            parts.append("【数据集信息】（全局上下文，所有分析都基于此数据）")
            parts.append(f"• 数据规模: {self._csv_info['shape'][0]}行 × {self._csv_info['shape'][1]}列")
            parts.append(f"• 列名: {', '.join(self._csv_info['columns'])}")

            parts.append("\n数据类型:")
            for col, dtype in self._csv_info['dtypes'].items():
                parts.append(f"  - {col}: {dtype}")

            # 添加数据特征提示
            has_sales = 'Sales' in self._csv_info['columns']
            has_rating = 'Rating' in self._csv_info['columns']

            if has_sales or has_rating:
                parts.append("\n⚠️ 数据特征提示:")
                if has_sales:
                    parts.append("  - Sales列包含'$'和','符号，需要清洗后才能数值计算")
                if has_rating:
                    parts.append("  - Rating列包含'%'符号，需要清洗后才能数值计算")

        # 2. Sandbox环境配置
        if self._sandbox_config:
            parts.append("\n" + self._sandbox_config)

        return "\n".join(parts)

    def get_context_summary(self) -> Dict[str, Any]:
        """
        获取上下文摘要（用于日志或调试）

        Returns:
            上下文信息的字典
        """
        return {
            'has_df_metadata': self._df_metadata is not None,
            'has_sandbox_config': self._sandbox_config is not None,
            'csv_info': self._csv_info,
            'init_time': self._init_time.isoformat()
        }

    def is_ready(self) -> bool:
        """
        检查全局上下文是否已就绪

        Returns:
            True if ready, False otherwise
        """
        return self._df_metadata is not None


# 全局单例实例
_global_context_instance: Optional[GlobalContext] = None


def get_global_context() -> GlobalContext:
    """
    获取全局上下文单例实例

    Returns:
        GlobalContext实例
    """
    global _global_context_instance

    if _global_context_instance is None:
        _global_context_instance = GlobalContext()

    return _global_context_instance


def reset_global_context():
    """重置全局上下文（主要用于测试）"""
    global _global_context_instance
    _global_context_instance = None
