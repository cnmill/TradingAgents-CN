# TradingAgents-CN MongoDB 数据字典

> 供平台内 AI、数据分析任务和数据库查询工具使用。本文档以当前工作区中的模型、服务实现、索引定义和迁移脚本为准，数据库中的实际文档可能包含数据源新增字段。

## 1. 数据库约定

- **数据库**：由 `MONGO_DB` 配置决定，默认连接配置见 `.env.example`；本文档不记录连接串、账号或密码。
- **数据库类型**：MongoDB。
- **文档主键**：所有集合都有 MongoDB 自动生成的 `_id`（`ObjectId`），除非另有说明，不把 `_id` 当作业务主键。
- **时间类型**：优先使用 BSON `Date`。历史数据中可能存在 ISO 字符串或 `YYYYMMDD` 字符串，查询前应根据字段说明兼容处理。
- **金额/价格/数量**：通常为 BSON `double`/`int`；不要仅凭字段名推断单位，按下表的单位说明解释。
- **数据来源**：常见值为 `tushare`、`akshare`、`baostock`、`qmt`、`local`。同一股票和日期可能有多个来源。

## 2. AI 查询规则

1. 只读查询默认使用 `find`、`aggregate`、`countDocuments`；除非用户明确要求，不执行 `insert`、`update`、`delete`、`drop` 或建索引。
2. 查询行情、财务或新闻时优先带上股票代码和时间范围，并设置 `limit`（建议不超过 100）。
3. 股票代码使用六位字符串（例如 `000001`），不能转成整数，以免丢失前导零。代码字段同时存在 `symbol` 和 `code` 时，先按集合说明选择；必要时用 `$or` 兼容历史数据。
4. 需要“最新一条”时按对应时间字段倒序排序：行情用 `trade_date`/`updated_at`，财务用 `report_period`，新闻用 `publish_time`。
5. 统计或比较不同数据源时必须显式返回 `data_source`/`source`，不要把不同来源的记录直接混合计算。
6. 除非用户明确要求原文，结果应排除 `_id`、凭据、令牌、密码、内部提示词和完整新闻正文等敏感或高体量字段。

## 3. 核心投资数据集合

### 3.1 `stock_basic_info`：A 股股票基础信息

一只股票通常有多个数据源文档；业务代码可能使用 `code`，标准模型使用 `symbol`。以实际文档中存在的字段为准。

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` / `code` | string | 六位股票代码；关联行情、财务和新闻 |
| `name` | string | 股票简称 |
| `exchange` / `market` | string | 交易所或市场，如 `SSE`、`SZSE`、`CN` |
| `board` | string | 板块 |
| `industry` / `industry_code` | string | 行业名称及代码 |
| `area` / `sector` | string | 地区或所属板块 |
| `list_date` | date/string | 上市日期 |
| `delist_date` | date/string/null | 退市日期 |
| `status` | string | 上市状态：`L` 上市、`D` 退市、`P` 暂停 |
| `is_hs` | boolean | 是否沪深港通标的 |
| `market_cap` / `total_mv` | number | 总市值；以实际来源单位为准 |
| `float_cap` / `circ_mv` | number | 流通市值 |
| `total_shares` / `total_share` | number | 总股本 |
| `float_shares` / `float_share` | number | 流通股本 |
| `pe`、`pb`、`turnover_rate` | number | 常用估值/交易指标（部分来源直接写在基础信息中） |
| `source` / `data_source` | string | 数据来源 |
| `created_at`、`updated_at` | date | 文档创建和更新时间 |

常用索引：`code`、`source`、`name`、`industry`、`market`、`total_mv`、`circ_mv`、`updated_at`。

### 3.2 `stock_daily_quotes`：股票历史行情

唯一业务维度为 `symbol + trade_date + data_source + period`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` / `code` | string | 股票代码 |
| `trade_date` | date/string | 交易日期 |
| `period` | string | 周期，通常为 `daily`、`weekly`、`monthly` |
| `open`、`high`、`low`、`close` | number | 开高低收价格 |
| `pre_close` | number/null | 前收盘价 |
| `change` | number | 涨跌额 |
| `pct_chg` | number | 涨跌幅（百分比） |
| `volume` / `vol` | number | 成交量；标准化服务通常转换为股 |
| `amount` / `turnover` | number | 成交额；标准化服务通常转换为元 |
| `turnover_rate` | number/null | 换手率（百分比） |
| `volume_ratio` | number/null | 量比 |
| `pe`、`pb`、`ps`、`dv_ratio`、`dv_ttm` | number/null | 估值和股息指标 |
| `total_mv`、`circ_mv` | number/null | 总市值、流通市值 |
| `adj_factor` | number/null | 复权因子 |
| `data_source` | string | 数据来源 |
| `created_at`、`updated_at` | date | 记录维护时间 |

