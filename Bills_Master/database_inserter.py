import sqlite3
from contextlib import contextmanager
from typing import Iterator, Dict, Any, Optional

# Output font colors
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"


class DatabaseManager:
    """
    Manages all database interactions including connection, schema creation,
    and data manipulation.
    """

    # --- SQL Definitions ---
    SQL_DEFINITIONS = {
        'create_year_month': '''
            CREATE TABLE IF NOT EXISTS YearMonth (
                id INTEGER PRIMARY KEY,
                year_month TEXT UNIQUE NOT NULL,
                remark TEXT
            )''',
        'create_parent': '''
            CREATE TABLE IF NOT EXISTS Parent (
                id INTEGER PRIMARY KEY,
                year_month_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(year_month_id, title)
            )''',
        'create_child': '''
            CREATE TABLE IF NOT EXISTS Child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(parent_id, title)
            )''',
        'create_item': '''
            CREATE TABLE IF NOT EXISTS Item (
                id INTEGER PRIMARY KEY,
                child_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                UNIQUE(child_id, amount, description)
            )''',
        'create_indices': [
            'CREATE INDEX IF NOT EXISTS idx_parent_ym ON Parent(year_month_id)',
            'CREATE INDEX IF NOT EXISTS idx_child_parent ON Child(parent_id)',
            'CREATE INDEX IF NOT EXISTS idx_item_child ON Item(child_id)'
        ],
        'year_month_insert': 'INSERT INTO YearMonth (year_month) VALUES (?) ON CONFLICT(year_month) DO NOTHING',
        'year_month_select': 'SELECT id FROM YearMonth WHERE year_month = ?',
        'year_month_update_remark': 'UPDATE YearMonth SET remark = ? WHERE year_month = ?',
        'parent_upsert': 'INSERT INTO Parent (year_month_id, title, order_num) VALUES (?, ?, ?) ON CONFLICT(year_month_id, title) DO UPDATE SET order_num = excluded.order_num',
        'parent_select': 'SELECT id FROM Parent WHERE year_month_id = ? AND title = ?',
        'child_upsert': 'INSERT INTO Child (parent_id, title, order_num) VALUES (?, ?, ?) ON CONFLICT(parent_id, title) DO UPDATE SET order_num = excluded.order_num',
        'child_select': 'SELECT id FROM Child WHERE parent_id = ? AND title = ?',
        'item_upsert': 'INSERT INTO Item (child_id, amount, description, order_num) VALUES (?, ?, ?, ?) ON CONFLICT(child_id, amount, description) DO UPDATE SET order_num = excluded.order_num'
    }
    # --- End SQL Definitions ---

    def __init__(self, db_name: str = 'bills.db'):
        self.db_name = db_name
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None

    def __enter__(self):
        """Opens the database connection and prepares a cursor."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
            return self
        except sqlite3.Error as e:
            print(f"{RED}Failed to connect to database {self.db_name}: {e}{RESET}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Commits or rolls back the transaction and closes the connection."""
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()

    def _execute_script(self, script: str):
        if self.cursor:
            self.cursor.executescript(script)
            
    def _execute(self, sql_key: str, params: tuple = ()):
        if self.cursor:
            sql = self.SQL_DEFINITIONS[sql_key]
            self.cursor.execute(sql, params)
            return self.cursor
        return None

    def _executemany(self, sql_key: str, params_list: list):
        if self.cursor:
            sql = self.SQL_DEFINITIONS[sql_key]
            self.cursor.executemany(sql, params_list)


    def create_schema(self) -> bool:
        """Creates database schema. Returns True on success, False on failure."""
        try:
            for key in ['create_year_month', 'create_parent', 'create_child', 'create_item']:
                self._execute(key)
            for index_query in self.SQL_DEFINITIONS['create_indices']:
                 if self.cursor:
                    self.cursor.execute(index_query)
            print(f"{GREEN}Database schema created/verified successfully.{RESET}")
            return True
        except sqlite3.Error as e:
            print(f"{RED}Error during database schema creation: {e}{RESET}")
            return False

    def upsert_year_month(self, year_month: str) -> Optional[int]:
        self._execute('year_month_insert', (year_month,))
        cursor = self._execute('year_month_select', (year_month,))
        result = cursor.fetchone() if cursor else None
        return result[0] if result else None

    def update_year_month_remark(self, remark: str, year_month: str):
        self._execute('year_month_update_remark', (remark, year_month))

    def upsert_parent(self, year_month_id: int, title: str, order_num: int) -> Optional[int]:
        self._execute('parent_upsert', (year_month_id, title, order_num))
        cursor = self._execute('parent_select', (year_month_id, title))
        result = cursor.fetchone() if cursor else None
        return result[0] if result else None
        
    def upsert_child(self, parent_id: int, title: str, order_num: int) -> Optional[int]:
        self._execute('child_upsert', (parent_id, title, order_num))
        cursor = self._execute('child_select', (parent_id, title))
        result = cursor.fetchone() if cursor else None
        return result[0] if result else None

    def bulk_upsert_items(self, items: list):
        if items:
            self._executemany('item_upsert', items)


