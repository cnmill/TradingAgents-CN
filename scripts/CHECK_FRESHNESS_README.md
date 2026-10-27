# 数据时效性检查工具

## 概述

`check_data_freshness.py` 是一个快速检查 TradingAgents-CN 数据库中股票数据是否为最新的工具脚本。

**核心功能**：
- ✅ 自动判断预期最新交易日（考虑周末、交易时间）
- ✅ 检查日线行情、基本信息、新闻数据的时效性
- ✅ 显示最近5个交易日的数据分布
- ✅ 支持查询特定股票的最新数据
- ✅ 美观的表格输出（基于 Rich 库）

---

## 使用方法

### 1. 基础检查（汇总模式）

```bash
# 方式1：直接运行 Python 脚本
cd /Users/mac/Documents/own/project/TradingAgents-CN
source .venv/bin/activate
python scripts/check_data_freshness.py

# 方式2：使用便捷脚本（推荐）
bash scripts/check_freshness.sh
```

**输出示例**：
```
╭─────────────────────────────────╮
│ TradingAgents-CN 数据时效性检查 │
╰─────────────────────────────────╯

                 数据集汇总                                   
┌───────────────────────────────┬───────────┬─────────────────────────┬────────┐
│ 数据集                        │ 状态      │ 最新日期/更新时间       │ 记录数 │
├───────────────────────────────┼───────────┼─────────────────────────┼────────┤
│ 日线行情 (stock_daily_quotes) │ ✅ 最新   │ 2026-10-27 (预期:       │    706 │
│                               │           │ 2026-10-27)             │        │
│ 基本信息 (stock_basic_info)   │ ✅ 最新   │ 2026-10-26 15:16:43     │  7,873 │
│ 新闻资讯 (stock_news)         │ ⚠️ 待更新 │ 2026-10-19 18:53:00     │     30 │
└───────────────────────────────┴───────────┴─────────────────────────┴────────┘

最近5个交易日数据分布:
  2026-10-27: ███████ 706 只
  2026-10-26: ████████████████████████ 5,144 只
  2026-10-23: ████████████████████████ 5,144 只
```

---

### 2. 详细模式

```bash
python scripts/check_data_freshness.py --detailed
# 或
bash scripts/check_freshness.sh -d
```

**额外输出**：
- 当前时间
- 预期最新交易日（自动计算）
- 实际最新日期
- 时效性判断结果

---

### 3. 查询特定股票

```bash
python scripts/check_data_freshness.py --stock 600487.SH
# 或
bash scripts/check_freshness.sh -s 600487.SH
```

**输出示例**：
```
╭─────────────────────────╮
│ 股票数据检查: 600487.SH │
╰─────────────────────────╯

              最近5个交易日                  
┌────────────┬────────┬────────┬────────────────┐
│ 日期       │ 收盘价 │ 涨跌幅 │         成交额 │
├────────────┼────────┼────────┼────────────────┤
│ 2026-10-26 │  48.06 │ -8.14% │ 706834.70 万元 │
│ 2026-10-23 │  52.32 │ +1.75% │ 863942.24 万元 │
│ 2026-10-22 │  51.42 │ -0.06% │ 835301.54 万元 │
└────────────┴────────┴────────┴────────────────┘

✅ 数据已是最新
  最新日期: 2026-10-26
  预期日期: 2026-10-27
```

---

## 参数说明

| 参数 | 简写 | 说明 |
|---|---|---|
| `--detailed` | `-d` | 显示详细信息（包含时效性判断） |
| `--stock <symbol>` | `-s <symbol>` | 查询特定股票（如: 600487.SH） |

---

## 交易日判断逻辑

脚本会自动计算"预期最新交易日"：

| 当前时间 | 预期最新交易日 |
|---|---|
| 周一 ~ 周五 **15:30后** | 当日 |
| 周一 ~ 周五 **15:30前** | 前一交易日 |
| **周六** | 上周五 |
| **周日** | 上周五 |

**示例**：
- 周五 16:00 → 预期周五
- 周一 10:00 → 预期上周五
- 周六 → 预期上周五

---

## 数据时效性状态

### ✅ 最新（fresh）
- 日线行情：`latest_date == expected_date`
- 基本信息：`updated_at` 在7天内
- 新闻资讯：`publish_time` 是今日

### ⚠️ 待更新（stale）
- 日线行情：`latest_date < expected_date`
- 基本信息：`updated_at` 超过7天
- 新闻资讯：`publish_time` 不是今日

### ❓ 未知（unknown）
- 缺少时间戳字段，无法判断

---

## 典型使用场景

### 场景1：每日开盘前检查

```bash
# 上午 9:20 检查昨日数据是否已同步
bash scripts/check_freshness.sh

# 预期：
# - 日线行情：昨日（如 10/26）✅
# - 基本信息：昨日 ✅
# - 新闻：可能 ⚠️（非关键）
```

### 场景2：盘后检查今日数据

```bash
# 下午 16:00 检查今日数据是否已同步
bash scripts/check_freshness.sh -d

# 预期：
# - 若定时任务已运行（18:00后）：今日 ✅
# - 若定时任务未运行（15:30-18:00）：昨日 ⚠️
```

