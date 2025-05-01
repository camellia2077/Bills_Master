import sqlite3
import re
import time
import os
from contextlib import contextmanager
# 假设 query.py 在同一个目录下或 Python 路径中
from query import query_1,query_2,query_3,query_4

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"

YEAR_MONTH_INSERT = '''
    INSERT INTO YearMonth (year_month)
    VALUES (?)
    ON CONFLICT(year_month) DO NOTHING
    '''

YEAR_MONTH_SELECT = 'SELECT id FROM YearMonth WHERE year_month = ?'

PARENT_UPSERT = '''
    INSERT INTO Parent (year_month_id, title, order_num)
    VALUES (?, ?, ?)
    ON CONFLICT(year_month_id, title)
    DO UPDATE SET order_num = excluded.order_num'''
PARENT_SELECT = 'SELECT id FROM Parent WHERE year_month_id = ? AND title = ?'

CHILD_UPSERT = '''
    INSERT INTO Child (parent_id, title, order_num)
    VALUES (?, ?, ?)
    ON CONFLICT(parent_id, title)
    DO UPDATE SET order_num = excluded.order_num'''
CHILD_SELECT = 'SELECT id FROM Child WHERE parent_id = ? AND title = ?'

ITEM_UPSERT = '''
    INSERT INTO Item (child_id, amount, description, order_num)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(child_id, amount, description)
    DO UPDATE SET order_num = excluded.order_num'''

