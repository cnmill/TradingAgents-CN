#!/usr/bin/env python3
"""
数据时效性检查脚本
用于快速识别最新（当日）数据是否已经入库

Usage:
    python scripts/check_data_freshness.py
    python scripts/check_data_freshness.py --detailed
    python scripts/check_data_freshness.py --stock 600487.SH
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from pymongo import MongoClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

console = Console()


def get_mongodb_client():
    """获取 MongoDB 客户端"""
    try:
        client = MongoClient('localhost', 27017, serverSelectionTimeoutMS=2000)
        # 测试连接
        client.server_info()
        return client
    except Exception as e:
        console.print(f"[red]❌ MongoDB 连接失败: {e}[/red]")
        sys.exit(1)


def get_latest_trading_date() -> str:
    """
    获取最新交易日
    规则：
    - 周一 ~ 周五: 当日
    - 周六: 上周五
    - 周日: 上周五
    """
    today = datetime.now()
    weekday = today.weekday()
    
    # 周六（5）回退1天，周日（6）回退2天
    if weekday == 5:  # 周六
        latest = today - timedelta(days=1)
    elif weekday == 6:  # 周日
        latest = today - timedelta(days=2)
    else:  # 周一到周五
        # 如果是工作日的上午 < 15:30，可能还没收盘，返回前一交易日
        if today.hour < 15 or (today.hour == 15 and today.minute < 30):
            if weekday == 0:  # 周一早盘，回退到上周五
                latest = today - timedelta(days=3)
            else:
                latest = today - timedelta(days=1)
        else:
            latest = today
    
    return latest.strftime('%Y-%m-%d')


def check_stock_daily_quotes(db) -> Dict:
    """检查日线行情数据"""
    collection = db['stock_daily_quotes']
    
    # 查询最近5天的数据分布
    pipeline = [
        {'$group': {'_id': '$trade_date', 'count': {'$sum': 1}}},
        {'$sort': {'_id': -1}},
        {'$limit': 5}
    ]
    
    results = list(collection.aggregate(pipeline))
    
    if not results:
        return {'status': 'empty', 'latest_date': None, 'count': 0, 'recent_dates': []}
    
    latest = results[0]
    expected_date = get_latest_trading_date()
    
    return {
        'status': 'fresh' if latest['_id'] == expected_date else 'stale',
        'latest_date': latest['_id'],
        'count': latest['count'],
        'expected_date': expected_date,
        'recent_dates': [(r['_id'], r['count']) for r in results]
    }


def check_stock_basic_info(db) -> Dict:
    """检查基本信息更新时间"""
    collection = db['stock_basic_info']
    
    # 统计总数
    total_count = collection.count_documents({})
    
    # 查询最近更新时间（假设有 updated_at 字段）
    sample = collection.find_one({}, sort=[('updated_at', -1)])
    
    if sample and 'updated_at' in sample:
        latest_update = sample['updated_at']
        if isinstance(latest_update, str):
            latest_update = datetime.fromisoformat(latest_update.replace('Z', '+00:00'))
        
        # 检查是否在最近7天内更新
        is_fresh = (datetime.now() - latest_update).days <= 7
        
        return {
            'status': 'fresh' if is_fresh else 'stale',
            'total_count': total_count,
            'latest_update': latest_update.strftime('%Y-%m-%d %H:%M:%S') if hasattr(latest_update, 'strftime') else str(latest_update)
        }
    else:
        return {
            'status': 'unknown',
            'total_count': total_count,
            'latest_update': '未知'
        }


def check_stock_news(db) -> Dict:
    """检查新闻数据"""
    collection = db['stock_news']
    
    total_count = collection.count_documents({})
    
    # 查询最新新闻时间
    sample = collection.find_one({}, sort=[('publish_time', -1)])
    
    if sample and 'publish_time' in sample:
        latest_time = sample['publish_time']
        if isinstance(latest_time, str):
            latest_time = datetime.fromisoformat(latest_time.replace('Z', '+00:00'))
        
        # 检查是否今日新闻
        is_today = latest_time.date() == datetime.now().date()
        
        return {
            'status': 'fresh' if is_today else 'stale',
            'total_count': total_count,
            'latest_time': latest_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(latest_time, 'strftime') else str(latest_time)
        }
    else:
        return {
            'status': 'unknown',
            'total_count': total_count,
            'latest_time': '未知'
        }


def check_specific_stock(db, symbol: str) -> Dict:
    """检查特定股票的数据"""
    collection = db['stock_daily_quotes']
    
    # 查询该股票最近5天数据
    quotes = list(collection.find(
        {'full_symbol': symbol},
        {'trade_date': 1, 'close': 1, 'pct_chg': 1, 'amount': 1, '_id': 0}
    ).sort('trade_date', -1).limit(5))
    
    if not quotes:
        return {'status': 'not_found', 'symbol': symbol, 'quotes': []}
    
    latest_date = quotes[0]['trade_date']
    expected_date = get_latest_trading_date()
    
    return {
        'status': 'fresh' if latest_date == expected_date else 'stale',
        'symbol': symbol,
        'latest_date': latest_date,
        'expected_date': expected_date,
        'quotes': quotes
    }


def display_summary(results: Dict):
    """显示汇总信息"""
    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]TradingAgents-CN 数据时效性检查[/bold cyan]",
        border_style="cyan"
    ))
    
    # 创建汇总表格
    table = Table(title="数据集汇总", box=box.ROUNDED)
    table.add_column("数据集", style="cyan", no_wrap=True)
    table.add_column("状态", style="bold")
    table.add_column("最新日期/更新时间", style="yellow")
    table.add_column("记录数", justify="right", style="magenta")
    
    # 日线行情
    quotes = results['quotes']
    status_emoji = "✅" if quotes['status'] == 'fresh' else "⚠️"
    status_text = f"{status_emoji} {'最新' if quotes['status'] == 'fresh' else '待更新'}"
    table.add_row(
        "日线行情 (stock_daily_quotes)",
        status_text,
        f"{quotes['latest_date']} (预期: {quotes['expected_date']})",
        f"{quotes['count']:,}"
    )
    
    # 基本信息
    basic = results['basic']
    status_emoji = "✅" if basic['status'] == 'fresh' else "⚠️"
    status_text = f"{status_emoji} {'最新' if basic['status'] == 'fresh' else '待更新'}"
    table.add_row(
        "基本信息 (stock_basic_info)",
        status_text,
        basic.get('latest_update', '未知'),
        f"{basic['total_count']:,}"
    )
    
    # 新闻数据
    news = results['news']
    status_emoji = "✅" if news['status'] == 'fresh' else "⚠️"
    status_text = f"{status_emoji} {'最新' if news['status'] == 'fresh' else '待更新'}"
    table.add_row(
        "新闻资讯 (stock_news)",
        status_text,
        news.get('latest_time', '未知'),
        f"{news['total_count']:,}"
    )
    
    console.print(table)
    
    # 显示最近5天数据分布
    if quotes['recent_dates']:
        console.print("\n[bold cyan]最近5个交易日数据分布:[/bold cyan]")
        for date, count in quotes['recent_dates']:
            bar = "█" * (count // 100)
            console.print(f"  {date}: [green]{bar}[/green] {count:,} 只")


def display_detailed(results: Dict):
    """显示详细信息"""
    display_summary(results)
    
    # 额外显示详细统计
    quotes = results['quotes']
    
    console.print("\n[bold cyan]数据时效性判断:[/bold cyan]")
    
    now = datetime.now()
    expected = get_latest_trading_date()
    
    console.print(f"  当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  预期最新交易日: [yellow]{expected}[/yellow]")
    console.print(f"  实际最新日期: [yellow]{quotes['latest_date']}[/yellow]")
    
    if quotes['status'] == 'fresh':
        console.print(f"  [green]✅ 数据已是最新！[/green]")
    else:
        console.print(f"  [red]⚠️  数据需要更新[/red]")
        console.print(f"  建议执行: [cyan]python -m scripts.sync_daily_quotes[/cyan]")


def display_stock_detail(result: Dict):
    """显示特定股票详情"""
    console.print("\n")
    
    if result['status'] == 'not_found':
        console.print(f"[red]❌ 未找到股票: {result['symbol']}[/red]")
        return
    
    console.print(Panel.fit(
        f"[bold cyan]股票数据检查: {result['symbol']}[/bold cyan]",
        border_style="cyan"
    ))
    
    # 创建表格
    table = Table(title=f"最近5个交易日", box=box.ROUNDED)
    table.add_column("日期", style="cyan")
    table.add_column("收盘价", justify="right", style="yellow")
    table.add_column("涨跌幅", justify="right", style="bold")
    table.add_column("成交额", justify="right", style="magenta")
    
    for quote in result['quotes']:
        pct = quote.get('pct_chg', 0)
        pct_style = "red" if pct < 0 else "green"
        
        table.add_row(
            quote['trade_date'],
            f"{quote.get('close', 0):.2f}",
            f"[{pct_style}]{pct:+.2f}%[/{pct_style}]",
            f"{quote.get('amount', 0) / 10000:.2f} 万元"
        )
    
    console.print(table)
    
    # 数据时效性
    status_emoji = "✅" if result['status'] == 'fresh' else "⚠️"
    status_text = "数据已是最新" if result['status'] == 'fresh' else "数据需要更新"
    console.print(f"\n{status_emoji} {status_text}")
    console.print(f"  最新日期: [yellow]{result['latest_date']}[/yellow]")
    console.print(f"  预期日期: [yellow]{result['expected_date']}[/yellow]")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='检查 TradingAgents-CN 数据时效性')
    parser.add_argument('--detailed', '-d', action='store_true', help='显示详细信息')
    parser.add_argument('--stock', '-s', type=str, help='检查特定股票（如: 600487.SH）')
    
    args = parser.parse_args()
    
    # 连接数据库
    client = get_mongodb_client()
    db = client['tradingagentscn_v0_mac']
    
    if args.stock:
        # 检查特定股票
        result = check_specific_stock(db, args.stock)
        display_stock_detail(result)
    else:
        # 检查所有数据集
        results = {
            'quotes': check_stock_daily_quotes(db),
            'basic': check_stock_basic_info(db),
            'news': check_stock_news(db)
        }
        
        if args.detailed:
            display_detailed(results)
        else:
            display_summary(results)
    
    console.print("\n")


if __name__ == '__main__':
    main()
