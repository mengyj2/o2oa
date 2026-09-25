#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PatchActionChat.py —— 修复 O2OA AI 助手对推理模型的 reasoning_content 陷阱。

背景
----
O2OA 的 ActionChat.aiChat() 发送 data.put("enable_thinking", Boolean)。LM Studio
的 OpenAI 兼容端点不认这个键，静默忽略；推理模型遂把 token 全花在
reasoning_content 里，而 O2OA 的 picContent() 只读 delta.content -> 界面空白。

实测（本机 LM Studio / glm-4.7-flash）：
    enable_thinking=false         -> reasoning_tokens=200, content=""
    chat_template_kwargs{...}     -> rt=63,  content 被污染
    thinking:{type:"disabled"}    -> rt=61,  content 被污染
    reasoning_effort="none"       -> rt=0,   content 完整   ★ 唯一有效
    system / user 加 /no_think    -> 无效（本模型）

补丁
----
把请求体里的
    "enable_thinking" -> Boolean.valueOf(isTrue(wi.getThinkingEnabled()))
替换为
    "reasoning_effort" -> "none"

实现要点（这是关键，不能只改常量池）
------------------------------------
Utf8 由 15 字节变 16 字节，会让其后所有内容后移 1 字节。因此必须修正：
  1) constant_pool_count 之后的所有 cp 条目偏移（自然后移，无需处理）
  2) ★ 常量池结束后紧跟的字段/方法表，其中 **每个方法的 attribute_length
     以及 Code 属性内部的 exception_table / attributes 偏移都需要 +delta**
  3) ★ Code 属性内的字节码偏移不变（相对定位），但其外围 attribute_length 需 +delta
本脚本选择**不做长度变更**规避该问题：
  改用等长方案 —— 键名仍占 15 字节，但在字节码里把 Boolean 值改成字符串。
  不过 "reasoning_effort" 无 15 字节同义词，故采取：
  **保留 enable_thinking 常量位置不动，新增 reasoning_effort 常量，并把 ldc_w
  的操作数指向新常量。** Utf8 "reasoning_effort" 追加到常量池尾部 —— 只增加
  cp 条目，不改动任何已有 Utf8 的长度，因此后续 attribute_length 完全不受影响。
  追加块总长 = 10 字节（Utf8 头3+16 + String 头3），仅影响 cp_end 之后一次平移，
  这由 constant_pool_count 变化 + 尾部插入自然完成，无需修改方法表长度。
