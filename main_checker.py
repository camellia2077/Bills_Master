# main_checker.py (已更新)

import os
import time

# 假设 bill_modifier 和 bill_validator 已被合并到 BillProcessor.py
# from BillProcessor import validate_file, process_single_file as modify_bill_file
# 为保持示例独立，我们继续使用分离的导入
from bill_validator import validate_file
from bill_modifier import process_single_file as modify_bill_file

# ANSI转义码_颜色代码
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- 功能开关 ---
ENABLE_SUM_UP_LINES = True
ENABLE_ADD_AUTORENEWAL = True
ENABLE_CLEANUP_EMPTY_ITEMS = True
ENABLE_SORT_CONTENT = True

# --- 定义配置文件路径 ---
VALIDATOR_CONFIG_PATH = "Validator_Config.json"
MODIFIER_CONFIG_PATH = "Modifier_Config.json" 

# ======================================================================
# 验证功能区 (已更新)
# ======================================================================
def print_validation_result(file_path, result):
    # ... 此函数代码无变化 ...
    filename = os.path.basename(file_path)
    print("-" * 40)
    print(f"文件: {filename}")
    if not result['errors']:
        print(f"{GREEN}校验通过{RESET}")
    else:
        print(f"{RED}校验失败, 发现 {len(result['errors'])} 个错误:{RESET}")
        for lineno, message in result['errors']:
            print(f"  - 第 {lineno:<4} 行: {message}")
    print(f"处理行数: {result['processed_lines']}")
    print(f"运行时间: {result['time']:.6f}秒")
    print("-" * 40 + "\n")

def handle_validation():
    path = input("请输入要[校验]的txt文件或目录路径 (输入0返回): ").strip()
    if path == '0': return
    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在。{RESET}")
        return
        
    # 检查验证器配置文件
    if not os.path.exists(VALIDATOR_CONFIG_PATH):
        print(f"{RED}关键错误: 验证配置文件 '{VALIDATOR_CONFIG_PATH}' 未找到。{RESET}")
        return

    files_to_process = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in sorted(files):
                if file.lower().endswith('.txt'):
                    files_to_process.append(os.path.join(root, file))
    elif os.path.isfile(path):
        files_to_process.append(path)
    if not files_to_process:
        print(f"在 {path} 中未找到任何 .txt 文件。")
        return
    for file_path in files_to_process:
        # 传入验证器配置路径
        validation_result = validate_file(file_path, VALIDATOR_CONFIG_PATH)
        print_validation_result(file_path, validation_result)

# ======================================================================
# 修改功能区 (已更新)
# ======================================================================
def handle_modification():
    path = input("请输入要[修正]的txt文件或目录路径 (输入0返回): ").strip()
    if path == '0': return

    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在。{RESET}")
        return
        
    # 检查修改器配置文件
    if not os.path.exists(MODIFIER_CONFIG_PATH):
        print(f"{YELLOW}警告: 修改配置文件 '{MODIFIER_CONFIG_PATH}' 未找到。自动续费功能将不可用。{RESET}")

    files_to_process = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in sorted(files):
                if file.lower().endswith('.txt'):
                    files_to_process.append(os.path.join(root, file))
    elif os.path.isfile(path):
        files_to_process.append(path)

    if not files_to_process:
        print(f"在 {path} 中未找到任何 .txt 文件。")
        return

    total_files, modified_count = len(files_to_process), 0
    start_time = time.perf_counter()

    print(f"\n--- 发现 {total_files} 个文件，开始处理 ---")
    print(f"行内求和功能: {'启用' if ENABLE_SUM_UP_LINES else '禁用'}")
    print(f"自动续费功能: {'启用' if ENABLE_ADD_AUTORENEWAL else '禁用'}")
    print(f"内容排序功能: {'启用' if ENABLE_SORT_CONTENT else '禁用'}")
    print(f"清理空项目功能: {'启用' if ENABLE_CLEANUP_EMPTY_ITEMS else '禁用'}")

    for file_path in files_to_process:
        print(f"\n--- 处理文件: {os.path.basename(file_path)} ---")
        
        # 传入修改器配置路径
        result = modify_bill_file(
            file_path,
            MODIFIER_CONFIG_PATH,
            ENABLE_SUM_UP_LINES,
            ENABLE_ADD_AUTORENEWAL,
            ENABLE_CLEANUP_EMPTY_ITEMS,
            ENABLE_SORT_CONTENT
        )

        if result['error']:
            print(f"{RED}错误: {result['error']}{RESET}")
        else:
            for log_entry in result['log']:
                if any(kw in log_entry for kw in ["更新", "添加", "计算", "清理", "删除", "排序"]):
                    print(f"{GREEN}  - {log_entry}{RESET}")
                elif any(kw in log_entry for kw in ["未作修改", "未发现"]):
                     print(f"{YELLOW}  - {log_entry}{RESET}")
                else:
                    print(f"  - {log_entry}")
            
            if result['modified']:
                modified_count += 1
    
    duration = time.perf_counter() - start_time
    print("\n========== 处理完成 ==========")
    print(f"总共处理文件数: {total_files}")
    print(f"成功修改文件数: {modified_count}")
    print(f"总耗时: {duration:.4f} 秒")

# ======================================================================
# 主程序循环 (无变动)
# ======================================================================
def main():
    while True:
        print("\n========== 账单工具箱 ==========")
        print("1. 校验账单文件格式")
        print("2. 格式化和修正账单文件 (求和/续费/清理/排序)")
        print("0. 退出")
        choice = input("请选择操作: ").strip()
        if choice == '1':
            handle_validation()
        elif choice == '2':
            handle_modification()
        elif choice == '0':
            print("程序退出。")
            break
        else:
            print(f"{RED}无效输入，请输入菜单中的数字。{RESET}")

if __name__ == "__main__":
    main()