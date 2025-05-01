import re
import os
import shutil
import time
import decimal # Use Decimal for accurate financial calculations

# ANSI 转义码_颜色代码
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- 新增: 功能开关 ---
ENABLE_SUM_UP_LINES = True      # 设置为 True 开启行内加法计算功能, False 关闭
ENABLE_ADD_AUTORENEWAL = True  # 设置为 True 开启添加自动续费功能, False 关闭
# --- 新增结束 ---

# 自动续费项目映射
AUTO_RENEWAL_MAP = {
    "web_service": [
        #(decimal.Decimal("15.0"), "uu加速器"), # Use Decimal
        (decimal.Decimal("25.0"), "迅雷加速器"), # Use Decimal
    ],
}

# --- 行内求和功能 ---
def sum_up_line(line):
    """
    检查单行是否包含 '数字+数字+...' 格式, 如果是则计算总和并返回新行.
    例如: '355+8.5+11+10+4吃饭' -> '388.5吃饭' (注意: 示例修改为无空格)
    返回: 计算后的行字符串 或 None (如果不匹配格式或计算出错)
    """
    # Regex to find lines starting with number(s) separated by '+' followed by a description
    match = re.match(r'^((?:\d+(?:\.\d+)?)(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*(.*)$', line)

    if match:
        numeric_part = match.group(1)
        description = match.group(2).strip()
        total = decimal.Decimal(0)
        numbers = re.split(r'\s*\+\s*', numeric_part)

        try:
            for num_str in numbers:
                total += decimal.Decimal(num_str)

            formatted_total = total.normalize()
            total_str = format(formatted_total, 'f')

            # Combine total and description (数字和描述紧邻)
            new_line = f"{total_str}{description}"
            return new_line
        except (decimal.InvalidOperation, ValueError) as e:
            print(f"{YELLOW}警告: 计算行内和时出错 (行: '{line}'): {e}{RESET}")
            return None
    return None
# --- 行内求和功能结束 ---

