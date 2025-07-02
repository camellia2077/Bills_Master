import datetime
import os
import sys
import time
from io import StringIO

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# MODIFIED: Import the new, more descriptive function names from query_db.py
from query_db import (
    display_yearly_summary,
    display_monthly_details,
    export_monthly_bill_as_text,
    display_yearly_parent_category_summary
)

# Import independent modules for parsing and database operations
from text_parser import parse_bill_file
from database_inserter import db_connection, insert_data_stream, create_database as create_db_schema

def handle_import():
    """
    Orchestrates the import process. This version is updated to handle boolean
    return values from parser and inserter modules.
    """
    path = input("请输入要导入的txt文件或文件夹路径(输入0返回):").strip()
    if path == '0':
        return

    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return

    files_to_process = []
    if os.path.isfile(path) and path.lower().endswith('.txt'):
        files_to_process.append(path)
    elif os.path.isdir(path):
        for root, _, files_in_dir in os.walk(path):
            for file_content in files_in_dir:
                if file_content.lower().endswith('.txt'):
                    files_to_process.append(os.path.join(root, file_content))
    else:
        print(f"{RED}错误: 无效的路径或文件类型.请输入单个 .txt 文件或包含 .txt 文件的文件夹路径.{RESET}")
        return

    if not files_to_process:
        print(f"{YELLOW}警告: 在 '{path}' 中没有找到 .txt 文件.{RESET}")
        return

    # --- MODIFICATION: Check boolean return from create_db_schema ---
    if not create_db_schema():
        # The module itself now prints the detailed error.
        print(f"{RED}错误：数据库初始化失败，导入操作已中止。{RESET}")
        return

    processed_count = 0
    failed_file = None  # To keep track of which file failed
    total_files_to_process = len(files_to_process)
    
    total_parse_time = 0.0
    total_db_time = 0.0
    total_operation_start_time = time.perf_counter()

    try:
        # A single transaction for all files. If one fails, all are rolled back.
        with db_connection() as conn:
            for file_path_item in files_to_process:
                failed_file = os.path.basename(file_path_item) # Assume this one might fail

                # --- MODIFICATION: Handle new return value from parser ---
                parse_start_time = time.perf_counter()
                parse_success, records_list = parse_bill_file(file_path_item)
                parse_end_time = time.perf_counter()
                total_parse_time += (parse_end_time - parse_start_time)
                
                if not parse_success:
                    # Parser already printed the error. Raise exception to trigger rollback.
                    raise ValueError("文件解析失败")

                # --- MODIFICATION: Handle new return value from inserter ---
                db_start_time = time.perf_counter()
                insert_success = insert_data_stream(conn, records_list)
                db_end_time = time.perf_counter()
                total_db_time += (db_end_time - db_start_time)
                
                if not insert_success:
                    # Inserter already printed the error. Raise exception to trigger rollback.
                    raise ValueError("数据库插入失败")

                processed_count += 1
                failed_file = None # Success, so reset the failed file variable

        # This block runs only if the transaction for all files was successful
        total_operation_end_time = time.perf_counter()
        total_duration = total_operation_end_time - total_operation_start_time

        print(f"\n{GREEN}===== 导入完成 ====={RESET}")
        print(f"成功导入文件数: {processed_count} / {total_files_to_process}")
        print("--------------------")
        print("计时统计:")
        print(f"  - 总耗时: {total_duration:.4f} 秒 ({total_duration * 1000:.2f} ms)")
        print(f"  - 文本解析总耗时: {total_parse_time:.4f} 秒 ({total_parse_time * 1000:.2f} ms)")
        print(f"  - 数据库插入总耗时: {total_db_time:.4f} 秒 ({total_db_time * 1000:.2f} ms)")
        
    except Exception as e:
        # This block runs if any exception occurs, causing a rollback
        total_operation_end_time = time.perf_counter()
        total_duration = total_operation_end_time - total_operation_start_time
        
        print(f"\n{RED}===== 导入失败 ====={RESET}")
        print(f"操作因在处理文件 '{failed_file}' 时发生错误而中止。")
        print(f"错误类型: {e}")
        print("数据库已回滚，所有本次导入的数据均未保存。")
        print("--------------------")
        print(f"成功导入文件数: {processed_count} / {total_files_to_process}")
        print(f"操作中止前总耗时: {total_duration:.4f} 秒 ({total_duration * 1000:.2f} ms)")


def main_app_loop():
    while True:
        print("\n========== 账单数据库选项 ==========\n")
        print("0. 从txt文件导入数据")
        print("1. 年消费查询")
        print("2. 月消费详情")
        print("3. 导出月账单")
        print("4. 年度分类统计")
        print("5. 退出")
        choice = input("请选择操作:").strip()

        if choice == '0':
            handle_import() # Call the local handle_import function
        elif choice == '1':
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
            # MODIFIED: Call the new function name
            display_yearly_summary(year_to_query)

        elif choice == '2':
            now = datetime.datetime.now()
            default_year = now.year
            default_month = now.month
            default_date_str = f"{default_year}{default_month:02d}"
            year_to_query = default_year
            month_to_query = default_month

            while True:
                date_input_str = input(f"请输入年月(默认为 {default_date_str}, 直接回车使用默认): ").strip()
                if not date_input_str:
                    print(f"使用默认年月: {year_to_query}-{month_to_query:02d}")
                    break
                if len(date_input_str) == 6 and date_input_str.isdigit():
                    year_val = int(date_input_str[:4])
                    month_val = int(date_input_str[4:])
                    if 1 <= month_val <= 12:
                        year_to_query = year_val
                        month_to_query = month_val
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            # MODIFIED: Call the new function name
            display_monthly_details(year_to_query, month_to_query)

        elif choice == '3':
            now = datetime.datetime.now()
            default_year = now.year
            default_month = now.month
            default_date_str = f"{default_year}{default_month:02d}"
            year_to_export = default_year
            month_to_export = default_month

            while True:
                date_input_str = input(f"请输入年月 (例如 202305, 默认为 {default_date_str}, 直接回车使用默认): ").strip()
                if not date_input_str:
                    print(f"使用默认年月: {year_to_export}-{month_to_export:02d}")
                    break
                if len(date_input_str) == 6 and date_input_str.isdigit():
                    year_val = int(date_input_str[:4])
                    month_val = int(date_input_str[4:])
                    if 1 <= month_val <= 12:
                        year_to_export = year_val
                        month_to_export = month_val
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            # MODIFIED: Call the new function name
            export_monthly_bill_as_text(year_to_export, month_to_export)

        elif choice == '4':
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
            
            # MODIFIED: Call the new function name
            display_yearly_parent_category_summary(year_to_query_stats, parent_title_str)
            
        elif choice == '5':
            print("程序结束运行")
            break
        else:
            print(f"{RED}无效输入,请输入选项中的数字(0-5).{RESET}")

if __name__ == "__main__":
    main_app_loop()