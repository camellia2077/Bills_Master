import re
import os
import shutil
import decimal
import json
from .status_logger import log_info, log_error

def _load_config(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _sum_up_line(line):
    match = re.match(r'^((?:\d+(?:\.\d+)?)(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*(.*)$', line)
    if match:
        numeric_part = match.group(1)
        description = match.group(2).strip()
        try:
            numbers = re.split(r'\s*\+\s*', numeric_part)
            total = sum(decimal.Decimal(num) for num in numbers)
            return f"{total:.2f}{description}", line
        except (decimal.InvalidOperation, ValueError):
            return None, None
    return None, None

def _perform_initial_modifications(file_path, enable_summing, enable_autorenewal, renewal_rules):
    if not os.path.exists(file_path):
        log_error(f"File not found: {file_path}")
        return False
    txt_modified = False
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
                            log_info(f"Calculated sum: '{old_line_content}' -> '{new_line_content}'")
                            txt_modified = True
                outfile.write(line_to_write)
                original_stripped = original_line.strip()
                if re.fullmatch(r'^[a-z]+(_[a-z]+)+$', original_stripped):
                    current_child_title = original_stripped
                    if enable_autorenewal and current_child_title in renewal_rules:
                        for item in renewal_rules.get(current_child_title, []):
                            amount = decimal.Decimal(str(item.get('amount', 0)))
                            description = item.get('description', 'Unknown Item')
                            line_to_insert = f"{amount.normalize():f}{description}(auto-renewal)"
                            if line_to_insert not in all_content_str:
                                outfile.write(line_to_insert + '\n')
                                log_info(f"Added line under '{current_child_title}': {line_to_insert}")
                                txt_modified = True
                elif not re.match(r'^(\d+\.?\d*)', original_stripped):
                    current_child_title = None
        if txt_modified:
            shutil.move(temp_file_path, file_path)
        else:
            os.remove(temp_file_path)
        return True
    except Exception as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        log_error(f"An unexpected error occurred during initial modifications: {e}")
        return False

def _get_line_type(line):
    stripped = line.strip()
    if not stripped: return 'BLANK', stripped
    if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+[\d]*$', stripped): return 'PARENT', stripped
    if re.fullmatch(r'^[a-z]+(?:_[a-z]+)+$', stripped): return 'SUB', stripped
    if re.match(r'^\d+(?:\.\d*)?', stripped): return 'CONTENT', stripped
    return 'OTHER', stripped

def _get_numeric_value_from_content(line_content):
    match = re.match(r'^(\d+(?:\.\d*)?)', line_content.strip())
    return decimal.Decimal(match.group(1)) if match else decimal.Decimal('-1')

def _process_structured_modifications(file_path, enable_cleanup, enable_sorting):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: lines = f.readlines()
        original_content = "".join(lines)
        bill_structure, current_parent_node, current_sub_node = [], None, None
        for line in lines:
            line_type, _ = _get_line_type(line)
            if line_type == 'PARENT':
                current_parent_node = {'type': 'PARENT', 'content': line, 'children': []}
                bill_structure.append(current_parent_node)
                current_sub_node = None
            elif line_type == 'SUB':
                current_sub_node = {'type': 'SUB', 'content': line, 'children': []}
                if current_parent_node: current_parent_node['children'].append(current_sub_node)
                else: bill_structure.append(current_sub_node)
            elif line_type == 'CONTENT' and current_sub_node:
                current_sub_node['children'].append({'type': 'CONTENT', 'content': line})
            else:
                bill_structure.append({'type': 'OTHER', 'content': line})
                current_parent_node, current_sub_node = None, None
        
        if enable_sorting:
            sorted_subs_count = 0
            for node in bill_structure:
                sub_nodes = node.get('children', []) if node['type'] == 'PARENT' else ([node] if node['type'] == 'SUB' else [])
                for sub_node in sub_nodes:
                    if sub_node.get('children'):
                        sub_node['children'].sort(key=lambda item: (-_get_numeric_value_from_content(item['content']), item['content']))
                        sorted_subs_count += 1
            if sorted_subs_count > 0: log_info(f"Sorted content for {sorted_subs_count} sub-items.")

        if enable_cleanup:
            for node in bill_structure:
                if node['type'] == 'PARENT':
                    deleted_subs = [child['content'].strip() for child in node.get('children', []) if not child.get('children')]
                    node['children'] = [child for child in node.get('children', []) if child.get('children')]
                    if deleted_subs: log_info(f"Deleted empty sub-items: {', '.join(deleted_subs)}")
            final_structure = [node for node in bill_structure if not (node['type'] == 'PARENT' and not node.get('children')) and not (node['type'] == 'SUB' and not node.get('children'))]
            if len(final_structure) < len(bill_structure): log_info("Deleted parent items that became empty.")
            bill_structure = final_structure

        new_lines = [node['content'] for node in bill_structure]
        for node in bill_structure:
            for child_node in node.get('children', []):
                new_lines.append(child_node['content'])
                for content_node in child_node.get('children', []):
                    new_lines.append(content_node['content'])
        
        new_content = "".join(new_lines)
        if new_content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f: f.write(new_content)
        return True
    except Exception as e:
        log_error(f"An unexpected error occurred during structured modifications: {e}")
        return False

def process_single_file(file_path, modifier_config_path, enable_summing, enable_autorenewal, enable_cleanup, enable_sorting):
    config = _load_config(modifier_config_path)
    renewal_rules = config.get('auto_renewal_rules', {})
    
    if enable_summing or (enable_autorenewal and renewal_rules):
        if not _perform_initial_modifications(file_path, enable_summing, enable_autorenewal, renewal_rules): return False
            
    if enable_cleanup or enable_sorting:
        if not _process_structured_modifications(file_path, enable_cleanup, enable_sorting): return False
            
    return True