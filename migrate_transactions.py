"""
Database migration for CreditTransaction enhancements
Adds detailed transaction tracking fields
"""
import sqlite3

def migrate_credit_transactions():
    """Add new columns to CreditTransaction table"""
    conn = sqlite3.connect('instance/barter.db')
    cursor = conn.cursor()
    
    columns_to_add = [
        ('description', 'VARCHAR(255)'),
        ('reason', 'VARCHAR(100)'),
        ('balance_before', 'FLOAT'),
        ('balance_after', 'FLOAT'),
        ('related_order_id', 'INTEGER'),
        ('related_item_id', 'INTEGER'),
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE credit_transaction ADD COLUMN {col_name} {col_type}')
            print(f'✓ Added {col_name} column')
        except Exception as e:
            error_msg = str(e).lower()
            if 'duplicate' in error_msg or 'already exists' in error_msg:
                print(f'✓ {col_name} already exists')
            else:
                print(f'✗ {col_name}: {str(e)[:50]}')
    
    conn.commit()
    conn.close()
    print('\nCreditTransaction migration complete!')

if __name__ == '__main__':
    migrate_credit_transactions()