@contextmanager
def db_connection():
    conn = sqlite3.connect('bills.db')
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def create_database():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS YearMonth (
                id INTEGER PRIMARY KEY,
                year_month TEXT UNIQUE NOT NULL,
                remark TEXT
            )''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Parent (
                id INTEGER PRIMARY KEY,
                year_month_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(year_month_id, title)
            )''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(parent_id, title)
            )''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Item (
                id INTEGER PRIMARY KEY,
                child_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(child_id, amount, description)
            )''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_parent_ym ON Parent(year_month_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_child_parent ON Child(parent_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_item_child ON Item(child_id)')
        conn.commit()


def parse_and_insert_file(file_path, conn):
    cursor = conn.cursor()
    current_parent_id = current_child_id = None
    parent_order = 0
    year_month_id = None
    year_month = None
    child_order_map = {}
    item_order_map = {}
    items_batch = []
    expect_remark = False
    line_num = 0 # Keep track for error reporting

    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            for line_num, line in enumerate(infile, 1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                if expect_remark:
                    if stripped_line.startswith('REMARK:'):
                        remark = stripped_line[7:].strip()
                        if year_month:
                            cursor.execute('UPDATE YearMonth SET remark = ? WHERE year_month = ?', (remark, year_month))
                        expect_remark = False
                        continue
                    else:
                        expect_remark = False

                if stripped_line.startswith('DATE:'):
                    if items_batch:
                        cursor.executemany(ITEM_UPSERT, items_batch)
                        items_batch = []

                    year_month = stripped_line[5:].strip()
                    cursor.execute(YEAR_MONTH_INSERT, (year_month,))
                    cursor.execute(YEAR_MONTH_SELECT, (year_month,))
                    result = cursor.fetchone()
                    if not result:
                         # Should not happen with ON CONFLICT DO NOTHING, but safety check
                         raise ValueError(f"Failed to insert or find YearMonth for {year_month}")
                    year_month_id = result[0]

                    parent_order = 0
                    child_order_map.clear()
                    item_order_map.clear()
                    current_parent_id = current_child_id = None
                    expect_remark = True
                    print(f"  Processing date: {year_month}") # Feedback

                elif year_month_id:
                    # Parent Title
                    if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+$', stripped_line):
                        if items_batch:
                            cursor.executemany(ITEM_UPSERT, items_batch)
                            items_batch = []
                        parent_order += 1
                        cursor.execute(PARENT_UPSERT, (year_month_id, stripped_line, parent_order))
                        cursor.execute(PARENT_SELECT, (year_month_id, stripped_line))
                        result = cursor.fetchone()
                        current_parent_id = result[0] if result else None
                        if current_parent_id:
                            child_order_map[current_parent_id] = 0
                        current_child_id = None
                        #print(f"    Parent: {stripped_line} (ID: {current_parent_id})")

                    # Child Title
                    elif current_parent_id and re.fullmatch(r'^[a-z]+(_[a-z]+)+$', stripped_line):
                        if items_batch:
                            cursor.executemany(ITEM_UPSERT, items_batch)
                            items_batch = []
                        child_order = child_order_map.get(current_parent_id, 0) + 1
                        child_order_map[current_parent_id] = child_order
                        cursor.execute(CHILD_UPSERT, (current_parent_id, stripped_line, child_order))
                        cursor.execute(CHILD_SELECT, (current_parent_id, stripped_line))
                        result = cursor.fetchone()
                        current_child_id = result[0] if result else None
                        if current_child_id:
                            item_order_map[current_child_id] = 0
                        #print(f"      Child: {stripped_line} (ID: {current_child_id})")

                    # Item
                    elif current_child_id:
                        if match := re.match(r'^(\d+\.?\d*)\s*(.*)$', stripped_line):
                            item_order = item_order_map.get(current_child_id, 0) + 1
                            item_order_map[current_child_id] = item_order
                            amount = float(match.group(1))
                            description = match.group(2).strip()
                            items_batch.append((
                                current_child_id,
                                amount,
                                description,
                                item_order
                            ))
                            #print(f"        Item: {amount} {description}")
                        # Silently ignore lines that don't match item format under a child

            # After the loop, process any remaining items
            if items_batch:
                cursor.executemany(ITEM_UPSERT, items_batch)

    except Exception as e:
        error_msg = f"处理文件 {os.path.basename(file_path)} 时失败: {str(e)}"
        if line_num > 0:
           error_msg += f" (接近行号 {line_num})"
        # Error will be caught by handle_import, leading to rollback
        raise RuntimeError(error_msg) from e


def handle_import():
    path = input("请输入要导入的txt文件或文件夹路径(输入0返回):").strip()
    if path == '0':
        return

    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return

    try:
        with db_connection() as conn: # Transaction managed here
            start_time = time.perf_counter()
            processed_count = 0
            processed_files_list = []
            error_occurred = False

            files_to_process = []
            if os.path.isfile(path) and path.lower().endswith('.txt'):
                 files_to_process.append(path)
            elif os.path.isdir(path):
                 for root, dirs, files in os.walk(path):
                     for file in files:
                         if file.lower().endswith('.txt'):
                             files_to_process.append(os.path.join(root, file))
            else:
                print(f"{RED}错误: 无效的路径或文件类型.请输入单个 .txt 文件或包含 .txt 文件的文件夹路径.{RESET}")
                return

            if not files_to_process:
                print(f"{YELLOW}警告: 在 '{path}' 中没有找到 .txt 文件.{RESET}")
                return

            for file_path in files_to_process:
                print(f"--- 开始导入文件: {os.path.basename(file_path)} ---")
                try:
                    parse_and_insert_file(file_path, conn)
                    processed_count += 1
                    processed_files_list.append(os.path.basename(file_path))
                    print(f"{GREEN}  成功导入: {os.path.basename(file_path)}{RESET}")
                except Exception as e:
                    print(f"{RED}错误: 导入文件 {os.path.basename(file_path)} 时发生错误: {e}{RESET}")
                    error_occurred = True
                    # Continue to next file, but transaction will be rolled back at the end if any error occurred

            # If any error occurred during the loop, the transaction will be rolled back by db_connection's __exit__
            if error_occurred:
                 print(f"\n{RED}由于处理过程中出现错误, 本次导入操作中的所有更改已被回滚.{RESET}")
                 # No need to manually rollback, context manager handles it
                 return # Exit after rollback

            # Only print success if no errors caused a rollback
            duration = time.perf_counter() - start_time
            print(f"\n{GREEN}数据导入完成!{RESET}")
            print(f"成功处理文件数: {processed_count}")
            # print(f"处理的文件: {', '.join(processed_files_list)}")
            print(f"总耗时: {duration:.4f} 秒")

    except Exception as e: # Catch errors like DB connection issues, or errors raised from parse_and_insert_file
        print(f"\n{RED}导入操作失败: {e}{RESET}")
        print(f"{RED}数据库更改已回滚 (如果连接成功的话).{RESET}")


def main():
    create_database() # Ensure DB exists on startup

    while True:
        print("\n========== 账单数据库选项 ==========\n")
        print("0. 从 TXT 导入数据")
        print("1. 年消费查询")
        print("2. 月消费详情")
        print("3. 导出月账单")
        print("4. 年度分类统计")
        print("5. 退出")
        choice = input("请选择操作:").strip()

        if choice == '0':
            handle_import()
        elif choice == '1':
            year = input("请输入年份 (例如 2024): ").strip()
            if year.isdigit() and len(year) == 4:
                 query_1(year)
            else:
                 print(f"{RED}输入错误,请输入四位数字年份.{RESET}")
        elif choice == '2':
            while True:
                date_input = input("请输入年月 (例如 202503): ").strip()
                if len(date_input) == 6 and date_input.isdigit():
                    year = int(date_input[:4])
                    month = int(date_input[4:])
                    if 1 <= month <= 12:
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            query_2(year, month)
        elif choice == '3':
            while True:
                date_input = input("请输入年月 (例如 202503): ").strip()
                if len(date_input) == 6 and date_input.isdigit():
                    year = int(date_input[:4])
                    month = int(date_input[4:])
                    if 1 <= month <= 12:
                        break
                    else:
                        print(f"{RED}输入的月份无效 (必须介于 01 到 12 之间).{RESET}")
                else:
                    print(f"{RED}输入格式错误, 请输入6位数字, 例如 202503.{RESET}")
            query_3(year, month)
        elif choice == '4':
            year = input("请输入年份 (例如 2024): ").strip()
            if not (year.isdigit() and len(year) == 4):
                 print(f"{RED}年份输入错误,请输入四位数字年份.{RESET}")
                 continue
            parent = input("请输入父标题 (例如 RENT房租水电): ").strip()
            if not parent:
                 print(f"{RED}父标题不能为空.{RESET}")
                 continue
            query_4(year, parent)
        elif choice == '5':
            print("程序结束运行")
            break
        else:
            print(f"{RED}无效输入, 请输入选项中的数字 (0-5).{RESET}")

if __name__ == "__main__":
    main()
