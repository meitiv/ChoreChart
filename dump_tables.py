#!/usr/bin/env python3
import pandas as pd
import sqlite3
from maitri_db import db
from maitri_db import tables

with sqlite3.connect(db) as con:
    for table in tables:
        pd.read_sql(
            con = con, sql = f"SELECT * FROM {table}"
        ).to_csv(
            f"data/{table}.csv", index = False
        )
        