def process_single_file(file_path, enable_summing, enable_autorenewal):
    """
    处理单个 TXT 文件:
    根据传入的布尔标志决定是否执行:
    1. 对符合 '数字+数字...' 格式的行进行求和计算 (如果 enable_summing is True).
    2. 在特定子标题下添加自动续费项目 (如果 enable_autorenewal is True).
    将结果写入临时文件, 如果有修改则替换原文件.
    返回 True 如果文件被修改, 否则返回 False.
    """
    if not os.path.exists(file_path):
        print(f"{RED}错误: 文件不存在 {file_path}{RESET}")
        return False

    txt_modified = False
    temp_file_path = file_path + ".tmp"
    current_child_title = None

    try:
        with open(file_path, 'r', encoding='utf-8-sig') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:

            original_lines = infile.readlines()

            for i, original_line in enumerate(original_lines):
                processed_line_content = original_line.strip()
                line_to_write = original_line # Default

                # --- 功能1: 行内求和 (受开关控制) ---
                calculated_line = None
                if enable_summing and processed_line_content: # 检查开关和是否为空行
                    calculated_line = sum_up_line(processed_line_content)
                    if calculated_line is not None:
                        indentation = original_line[:-len(original_line.lstrip())]
                        line_to_write = indentation + calculated_line + '\n'
                        if line_to_write != original_line:
                            print(f"{GREEN}信息: 计算总和: '{processed_line_content}' -> '{calculated_line}'{RESET}")
                            txt_modified = True
                    # 如果 calculated_line 为 None (不匹配或出错), line_to_write 保持 original_line

                # 如果求和功能关闭或未执行求和，确保 line_to_write 是原始行
                if calculated_line is None:
                    line_to_write = original_line

                # --- 写入处理后的行 ---
                outfile.write(line_to_write)

                # --- 功能2: 添加自动续费 (受开关控制) ---
                # 检查 *原始* 行是否是子标题
                original_stripped = original_line.strip()
                if re.fullmatch(r'^[a-z]+(_[a-z]+)+$', original_stripped):
                    current_child_title = original_stripped
                    # 检查开关和这个子标题是否在映射中
                    if enable_autorenewal and current_child_title in AUTO_RENEWAL_MAP:
                        items_to_add = AUTO_RENEWAL_MAP[current_child_title]
                        for amount, description in items_to_add:
                            auto_renewal_desc_txt = description + "(自动续费)"
                            amount_decimal = decimal.Decimal(amount)
                            amount_str = format(amount_decimal.normalize(), 'f')
                            txt_line_to_insert = f"{amount_str}{auto_renewal_desc_txt}"
                            line_exists = False

                            # 检查重复逻辑 (保持不变)
                            lookahead_range = min(len(items_to_add) + 3, len(original_lines) - (i + 1))
                            for j in range(1, lookahead_range):
                                next_original_line_stripped = original_lines[i+j].strip()
                                if next_original_line_stripped.startswith(txt_line_to_insert):
                                    match_item = re.match(r'^(\d+(?:\.\d+)?)\s*(.*)$', next_original_line_stripped)
                                    if match_item:
                                        existing_amount_str = match_item.group(1)
                                        existing_desc = match_item.group(2).strip()
                                        try:
                                            if decimal.Decimal(existing_amount_str) == amount_decimal and existing_desc == auto_renewal_desc_txt:
                                                line_exists = True
                                                break
                                        except decimal.InvalidOperation:
                                            pass

                            if not line_exists:
                                line_content_to_write = txt_line_to_insert + '\n'
                                outfile.write(line_content_to_write) # 写入新行
                                print(f"{GREEN}信息: 在'{current_child_title}'下添加了行: {txt_line_to_insert}{RESET}")
                                txt_modified = True # 标记已修改

                # 重置上下文逻辑 (保持不变)
                elif not re.match(r'^(\d+\.?\d*)', original_stripped):
                    current_child_title = None

        # --- 文件读取写入循环结束 ---

        if txt_modified:
            try:
                shutil.move(temp_file_path, file_path)
                print(f"{GREEN}信息: 文件 {os.path.basename(file_path)} 已成功更新.{RESET}")
                return True
            except OSError as e:
                print(f"{RED}错误: 无法将临时文件 {temp_file_path} 替换回 {file_path}. 错误: {e}{RESET}")
                if os.path.exists(temp_file_path):
                    try: os.remove(temp_file_path)
                    except OSError: pass
                raise RuntimeError(f"无法更新原始文件 {file_path}") from e
        else:
            # 即使文件未修改，也要删除临时文件
            print(f"{YELLOW}信息: 文件 {os.path.basename(file_path)} 未作修改.{RESET}")
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except OSError as e: print(f"{YELLOW}警告: 删除临时文件 {temp_file_path} 失败: {e}{RESET}")
            return False

    except FileNotFoundError:
         print(f"{RED}错误: 文件未找到 {file_path}{RESET}")
         if os.path.exists(temp_file_path):
             try: os.remove(temp_file_path)
             except OSError: pass
         return False
    except Exception as e:
        print(f"{RED}处理文件 {os.path.basename(file_path)} 时发生意外错误: {e}{RESET}")
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                print(f"{YELLOW}信息: 因发生错误, 已删除临时文件 {temp_file_path}.{RESET}")
            except OSError as rm_err:
                print(f"{RED}严重错误: 处理中发生错误, 且无法删除临时文件 {temp_file_path}. 错误: {rm_err}{RESET}")
        raise RuntimeError(f"处理文件 {os.path.basename(file_path)} 时失败: {str(e)}") from e


