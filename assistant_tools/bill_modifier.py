# bill_modifier.py

import re
import os
import shutil
import decimal

# --- 模块配置 ---
# 自动续费项目映射，这是模块的内部配置
AUTO_RENEWAL_MAP = {
    "web_service": [
        (decimal.Decimal("25.0"), "迅雷加速器"),
    ],
}

# --- 内部核心功能函数 ---
def _sum_up_line(line):
    """
    检查并计算行内的加法表达式。
    返回: (new_line, original_line_stripped) 或 (None, None)
    """
    match = re.match(r'^((?:\d+(?:\.\d+)?)(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*(.*)$', line)
    if match:
        numeric_part = match.group(1)
        description = match.group(2).strip()
        try:
            numbers = re.split(r'\s*\+\s*', numeric_part)
            total = sum(decimal.Decimal(num) for num in numbers)
            formatted_total = total.normalize()
            total_str = format(formatted_total, 'f')
            new_line = f"{total_str}{description}"
            return new_line, line
        except (decimal.InvalidOperation, ValueError):
            return None, None # 计算错误，不处理
    return None, None

# --- 公开的API函数 ---
def process_single_file(file_path, enable_summing, enable_autorenewal):
    """
    处理单个TXT文件，根据标志执行求和与添加自动续费功能。

    Args:
        file_path (str): 要处理的文件路径。
        enable_summing (bool): 是否启用行内求和。
        enable_autorenewal (bool): 是否启用自动续费添加。

    Returns:
        dict: 一个包含处理结果的字典，格式为:
              {
                  'modified': bool,
                  'log': list[str], # 操作日志
                  'error': str | None # 错误信息
              }
    """
    if not os.path.exists(file_path):
        return {'modified': False, 'log': [], 'error': f"文件不存在: {file_path}"}

    txt_modified = False
    log = []
    temp_file_path = file_path + ".tmp"
    current_child_title = None

    try:
        with open(file_path, 'r', encoding='utf-8-sig') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:

            original_lines = infile.readlines()
            all_content_str = "".join(original_lines) # 用于检查现有行

            for i, original_line in enumerate(original_lines):
                line_to_write = original_line
                
                # --- 功能1: 行内求和 ---
                if enable_summing and original_line.strip():
                    new_line_content, old_line_content = _sum_up_line(original_line.strip())
                    if new_line_content:
                        indentation = original_line[:-len(original_line.lstrip())]
                        line_to_write = indentation + new_line_content + '\n'
                        if line_to_write != original_line:
                            log.append(f"计算总和: '{old_line_content}' -> '{new_line_content}'")
                            txt_modified = True
                
                outfile.write(line_to_write)

                # --- 功能2: 添加自动续费 ---
                original_stripped = original_line.strip()
                if re.fullmatch(r'^[a-z]+(_[a-z]+)+$', original_stripped):
                    current_child_title = original_stripped
                    if enable_autorenewal and current_child_title in AUTO_RENEWAL_MAP:
                        items_to_add = AUTO_RENEWAL_MAP[current_child_title]
                        for amount, description in items_to_add:
                            auto_renewal_desc_txt = description + "(自动续费)"
                            amount_str = format(decimal.Decimal(amount).normalize(), 'f')
                            line_to_insert = f"{amount_str}{auto_renewal_desc_txt}"
                            
                            # 检查是否已存在
                            if line_to_insert not in all_content_str:
                                outfile.write(line_to_insert + '\n')
                                log.append(f"在'{current_child_title}'下添加了行: {line_to_insert}")
                                txt_modified = True
                
                elif not re.match(r'^(\d+\.?\d*)', original_stripped):
                    current_child_title = None

        if txt_modified:
            shutil.move(temp_file_path, file_path)
            log.append(f"文件 {os.path.basename(file_path)} 已成功更新。")
        else:
            os.remove(temp_file_path)
            log.append(f"文件 {os.path.basename(file_path)} 未作修改。")

        return {'modified': txt_modified, 'log': log, 'error': None}

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return {'modified': False, 'log': log, 'error': f"处理文件时发生意外错误: {e}"}