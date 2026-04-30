from __future__ import annotations

import glob
import json
import os
import re
import shutil
from typing import Any, Callable


def legacy_results_root_dir(*, data_path: Callable[..., str], results_dirname: str) -> str:
    return data_path(results_dirname)


def results_dir(*, data_path: Callable[..., str], results_dirname: str, instance_id: str) -> str:
    return data_path(results_dirname, instance_id)


def results_state_path(*, results_dir_value: str) -> str:
    return os.path.join(results_dir_value, 'results_state.json')


def legacy_results_state_path(*, data_path: Callable[..., str]) -> str:
    return data_path('results_state.json')


def migrate_legacy_results_layout(*, legacy_root: str, instance_dir: str, legacy_state: str, current_state_path: str) -> None:
    try:
        legacy_shards = [p for p in glob.glob(os.path.join(legacy_root, 'results_*.jsonl')) if os.path.isfile(p)]
    except Exception:
        legacy_shards = []
    legacy_state_exists = os.path.isfile(legacy_state)
    if not legacy_shards and not legacy_state_exists:
        return
    try:
        instance_has_shards = bool([p for p in glob.glob(os.path.join(instance_dir, 'results_*.jsonl')) if os.path.isfile(p)])
    except Exception:
        instance_has_shards = False
    if instance_has_shards or os.path.isfile(current_state_path):
        return
    try:
        os.makedirs(instance_dir, exist_ok=True)
    except Exception:
        pass
    for pth in legacy_shards:
        try:
            shutil.move(pth, os.path.join(instance_dir, os.path.basename(pth)))
        except Exception:
            pass
    if legacy_state_exists:
        try:
            shutil.move(legacy_state, current_state_path)
        except Exception:
            pass


def read_json(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def write_json(path: str, obj: dict) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def flow_totals_path(*, data_path: Callable[..., str]) -> str:
    return data_path('flow_totals.json')


def flow_totals_read(*, read_json_fn: Callable[[str], dict], flow_totals_path_value: str) -> dict[str, int]:
    raw = read_json_fn(flow_totals_path_value)
    if not isinstance(raw, dict):
        raw = {}
    return {
        'protocol': int(raw.get('protocol', 0) or 0),
        'browser': int(raw.get('browser', 0) or 0),
    }


def flow_totals_inc(*, flow: str, delta: int, flow_totals_lock: Any, flow_totals_read_fn: Callable[[], dict[str, int]], write_json_fn: Callable[[str, dict], None], flow_totals_path_value: str) -> None:
    key = (flow or '').strip().lower()
    if key not in ('protocol', 'browser'):
        return
    with flow_totals_lock:
        st = flow_totals_read_fn()
        st[key] = int(st.get(key, 0) or 0) + int(delta)
        write_json_fn(flow_totals_path_value, st)


def flow_totals_snapshot(*, flow_totals_read_fn: Callable[[], dict[str, int]]) -> tuple[int, int]:
    st = flow_totals_read_fn()
    return int(st.get('protocol', 0) or 0), int(st.get('browser', 0) or 0)


def infer_results_state(*, results_dir_value: str, results_shard_size: int) -> dict:
    try:
        os.makedirs(results_dir_value, exist_ok=True)
    except Exception:
        pass
    try:
        files = [p for p in glob.glob(os.path.join(results_dir_value, 'results_*.jsonl')) if os.path.isfile(p)]
        if not files:
            return {'shard_id': 0, 'line_in_shard': 0}

        def _sid(pth: str) -> int:
            m = re.search(r'results_(\d+)\.jsonl$', os.path.basename(pth))
            return int(m.group(1)) if m else -1

        files.sort(key=_sid)
        last = files[-1]
        shard_id = _sid(last)
        if shard_id < 0:
            return {'shard_id': 0, 'line_in_shard': 0}
        line_count = 0
        try:
            with open(last, 'r', encoding='utf-8') as f:
                for _ in f:
                    line_count += 1
        except Exception:
            line_count = 0
        if line_count >= results_shard_size:
            return {'shard_id': shard_id + 1, 'line_in_shard': 0}
        return {'shard_id': shard_id, 'line_in_shard': line_count}
    except Exception:
        return {'shard_id': 0, 'line_in_shard': 0}


def load_results_state(*, read_json_fn: Callable[[str], dict], results_state_path_value: str, infer_results_state_fn: Callable[[], dict]) -> dict:
    st = read_json_fn(results_state_path_value)
    if 'shard_id' in st and 'line_in_shard' in st:
        return st
    return infer_results_state_fn()


def append_result_line(*, line: str, data_dir: str, results_dir_value: str, load_results_state_fn: Callable[[], dict], write_json_fn: Callable[[str, dict], None], results_state_path_value: str, results_shard_size: int) -> None:
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(results_dir_value, exist_ok=True)
    except Exception:
        pass
    payload = (line or '').rstrip('\r\n') + '\n'
    st = load_results_state_fn()
    shard_id = int(st.get('shard_id', 0) or 0)
    line_in_shard = int(st.get('line_in_shard', 0) or 0)
    shard_path = os.path.join(results_dir_value, f'results_{shard_id:06d}.jsonl')
    with open(shard_path, 'a', encoding='utf-8') as f:
        f.write(payload)
    line_in_shard += 1
    if line_in_shard >= results_shard_size:
        shard_id += 1
        line_in_shard = 0
    write_json_fn(results_state_path_value, {'shard_id': shard_id, 'line_in_shard': line_in_shard})
