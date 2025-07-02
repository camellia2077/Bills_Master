# ANSI escape codes for colored console output
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"

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