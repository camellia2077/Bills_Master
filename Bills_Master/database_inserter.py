import sqlite3
from contextlib import contextmanager

# Output font colors (if needed for messages from this module)
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

# --- SQL Definitions ---
YEAR_MONTH_INSERT = '''
    INSERT INTO YearMonth (year_month)
    VALUES (?)
    ON CONFLICT(year_month) DO NOTHING
    '''
YEAR_MONTH_SELECT = 'SELECT id FROM YearMonth WHERE year_month = ?'
YEAR_MONTH_UPDATE_REMARK = 'UPDATE YearMonth SET remark = ? WHERE year_month = ?'

PARENT_UPSERT = '''
    INSERT INTO Parent (year_month_id, title, order_num)
    VALUES (?, ?, ?)
    ON CONFLICT(year_month_id, title)
    DO UPDATE SET order_num = excluded.order_num'''
PARENT_SELECT = 'SELECT id FROM Parent WHERE year_month_id = ? AND title = ?'

CHILD_UPSERT = '''
    INSERT INTO Child (parent_id, title, order_num)
    VALUES (?, ?, ?)
    ON CONFLICT(parent_id, title)
    DO UPDATE SET order_num = excluded.order_num'''
CHILD_SELECT = 'SELECT id FROM Child WHERE parent_id = ? AND title = ?'

ITEM_UPSERT = '''
    INSERT INTO Item (child_id, amount, description, order_num)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(child_id, amount, description)
    DO UPDATE SET order_num = excluded.order_num'''
# --- End SQL Definitions ---

@contextmanager
def db_connection(db_name='bills.db'): # Allow db_name to be specified
    conn = sqlite3.connect(db_name)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def create_database(db_name='bills.db'):
    try:
        with db_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS YearMonth (
                    id INTEGER PRIMARY KEY,
                    year_month TEXT UNIQUE NOT NULL,
                    remark TEXT
                )''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Parent (
                    id INTEGER PRIMARY KEY,
                    year_month_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    order_num INTEGER NOT NULL,
                    UNIQUE(year_month_id, title)
                )''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Child (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    order_num INTEGER NOT NULL,
                    UNIQUE(parent_id, title)
                )''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Item (
                    id INTEGER PRIMARY KEY,
                    child_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL,
                    order_num INTEGER NOT NULL,
                    UNIQUE(child_id, amount, description)
                )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_parent_ym ON Parent(year_month_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_child_parent ON Child(parent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_item_child ON Item(child_id)')
    except sqlite3.Error as e:
        # The error is re-raised for the caller to handle.
        raise

def insert_data_stream(conn, data_stream):
    """
    Processes a stream of structured data from the parser and inserts it into the database.
    """
    cursor = conn.cursor()
    current_year_month_id = None
    current_year_month_str = None # Needed for remarks
    current_parent_id = None
    current_child_id = None
    items_batch = []
    # Max items to batch before executing, to avoid holding too many in memory
    # but still get some benefit from executemany
    ITEM_BATCH_SIZE = 100

    for record in data_stream:
        record_type = record['type']
        line_num = record.get('line_num', 'N/A') # Get line number for error reporting

        try:
            if record_type == 'year_month':
                if items_batch: # Process any pending items from previous date block
                    cursor.executemany(ITEM_UPSERT, items_batch)
                    items_batch = []
                current_year_month_str = record['value']
                cursor.execute(YEAR_MONTH_INSERT, (current_year_month_str,))
                cursor.execute(YEAR_MONTH_SELECT, (current_year_month_str,))
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Failed to insert/find YearMonth ID for {current_year_month_str}")
                current_year_month_id = result[0]
                current_parent_id = None # Reset context
                current_child_id = None  # Reset context

            elif record_type == 'remark':
                if not record['year_month']: # Should have year_month context from parser
                     raise ValueError(f"Remark '{record['text']}' found without associated DATE (line {line_num}).")
                cursor.execute(YEAR_MONTH_UPDATE_REMARK, (record['text'], record['year_month']))

            elif record_type == 'parent':
                if not current_year_month_id:
                    raise ValueError(f"Parent '{record['title']}' found without preceding DATE (line {line_num}).")
                if items_batch: # Process pending items before switching parent
                    cursor.executemany(ITEM_UPSERT, items_batch)
                    items_batch = []
                cursor.execute(PARENT_UPSERT, (current_year_month_id, record['title'], record['order_num']))
                cursor.execute(PARENT_SELECT, (current_year_month_id, record['title']))
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Failed to get Parent ID for '{record['title']}' under YM_ID {current_year_month_id}")
                current_parent_id = result[0]
                current_child_id = None # Reset child context

            elif record_type == 'child':
                if not current_parent_id:
                    raise ValueError(f"Child '{record['title']}' found without preceding PARENT (line {line_num}).")
                if items_batch: # Process pending items before switching child
                    cursor.executemany(ITEM_UPSERT, items_batch)
                    items_batch = []
                cursor.execute(CHILD_UPSERT, (current_parent_id, record['title'], record['order_num']))
                cursor.execute(CHILD_SELECT, (current_parent_id, record['title']))
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Failed to get Child ID for '{record['title']}' under Parent_ID {current_parent_id}")
                current_child_id = result[0]

            elif record_type == 'item':
                if not current_child_id:
                    raise ValueError(f"Item '{record['description']}' found without preceding CHILD (line {line_num}).")
                items_batch.append((
                    current_child_id,
                    record['amount'],
                    record['description'],
                    record['order_num']
                ))
                if len(items_batch) >= ITEM_BATCH_SIZE:
                    cursor.executemany(ITEM_UPSERT, items_batch)
                    items_batch = []
        except Exception as e:
            # Augment error with line number if available
            raise type(e)(f"Error processing record (approx. line {line_num}): {record}. Original error: {e}")

    # After the loop, process any remaining items in the batch
    if items_batch:
        cursor.executemany(ITEM_UPSERT, items_batch)