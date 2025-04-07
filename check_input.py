import os
import re
import time
from typing import Dict, List, Tuple

def validate_file(file_path: str) -> Tuple[bool, List[str], int]:
    """
    验证单个文件的合法性
    
    :param file_path: 文件路径
    :return: (是否合法, 错误信息列表, 处理行数)
    """
    errors = []
    line_count = 0
    current_parent = None
    current_child = None
    expecting_content = False
    has_content = False
    date_found = False
    parents_without_children = set()
    
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    for i, line in enumerate(lines, 1):
        stripped_line = line.strip()
        if not stripped_line:  # 空行跳过
            continue
        
        line_count += 1
        
        # 检查第一行是否是DATE标题
        if line_count == 1:
            if not re.fullmatch(r'DATE\d{6}.*', stripped_line):
                errors.append(f"第{i}行错误: 第一行必须是DATE加6位数字 (如 DATE202409), 但找到 '{stripped_line}'")
            else:
                date_found = True
            continue
        
        # 检查是否是父级标题
        if re.fullmatch(r'[A-Z]+[^\s]*', stripped_line):
            if expecting_content:
                errors.append(f"第{i}行错误: 在期待子标题内容时找到父级标题 '{stripped_line}'")
            
            # 验证父级标题格式
            if not re.fullmatch(r'[A-Z]+\S*', stripped_line):
                errors.append(f"第{i}行错误: 父级标题必须由大写英文和汉字构成, 但找到 '{stripped_line}'")
            
            current_parent = stripped_line
            parents_without_children.add(current_parent)
            current_child = None
            expecting_content = False
            continue
        
        # 检查是否是子标题
        if current_parent and not current_child:
            expected_child = re.sub(r'([A-Z]+).*', lambda m: m.group(1).lower() + '_', current_parent)
            if not stripped_line.startswith(expected_child):
                errors.append(f"第{i}行错误: 子标题应以 '{expected_child}' 开头, 但找到 '{stripped_line}'")
            else:
                current_child = stripped_line
                if current_parent in parents_without_children:
                    parents_without_children.remove(current_parent)
                expecting_content = True
                has_content = False
            continue
        
        # 检查子标题内容
        if expecting_content:
            # 检查内容格式: 数字(可含小数点) + 文本内容，中间不能有空格
            if not re.fullmatch(r'\d+\.?\d*\S*', stripped_line):
                errors.append(f"第{i}行错误: 内容格式应为'数字+文本'(如'362饭'), 不能有空格或特殊字符, 但找到 '{stripped_line}'")
            has_content = True
            expecting_content = False
            continue
    
    # 检查DATE标题是否存在
    if not date_found:
        errors.append("错误: 文件缺少DATE标题")
    
    # 检查是否有父级标题没有子标题
    for parent in parents_without_children:
        if parent.startswith('DATE'):
            continue  # DATE标题可以没有子标题
        errors.append(f"错误: 父级标题 '{parent}' 没有子标题")
    
    # 检查最后一个子标题是否有内容
    if current_child and not has_content:
        errors.append(f"错误: 子标题 '{current_child}' 没有内容")
    
    return len(errors) == 0, errors, line_count

def validate_files(input_path: str):
    """
    验证文件或目录中的所有txt文件
    
    :param input_path: 文件路径或目录路径
    """
    start_time = time.perf_counter()
    
    if os.path.isdir(input_path):
        print(f"正在验证目录: {input_path}")
        txt_files = [f for f in os.listdir(input_path) if f.endswith('.txt')]
        if not txt_files:
            print("目录中没有txt文件")
            return
    else:
        if not input_path.endswith('.txt'):
            print("错误: 输入的文件不是txt文件")
            return
        txt_files = [os.path.basename(input_path)]
        input_path = os.path.dirname(input_path) or '.'
    
    total_files = 0
    total_passed = 0
    total_errors = 0
    total_lines = 0
    
    for filename in txt_files:
        total_files += 1
        file_path = os.path.join(input_path, filename)
        print(f"\n验证文件: {filename}")
        
        file_start_time = time.perf_counter()
        is_valid, errors, line_count = validate_file(file_path)
        file_elapsed = time.perf_counter() - file_start_time
        
        total_lines += line_count
        
        if is_valid:
            print("结果: 通过")
            total_passed += 1
        else:
            print("结果: 失败")
            total_errors += len(errors)
            for error in errors:
                print(f"  {error}")
        
        print(f"处理行数: {line_count}")
        print(f"处理时间: {file_elapsed:.6f}秒")
    
    elapsed = time.perf_counter() - start_time
    
    print(f"总文件数: {total_files}")
    print(f"通过文件数: {total_passed}")
    print(f"失败文件数: {total_files - total_passed}")
    #print(f"总错误数: {total_errors}")
    print(f"总处理行数: {total_lines}")
    print(f"总运行时间: {elapsed:.6f}秒")

if __name__ == "__main__":
    input_path = input("请输入txt文件路径或目录路径: ")
    validate_files(input_path)