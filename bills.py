import sqlite3
import re
import time
import os
from contextlib import contextmanager
import shutil
from query import query_1,query_2,query_3,query_4
#ANSI转义码_颜色代码
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m" 

ENABLE_AUTO_RENEWAL = False

# 自动续费项目映射: '子标题':(金额, 描述)
AUTO_RENEWAL_MAP = {
    "web_service": (15.0, "uu加速器"),
}



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
    """带事务管理的数据库连接上下文管理器"""
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
    """创建数据库表结构并添加索引"""
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

def parse_and_insert_file(file_path, conn, enable_auto_renewal):
    """
    解析文件,插入数据到数据库,并在需要时修改原始TXT文件以包含自动续费项.
    使用临时文件策略保证安全.
    """
    cursor = conn.cursor()
    current_parent_id = current_child_id = None
    parent_order = 0
    year_month_id = None
    year_month = None
    child_order_map = {}
    item_order_map = {}
    items_batch = [] # 用于数据库批量插入
    expect_remark = False
    found_auto_renewal_keys_for_month = set()
    txt_modified = False # 标记TXT文件是否需要被实际修改

    # 生成临时文件名
    temp_file_path = file_path + ".tmp"

    try:
        # 同时打开原文件读 和 临时文件写
        with open(file_path, 'r', encoding='utf-8') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:

            for line_num, line in enumerate(infile, 1):
                # 1. 先将原始行写入临时文件 (保留原始格式,包括换行符)
                outfile.write(line)

                # 2. 处理行内容用于数据库插入
                stripped_line = line.strip()
                if not stripped_line:
                    continue # 空行跳过处理,但已写入临时文件

                # --- 处理 REMARK: (逻辑不变) ---
                if expect_remark:
                    if stripped_line.startswith('REMARK:'):
                        remark = stripped_line[7:].strip()
                        if year_month:
                            cursor.execute('UPDATE YearMonth SET remark = ? WHERE year_month = ?', (remark, year_month))
                        expect_remark = False
                        continue
                    else:
                        expect_remark = False
                # --- REMARK 处理结束 ---

                # --- 处理 DATE: (逻辑不变, 除了检查上月遗漏) ---
                if stripped_line.startswith('DATE:'):
                    # 检查上一个月份的未匹配自动续费项 (数据库逻辑,不影响TXT)
                    if enable_auto_renewal and year_month_id is not None:
                        all_expected_keys = set(AUTO_RENEWAL_MAP.keys())
                        missed_keys = all_expected_keys - found_auto_renewal_keys_for_month
                        for key in missed_keys:
                            amount, desc = AUTO_RENEWAL_MAP[key]
                            print(f"{YELLOW}提示(数据库): 文件 {os.path.basename(file_path)} ({year_month}) 未找到子标题 '{key}',数据库跳过 '{amount}{desc}' 添加.{RESET}")

                    # 提交数据库批处理
                    if items_batch:
                        cursor.executemany(ITEM_UPSERT, items_batch)
                        items_batch = []

                    # 解析新的年月等 (数据库逻辑)
                    year_month = stripped_line[5:].strip()
                    cursor.execute(YEAR_MONTH_INSERT, (year_month,))
                    cursor.execute(YEAR_MONTH_SELECT, (year_month,))
                    result = cursor.fetchone()
                    year_month_id = result[0] if result else None

                    # 重置状态 (数据库逻辑)
                    parent_order = 0
                    child_order_map.clear()
                    item_order_map.clear()
                    found_auto_renewal_keys_for_month.clear()
                    current_parent_id = current_child_id = None
                    expect_remark = True
                # --- DATE 处理结束 ---

                # --- 处理 Parent / Child / Item (数据库逻辑 + TXT写入触发点) ---
                elif year_month_id:
                    # 处理 Parent Title (数据库逻辑)
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

                    # 处理 Child Title (数据库逻辑 + **TXT修改触发点**)
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

                            # --- **核心修改:自动续费处理 (数据库 & TXT)** ---
                            if enable_auto_renewal and stripped_line in AUTO_RENEWAL_MAP:
                                amount, description = AUTO_RENEWAL_MAP[stripped_line]
                                auto_renewal_desc_db = description + " (自动续费)"
                                auto_renewal_desc_txt = description + " (自动续费)" # TXT也加标记

                                # A. 数据库部分 (添加到 items_batch)
                                item_order_db = item_order_map.get(current_child_id, 0) + 1
                                item_order_map[current_child_id] = item_order_db
                                items_batch.append((
                                    current_child_id,
                                    amount,
                                    auto_renewal_desc_db,
                                    item_order_db
                                ))
                                found_auto_renewal_keys_for_month.add(stripped_line)

                                # B. TXT 部分 (直接写入 outfile)
                                #    格式化金额,整数不带小数点,小数保留两位
                                amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                                txt_line_to_insert = f"{amount_str}{auto_renewal_desc_txt}\n"#txt文本插入的自动续费子项目
                                outfile.write(txt_line_to_insert) # 在子标题行之后写入
                                txt_modified = True # 标记文件已被修改

                                print(f"{GREEN}信息: 文件 {os.path.basename(file_path)} ({year_month}) 在'{stripped_line}'下添加了'{amount}{description}' (数据库和TXT).{RESET}")
                            # --- 自动续费处理结束 ---

                    # 处理 Item (数据库逻辑)
                    elif current_child_id:
                        if match := re.match(r'^(\d+\.?\d*)\s*(.*)$', stripped_line):
                            item_order = item_order_map.get(current_child_id, 0) + 1
                            item_order_map[current_child_id] = item_order
                            items_batch.append((
                                current_child_id,
                                float(match.group(1)),
                                match.group(2).strip(),
                                item_order
                            ))
                        
            # --- 文件循环结束后 ---
            # 处理最后一个月份的数据库未匹配项
            if enable_auto_renewal and year_month_id is not None:
                 all_expected_keys = set(AUTO_RENEWAL_MAP.keys())
                 missed_keys = all_expected_keys - found_auto_renewal_keys_for_month
                 for key in missed_keys:
                      amount, desc = AUTO_RENEWAL_MAP[key]
                      print(f"{YELLOW}提示(数据库): 文件 {os.path.basename(file_path)} ({year_month}) 结束时未找到子标题 '{key}',数据库跳过 '{amount}{desc}' 添加.{RESET}")

            # 提交最后一批数据库数据
            if items_batch:
                cursor.executemany(ITEM_UPSERT, items_batch)

        # --- with 块结束,文件已关闭 ---

        # 3. 如果TXT文件被修改过,则替换原文件
        if txt_modified:
            try:
                # 使用shutil.move进行替换,通常比os.remove+os.rename更原子性或健壮
                shutil.move(temp_file_path, file_path)
                print(f"{GREEN}信息: 文件 {os.path.basename(file_path)} 已成功更新自动续费内容.{RESET}")
            except OSError as e:
                print(f"{RED}错误: 无法将 {temp_file_path} 替换回 {file_path}.错误: {e}{RESET}")
                # 尝试删除临时文件,避免残留
                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except OSError:
                        pass # 忽略删除错误
                raise RuntimeError(f"无法更新原始文件 {file_path}") from e
        else:
            # 如果TXT未被修改,则直接删除临时文件
            if os.path.exists(temp_file_path):
                 try:
                     os.remove(temp_file_path)
                 except OSError as e:
                      print(f"{YELLOW}警告: 未修改TXT文件,但删除临时文件 {temp_file_path} 失败: {e}{RESET}")

    except Exception as e:
        # 捕获所有在文件处理或数据库操作中发生的错误
        # 尝试删除可能存在的临时文件
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                print(f"{YELLOW}信息: 因发生错误,已删除临时文件 {temp_file_path}.{RESET}")
            except OSError as rm_err:
                print(f"{RED}严重错误: 处理中发生错误,且无法删除临时文件 {temp_file_path}.错误: {rm_err}{RESET}")
        error_msg = f"处理文件 {os.path.basename(file_path)} 时失败: {str(e)}"
        if 'line_num' in locals():
            error_msg += f" (接近行号 {line_num})"
        raise RuntimeError(error_msg) from e




