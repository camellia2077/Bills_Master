# bill_validator.py

import re
import time
from collections import defaultdict

# 验证逻辑函数（大部分从原文件中复制而来）
# 我们将一些内部帮助函数标记为“私有”（以_开头），这是一种惯例
def _check_parent_title_format(line):
    """
    检查行是否符合父标题的所有规则 (格式 + 必须含汉字)。
    返回:
      0: 完全有效
      1: 格式基本正确，但缺少汉字
      2: 格式无效
    """
    if re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
        if re.search(r'[\u4e00-\u9fff]', line):
            return 0
        else:
            return 1
    else:
        return 2

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

# --- 状态处理函数（保持不变，也可以加_前缀） ---
def _handle_parent_state(line, lineno, state):
    status = _check_parent_title_format(line)
    if status == 0:
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        return []
    elif status == 1:
        return [(lineno, "父级标题格式正确但缺少汉字")]
    else:
        return [(lineno, "期望父级标题 (格式: 大写字母开头, 必须含汉字, 可有数字), 但找到不匹配的内容")]

def _handle_sub_state(line, lineno, state):
    errors = []
    current_parent = state['current_parent']
    if not current_parent:
        return [(lineno, "未找到父级标题")]
    
    parent_lineno, parent_line = current_parent
    match = re.match(r'^([A-Z]+)', parent_line)
    if not match:
        return [(parent_lineno, "父级标题格式错误")]
    
    expected_prefix = f"{match.group(1).lower()}_"
    if re.fullmatch(f"^{expected_prefix}[a-z]+$", line):
        new_sub = (lineno, line)
        state['subs'][current_parent].append(new_sub)
        state['current_sub'] = new_sub
        state['expecting'] = 'content'
    elif _check_parent_title_format(line) == 0:
        errors.append((current_parent[0], "父级标题缺少子标题"))
        state['current_parent'] = (lineno, line)
        state['parents'].append(state['current_parent'])
        state['expecting'] = 'sub'
    else:
        errors.append((lineno, f"子标题应以{expected_prefix}开头且仅含小写字母"))
    return errors

def _handle_content_state(line, lineno, state):
    errors = []
    current_sub = state['current_sub']
    current_parent = state['current_parent']

    is_content = re.fullmatch(r'^\d+(?:\.\d+)?(?:[^\d\s][\d\u4e00-\u9fffa-zA-Z_-]*)+$', line)
    parent_check_status = _check_parent_title_format(line)

    is_new_sub = False
    if current_parent:
        parent_initials_match = re.match(r'^([A-Z]+)', current_parent[1])
        if parent_initials_match:
             expected_sub_prefix = f"{parent_initials_match.group(1).lower()}_"
             is_new_sub = re.fullmatch(f"^{expected_sub_prefix}[a-z]+$", line)

    if is_content:
        if not current_sub:
             errors.append((lineno, "找到内容行，但当前没有活动的子标题"))
        else:
             state['content_counts'][current_sub] += 1
    elif parent_check_status == 0:
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
    elif parent_check_status == 1:
         errors.append((lineno, "父级标题格式正确但缺少汉字"))
    else:
         errors.append((lineno, "期望内容行、新子标题或新父标题, 但找到其他内容"))
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
    # 检查未闭合的父标题
    if state['expecting'] == 'sub' and state['current_parent']:
        errors.append((state['current_parent'][0], "父级标题缺少子标题"))
    # 检查未闭合的子标题
    elif state['expecting'] == 'content' and state['current_sub']:
        if state['content_counts'][state['current_sub']] == 0:
            errors.append((state['current_sub'][0], "子标题缺少内容行"))
    # 检查所有父标题是否有子标题
    for parent in state['parents']:
        if not state['subs'].get(parent):
            # 避免重复报错
            if (parent[0], "父级标题缺少子标题") not in errors:
                errors.append((parent[0], "父级标题缺少子标题"))
    return errors

# --- 公开的API函数 ---
def validate_file(file_path):
    """
    验证单个账单文件格式。这是此模块的主要入口点。

    Args:
        file_path (str): 要验证的文件的路径。

    Returns:
        dict: 一个包含验证结果的字典，格式为:
              {
                  'processed_lines': int,
                  'errors': list[tuple(int, str)],
                  'time': float
              }
    """
    start_time = time.perf_counter()
    state = {
        'expecting': 'parent',
        'current_parent': None,
        'current_sub': None,
        'parents': [],
        'subs': defaultdict(list),
        'content_counts': defaultdict(int),
        'errors': []
    }
    
    try:
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
    except Exception as e:
        # 模块应该向上抛出异常或在结果中报告它
        return {
            'processed_lines': 0,
            'errors': [(0, f"处理文件时发生意外错误: {e}")],
            'time': time.perf_counter() - start_time
        }