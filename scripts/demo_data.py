"""生成可重复导入的完全虚构档案；稳定 UUID，绝不自动写入用户库。"""
import io
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from friendbook.core import new_record, photo_bytes, atomic_json


def create_demo():
    rows = []
    names = ['林知夏', '陈望舒', '许星河', '周以宁', '宋清禾', '江予安', '林知夏', '苏映岚', '陆景行', '顾南枝', '温书言', '']
    colors = ['#a293b4', '#88aaa4', '#b6a077', '#809cb4']
    for i, name in enumerate(names):
        r = new_record()
        r.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'friendbook-fictional-demo/' + str(i))),
                 name=name + '（虚构）' if name else '', birth=['2002-03', '2001', '', '2003-11'][i % 4],
                 interests=['阅读、摄影', '徒步、烘焙', '绘画、电影', '编程、音乐'][i % 4],
                 contacts={'演示邮箱': f'friend{i + 1}@example.invalid'},
                 tags=[['阅读', '校园'], ['户外'], ['创作'], ['技术', '音乐']][i % 4],
                 group=['同学', '社团', '朋友'][i % 3], favorite=i in (0, 2, 4),
                 notes='这是完全虚构的演示资料，不对应真实人物。\n下次见面：交流近期读过的书。',
                 custom={'相识场景': '虚构的校园读书会', '喜欢的颜色': '紫色'} if i % 2 == 0 else {})
        if i < 5:
            img = Image.new('RGB', (240, 240), colors[i % 4])
            draw = ImageDraw.Draw(img)
            draw.ellipse((80, 42, 160, 122), fill='#eeeae5')
            draw.rounded_rectangle((48, 138, 192, 250), 60, fill='#eeeae5')
            raw = io.BytesIO()
            img.save(raw, 'PNG')
            r['photo'] = photo_bytes(raw.getvalue())
        rows.append(r)
    return dict(schema=1, active=rows, trash=[])


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'demo' / '虚构好友档案.json'
    path.parent.mkdir(exist_ok=True)
    atomic_json(path, create_demo())
    print('Created fictional demo archive (12 records).')
