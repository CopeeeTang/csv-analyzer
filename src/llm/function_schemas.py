"""智谱AI Function Calling Schema定义"""

from typing import Dict, Any


class CodeGenerationSchemas:
    """代码生成的Function Calling Schema"""

    @staticmethod
    def get_python_code_schema() -> Dict[str, Any]:
        """
        获取Python代码生成的Schema

        Returns:
            符合智谱AI格式的tools定义
        """
        return {
            "type": "function",
            "function": {
                "name": "generate_python_code",
                "description": "生成用于CSV数据分析的Python代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "analysis_approach": {
                            "type": "string",
                            "description": "分析方法的简要说明，例如：按时间分组计算销售额总和"
                        },
                        "code": {
                            "type": "string",
                            "description": "可执行的Python代码，使用df变量操作DataFrame，需要打印结果。重要：不要使用__import__()函数，直接使用import语句。"
                        },
                        "imports": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "需要的额外import语句（如果有）"
                        },
                        "expected_output": {
                            "type": "string",
                            "description": "预期输出的简要描述"
                        }
                    },
                    "required": ["code", "analysis_approach"]
                }
            }
        }

    @staticmethod
    def get_code_explanation_schema() -> Dict[str, Any]:
        """
        获取代码解释的Schema

        Returns:
            符合智谱AI格式的tools定义
        """
        return {
            "type": "function",
            "function": {
                "name": "explain_analysis_result",
                "description": "解释数据分析的结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "分析结果的简明总结（1-2句话）"
                        },
                        "key_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键发现列表"
                        },
                        "data_insights": {
                            "type": "string",
                            "description": "从数据中得出的洞察和解释"
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "基于分析的建议（可选）"
                        }
                    },
                    "required": ["summary", "key_findings", "data_insights"]
                }
            }
        }

    @staticmethod
    def get_error_analysis_schema() -> Dict[str, Any]:
        """
        获取错误分析的Schema（用于错误重试）

        Returns:
            符合智谱AI格式的tools定义
        """
        return {
            "type": "function",
            "function": {
                "name": "analyze_and_fix_code_error",
                "description": "分析代码错误并生成修正后的代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "error_analysis": {
                            "type": "object",
                            "properties": {
                                "root_cause": {
                                    "type": "string",
                                    "description": "错误的根本原因分析"
                                },
                                "why_it_failed": {
                                    "type": "string",
                                    "description": "为什么之前的代码会失败"
                                },
                                "solution_approach": {
                                    "type": "string",
                                    "description": "解决方案的思路"
                                }
                            },
                            "required": ["root_cause", "why_it_failed", "solution_approach"]
                        },
                        "fixed_code": {
                            "type": "string",
                            "description": "修正后的完整可执行Python代码。重要：不要使用__import__()函数，直接使用import语句。"
                        },
                        "changes_made": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "所做的关键修改列表"
                        }
                    },
                    "required": ["error_analysis", "fixed_code", "changes_made"]
                }
            }
        }
