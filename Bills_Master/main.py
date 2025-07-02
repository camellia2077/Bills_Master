import datetime
import os
import sys
import time
import sqlite3
import json
from io import StringIO

# 从 common.py 导入颜色
from common import RED, GREEN, YELLOW, RESET, CYAN, BLUE

# 导入各个功能模块
from Query.query_db import (
    display_yearly_summary,
    display_monthly_details,
    export_monthly_bill_as_text,
    display_yearly_parent_category_summary
)
from TextParser.text_parser import parse_bill_file
from Inserter.database_inserter import insert_data, create_database as create_db_schema
from Reprocessor import BillProcessor


# --- 辅助函数，用于获取用户输入和文件列表 ---

def _get_files_to_process():
    """
    提示用户输入路径，并返回一个txt文件列表。
    如果路径无效或未找到文件，则返回None。
    """
    path = input("请输入要处理的txt文件或文件夹路径 (输入0返回): ").strip()
    if path == '0':
        return None

    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return None

    files = []
    if os.path.isfile(path) and path.lower().endswith('.txt'):
        files.append(path)
    elif os.path.isdir(path):
        files.extend([
            os.path.join(root, file)
            for root, _, dir_files in os.walk(path)
            for file in dir_files if file.lower().endswith('.txt')
        ])
    else:
        print(f"{RED}错误: 无效的路径或文件类型。请输入 .txt 文件或包含 .txt 文件的文件夹。{RESET}")
        return None

    if not files:
        print(f"{YELLOW}警告: 在 '{path}' 中没有找到 .txt 文件。{RESET}")
        return None
    
    return files


# --- 功能处理函数 ---

def _initialize_processor():
    """尝试初始化BillProcessor并处理配置文件错误。"""
    validator_config = 'config/validator_config.json'
    modifier_config = 'config/modifier_config.json'
    try:
        return BillProcessor(
            validator_config_path=validator_config,
            modifier_config_path=modifier_config
        )
    except FileNotFoundError as e:
        print(f"\n{RED}错误: 配置文件未找到。请确保 '{validator_config}' 和 '{modifier_config}' 文件存在。{RESET}")
        print(f"详细信息: {e}")
        return None

def handle_validation_modification_menu():
    """
    显示并处理“验证/修改”的二级菜单（不含短路模式）。
    """
    processor = _initialize_processor()
    if not processor:
        return

    while True:
        print("\n--- 验证/修改账单文件 (子菜单) ---")
        print("1. 仅验证文件")
        print("2. 仅修改文件")
        print("3. 返回主菜单")
        choice = input("请选择操作: ").strip()

        if choice == '3':
            break

        if choice not in ['1', '2']:
            print(f"{RED}无效输入，请输入1-3之间的数字。{RESET}")
            continue

        files_to_process = _get_files_to_process()
        if not files_to_process:
            continue

        print(f"\n{CYAN}--- 开始处理 {len(files_to_process)} 个文件 ---{RESET}")

        if choice == '1': # 仅验证
            for file_path in files_to_process:
                print(f"\n{'='*40}\nProcessing file: {os.path.basename(file_path)}")
                # --- MODIFIED: No longer need to print results here. ---
                # The processor now handles its own detailed logging.
                processor.validate_bill_file(file_path)

        elif choice == '2': # 仅修改
            for file_path in files_to_process:
                 print(f"\n{'='*40}\nProcessing file: {os.path.basename(file_path)}")
                 processor.modify_bill_file(file_path)
        
        print(f"\n{CYAN}--- 所有文件处理完毕 ---{RESET}")

def handle_short_circuit_mode():
    """
    处理“验证并修改”的短路模式，直接从主菜单调用。
    """
    processor = _initialize_processor()
    if not processor:
        return

    files_to_process = _get_files_to_process()
    if not files_to_process:
        return
        
    print(f"\n{CYAN}--- 开始处理 {len(files_to_process)} 个文件 (短路模式) ---{RESET}")
    print(f"{YELLOW}注意：修改操作将根据 'config/modifier_config.json' 中的设置自动执行。{RESET}")
    for file_path in files_to_process:
        print(f"\n{'='*40}\nProcessing file: {os.path.basename(file_path)}")
        # --- MODIFIED: No longer need to print results here. ---
        # The processor prints details internally. We just get the final message.
        success, message, result = processor.validate_and_modify_bill_file(file_path)
        # The 'message' gives a summary, which is good to keep.
        print(f"处理结果: {message}")
    
    print(f"\n{CYAN}--- 所有文件处理完毕 ---{RESET}")


