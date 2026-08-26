# -*- coding: utf-8 -*-
"""Level-Maker 校验器 CLI。

用法:
    python3 cli.py <单关 JSON 或关卡目录>   # 目录则批量校验
选项:
    --quiet    只输出汇总
    --level    输出每关第一处错误（定位用）
"""
import json, glob, os, sys
from validator import LevelValidator


def load(f):
    with open(f, encoding="utf-8-sig") as fp:
        return json.load(fp)


def run_one(f, strict_color=False, max_num=None):
    bn = os.path.basename(f)
    if max_num is not None:
        import re
        m = re.match(r"lv_([0-9]+)_A\.json$", bn)
        if not m or int(m.group(1)) > max_num:
            return None
    try:
        lvl = load(f)
    except Exception as ex:
        return False, [f"(JSON 解析失败: {ex})"], []
    v = LevelValidator(lvl, bn, strict_color=strict_color)
    ok, errs, warns = v.validate()
    return ok, errs, warns


def main(argv):
    quiet = "--quiet" in argv
    level = "--level" in argv
    strict = "--strict" in argv
    max_num = None
    args = []
    for a in argv:
        if a.startswith("--max-num="):
            max_num = int(a.split("=")[1])
        elif not a.startswith("--"):
            args.append(a)
    if not args:
        print(__doc__)
        return 1
    target = args[0]
    if os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, "*.json")))
    else:
        files = [target]

    total = 0
    bad = []
    for f in files:
        res = run_one(f, strict_color=strict, max_num=max_num)
        if res is None:
            continue
        total += 1
        ok, errs, warns = res
        if not ok:
            bad.append((f, errs, warns))
            if not quiet:
                print("✗", os.path.basename(f))
                for e in errs[:6]:
                    print("    ", e)
                if warns and level:
                    for w in warns[:3]:
                        print("    ~", w)
        else:
            if not quiet:
                print("✓", os.path.basename(f))

    print(f"\n===== 结果: {total - len(bad)}/{total} 通过, {len(bad)} 失败 =====")
    if bad:
        print("失败清单:")
        for f, errs, warns in bad:
            print(" -", os.path.basename(f), f"({len(errs)} 错误)")
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
