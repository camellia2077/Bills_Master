import re
import time
import json
from collections import defaultdict

# --- 辅助函数 ---
def _load_config(config_path):
    """加载并解析JSON配置文件。"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _transform_config_for_validation(config_data):
    """将新的结构化配置转换为验证逻辑所需的简单字典格式。"""
    validation_map = {}
    if 'categories' not in config_data or not isinstance(config_data['categories'], list):
        return {}
    for category in config_data.get('categories', []):
        if isinstance(category, dict) and 'parent_item' in category and 'sub_items' in category:
            parent_name = category['parent_item']
            sub_items_list = category['sub_items']
            validation_map[parent_name] = sub_items_list
    return validation_map

# --- 核心验证逻辑函数 (已更新) ---
def _read_and_preprocess(file_path):
    """逐行读取文件并预处理行"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [(lineno, line.strip()) for lineno, line in enumerate(f, 1) if line.strip()]

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
    """处理父标题状态"""
    if line in state['config']:
        state['current_parent'] = (lineno, line)
        state['parents'].add(state['current_parent'])
        state['expecting'] = 'sub'
        return []
    elif re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', line):
        return [(lineno, f"父标题 '{line}' 不在配置文件中")]
    else:
        return [(lineno, "期望一个在配置文件中定义的父级标题, 但找到不匹配的内容")]

def _handle_sub_state(line, lineno, state):
    """处理子标题状态"""
    errors = []
    current_parent = state['current_parent']
    if not current_parent:
        return [(lineno, "未找到父级标题")]
    
    parent_lineno, parent_name = current_parent
    valid_subs = state['config'].get(parent_name, [])

    if line in valid_subs:
        state['current_sub'] = (lineno, line)
        state['subs'][current_parent].add(state['current_sub'])
        state['expecting'] = 'content'
    elif line in state['config']:
        errors.append((parent_lineno, f"父级标题 '{parent_name}' 缺少子标题"))
        state['current_parent'] = (lineno, line)
        state['parents'].add(state['current_parent'])
        state['expecting'] = 'sub'
    else:
        errors.append((lineno, f"子标题 '{line}' 对于父级标题 '{parent_name}' 无效, 或该行不是一个有效的父标题"))
    return errors

def _handle_content_state(line, lineno, state):
    """处理内容状态"""
    errors = []
    current_sub = state['current_sub']
    current_parent = state['current_parent']
    is_content = re.fullmatch(r'^\d+(?:\.\d+)?(?:[^\d\s][\d\u4e00-\u9fffa-zA-Z_-]*)+$', line)
    is_new_parent = line in state['config']
    is_new_sub = current_parent and line in state['config'].get(current_parent[1], [])

    if is_content:
        if not current_sub:
            errors.append((lineno, "找到内容行，但当前没有活动的子标题"))
        else:
            state['content_counts'][current_sub] += 1
    elif is_new_parent:
        if current_sub and state['content_counts'][current_sub] == 0:
            state['warnings'].append((current_sub[0], f"子标题 '{current_sub[1]}' 缺少内容行"))
        state['current_parent'] = (lineno, line)
        state['parents'].add(state['current_parent'])
        state['current_sub'] = None
        state['expecting'] = 'sub'
    elif is_new_sub:
        if current_sub and state['content_counts'][current_sub] == 0:
            state['warnings'].append((current_sub[0], f"子标题 '{current_sub[1]}' 缺少内容行"))
        state['current_sub'] = (lineno, line)
        state['subs'][current_parent].add(state['current_sub'])
        state['expecting'] = 'content'
    else:
        errors.append((lineno, "期望内容行、配置文件中有效的子标题或父标题, 但找到其他内容"))
    return errors

def _process_lines(lines, state):
    """处理所有数据行"""
    for i in range(2, len(lines)):
        lineno, line = lines[i]
        handler = { 'parent': _handle_parent_state, 'sub': _handle_sub_state, 'content': _handle_content_state }[state['expecting']]
        state['errors'].extend(handler(line, lineno, state))

def _post_validation_checks(state):
    """后处理验证检查，现在返回(errors, warnings)"""
    errors, warnings = [], []
    # 检查最后的子标题是否为空
    if state['expecting'] == 'content' and state['current_sub'] and state['content_counts'][state['current_sub']] == 0:
        warnings.append((state['current_sub'][0], f"子标题 '{state['current_sub'][1]}' 缺少内容行"))
    
    # 检查父标题是否缺少子标题，以及父标题下所有子标题是否都为空
    for parent in state['parents']:
        subs_of_parent = state['subs'].get(parent)
        if not subs_of_parent:
            errors.append((parent[0], f"父级标题 '{parent[1]}' 缺少子标题"))
        # 如果父标题有子标题，但所有子标题内容都为空，现在是警告
        elif all(state['content_counts'][sub] == 0 for sub in subs_of_parent):
            # <<< THIS LINE HAS BEEN CHANGED FROM errors.append TO warnings.append >>>
            warnings.append((parent[0], f"父标题 '{parent[1]}' 的所有子标题均缺少内容行"))
            
    return errors, warnings

def validate_file(file_path, config_path):
    """验证单个账单文件，返回 (is_valid: bool, result: dict)"""
    start_time = time.perf_counter()
    state = {
        'expecting': 'parent', 'current_parent': None, 'current_sub': None,
        'parents': set(), 'subs': defaultdict(set), 'content_counts': defaultdict(int),
        'errors': [], 'warnings': [], 'config': {}
    }
    
    def format_return(is_valid, processed_lines, errors, warnings, time_taken):
        unique_errors = sorted(list(set(errors)), key=lambda x: x[0])
        unique_warnings = sorted(list(set(warnings)), key=lambda x: x[0])
        result = {
            'processed_lines': processed_lines, 'errors': unique_errors,
            'warnings': unique_warnings, 'time': time_taken
        }
        return (is_valid, result)

    try:
        raw_config = _load_config(config_path)
        state['config'] = _transform_config_for_validation(raw_config)
        
        if not state['config']:
            return format_return(False, 0, [(0, f"错误: 配置文件 '{config_path}' 格式不正确或内容为空。")], [], time.perf_counter() - start_time)
        
        lines = _read_and_preprocess(file_path)
        state['errors'].extend(_validate_date_and_remark(lines))
        
        if len(lines) >= 2:
            _process_lines(lines, state)
        
        post_errors, post_warnings = _post_validation_checks(state)
        state['errors'].extend(post_errors)
        state['warnings'].extend(post_warnings)
        
        is_valid = not bool(state['errors'])
        return format_return(is_valid, len(lines), state['errors'], state['warnings'], time.perf_counter() - start_time)

    except FileNotFoundError:
        return format_return(False, 0, [(0, f"错误: 文件 '{file_path}' 或配置文件 '{config_path}' 未找到。")], [], time.perf_counter() - start_time)
    except Exception as e:
        return format_return(False, 0, [(0, f"处理文件时发生意外错误: {e}")], [], time.perf_counter() - start_time)