

import re
import os
import shutil
import decimal
import json

# --- 内部核心功能函数 (已更新) ---

def _load_config(config_path):
    """(新增) 通用配置加载函数。"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 如果文件不存在或格式错误，返回空字典，让调用方处理
        return {}

def _sum_up_line(line):
    # ... 此函数代码无变化 ...
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


def _perform_initial_modifications(file_path, enable_summing, enable_autorenewal, renewal_rules):
    # ... 此函数逻辑无变化，仅依赖传入的 renewal_rules ...
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
                    if enable_autorenewal and current_child_title in renewal_rules:
                        items_to_add = renewal_rules[current_child_title]
                        for item in items_to_add:
                            amount = decimal.Decimal(str(item.get('amount', 0)))
                            description = item.get('description', '未知项目')
                            auto_renewal_desc_txt = description + "(自动续费)"
                            amount_str = format(amount.normalize(), 'f')
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
    # ... 此函数代码无变化 ...
    stripped = line.strip()
    if not stripped: return 'BLANK', stripped
    if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', stripped): return 'PARENT', stripped
    if re.fullmatch(r'^[a-z]+(?:_[a-z]+)+$', stripped): return 'SUB', stripped
    if re.match(r'^\d+(?:\.\d*)?', stripped): return 'CONTENT', stripped
    return 'OTHER', stripped

def _get_numeric_value_from_content(line_content):
    # ... 此函数代码无变化 ...
    match = re.match(r'^(\d+(?:\.\d*)?)', line_content.strip())
    return decimal.Decimal(match.group(1)) if match else decimal.Decimal('-1')

def _process_structured_modifications(file_path, enable_cleanup, enable_sorting):
    # ... 此函数代码无变化 ...
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        original_content = "".join(lines)
        log = []
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
        if enable_sorting:
            sorted_subs_count = 0
            for node in bill_structure:
                sub_nodes = []
                if node['type'] == 'PARENT':
                    sub_nodes = node.get('children', [])
                elif node['type'] == 'SUB':
                    sub_nodes = [node]
                for sub_node in sub_nodes:
                    if sub_node.get('children'):
                        sub_node['children'].sort(
                            key=lambda item: (
                                -_get_numeric_value_from_content(item['content']),
                                item['content']
                            )
                        )
                        sorted_subs_count += 1
            if sorted_subs_count > 0:
                log.append(f"对 {sorted_subs_count} 个子项目的内容进行了排序。")
        deleted_subs, deleted_parents = [], []
        if enable_cleanup:
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
            final_structure_after_cleanup = []
            for node in bill_structure:
                if node['type'] == 'PARENT':
                    if node.get('children'):
                        final_structure_after_cleanup.append(node)
                    else:
                        deleted_parents.append(node['content'].strip())
                elif node['type'] == 'SUB':
                    if node.get('children'):
                        final_structure_after_cleanup.append(node)
                else:
                    final_structure_after_cleanup.append(node)
            bill_structure = final_structure_after_cleanup
            if deleted_subs:
                log.append(f"删除了空子项目: {', '.join(deleted_subs)}")
            if deleted_parents:
                log.append(f"删除了空父项目: {', '.join(deleted_parents)}")
        new_lines = []
        for node in bill_structure:
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
            if not log:
                log.append("成功更新了文件格式。")
            return True, log
        else:
            return False, log
    except Exception as e:
        raise Exception(f"执行结构化修改时出错: {e}")

# --- 公开的API函数 (已更新) ---
def process_single_file(file_path, modifier_config_path, enable_summing, enable_autorenewal, enable_cleanup, enable_sorting):
    """(已更新) 处理单个文件，按顺序执行启用的所有修改功能。"""
    overall_modified = False
    log = []

    # 从指定的修改器配置文件加载规则
    config = _load_config(modifier_config_path)
    renewal_rules = config.get('auto_renewal_rules', {})

    # 阶段1: 行内修改 (求和, 自动续费)
    if enable_summing or (enable_autorenewal and renewal_rules):
        try:
            stage1_result = _perform_initial_modifications(
                file_path, enable_summing, enable_autorenewal, renewal_rules
            )
            if stage1_result['error']: return stage1_result
            overall_modified = stage1_result['modified']
            log.extend(stage1_result['log'])
        except Exception as e:
            return {'modified': False, 'log': log, 'error': str(e)}

    # 阶段2: 结构化修改 (排序, 清理)
    if enable_cleanup or enable_sorting:
        try:
            modified, stage2_log = _process_structured_modifications(file_path, enable_cleanup, enable_sorting)
            overall_modified = overall_modified or modified
            log.extend(stage2_log)
        except Exception as e:
            return {'modified': overall_modified, 'log': log, 'error': str(e)}
    
    if not overall_modified and not any(log):
        log.append(f"文件 {os.path.basename(file_path)} 未作任何修改。")
    
    return {'modified': overall_modified, 'log': list(dict.fromkeys(log)), 'error': None}