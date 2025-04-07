import os
import re
import time
from collections import defaultdict

def validate_file(file_path):
    start_time = time.perf_counter()
    errors = []
    parents = []
    subs = defaultdict(list)
    content_counts = defaultdict(int)
    current_parent = None
    current_sub = None
    expecting = 'parent'

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = []
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped:
                lines.append((lineno, stripped))
    
    processed_lines = len(lines)
    
    # 检查DATE和REMARK行（保持不变）
    if len(lines) < 2:
        errors.append((0, "文件必须包含至少DATE和REMARK两行"))
    else:
        date_lineno, date_line = lines[0]
        if not re.fullmatch(r'^DATE:\d{6}$', date_line):
            errors.append((date_lineno, "DATE格式错误，必须为DATE:后接6位数字"))
        remark_lineno, remark_line = lines[1]
        if not re.fullmatch(r'^REMARK:.*$', remark_line):
            errors.append((remark_lineno, "REMARK格式错误，必须为REMARK:开头"))

    # 处理后续行
    for i in range(2, len(lines)):
        lineno, line = lines[i]
        if expecting == 'parent':
            if re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
                current_parent = (lineno, line)
                parents.append(current_parent)
                expecting = 'sub'
            else:
                errors.append((lineno, "期望父级标题，但找到其他内容"))
        elif expecting == 'sub':
            if current_parent is None:
                errors.append((lineno, "未找到父级标题"))
                continue
            parent_lineno, parent_line = current_parent
            match = re.match(r'^([A-Z]+)', parent_line)
            if not match:
                errors.append((parent_lineno, "父级标题格式错误"))
                continue
            parent_english = match.group(1).lower()
            sub_pattern = re.compile(f'^{parent_english}_[a-z]+$')
            if sub_pattern.fullmatch(line):
                current_sub = (lineno, line)
                subs[current_parent].append(current_sub)
                expecting = 'content'
            else:
                # 检查是否为新的副标题
                if re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
                    errors.append((current_parent[0], "父级标题缺少子标题"))
                    current_parent = (lineno, line)
                    parents.append(current_parent)
                    expecting = 'sub'
                else:
                    errors.append((lineno, f"子标题应以{parent_english}_开头且仅含小写字母"))
        elif expecting == 'content':
            if re.fullmatch(r'^\d+(?:\.\d+)?(?:[^\d\s][\d\u4e00-\u9fffa-zA-Z_-]*)+$', line):
                content_counts[current_sub] += 1
            else:
                # 检查是否为新的副标题
                if re.fullmatch(r'^[A-Z]+[\d\u4e00-\u9fff]*$', line):
                    if current_sub and content_counts.get(current_sub, 0) == 0:
                        errors.append((current_sub[0], "子标题缺少内容行"))
                    current_parent = (lineno, line)
                    parents.append(current_parent)
                    expecting = 'sub'
                else:
                    # 检查是否为新的子标题
                    match = re.match(r'^([A-Z]+)', current_parent[1])
                    if match:
                        parent_english = match.group(1).lower()
                        sub_pattern = re.compile(f'^{parent_english}_[a-z]+$')
                        if sub_pattern.fullmatch(line):
                            if current_sub and content_counts.get(current_sub, 0) == 0:
                                errors.append((current_sub[0], "子标题缺少内容行"))
                            current_sub = (lineno, line)
                            subs[current_parent].append(current_sub)
                            expecting = 'content'
                        else:
                            errors.append((lineno, "内容格式错误或未预期的标题"))
                    else:
                        errors.append((lineno, "内容格式错误或未预期的标题"))

    # 后处理检查
    if expecting == 'sub' and current_parent:
        errors.append((current_parent[0], "父级标题缺少子标题"))
    elif expecting == 'content' and current_sub:
        if content_counts.get(current_sub, 0) == 0:
            errors.append((current_sub[0], "子标题缺少内容行"))
    for parent in parents:
        if not subs.get(parent, []):
            errors.append((parent[0], "父级标题缺少子标题"))

    elapsed = time.perf_counter() - start_time
    return {
        'processed_lines': processed_lines,
        'errors': sorted(errors, key=lambda x: x[0]),
        'time': elapsed
    }


def main():
    while(True):
        path = input("请输入文件或目录路径：").strip()
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.txt'):
                        file_path = os.path.join(root, file)
                        try:
                            result = validate_file(file_path)
                            # 新增目录和文件名输出
                            print(f"\n目录: {os.path.dirname(file_path)}")
                            print(f"文件名: {os.path.basename(file_path)}")
                            print(f"处理行数: {result['processed_lines']}")
                            print(f"运行时间: {result['time']:.6f}秒")
                            if not result['errors']:
                                print("校验通过")
                            else:
                                print("校验失败，错误详情:")
                                for err in result['errors']:
                                    print(f"第 {err[0]} 行: {err[1]}")
                        except Exception as e:
                            # 异常信息也拆分显示
                            print(f"\n目录: {os.path.dirname(file_path)}")
                            print(f"文件名: {os.path.basename(file_path)} 处理失败，原因: {str(e)}")
        elif os.path.isfile(path):
            try:
                result = validate_file(path)
                # 单个文件也拆分显示
                print(f"\n目录: {os.path.dirname(path)}")
                print(f"文件名: {os.path.basename(path)}")
                print(f"处理行数: {result['processed_lines']}")
                print(f"运行时间: {result['time']:.6f}秒")
                if not result['errors']:
                    print("校验通过")
                else:
                    print("校验失败，错误详情:")
                    for err in result['errors']:
                        print(f"第 {err[0]} 行: {err[1]}")
            except Exception as e:
                print(f"\n目录: {os.path.dirname(path)}")
                print(f"文件名: {os.path.basename(path)} 处理失败，原因: {str(e)}")
        else:
            print("无效路径")
if __name__ == "__main__":
    main()