def handle_import():
    """
    处理将文件数据导入数据库的流程。
    """
    files_to_process = _get_files_to_process()
    if not files_to_process:
        return

    if not create_db_schema():
        print(f"{RED}错误：数据库初始化失败，导入操作已中止。{RESET}")
        return

    all_records, total_parse_time, failed_file_on_parse = [], 0.0, None
    total_files = len(files_to_process)
    
    print(f"找到 {total_files} 个文件. 开始解析...")
    try:
        for i, file_path in enumerate(files_to_process):
            failed_file_on_parse = os.path.basename(file_path)
            print(f"  ({i+1}/{total_files}) 正在解析: {failed_file_on_parse}")

            parse_start = time.perf_counter()
            success, records = parse_bill_file(file_path)
            total_parse_time += (time.perf_counter() - parse_start)

            if not success:
                raise ValueError(f"文件解析失败: {failed_file_on_parse}")

            all_records.extend(records)
        
        failed_file_on_parse = None

        if not all_records:
            print(f"{YELLOW}警告: 所有文件中均未找到可导入的数据记录。{RESET}")
            return

        print("\n所有文件解析成功. 开始将数据写入数据库...")
        db_start_time = time.perf_counter()
        insert_success = insert_data(iter(all_records))
        total_db_time = time.perf_counter() - db_start_time
        
        if not insert_success:
            raise RuntimeError("数据库插入操作失败")

        print(f"\n{GREEN}===== 导入完成 ====={RESET}")
        # ... (成功信息打印) ...

    except (ValueError, RuntimeError, sqlite3.Error) as e:
        print(f"\n{RED}===== 导入失败 ====={RESET}")
        # ... (失败信息打印) ...


def main_app_loop():
    """主应用循环，显示主菜单并分发任务。"""
    while True:
        print(f"\n{BLUE}========== 账单数据库主菜单 =========={RESET}\n")
        print("0. 验证/修改账单文件 (子菜单)")
        print("1. 验证并修改文件 (短路模式)")
        print("2. 从txt文件导入数据到数据库")
        print("3. 年消费查询")
        print("4. 月消费详情")
        print("5. 导出月账单")
        print("6. 年度分类统计")
        print("7. 退出")
        choice = input("请选择操作: ").strip()

        if choice == '0':
            handle_validation_modification_menu()
        elif choice == '1':
            handle_short_circuit_mode()
        elif choice == '2':
            handle_import()
        elif choice == '3':
            # ... 年消费查询代码 (无变化) ...
            current_system_year = datetime.datetime.now().year
            year_to_query = str(current_system_year)
            while True:
                year_input_str = input(f"请输入年份(默认为 {current_system_year}, 直接回车使用默认): ").strip()
                if not year_input_str:
                    print(f"使用默认年份: {year_to_query}")
                    break
                if year_input_str.isdigit() and len(year_input_str) == 4:
                    year_to_query = year_input_str
                    break
                else:
                    print(f"{RED}输入错误, 请输入四位数字年份.{RESET}")
            display_yearly_summary(year_to_query)
        elif choice == '4':
            # ... 月消费详情代码 (无变化) ...
            now = datetime.datetime.now()
            default_year, default_month = now.year, now.month
            default_date_str = f"{default_year}{default_month:02d}"
            year_to_query, month_to_query = default_year, default_month
            while True:
                date_input_str = input(f"请输入年月(默认为 {default_date_str}, 直接回车使用默认): ").strip()
                if not date_input_str:
                    print(f"使用默认年月: {year_to_query}-{month_to_query:02d}")
                    break
                if len(date_input_str) == 6 and date_input_str.isdigit():
                    year_val, month_val = int(date_input_str[:4]), int(date_input_str[4:])
                    if 1 <= month_val <= 12:
                        year_to_query, month_to_query = year_val, month_val
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            display_monthly_details(year_to_query, month_to_query)
        elif choice == '5':
            # ... 导出月账单代码 (无变化) ...
            now = datetime.datetime.now()
            default_year, default_month = now.year, now.month
            default_date_str = f"{default_year}{default_month:02d}"
            year_to_export, month_to_export = default_year, default_month
            while True:
                date_input_str = input(f"请输入年月 (例如 202305, 默认为 {default_date_str}, 直接回车使用默认): ").strip()
                if not date_input_str:
                    print(f"使用默认年月: {year_to_export}-{month_to_export:02d}")
                    break
                if len(date_input_str) == 6 and date_input_str.isdigit():
                    year_val, month_val = int(date_input_str[:4]), int(date_input_str[4:])
                    if 1 <= month_val <= 12:
                        year_to_export, month_to_export = year_val, month_val
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            export_monthly_bill_as_text(year_to_export, month_to_export)
        elif choice == '6':
            # ... 年度分类统计代码 (无变化) ...
            current_system_year = datetime.datetime.now().year
            year_to_query_stats = str(current_system_year)
            while True:
                year_input_str = input(f"请输入年份 (默认为 {current_system_year}, 直接回车使用默认): ").strip()
                if not year_input_str:
                    print(f"使用默认年份: {year_to_query_stats}")
                    break
                if year_input_str.isdigit() and len(year_input_str) == 4:
                    year_to_query_stats = year_input_str
                    break
                else:
                    print(f"{RED}年份输入错误, 请输入四位数字年份.{RESET}")
            parent_title_str = ""
            while not parent_title_str:
                parent_title_str = input("请输入父标题 (例如 RENT房租水电): ").strip()
                if not parent_title_str:
                    print(f"{RED}父标题不能为空.{RESET}")
            display_yearly_parent_category_summary(year_to_query_stats, parent_title_str)
        elif choice == '7':
            print("程序结束运行")
            break
        else:
            print(f"{RED}无效输入，请输入选项中的数字(0-7)。{RESET}")


if __name__ == "__main__":
    main_app_loop()