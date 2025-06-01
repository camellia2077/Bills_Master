import re
import os

# Regular expressions (can be defined here or passed if they need to be more dynamic)
RE_PARENT = r'^[A-Z]+[\u4e00-\u9fff]+$'
RE_CHILD = r'^[a-z]+(_[a-z]+)+$'
RE_ITEM = r'^(\d+\.?\d*)\s*(.*)$'

def parse_bill_file(file_path):
    """
    Parses a bill text file and yields structured data records.
    Each record is a dictionary indicating the type of data and its content.
    Order numbers are generated based on appearance.
    """
    parent_order = 0
    child_order_map = {} # Key: parent_title, Value: last child_order for that parent
    item_order_map = {}  # Key: child_title (scoped by current parent), Value: last item_order

    current_parent_title_for_child_scope = None
    current_child_title_for_item_scope = None
    expect_remark_for_year_month = None # Stores the year_month string expecting a remark

    print(f"  Parsing file: {os.path.basename(file_path)}")
    with open(file_path, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, 1):
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # Check for REMARK first if one is expected
            if expect_remark_for_year_month:
                if stripped_line.startswith('REMARK:'):
                    remark_text = stripped_line[7:].strip()
                    yield {
                        'type': 'remark',
                        'year_month': expect_remark_for_year_month,
                        'text': remark_text,
                        'line_num': line_num
                    }
                    expect_remark_for_year_month = None # Reset expectation
                    continue
                else:
                    # If a line is not a remark and one was expected,
                    # the expectation is cleared, and the line is processed normally.
                    expect_remark_for_year_month = None

            if stripped_line.startswith('DATE:'):
                year_month = stripped_line[5:].strip()
                if not re.fullmatch(r'^\d{6}$', year_month): # Basic validation
                    raise ValueError(f"Invalid DATE format '{year_month}' at line {line_num} in {file_path}. Expected YYYYMM.")
                yield {
                    'type': 'year_month',
                    'value': year_month,
                    'line_num': line_num
                }
                # Reset orders and current scope for the new date
                parent_order = 0
                child_order_map.clear()
                item_order_map.clear()
                current_parent_title_for_child_scope = None
                current_child_title_for_item_scope = None
                expect_remark_for_year_month = year_month # Expect a remark for this date
                print(f"    Parsed DATE: {year_month}")

            elif re.fullmatch(RE_PARENT, stripped_line):
                parent_order += 1
                current_parent_title_for_child_scope = stripped_line
                # Reset child and item order for this new parent
                child_order_map[current_parent_title_for_child_scope] = 0
                current_child_title_for_item_scope = None # New parent means child context is reset
                yield {
                    'type': 'parent',
                    'title': stripped_line,
                    'order_num': parent_order,
                    'line_num': line_num
                }
                print(f"      Parsed PARENT: {stripped_line} (Order: {parent_order})")


            elif current_parent_title_for_child_scope and \
                 re.fullmatch(RE_CHILD, stripped_line):
                # Get current child order for this parent, then increment
                current_child_order = child_order_map.get(current_parent_title_for_child_scope, 0) + 1
                child_order_map[current_parent_title_for_child_scope] = current_child_order
                current_child_title_for_item_scope = stripped_line
                # Reset item order for this new child
                item_order_map[current_child_title_for_item_scope] = 0
                yield {
                    'type': 'child',
                    'title': stripped_line,
                    'order_num': current_child_order,
                    'parent_title': current_parent_title_for_child_scope, # For context if needed by inserter
                    'line_num': line_num
                }
                print(f"        Parsed CHILD: {stripped_line} (Order: {current_child_order}) under {current_parent_title_for_child_scope}")

            elif current_parent_title_for_child_scope and \
                 current_child_title_for_item_scope: # Must be under a child
                match = re.match(RE_ITEM, stripped_line)
                if match:
                    amount = float(match.group(1))
                    description = match.group(2).strip()
                    # Get current item order for this child, then increment
                    current_item_order = item_order_map.get(current_child_title_for_item_scope, 0) + 1
                    item_order_map[current_child_title_for_item_scope] = current_item_order
                    yield {
                        'type': 'item',
                        'amount': amount,
                        'description': description,
                        'order_num': current_item_order,
                        'child_title': current_child_title_for_item_scope, # For context
                        'parent_title': current_parent_title_for_child_scope, # For context
                        'line_num': line_num
                    }
                    # print(f"          Parsed ITEM: {amount} {description} (Order: {current_item_order})") # Can be too verbose
                elif stripped_line and not stripped_line.startswith("REMARK:"): # Avoid error on empty or remark lines if not expected
                     # If it's not empty and not an item, and we are in item context, it's an unknown format
                    # However, if a remark was *not* expected here, this might be an error.
                    # For now, we assume valid files will only have items or be blank after a child.
                    # Or, it could be an error in the file structure.
                    print(f"        WARNING: Line {line_num}: '{stripped_line}' in {file_path} was not recognized as an item under child '{current_child_title_for_item_scope}'. It might be ignored or cause issues if it's not a blank line.")
            elif stripped_line: # A line that is not blank and doesn't match anything after DATE might be an error
                 raise ValueError(f"Line {line_num}: '{stripped_line}' in {file_path} is in an unexpected format or position. Ensure DATE is declared before other entries.")