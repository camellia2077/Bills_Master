import sqlite3
import re
import time
import os
from contextlib import contextmanager

# Output font colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

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
    except Exception as e: # Ensure commit is skipped on error
        conn.rollback() # Rollback on error
        raise # Re-raise the exception
    finally:
        conn.close() # Ensure connection is always closed

def create_database():
    try:
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
        print(f"{GREEN}Database schema checked/created successfully.{RESET}")
    except sqlite3.Error as e:
        print(f"{RED}Database error during schema creation: {e}{RESET}")
        raise # Re-raise to inform the calling function (e.g., in main.py)

def parse_and_insert_file(file_path, conn): # conn is passed in
    cursor = conn.cursor()
    current_parent_id = current_child_id = None
    parent_order = 0
    year_month_id = None
    year_month = None
    child_order_map = {}
    item_order_map = {}
    items_batch = []
    expect_remark = False
    line_num = 0
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
                    raise ValueError(f"严重错误: 无法为 {year_month} 插入或找到 YearMonth ID (行号 {line_num})")
                year_month_id = result[0]

                parent_order = 0
                child_order_map.clear()
                item_order_map.clear()
                current_parent_id = current_child_id = None
                expect_remark = True
                print(f"  Processing date: {year_month}")

            elif year_month_id:
                if re.fullmatch(r'^[A-Z]+[\u4e00-\u9fff]+$', stripped_line):
                    if items_batch:
                        cursor.executemany(ITEM_UPSERT, items_batch)
                        items_batch = []
                    parent_order += 1
                    cursor.execute(PARENT_UPSERT, (year_month_id, stripped_line, parent_order))
                    cursor.execute(PARENT_SELECT, (year_month_id, stripped_line))
                    result = cursor.fetchone()
                    current_parent_id = result[0] if result else None
                    if not current_parent_id:
                         raise ValueError(f"严重错误: 无法为 {stripped_line} 在 {year_month} 获取 Parent ID (行号 {line_num})")
                    child_order_map[current_parent_id] = 0
                    current_child_id = None

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
                    if not current_child_id:
                         raise ValueError(f"严重错误: 无法为 {stripped_line} 在 Parent ID {current_parent_id} 下获取 Child ID (行号 {line_num})")
                    item_order_map[current_child_id] = 0

                elif current_child_id:
                    match = re.match(r'^(\d+\.?\d*)\s*(.*)$', stripped_line)
                    if match:
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
    if items_batch:
        cursor.executemany(ITEM_UPSERT, items_batch)


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
        for root, _, files_in_dir in os.walk(path): # Renamed 'files' to 'files_in_dir'
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

    try:
        with db_connection() as conn: # Single transaction for all files in this import operation
            for file_path_item in files_to_process:
                print(f"--- 开始导入文件: {os.path.basename(file_path_item)} ---")
                try:
                    parse_and_insert_file(file_path_item, conn)
                    processed_count += 1
                    # Removed processed_files_list as it wasn't used for the final success message anymore
                    print(f"{GREEN}  文件 {os.path.basename(file_path_item)} 已成功暂存处理.{RESET}")
                except Exception as e:
                    print(f"{RED}错误: 处理文件 {os.path.basename(file_path_item)} 时发生严重错误: {e}{RESET}")
                    print(f"{RED}由于此文件错误, 本次导入操作中所有文件的更改都将回滚.{RESET}")
                    raise # Re-raise to trigger rollback in db_connection and the outer catch

        # If the loop completes without re-raising an exception, commit happens via db_connection context manager.
        duration = time.perf_counter() - start_time
        print(f"\n{GREEN}数据导入事务处理完成!{RESET}")
        print(f"成功处理文件数: {processed_count}")
        print(f"总耗时: {duration:.4f} 秒")
        print(f"{GREEN}所有成功处理文件的更改已提交.{RESET}")

    except Exception as e:
        # This catches errors from db_connection() opening, or errors re-raised from file processing.
        print(f"\n{RED}导入操作因错误中断: {e}{RESET}")
        print(f"{RED}由于发生错误, 本次导入操作中所有文件的更改均未提交 (已回滚).{RESET}")
