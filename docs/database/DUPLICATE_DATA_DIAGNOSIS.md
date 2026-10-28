# stock_daily_quotes 重复数据诊断报告

**诊断时间**: 2026-10-27  
**集合**: `tradingagentscn_v0_mac.stock_daily_quotes`  
**问题**: 单日出现 10,703 条记录（正常应为 5,500 条左右）

---

## 🔍 问题根因

### 现象

**10/27 数据统计**：
- 总记录数: **10,703 条**
- 唯一股票: **5,577 只**
- 重复倍数: **1.92x**

**重复分布**：
- 单条记录股票: 487 只 ✅
- **重复2次股票: 5,054 只** ⚠️（占比 90.6%）
- 重复3次股票: 36 只 🚨

### 根本原因

**🎯 多数据源重复写入，未去重！**

同一只股票在同一天被 **3个数据源各写入1条**：
1. **tushare** — 2026-10-27 20:24:08
2. **baostock** — 2026-10-28 00:11:29
3. **akshare** — 2026-10-28 02:07:30

**示例**（600843 上海建工）：

| 字段 | Tushare | Baostock | Akshare | 是否一致 |
|------|---------|----------|---------|---------|
| close | 7.46 | 7.46 | 7.46 | ✅ |
| volume | 24629052 | 24629052 | 24629052 | ✅ |
| amount | 187925533.0 | 187925532.86 | 187925533.0 | ❌ 微小差异 |
| data_source | tushare | baostock | akshare | ❌ **不同** |
| created_at | 20:24:08 | 00:11:29 | 02:07:30 | ❌ **不同时间** |
| adjustflag | None | 2.0 | None | ❌ Baostock 独有字段 |
| turnover_rate | None | 5.2489 | None | ❌ Baostock 独有字段 |

---

## 🛡️ 现有索引（失效）

```javascript
// 现有唯一索引（包含 data_source）
symbol_date_source_period_unique: {
  key: [('symbol', 1), ('trade_date', 1), ('data_source', 1), ('period', 1)],
  unique: true
}
```

**为什么失效？**
- 索引包含了 `data_source` 字段
- 不同数据源的数据被视为"不同记录"，可以同时存在
- 导致 tushare/baostock/akshare 各写入一份，绕过了唯一性约束

---

## 💡 修复方案

### 方案 A：修改索引（推荐）⭐

**适用场景**：只保留一个数据源的数据，优先级 Tushare > Baostock > Akshare

#### 1. 删除旧索引
```javascript
db.stock_daily_quotes.dropIndex('symbol_date_source_period_unique');
```

#### 2. 创建新的唯一索引（不包含 data_source）
```javascript
db.stock_daily_quotes.createIndex(
  {symbol: 1, trade_date: 1, period: 1},
  {unique: true, name: 'symbol_date_period_unique'}
);
```

#### 3. 清理历史重复数据
```python
from pymongo import MongoClient

client = MongoClient('localhost', 27017)
db = client['tradingagentscn_v0_mac']
collection = db['stock_daily_quotes']

# 数据源优先级（高 → 低）
SOURCE_PRIORITY = {'tushare': 1, 'baostock': 2, 'akshare': 3}

# 查找所有重复记录
pipeline = [
    {'$group': {
        '_id': {'symbol': '$symbol', 'trade_date': '$trade_date', 'period': '$period'},
        'count': {'$sum': 1},
        'ids': {'$push': '$_id'},
        'sources': {'$push': '$data_source'}
    }},
    {'$match': {'count': {'$gt': 1}}}
]

duplicates = list(collection.aggregate(pipeline))
print(f"找到 {len(duplicates)} 组重复数据")

deleted_count = 0
for dup in duplicates:
    symbol = dup['_id']['symbol']
    trade_date = dup['_id']['trade_date']
    period = dup['_id']['period']
    
    # 查找该组的所有记录
    records = list(collection.find({
        'symbol': symbol,
        'trade_date': trade_date,
        'period': period
    }).sort('_id', 1))
    
    # 按数据源优先级排序（Tushare 优先）
    records.sort(key=lambda x: SOURCE_PRIORITY.get(x.get('data_source'), 99))
    
    # 保留第一条（优先级最高），删除其余
    keep_id = records[0]['_id']
    delete_ids = [r['_id'] for r in records[1:]]
    
    result = collection.delete_many({'_id': {'$in': delete_ids}})
    deleted_count += result.deleted_count

print(f"✅ 清理完成，删除 {deleted_count} 条重复记录")
```

