"""配置管理模块"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """配置类"""

    def __init__(self, config_dict: Dict[str, Any]):
        self._config = config_dict

    def get(self, key: str, default=None):
        """获取配置项，支持点号分隔的嵌套键"""
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def __getitem__(self, key):
        return self.get(key)

    def __repr__(self):
        return f"Config({self._config})"


def load_config(config_path: str = None) -> Config:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径，默认为项目根目录的config/config.yaml

    Returns:
        Config对象
    """
    if config_path is None:
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "config.yaml"

    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config_dict = yaml.safe_load(f)

    # 替换环境变量
    config_dict = _replace_env_vars(config_dict)

    return Config(config_dict)


def _replace_env_vars(config_dict: Dict) -> Dict:
    """递归替换配置中的环境变量"""
    for key, value in config_dict.items():
        if isinstance(value, dict):
            config_dict[key] = _replace_env_vars(value)
        elif isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_key = value[2:-1]
            config_dict[key] = os.getenv(env_key, value)

    return config_dict


def get_api_key() -> str:
    """获取智谱AI API密钥"""
    api_key = os.getenv('ZHIPU_API_KEY')
    if not api_key:
        raise ValueError(
            "未设置ZHIPU_API_KEY环境变量。"
            "请创建.env文件并设置: ZHIPU_API_KEY=your_key"
        )
    return api_key
