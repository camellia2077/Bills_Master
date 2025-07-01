# bill_validator.py

import re
import time
import json
from collections import defaultdict

# --- 新增辅助函数 ---
def _load_config(config_path):
    """加载并解析JSON配置文件。"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- 核心验证逻辑函数 (已更新) ---

def _read_and_preprocess(file_path):
    """逐行读取文件并预处理行"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [
            (lineno, line.strip())
            for lineno, line in enumerate(f, 1)
            if line.strip()
        ]

def _validate_date_and_remark(lines):
    """验证DATE和REMARK行"""
    errors = []
    if len(lines) < 2:
        errors.append((0, "文件必须包含至少DATE和REMARK两行"))
        return errors
    
    date_lineno, date_line = lines[0]
    if not re.fullmatch(r'^DATE:\d{6}$', date_line):
        errors.append((date_lineno, "DATE格式错误,必须为DATE:后接6位数字"))
    
    remark_lineno, remark_line = lines[1]
    if not re.fullmatch(r'^REMARK:.*$', remark_line):
        errors.append((remark_lineno, "REMARK格式错误,必须为REMARK:开头"))
    
    return errors

# --- 状态处理函数 (已更新以使用config) ---

def _handle_parent_state(line, lineno, state):
    """处理父标题状态，验证标题是否在配置中"""
    if line in state['config']:
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        return []
    else:
        # 提供更具体的错误信息
        if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', line):
            return [(lineno, f"父级标题 '{line}' 不在配置文件中")]
        else:
            return [(lineno, "期望一个在配置文件中定义的父级标题, 但找到不匹配的内容")]

def _handle_sub_state(line, lineno, state):
    """处理子标题状态，验证子标题是否属于父标题的配置"""
    errors = []
    current_parent = state['current_parent']
    if not current_parent:
        return [(lineno, "未找到父级标题")]
    
    parent_lineno, parent_name = current_parent
    valid_subs = state['config'].get(parent_name, [])

    # 检查当前行是否是为当前父项定义的有效子项
    if line in valid_subs:
        new_sub = (lineno, line)
        state['subs'][current_parent].append(new_sub)
        state['current_sub'] = new_sub
        state['expecting'] = 'content'
    # 检查当前行是否是一个新的（但有效的）父项
    elif line in state['config']:
        errors.append((parent_lineno, f"父级标题 '{parent_name}' 缺少子标题"))
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
    else:
        errors.append((lineno, f"子标题 '{line}' 对于父级标题 '{parent_name}' 无效, 或该行不是一个有效的父标题"))
    return errors

def _handle_content_state(line, lineno, state):
    """处理内容状态，并检查是否过渡到新的父/子标题"""
    errors = []
    current_sub = state['current_sub']
    current_parent = state['current_parent']

    is_content = re.fullmatch(r'^\d+(?:\.\d+)?(?:[^\d\s][\d\u4e00-\u9fffa-zA-Z_-]*)+$', line)
    
    # 根据配置检查是否为新父项或新子项
    is_new_parent = line in state['config']
    is_new_sub = False
    if current_parent:
        valid_subs = state['config'].get(current_parent[1], [])
        if line in valid_subs:
            is_new_sub = True

    if is_content:
        if not current_sub:
             errors.append((lineno, "找到内容行，但当前没有活动的子标题"))
        else:
             state['content_counts'][current_sub] += 1
    elif is_new_parent:
        if current_sub and state['content_counts'][current_sub] == 0:
            errors.append((current_sub[0], "子标题缺少内容行"))
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        state['current_sub'] = None
    elif is_new_sub:
         if current_sub and state['content_counts'][current_sub] == 0:
             errors.append((current_sub[0], "子标题缺少内容行"))
         new_sub = (lineno, line)
         if not current_parent:
              errors.append((lineno, "找到新子标题，但父标题信息丢失"))
         else:
              state['subs'][current_parent].append(new_sub)
              state['current_sub'] = new_sub
              state['expecting'] = 'content'
    else:
         errors.append((lineno, "期望内容行、配置文件中有效的子标题或父标题, 但找到其他内容"))
    return errors

def _process_lines(lines, state):
    """处理所有数据行"""
    for i in range(2, len(lines)):
        lineno, line = lines[i]
        handler = {
            'parent': _handle_parent_state,
            'sub': _handle_sub_state,
            'content': _handle_content_state
        }[state['expecting']]
        
        errors = handler(line, lineno, state)
        if errors:
            state['errors'].extend(errors)

def _post_validation_checks(state):
    """后处理验证检查 (逻辑不变)"""
    errors = []
    # 检查未闭合的父标题
    if state['expecting'] == 'sub' and state['current_parent']:
        errors.append((state['current_parent'][0], f"父级标题 '{state['current_parent'][1]}' 缺少子标题"))
    # 检查未闭合的子标题
    elif state['expecting'] == 'content' and state['current_sub']:
        if state['content_counts'][state['current_sub']] == 0:
            errors.append((state['current_sub'][0], "子标题缺少内容行"))
    # 检查所有父标题是否有子标题
    for parent in state['parents']:
        if not state['subs'].get(parent):
            # 避免重复报错
            err_tuple = (parent[0], f"父级标题 '{parent[1]}' 缺少子标题")
            if err_tuple not in errors:
                errors.append(err_tuple)
    return errors

# --- 公开的API函数 (已更新) ---
def validate_file(file_path, config_path):
    """
    验证单个账单文件格式，并根据JSON配置文件校验父项和子项。

    Args:
        file_path (str): 要验证的账单文件的路径。
        config_path (str): Validator_Config.json配置文件的路径。

    Returns:
        dict: 一个包含验证结果的字典。
    """
    start_time = time.perf_counter()
    state = {
        'expecting': 'parent',
        'current_parent': None,
        'current_sub': None,
        'parents': [],
        'subs': defaultdict(list),
        'content_counts': defaultdict(int),
        'errors': [],
        'config': {} # 为配置数据预留位置
    }
    
    try:
        # 首先加载配置
        state['config'] = _load_config(config_path)
        
        lines = _read_and_preprocess(file_path)
        processed_lines = len(lines)
        
        state['errors'].extend(_validate_date_and_remark(lines))
        
        if len(lines) >= 2:
            _process_lines(lines, state)
        
        state['errors'].extend(_post_validation_checks(state))
        
        # 去重和排序错误
        unique_errors = sorted(list(set(state['errors'])), key=lambda x: x[0])

        return {
            'processed_lines': processed_lines,
            'errors': unique_errors,
            'time': time.perf_counter() - start_time
        }
    except FileNotFoundError:
        return {
            'processed_lines': 0,
            'errors': [(0, f"错误: 配置文件 '{config_path}' 未找到。")],
            'time': time.perf_counter() - start_time
        }
    except json.JSONDecodeError:
        return {
            'processed_lines': 0,
            'errors': [(0, f"错误: 配置文件 '{config_path}' 格式无效。")],
            'time': time.perf_counter() - start_time
        }
    except Exception as e:
        return {
            'processed_lines': 0,
            'errors': [(0, f"处理文件时发生意外错误: {e}")],
            'time': time.perf_counter() - start_time
        }