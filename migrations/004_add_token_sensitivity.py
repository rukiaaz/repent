"""
Migration 004: Add anti_token_sensitivity column

Adds a column to store token protection sensitivity level (low/medium/high)
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "discord.db")

def migrate():
    """Add anti_token_sensitivity column to guilds table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add the column if it doesn't exist
        cursor.execute("""
            ALTER TABLE guilds 
            ADD COLUMN anti_token_sensitivity TEXT DEFAULT 'medium'
        """)
        
        conn.commit()
        print("✓ Successfully added anti_token_sensitivity column")
        return True
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("✓ Column already exists, skipping")
            return True
        else:
            print(f"✗ Error adding column: {e}")
            return False
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