def process_path(path, enable_summing, enable_autorenewal):
    """
    处理用户输入的路径，可能是单个文件或文件夹。
    将功能开关传递给 process_single_file。
    """
    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return

    start_time = time.perf_counter()
    processed_count = 0
    modified_count = 0
    error_count = 0
    files_to_process = []

    # 文件查找逻辑 (保持不变)
    if os.path.isfile(path) and path.lower().endswith('.txt'):
        files_to_process.append(os.path.normpath(os.path.abspath(path)))
    elif os.path.isdir(path):
        print(f"--- 正在扫描文件夹: {path} ---")
        found_files = set()
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            files = [f for f in files if not f.startswith('.')]
            for file in files:
                if file.lower().endswith('.txt'):
                    full_path = os.path.join(root, file)
                    normalized_path = os.path.normpath(os.path.abspath(full_path))
                    found_files.add(normalized_path)
        files_to_process = sorted(list(found_files))
    else:
        print(f"{RED}错误: 输入的路径既不是有效的 .txt 文件，也不是文件夹.{RESET}")
        return

    if not files_to_process:
        print(f"{YELLOW}警告: 在 '{path}' 中没有找到 .txt 文件.{RESET}")
        return

    print(f"--- 发现 {len(files_to_process)} 个 .txt 文件准备处理 ---")

    for file_path in files_to_process:
        try:
            try:
                base_path = path if os.path.isdir(path) else os.path.dirname(path)
                relative_path = os.path.relpath(file_path, start=base_path)
            except ValueError:
                relative_path = os.path.basename(file_path)

            print(f"\n--- 处理文件: {relative_path} ---")
            # --- 修改: 将开关传递给处理函数 ---
            modified = process_single_file(file_path, enable_summing, enable_autorenewal)
            # --- 修改结束 ---
            processed_count += 1
            if modified:
                modified_count += 1
        except Exception as e:
            print(f"{RED}处理文件 {os.path.basename(file_path)} 时遇到顶层错误: {e}，跳过此文件.{RESET}")
            error_count += 1

    # 结果报告逻辑 (保持不变)
    duration = time.perf_counter() - start_time
    print("\n========== 处理完成 ==========")
    print(f"总共检查文件数: {processed_count}")
    print(f"成功修改文件数: {modified_count}")
    if error_count > 0:
         print(f"{RED}处理失败文件数: {error_count}{RESET}")
    print(f"总耗时: {duration:.4f} 秒")


def main():
    print("========== TXT 账单处理工具 ==========")
    # --- 修改: 显示功能状态 ---
    print(f"功能:")
    print(f"  1. 计算行内加法: {'启用' if ENABLE_SUM_UP_LINES else '禁用'}")
    print(f"  2. 添加自动续费项: {'启用' if ENABLE_ADD_AUTORENEWAL else '禁用'}")
    print(f"  (可在脚本顶部修改 ENABLE_SUM_UP_LINES 和 ENABLE_ADD_AUTORENEWAL 来开关功能)")
    # --- 修改结束 ---

    if ENABLE_ADD_AUTORENEWAL and not AUTO_RENEWAL_MAP:
         print(f"{YELLOW}警告: 自动续费功能已启用, 但 AUTO_RENEWAL_MAP 为空.{RESET}")
    elif ENABLE_ADD_AUTORENEWAL:
         print("\n将尝试为以下子标题自动添加项目 (如果找到对应子标题且项目不存在):")
         for key, items_list in AUTO_RENEWAL_MAP.items():
             print(f"  - 子标题 '{key}':")
             for amount, desc in items_list:
                 amount_decimal = decimal.Decimal(amount)
                 amount_str = format(amount_decimal.normalize(), 'f')
                 print(f"      -> 添加行: {amount_str}{desc}(自动续费)")

    while True:
        path_input = input("\n请输入要处理的 .txt 文件或包含 .txt 文件的文件夹路径 (输入 0 退出): ").strip()
        if path_input == '0':
            break
        # --- 修改: 将开关状态传递给 process_path ---
        process_path(path_input, ENABLE_SUM_UP_LINES, ENABLE_ADD_AUTORENEWAL)
        # --- 修改结束 ---

    print("\n程序已退出。")

if __name__ == "__main__":
    main()
