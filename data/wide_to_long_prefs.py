#!/usr/bin/env python3

import pandas as pd

people = pd.read_csv('people.csv')
prefs = pd.read_csv('preferences_wide.csv')
daily = pd.read_csv('daily_tasks.csv')
weekly = pd.read_csv('weekly_tasks.csv')
occasional = pd.read_csv('occasional_tasks.csv')
seasonal = pd.read_csv('seasonal_tasks.csv')

def get_task_type(task_name):
    for task_type in ['daily', 'weekly', 'occasional', 'seasonal']:
        if task_name in eval(task_type).task.values:
            return task_type

# melt
prefs = prefs.melt(id_vars = 'task', var_name = 'first_name',
                   value_name = 'preference')
prefs['task_type'] = prefs.task.apply(get_task_type)
people = people.reset_index(names = 'person_id')
prefs = prefs.merge(people[['first_name', 'person_id']], on =
                    'first_name')
prefs[['task', 'task_type', 'person_id',
       'preference']].to_csv('preferences.csv', index = False)
