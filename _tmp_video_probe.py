import os
import mimetypes
import sqlite3
import struct

p = r'C:\Users\xhang\OneDrive\Desktop\Olatricity\static\uploads\homepage\videos\5d4add1e835c4bcfb3bc2730fb642237.mov'
print('exists', os.path.isfile(p))
print('size_mb', round(os.path.getsize(p) / 1024 / 1024, 2) if os.path.isfile(p) else None)
print('guess', mimetypes.guess_type(p))
print('mov', mimetypes.guess_type('x.mov'))
print('mp4', mimetypes.guess_type('x.mp4'))
print('m4v', mimetypes.guess_type('x.m4v'))

# Peek ISO/QuickTime box types
if os.path.isfile(p):
    with open(p, 'rb') as f:
        head = f.read(64)
    print('head_hex', head[:32].hex())
    print('head_ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in head[:64]))

    fsize = os.path.getsize(p)
    with open(p, 'rb') as f:
        codecs = []
        brands = []
        offset = 0
        while offset + 8 <= fsize and offset < 2_000_000:
            f.seek(offset)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size = struct.unpack('>I', hdr[:4])[0]
            typ = hdr[4:8]
            if size == 1:
                ext = f.read(8)
                if len(ext) < 8:
                    break
                size = struct.unpack('>Q', ext)[0]
                hdr_len = 16
            elif size == 0:
                size = fsize - offset
                hdr_len = 8
            else:
                hdr_len = 8
            if size < hdr_len:
                break
            if typ == b'ftyp':
                payload = f.read(min(size - hdr_len, 32))
                brands.append(payload[:4])
                print('ftyp', payload)
            if typ in (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'stsd'):
                print('box', typ, 'size', size, 'at', offset)
            if typ == b'stsd':
                payload = f.read(min(size - hdr_len, 200))
                print('stsd_ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in payload))
            # walk children of container boxes
            if typ in (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'udta', b'meta'):
                offset += hdr_len
                continue
            if size <= 0:
                break
            offset += size
        print('brands', brands)

db = r'C:\Users\xhang\OneDrive\Desktop\Olatricity\3G_ERP_V1.db'
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('tables', [r[0] for r in cur.fetchall() if 'home' in r[0].lower() or 'Home' in r[0]])
for name in ['homepage_content', 'homepagecontent', 'HomepageContent']:
    try:
        cur.execute(f'SELECT * FROM {name} LIMIT 1')
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        print(name, cols)
        if row:
            data = dict(zip(cols, row))
            print({k: data[k] for k in data if 'video' in k.lower() or 'banner' in k.lower() or 'publish' in k.lower()})
    except Exception as e:
        print(name, 'fail', e)
