# BillProcessor.py
# 这个模块整合了 bill_validator.py 和 bill_modifier.py 的所有功能。

import re
import time
import json
import os
import shutil
import decimal
from collections import defaultdict

# ======================================================================
# 来自 bill_modifier.py 的常量和功能
# ======================================================================

# --- 模块配置 ---
AUTO_RENEWAL_MAP = {
    "web_service": [
        (decimal.Decimal("25.0"), "迅雷加速器"),
    ],
}

# --- 内部核心功能函数 ---
def _sum_up_line(line):
    """(无变动) 检查并计算行内的加法表达式。"""
    match = re.match(r'^((?:\d+(?:\.\d+)?)(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*(.*)$', line)
    if match:
        numeric_part = match.group(1)
        description = match.group(2).strip()
        try:
            numbers = re.split(r'\s*\+\s*', numeric_part)
            total = sum(decimal.Decimal(num) for num in numbers)
            total_str = f"{total:.2f}"
            new_line = f"{total_str}{description}"
            return new_line, line
        except (decimal.InvalidOperation, ValueError):
            return None, None
    return None, None

def _perform_initial_modifications(file_path, enable_summing, enable_autorenewal):
    """执行行内求和与添加自动续费。"""
    if not os.path.exists(file_path):
        return {'modified': False, 'log': [], 'error': f"文件不存在: {file_path}"}
    txt_modified = False
    log = []
    temp_file_path = file_path + ".tmp"
    current_child_title = None
    try:
        with open(file_path, 'r', encoding='utf-8') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:
            original_lines = infile.readlines()
            all_content_str = "".join(original_lines)
            for original_line in original_lines:
                line_to_write = original_line
                if enable_summing and original_line.strip():
                    new_line_content, old_line_content = _sum_up_line(original_line.strip())
                    if new_line_content:
                        indentation = original_line[:-len(original_line.lstrip())]
                        line_to_write = indentation + new_line_content + '\n'
                        if line_to_write != original_line:
                            log.append(f"计算总和: '{old_line_content}' -> '{new_line_content}'")
                            txt_modified = True
                outfile.write(line_to_write)
                original_stripped = original_line.strip()
                if re.fullmatch(r'^[a-z]+(_[a-z]+)+$', original_stripped):
                    current_child_title = original_stripped
                    if enable_autorenewal and current_child_title in AUTO_RENEWAL_MAP:
                        items_to_add = AUTO_RENEWAL_MAP[current_child_title]
                        for amount, description in items_to_add:
                            auto_renewal_desc_txt = description + "(自动续费)"
                            amount_str = format(decimal.Decimal(amount).normalize(), 'f')
                            line_to_insert = f"{amount_str}{auto_renewal_desc_txt}"
                            if line_to_insert not in all_content_str:
                                outfile.write(line_to_insert + '\n')
                                log.append(f"在'{current_child_title}'下添加了行: {line_to_insert}")
                                txt_modified = True
                elif not re.match(r'^(\d+\.?\d*)', original_stripped):
                    current_child_title = None
        if txt_modified:
            shutil.move(temp_file_path, file_path)
        else:
            os.remove(temp_file_path)
        return {'modified': txt_modified, 'log': log, 'error': None}
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return {'modified': False, 'log': log, 'error': f"处理文件时发生意外错误: {e}"}

def _get_line_type(line):
    """根据行内容判断其类型 (父项, 子项, 内容, 其他)。"""
    stripped = line.strip()
    if not stripped: return 'BLANK', stripped
    if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', stripped): return 'PARENT', stripped
    if re.fullmatch(r'^[a-z]+(?:_[a-z]+)+$', stripped): return 'SUB', stripped
    if re.match(r'^\d+(?:\.\d*)?', stripped): return 'CONTENT', stripped
    return 'OTHER', stripped

