# ANSI escape codes for colored console output
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
from typing import Dict

def log_step_start(message: str):
    """Prints a message indicating a major step is beginning."""
    print(f"\n{CYAN}>>> {message}{RESET}")

def log_step_end(message: str, success: bool = True):
    """Prints a message indicating a step has finished, colored by outcome."""
    if success:
        print(f"{GREEN}✔ {message}{RESET}")
    else:
        print(f"{RED}✖ {message}{RESET}")

def log_info(message: str):
    """Prints a general informational message for sub-steps."""
    print(f"  - {message}")

def log_error(message: str):
    """Prints an error message for a sub-step."""
    print(f"  {RED}- {message}{RESET}")

# --- NEW FUNCTION ---
def log_validation_results(result: Dict):
    """
    Prints the detailed errors and warnings from a validation result dictionary.
    """
    if not result:
        return
        
    errors = result.get('errors', [])
    warnings = result.get('warnings', [])

    if not errors and not warnings:
        print(f"{GREEN}  ✔ 文件通过验证，未发现错误或警告。{RESET}")
    
    if errors:
        print(f"{RED}  ✖ 发现 {len(errors)} 个验证错误:{RESET}")
        for lineno, err_msg in errors:
            print(f"{RED}    - L{lineno}: {err_msg}{RESET}")
    
    if warnings:
        print(f"{YELLOW}  ! 发现 {len(warnings)} 个验证警告:{RESET}")
        for lineno, warn_msg in warnings:
            print(f"{YELLOW}    - L{lineno}: {warn_msg}{RESET}")