def handle_import(enable_auto_renewal):
    """处理数据导入流程"""
    path = input("请输入要导入的txt文件或文件夹路径(输入0返回):").strip()
    if path == '0':
        return

    if not os.path.exists(path):
        print(f"{RED}错误: 路径 '{path}' 不存在.{RESET}")
        return

    try:
        with db_connection() as conn:
            start_time = time.perf_counter()
            processed_count = 0
            processed_files_list = [] # 用于跟踪实际处理的文件

            if os.path.isfile(path) and path.lower().endswith('.txt'):
                try:
                    # 将 enable_auto_renewal 传递下去
                    parse_and_insert_file(path, conn, enable_auto_renewal)
                    processed_count = 1
                    processed_files_list.append(os.path.basename(path))
                except Exception as e:
                     print(f"{RED}错误: 处理文件 {os.path.basename(path)} 时发生错误: {e}{RESET}")
                     # 选择是否继续处理其他文件,或在此处直接返回/抛出异常
                     # return # 如果希望单个文件错误停止整个导入

            elif os.path.isdir(path):
                files_to_process = []
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.lower().endswith('.txt'):
                            files_to_process.append(os.path.join(root, file))

                if not files_to_process:
                     print(f"{YELLOW}警告: 文件夹 '{path}' 中没有找到 .txt 文件.{RESET}")
                     return

                for file_path in files_to_process:
                    try:
                         # 将 enable_auto_renewal 传递下去
                         parse_and_insert_file(file_path, conn, enable_auto_renewal)
                         processed_count += 1
                         processed_files_list.append(os.path.basename(file_path))
                    except Exception as e:
                         print(f"{RED}错误: 处理文件 {os.path.basename(file_path)} 时发生错误: {e}{RESET}")
                         # 选择是否继续处理其他文件

                if processed_count == 0 and files_to_process:
                     print(f"{RED}错误: 尝试处理 {len(files_to_process)} 个文件,但所有文件都处理失败.{RESET}")
                     # 由于使用了事务,即使部分文件失败,只要没有raise导致conn.rollback(),成功的仍然会提交
                     # 但这里可以根据需要决定是否强制回滚 conn.rollback() 然后 raise Exception("...")

            else:
                print(f"{RED}错误: 无效的路径或文件类型.请输入单个 .txt 文件或包含 .txt 文件的文件夹路径.{RESET}")
                return # 无需继续执行

            # 只有在没有严重错误(导致回滚)的情况下才打印成功信息
            if processed_count > 0:
                 duration = time.perf_counter() - start_time
                 print(f"\n{GREEN}数据导入完成!{RESET}")
                 print(f"成功处理文件数: {processed_count}")
                 # print(f"处理的文件: {', '.join(processed_files_list)}") # 如果文件过多可能不适合打印
                 print(f"总耗时: {duration:.4f} 秒")
            elif not processed_files_list and not os.path.isfile(path): # 文件夹情况,但没找到txt
                 pass # 之前已经打印过警告
            else: # 尝试处理但失败数为0,或者路径无效
                 print(f"{YELLOW}没有成功处理任何文件.{RESET}")


    except RuntimeError as e: # 捕获由 parse_and_insert_file 抛出的特定错误
         print(f"\n{RED}导入操作失败: {e}{RESET}")
         print(f"{RED}数据库更改已回滚,数据未保存.{RESET}")
    except Exception as e: # 捕获其他意外错误,例如数据库连接问题
         print(f"\n{RED}发生意外错误导致导入失败: {e}{RESET}")
         print(f"{RED}数据库更改可能已回滚.{RESET}")

