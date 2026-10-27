"""Stock browsing uses stored data, independent of online provider availability."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import unittest

from app.services.stock_data_service import StockDataService


def check_list_uses_existing_source(sources, expected):
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=sources)
    cursor = collection.find.return_value
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{'code': '000001', 'name': '平安银行'}])
    with patch('app.services.stock_data_service.get_mongo_db', return_value={'stock_basic_info': collection}), patch(
        'app.core.data_source_priority.get_enabled_data_sources_async',
        new=AsyncMock(return_value=['tushare', 'akshare']),
    ):
        result = asyncio.run(StockDataService().get_stock_list(page=2, industry='银行'))
    assert result[0].symbol == '000001'
    collection.find.assert_called_once_with({'industry': '银行', 'source': expected}, {'_id': 0})
    cursor.skip.assert_called_once_with(20)
    cursor.sort.assert_called_once()


def check_database_error_is_not_empty_success():
    collection = MagicMock()
    collection.distinct = AsyncMock(side_effect=RuntimeError('database unavailable'))
    with patch('app.services.stock_data_service.get_mongo_db', return_value={'stock_basic_info': collection}), patch(
        'app.core.data_source_priority.get_enabled_data_sources_async', new=AsyncMock(return_value=['tushare']),
    ), unittest.TestCase().assertRaisesRegex(RuntimeError, 'database unavailable'):
        asyncio.run(StockDataService().get_stock_list())


def check_empty_later_page_does_not_switch_source():
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=['tushare', 'akshare'])
    cursor = collection.find.return_value
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    with patch('app.services.stock_data_service.get_mongo_db', return_value={'stock_basic_info': collection}), patch(
        'app.core.data_source_priority.get_enabled_data_sources_async', new=AsyncMock(return_value=['tushare', 'akshare']),
    ):
        assert asyncio.run(StockDataService().get_stock_list(page=100)) == []
    collection.find.assert_called_once_with({'source': 'tushare'}, {'_id': 0})


class StockDataListTests(unittest.TestCase):
    def test_sources(self):
        for sources, expected in [(['akshare'], 'akshare'), (['local'], 'local'), ([], None), (['akshare', 'tushare'], 'tushare')]:
            with self.subTest(sources=sources):
                check_list_uses_existing_source(sources, expected)

    def test_failure(self):
        check_database_error_is_not_empty_success()

    def test_pagination(self):
        check_empty_later_page_does_not_switch_source()