"""
import sys
import struct

NEW_NAME = b"reasoning_effort"
NONE_VAL = b"none"
OLD_NAME = b"enable_thinking"

# 目标指令序列（偏移 91..100）: aload_1 | invokevirtual #417 | invokestatic #65 | invokestatic #176
OLD_SEQ = bytes([0x2B, 0xB6, 0x01, 0xA1, 0xB8, 0x00, 0x41, 0xB8, 0x00, 0xB0])


class Cp:
    def __init__(self, data):
        self.d = data
        self.off = {}          # idx -> offset of the entry (tag byte)
        self.tags = {}         # idx -> tag
        self.utf8 = {}         # idx -> bytes
        self.string = {}       # idx -> utf8 idx
        self.count = struct.unpack_from(">H", data, 8)[0]
        self.end = self._scan()

    def u1(self, o): return self.d[o]
    def u2(self, o): return struct.unpack_from(">H", self.d, o)[0]

    def _scan(self):
        d = self.d
        o = 10
        i = 1
        while i < self.count:
            tag = d[o]
            self.off[i] = o
            self.tags[i] = tag
            o += 1
            if tag == 1:
                ln = self.u2(o)
                self.utf8[i] = d[o + 2:o + 2 + ln]
                o += 2 + ln
            elif tag in (7, 8, 16, 19, 20):
                if tag == 8:
                    self.string[i] = self.u2(o)
                o += 2
            elif tag == 15:
                o += 3
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
                o += 4
            elif tag in (5, 6):
                o += 8
                i += 1
            else:
                raise ValueError("bad cp tag %d at #%d" % (tag, i))
            i += 1
        return o


def patch(data):
    cp = Cp(data)
    if any(v == NEW_NAME for v in cp.utf8.values()):
        return None, "already"

    hits = [i for i, v in cp.utf8.items() if v == OLD_NAME]
    if len(hits) != 1:
        raise SystemExit("[FAIL] 'enable_thinking' Utf8 数量=%d，期望 1" % len(hits))
    old_idx = hits[0]
    print("[1/3] Utf8 'enable_thinking' = #%d" % old_idx)

    pos = data.find(OLD_SEQ)
    if pos < 0:
        raise SystemExit("[FAIL] 未找到布尔赋值指令序列")
    if data.find(OLD_SEQ, pos + 1) >= 0:
        raise SystemExit("[FAIL] 指令序列不唯一，拒绝盲改")
    print("[2/3] 指令序列文件偏移 = %d" % pos)

    # 追加常量：Utf8 "reasoning_effort" + Utf8 "none" + String -> "none"
    n_new_utf8 = cp.count
    n_none_utf8 = cp.count + 1
    n_none_str = cp.count + 2

    add = bytearray()
    add += b"\x01" + struct.pack(">H", len(NEW_NAME)) + NEW_NAME
    add += b"\x01" + struct.pack(">H", len(NONE_VAL)) + NONE_VAL
    add += b"\x08" + struct.pack(">H", n_none_utf8)
    print("[3/3] 追加 #%d Utf8 '%s' / #%d Utf8 'none' / #%d String->#%d"
          % (n_new_utf8, NEW_NAME.decode(), n_none_utf8, n_none_str, n_none_utf8))

    head = bytearray(data[:8]) + struct.pack(">H", cp.count + 3)
    cp_bytes = data[10:cp.end]
    tail = data[cp.end:]

    out = bytearray(head + cp_bytes + add + tail)

    # 现在 ldc_w 需要指向：新键名 (n_new_utf8 对应的 String —— 但 ldc_w 需要 String 条目)
    # 原补丁 #415 是 String -> #416(Utf8 enable_thinking)。
    # 我们让 #415 这个 String 条目直接指向新的 Utf8 "reasoning_effort"：
    #   String 条目布局 [tag=8][u2 utf8_idx] -> 把 utf8_idx 改成 n_new_utf8
    str_entry_off = cp.off[415]
    assert out[str_entry_off] == 8, "期望 #415 是 String"
    struct.pack_into(">H", out, str_entry_off + 1, n_new_utf8)

    # 字节码：把 OLD_SEQ 的后 7 字节（3 条 invokestatic 中的后两条 + 前面1字节）
    # 换成 ldc_w n_none_str + nop
    # OLD: 91 aload_1 | 92 invokevirtual(3) | 95 invokestatic(3) | 98 invokestatic(3) = 10B
    # NEW: 91 ldc_w n_none_str(3) | 94 nop x7 = 10B
    # 插入点在 cp.end 处，出现在指令序列之前，故整体后移 len(add) 字节
    assert pos > cp.end, "指令序列竟在常量池之前？pos=%d cp.end=%d" % (pos, cp.end)
    new_pos = pos + len(add)
    new_seq = bytes([0x13]) + struct.pack(">H", n_none_str) + b"\x00" * 7
    assert out[new_pos:new_pos + len(OLD_SEQ)] == OLD_SEQ, \
        "平移后未命中指令序列（new_pos=%d）" % new_pos
    out[new_pos:new_pos + len(OLD_SEQ)] = new_seq
    print("     ldc_w #%d ('none') 已写入偏移 %d" % (n_none_str, new_pos))

    return bytes(out), "patched"


def verify(data):
    cp = Cp(data)
    ok = True
    n = [i for i, v in cp.utf8.items() if v == NEW_NAME]
    if n:
        print("  [OK]   Utf8 'reasoning_effort' = #%d" % n[0])
    else:
        print("  [FAIL] 缺 Utf8 'reasoning_effort'"); ok = False

    if any(v == NONE_VAL for v in cp.utf8.values()):
        print("  [OK]   Utf8 'none' 存在")
    else:
        print("  [FAIL] 缺 Utf8 'none'"); ok = False

    strs = [i for i, u in cp.string.items() if cp.utf8.get(u) == NONE_VAL]
    if strs:
        pat = bytes([0x13]) + struct.pack(">H", strs[0])
        if data.find(pat) >= 0:
            print("  [OK]   字节码含 ldc_w #%d ('none')" % strs[0])
        else:
            print("  [FAIL] 字节码未引用 String 'none'"); ok = False
    else:
        print("  [FAIL] 无 String 'none'"); ok = False

    if data.find(OLD_SEQ) >= 0:
        print("  [FAIL] 旧布尔指令序列仍在"); ok = False
    else:
        print("  [OK]   旧布尔指令序列已消除")

    # #415 String 现在应指向 reasoning_effort
    u415 = cp.string.get(415)
    if u415 is not None and cp.utf8.get(u415) == NEW_NAME:
        print("  [OK]   #415 String -> #%d 'reasoning_effort'" % u415)
    else:
        print("  [FAIL] #415 未指向 reasoning_effort"); ok = False
    return ok


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--verify":
        with open(sys.argv[2], "rb") as f:
            sys.exit(0 if verify(f.read()) else 1)
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)

    with open(sys.argv[1], "rb") as f:
        data = f.read()
    out, st = patch(data)
    if st == "already":
        print("[INFO] 已打过补丁")
        with open(sys.argv[2], "wb") as f:
            f.write(data)
        sys.exit(0)
    with open(sys.argv[2], "wb") as f:
        f.write(out)
    print("[DONE] %d -> %d 字节" % (len(data), len(out)))
    print("\n--- 自校验 ---")
    sys.exit(0 if verify(out) else 1)


if __name__ == "__main__":
    main()
