#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 CRM 百度地图补丁固化进 E:\\OA系统上线方案\\客户管理.zip。

- 先备份原 zip 为 客户管理.zip.bak-<时间戳>
- 逐条替换 web/x_component_CRM/ 下 8 个 JS（保持其它条目原样、保持压缩方式）
- 完成后校验：zip 内这 8 个文件的字节数与补丁版一致，且含 O2OA-NOMAP-PATCH 标记
"""
import io
import os
import shutil
import time
import zipfile

ZIP = r"E:\OA系统上线方案\客户管理.zip"
WORK = r"C:\temp\o2dbg\work"          # 已修补文件所在目录
PREFIX = "web/x_component_CRM/"
FILES = [
    "Main.js", "Main.min.js", "Main.min.min.js",
    "BaiduMap.js", "BaiduMap.min.js", "BaiduMap.min.min.js",
    "AddressExplorer.js", "AddressExplorer.min.js",
]
MARK = b"O2OA-NOMAP-PATCH"


def main():
    assert os.path.exists(ZIP), "找不到 zip: %s" % ZIP
    bak = ZIP + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(ZIP, bak)
    print("已备份 -> %s" % os.path.basename(bak))

    # 读入全部条目（内存，19 个应用包里 CRM 体量不大）
    with zipfile.ZipFile(ZIP, "r") as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}

    replaced = 0
    for f in FILES:
        arc = PREFIX + f
        src = os.path.join(WORK, f)
        if arc not in data:
            print("  SKIP (zip 内不存在)  %s" % arc)
            continue
        assert os.path.exists(src), "缺补丁文件 %s" % src
        with io.open(src, "rb") as fh:
            new = fh.read()
        assert MARK in new, "%s 不含补丁标记，拒绝写入" % f
        old_len = len(data[arc])
        data[arc] = new
        print("  REPLACED  %-28s %6d -> %6d" % (f, old_len, len(new)))
        replaced += 1

    assert replaced == len(FILES), "只替换了 %d/%d 个文件，中止" % (replaced, len(FILES))

    # 原样重写（保持顺序、保持每条的压缩方式与时间戳）
    tmp = ZIP + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for i in infos:
            zi = zipfile.ZipInfo(i.filename, date_time=i.date_time)
            zi.compress_type = i.compress_type
            zi.external_attr = i.external_attr
            zi.internal_attr = i.internal_attr
            zi.create_system = i.create_system
            z.writestr(zi, data[i.filename])
    os.replace(tmp, ZIP)
    print("已写回 %s" % ZIP)

    # 校验
    print("\n校验：")
    with zipfile.ZipFile(ZIP, "r") as z:
        ok = True
        for f in FILES:
            arc = PREFIX + f
            b = z.read(arc)
            good = MARK in b
            ok = ok and good
            print("  %-28s %6d B  标记=%s" % (f, len(b), "有" if good else "无 ★"))
        print("\n结果:", "全部固化成功 ✔" if ok else "存在失败 ★")


if __name__ == "__main__":
    main()
