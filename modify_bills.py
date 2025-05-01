import re
import os
import shutil
import time

# ANSI 转义码_颜色代码 (保留用于输出信息)
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- 修改: 自动续费项目映射 ---
# 使用列表允许多个项目对应同一个子标题
AUTO_RENEWAL_MAP = {
    "web_service": [ # 值现在是一个列表
        (15.0, "uu加速器"),
        (25.0, "迅雷加速器"),
    ],
    # "another_service": [
    #    (100.0, "Some Service"),
    #    (50.0, "Another Related Service"),
    # ],
}
# --- 修改结束 ---

def add_auto_renewal_to_txt(file_path):
    """
    读取 TXT 文件, 如果找到 AUTO_RENEWAL_MAP 中定义的子标题,
    就在该子标题下添加对应的所有自动续费项目行.
    使用临时文件保证原子性操作.
    返回 True 如果文件被修改,否则返回 False.
    """
    if not AUTO_RENEWAL_MAP:
        print(f"{YELLOW}警告: AUTO_RENEWAL_MAP 为空, 不会向文件 {os.path.basename(file_path)} 添加任何项目.{RESET}")
        return False

    txt_modified = False
    temp_file_path = file_path + ".tmp"
    current_child_title = None
    # added_items_in_run = set() # 如果需要更复杂的防止重复添加逻辑，可以使用这个

    try:
        with open(file_path, 'r', encoding='utf-8') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:

            for line in infile:
                outfile.write(line) # 先写入原始行
                stripped_line = line.strip()

                if not stripped_line:
                    continue

                # 检查是否是子标题行
                if re.fullmatch(r'^[a-z]+(_[a-z]+)+$', stripped_line):
                    current_child_title = stripped_line
                    # 检查这个子标题是否在映射中
                    if current_child_title in AUTO_RENEWAL_MAP:
                        # --- 修改: 遍历列表中的所有项目 ---
                        items_to_add = AUTO_RENEWAL_MAP[current_child_title]
                        for amount, description in items_to_add:
                            auto_renewal_desc_txt = description + "(自动续费)"
                            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                            txt_line_to_insert = f"{amount_str}{auto_renewal_desc_txt}\n"

                            # **重要**: 当前逻辑每次运行都会添加所有映射项。
                            # 如果希望只在项不存在时添加，需要更复杂的逻辑来检查文件内容。
                            # 为简化起见，这里每次都添加。

                            outfile.write(txt_line_to_insert) # 添加自动续费行
                            print(f"{GREEN}信息: 文件 {os.path.basename(file_path)} 在'{current_child_title}'下添加了行: {txt_line_to_insert.strip()}{RESET}")
                            txt_modified = True # 标记文件已被修改
                        # --- 修改结束 ---

                # 如果当前行不是子标题，且不是 Item 行 (数字开头)，则重置上下文
                elif not re.match(r'^(\d+\.?\d*)\s*(.*)$', stripped_line):
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
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except OSError as e: print(f"{YELLOW}警告: 文件未修改, 但删除临时文件 {temp_file_path} 失败: {e}{RESET}")
            return False

    except Exception as e:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                print(f"{YELLOW}信息: 因发生错误, 已删除临时文件 {temp_file_path}.{RESET}")
            except OSError as rm_err:
                print(f"{RED}严重错误: 处理中发生错误, 且无法删除临时文件 {temp_file_path}. 错误: {rm_err}{RESET}")
        raise RuntimeError(f"处理文件 {os.path.basename(file_path)} 时失败: {str(e)}") from e


def process_path(path):
    """
    处理用户输入的路径，可能是单个文件或文件夹。
    """
    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return

    start_time = time.perf_counter()
    processed_count = 0
    modified_count = 0
    files_to_process = []

    if os.path.isfile(path) and path.lower().endswith('.txt'):
        files_to_process.append(path)
    elif os.path.isdir(path):
        print(f"--- 正在扫描文件夹: {path} ---")
        # 使用 set 来防止因奇怪的文件系统行为（如大小写不敏感）导致重复添加
        found_files = set()
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.txt'):
                    full_path = os.path.join(root, file)
                    # 标准化路径表示，减少重复可能性
                    normalized_path = os.path.normpath(os.path.abspath(full_path))
                    found_files.add(normalized_path)
        files_to_process = sorted(list(found_files)) # 排序以获得一致的处理顺序
    else:
        print(f"{RED}错误: 输入的路径既不是有效的 .txt 文件，也不是文件夹.{RESET}")
        return

    if not files_to_process:
        print(f"{YELLOW}警告: 在 '{path}' 中没有找到 .txt 文件.{RESET}")
        return

    print(f"--- 发现 {len(files_to_process)} 个 .txt 文件准备处理 ---")

    for file_path in files_to_process:
        try:
            # 打印正在处理的文件名（使用相对路径可能更清晰，如果路径太长）
            relative_path = os.path.relpath(file_path, start=os.path.dirname(path) if os.path.isdir(path) else os.path.dirname(file_path))
            print(f"\n--- 处理文件: {relative_path} ---")
            modified = add_auto_renewal_to_txt(file_path)
            processed_count += 1
            if modified:
                modified_count += 1
        except Exception as e:
            print(f"{RED}处理文件 {os.path.basename(file_path)} 时遇到无法恢复的错误: {e}，跳过此文件.{RESET}")


    duration = time.perf_counter() - start_time
    print("\n========== 处理完成 ==========")
    print(f"总共检查文件数: {processed_count}")
    print(f"成功修改文件数: {modified_count}")
    print(f"总耗时: {duration:.4f} 秒")


def main():
    print("========== TXT 自动续费项添加工具 ==========")
    if not AUTO_RENEWAL_MAP:
         print(f"{YELLOW}警告: AUTO_RENEWAL_MAP 为空, 不会添加任何自动续费项目.{RESET}")
         print(f"{YELLOW}请在脚本顶部编辑 AUTO_RENEWAL_MAP 添加项目.{RESET}")
    else:
         print("将尝试为以下子标题自动添加项目 (如果找到对应子标题):")
         # --- 修改: 正确显示列表中的所有项目 ---
         for key, items_list in AUTO_RENEWAL_MAP.items():
             print(f"  - 子标题 '{key}':")
             for amount, desc in items_list:
                 amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                 print(f"      -> 添加行: {amount_str}{desc}(自动续费)")
         # --- 修改结束 ---

    while True:
        path_input = input("\n请输入要处理的 .txt 文件或包含 .txt 文件的文件夹路径 (输入 0 退出): ").strip()
        if path_input == '0':
            break
        process_path(path_input) # 调用处理函数

    print("\n程序已退出。")

if __name__ == "__main__":
    main()