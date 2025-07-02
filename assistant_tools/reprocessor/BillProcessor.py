import os
# 在模块名前加上点，表示从当前包（reprocessor）内导入
from .bill_modifier import process_single_file as modify_bill
from .bill_validator import validate_file as validate_bill
from .status_logger import log_step_start, log_step_end
from typing import Tuple, Dict

class BillProcessor:
    """A class to encapsulate the functionality of validating and modifying bill files."""

    def __init__(self, validator_config_path: str, modifier_config_path: str):
        if not os.path.exists(validator_config_path):
            raise FileNotFoundError(f"Validator config file not found at: {validator_config_path}")
        if not os.path.exists(modifier_config_path):
            raise FileNotFoundError(f"Modifier config file not found at: {modifier_config_path}")
        self.validator_config_path = validator_config_path
        self.modifier_config_path = modifier_config_path

    def validate_bill_file(self, bill_file_path: str) -> Tuple[bool, Dict]:
        """Validates a single bill file against the rules defined in the validator configuration."""
        filename = os.path.basename(bill_file_path)
        log_step_start(f"Validating file: {filename}")
        
        if not os.path.exists(bill_file_path):
            raise FileNotFoundError(f"The specified bill file was not found: {bill_file_path}")
            
        is_valid, result = validate_bill(bill_file_path, self.validator_config_path)
        log_step_end("Validation complete", success=is_valid)
        return is_valid, result

    def modify_bill_file(self, bill_file_path: str, enable_summing: bool = True, 
                         enable_autorenewal: bool = True, enable_cleanup: bool = True, 
                         enable_sorting: bool = True) -> bool:
        """Modifies a single bill file. Logs are printed directly."""
        filename = os.path.basename(bill_file_path)
        log_step_start(f"Modifying file: {filename}")

        if not os.path.exists(bill_file_path):
            raise FileNotFoundError(f"The specified bill file was not found: {bill_file_path}")
        
        success = modify_bill(
            file_path=bill_file_path,
            modifier_config_path=self.modifier_config_path,
            enable_summing=enable_summing,
            enable_autorenewal=enable_autorenewal,
            enable_cleanup=enable_cleanup,
            enable_sorting=enable_sorting
        )
        log_step_end("Modification complete", success=success)
        return success

    def validate_and_modify_bill_file(self, bill_file_path: str, 
                                      enable_summing: bool, enable_autorenewal: bool, 
                                      enable_cleanup: bool, enable_sorting: bool) -> Tuple[bool, str, Dict]:
        """Sequentially validates and then modifies a file."""
        # Step 1: Validate
        is_valid, validation_result = self.validate_bill_file(bill_file_path)
        if not is_valid:
            message = "Validation failed. Halting process."
            return False, message, validation_result
        
        # Step 2: Modify
        mod_success = self.modify_bill_file(
            bill_file_path, enable_summing, enable_autorenewal, enable_cleanup, enable_sorting
        )
        if mod_success:
            message = "Validation passed and modification successful."
            return True, message, validation_result
        else:
            message = "Validation passed but modification failed."
            return False, message, validation_result