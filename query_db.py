#用于从数据库中查询数据
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
    """Queries annual consumption statistics and returns them as a dictionary."""
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
    conn.close()
    
    if results:
        year_total = sum(row[1] for row in results)
        month_count = len(results)
        average = year_total / month_count
        
        monthly_details = [{'year_month': ym_str, 'total': total} for ym_str, total in results]
        
        return {
            'year_total': year_total,
            'average_monthly': average,
            'monthly_details': monthly_details
        }
    else:
        return None

def query_2(year, month):
    """Queries detailed monthly consumption and returns it as a dictionary."""
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
    total_result = cursor.fetchone()
    
    if not total_result or total_result[0] is None:
        conn.close()
        return None
        
    total_consumption = total_result[0]
    data = get_sorted_data(conn, ym)
    conn.close()

    return {
        'total_consumption': total_consumption,
        'details': data
    }


def query_3(year, month):
    """Generates a bill string in the original file format and returns it."""
    ym = f"{year}{month:02d}"
    conn = sqlite3.connect('bills.db')
    
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM YearMonth WHERE year_month = ?', (ym,))
    if not cursor.fetchone():
        conn.close()
        return None
    
    data = get_sorted_data(conn, ym)
    conn.close()

    output = [f"DATE:{ym}"]
    first_parent = True
    
    for p_title, p_data in data.items():
        if not first_parent:
            output.append('')
        output.append(p_title)
        
        for c_title, c_data in p_data['children'].items():
            output.append(c_title)
            
            for amount, desc in c_data['items']:
                amount_str = f"{int(amount)}" if amount == int(amount) else f"{amount}"
                output.append(f"{amount_str} {desc}")
        
        first_parent = False
    
    return '\n'.join(output)

def query_4(year, parent):
    """Queries the total annual consumption for a specific parent category and returns the value."""
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
    conn.close()
    return total