def main():
    create_database()
    print("\n========== 自动续费设置 ==========")
    if ENABLE_AUTO_RENEWAL:
        print(f"{GREEN}自动续费功能已开启.{RESET}")
        if not AUTO_RENEWAL_MAP:
            print(f"{YELLOW}警告: 自动续费功能已开启,但 AUTO_RENEWAL_MAP 为空,将不会添加任何自动续费项目.{RESET}")
            print(f"{YELLOW}请在脚本顶部编辑 AUTO_RENEWAL_MAP 添加项目.{RESET}")
        else:
            print("将为以下子标题自动添加项目:")
            for key, (amount, desc) in AUTO_RENEWAL_MAP.items():
                print(f"  - '{key}': {amount} {desc}")
    else:
        print(f"{YELLOW}自动续费功能已关闭.{RESET}")
    # --- 新增结束 ---

    while True:
        print("\n========== 选项 ==========\n")
        print("0. 导入数据")
        print("1. 年消费查询")
        print("2. 月消费详情")
        print("3. 导出月账单")
        print("4. 年度分类统计")
        print("5. 退出")
        choice = input("请选择操作:").strip()

        if choice == '0':
            # 将 ENABLE_AUTO_RENEWAL 传递给 handle_import
            handle_import(ENABLE_AUTO_RENEWAL)
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
                 continue # 跳过本次循环
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
