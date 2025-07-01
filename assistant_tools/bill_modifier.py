# bill_modifier.py (已更新日志功能)

import re
import os
import shutil
import decimal

# --- 模块配置 (无变动) ---
AUTO_RENEWAL_MAP = {
    "web_service": [
        (decimal.Decimal("25.0"), "迅雷加速器"),
    ],
}

# --- 内部核心功能函数 (无变动) ---
def _sum_up_line(line):
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
    stripped = line.strip()
    if not stripped: return 'BLANK', stripped
    if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', stripped): return 'PARENT', stripped
    if re.fullmatch(r'^[a-z]+(?:_[a-z]+)+$', stripped): return 'SUB', stripped
    if re.match(r'^\d+(?:\.\d*)?', stripped): return 'CONTENT', stripped
    return 'OTHER', stripped

# --- 功能函数 (已更新日志) ---
def _cleanup_empty_items(file_path):
    """(已更新) 清理文件中的空项目，并返回详细的清理日志。"""
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

        # !!!核心改动: 在过滤时记录被删除项!!!
        deleted_subs, deleted_parents = [], []
        
        # 步骤2A: 识别并收集空的子项目
        for node in bill_structure:
            if node['type'] == 'PARENT':
                kept_children = []
                for sub_node in node.get('children', []):
                    if sub_node.get('children'):
                        kept_children.append(sub_node)
                    else:
                        deleted_subs.append(sub_node['content'].strip())
                node['children'] = kept_children
            elif node['type'] == 'SUB' and not node.get('children'): # 处理孤立的空子项
                deleted_subs.append(node['content'].strip())

        # 步骤2B: 过滤结构，收集空的父项目
        final_structure = []
        for node in bill_structure:
            if node['type'] == 'PARENT':
                if node.get('children'):
                    final_structure.append(node)
                else:
                    deleted_parents.append(node['content'].strip())
            elif node['type'] == 'SUB': # 处理孤立的子项
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
            
            # 步骤4: 生成详细日志
            cleanup_log = []
            if deleted_subs:
                cleanup_log.append(f"删除了空子项目: {', '.join(deleted_subs)}")
            if deleted_parents:
                cleanup_log.append(f"删除了空父项目: {', '.join(deleted_parents)}")
            
            # 如果日志为空但文件被修改了（例如，只删了空行），提供通用消息
            if not cleanup_log:
                cleanup_log.append("成功清理了文件中的空行或格式。")
            
            return True, cleanup_log
        else:
            return False, []

    except Exception as e:
        raise Exception(f"清理空项目时出错: {e}")

# --- 公开的API函数 (无变动) ---
def process_single_file(file_path, enable_summing, enable_autorenewal, enable_cleanup):
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