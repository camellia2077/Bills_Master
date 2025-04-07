#修改菜单交互逻辑
import sqlite3
import re
import time
import os
from contextlib import contextmanager

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
                year_month TEXT UNIQUE NOT NULL
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
    """解析文件并插入数据（使用传入的连接）"""
    cursor = conn.cursor()
    current_parent_id = current_child_id = None
    parent_order = child_order = 0
    year_month_id = None
    child_order_map = {}
    item_order_map = {}
    items_batch = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                if stripped_line.startswith('DATE'):
                    if items_batch:
                        cursor.executemany(ITEM_UPSERT, items_batch)
                        items_batch = []
                    year_month = stripped_line[4:]
                    cursor.execute(YEAR_MONTH_INSERT, (year_month,))
                    cursor.execute(YEAR_MONTH_SELECT, (year_month,))
                    result = cursor.fetchone()
                    year_month_id = result[0] if result else None
                    parent_order = 0
                    child_order_map.clear()
                    item_order_map.clear()
                    current_parent_id = current_child_id = None

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
                        item_order_map[current_child_id] = 0

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
            
            if items_batch:
                cursor.executemany(ITEM_UPSERT, items_batch)
    except Exception as e:
        raise RuntimeError(f"处理文件 {file_path} 失败: {str(e)}") from e

def get_sorted_data(conn, year_month):
    """统一获取排序后的数据（父按总金额倒序，子按总金额倒序，项目按金额倒序）"""
    cursor = conn.cursor()
    
    cursor.execute('''
        WITH parent_totals AS (
            SELECT p.id, p.title, SUM(i.amount) AS total
            FROM Parent p
            JOIN Child c ON p.id = c.parent_id
            JOIN Item i ON c.id = i.child_id
            WHERE p.year_month_id = (SELECT id FROM YearMonth WHERE year_month = ?)
            GROUP BY p.id
        ),
        child_totals AS (
            SELECT c.id, c.parent_id, c.title, SUM(i.amount) AS total
            FROM Child c
            JOIN Item i ON c.id = i.child_id
            GROUP BY c.id
        )
        SELECT 
            p.title AS parent_title,
            p.total AS parent_total,
            c.title AS child_title,
            c.total AS child_total,
            i.amount,
            i.description
        FROM parent_totals p
        JOIN child_totals c ON p.id = c.parent_id
        JOIN Item i ON c.id = i.child_id
        ORDER BY 
            p.total DESC,
            c.total DESC,
            i.amount DESC
    ''', (year_month,))
    
    structured_data = {}
    for row in cursor:
        (p_title, p_total, c_title, c_total, amount, desc) = row
        
        if p_title not in structured_data:
            structured_data[p_title] = {
                'total': p_total,
                'children': {}
            }
        
        if c_title not in structured_data[p_title]['children']:
            structured_data[p_title]['children'][c_title] = {
                'total': c_total,
                'items': []
            }
        
        structured_data[p_title]['children'][c_title]['items'].append(
            (amount, desc)
        )
    
    return structured_data

def query_1(year):
    conn = sqlite3.connect('bills.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ym.year_month, SUM(i.amount)
        FROM YearMonth ym
        JOIN Parent p ON ym.id = p.year_month_id
        JOIN Child c ON p.id = c.parent_id
        JOIN Item i ON c.id = i.child_id
        WHERE ym.year_month LIKE ? || '%'
        GROUP BY ym.year_month
    ''', (year,))
    results = cursor.fetchall()
    
    if results:
        year_total = sum(row[1] for row in results)
        month_count = len(results)
        average = year_total / month_count
        
        print("-------------------------------\n")
        print(f"{year}年消费统计:")
        print(f"年度总消费: {year_total:.2f}元")
        print(f"月均消费: {average:.2f}元")
        print("各月消费明细:")
        for ym_str, total in results:
            year_part = ym_str[:4]
            month_part = int(ym_str[4:])
            print(f"  {year_part}年{month_part}月: {total:.2f}元")
        print("\n")
        print("-------------------------------")
    else:
        print("无数据")
    
    conn.close()

def query_2(year, month):
    ym = f"{year}{month:02d}"
    conn = sqlite3.connect('bills.db')
    
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(i.amount)
        FROM Item i
        JOIN Child c ON i.child_id = c.id
        JOIN Parent p ON c.parent_id = p.id
        JOIN YearMonth ym ON p.year_month_id = ym.id
        WHERE ym.year_month = ?
    ''', (ym,))
    total = cursor.fetchone()[0]
    
    if not total:
        print("无数据")
        conn.close()
        return
    
    print(f"\n{ym}总消费: {total:.2f}元")
    
    data = get_sorted_data(conn, ym)
    
    for p_title, p_data in data.items():
        print(f"\n【{p_title}】{p_data['total']:.2f}元 ({p_data['total']/total*100:.1f}%)")
        
        for c_title, c_data in p_data['children'].items():
            print(f"\n    {c_title}: {c_data['total']:.2f}元")
            
            for amount, desc in c_data['items']:
                amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount}"
                print(f"        {amount_str} {desc}")
    
    conn.close()

