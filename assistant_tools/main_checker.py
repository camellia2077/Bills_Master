# main_checker.py (已更正)

import os
import time

# 从我们创建的模块中导入核心函数
from bill_validator import validate_file
from bill_modifier import process_single_file as modify_bill_file

# ANSI转义码_颜色代码
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- 功能开关 (为修改功能服务) ---
ENABLE_SUM_UP_LINES = True
ENABLE_ADD_AUTORENEWAL = True # 正确的变量名
ENABLE_CLEANUP_EMPTY_ITEMS = True

# --- 定义配置文件的路径 ---
CONFIG_FILE_PATH = "Validator_Config.json"

# ======================================================================
# 验证功能区 (无变动)
# ======================================================================
def print_validation_result(file_path, result):
    """打印验证结果"""
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
    """处理文件验证的整个流程"""
    path = input("请输入要[校验]的txt文件或目录路径 (输入0返回): ").strip()
    if path == '0': return
    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在。{RESET}")
        return
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"{RED}关键错误: 配置文件 '{CONFIG_FILE_PATH}' 未找到。请确保它存在。{RESET}")
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
        validation_result = validate_file(file_path, CONFIG_FILE_PATH)
        print_validation_result(file_path, validation_result)

# ======================================================================
# 修改功能区 (已更新日志打印)
# ======================================================================
def handle_modification():
    path = input("请输入要[修正]的txt文件或目录路径 (输入0返回): ").strip()
    if path == '0': return
    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在。{RESET}")
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
    total_files, modified_count = len(files_to_process), 0
    start_time = time.perf_counter()
    print(f"\n--- 发现 {total_files} 个文件，开始处理 ---")
    print(f"行内求和功能: {'启用' if ENABLE_SUM_UP_LINES else '禁用'}")
    print(f"自动续费功能: {'启用' if ENABLE_ADD_AUTORENEWAL else '禁用'}")
    print(f"清理空项目功能: {'启用' if ENABLE_CLEANUP_EMPTY_ITEMS else '禁用'}")
    for file_path in files_to_process:
        print(f"\n--- 处理文件: {os.path.basename(file_path)} ---")
        result = modify_bill_file(
            file_path,
            ENABLE_SUM_UP_LINES,
            ENABLE_ADD_AUTORENEWAL,
            ENABLE_CLEANUP_EMPTY_ITEMS
        )
        if result['error']:
            print(f"{RED}错误: {result['error']}{RESET}")
        else:
            for log_entry in result['log']:
                if any(kw in log_entry for kw in ["更新", "添加", "计算", "清理", "删除"]):
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
    """主函数，负责循环接收用户输入"""
    while True:
        print("\n========== 账单工具箱 ==========")
        print("1. 校验账单文件格式")
        print("2. 格式化和修正账单文件 (求和/续费/清理)")
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