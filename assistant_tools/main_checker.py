import os
import time
import json
# 从 reprocessor 包中导入 BillProcessor
from reprocessor.BillProcessor import BillProcessor

# ANSI escape codes for colored console output
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- Feature Flags ---
ENABLE_SUM_UP_LINES = True
ENABLE_ADD_AUTORENEWAL = True
ENABLE_CLEANUP_EMPTY_ITEMS = True
ENABLE_SORT_CONTENT = True

# --- 主配置文件路径 ---
MAIN_CONFIG_FILE = "main_config.json"

def print_validation_result(file_path, is_valid, result_data):
    """Prints a formatted summary of the validation results."""
    filename = os.path.basename(file_path)
    print("\n" + "-" * 20 + f" Validation Summary: {filename} " + "-" * 20)
    if is_valid:
        print(f"{GREEN}Result: PASSED (No critical errors found){RESET}")
    else:
        print(f"{RED}Result: FAILED (Critical errors found){RESET}")
    
    if result_data['errors']:
        print(f"{RED}Errors ({len(result_data['errors'])}):{RESET}")
        for lineno, message in result_data['errors']: print(f"  - Line {lineno:<4}: {message}")
    
    if result_data['warnings']:
        print(f"{YELLOW}Warnings ({len(result_data['warnings'])}):{RESET}")
        for lineno, message in result_data['warnings']: print(f"  - Line {lineno:<4}: {message}")
    
    print(f"Details: {result_data['processed_lines']} lines processed in {result_data['time']:.6f}s.")
    print("-" * (42 + len(filename)) + "\n")


def get_files_from_path(path):
    """Helper to get a list of .txt files from a given path."""
    if not os.path.exists(path):
        print(f"{RED}Error: Path '{path}' does not exist.{RESET}")
        return []
    files_to_process = []
    if os.path.isdir(path):
        files_to_process.extend([os.path.join(root, file) for root, _, files in os.walk(path) for file in sorted(files) if file.lower().endswith('.txt')])
    elif os.path.isfile(path) and path.lower().endswith('.txt'):
        files_to_process.append(path)
    if not files_to_process:
        print(f"{YELLOW}No .txt files found in '{path}'.{RESET}")
    return files_to_process

def handle_validation(processor: BillProcessor):
    """Handles validating bill files."""
    path = input("Enter path to [Validate] (or 0 to return): ").strip()
    if path == '0': return
    for file_path in get_files_from_path(path):
        try:
            is_valid, validation_result = processor.validate_bill_file(file_path)
            print_validation_result(file_path, is_valid, validation_result)
        except Exception as e:
            print(f"{RED}An unexpected error occurred: {e}{RESET}")

def handle_modification(processor: BillProcessor):
    """Handles modifying bill files."""
    path = input("Enter path to [Modify] (or 0 to return): ").strip()
    if path == '0': return
    files_to_process = get_files_from_path(path)
    if not files_to_process: return

    for file_path in files_to_process:
        try:
            processor.modify_bill_file(
                file_path, ENABLE_SUM_UP_LINES, ENABLE_ADD_AUTORENEWAL,
                ENABLE_CLEANUP_EMPTY_ITEMS, ENABLE_SORT_CONTENT
            )
        except Exception as e:
            print(f"{RED}An unexpected error occurred: {e}{RESET}")

def handle_validation_and_modification(processor: BillProcessor):
    """Handles validating AND then modifying bill files."""
    path = input("Enter path to [Validate & Modify] (or 0 to return): ").strip()
    if path == '0': return
    for file_path in get_files_from_path(path):
        try:
            success, message, validation_details = processor.validate_and_modify_bill_file(
                file_path, ENABLE_SUM_UP_LINES, ENABLE_ADD_AUTORENEWAL,
                ENABLE_CLEANUP_EMPTY_ITEMS, ENABLE_SORT_CONTENT
            )
            if success:
                print(f"{GREEN}Overall Result for {os.path.basename(file_path)}: {message}{RESET}")
            else:
                print(f"{RED}Overall Result for {os.path.basename(file_path)}: {message}{RESET}")
        except Exception as e:
            print(f"{RED}An unexpected error occurred: {e}{RESET}")

def load_config_paths(config_file: str) -> dict:
    """从主配置文件加载路径。"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{RED}Critical Error: Main config file '{config_file}' not found.{RESET}")
        return None
    except json.JSONDecodeError:
        print(f"{RED}Critical Error: Could not decode JSON from '{config_file}'.{RESET}")
        return None
    except KeyError as e:
        print(f"{RED}Critical Error: Missing key {e} in '{config_file}'.{RESET}")
        return None


def main():
    """Main function to run the Bill Toolbox application."""
    # 从主配置文件加载路径
    config_paths = load_config_paths(MAIN_CONFIG_FILE)
    if not config_paths:
        return

    try:
        # 使用加载的路径初始化处理器
        processor = BillProcessor(
            validator_config_path=config_paths['validator_config_path'],
            modifier_config_path=config_paths['modifier_config_path']
        )
    except FileNotFoundError as e:
        print(f"{RED}Critical Error: {e}{RESET}")
        return
        
    while True:
        print("\n========== Bill Toolbox ==========")
        print("1. Validate Bill File(s) Format")
        print("2. Modify Bill File(s) Only")
        print("3. Validate AND Modify File(s) (验证失败则中止)")
        print("0. Exit")
        choice = input("Select an option: ").strip()
        
        if choice == '1': handle_validation(processor) 
        elif choice == '2': handle_modification(processor)
        elif choice == '3': handle_validation_and_modification(processor)
        elif choice == '0':
            print("Exiting program.")
            break
        else:
            print(f"{RED}Invalid input, please enter a number from the menu.{RESET}")

if __name__ == "__main__":
    main()