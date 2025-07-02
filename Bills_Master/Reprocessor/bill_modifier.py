import re
import os
import shutil
import decimal
import json
from .status_logger import log_info, log_error

# _load_config, _sum_up_line, _perform_initial_modifications, _get_line_type, _get_numeric_value_from_content 函数保持不变
def _load_config(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_error(f"Failed to load or parse config file: {config_path}")
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

# --- MODIFIED: This function now accepts formatting rules from the config ---
def _reconstruct_content_with_formatting(bill_structure, formatting_rules):
    """
    Reconstructs the file content from the structure with improved formatting
    based on rules from the config file.
    """
    # Get formatting rules from config, with default values for safety
    lines_after_parent_section = formatting_rules.get('lines_after_parent_section', 2)
    lines_after_parent_title = formatting_rules.get('lines_after_parent_title', 1)
    lines_between_sub_items = formatting_rules.get('lines_between_sub_items', 1)

    output_lines = []
    num_top_nodes = len(bill_structure)

    for i, node in enumerate(bill_structure):
        node_type = node.get('type')

        if node_type != 'PARENT':
            output_lines.append(node['content'].strip())
            continue

        output_lines.append(node['content'].strip())
        children = node.get('children', [])
        
        if children:
            # Rule: Add blank lines between parent and first sub-item
            for _ in range(lines_after_parent_title):
                output_lines.append('')

            num_children = len(children)
            for j, child_node in enumerate(children):
                output_lines.append(child_node['content'].strip())
                for content_node in child_node.get('children', []):
                    output_lines.append(content_node['content'].strip())

                # Rule: Add blank lines between sub-items
                if j < num_children - 1:
                    for _ in range(lines_between_sub_items):
                        output_lines.append('')
        
        # Rule: Add blank lines after the entire parent section
        if i < num_top_nodes - 1:
            for _ in range(lines_after_parent_section):
                output_lines.append('')

    return '\n'.join(output_lines) + '\n'


# --- MODIFIED: This function now passes the config down ---
def _process_structured_modifications(file_path, enable_cleanup, enable_sorting, config):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        original_content = "".join(lines)
        processed_lines = [line for line in lines if line.strip()]
        
        if not processed_lines:
            return True

        bill_structure, current_parent_node, current_sub_node = [], None, None
        
        for line in processed_lines:
            line_type, _ = _get_line_type(line)
            if line_type == 'PARENT':
                current_parent_node = {'type': 'PARENT', 'content': line, 'children': []}
                bill_structure.append(current_parent_node)
                current_sub_node = None
            elif line_type == 'SUB':
                current_sub_node = {'type': 'SUB', 'content': line, 'children': []}
                if current_parent_node:
                    current_parent_node['children'].append(current_sub_node)
                else:
                    bill_structure.append(current_sub_node)
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
            if sorted_subs_count > 0:
                log_info(f"Sorted content for {sorted_subs_count} sub-items.")

        if enable_cleanup:
            for node in bill_structure:
                if node['type'] == 'PARENT':
                    deleted_subs = [child['content'].strip() for child in node.get('children', []) if not child.get('children')]
                    node['children'] = [child for child in node.get('children', []) if child.get('children')]
                    if deleted_subs:
                        log_info(f"Deleted empty sub-items: {', '.join(deleted_subs)}")
            final_structure = [node for node in bill_structure if not (node['type'] == 'PARENT' and not node.get('children')) and not (node['type'] == 'SUB' and not node.get('children'))]
            if len(final_structure) < len(bill_structure):
                log_info("Deleted parent items that became empty.")
            bill_structure = final_structure

        # --- MODIFIED: Pass the formatting rules from the config ---
        formatting_rules = config.get('formatting_rules', {})
        new_content = _reconstruct_content_with_formatting(bill_structure, formatting_rules)
        
        if new_content.strip() != original_content.strip():
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        return True
    except Exception as e:
        log_error(f"An unexpected error occurred during structured modifications: {e}")
        return False

def process_single_file(file_path: str, modifier_config_path: str) -> bool:
    """
    Processes a single file based on settings from the modifier config file.
    """
    config = _load_config(modifier_config_path)
    
    flags = config.get('modification_flags', {})
    enable_summing = flags.get('enable_summing', False)
    enable_autorenewal = flags.get('enable_autorenewal', False)
    enable_cleanup = flags.get('enable_cleanup', False)
    enable_sorting = flags.get('enable_sorting', False)
    
    renewal_rules = config.get('auto_renewal_rules', {})
    
    log_info(f"Summing: {'Enabled' if enable_summing else 'Disabled'}")
    log_info(f"Auto-renewal: {'Enabled' if enable_autorenewal else 'Disabled'}")
    log_info(f"Cleanup: {'Enabled' if enable_cleanup else 'Disabled'}")
    log_info(f"Sorting: {'Enabled' if enable_sorting else 'Disabled'}")

    if enable_summing or (enable_autorenewal and renewal_rules):
        if not _perform_initial_modifications(file_path, enable_summing, enable_autorenewal, renewal_rules): 
            return False
            
    if enable_cleanup or enable_sorting:
        # --- MODIFIED: Pass the entire config object down ---
        if not _process_structured_modifications(file_path, enable_cleanup, enable_sorting, config): 
            return False
            
    return True