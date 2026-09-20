"""Presentation categories over schema-1 contacts; legacy labels remain lossless."""
import re

CONTACT_KINDS = ('电话', 'QQ', '微信', '邮箱', '其他')
PROFILE_FIELDS = ('籍贯', '现居地', '学校 / 单位', '职业')
_PATTERNS = {
    '电话': r'(?:电话|手机|手机号码|联系电话|工作电话|家庭电话|tel|phone)\s*\d*',
    'QQ': r'QQ(?:号|号码)?\s*\d*',
    '微信': r'(?:微信|微信号|wechat)\s*\d*',
    '邮箱': r'(?:邮箱|电子邮箱|电子邮件|email|e-mail)\s*\d*',
}


def contact_kind(name):
    return next((kind for kind, pattern in _PATTERNS.items()
                 if re.fullmatch(pattern, name.strip(), re.IGNORECASE)), '其他')


def grouped_contacts(values):
    groups = {kind: [] for kind in CONTACT_KINDS}
    for name, value in values.items():
        groups[contact_kind(name)].append((name, value))
    return groups


def contact_caption(kind, index, count, original=''):
    canonical = re.fullmatch(re.escape(kind) + r'\s*\d*', original, re.IGNORECASE)
    if original and not canonical:
        return original
    return kind + (str(index + 1) if count > 1 else '')
