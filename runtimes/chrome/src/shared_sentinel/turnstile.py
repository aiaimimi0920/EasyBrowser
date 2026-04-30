"""
OpenAI Turnstile 字节码虚拟机解码器

负责解析并执行 `/backend-anon/sentinel/chat-requirements` 返回的 Turnstile 挑战字节码。
"""

import base64
import json
import random
import time
from collections import OrderedDict, defaultdict
from typing import Any, Callable, Dict, List


class OrderedMap:
    def __init__(self):
        self.map = OrderedDict()

    def add(self, key: str, value: Any):
        self.map[key] = value

    def to_json(self):
        return json.dumps(self.map)

    def __str__(self):
        return self.to_json()


def get_turnstile_token(dx: str, p: str) -> str:
    """第一层解密: base64 解码后与 proof token 进行 XOR 操作"""
    decoded_bytes = base64.b64decode(dx)
    result = []
    p_length = len(p)
    if p_length != 0:
        for i, r in enumerate(decoded_bytes.decode('utf-8', errors='ignore')):
            result.append(chr(ord(r) ^ ord(p[i % p_length])))
    else:
        result = list(decoded_bytes.decode('utf-8', errors='ignore'))
    return "".join(result)


def is_slice(input_val: Any) -> bool:
    return isinstance(input_val, (list, tuple))

def is_float(input_val: Any) -> bool:
    return isinstance(input_val, (float, int)) and not isinstance(input_val, bool)

def is_string(input_val: Any) -> bool:
    return isinstance(input_val, str)

def to_str(input_val: Any) -> str:
    if input_val is None:
        return "undefined"
    elif is_float(input_val):
        return f"{input_val:.16g}"
    elif is_string(input_val):
        special_cases = {
            "window.Math": "[object Math]",
            "window.Reflect": "[object Reflect]",
            "window.performance": "[object Performance]",
            "window.localStorage": "[object Storage]",
            "window.Object": "function Object() { [native code] }",
            "window.Reflect.set": "function set() { [native code] }",
            "window.performance.now": "function () { [native code] }",
            "window.Object.create": "function create() { [native code] }",
            "window.Object.keys": "function keys() { [native code] }",
            "window.Math.random": "function random() { [native code] }",
        }
        return special_cases.get(input_val, input_val)
    elif isinstance(input_val, list) and all(isinstance(item, str) for item in input_val):
        return ",".join(input_val)
    else:
        return str(input_val)


