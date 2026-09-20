import base64
import copy
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime
from collections import Counter
from PIL import Image, ImageOps
from .linked import LinkedBook

MAX_FILE = 100 * 1024 * 1024


def new_record():
    return dict(id=str(uuid.uuid4()), version=1, name='', birth='', interests='',
                contacts={}, tags=[], group='', favorite=False, notes='', custom={}, photo='')


def photo_bytes(raw):
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError('照片不能超过 15 MB')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 30_000_000:
                raise ValueError('照片像素过大')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1000, 1000))
            output = io.BytesIO()
            image.save(output, 'JPEG', quality=88)
            return base64.b64encode(output.getvalue()).decode('ascii')
    except Exception as exc:
        raise ValueError('照片无法读取或已损坏，请选择有效图片') from exc


def validate_record(record):
    if not isinstance(record, dict) or set(record) != set(new_record()):
        raise ValueError('档案字段不完整或格式版本不兼容')
    r = copy.deepcopy(record)
    try:
        uuid.UUID(r['id'])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('无效的内部 ID') from exc
    if type(r['version']) is not int or r['version'] < 1 or type(r['favorite']) is not bool:
        raise ValueError('无效的版本号或收藏状态')
    for key in ('name', 'birth', 'interests', 'group', 'notes', 'photo'):
        if not isinstance(r[key], str) or len(r[key]) > (4_000_000 if key == 'photo' else 20000):
            raise ValueError('文本内容格式错误或过长')
        if key != 'photo':
            r[key] = r[key].strip()
    if r['birth']:
        if not re.fullmatch(r'\d{4}(-\d{2})?', r['birth']):
            raise ValueError('出生年月请填 YYYY 或 YYYY-MM，未知请留空')
        year = int(r['birth'][:4])
        month = int(r['birth'][5:]) if len(r['birth']) > 4 else None
        if not 1 <= year <= datetime.now().year or (month is not None and not 1 <= month <= 12):
            raise ValueError('出生年月超出有效范围')
        if r['birth'] > datetime.now().strftime('%Y-%m'):
            raise ValueError('出生年月不能在未来')
    for key in ('contacts', 'custom'):
        if not isinstance(r[key], dict) or len(r[key]) > 200:
            raise ValueError('属性应为键值对，最多 200 项')
        if any(not isinstance(k, str) or not k.strip() or not isinstance(v, str)
               or len(k) > 200 or len(v) > 20000 for k, v in r[key].items()):
            raise ValueError('属性名称不能为空，属性内容应为文本')
    if not isinstance(r['tags'], list) or len(r['tags']) > 200 or any(
            not isinstance(t, str) or len(t) > 200 for t in r['tags']):
        raise ValueError('标签格式错误')
    r['tags'] = list(dict.fromkeys(t.strip() for t in r['tags'] if t.strip()))
    if r['photo']:
        try:
            raw = base64.b64decode(r['photo'], validate=True)
            with Image.open(io.BytesIO(raw)) as im:
                if im.width * im.height > 30_000_000:
                    raise ValueError()
                im.verify()
        except Exception as exc:
            raise ValueError('档案中的照片已损坏') from exc
    return r


