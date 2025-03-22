
import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
import sys

def backup_directory(path, suffix='backup'):
    """Create a backup of a directory"""
    if not os.path.exists(path):
        print(f"Directory not found: {path}")
        return
    
    backup_path = f"{path}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copytree(path, backup_path)
    print(f"Backup created at: {backup_path}")

def remove_directory(path):
    """Remove a directory if it exists"""
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"Removed directory: {path}")

def backup_database(db_path):
    """Create a backup of the database file"""
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return
    
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copyfile(db_path, backup_path)
    print(f"Database backup created at {backup_path}")

def fix_alembic_version_table(db_path):
    """Remove alembic_version table from database if it exists"""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if alembic_version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        if cursor.fetchone():
            # Drop the table
            cursor.execute("DROP TABLE alembic_version")
            conn.commit()
            print("Removed alembic_version table from database")
        else:
            print("alembic_version table not found in database")
        
        conn.close()
    except Exception as e:
        print(f"Error accessing database: {e}")

def main():
    # Current working directory
    cwd = os.getcwd()
    
    # Get database path
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("dotenv not found, using default database path")
    
    # Default database path
    default_db_path = os.path.join(cwd, 'instance', 'database.db')
    
    # Try to get from environment
    db_uri = os.getenv('SQLALCHEMY_DATABASE_URI', f'sqlite:///{default_db_path}')
    db_path = db_uri.replace('sqlite:///', '')
    
    # If path is relative, make it relative to current directory
    if not os.path.isabs(db_path):
        db_path = os.path.join(cwd, db_path)
    
    # Also check for common alternatives
    possible_db_paths = [
        db_path,
        os.path.join(cwd, 'swayam.db'),
        os.path.join(cwd, 'instance', 'swayam.db'),
        default_db_path
    ]
    
    # Find the database file
    db_found = False
    for path in possible_db_paths:
        if os.path.exists(path):
            db_path = path
            db_found = True
            print(f"Found database at: {db_path}")
            break
    
    if not db_found:
        print(f"No database found. Will use path from environment: {db_path}")
    
    # Backup and fix the database if it exists
    if os.path.exists(db_path):
        backup_database(db_path)
        fix_alembic_version_table(db_path)
    
    # Path to migrations directory
    migrations_dir = os.path.join(cwd, 'migrations')
    
    # Backup migrations directory if it exists
    if os.path.exists(migrations_dir):
        backup_directory(migrations_dir)
        remove_directory(migrations_dir)
    
    print("\nMigration reset completed!")
    print("\nTo reinitialize your database migrations, run these commands in order:")
    print("1. flask db init")
    print("2. flask db migrate -m 'initial migration'")
    print("3. flask db upgrade")
    print("\nThis will create a fresh migration history based on your current models.")

if __name__ == "__main__":
    main()