def get_func_map(start_time: float) -> Dict[float, Any]:
    """初始化 Turnstile 虚拟机的指令映射表"""
    process_map = defaultdict(lambda: None)

    def func_1(e, t):
        e_str = to_str(process_map[e])
        t_str = to_str(process_map[t])
        if e_str is not None and t_str is not None:
            # XOR 解密内部逻辑
            res = []
            p_len = len(t_str)
            if p_len != 0:
                for i, r in enumerate(e_str):
                    res.append(chr(ord(r) ^ ord(t_str[i % p_len])))
            else:
                res = list(e_str)
            process_map[e] = "".join(res)

    def func_2(e, t):
        process_map[e] = t

    def func_5(e, t):
        n = process_map[e]
        tres = process_map[t]
        if n is None:
            process_map[e] = tres
        elif is_slice(n):
            nt = n + [tres] if tres is not None else n
            process_map[e] = nt
        else:
            if is_string(n) or is_string(tres):
                res = to_str(n) + to_str(tres)
            elif is_float(n) and is_float(tres):
                res = n + tres
            else:
                res = "NaN"
            process_map[e] = res

    def func_6(e, t, n):
        tv = process_map[t]
        nv = process_map[n]
        if is_string(tv) and is_string(nv):
            res = f"{tv}.{nv}"
            if res == "window.document.location":
                process_map[e] = "https://chatgpt.com/"
            else:
                process_map[e] = res

    def func_7(e, *args):
        n = [process_map[arg] for arg in args]
        ev = process_map[e]
        if isinstance(ev, str):
            if ev == "window.Reflect.set":
                obj = n[0]
                key_str = str(n[1])
                val = n[2]
                if hasattr(obj, 'add'):
                    obj.add(key_str, val)
        elif callable(ev):
            ev(*n)

    def func_8(e, t):
        process_map[e] = process_map[t]

    def func_14(e, t):
        tv = process_map[t]
        if is_string(tv):
            try:
                token_list = json.loads(tv)
                process_map[e] = token_list
            except json.JSONDecodeError:
                process_map[e] = None
        else:
            process_map[e] = None

    def func_15(e, t):
        tv = process_map[t]
        process_map[e] = json.dumps(tv, separators=(',', ':'))

    def func_17(e, t, *args):
        i = [process_map[arg] for arg in args]
        tv = process_map[t]
        res = None
        if isinstance(tv, str):
            if tv == "window.performance.now":
                current_time = time.time_ns()
                elapsed_ns = current_time - int(start_time * 1e9)
                res = (elapsed_ns + random.random()) / 1e6
            elif tv == "window.Object.create":
                res = OrderedMap()
            elif tv == "window.Object.keys":
                if isinstance(i[0], str) and i[0] == "window.localStorage":
                    res = [
                        "STATSIG_LOCAL_STORAGE_INTERNAL_STORE_V4",
                        "STATSIG_LOCAL_STORAGE_STABLE_ID",
                        "client-correlated-secret",
                        "oai/apps/capExpiresAt",
                        "oai-did",
                        "STATSIG_LOCAL_STORAGE_LOGGING_REQUEST",
                        "UiState.isNavigationCollapsed.1",
                    ]
            elif tv == "window.Math.random":
                res = random.random()
        elif callable(tv):
            res = tv(*i)
        process_map[e] = res

    def func_18(e):
        ev = process_map[e]
        e_str = to_str(ev)
        try:
            decoded = base64.b64decode(e_str).decode()
            process_map[e] = decoded
        except Exception:
            process_map[e] = ""

    def func_19(e):
        ev = process_map[e]
        e_str = to_str(ev)
        encoded = base64.b64encode(e_str.encode()).decode()
        process_map[e] = encoded

    def func_20(e, t, n, *args):
        o = [process_map[arg] for arg in args]
        ev = process_map[e]
        tv = process_map[t]
        if ev == tv:
            nv = process_map[n]
            if callable(nv):
                nv(*o)

    def func_21(*args):
        pass

    def func_23(e, t, *args):
        i = list(args)
        ev = process_map[e]
        tv = process_map[t]
        if ev is not None and callable(tv):
            tv(*i)

    def func_24(e, t, n):
        tv = process_map[t]
        nv = process_map[n]
        if is_string(tv) and is_string(nv):
            process_map[e] = f"{tv}.{nv}"

    process_map.update({
        1: func_1, 2: func_2, 5: func_5, 6: func_6, 7: func_7,
        8: func_8, 10: "window", 14: func_14, 15: func_15,
        17: func_17, 18: func_18, 19: func_19, 20: func_20,
        21: func_21, 23: func_23, 24: func_24,
    })

    return process_map


def process_turnstile(dx: str, p: str) -> str:
    """
    完整的 Turnstile 字节码虚拟机解码流程
    
    Args:
        dx: 服务端返回的 turnstile.dx
        p: 我们生成的 proof token (gAAAAAC...)
        
    Returns:
        str: 解码后生成的 turnstile token
    """
    start_time = time.time()
    
    # 1. 解码 + XOR 异或
    tokens_json = get_turnstile_token(dx, p)
    res = ""
    
    try:
        token_list = json.loads(tokens_json)
    except json.JSONDecodeError:
        return ""

    # 2. 初始化 VM
    process_map = get_func_map(start_time)

    def func_3(e: str):
        nonlocal res
        res = base64.b64encode(e.encode()).decode()

    process_map[3] = func_3
    process_map[9] = token_list
    process_map[16] = p

    # 3. 执行指令
    for token in token_list:
        try:
            if not token: continue
            cmd_code = token[0]
            args = token[1:]
            func = process_map.get(cmd_code)
            if callable(func):
                func(*args)
        except Exception as exc:
            print(f"Turnstile VM execution error on {token}: {exc}")
            continue

    return res
