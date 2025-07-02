import re
import os

# 为错误信息添加颜色
RED = "\033[31m"
RESET = "\033[0m"

# Regular expressions (can be defined here or passed if they need to be more dynamic)
RE_PARENT = r'^[A-Z]+[\u4e00-\u9fff]+$'
RE_CHILD = r'^[a-z]+(_[a-z]+)+$'
RE_ITEM = r'^(\d+\.?\d*)\s*(.*)$'

def parse_bill_file(file_path):
    """
    Parses a bill text file.
    On success, returns a tuple: (True, list_of_records).
    On failure, prints an error message and returns (False, None).
    """
    records = []  # MODIFIED: Collect records in a list instead of yielding
    parent_order = 0
    child_order_map = {} # Key: parent_title, Value: last child_order for that parent
    item_order_map = {}  # Key: child_title (scoped by current parent), Value: last item_order

    current_parent_title_for_child_scope = None
    current_child_title_for_item_scope = None
    expect_remark_for_year_month = None # Stores the year_month string expecting a remark

    # NEW: Wrap the entire parsing process in a try-except block
    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            for line_num, line in enumerate(infile, 1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                # Check for REMARK first if one is expected
                if expect_remark_for_year_month:
                    if stripped_line.startswith('REMARK:'):
                        remark_text = stripped_line[7:].strip()
                        # MODIFIED: Append instead of yield
                        records.append({
                            'type': 'remark',
                            'year_month': expect_remark_for_year_month,
                            'text': remark_text,
                            'line_num': line_num
                        })
                        expect_remark_for_year_month = None # Reset expectation
                        continue
                    else:
                        expect_remark_for_year_month = None

                if stripped_line.startswith('DATE:'):
                    year_month = stripped_line[5:].strip()
                    if not re.fullmatch(r'^\d{6}$', year_month):
                        raise ValueError(f"Invalid DATE format '{year_month}' at line {line_num} in {file_path}. Expected YYYYMM.")
                    # MODIFIED: Append instead of yield
                    records.append({
                        'type': 'year_month',
                        'value': year_month,
                        'line_num': line_num
                    })
                    parent_order = 0
                    child_order_map.clear()
                    item_order_map.clear()
                    current_parent_title_for_child_scope = None
                    current_child_title_for_item_scope = None
                    expect_remark_for_year_month = year_month

                elif re.fullmatch(RE_PARENT, stripped_line):
                    parent_order += 1
                    current_parent_title_for_child_scope = stripped_line
                    child_order_map[current_parent_title_for_child_scope] = 0
                    current_child_title_for_item_scope = None
                    # MODIFIED: Append instead of yield
                    records.append({
                        'type': 'parent',
                        'title': stripped_line,
                        'order_num': parent_order,
                        'line_num': line_num
                    })

                elif current_parent_title_for_child_scope and re.fullmatch(RE_CHILD, stripped_line):
                    current_child_order = child_order_map.get(current_parent_title_for_child_scope, 0) + 1
                    child_order_map[current_parent_title_for_child_scope] = current_child_order
                    current_child_title_for_item_scope = stripped_line
                    item_order_map[current_child_title_for_item_scope] = 0
                    # MODIFIED: Append instead of yield
                    records.append({
                        'type': 'child',
                        'title': stripped_line,
                        'order_num': current_child_order,
                        'parent_title': current_parent_title_for_child_scope,
                        'line_num': line_num
                    })

                elif current_parent_title_for_child_scope and current_child_title_for_item_scope:
                    match = re.match(RE_ITEM, stripped_line)
                    if match:
                        amount = float(match.group(1))
                        description = match.group(2).strip()
                        current_item_order = item_order_map.get(current_child_title_for_item_scope, 0) + 1
                        item_order_map[current_child_title_for_item_scope] = current_item_order
                        # MODIFIED: Append instead of yield
                        records.append({
                            'type': 'item',
                            'amount': amount,
                            'description': description,
                            'order_num': current_item_order,
                            'child_title': current_child_title_for_item_scope,
                            'parent_title': current_parent_title_for_child_scope,
                            'line_num': line_num
                        })
                    elif stripped_line and not stripped_line.startswith("REMARK:"):
                        pass
                elif stripped_line:
                     raise ValueError(f"Line {line_num}: '{stripped_line}' in {file_path} is in an unexpected format or position. Ensure DATE is declared before other entries.")
        
        # NEW: Return True and the collected data on success
        return True, records

    except (ValueError, IOError) as e:
        # NEW: Catch any error, print it, and return False
        print(f"{RED}Error parsing file '{os.path.basename(file_path)}': {e}{RESET}")
        return False, None