常用索引：`(symbol, trade_date, data_source, period)` 唯一索引、`symbol`、`trade_date`、`(symbol, trade_date)`。

### 3.3 `market_quotes`、`market_quotes_hk`、`market_quotes_us`：最新行情

`market_quotes` 为 A 股主集合，港股和美股分别使用带后缀的集合。部分实时行情使用 `code`，部分历史兼容逻辑使用 `symbol`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` / `symbol` | string | 股票或 ETF 代码 |
| `name` | string | 名称 |
| `price` / `current_price` | number | 当前价 |
| `pre_close`、`open`、`high`、`low` | number | 前收、开、高、低 |
| `change`、`pct_chg` | number | 涨跌额、涨跌幅 |
| `volume`、`amount` | number | 成交量、成交额 |
| `turnover_rate` | number/null | 换手率 |
| `bid_prices`、`bid_volumes` | array[number] | 买一至买五价格和数量 |
| `ask_prices`、`ask_volumes` | array[number] | 卖一至卖五价格和数量 |
| `timestamp` / `updated_at` | date | 行情时间或更新时间 |
| `data_source` / `source` | string | 数据来源 |

`market_quotes.code` 建有唯一索引（行情采集服务）；查询最新行情时应按 `updated_at` 或 `timestamp` 校验新鲜度。

### 3.4 `etf_basic_info`、`etf_daily_quotes`：ETF 数据

字段结构分别参考 `stock_basic_info` 和 `stock_daily_quotes`，主代码字段通常为 `code`。ETF 集合还可能包含 `fund_type`、`fund_company`、`management_fee`、`tracking_index`、`nav`、`unit_nav` 等来源扩展字段。不要把 ETF 与普通股票混合统计。

### 3.5 `stock_financial_data`：财务数据快照

唯一业务维度为 `symbol + report_period + data_source`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` / `code` | string | 股票代码 |
| `report_period` | string | 报告期，通常为 `YYYYMMDD` |
| `report_type` | string | `annual` 年报或 `quarterly` 季报 |
| `ann_date`、`f_ann_date` | date/string | 公告日期、实际公告日期 |
| `balance_sheet` | object | 资产负债表，如 `total_assets`、`total_liab`、`cash_and_equivalents` |
| `income_statement` | object | 利润表，如 `revenue`、`oper_profit`、`n_income_attr_p`、`basic_eps` |
| `cashflow_statement` | object | 现金流量表，如 `n_cashflow_act`、`n_cashflow_inv_act` |
| `financial_indicators` | object | `roe`、`roa`、`gross_margin`、`net_margin`、`debt_to_assets`、`pe`、`pb` 等 |
| `data_source` / `source` | string | 数据来源 |
| `created_at`、`updated_at` | date | 维护时间 |

财务字段允许为空；AI 不应把 `null` 当作 0。`stock_financial_periods` 是按报告期展开的筛选辅助集合，字段以 `symbol`、`source`、`report_period`、`ann_date` 和展开后的财务指标为主，适合因子筛选，不应与快照集合重复计数。

### 3.6 `stock_news`：股票及市场新闻

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | string/null | 主要关联股票代码 |
| `symbols` | array[string] | 关联的多个股票代码 |
| `title` | string | 标题 |
| `content`、`summary` | string/null | 正文、摘要 |
| `url` | string | 原文链接 |
| `source` / `data_source` | string | 新闻来源/采集源 |
| `author` | string/null | 作者 |
| `publish_time` | date | 发布时间 |
| `category` | string | `company_announcement`、`industry_news`、`market_news`、`research_report` |
| `sentiment` | string/null | `positive`、`negative`、`neutral` |
| `sentiment_score` | number/null | -1 到 1 |
| `keywords` | array[string] | 关键词 |
| `importance` | string | `high`、`medium`、`low` |
| `language` | string | 默认 `zh-CN` |
| `created_at`、`updated_at` | date | 维护时间 |

唯一索引：`url + title + publish_time`。时间范围查询使用 `publish_time`，并设置结果上限。

### 3.7 `stock_technical_indicators`：技术指标

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | string | 股票代码 |
| `trade_date` | date/string | 指标日期 |
| `period` | string | 默认 `daily` |
| `ma` | object | `ma5`、`ma10`、`ma20`、`ma60` |
| `indicators` | object | `rsi`、`macd`、`macd_signal`、`macd_hist`、`kdj_k/d/j`、`boll_upper/mid/lower`、`cci`、`williams_r`、`bias`、`roc` 等 |
| `data_source`、`created_at`、`updated_at` | string/date | 来源和维护时间 |

## 4. 分析、用户和平台集合

下列集合由平台服务使用，字段可能随功能扩展；AI 查询时应先用投影限制字段，并按 `user_id` 隔离用户数据。

