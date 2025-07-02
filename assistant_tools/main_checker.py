import os
import time
from BillProcessor import BillProcessor

# ANSI escape codes for colored console output
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# --- Feature Flags ---
ENABLE_SUM_UP_LINES = True
ENABLE_ADD_AUTORENEWAL = True
ENABLE_CLEANUP_EMPTY_ITEMS = True
ENABLE_SORT_CONTENT = True

# --- Configuration File Paths ---
VALIDATOR_CONFIG_PATH = "Validator_Config.json"
MODIFIER_CONFIG_PATH = "Modifier_Config.json" 

# ======================================================================
# Validation Function Area
# ======================================================================
def print_validation_result(file_path, result):
    """Prints the results of a validation check in a formatted way."""
    filename = os.path.basename(file_path)
    print("-" * 40)
    print(f"File: {filename}")
    if not result['errors']:
        print(f"{GREEN}Validation Passed{RESET}")
    else:
        print(f"{RED}Validation Failed, found {len(result['errors'])} errors:{RESET}")
        for lineno, message in result['errors']:
            print(f"  - Line {lineno:<4}: {message}")
    print(f"Processed Lines: {result['processed_lines']}")
    print(f"Execution Time: {result['time']:.6f} seconds")
    print("-" * 40 + "\n")

def handle_validation(processor: BillProcessor):
    """
    Handles the user interaction for validating bill files.

    Args:
        processor (BillProcessor): An instance of the BillProcessor class.
    """
    path = input("Enter the path of the .txt file or directory to [Validate] (Enter 0 to return): ").strip()
    if path == '0': return
    if not os.path.exists(path):
        print(f"{RED}Error: Path '{path}' does not exist.{RESET}")
        return

    files_to_process = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            files_to_process.extend([os.path.join(root, file) for file in sorted(files) if file.lower().endswith('.txt')])
    elif os.path.isfile(path):
        files_to_process.append(path)
    
    if not files_to_process:
        print(f"No .txt files found in {path}.")
        return

    for file_path in files_to_process:
        try:
            # Use the processor to validate the file
            validation_result = processor.validate_bill_file(file_path)
            print_validation_result(file_path, validation_result)
        except Exception as e:
            print(f"{RED}An unexpected error occurred while processing {os.path.basename(file_path)}: {e}{RESET}")

# ======================================================================
# Modification Function Area
# ======================================================================
def handle_modification(processor: BillProcessor):
    """
    Handles the user interaction for modifying bill files.

    Args:
        processor (BillProcessor): An instance of the BillProcessor class.
    """
    path = input("Enter the path of the .txt file or directory to [Modify] (Enter 0 to return): ").strip()
    if path == '0': return

    if not os.path.exists(path):
        print(f"{RED}Error: Path '{path}' does not exist.{RESET}")
        return

    files_to_process = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            files_to_process.extend([os.path.join(root, file) for file in sorted(files) if file.lower().endswith('.txt')])
    elif os.path.isfile(path):
        files_to_process.append(path)

    if not files_to_process:
        print(f"No .txt files found in {path}.")
        return

    total_files, modified_count = len(files_to_process), 0
    start_time = time.perf_counter()

    print(f"\n--- Found {total_files} files, starting process ---")
    print(f"Line Sum-up: {'Enabled' if ENABLE_SUM_UP_LINES else 'Disabled'}")
    print(f"Auto-renewal: {'Enabled' if ENABLE_ADD_AUTORENEWAL else 'Disabled'}")
    print(f"Content Sorting: {'Enabled' if ENABLE_SORT_CONTENT else 'Disabled'}")
    print(f"Cleanup Empty Items: {'Enabled' if ENABLE_CLEANUP_EMPTY_ITEMS else 'Disabled'}")

    for file_path in files_to_process:
        print(f"\n--- Processing file: {os.path.basename(file_path)} ---")
        try:
            # Use the processor to modify the file
            result = processor.modify_bill_file(
                file_path,
                ENABLE_SUM_UP_LINES,
                ENABLE_ADD_AUTORENEWAL,
                ENABLE_CLEANUP_EMPTY_ITEMS,
                ENABLE_SORT_CONTENT
            )

            if result['error']:
                print(f"{RED}Error: {result['error']}{RESET}")
            else:
                for log_entry in result['log']:
                    if any(kw in log_entry for kw in ["Updated", "Added", "Calculated", "Cleaned", "Deleted", "Sorted"]):
                        print(f"{GREEN}  - {log_entry}{RESET}")
                    elif "No changes" in log_entry or "not found" in log_entry:
                        print(f"{YELLOW}  - {log_entry}{RESET}")
                    else:
                        print(f"  - {log_entry}")
                
                if result['modified']:
                    modified_count += 1
        except Exception as e:
            print(f"{RED}An unexpected error occurred while processing {os.path.basename(file_path)}: {e}{RESET}")

    duration = time.perf_counter() - start_time
    print("\n========== Processing Complete ==========")
    print(f"Total files processed: {total_files}")
    print(f"Files successfully modified: {modified_count}")
    print(f"Total time elapsed: {duration:.4f} seconds")

# ======================================================================
# Main Program Loop
# ======================================================================
def main():
    """
    Main function to run the Bill Toolbox application.
    It initializes the BillProcessor and handles the main menu loop.
    """
    try:
        # Initialize the processor at the start
        processor = BillProcessor(VALIDATOR_CONFIG_PATH, MODIFIER_CONFIG_PATH)
    except FileNotFoundError as e:
        print(f"{RED}Critical Error: {e}{RESET}")
        print("Please ensure the configuration files exist and try again. Exiting program.")
        return

    while True:
        print("\n========== Bill Toolbox ==========")
        print("1. Validate Bill File(s) Format")
        print("2. Format and Modify Bill File(s) (Sum/Renew/Cleanup/Sort)")
        print("0. Exit")
        choice = input("Select an option: ").strip()
        
        if choice == '1':
            handle_validation(processor) 
        elif choice == '2':
            handle_modification(processor) 
        elif choice == '0':
            print("Exiting program.")
            break
        else:
            print(f"{RED}Invalid input, please enter a number from the menu.{RESET}")

if __name__ == "__main__":
    main()