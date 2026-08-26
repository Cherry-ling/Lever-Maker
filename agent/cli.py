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


def run_one(f):
    try:
        lvl = load(f)
    except Exception as ex:
        return False, [f"(JSON 解析失败: {ex})"], []
    v = LevelValidator(lvl, os.path.basename(f))
    ok, errs, warns = v.validate()
    return ok, errs, warns


def main(argv):
    quiet = "--quiet" in argv
    level = "--level" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    target = args[0]
    if os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, "*.json")))
    else:
        files = [target]

    total = len(files)
    bad = []
    for f in files:
        ok, errs, warns = run_one(f)
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
