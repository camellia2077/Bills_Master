# bill_validator.py (已更新以处理新的JSON结构)

import re
import time
import json
from collections import defaultdict

# --- 辅助函数 ---
def _load_config(config_path):
    """加载并解析JSON配置文件。"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- 新增: 配置转换函数 ---
def _transform_config_for_validation(config_data):
    """将新的结构化配置转换为验证逻辑所需的简单字典格式。"""
    validation_map = {}
    if 'categories' not in config_data or not isinstance(config_data['categories'], list):
        return {}  # 如果顶层结构不对，返回空字典

    for category in config_data.get('categories', []):
        if isinstance(category, dict) and 'parent_item' in category and 'sub_items' in category:
            parent_name = category['parent_item']
            sub_items_list = category['sub_items']
            validation_map[parent_name] = sub_items_list
    return validation_map

# --- 核心验证逻辑函数 (保持不变) ---
# _read_and_preprocess, _validate_date_and_remark, _handle_parent_state, 
# _handle_sub_state, _handle_content_state, _process_lines, _post_validation_checks
# 这些函数完全不需要任何修改，因为我们将配置转换回了它们期望的格式。
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

def _handle_parent_state(line, lineno, state):
    """处理父标题状态，验证标题是否在配置中"""
    if line in state['config']:
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        return []
    else:
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

    if line in valid_subs:
        new_sub = (lineno, line)
        state['subs'][current_parent].append(new_sub)
        state['current_sub'] = new_sub
        state['expecting'] = 'content'
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
    """后处理验证检查"""
    errors = []
    if state['expecting'] == 'sub' and state['current_parent']:
        errors.append((state['current_parent'][0], f"父级标题 '{state['current_parent'][1]}' 缺少子标题"))
    elif state['expecting'] == 'content' and state['current_sub']:
        if state['content_counts'][state['current_sub']] == 0:
            errors.append((state['current_sub'][0], "子标题缺少内容行"))
    for parent in state['parents']:
        if not state['subs'].get(parent):
            err_tuple = (parent[0], f"父级标题 '{parent[1]}' 缺少子标题")
            if err_tuple not in errors:
                errors.append(err_tuple)
    return errors

# --- 公开的API函数 (已更新) ---
def validate_file(file_path, config_path):
    """
    验证单个账单文件格式，并根据JSON配置文件校验父项和子项。
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
        'config': {}
    }
    
    try:
        # !!!核心改动!!!
        # 步骤 1: 加载原始的、结构化的JSON文件
        raw_config = _load_config(config_path)
        # 步骤 2: 将其转换为验证逻辑所需的简单字典格式
        state['config'] = _transform_config_for_validation(raw_config)
        
        if not state['config']:
            return {
                'processed_lines': 0,
                'errors': [(0, f"错误: 配置文件 '{config_path}' 格式不正确或内容为空。")],
                'time': time.perf_counter() - start_time
            }
        
        lines = _read_and_preprocess(file_path)
        processed_lines = len(lines)
        
        state['errors'].extend(_validate_date_and_remark(lines))
        
        if len(lines) >= 2:
            _process_lines(lines, state)
        
        state['errors'].extend(_post_validation_checks(state))
        
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