from datetime import date
import pytest
from friendbook.core import Store, new_record
from friendbook.labels import with_labels
from friendbook.analytics import AGE_ORDER, QUALITY_CHECKS


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / 'analytics.sqlite3')
    yield store
    store.close()


def test_drilldown_matches_all_metric_counts_and_preserves_order(store):
    today = date(2026, 9, 27)
    for index, birth in enumerate(('', '2008', '2008-09', '2008-08', '1990-12', '1966-01')):
        record = new_record()
        record.update(name=f'虚构 {index}', birth=birth,
                      interests='阅读、摄影，阅读' if index % 2 else '', favorite=True)
        record = with_labels(record, ['（未标记）', '同学'] if index % 2 else [])
        store.save(record)
    store.create_label('空标签')
    gone = new_record()
    gone.update(name='仅在回收站', birth='2000-09', interests='不应出现')
    store.save(gone)
    store.delete(gone['id'])
    before = store.payload()
    data = store.overview(today)
    ids = [r['id'] for r in store.records()]
    dimensions = {'标签': data['groups'], '年龄': data['ages'], '兴趣': data['interests'],
                  '生日月份': dict(data['months'])}
    dimensions['生日月份'][None] = data['month_unknown']
    dimensions['资料检查'] = store.quality_overview()
    for dimension, counts in dimensions.items():
        for category, count in counts.items():
            records = store.statistics_records(dimension, category, today)
            assert len(records) == count
            found = [r['id'] for r in records]
            assert found == [uid for uid in ids if uid in found]
            for record in records:
                record['name'] = '仅修改返回副本'
    assert store.payload() == before
    assert len(store.statistics_records('标签', '（未标记）')) == 3
    assert len(store.statistics_records('标签', '')) == 3


def test_unknown_fields_are_gaps_not_fabricated_values(store):
    record = new_record()
    record.update(contacts={'电话': '  '}, interests='，;、', birth='2000')
    store.save(record)
    checks = store.quality_overview()
    assert checks['birth_year'] == 0 and checks['birth_month'] == 1
    assert checks['contacts'] == checks['interests'] == checks['name'] == 1
    assert store.record(record['id'])['birth'] == '2000'
    assert not store.statistics_records('生日月份', 1)
    assert len(store.statistics_records('生日月份', None)) == 1


def test_empty_metrics_have_zero_counts_and_no_fake_friends(store):
    assert store.quality_overview() == {key: 0 for key, _ in QUALITY_CHECKS}
    for category in AGE_ORDER:
        assert not store.statistics_records('年龄', category)
