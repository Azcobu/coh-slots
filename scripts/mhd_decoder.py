# Demonstrates decoding of MBD format Mids blocks.

import base64, brotli, json

def main():
    lines ='''|MBD;25373;1635;2180;BASE64;|
|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|
|ieBthggkJLPyaYruj0arSoMiuu1EdG49mrQD|'''

    line_list = [l for l in lines.splitlines() if l]
    # 1. Parse header
    header_line = line_list[0]  # |MBD;6309;481;644;BASE64;|
    # 2. Strip pipes from payload lines, concatenate
    payload = ''.join(line.strip('|') for line in line_list[1:])
    # 3. Base64 decode → Brotli decompress → JSON parse
    build = json.loads(brotli.decompress(base64.b64decode(payload)))
    print(build)

if __name__ == '__main__':
    main()
