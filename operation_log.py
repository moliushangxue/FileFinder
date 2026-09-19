#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 操作历史记录（追加式 JSONL 日志）

每次"复制/剪切到目标文件夹"完成后，把每个文件的"源路径 → 最终落点 → 结果"
追加写入本地日志，供用户回顾自己的操作、对照日志手动回退。

存储格式：JSONL（每行一条 JSON 记录）
  - 追加写入：崩溃/断电最多丢最后一行，已有历史不受影响
  - 可用记事本 / VS Code 直接打开阅读（ensure_ascii=False，中文路径可读）
  - 覆盖类操作的原文件已被替换，条目中会标注"原内容无法恢复"

存储位置：用户配置目录（constants.get_config_dir()），与 config.json 同目录。
打包成 exe 后程序目录可能没有写权限，不能放程序目录。

重要原则：写日志失败绝不能影响文件操作主流程，
record_operation 内部兜底所有异常。
"""

import json
import os
import time

from constants import get_config_dir

# 日志文件名（位于用户配置目录下）
LOG_FILE_NAME = "operation_history.jsonl"


def get_log_path():
    """返回操作历史日志的完整路径"""
    return os.path.join(get_config_dir(), LOG_FILE_NAME)


def record_operation(op, action, target, items, stats):
    """把一次文件操作追加写入历史日志

    参数:
        op:     操作代码（"copy" / "move"）
        action: 操作中文名（"复制" / "剪切"，方便用户直接阅读日志）
        target: 目标文件夹（用户最容易忘记的信息）
        items:  逐文件明细列表，每项为 dict：
                {"src": 源路径, "dst": 最终目标路径, "status": ...}
                status 取值：
                  "ok"          — 正常成功
                  "renamed"     — 成功，但目标名冲突自动改名为 dst（含编号）
                  "overwritten" — 成功，但覆盖了目标位置原有文件（原内容无法恢复）
                  "skipped"     — 用户选择跳过（未做任何改动）
                  "failed"      — 执行失败（附 error 原因，dst 为尝试写入的路径）
        stats:  统计 {"success": n, "skipped": n, "failed": n}
    """
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),   # 本地时间，方便用户对照记忆
        "op": op,
        "action": action,
        "target": target,
        "stats": stats,
        "items": items,
    }
    try:
        path = get_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 追加一行；一次操作一条记录，方便整体回退时分组阅读
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        # 写日志失败不影响文件操作本身，仅打印到控制台方便排查
        print(f"写入操作历史失败: {e}")
