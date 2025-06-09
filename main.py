import datetime
import os
import time

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"
from query_db import query_1, query_2, query_3, query_4

# Import independent modules for parsing and database operations
from text_parser import parse_bill_file
from database_inserter import db_connection, insert_data_stream, create_database as create_db_schema

def handle_import():
    """
    Orchestrates the import process by parsing files and inserting data into the database.
    This function is now part of the main application logic.
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

    processed_count = 0
    start_time = time.perf_counter()

    # The db_connection context manager will handle commit/rollback for the entire import operation
    try:
        with db_connection() as conn: # Single transaction for all files
            for file_path_item in files_to_process:
                file_basename = os.path.basename(file_path_item)
                print(f"--- 开始处理文件: {file_basename} ---")
                try:
                    # 1. Parse the file to get a stream of structured data
                    data_stream = parse_bill_file(file_path_item)

                    # 2. Insert the structured data into the database
                    insert_data_stream(conn, data_stream)

                    processed_count += 1
                    print(f"{GREEN}  文件 {file_basename} 已成功暂存处理 (等待最终提交).{RESET}")
                except ValueError as ve: # Catch parsing errors or logical errors during insertion
                    print(f"{RED}处理文件 {file_basename} 时发生错误: {ve}{RESET}")
                    print(f"{RED}由于此文件错误, 本次导入操作中所有文件的更改都将回滚.{RESET}")
                    raise # Re-raise to trigger rollback in db_connection and the outer catch
                except Exception as e:
                    print(f"{RED}处理文件 {file_basename} 时发生未预料的严重错误: {e}{RESET}")
                    print(f"{RED}由于此文件错误, 本次导入操作中所有文件的更改都将回滚.{RESET}")
                    raise # Re-raise

        # If the loop completes without re-raising, commit happens via db_connection
        duration = time.perf_counter() - start_time
        print(f"\n{GREEN}所有文件处理完毕!{RESET}")
        print(f"成功暂存并准备提交文件数: {processed_count}")
        print(f"总耗时: {duration:.4f} 秒")
        print(f"{GREEN}数据库事务已成功提交.{RESET}")

    except Exception as e:
        # This catches errors from db_connection opening, or errors re-raised from file processing.
        # The rollback is handled by db_connection's __exit__ method.
        print(f"\n{RED}导入操作因错误中断.{RESET}")


def main_app_loop():
    try:
        # Call the schema creation function directly from the database module
        create_db_schema()
        print(f"{GREEN}Database schema checked/created successfully.{RESET}")
    except Exception as e:
        print(f"{RED}严重错误: 数据库初始化失败: {e}{RESET}")
        print(f"{RED}程序可能无法正常运行. 请检查数据库文件权限或配置.{RESET}")
        # return # Optionally exit

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
            query_1(year_to_query)

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
            query_2(year_to_query, month_to_query)

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
            query_3(year_to_export, month_to_export)

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
            
            query_4(year_to_query_stats, parent_title_str)
            
        elif choice == '5':
            print("程序结束运行")
            break
        else:
            print(f"{RED}无效输入,请输入选项中的数字(0-5).{RESET}")

if __name__ == "__main__":
    main_app_loop()