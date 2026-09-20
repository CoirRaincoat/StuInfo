"""Multi-label values, with a lossless fallback for the original group field."""
import copy


def normalize_labels(values, *, limit=200):
    if not isinstance(values, (list, tuple)) or len(values) > limit:
        raise ValueError('标签列表格式错误或数量过多')
    if any(not isinstance(value, str) or len(value) > 20000 for value in values):
        raise ValueError('标签名称格式错误或过长')
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def record_labels(record):
    """Return a fresh list; an untouched legacy group remains a single label."""
    labels = record.get('labels', [])
    if labels:
        return list(labels)
    group = record.get('group', '').strip()
    return [group] if group else []


def with_labels(record, labels):
    result = copy.deepcopy(record)
    result['labels'] = normalize_labels(labels)
    # Preserve the old field as the first-label compatibility projection.
    result['group'] = result['labels'][0] if result['labels'] else ''
    return result
