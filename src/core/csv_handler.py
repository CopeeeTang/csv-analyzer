"""CSV文件处理器"""

import pandas as pd
import logging
from pathlib import Path
from typing import Dict, Any


class CSVHandler:
    """CSV文件处理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.df: pd.DataFrame = None
        self.file_path: str = None

    def load(self, file_path: str) -> pd.DataFrame:
        """
        加载CSV文件

        Args:
            file_path: CSV文件路径

        Returns:
            pandas DataFrame

        Raises:
            FileNotFoundError: 文件不存在
            Exception: 加载失败
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self.logger.info(f"加载CSV文件: {file_path}")

        try:
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']

            for encoding in encodings:
                try:
                    self.df = pd.read_csv(file_path, encoding=encoding)
                    self.file_path = str(file_path)
                    self.logger.info(
                        f"成功加载 (编码: {encoding}), "
                        f"形状: {self.df.shape}"
                    )
                    return self.df
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败，使用默认编码
            self.df = pd.read_csv(file_path)
            self.file_path = str(file_path)
            return self.df

        except Exception as e:
            self.logger.error(f"加载CSV失败: {str(e)}")
            raise

    def get_info(self) -> Dict[str, Any]:
        """
        获取DataFrame信息

        Returns:
            包含DataFrame元信息的字典
        """
        if self.df is None:
            raise ValueError("未加载任何数据，请先调用load()")

        # 获取数据类型
        dtypes_dict = {col: str(dtype) for col, dtype in self.df.dtypes.items()}

        # 获取前5行的字符串表示
        head_str = self.df.head().to_string()

        info = {
            'columns': list(self.df.columns),
            'shape': self.df.shape,
            'dtypes': dtypes_dict,
            'head': self.df.head().to_dict(),
            'head_str': head_str,
            'file_path': self.file_path
        }

        return info

    def get_summary(self) -> str:
        """
        获取数据摘要（用于显示）

        Returns:
            格式化的摘要字符串
        """
        if self.df is None:
            return "未加载数据"

        summary_parts = [
            f"文件: {Path(self.file_path).name}",
            f"形状: {self.df.shape[0]} 行 × {self.df.shape[1]} 列",
            f"列名: {', '.join(self.df.columns)}",
            "\n数据预览:",
            self.df.head().to_string()
        ]

        return "\n".join(summary_parts)

    def validate(self) -> bool:
        """
        验证数据是否有效

        Returns:
            数据是否有效
        """
        if self.df is None:
            return False

        if self.df.empty:
            self.logger.warning("DataFrame为空")
            return False

        return True
