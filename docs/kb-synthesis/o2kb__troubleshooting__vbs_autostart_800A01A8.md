# 自启VBS报错800A01A8（缺少对象 'sh'）

> category: o2kb::troubleshooting  |  id: o2kb::troubleshooting::vbs_autostart_800A01A8

症状：%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\O2OA_AI_stack_autostart.vbs 在登录/双击时报「800A01A8 缺少对象 'sh'」，且行号错位（实际指 sh.Run 那行），AI 栈开机后根本没被拉起。

根因：VBS 以 UTF-8 无 BOM + 中文注释 + LF 行尾保存。Windows Script Host 按 ANSI/GBK 解析，中文多字节高位字节会吞掉其后的换行符，使 `Set sh = CreateObject(...)` 那一行被并入上一行注释而未执行；后续 `sh.Run ...` 引用 sh 时对象不存在即报 800A01A8，且因换行被吞行号整体错位（如报第7行）。

修复（编码层面免疫）：整文件改写为纯 ASCII 注释 + CRLF。验证：`file` 显示 "ASCII text, with CRLF"；`grep -P '[\x80-\xFF]'` 非 ASCII 字节扫描为空。永不在此文件写中文。自启 VBS 的权威源应放进仓库 gateway/autostart/，Startup 仅放置副本。
