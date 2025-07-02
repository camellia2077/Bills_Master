# query_db.py
import sqlite3

# ==============================================================================
# 0. 查询基类 (用于共享逻辑)
# ==============================================================================
class BaseQuery:
    """所有查询类的基类，用于共享数据库路径。"""
    def __init__(self, db_path='bills.db'):
        self.db_path = db_path

    def run(self):
        """运行查询的模板方法。"""
        # 这是一个抽象方法，子类应该实现自己的版本
        raise NotImplementedError("每个查询子类必须实现 run() 方法")

# ==============================================================================
# 1. 针对每种查询的独立类
# ==============================================================================

class YearlySummaryQuery(BaseQuery):
    """处理年度消费总览的查询类。"""
    def __init__(self, year, db_path='bills.db'):
        super().__init__(db_path)
        self.year = year

    def _fetch_data(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ym.year_month, SUM(i.amount)
                FROM YearMonth ym
                JOIN Parent p ON ym.id = p.year_month_id
                JOIN Child c ON p.id = c.parent_id
                JOIN Item i ON c.id = i.child_id
                WHERE ym.year_month LIKE ? || '%'
                GROUP BY ym.year_month
            ''', (self.year,))
            return cursor.fetchall()

    def _format_data(self, data):
        if not data:
            return "无数据"
        year_total = sum(row[1] for row in data)
        month_count = len(data)
        average = year_total / month_count
        lines = [
            "-------------------------------",
            f"{self.year}年消费统计:",
            f"年度总消费: {year_total:.2f}元",
            f"月均消费: {average:.2f}元", "各月消费明细:"
        ]
        for ym_str, total in data:
            lines.append(f"  {self.year}年{int(ym_str[4:])}月: {total:.2f}元")
        lines.append("-------------------------------")
        return "\n".join(lines)

    def run(self):
        data = self._fetch_data()
        output = self._format_data(data)
        print(output)

class MonthlyDetailsQuery(BaseQuery):
    """处理月度消费详情的查询类。"""
    def __init__(self, year, month, db_path='bills.db'):
        super().__init__(db_path)
        self.year = year
        self.month = f"{int(month):02d}"
        self.year_month = f"{year}{self.month}"

    def _fetch_data(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(i.amount) FROM Item i JOIN Child c ON i.child_id = c.id JOIN Parent p ON c.parent_id = p.id JOIN YearMonth ym ON p.year_month_id = ym.id WHERE ym.year_month = ?", (self.year_month,))
            total_result = cursor.fetchone()
            if not total_result or total_result[0] is None:
                return None, None
            
            # 使用内部帮助函数来获取结构化数据
            cursor.execute('''WITH parent_totals AS (...), child_totals AS (...) SELECT ...''', (self.year_month,))
            structured_data = {} # ... 此处省略与之前版本相同的结构化数据构造逻辑
            for row in cursor.fetchall():
                 (p_title, p_total, c_title, c_total, amount, desc) = row
                 if p_title not in structured_data: structured_data[p_title] = {'total': p_total, 'children': {}}
                 if c_title not in structured_data[p_title]['children']: structured_data[p_title]['children'][c_title] = {'total': c_total, 'items': []}
                 structured_data[p_title]['children'][c_title]['items'].append((amount, desc))
            return total_result[0], structured_data

    def _format_data(self, data):
        total_amount, detailed_data = data
        if total_amount is None:
            return "无数据"
        lines = [f"\n{self.year_month} 总消费: {total_amount:.2f}元"]
        for p_title, p_data in detailed_data.items():
            percentage = (p_data['total'] / total_amount * 100) if total_amount else 0
            lines.append(f"\n【{p_title}】{p_data['total']:.2f}元 ({percentage:.1f}%)")
            for c_title, c_data in p_data['children'].items():
                lines.append(f"\n    {c_title}: {c_data['total']:.2f}元")
                for amount, desc in c_data['items']:
                    lines.append(f"        {int(amount) if float(amount).is_integer() else amount} {desc}")
        return "\n".join(lines)

    def run(self):
        data = self._fetch_data()
        output = self._format_data(data)
        print(output)

class MonthlyBillExportQuery(MonthlyDetailsQuery): # 继承月度详情查询类，因为它需要相同的数据
    """处理导出月度账单的查询类。"""
    def _format_data(self, data): # 只重写格式化方法
        _, detailed_data = data
        if not detailed_data:
            return "无数据"
        output = [f"DATE:{self.year_month}"]
        for i, (p_title, p_data) in enumerate(detailed_data.items()):
            if i > 0: output.append('')
            output.append(p_title)
            for c_title, c_data in p_data['children'].items():
                output.append(f"    {c_title}")
                for amount, desc in c_data['items']:
                    output.append(f"        {int(amount) if float(amount).is_integer() else amount} {desc}")
        return "\n".join(output)

class YearlyCategoryQuery(BaseQuery):
    """处理年度分类统计的查询类。"""
    def __init__(self, year, parent_title, db_path='bills.db'):
        super().__init__(db_path)
        self.year = year
        self.parent_title = parent_title

    def _fetch_data(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(i.amount) FROM Item i JOIN Child c ON ... WHERE ym.year_month LIKE ? || '%' AND p.title = ?", (self.year, self.parent_title))
            result = cursor.fetchone()
            return result[0] if result else None

    def _format_data(self, total):
        if total is not None:
            return f"{self.year}年[{self.parent_title}]总消费: {total:.2f}元"
        return "无数据"

    def run(self):
        data = self._fetch_data()
        output = self._format_data(data)
        print(output)


# ==============================================================================
# 2. 公共接口函数
# ==============================================================================

def display_yearly_summary(year):
    """查询并显示年度消费总览。"""
    query = YearlySummaryQuery(year)
    query.run()

def display_monthly_details(year, month):
    """查询并显示月度消费详情。"""
    query = MonthlyDetailsQuery(year, month)
    query.run()

def export_monthly_bill_as_text(year, month):
    """以纯文本格式导出月度账单。"""
    query = MonthlyBillExportQuery(year, month)
    query.run()

def display_yearly_parent_category_summary(year, parent_title):
    """查询并显示指定父分类的年度总消费。"""
    query = YearlyCategoryQuery(year, parent_title)
    query.run()