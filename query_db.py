import sqlite3

def get_sorted_data(conn, year_month):
    """统一获取排序后的数据(父按总金额倒序,子按总金额倒序,项目按金额倒序)"""
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
