# text_parser.py
import re
import os

# 从 common.py 导入颜色
from common import RED, RESET

# 正则表达式定义
RE_PARENT = r'^[A-Z]+[\u4e00-\u9fff]+$'
RE_CHILD = r'^[a-z]+(_[a-z]+)+$'
RE_ITEM = r'^(\d+\.?\d*)\s*(.*)$'

class BillParser:
    """
    一个专门用于解析账单文件的类。
    它封装了解析过程中的所有状态和逻辑。
    """
    def __init__(self, file_path):
        """初始化解析器所需的状态。"""
        self.file_path = file_path
        self.records = []
        self.line_num = 0
        
        # 解析过程中的状态变量
        self.parent_order = 0
        self.child_order_map = {}
        self.item_order_map = {}
        self.current_parent_title = None
        self.current_child_title = None
        self.expect_remark_for_year_month = None

    def parse(self):
        """
        执行文件解析的主方法。
        成功则返回 (True, records_list)，失败则返回 (False, None)。
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as infile:
                for self.line_num, line in enumerate(infile, 1):
                    self._process_line(line)
            return True, self.records
        except (ValueError, IOError) as e:
            print(f"{RED}Error parsing file '{os.path.basename(self.file_path)}': {e}{RESET}")
            return False, None

    def _process_line(self, line):
        """根据行内容，分发给相应的处理方法。"""
        stripped_line = line.strip()
        if not stripped_line:
            return

        # 优先处理 REMARK
        if self.expect_remark_for_year_month and stripped_line.startswith('REMARK:'):
            self._handle_remark(stripped_line)
            return
        else:
            # 如果之前期待一个REMARK但没等到，就重置期待状态
            self.expect_remark_for_year_month = None

        if stripped_line.startswith('DATE:'):
            self._handle_date(stripped_line)
        elif re.fullmatch(RE_PARENT, stripped_line):
            self._handle_parent(stripped_line)
        elif self.current_parent_title and re.fullmatch(RE_CHILD, stripped_line):
            self._handle_child(stripped_line)
        elif self.current_parent_title and self.current_child_title:
            self._handle_item(stripped_line)
        elif stripped_line:
            raise ValueError(f"Line {self.line_num}: '{stripped_line}' format is unexpected or out of order.")

    def _handle_date(self, line):
        """处理 DATE 行。"""
        year_month = line[5:].strip()
        if not re.fullmatch(r'^\d{6}$', year_month):
            raise ValueError(f"Invalid DATE format '{year_month}' at line {self.line_num}. Expected YYYYMM.")
        
        self.records.append({'type': 'year_month', 'value': year_month, 'line_num': self.line_num})
        
        # 重置月度状态
        self.parent_order = 0
        self.child_order_map.clear()
        self.item_order_map.clear()
        self.current_parent_title = None
        self.current_child_title = None
        self.expect_remark_for_year_month = year_month

    def _handle_remark(self, line):
        """处理 REMARK 行。"""
        remark_text = line[7:].strip()
        self.records.append({
            'type': 'remark',
            'year_month': self.expect_remark_for_year_month,
            'text': remark_text,
            'line_num': self.line_num
        })
        self.expect_remark_for_year_month = None  # 重置

    def _handle_parent(self, line):
        """处理父分类行。"""
        self.parent_order += 1
        self.current_parent_title = line
        self.child_order_map[self.current_parent_title] = 0
        self.current_child_title = None # 进入新的父分类，清空子分类状态
        
        self.records.append({
            'type': 'parent', 'title': line, 'order_num': self.parent_order, 'line_num': self.line_num
        })

    def _handle_child(self, line):
        """处理子分类行。"""
        current_child_order = self.child_order_map.get(self.current_parent_title, 0) + 1
        self.child_order_map[self.current_parent_title] = current_child_order
        self.current_child_title = line
        self.item_order_map[self.current_child_title] = 0 # 进入新的子分类，清空项目顺序
        
        self.records.append({
            'type': 'child', 'title': line, 'order_num': current_child_order,
            'parent_title': self.current_parent_title, 'line_num': self.line_num
        })

    def _handle_item(self, line):
        """处理消费项目行。"""
        match = re.match(RE_ITEM, line)
        if not match:
            # 如果行不为空且不是项目格式，可以忽略或根据需求报错
            return

        amount = float(match.group(1))
        description = match.group(2).strip()
        current_item_order = self.item_order_map.get(self.current_child_title, 0) + 1
        self.item_order_map[self.current_child_title] = current_item_order
        
        self.records.append({
            'type': 'item', 'amount': amount, 'description': description, 'order_num': current_item_order,
            'child_title': self.current_child_title, 'parent_title': self.current_parent_title,
            'line_num': self.line_num
        })

# ==============================================================================
# 公共接口函数
# ==============================================================================
def parse_bill_file(file_path):
    """
    解析账单文件的高层接口。
    这个函数创建 BillParser 的实例并运行它，保持对外的调用方式不变。
    """
    parser = BillParser(file_path)
    return parser.parse()