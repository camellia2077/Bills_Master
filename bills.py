import os
import time
from text_parser import parse_bill_file # Import from new parser module
from database_inserter import db_connection, insert_data_stream, create_database as create_db_schema # Import from new inserter module

# Output font colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# Expose create_database for main.py, now it calls the one from database_inserter
def create_database():
    """Creates or checks the database schema."""
    try:
        create_db_schema() # Call the actual schema creation function
        print(f"{GREEN}Database schema checked/created successfully.{RESET}")
    except Exception as e:
        # Error already printed by create_db_schema, just re-raise
        raise

def handle_import():
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
        # Error message is already printed by db_connection or the inner try-except
        # print(f"{RED}由于发生错误, 本次导入操作中所有文件的更改均未提交 (已回滚).{RESET}")
