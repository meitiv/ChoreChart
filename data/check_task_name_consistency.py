#!/usr/bin/env python3

import pandas as pd

prefs = pd.read_csv('preferences.csv')
daily = pd.read_csv('daily_tasks.csv')
weekly = pd.read_csv('weekly_tasks.csv')
occa = pd.read_csv('occasional_tasks.csv')
seas = pd.read_csv('seasonal_tasks.csv')

all_tasks = pd.concat((daily.task, weekly.task, occa.task, seas.task))

# get misaligned names that are in prefs but not in task definitions
print('In prefs but not in tasks:')
print(set(prefs.task) - set(all_tasks))

print()
print('In tasks but not in prefs:')
print(set(all_tasks) - set(prefs.task))
