from datetime import date
from friendbook.core import Store, new_record


def test_unknowns_and_age_ranges(tmp_path):
    store = Store(tmp_path / 'db.sqlite3')
    for birth in ['', '2000', '2000-09', '1996', '1996-10', '1996-08']:
        record = new_record()
        record.update(birth=birth, interests='阅读、阅读, 摄影', group='自定义')
        store.save(record)
    stats = store.overview(date(2026, 9, 20))
    assert stats['total'] == 6
    assert stats['birth_unknown'] == 1 and stats['month_unknown'] == 3
    assert stats['ages']['出生年份未知'] == 1
    assert stats['ages']['年龄段不确定'] == 1  # 1996 year only: 29 or 30
    assert stats['ages']['18–29 岁'] == 3
    assert stats['ages']['30–44 岁'] == 1
    assert len(stats['birthdays']) == 1
    assert stats['interests']['阅读'] == 6
    assert sum(stats['ages'].values()) == stats['total']
    store.close()


def test_group_commands_and_copy_boundary(tmp_path):
    store = Store(tmp_path / 'db.sqlite3')
    a, b = new_record(), new_record()
    a.update(group='全部分组', custom={'key': 'unchanged'})
    store.save(a)
    store.save(b)
    assert len(store.records(group='全部分组')) == 1
    assert len(store.records(group='')) == 1
    assert len(store.records()) == 2
    copy = store.record(a['id'])
    copy['custom']['key'] = 'changed'
    assert store.record(a['id'])['custom']['key'] == 'unchanged'
    order = [r['id'] for r in store.records()]
    assert store.rename_group('全部分组', '新分组') == 1
    assert store.record(a['id'])['version'] == 2
    assert [r['id'] for r in store.records()] == order
    store.move_relative(a['id'], 1)
    assert [r['id'] for r in store.records()] == order[::-1]
    store.close()