### 场景3：持仓个股快速检查

```bash
# 检查亨通光电最新行情
bash scripts/check_freshness.sh -s 600487.SH

# 检查多只持仓
for symbol in 600487.SH 000001.SZ 600036.SH; do
    echo "=== $symbol ==="
    bash scripts/check_freshness.sh -s $symbol
    echo ""
done
```

### 场景4：集成到自动化流程

```bash
#!/bin/bash
# daily_check.sh - 每日数据健康检查

cd /Users/mac/Documents/own/project/TradingAgents-CN

# 检查数据时效性
source .venv/bin/activate
result=$(python scripts/check_data_freshness.py --detailed)

# 判断是否需要同步
if echo "$result" | grep -q "⚠️ 数据需要更新"; then
    echo "检测到数据过期，启动同步..."
    python -m scripts.sync_daily_quotes
else
    echo "✅ 数据已是最新，无需同步"
fi
```

---

## 注意事项

### 1. MongoDB 连接
- 默认连接：`localhost:27017`（无认证）
- 数据库名：`tradingagentscn_v0_mac`
- 连接超时：2秒

### 2. 依赖库
需要以下 Python 包（已包含在项目环境中）：
- `pymongo`：MongoDB 客户端
- `rich`：美观的终端输出

### 3. 数据同步时间
根据 TradingAgents-CN 配置，定时任务在 **每日 18:00** 自动同步：
- 15:00 收盘
- 18:00 数据入库（延迟 3 小时）

**因此**：
- **18:00前**：预期看到"⚠️ 待更新"（正常）
- **18:30后**：预期看到"✅ 最新"（已同步）

### 4. 周末/节假日
- **周六/周日**：预期上周五数据（✅ 最新）
- **假期后首日上午**：预期假期前最后一个交易日

---

## 故障排查

### 问题1：`ModuleNotFoundError: No module named 'rich'`

**原因**：未激活项目虚拟环境

**解决**：
```bash
cd /Users/mac/Documents/own/project/TradingAgents-CN
source .venv/bin/activate
python scripts/check_data_freshness.py
```

或使用便捷脚本（自动激活环境）：
```bash
bash scripts/check_freshness.sh
```

---

### 问题2：`❌ MongoDB 连接失败`

**原因**：Docker 容器未启动

**解决**：
```bash
# 检查容器状态
docker ps | grep tradingagents-mongodb

# 启动容器
docker start tradingagents-mongodb
```

---

### 问题3：数据永远显示"⚠️ 待更新"

**可能原因**：
1. 定时同步任务未运行
2. 数据源 API 故障
3. 网络问题

**排查步骤**：
```bash
# 1. 检查后端日志
tail -100 /tmp/tradingagents_backend.log | grep -i "sync\|error"

# 2. 手动触发同步（如果有对应脚本）
python -m scripts.sync_daily_quotes

# 3. 检查 MongoDB 最新记录时间戳
python3 << EOF
from pymongo import MongoClient
c = MongoClient('localhost', 27017)
db = c['tradingagentscn_v0_mac']
latest = db.stock_daily_quotes.find_one({}, sort=[('_id', -1)])
print(f"最新记录插入时间: {latest['_id'].generation_time}")
EOF
```

---

## 文件位置

- **脚本**: `/Users/mac/Documents/own/project/TradingAgents-CN/scripts/check_data_freshness.py`
- **便捷启动**: `/Users/mac/Documents/own/project/TradingAgents-CN/scripts/check_freshness.sh`
- **文档**: `/Users/mac/Documents/own/project/TradingAgents-CN/scripts/CHECK_FRESHNESS_README.md`

---

## 扩展示例

### 集成到 Hermes Skill

```python
from hermes_tools import terminal

# 检查数据时效性
result = terminal(
    command="cd /Users/mac/Documents/own/project/TradingAgents-CN && "
            "bash scripts/check_freshness.sh -s 600487.SH",
    timeout=10
)

if "✅ 数据已是最新" in result['output']:
    print("可以开始分析")
else:
    print("数据过期，请先同步")
```

### Python 脚本调用

```python
import subprocess
import json

# 获取数据时效性状态
def check_data_status():
    result = subprocess.run(
        ["bash", "scripts/check_freshness.sh"],
        cwd="/Users/mac/Documents/own/project/TradingAgents-CN",
        capture_output=True,
        text=True
    )
    
    # 解析输出判断是否最新
    is_fresh = "✅ 数据已是最新" in result.stdout
    return is_fresh

if __name__ == '__main__':
    if check_data_status():
        print("开始执行量化策略...")
    else:
        print("等待数据同步...")
```

---

## 更新日志

### 2026-10-27
- ✅ 首次创建
- ✅ 实现基础检查、详细模式、单股票查询
- ✅ 添加交易日自动判断逻辑
- ✅ 创建便捷启动脚本 `check_freshness.sh`

---

**快速开始**：
```bash
cd /Users/mac/Documents/own/project/TradingAgents-CN
bash scripts/check_freshness.sh
```
