# 快速开始指南

5分钟快速上手CSV数据分析系统！
(我保留了我自己的zhipu的apikey用于测试，请省着点用)

---


## 步骤1: 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

---

## 步骤2: 安装依赖

```bash
pip install -r requirements.txt
```

## 步骤3: 运行系统

```bash
python main.py data/your_data.csv
```

系统启动后会显示：

```
╔════════════════════════════════════════╗
║ CSV数据分析系统                        ║
║ 基于智谱GLM-4.6大模型                  ║
╚════════════════════════════════════════╝

┌─ 数据加载成功 ──────────────┐
│ 文件: your_data.csv          │
│ 形状: 1000 行 × 5 列         │
│ ...                          │
└──────────────────────────────┘

❓ 请输入问题:
```

---

## 步骤4: 开始分析

### 示例1: 基础统计
```
❓ 请输入问题: 数据集有多少行多少列？

[系统会生成代码并执行]

生成的代码:
print(f"数据集形状: {df.shape}")
print(f"行数: {df.shape[0]}, 列数: {df.shape[1]}")

执行结果:
数据集形状: (1000, 5)
行数: 1000, 列数: 5

分析解释:
该数据集包含1000行数据和5列字段...
```

### 示例2: 趋势分析
```
❓ 请输入问题: 分析销售额随时间的变化趋势

[系统生成可视化代码]

执行结果:
图表已保存

📊 图表已保存: output/plots/plot_xxx_1.png

分析解释:
从图表可以看出，销售额呈现上升趋势...
```

### 示例3: 关联问题
```
❓ 请输入问题: 对不同产品类别进行同样的分析

[系统利用历史上下文，理解"同样的分析"]
```

---

## 步骤5: 退出和查看结果

```
❓ 请输入问题: exit

┌─ 会话统计 ────────────┐
│ 总轮次      : 3        │
│ 成功次数    : 3        │
│ 失败次数    : 0        │
│ 生成图表    : 2        │
└────────────────────────┘

✓ 分析报告已导出: output/reports/20250115_143022.md

感谢使用CSV数据分析系统！
```

### 查看输出文件

```bash
# 查看会话记录
cat output/sessions/20250115_143022.json

# 查看图表
open output/plots/plot_20250115_143022_1.png

# 查看分析报告
cat output/reports/20250115_143022.md
```

---

## 常见问题排查

### 问题1: ModuleNotFoundError

```bash
# 重新安装依赖
pip install -r requirements.txt

# 确认虚拟环境已激活
which python  # 应该指向venv目录
```

### 问题2: API密钥错误

```bash
# 检查.env文件
cat .env

# 确保格式正确（无引号、无空格）
ZHIPU_API_KEY=your_key_here

# 测试API连接
python test_api.py
```

### 问题3: CSV编码错误

```bash
# 转换为UTF-8编码
iconv -f GBK -t UTF-8 input.csv > output.csv

# 或使用Python
python -c "import pandas as pd; pd.read_csv('file.csv', encoding='gbk').to_csv('file_utf8.csv', encoding='utf-8', index=False)"
```

### 问题4: 执行超时

编辑 `config/config.yaml`:
```yaml
executor:
  timeout: 60  # 增加到60秒
```

### 问题5: 代码执行被拒绝

查看错误信息 - 系统的Sandbox可能阻止了危险操作：
- ✅ 允许: pandas, numpy, matplotlib
- ❌ 禁止: os, sys, subprocess, eval, exec

---

## 命令行选项

```bash
# 使用自定义配置
python main.py data/test.csv --config my_config.yaml

# 指定会话ID
python main.py data/test.csv --session-id my_analysis

# 调整日志级别
python main.py data/test.csv --log-level DEBUG
```

---

## 测试问题建议

### 基础分析
1. 数据集的基本信息是什么？
2. 每列的数据类型是什么？
3. 是否有缺失值？

### 统计分析
4. 计算数值列的平均值
5. 找出最大值和最小值
6. 计算标准差

### 可视化
7. 绘制数据分布直方图
8. 制作各类别的饼图
9. 绘制时间序列趋势线

### 关联问题（测试上下文）
10. 第一问：分析A类别的销售额
11. 第二问：对B类别做同样的分析
12. 第三问：比较这两个类别

---

## 验证系统改进

运行综合测试脚本验证所有核心功能：

```bash
python verify_improvements.py
```

测试内容：
- ✅ API连接测试
- ✅ Sandbox安全隔离（5个子测试）
- ✅ 长上下文处理（4个子测试）
- ✅ Function Calling代码生成
- ✅ 智能上下文压缩

---

## 下一步

- 📖 阅读 [README.md](README.md) 了解完整功能和架构
- 🎥 录制演示视频（使用asciinema）
- 🧪 运行 `pytest tests/` 查看单元测试

---

**祝使用愉快！** 🎉

遇到问题？查看 [README.md](README.md) 获取更多帮助。