| 集合 | 用途 | 常用字段/关联 |
|---|---|---|
| `users` | 用户账号 | `_id`、`id`、`username`、`email`、`roles`、`created_at`；禁止返回密码哈希和令牌 |
| `user_favorites` | 用户自选股 | `user_id`、`favorites`、`updated_at` |
| `user_tags`、`watchlist_groups` | 自选股标签/分组 | `user_id`、名称、代码列表、排序字段 |
| `analysis_tasks` | 分析任务 | `task_id`、`user_id`、`status`、`symbol`、`created_at`、`result` |
| `unified_analysis_tasks` | 统一分析任务 | `task_id`、`user_id`、`status`、`created_at`、任务参数 |
| `analysis_batches` | 批量分析批次 | 批次 ID、任务列表、状态、时间字段 |
| `analysis_reports` | 分析报告 | `analysis_id`、`task_id`、`user_id`、`symbol`、`report`、`created_at` |
| `position_analysis_reports` | 持仓分析报告 | `user_id`、持仓标识、报告内容、`created_at` |
| `screening_presets` | 用户选股条件 | `user_id`、`name`、筛选条件、`created_at`、`updated_at` |
| `screening_conversations` | 智能选股会话 | `user_id`、会话 ID、消息/状态、时间字段 |
| `assistant_threads` | AI 会话主题 | `user_id`、`thread_id`、标题、状态、`created_at`、`updated_at` |
| `assistant_thread_messages` | AI 会话消息 | `thread_id`、角色、内容、序号、时间字段 |
| `assistant_thread_checkpoints` | AI 会话检查点 | `thread_id`、检查点状态、时间字段 |
| `system_configs` | 系统配置 | `config_key`、`config_value`、`is_active`、更新时间；配置值可能含敏感信息 |
| `llm_providers` | 模型供应商配置 | `name`、能力、启用状态；禁止返回 API Key |
| `workflows`、`workflow_definitions` | 工作流定义和实例 | 工作流 ID、名称、状态、节点、时间字段 |
| `scheduled_analysis_configs` | 定时分析配置 | 用户/任务、cron、启用状态 |
| `scheduler_executions`、`scheduler_history` | 调度执行记录 | 执行 ID、任务 ID、状态、开始/结束时间 |
| `operation_logs` | 操作审计日志 | 用户、动作、路径、`success`、`timestamp` |
| `token_usage` | 模型 Token 用量 | `user_id`/`session_id`、模型、Token 数、成本、时间 |
| `sync_status`、`quotes_ingestion_status` | 数据同步状态 | 任务、数据源、状态、开始/结束时间、错误信息 |
| `datasource_groupings`、`market_categories` | 数据源和市场路由 | 市场类别、数据源、优先级、启用状态 |
| `paper_accounts`、`paper_positions`、`paper_orders`、`paper_trades` | 模拟交易 | `user_id`、`code`、数量、价格、方向、状态、时间 |

## 5. 缓存和扩展集合

`cache`、`stock_data`、`news_data`、`fundamentals_data`、`financial_data_cache`、`historical_data`、`social_media_messages` 等集合用于缓存或数据源扩展。它们不是唯一事实来源，可能有过期数据、来源特有字段或不同单位。回答用户的正式行情/财务问题时，应优先使用第 3 节集合，并返回数据来源和时间。

## 6. 常用查询模板

```javascript
// 查询某股票最近 20 个交易日行情
db.stock_daily_quotes.find(
  {symbol: "000001", trade_date: {$gte: ISODate("2026-01-01")}},
  {_id: 0, symbol: 1, trade_date: 1, open: 1, high: 1, low: 1, close: 1, pct_chg: 1, data_source: 1}
).sort({trade_date: -1}).limit(20)

// 查询最新一期财务数据
db.stock_financial_data.find(
  {symbol: "000001", data_source: "tushare"},
  {_id: 0, symbol: 1, report_period: 1, report_type: 1, financial_indicators: 1, income_statement: 1}
).sort({report_period: -1}).limit(1)

// 查询最近 7 天关联股票的高重要性新闻
db.stock_news.find(
  {symbols: "000001", publish_time: {$gte: ISODate("2026-10-20")}, importance: "high"},
  {_id: 0, title: 1, summary: 1, url: 1, publish_time: 1, sentiment: 1, source: 1}
).sort({publish_time: -1}).limit(50)
```

## 7. 版本和维护

- 本字典描述的是代码层约定，不替代 MongoDB 的实际 schema validation 或索引状态。
- 新增集合、字段、索引或字段单位时，应同步更新本文档，并注明兼容的历史字段。
- 生产环境排查字段时，可使用 `db.listCollections()`、`db.<collection>.getIndexes()` 和有限样本 `findOne()`；不要把完整生产文档或凭据写入提示词、日志或报告。
