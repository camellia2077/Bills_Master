import os
import re
import time
from collections import defaultdict
#ANSI转义码_颜色代码
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"      # 重置所有样式
BOLD = "\033[1m"       # 加粗
DIM = "\033[2m"        # 暗淡/变淡
ITALIC = "\033[3m"     # 斜体
UNDERLINE = "\033[4m"  # 下划线
BLINK = "\033[5m"      # 闪烁
def check_parent_title_format(line):
    """
    检查行是否符合父标题的所有规则 (格式 + 必须含汉字).
    返回:
      0: 完全有效
      1: 格式基本正确，但缺少汉字
      2: 格式无效
    """
    if re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
        if re.search(r'[\u4e00-\u9fff]', line):
            return 0  # 完全有效
        else:
            return 1  # 缺少汉字
    else:
        return 2  # 格式无效
def read_and_preprocess(file_path):
    """逐行读取文件并预处理行"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [
            (lineno, line.strip())
            for lineno, line in enumerate(f, 1)
            if line.strip()
        ]

def validate_date_and_remark(lines):
    """验证DATE和REMARK行"""
    errors = []
    if len(lines) < 2:
        errors.append((0, "文件必须包含至少DATE和REMARK两行"))
        return errors
    
    # 验证DATE行
    date_lineno, date_line = lines[0]
    if not re.fullmatch(r'^DATE:\d{6}$', date_line):
        errors.append((date_lineno, "DATE格式错误,必须为DATE:后接6位数字"))
    
    # 验证REMARK行
    remark_lineno, remark_line = lines[1]
    if not re.fullmatch(r'^REMARK:.*$', remark_line):
        errors.append((remark_lineno, "REMARK格式错误,必须为REMARK:开头"))
    
    return errors

def handle_parent_state(line, lineno, state):
    """处理父标题状态"""
    status = check_parent_title_format(line)

    if status == 0: # 完全有效
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        return []
    elif status == 1: # 缺少汉字
        # 如果需要，可以不改变状态，仅报错
        return [(lineno, "父级标题格式正确但缺少汉字")]
    else: # 格式无效
        return [(lineno, "期望父级标题 (格式: 大写字母开头, 必须含汉字, 可有数字), 但找到不匹配的内容")]

def handle_sub_state(line, lineno, state):
    """处理子标题状态"""
    errors = []
    current_parent = state['current_parent']
    
    if not current_parent:
        errors.append((lineno, "未找到父级标题"))
        return errors
    
    parent_lineno, parent_line = current_parent
    if not (match := re.match(r'^([A-Z]+)', parent_line)):
        errors.append((parent_lineno, "父级标题格式错误"))
        return errors
    
    expected_prefix = f"{match.group(1).lower()}_"
    if re.fullmatch(f"^{expected_prefix}[a-z]+$", line):
        new_sub = (lineno, line)
        state['subs'][current_parent].append(new_sub)
        state['current_sub'] = new_sub
        state['expecting'] = 'content'
    elif re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
        errors.append((current_parent[0], "父级标题缺少子标题"))
        state['current_parent'] = (lineno, line)
        state['parents'].append(state['current_parent'])
        state['expecting'] = 'sub'
    else:
        errors.append((lineno, f"子标题应以{expected_prefix}开头且仅含小写字母"))
    
    return errors

def handle_content_state(line, lineno, state):
    """处理内容行状态"""
    errors = []
    current_sub = state['current_sub']
    current_parent = state['current_parent'] # 在函数开始处获取，避免后面重复访问

    # --- 先检查是否是内容行 ---
    is_content = re.fullmatch(r'^\d+(?:\.\d+)?(?:[^\d\s][\d\u4e00-\u9fffa-zA-Z_-]*)+$', line)

    # --- 再检查是否是新父标题 ---
    parent_check_status = check_parent_title_format(line)

    # --- 再检查是否是新子标题 ---
    is_new_sub = False
    expected_sub_prefix = ""
    if current_parent: # 必须有父标题才能判断子标题
        parent_initials_match = re.match(r'^([A-Z]+)', current_parent[1])
        if parent_initials_match:
             expected_sub_prefix = f"{parent_initials_match.group(1).lower()}_"
             is_new_sub = re.fullmatch(f"^{expected_sub_prefix}[a-z]+$", line)


    # --- 根据检查结果处理状态和错误 ---
    if is_content:
        if not current_sub:
             errors.append((lineno, "找到内容行，但当前没有活动的子标题"))
        else:
             state['content_counts'][current_sub] += 1
        # 成功找到内容行，状态不变，准备接收下一行 (可能是内容/新子/新父)
    elif parent_check_status == 0: # 是有效的新父标题
        # 检查上一个子标题是否缺少内容
        if current_sub and state['content_counts'][current_sub] == 0:
            errors.append((current_sub[0], "子标题缺少内容行"))
        # 设置新的父标题状态
        new_parent = (lineno, line)
        state['parents'].append(new_parent)
        state['current_parent'] = new_parent
        state['expecting'] = 'sub'
        state['current_sub'] = None # 重置当前子标题
    elif is_new_sub: # 是有效的新子标题
         # 检查上一个子标题是否缺少内容
         if current_sub and state['content_counts'][current_sub] == 0:
             errors.append((current_sub[0], "子标题缺少内容行"))
         # 设置新的子标题状态
         new_sub = (lineno, line)
         if not current_parent:
              # 理论上不应该发生，因为 is_new_sub 依赖 current_parent
              errors.append((lineno, "找到新子标题，但父标题信息丢失"))
         else:
              state['subs'][current_parent].append(new_sub)
              state['current_sub'] = new_sub
              state['expecting'] = 'content'
    elif parent_check_status == 1: # 格式像父标题但缺汉字
         errors.append((lineno, "父级标题格式正确但缺少汉字"))
         # 不改变状态，仅报错
    else: # 其他所有情况
         # 检查上一个子标题是否缺少内容（如果这是文件的最后有效行）
         # 这个检查可能更适合放在 post_validation_checks
         errors.append((lineno, "期望内容行、新子标题或新父标题, 但找到其他内容"))

    return errors

def process_lines(lines, state):
    """处理所有数据行"""
    for i in range(2, len(lines)):
        lineno, line = lines[i]
        handler = {
            'parent': handle_parent_state,
            'sub': handle_sub_state,
            'content': handle_content_state
        }[state['expecting']]
        
        if errors := handler(line, lineno, state):
            state['errors'].extend(errors)

def post_validation_checks(state):
    """后处理验证检查"""
    errors = []
    # 检查未闭合的父标题
    if state['expecting'] == 'sub' and state['current_parent']:
        errors.append((state['current_parent'][0], "父级标题缺少子标题"))
    # 检查未闭合的子标题
    elif state['expecting'] == 'content' and state['current_sub']:
        if state['content_counts'][state['current_sub']] == 0:
            errors.append((state['current_sub'][0], "子标题缺少内容行"))
    # 检查所有父标题是否有子标题
    for parent in state['parents']:
        if not state['subs'].get(parent):
            errors.append((parent[0], "父级标题缺少子标题"))
    return errors

def validate_file(file_path):
    """主验证函数"""
    start_time = time.perf_counter()
    
    # 初始化状态
    state = {
        'expecting': 'parent',
        'current_parent': None,
        'current_sub': None,
        'parents': [],
        'subs': defaultdict(list),
        'content_counts': defaultdict(int),
        'errors': []
    }
    
    # 读取并预处理文件
    lines = read_and_preprocess(file_path)
    processed_lines = len(lines)
    
    # 验证前两行
    state['errors'].extend(validate_date_and_remark(lines))
    
    # 处理数据行
    if len(lines) >= 2:
        process_lines(lines, state)
    
    # 后处理检查
    state['errors'].extend(post_validation_checks(state))
    
    return {
        'processed_lines': processed_lines,
        'errors': sorted(state['errors'], key=lambda x: x[0]),
        'time': time.perf_counter() - start_time
    }

def print_result(file_path, result):
    """打印验证结果"""
    filename = os.path.basename(file_path)
    if not result['errors']:
        print(f"{GREEN}{filename} 校验通过{RESET}")
    else:
        print(f"{RED}校验失败,错误详情:{RESET}")
        for err in result['errors']:
            print(f"第 {err[0]} 行: {err[1]}")
    #print(f"\n目录: {os.path.dirname(file_path)}")
    print(f"运行时间: {result['time']:.6f}秒")
    print(f"文件名: {filename} 处理行数: {result['processed_lines']}")
    print("\n")
    
    
def process_path(path):
    """处理路径（文件或目录）"""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.txt'):
                    process_single_file(os.path.join(root, file))
    elif os.path.isfile(path):
        process_single_file(path)
    else:
        print(f"{RED}无效路径{RESET}")

def process_single_file(file_path):
    """处理单个文件"""
    try:
        print_result(file_path, validate_file(file_path))
    except Exception as e:
        print(f"\n目录: {os.path.dirname(file_path)}")
        print(f"文件名: {os.path.basename(file_path)} 处理失败,原因: {str(e)}")
        

def main():
    """主函数"""
    while True:
        path = input("请输入文件或目录路径:").strip()
        process_path(path)

if __name__ == "__main__":
    main()
