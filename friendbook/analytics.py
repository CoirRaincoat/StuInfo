"""Shared statistical definitions; incomplete dates stay incomplete."""
import re
from .labels import record_labels


AGE_BANDS = ((0, 17, '0–17 岁'), (18, 29, '18–29 岁'), (30, 44, '30–44 岁'),
             (45, 59, '45–59 岁'), (60, 10000, '60 岁及以上'))
AGE_ORDER = [band[2] for band in AGE_BANDS] + ['年龄段不确定', '出生年份未知']
QUALITY_CHECKS = (
    ('name', '未填写姓名'), ('birth_year', '出生年份未知'),
    ('birth_month', '出生月份未知'), ('contacts', '未填写联系方式'),
    ('interests', '未填写兴趣'), ('labels', '未设置标签'), ('photo', '未设置照片'))


def interest_tokens(record):
    return {text.strip() for text in re.split(r'[,，、;；\n]+', record['interests']) if text.strip()}


def age_category(record, today):
    birth = record['birth']
    if not birth:
        return '出生年份未知'
    base = today.year - int(birth[:4])
    low, high = max(0, base - 1), base
    if len(birth) == 7:
        month = int(birth[5:])
        if month < today.month:
            low = high = base
        elif month > today.month:
            low = high = max(0, base - 1)
    return next((name for lower, upper, name in AGE_BANDS if lower <= low <= high <= upper),
                '年龄段不确定')


def missing_fields(record):
    """These are optional information gaps, not errors or a completeness score."""
    checks = {
        'name': not record['name'].strip(),
        'birth_year': not record['birth'],
        'birth_month': len(record['birth']) != 7,
        'contacts': not any(value.strip() for value in record['contacts'].values()),
        'interests': not interest_tokens(record),
        'labels': not record_labels(record),
        'photo': not record['photo'],
    }
    return {key for key, missing in checks.items() if missing}


def matches_category(record, dimension, category, today):
    if dimension == '标签':
        labels = record_labels(record)
        return not labels if category == '' else category in labels
    if dimension == '兴趣':
        return category in interest_tokens(record)
    if dimension == '年龄':
        return age_category(record, today) == category
    if dimension == '生日月份':
        birth = record['birth']
        return len(birth) != 7 if category is None else len(birth) == 7 and int(birth[5:]) == category
    if dimension == '资料检查':
        return category in missing_fields(record)
    raise ValueError('未知的统计维度')
