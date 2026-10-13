"""A readable image header is insufficient for safely accepting an archive."""
import base64
import io

import pytest
from PIL import Image

from friendbook.core import Store, atomic_json, new_record, validate_record


@pytest.fixture
def jpeg_bytes():
    output = io.BytesIO()
    Image.effect_noise((128, 128), 100).convert('RGB').save(output, 'JPEG')
    return output.getvalue()


def photo_record(raw):
    return dict(new_record(), name='虚构照片演示',
                photo=base64.b64encode(raw).decode('ascii'))


def test_truncated_jpeg_with_valid_header_is_rejected(jpeg_bytes):
    truncated = jpeg_bytes[:len(jpeg_bytes) // 2]
    # This is the prior loophole: verify() alone accepts this broken pixel data.
    with Image.open(io.BytesIO(truncated)) as image:
        image.verify()
    with pytest.raises(ValueError, match='照片已损坏'):
        validate_record(photo_record(truncated))


def test_validation_keeps_original_image_bytes(jpeg_bytes):
    record = photo_record(jpeg_bytes)
    assert validate_record(record)['photo'] == record['photo']


@pytest.mark.parametrize('operation', ['import_file', 'recover'])
def test_corrupt_photo_archive_never_partially_replaces_data(tmp_path, jpeg_bytes, operation):
    store = Store(tmp_path / 'friends.sqlite3')
    try:
        store.save(photo_record(jpeg_bytes))
        before = store.payload()
        revision = store.revision
        archive = tmp_path / 'broken.json'
        broken = photo_record(jpeg_bytes[:len(jpeg_bytes) // 2])
        atomic_json(archive, dict(schema=1, active=[new_record(), broken], trash=[]))
        with pytest.raises(ValueError, match='照片已损坏'):
            getattr(store, operation)(archive)
        assert store.payload() == before
        assert store.revision == revision
        store.reload()
        assert store.payload() == before
        assert store.revision == revision
    finally:
        store.close()
