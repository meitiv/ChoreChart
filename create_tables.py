#!/usr/bin/env python3
import sqlite3
import pandas as pd
from maitri_db import db
from maitri_db import tables

with sqlite3.connect(db) as con:
    for table in tables:
        print(f'Creating {table}')
        pd.read_csv(f'data/{table}.csv').to_sql(
            con = con,
            name = table,
            if_exists = 'replace',
            index = False
        )