def atomic_json(path, payload):
    path = Path(path)
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded.encode('utf-8')) > MAX_FILE:
        raise ValueError('档案总大小超过 100 MB，请缩减照片或档案数量')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.friendbook-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    """所有变更先在候选链表完成，磁盘提交成功后才发布新内存状态。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.execute('PRAGMA synchronous=FULL')
        if self.db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('数据库检查失败，请保留原文件并从备份恢复')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        self.db.execute("INSERT OR IGNORE INTO state VALUES (1,0,?)", (json.dumps(dict(schema=1, active=[], trash=[])),))
        self.db.commit()
        self.reload()

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or type(payload.get('schema')) is not int or payload.get('schema') != 1:
            raise ValueError('不支持的文件版本')
        book = LinkedBook()
        trash = {}
        for key in ('active', 'trash'):
            if not isinstance(payload.get(key), list) or len(payload[key]) > 50000:
                raise ValueError('档案集合格式错误或过大')
        for raw in payload['active']:
            book.insert(validate_record(raw))
        for raw in payload['trash']:
            r = validate_record(raw)
            if r['id'] in book.index or r['id'] in trash:
                raise ValueError('文件含重复内部 ID')
            trash[r['id']] = r
        book.validate()
        return book, trash

    def reload(self):
        rev, raw = self.db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
        book, trash = self.decode(json.loads(raw))
        self.book, self.trash, self.revision = book, trash, rev

    def payload(self):
        return dict(schema=1, active=list(self.book), trash=list(self.trash.values()))

    def change(self, operation):
        book = LinkedBook()
        for record in self.book:
            book.insert(copy.deepcopy(record))
        trash = copy.deepcopy(self.trash)
        result = operation(book, trash)
        book.validate()
        payload = json.dumps(dict(schema=1, active=list(book), trash=list(trash.values())), ensure_ascii=False)
        if len(book) > 50000 or len(trash) > 50000 or len(payload.encode('utf-8')) > MAX_FILE:
            raise ValueError('档案超过容量限制（单集合 50000 份、完整数据 100 MB），本次变更未保存')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            cursor = self.db.execute('UPDATE state SET revision=revision+1,payload=? WHERE id=1 AND revision=?', (payload, self.revision))
            if cursor.rowcount != 1:
                raise ValueError('数据已被另一窗口修改，请刷新后重新编辑')
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.book, self.trash = book, trash
        self.revision += 1
        return result

    def save(self, record, anchor=None, before=False, expected=None):
        r = validate_record(record)
        def op(book, trash):
            if r['id'] in trash:
                raise ValueError('该档案已在回收站，请先还原')
            if expected is not None:
                if r['id'] not in book.index or book.get(r['id'])['version'] != expected:
                    raise ValueError('档案已发生变化，请重新打开编辑')
                r['version'] = expected + 1
                book.update(r['id'], r)
            else:
                book.insert(r, anchor, before)
        self.change(op)

    def delete(self, uid):
        self.change(lambda b, t: t.update({uid: b.remove(uid)}))

    def restore_item(self, uid):
        self.change(lambda b, t: b.insert(t.pop(uid)))

    def purge(self, uid):
        self.change(lambda b, t: t.pop(uid))

    def move(self, uid, anchor, before=False):
        self.change(lambda b, t: b.move(uid, anchor, before))

    def search(self, query='', group='', tag='', favorites=False):
        terms = query.casefold().split()
        for r in self.book:
            text = ' '.join(str(r[k]) for k in ('name', 'birth', 'interests', 'contacts', 'tags', 'notes', 'custom', 'group')).casefold()
            if all(term in text for term in terms) and (not group or group == r['group']) and (
                    not tag or tag.casefold() in (t.casefold() for t in r['tags'])) and (not favorites or r['favorite']):
                yield r

    def duplicates(self, record):
        contacts = {v.strip().casefold() for v in record['contacts'].values() if v.strip()}
        for r in self.book:
            if r['id'] != record['id'] and ((record['name'] and r['name'].casefold() == record['name'].casefold()) or
                    contacts.intersection(v.strip().casefold() for v in r['contacts'].values() if v.strip())):
                yield r

    def merge(self, keep, source, merged, expected):
        r = validate_record(merged)
        if keep == source or r['id'] != keep:
            raise ValueError('合并对象无效')
        def op(book, trash):
            if book.get(keep)['version'] != expected:
                raise ValueError('保留档案已修改，请重新合并')
            r['version'] = expected + 1
            book.update(keep, r)
            trash[source] = book.remove(source)
        self.change(op)

    def export(self, path, backup=False):
        self._safe_destination(path)
        data = self.payload()
        if not backup:
            data['trash'] = []
        atomic_json(path, data)

    def _safe_destination(self, path):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('不能覆盖正在使用的数据库')

    @staticmethod
    def read_archive(path):
        if Path(path).stat().st_size > MAX_FILE:
            raise ValueError('文件超过 100 MB 限制')
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('JSON 文件存在重复字段，请修正后导入')
                result[key] = value
            return result
        with open(path, encoding='utf-8-sig') as stream:
            payload = json.load(stream, object_pairs_hook=unique_object)
        return Store.decode(payload)

    def import_file(self, path):
        incoming, _ = self.read_archive(path)
        def op(book, trash):
            added = skipped = 0
            for r in incoming:
                if r['id'] in book.index or r['id'] in trash:
                    skipped += 1
                else:
                    book.insert(r)
                    added += 1
            return added, skipped
        return self.change(op)

    def recover(self, path):
        incoming, removed = self.read_archive(path)
        safety = self.path.parent / ('恢复前备份-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        self.export(safety, backup=True)
        def op(book, trash):
            while book.head:
                book.remove(book.head.data['id'])
            for r in incoming:
                book.insert(r)
            trash.clear()
            trash.update(removed)
        self.change(op)
        return safety

    def close(self):
        self.db.close()

    # UI-facing read/command boundary. No widget needs to inspect mutable nodes.
    def records(self, query='', group=None, tag='', favorites=False, trash=False):
        if trash:
            terms = query.casefold().split()
            source = (r for r in self.trash.values() if all(
                term in (r['name'] + ' ' + r['notes']).casefold() for term in terms))
        else:
            source = self.search(query, group or '', tag, favorites)
        return [copy.deepcopy(r) for r in source if trash or group is None or r['group'] == group]

    def record(self, uid, trash=False):
        return copy.deepcopy(self.trash[uid] if trash else self.book.get(uid))

    def counts(self):
        return len(self.book), len(self.trash)

    def group_counts(self):
        return Counter(r['group'] for r in self.book)

    def duplicate_records(self, record):
        return [copy.deepcopy(r) for r in self.duplicates(record)]

    def move_relative(self, uid, direction):
        if direction not in (-1, 1):
            raise ValueError('移动方向无效')
        node = self.book.index[uid]
        neighbor = node.prev if direction < 0 else node.next
        if neighbor:
            self.move(uid, neighbor.data['id'], direction < 0)

    def rename_group(self, old, new):
        new = new.strip()
        if len(new) > 20000:
            raise ValueError('分组名称过长')
        def op(book, trash):
            count = 0
            for r in book:
                if r['group'] == old:
                    book.update(r['id'], dict(r, group=new, version=r['version'] + 1))
                    count += 1
            return count
        return self.change(op)

    def connection_rows(self):
        rows = []
        node = self.book.head
        while node:
            rows.append((node.prev.data['id'] if node.prev else None,
                         node.data['id'], node.data['name'],
                         node.next.data['id'] if node.next else None))
            node = node.next
        return rows

    def adopt(self, book, trash, revision):
        """Publish a validated worker snapshot after its connection has closed."""
        self.book, self.trash, self.revision = book, trash, revision

    def preview_import(self, path):
        incoming, _ = self.read_archive(path)
        records = list(incoming)
        skipped = sum(r['id'] in self.book.index or r['id'] in self.trash for r in records)
        return dict(records=records, total=len(records), skipped=skipped)

    def import_prepared(self, records):
        # A preview is an external input buffer, never the runtime collection.
        incoming, _ = self.decode(dict(schema=1, active=records, trash=[]))
        def op(book, trash):
            added = skipped = 0
            for r in incoming:
                if r['id'] in book.index or r['id'] in trash:
                    skipped += 1
                else:
                    book.insert(r)
                    added += 1
            return added, skipped
        return self.change(op)

    def overview(self, today=None):
        today = today or datetime.now().date()
        groups, interests, months, ages = Counter(), Counter(), Counter(), Counter()
        birthdays = []
        favorites = birth_unknown = month_unknown = interests_unknown = 0
        age_bands = ((0, 17, '0–17 岁'), (18, 29, '18–29 岁'), (30, 44, '30–44 岁'),
                     (45, 59, '45–59 岁'), (60, 10000, '60 岁及以上'))
        for r in self.book:
            groups[r['group']] += 1
            favorites += r['favorite']
            tokens = {t.strip() for t in re.split(r'[,，、;；\n]+', r['interests']) if t.strip()}
            interests.update(tokens)
            interests_unknown += not tokens
            birth = r['birth']
            if not birth:
                birth_unknown += 1
                month_unknown += 1
                ages['出生年份未知'] += 1
                continue
            base = today.year - int(birth[:4])
            low, high = max(0, base - 1), base
            if len(birth) == 7:
                month = int(birth[5:])
                months[month] += 1
                if month == today.month:
                    birthdays.append(dict(id=r['id'], name=r['name'], birth=birth, group=r['group']))
                elif month < today.month:
                    low = high = base
                else:
                    low = high = max(0, base - 1)
            else:
                month_unknown += 1
            band = next((label for lower, upper, label in age_bands if lower <= low <= high <= upper), '年龄段不确定')
            ages[band] += 1
        return dict(total=len(self.book), trash=len(self.trash), favorites=favorites,
                    groups=groups, interests=interests, months=months, ages=ages,
                    birthdays=birthdays, birth_unknown=birth_unknown, month_unknown=month_unknown,
                    interests_unknown=interests_unknown)