class DataProcessor:
    """
    Processes a stream of structured data and uses a DatabaseManager
    to insert it into the database.
    """
    ITEM_BATCH_SIZE = 100

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.current_year_month_id: Optional[int] = None
        self.current_parent_id: Optional[int] = None
        self.current_child_id: Optional[int] = None
        self.items_batch: list = []

    def process_stream(self, data_stream: Iterator[Dict[str, Any]]) -> bool:
        """
        Processes the data stream record by record.
        Returns True on success, False on failure.
        """
        try:
            for record in data_stream:
                self._process_record(record)
            
            self._flush_items_batch() # Final flush for any remaining items
            return True
        except ValueError as e:
            print(f"{RED}Data processing failed. Error: {e}{RESET}")
            return False
        except Exception as e:
            # Catch any other unexpected errors during processing
            print(f"{RED}An unexpected error occurred during data processing: {e}{RESET}")
            return False
            
    def _process_record(self, record: Dict[str, Any]):
        """Routes a single record to the appropriate handler."""
        record_type = record['type']
        line_num = record.get('line_num', 'N/A')

        try:
            handler = getattr(self, f"_handle_{record_type}")
            handler(record)
        except (AttributeError, TypeError):
             raise ValueError(f"Unknown or malformed record type '{record_type}' at line {line_num}.")
        except ValueError as e:
            # Re-raise ValueErrors with more context
            raise ValueError(f"Error processing record (approx. line {line_num}): {record}. Details: {e}")


    def _flush_items_batch(self):
        """Writes the current batch of items to the database."""
        if self.items_batch:
            self.db.bulk_upsert_items(self.items_batch)
            self.items_batch = []
            
    def _handle_year_month(self, record: Dict[str, Any]):
        self._flush_items_batch()
        self.current_year_month_id = self.db.upsert_year_month(record['value'])
        if not self.current_year_month_id:
            raise ValueError(f"Failed to insert/find YearMonth ID for {record['value']}")
        # Reset downstream IDs
        self.current_parent_id = None
        self.current_child_id = None

    def _handle_remark(self, record: Dict[str, Any]):
        if not record.get('year_month'):
            raise ValueError(f"Remark '{record['text']}' found without an associated DATE.")
        self.db.update_year_month_remark(record['text'], record['year_month'])
        
    def _handle_parent(self, record: Dict[str, Any]):
        if not self.current_year_month_id:
            raise ValueError(f"Parent '{record['title']}' found without a preceding DATE.")
        self._flush_items_batch()
        self.current_parent_id = self.db.upsert_parent(
            self.current_year_month_id, record['title'], record['order_num']
        )
        if not self.current_parent_id:
            raise ValueError(f"Failed to get Parent ID for '{record['title']}'")
        # Reset downstream ID
        self.current_child_id = None
        
    def _handle_child(self, record: Dict[str, Any]):
        if not self.current_parent_id:
            raise ValueError(f"Child '{record['title']}' found without a preceding PARENT.")
        self._flush_items_batch()
        self.current_child_id = self.db.upsert_child(
            self.current_parent_id, record['title'], record['order_num']
        )
        if not self.current_child_id:
            raise ValueError(f"Failed to get Child ID for '{record['title']}'")

    def _handle_item(self, record: Dict[str, Any]):
        if not self.current_child_id:
            raise ValueError(f"Item '{record['description']}' found without a preceding CHILD.")
        
        self.items_batch.append((
            self.current_child_id,
            record['amount'],
            record['description'],
            record['order_num']
        ))
        
        if len(self.items_batch) >= self.ITEM_BATCH_SIZE:
            self._flush_items_batch()

# --- Public API Function ---

def create_database(db_name: str = 'bills.db') -> bool:
    """
    Creates and initializes the database schema.

    Args:
        db_name: The name of the database file.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with DatabaseManager(db_name) as db:
            return db.create_schema()
    except Exception as e:
        # The DatabaseManager will print its own connection error.
        # This catches other potential issues.
        print(f"{RED}An unexpected error occurred during DB creation: {e}{RESET}")
        return False


def insert_data(data_stream: Iterator[Dict[str, Any]], db_name: str = 'bills.db') -> bool:
    """
    High-level function to process a stream of data and insert it into the database.
    This function handles database connection, processing, and transactions.

    Args:
        data_stream: An iterator yielding structured dictionaries.
        db_name: The name of the database file to use.

    Returns:
        True on success, False on failure.
    """
    print("Starting database insertion process...")
    try:
        with DatabaseManager(db_name) as db_manager:
            processor = DataProcessor(db_manager)
            success = processor.process_stream(data_stream)
            if success:
                print(f"{GREEN}Data insertion process completed successfully.{RESET}")
            else:
                # Error message will be printed by the processor
                print(f"{RED}Data insertion process failed. Rolling back changes.{RESET}")
            return success
    except sqlite3.Error as e:
        print(f"{RED}A database error occurred: {e}. The transaction has been rolled back.{RESET}")
        return False
    except Exception as e:
        print(f"{RED}An unexpected error occurred: {e}. The transaction has been rolled back.{RESET}")
        return False