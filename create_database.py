#!/usr/bin/env python3
import sqlite3
import pandas as pd

tables = [
    'people',
    'daily_tasks',
    'weekly_tasks',
    'occasional_tasks',
    'seasonal_tasks',
    'preferences'
]

def main(db_path):
    """Create all tables for the Chore Chart app"""
    connection = sqlite3.connect(db_path)
    for table in tables:
        print(f'Loading {table}')
        pd.read_csv(f'data/{table}.csv').to_sql(
            con = connection,
            name = table,
            if_exists = 'replace',
            index_label = 'id'
        )

if __name__ == '__main__':
    main('maitri_chores.db')