def _cleanup_empty_items(file_path):
    """清理文件中的空项目，并返回详细的清理日志。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        original_content = "".join(lines)
        bill_structure = []
        current_parent_node, current_sub_node = None, None
        for line in lines:
            line_type, _ = _get_line_type(line)
            if line_type == 'PARENT':
                node = {'type': 'PARENT', 'content': line, 'children': []}
                bill_structure.append(node)
                current_parent_node, current_sub_node = node, None
            elif line_type == 'SUB':
                node = {'type': 'SUB', 'content': line, 'children': []}
                if current_parent_node:
                    current_parent_node['children'].append(node)
                else:
                    bill_structure.append(node)
                current_sub_node = node
            elif line_type == 'CONTENT':
                if current_sub_node:
                    current_sub_node['children'].append({'type': 'CONTENT', 'content': line})
            else:
                bill_structure.append({'type': 'OTHER', 'content': line})
                current_parent_node, current_sub_node = None, None
        deleted_subs, deleted_parents = [], []
        for node in bill_structure:
            if node['type'] == 'PARENT':
                kept_children = []
                for sub_node in node.get('children', []):
                    if sub_node.get('children'):
                        kept_children.append(sub_node)
                    else:
                        deleted_subs.append(sub_node['content'].strip())
                node['children'] = kept_children
            elif node['type'] == 'SUB' and not node.get('children'):
                deleted_subs.append(node['content'].strip())
        final_structure = []
        for node in bill_structure:
            if node['type'] == 'PARENT':
                if node.get('children'):
                    final_structure.append(node)
                else:
                    deleted_parents.append(node['content'].strip())
            elif node['type'] == 'SUB':
                if node.get('children'):
                    final_structure.append(node)
            else:
                final_structure.append(node)
        new_lines = []
        for node in final_structure:
            new_lines.append(node['content'])
            if node.get('children'):
                for child_node in node['children']:
                    new_lines.append(child_node['content'])
                    if child_node.get('children'):
                        for content_node in child_node['children']:
                            new_lines.append(content_node['content'])
        new_content = "".join(new_lines)
        if new_content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            cleanup_log = []
            if deleted_subs:
                cleanup_log.append(f"删除了空子项目: {', '.join(deleted_subs)}")
            if deleted_parents:
                cleanup_log.append(f"删除了空父项目: {', '.join(deleted_parents)}")
            if not cleanup_log:
                cleanup_log.append("成功清理了文件中的空行或格式。")
            return True, cleanup_log
        else:
            return False, []
    except Exception as e:
        raise Exception(f"清理空项目时出错: {e}")

def process_single_file(file_path, enable_summing, enable_autorenewal, enable_cleanup):
    """公开API：处理单个文件，按顺序执行启用的所有修改功能。"""
    overall_modified = False
    log = []
    if enable_summing or enable_autorenewal:
        try:
            stage1_result = _perform_initial_modifications(file_path, enable_summing, enable_autorenewal)
            if stage1_result['error']:
                return stage1_result
            overall_modified = overall_modified or stage1_result['modified']
            log.extend(stage1_result['log'])
        except Exception as e:
            return {'modified': False, 'log': log, 'error': str(e)}
    if enable_cleanup:
        try:
            cleanup_modified, cleanup_log = _cleanup_empty_items(file_path)
            overall_modified = overall_modified or cleanup_modified
            log.extend(cleanup_log)
        except Exception as e:
            return {'modified': overall_modified, 'log': log, 'error': str(e)}
    if not overall_modified:
        log.append(f"文件 {os.path.basename(file_path)} 未作任何修改。")
    return {'modified': overall_modified, 'log': list(dict.fromkeys(log)), 'error': None}


# ======================================================================
# 来自 bill_validator.py 的功能
# ======================================================================

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

def validate_file(file_path, config_path):
    """公开API：验证单个账单文件格式，并根据JSON配置文件校验父项和子项。"""
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
        raw_config = _load_config(config_path)
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