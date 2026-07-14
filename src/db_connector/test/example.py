import psycopg2
from psycopg2 import sql, Error
import psycopg2.extras

# Connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'database': 'your_database',
    'user': 'your_username',
    'password': 'your_password',
    'port': 5432  # default PostgreSQL port
}

def get_connection():
    """Establish connection to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None


class PostgreSQLManager:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = psycopg2.connect(**self.config)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
            print("Connected to PostgreSQL database successfully")
            return True
        except Error as e:
            print(f"Error connecting to database: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            print("Database connection closed")
    
    def create_table(self, table_name, columns):
        """
        Create a table with specified columns
        columns: dict {'column_name': 'data_type'}
        """
        try:
            columns_def = ', '.join([f"{col} {dtype}" for col, dtype in columns.items()])
            create_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_def})"
            self.cursor.execute(create_query)
            self.connection.commit()
            print(f"Table '{table_name}' created successfully")
            return True
        except Error as e:
            print(f"Error creating table: {e}")
            self.connection.rollback()
            return False
    
    def insert_record(self, table_name, data):
        """
        Insert a single record
        data: dict {'column_name': value}
        """
        try:
            columns = data.keys()
            values = data.values()
            
            insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table_name),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join([sql.Placeholder()] * len(values))
            )
            
            self.cursor.execute(insert_query, list(values))
            self.connection.commit()
            print("Record inserted successfully")
            return True
        except Error as e:
            print(f"Error inserting record: {e}")
            self.connection.rollback()
            return False
    
    def insert_multiple_records(self, table_name, records):
        """
        Insert multiple records
        records: list of dicts
        """
        try:
            if not records:
                return True
            
            columns = records[0].keys()
            values_list = [list(record.values()) for record in records]
            
            insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table_name),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join([sql.Placeholder()] * len(columns))
            )
            
            # Execute for each record using executemany
            self.cursor.executemany(insert_query, values_list)
            self.connection.commit()
            print(f"{len(records)} records inserted successfully")
            return True
        except Error as e:
            print(f"Error inserting multiple records: {e}")
            self.connection.rollback()
            return False
    
    def select_records(self, table_name, conditions=None, columns='*', order_by=None, limit=None):
        """
        Select records with optional conditions
        conditions: dict {'column': value} or string WHERE clause
        """
        try:
            if isinstance(columns, list):
                columns_str = ', '.join(columns)
            else:
                columns_str = columns
            
            query = f"SELECT {columns_str} FROM {table_name}"
            
            params = []
            if conditions:
                if isinstance(conditions, dict):
                    where_clause = ' AND '.join([f"{col} = %s" for col in conditions.keys()])
                    params = list(conditions.values())
                    query += f" WHERE {where_clause}"
                else:
                    query += f" WHERE {conditions}"
            
            if order_by:
                query += f" ORDER BY {order_by}"
            
            if limit:
                query += f" LIMIT {limit}"
            
            self.cursor.execute(query, params)
            results = self.cursor.fetchall()
            
            # Convert to list of dicts
            records = [dict(row) for row in results]
            print(f"Retrieved {len(records)} records")
            return records
        except Error as e:
            print(f"Error selecting records: {e}")
            return []
    
    def update_records(self, table_name, updates, conditions):
        """
        Update records
        updates: dict {'column': new_value}
        conditions: dict {'column': value} or string WHERE clause
        """
        try:
            set_clause = ', '.join([f"{col} = %s" for col in updates.keys()])
            values = list(updates.values())
            
            if isinstance(conditions, dict):
                where_clause = ' AND '.join([f"{col} = %s" for col in conditions.keys()])
                values.extend(list(conditions.values()))
            else:
                where_clause = conditions
            
            update_query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
            
            self.cursor.execute(update_query, values)
            self.connection.commit()
            row_count = self.cursor.rowcount
            print(f"{row_count} record(s) updated successfully")
            return row_count
        except Error as e:
            print(f"Error updating records: {e}")
            self.connection.rollback()
            return -1
    
    def delete_records(self, table_name, conditions=None):
        """
        Delete records
        conditions: dict {'column': value} or string WHERE clause
        If no conditions provided, all records will be deleted
        """
        try:
            query = f"DELETE FROM {table_name}"
            
            params = []
            if conditions:
                if isinstance(conditions, dict):
                    where_clause = ' AND '.join([f"{col} = %s" for col in conditions.keys()])
                    params = list(conditions.values())
                    query += f" WHERE {where_clause}"
                else:
                    query += f" WHERE {conditions}"
            
            self.cursor.execute(query, params)
            self.connection.commit()
            row_count = self.cursor.rowcount
            print(f"{row_count} record(s) deleted successfully")
            return row_count
        except Error as e:
            print(f"Error deleting records: {e}")
            self.connection.rollback()
            return -1
    
    def execute_custom_query(self, query, params=None):
        """Execute custom SQL query"""
        try:
            self.cursor.execute(query, params)
            
            if query.strip().upper().startswith('SELECT'):
                results = self.cursor.fetchall()
                records = [dict(row) for row in results]
                print(f"Query executed, returned {len(records)} records")
                return records
            else:
                self.connection.commit()
                row_count = self.cursor.rowcount
                print(f"Query executed successfully, {row_count} rows affected")
                return row_count
        except Error as e:
            print(f"Error executing custom query: {e}")
            self.connection.rollback()
            return None
    
    def transaction_example(self, operations):
        """Example of using transactions"""
        try:
            # Start transaction
            self.connection.autocommit = False
            
            for operation in operations:
                self.cursor.execute(operation['query'], operation.get('params', []))
            
            # Commit transaction
            self.connection.commit()
            print("Transaction committed successfully")
            return True
        except Error as e:
            # Rollback on error
            self.connection.rollback()
            print(f"Transaction rolled back due to error: {e}")
            return False
        finally:
            self.connection.autocommit = True

# Example usage
def main():
    # Initialize database manager
    db_manager = PostgreSQLManager(DB_CONFIG)
    
    # Connect to database
    if not db_manager.connect():
        return
    
    try:
        # 1. CREATE TABLE
        columns = {
            'id': 'SERIAL PRIMARY KEY',
            'name': 'VARCHAR(100) NOT NULL',
            'email': 'VARCHAR(100) UNIQUE',
            'age': 'INTEGER',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        db_manager.create_table('users', columns)
        
        # 2. INSERT SINGLE RECORD
        user_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'age': 30
        }
        db_manager.insert_record('users', user_data)
        
        # 3. INSERT MULTIPLE RECORDS
        users_data = [
            {'name': 'Jane Smith', 'email': 'jane@example.com', 'age': 25},
            {'name': 'Bob Johnson', 'email': 'bob@example.com', 'age': 35},
            {'name': 'Alice Brown', 'email': 'alice@example.com', 'age': 28}
        ]
        db_manager.insert_multiple_records('users', users_data)
        
        # 4. SELECT RECORDS
        # Select all
        all_users = db_manager.select_records('users')
        print("All users:", all_users)
        
        # Select with conditions
        young_users = db_manager.select_records(
            'users', 
            conditions={'age': 30}, 
            columns=['name', 'email']
        )
        print("Young users:", young_users)
        
        # 5. UPDATE RECORDS
        db_manager.update_records(
            'users',
            updates={'age': 31},
            conditions={'name': 'John Doe'}
        )
        
        # 6. DELETE RECORDS
        db_manager.delete_records('users', conditions={'id': 4})
        
        # 7. EXECUTE CUSTOM QUERY
        result = db_manager.execute_custom_query(
            "SELECT * FROM users WHERE age > %s ORDER BY age DESC",
            [25]
        )
        print("Custom query result:", result)
        
        # 8. TRANSACTION EXAMPLE
        operations = [
            {'query': "UPDATE users SET age = age + 1 WHERE id = 1"},
            {'query': "UPDATE users SET age = age + 1 WHERE id = 2"},
        ]
        db_manager.transaction_example(operations)
        
    finally:
        # Disconnect
        db_manager.disconnect()

if __name__ == "__main__":
    main()