---

### 方案 B：保留多数据源（备选）

**适用场景**：需要对比多个数据源的数据质量，保留所有来源

#### 修改应用层查询逻辑
```python
# 查询时只取优先级最高的数据源
def get_daily_quotes(symbol, trade_date):
    # 按数据源优先级排序
    for source in ['tushare', 'baostock', 'akshare']:
        result = collection.find_one({
            'symbol': symbol,
            'trade_date': trade_date,
            'data_source': source
        })
        if result:
            return result
    return None
```

#### 或添加视图/去重查询
```javascript
// 创建去重视图（只展示 Tushare 数据）
db.createView(
  'stock_daily_quotes_unique',
  'stock_daily_quotes',
  [
    {$sort: {symbol: 1, trade_date: 1, data_source: 1}},
    {$group: {
      _id: {symbol: '$symbol', trade_date: '$trade_date'},
      doc: {$first: '$$ROOT'}
    }},
    {$replaceRoot: {newRoot: '$doc'}}
  ]
);
```

---

### 方案 C：修改数据同步逻辑（治本）⭐⭐

**在数据写入时就去重，而非事后清理**

#### Python 同步脚本修改
```python
# ❌ 错误做法（会重复插入）
collection.insert_many(records)

# ✅ 正确做法（upsert 自动去重）
from pymongo import UpdateOne

operations = [
    UpdateOne(
        {
            'symbol': rec['symbol'],
            'trade_date': rec['trade_date'],
            'period': rec.get('period', 'daily')
        },
        {
            '$set': rec,
            '$setOnInsert': {'created_at': datetime.now()}
        },
        upsert=True
    )
    for rec in records
]

result = collection.bulk_write(operations)
print(f"插入: {result.upserted_count}, 更新: {result.modified_count}")
```

#### 或先删除再插入
```python
# 批量删除当天数据
collection.delete_many({
    'trade_date': today,
    'data_source': 'tushare'  # 只删除当前数据源的
})

# 重新插入
collection.insert_many(records)
```

---

## 📋 执行清单

### 立即执行（紧急修复）

- [ ] 1. 备份数据库
  ```bash
  docker exec tradingagents-mongodb mongodump \
    --db=tradingagentscn_v0_mac \
    --collection=stock_daily_quotes \
    --out=/tmp/mongodb_backup_20261027
  ```

- [ ] 2. 运行去重脚本（保留 Tushare 优先）
  ```bash
  python3 /path/to/dedup_script.py
  ```

- [ ] 3. 删除旧索引，创建新索引
  ```bash
  mongosh tradingagentscn_v0_mac --eval "
    db.stock_daily_quotes.dropIndex('symbol_date_source_period_unique');
    db.stock_daily_quotes.createIndex(
      {symbol: 1, trade_date: 1, period: 1},
      {unique: true, name: 'symbol_date_period_unique'}
    );
  "
  ```

### 根本修复（代码层面）

- [ ] 4. 修改后端数据同步服务
  - 文件: `backend/app/services/stock_data_sync.py`（或类似路径）
  - 改为 `bulk_write` + `UpdateOne(upsert=True)`

- [ ] 5. 添加单元测试
  - 验证同一股票+同日期不会插入2次
  - 验证不同数据源写入后只保留1条

- [ ] 6. 监控告警
  - 每日检查重复率：`唯一股票数 / 总记录数 < 0.95` 则告警

---

## 🎯 预期效果

**修复前**：
- 10/27 数据: 10,703 条（5,577 只股票）
- 平均每只股票: 1.92 条

**修复后**：
- 10/27 数据: **5,577 条**（5,577 只股票）✅
- 平均每只股票: **1.00 条**✅
- 节省存储空间: **~48%**

---

## 📌 注意事项

1. **数据源选择**：Tushare 15000积分数据最全面，优先保留
2. **历史数据**：修复脚本会清理所有历史重复（不止10/27），耗时可能较长
3. **业务影响**：修复期间建议停止数据同步服务，避免冲突
4. **回滚方案**：修复前务必备份，出问题可快速恢复

---

**诊断工具**: `/tmp/analyze_duplicates_v2.py`  
**修复脚本**: 待编写（基于上述方案A）
