import os
from bill_modifier import process_single_file as modify_bill
from bill_validator import validate_file as validate_bill

class BillProcessor:
    """
    A class to encapsulate the functionality of validating and modifying bill files.
    This processor acts as a centralized interface for bill processing operations,
    using external configuration files for validation and modification rules.
    """

    def __init__(self, validator_config_path: str, modifier_config_path: str):
        """
        Initializes the BillProcessor with paths to the necessary configuration files.

        Args:
            validator_config_path (str): The path to the validator's JSON configuration file 
                                         (e.g., 'Validator_Config.json').
            modifier_config_path (str): The path to the modifier's JSON configuration file 
                                        (e.g., 'Modifier_Config.json').
        
        Raises:
            FileNotFoundError: If either of the configuration files cannot be found at the
                               provided paths.
        """
        if not os.path.exists(validator_config_path):
            raise FileNotFoundError(f"Validator config file not found at: {validator_config_path}")
        if not os.path.exists(modifier_config_path):
            raise FileNotFoundError(f"Modifier config file not found at: {modifier_config_path}")
            
        self.validator_config_path = validator_config_path
        self.modifier_config_path = modifier_config_path

    def validate_bill_file(self, bill_file_path: str) -> dict:
        """
        Validates a single bill file against the rules defined in the validator configuration.

        Args:
            bill_file_path (str): The path to the bill file to be validated.

        Returns:
            dict: A dictionary containing the validation results, including any errors found,
                  the number of processed lines, and the time taken.
        
        Raises:
            FileNotFoundError: If the bill file does not exist.
        """
        if not os.path.exists(bill_file_path):
            raise FileNotFoundError(f"The specified bill file was not found: {bill_file_path}")
        
        print(f"Starting validation for: {os.path.basename(bill_file_path)}...")
        result = validate_bill(bill_file_path, self.validator_config_path)
        print("Validation complete.")
        return result

    def modify_bill_file(self, 
                         bill_file_path: str, 
                         enable_summing: bool = True, 
                         enable_autorenewal: bool = True, 
                         enable_cleanup: bool = True, 
                         enable_sorting: bool = True) -> dict:
        """
        Modifies a single bill file based on a set of enabled operations and rules from
        the modifier configuration.

        Args:
            bill_file_path (str): The path to the bill file to be modified.
            enable_summing (bool, optional): Enables summing up of arithmetic expressions 
                                             (e.g., '10+15...'). Defaults to True.
            enable_autorenewal (bool, optional): Enables adding predefined recurring expenses. 
                                                  Defaults to True.
            enable_cleanup (bool, optional): Enables removal of empty parent or sub-categories. 
                                             Defaults to True.
            enable_sorting (bool, optional): Enables sorting of expense items under each 
                                             sub-category by amount. Defaults to True.

        Returns:
            dict: A dictionary containing the modification results, including a log of changes,
                  a modification status flag, and any errors that occurred.
        
        Raises:
            FileNotFoundError: If the bill file does not exist.
        """
        if not os.path.exists(bill_file_path):
            raise FileNotFoundError(f"The specified bill file was not found: {bill_file_path}")
            
        print(f"Starting modification for: {os.path.basename(bill_file_path)}...")
        result = modify_bill(
            file_path=bill_file_path,
            modifier_config_path=self.modifier_config_path,
            enable_summing=enable_summing,
            enable_autorenewal=enable_autorenewal,
            enable_cleanup=enable_cleanup,
            enable_sorting=enable_sorting
        )
        print("Modification complete.")
        return result