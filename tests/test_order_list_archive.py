"""Arsiv kartlari: uygulamayi/gercek DB'yi acmadan liste regresyonlari.

Calistirma: python tests/test_order_list_archive.py
Kaynak fonksiyonlar AST ile yuklenir; sorgular yalniz bellek SQLite'ta calisir.
"""
import ast
import json
import logging
import math
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from flask import Flask, request
from jinja2 import Environment, select_autoescape
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy import desc, false, func, literal, nullslast, or_
from sqlalchemy.orm import aliased, declarative_base, scoped_session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = {
    'get_union_all_orders', '_with_archived_orders', '_get_sort_key', '_get_kaynak',
    '_get_per_page', '_sort_clause', '_group_sort_clause', '_normalize_details',
    '_append_details', '_page_bounds', '_merge_order_rows', '_overdue_order_numbers',
    '_decorate_order_priority', 'get_order_list', 'process_order_details',
    'get_filtered_orders', 'get_archived_order_list',
}


def load_functions(namespace):
    source = ast.parse((ROOT / 'order_list_service.py').read_text(encoding='utf-8'))
    nodes = [node for node in source.body
             if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    missing = FUNCTIONS - {node.name for node in nodes}
    if missing:
        raise AssertionError(f'Missing source functions: {sorted(missing)}')
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(ROOT / 'order_list_service.py'), 'exec'), namespace)


class OrderListArchiveTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.session = scoped_session(sessionmaker(bind=self.engine))
        self.base = declarative_base()
        self.base.query = self.session.query_property()
        self.models = {}
        for name in ('OrderCreated', 'OrderHazirlaniyor', 'OrderPicking', 'OrderShipped',
                     'OrderDelivered', 'OrderCancelled', 'Archive'):
            columns = {
                '__tablename__': name.lower(),
                'id': Column(Integer, primary_key=True),
                'order_date': Column(DateTime),
                'agreed_delivery_date': Column(DateTime),
                'estimated_delivery_end': Column(DateTime),
                'details': Column(Text),
            }
            for field in ('order_number', 'merchant_sku', 'product_barcode', 'status',
                          'cargo_provider_name', 'customer_name', 'customer_surname',
                          'customer_address', 'cargo_tracking_number', 'shipping_barcode',
                          'archive_reason', 'source'):
                columns[field] = Column(String)
            columns['archive_date'] = Column(DateTime)
            self.models[name] = type(name, (self.base,), columns)
        self.models['Product'] = type('Product', (self.base,), {
            '__tablename__': 'product', 'id': Column(Integer, primary_key=True),
            'barcode': Column(String), 'product_main_id': Column(String),
            'color': Column(String), 'size': Column(String),
        })
        self.base.metadata.create_all(self.engine)
        self.app = Flask(__name__)
        self.notes = types.ModuleType('siparis_notu')
        self.notes.get_notes_map = lambda numbers: {}
        production = types.ModuleType('uretim_modu')
        production.URETIM_DURUM_ACIKLAMASI = {}
        production.URETIM_DURUM_ETIKETI = {}
        production.uretim_durum_haritasi = lambda numbers: {}
        self.module_patch = patch.dict(sys.modules, {
            'siparis_notu': self.notes, 'uretim_modu': production,
        })
        self.module_patch.start()
        self.ns = dict(
            self.models, db=types.SimpleNamespace(session=self.session),
            literal=literal, desc=desc, or_=or_, func=func, nullslast=nullslast,
            false=false, aliased=aliased, json=json, math=math, datetime=datetime,
            request=request, logger=logging.getLogger(__name__),
            SORT_OPTIONS=('date_desc', 'deadline_asc', 'deadline_desc'),
            DEFAULT_SORT='date_desc', PER_PAGE_OPTIONS=(50, 100, 200),
            DEFAULT_PER_PAGE=50, KAYNAK_OPTIONS=('hepsi', 'trendyol', 'shopify'),
            DEFAULT_KAYNAK='hepsi',
            PRIORITY_STATUS_CODES=frozenset(('Created', 'Hazirlaniyor', 'Picking')),
            _get_overdue_orders=lambda: [], _get_order_pull_enabled=lambda: True,
            shopify_kartlari=lambda **kwargs: [],
            kartlari_sirala=lambda cards, sort: cards,
            get_product_image=lambda barcode: '/test-product.png',
            render_template=lambda template, **context: context,
            flash=lambda *args: None, url_for=lambda *args, **kwargs: '/unexpected',
            redirect=self.unexpected_redirect,
        )
        load_functions(self.ns)

    def tearDown(self):
        self.module_patch.stop()
        self.session.remove()
        self.engine.dispose()

    def unexpected_redirect(self, url):
        self.fail(f'List raised an error and redirected to {url}')

    def add(self, model, number, **values):
        fields = dict(
            order_number=number, order_date=datetime(2026, 10, 20, 12),
            customer_name='Test', customer_surname='Musteri',
            details=json.dumps([{'barcode': 'SKU-1', 'quantity': 2}]),
            status='Created',
        )
        fields.update(values)
        row = self.models[model](**fields)
        self.session.add(row)
        self.session.commit()
        return row

    def listing(self, query='', status=None):
        with self.app.test_request_context('/order-list/all' + ('?' + query if query else '')):
            if status:
                return self.ns['get_filtered_orders'](status)
            return self.ns['get_order_list']()

    def test_archive_replaces_stale_active_copy_and_preserves_details(self):
        self.add('OrderCreated', 'ARCH-1',
                 details=json.dumps([{'barcode': 'STALE', 'quantity': 99}]))
        self.add('Archive', 'ARCH-1', archive_reason='Stokta Yok/Rafta Yok',
                 shipping_barcode='CARGO-123', status='Picking',
                 agreed_delivery_date=datetime(2020, 1, 1))
        self.add('OrderDelivered', 'LIVE-2')
        result = self.listing()
        self.assertEqual(result['total_orders_count'], 2)
        cards = {card.order_number: card for card in result['orders']}
        archived = cards['ARCH-1']
        self.assertEqual(archived.status, 'Archived')
        self.assertTrue(archived.is_archived)
        self.assertEqual(archived.archive_reason, 'Stokta Yok/Rafta Yok')
        self.assertEqual(archived.cargo_tracking_number, 'CARGO-123')
        self.assertEqual([item['quantity'] for item in archived.processed_details], [2])
        self.assertFalse(archived.is_overdue)
        self.assertFalse(archived.is_urgent)
        self.assertEqual(cards['LIVE-2'].status, 'Delivered')
        self.assertFalse(cards['LIVE-2'].is_archived)

    def test_archives_take_part_in_pagination_and_more_than_five_search_results(self):
        for index in range(55):
            self.add('Archive', f'ARCH-{index:03}',
                     order_date=datetime(2026, 10, 20) - timedelta(minutes=index))
        self.add('OrderCreated', 'ACTIVE-1', order_date=datetime(2026, 10, 21))
        first = self.listing()
        second = self.listing('page=2')
        self.assertEqual(first['total_orders_count'], 56)
        self.assertEqual(first['total_pages'], 2)
        self.assertEqual(len(first['orders']), 50)
        self.assertEqual(len(second['orders']), 6)
        self.assertEqual(first['orders'][0].order_number, 'ACTIVE-1')
        self.assertFalse({o.order_number for o in first['orders']} &
                         {o.order_number for o in second['orders']})
        search = self.listing('search=ARCH-')
        self.assertEqual(search['total_orders_count'], 55)
        self.assertEqual(len(search['orders']), 50)

    def test_search_finds_archive_number_and_full_customer_name(self):
        self.add('Archive', 'ARCH-7', customer_name='Ayse', customer_surname='Kaya')
        self.add('OrderCreated', 'ACTIVE-1')
        for query in ('search=ARCH-7', 'search=Ayse+Kaya'):
            with self.subTest(query=query):
                result = self.listing(query)
                self.assertEqual([o.order_number for o in result['orders']], ['ARCH-7'])

    def test_status_search_shows_archive_without_changing_normal_status_tab(self):
        self.add('OrderCreated', 'LIVE-1', customer_name='Ortak')
        self.add('OrderShipped', 'LIVE-2', customer_name='Ortak')
        self.add('Archive', 'ARCH-1', customer_name='Ortak', status='Picking')
        normal = self.listing(status='Yeni')
        self.assertEqual([o.order_number for o in normal['orders']], ['LIVE-1'])
        search = self.listing('search=Ortak', status='Yeni')
        self.assertEqual({o.order_number for o in search['orders']}, {'LIVE-1', 'ARCH-1'})

    def test_source_filters_keep_archived_shopify_out_of_trendyol(self):
        self.add('Archive', 'TY-1', source='trendyol')
        self.add('Archive', 'SH-2', source='shopify')
        for status in (None, 'Yeni'):
            for source, expected in (('hepsi', {'TY-1', 'SH-2'}),
                                     ('trendyol', {'TY-1'}), ('shopify', {'SH-2'})):
                with self.subTest(source=source, status=status):
                    result = self.listing(f'kaynak={source}&search=Test', status=status)
                    self.assertEqual({o.order_number for o in result['orders']}, expected)

    def test_archived_status_filter_lists_only_archives(self):
        self.add('OrderCreated', 'LIVE-1')
        self.add('OrderDelivered', 'LIVE-2')
        self.add('OrderCreated', 'ARCH-1', details=json.dumps([{'barcode': 'STALE', 'quantity': 9}]))
        self.add('Archive', 'ARCH-1', customer_name='Ayse')
        self.add('Archive', 'SH-2')
        with self.app.test_request_context('/order-list/archived'):
            result = self.ns['get_archived_order_list']()
        self.assertEqual(result['active_list'], 'archived')
        self.assertEqual({o.order_number for o in result['orders']}, {'ARCH-1', 'SH-2'})
        self.assertTrue(all(o.is_archived for o in result['orders']))
        for query, expected in (('kaynak=trendyol', {'ARCH-1'}), ('kaynak=shopify', {'SH-2'}),
                                ('search=Ayse', {'ARCH-1'})):
            with self.subTest(query=query):
                with self.app.test_request_context('/order-list/archived?' + query):
                    result = self.ns['get_archived_order_list']()
                self.assertEqual({o.order_number for o in result['orders']}, expected)

    def render_card(self, card):
        source = (ROOT / 'templates/order_list.html').read_text(encoding='utf-8')
        start = source.index('{% macro order_card(')
        end = source.index('{% endmacro %}', start) + len('{% endmacro %}')
        env = Environment(autoescape=select_autoescape(default=True))
        env.filters['ist'] = lambda value, fmt: value.strftime(fmt)
        env.globals.update(
            url_for=lambda endpoint, **params: '/' + endpoint + '?' + urlencode(params),
            kargo_rozet=lambda *args: '',
        )
        return str(env.from_string(source[start:end]).module.order_card(card, 'test'))

    def test_archive_card_shows_reason_and_keeps_live_order_actions_off(self):
        self.add('Archive', 'ARCH-1', archive_reason='<script>reason</script>')
        card = self.listing()['orders'][0]
        html = self.render_card(card)
        self.assertIn('Arşivde', html)
        self.assertIn('&lt;script&gt;reason&lt;/script&gt;', html)
        self.assertNotIn('<script>reason</script>', html)
        self.assertIn('archive.display_archive?search=ARCH-1', html)
        self.assertNotIn('order_list_service.order_label', html)
        self.assertNotIn('kargo-sec-cb', html)
        self.assertNotIn('showArchiveModal', html)

    def test_active_card_keeps_print_archive_and_cargo_actions(self):
        self.add('OrderCreated', 'LIVE-1')
        html = self.render_card(self.listing()['orders'][0])
        self.assertIn('order_list_service.order_label', html)
        self.assertIn('kargo-sec-cb', html)
        self.assertIn('showArchiveModal', html)
        self.assertNotIn('archive.display_archive', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
