"""
OpenAI ChatGPT Proof of Work (PoW) Token 生成器

支持两种模式：
1. 响应式 PoW (gAAAAAB): 基于服务端返回的 seed 和 difficulty 求解
2. 自生成 Requirements Token (gAAAAAC): 客户端本地生成，用于初始请求

核心算法: SHA3-512 哈希 + Base64 编码
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from .config import (
    CORES, SCREENS, MAX_ATTEMPTS,
    NAVIGATOR_KEYS, DOCUMENT_KEYS, WINDOW_KEYS,
    DEFAULT_USER_AGENT, get_data_build,
)

POW_TIMEZONE = timezone(timedelta(hours=-5), name="Eastern Standard Time")


def get_parse_time() -> str:
    """
    生成模拟浏览器的时间戳字符串。
    格式: "Mon Jan 01 2026 12:00:00 GMT-0500 (Eastern Standard Time)"
    """
    now = datetime.now(POW_TIMEZONE)
    return now.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"


def build_config(
    user_agent: str | None = None,
    core: int | None = None,
    screen: int | None = None,
    data_build: str | None = None,
) -> list:
    """
    构建浏览器环境配置数组。

    模拟浏览器中收集的环境信息，允许从外部传入确定的核心数、分辨率和 data-build。
    """
    if user_agent is None:
        user_agent = DEFAULT_USER_AGENT

    actual_core = core if core is not None else random.choice(CORES)
    actual_screen = screen if screen is not None else random.choice(SCREENS)
    actual_data_build = data_build if data_build is not None else get_data_build()

    config = [
        actual_core + actual_screen,            # [0]  核心数 + 屏幕分辨率
        get_parse_time(),                       # [1]  格式化时间
        None,                                   # [2]  null
        random.random(),                        # [3]  随机数 (迭代时被覆盖)
        user_agent,                             # [4]  User-Agent
        None,                                   # [5]  脚本 URL (null)
        actual_data_build,                      # [6]  data-build 属性值
        "en-US",                                # [7]  语言
        "en-US,es-US,en,es",                    # [8]  语言列表
        0,                                      # [9]  固定值
        random.choice(NAVIGATOR_KEYS),          # [10] navigator 随机 key
        "location",                             # [11] document key (固定)
        random.choice(WINDOW_KEYS),             # [12] window 随机 key
        time.perf_counter(),                    # [13] 性能计时器
        str(uuid.uuid4()),                      # [14] UUID
        "",                                     # [15] 空字符串
        actual_core,                            # [16] 核心数
        int(time.time()),                       # [17] Unix 时间戳
    ]
    return config


def solve_challenge(seed: str, difficulty: str, config: list) -> tuple[str, bool]:
    """
    求解 PoW 挑战。
    
    算法流程:
    1. 将 config 数组分成 3 段静态部分 (去掉动态索引 [3] 和 [9])
    2. 在每次迭代中:
       - 将 i 填入 config[3]，将 i>>1 填入 config[9]
       - JSON 序列化 -> Base64 编码
       - SHA3-512(seed + base64_config)
       - 检查哈希值前 N 个字节是否 <= difficulty
    
    Args:
        seed: 服务端提供的随机种子
        difficulty: 难度值 (十六进制字符串，如 "0fffff")
        config: build_config() 生成的环境配置
    
    Returns:
        tuple: (base64 编码的解, 是否成功)
    """
    seed_encoded = seed.encode()
    target_diff = bytes.fromhex(difficulty)
    diff_len = len(target_diff)

    # 预计算静态 JSON 片段 (性能优化)
    # config[:3] = [core+screen, time, null]
    part1 = (json.dumps(config[:3], separators=(',', ':'), ensure_ascii=False)[:-1] + ',').encode()
    # config[4:9] = [user_agent, null, data_build, lang, lang_list]
    part2 = (',' + json.dumps(config[4:9], separators=(',', ':'), ensure_ascii=False)[1:-1] + ',').encode()
    # config[10:] = [nav_key, doc_key, win_key, perf_counter, uuid, "", 8, timestamp]
    part3 = (',' + json.dumps(config[10:], separators=(',', ':'), ensure_ascii=False)[1:]).encode()

    for i in range(MAX_ATTEMPTS):
        # 动态部分: config[3] = i, config[9] = i >> 1
        dynamic1 = str(i).encode()
        dynamic2 = str(i >> 1).encode()

        full_json = part1 + dynamic1 + part2 + dynamic2 + part3
        b64_encoded = base64.b64encode(full_json)

        hash_value = hashlib.sha3_512(seed_encoded + b64_encoded).digest()

        if hash_value[:diff_len] <= target_diff:
            return b64_encoded.decode(), True

    # 超过最大迭代次数，返回 fallback 值
    fallback = 'wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D' + base64.b64encode(f'"{seed}"'.encode()).decode()
    return fallback, False


def generate_proof_token(
    required: bool,
    seed: str = "",
    difficulty: str = "",
    user_agent: str | None = None,
    core: int | None = None,
    screen: int | None = None,
    data_build: str | None = None,
) -> str | None:
    """
    生成 PoW proof token (gAAAAAB 前缀)。
    """
    if not required:
        return None

    config = build_config(
        user_agent=user_agent,
        core=core,
        screen=screen,
        data_build=data_build,
    )
    
    answer, solved = solve_challenge(seed, difficulty, config)
    if solved:
        return "gAAAAAB" + answer

    fallback_b64 = base64.b64encode(f'"{seed}"'.encode()).decode()
    return "gAAAAABwQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + fallback_b64


def generate_requirements_token(
    user_agent: str | None = None,
    core: int | None = None,
    screen: int | None = None,
    data_build: str | None = None,
) -> str:
    """
    生成 requirements token (gAAAAAC 前缀)。
    
    这是客户端自行生成的 token，用于初始的 sentinel/chat-requirements 请求。
    不依赖服务端返回的 seed/difficulty，而是使用本地随机值和固定难度。
    
    Args:
        user_agent: 浏览器 User-Agent
        core: 可选的 CPU 核心数
        screen: 可选的屏幕分辨率
    
    Returns:
        str: "gAAAAAC" + base64 编码的解
    
    Raises:
        RuntimeError: 如果未能在最大迭代次数内求解
    """
    config = build_config(
        user_agent=user_agent,
        core=core,
        screen=screen,
        data_build=data_build,
    )
    seed = format(random.random())
    difficulty = "0fffff"

    answer, solved = solve_challenge(seed, difficulty, config)

    if solved:
        return 'gAAAAAC' + answer
    else:
        raise RuntimeError(f"无法在 {MAX_ATTEMPTS} 次迭代内求解 requirements token 挑战")


# ============================================
# 快捷函数
# ============================================
def get_pow_token(
    user_agent: str | None = None,
    core: int | None = None,
    screen: int | None = None,
    data_build: str | None = None,
) -> str:
    """快捷方式: 生成一个 requirements token"""
    return generate_requirements_token(
        user_agent=user_agent,
        core=core,
        screen=screen,
        data_build=data_build,
    )


if __name__ == "__main__":
    print("=" * 60)
    print("OpenAI PoW Token Generator")
    print("=" * 60)

    # 生成 requirements token (gAAAAAC)
    token = generate_requirements_token()
    print(f"\n[Requirements Token] (gAAAAAC 前缀)")
    print(f"  长度: {len(token)}")
    print(f"  Token: {token[:80]}...")

    # 模拟生成 proof token (gAAAAAB)
    test_seed = "test_seed_value"
    test_difficulty = "0fffff"
    proof = generate_proof_token(True, test_seed, test_difficulty)
    print(f"\n[Proof Token] (gAAAAAB 前缀)")
    print(f"  Seed: {test_seed}")
    print(f"  Difficulty: {test_difficulty}")
    print(f"  长度: {len(proof)}")
    print(f"  Token: {proof[:80]}...")