def query_3(year, month):
    ym = f"{year}{month:02d}"
    conn = sqlite3.connect('bills.db')
    
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM YearMonth WHERE year_month = ?', (ym,))
    if not cursor.fetchone():
        print("无数据")
        conn.close()
        return
    
    data = get_sorted_data(conn, ym)
    
    output = [f"DATE{ym}"]
    first_parent = True
    
    for p_title, p_data in data.items():
        if not first_parent:
            output.append('')
        output.append(p_title)
        
        for c_title, c_data in p_data['children'].items():
            output.append(c_title)
            
            for amount, desc in c_data['items']:
                amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount}"
                output.append(f"{amount_str}{desc}")
        
        first_parent = False
    
    print('\n'.join(output))
    conn.close()

def query_4(year, parent):
    conn = sqlite3.connect('bills.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(i.amount)
        FROM Item i
        JOIN Child c ON i.child_id = c.id
        JOIN Parent p ON c.parent_id = p.id
        JOIN YearMonth ym ON p.year_month_id = ym.id
        WHERE ym.year_month LIKE ? || '%' AND p.title = ?
    ''', (year, parent))
    total = cursor.fetchone()[0]
    if total:
        print(f"{year}年[{parent}]总消费: {total:.2f}元")
    else:
        print("无数据")
    conn.close()

def handle_import():
    """处理数据导入流程"""
    path = input("请输入要导入的txt文件或文件夹路径（输入0返回）：").strip()
    if path == '0':
        return
    
    if not os.path.exists(path):
        print("路径不存在")
        return

    try:
        with db_connection() as conn:
            start_time = time.perf_counter()
            processed = 0
            
            if os.path.isfile(path) and path.endswith('.txt'):
                parse_and_insert_file(path, conn)
                processed = 1
            elif os.path.isdir(path):
                processed_files = []
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.endswith('.txt'):
                            file_path = os.path.join(root, file)
                            processed_files.append(file_path)
                for file_path in processed_files:
                    parse_and_insert_file(file_path, conn)
                processed = len(processed_files)
                
                if not processed:
                    print("文件夹中没有txt文件")
                    return
            else:
                print("无效路径")
                return

            print(f"数据导入完成，处理文件数：{processed}，总耗时：{time.perf_counter() - start_time:.4f}秒")
            
    except Exception as e:
        print(f"操作已回滚，数据未保存。错误原因：{str(e)}")

def main():
    create_database()
    while True:
        print("\n========== 主菜单 ==========")
        print("0. 导入数据")
        print("1. 年消费查询")
        print("2. 月消费详情")
        print("3. 导出月账单")
        print("4. 年度分类统计")
        print("5. 退出")
        choice = input("请选择操作：").strip()

        if choice == '0':
            handle_import()
        elif choice == '1':
            year = input("请输入年份: ")
            query_1(year)
        elif choice == '2':
            while True:
                date_input = input("请输入年月（例如202503）: ").strip()
                if len(date_input) != 6 or not date_input.isdigit():
                    print("输入格式错误，请输入6位数字，例如202503。")
                    continue
                year = int(date_input[:4])
                month = int(date_input[4:])
                if 1 <= month <= 12:
                    break
                print("月份无效，必须介于01到12之间。")
            query_2(year, month)
        elif choice == '3':
            while True:
                date_input = input("请输入年月（例如202503）: ").strip()
                if len(date_input) != 6 or not date_input.isdigit():
                    print("输入格式错误，请输入6位数字，例如202503。")
                    continue
                year = int(date_input[:4])
                month = int(date_input[4:])
                if 1 <= month <= 12:
                    break
                print("月份无效，必须介于01到12之间。")
            query_3(year, month)
        elif choice == '4':
            year = input("年份: ")
            parent = input("父标题: ")
            query_4(year, parent)
        elif choice == '5':
            print("感谢使用，再见！")
            break
        else:
            print("无效输入，请重新选择。")

if __name__ == "__main__":
    main()