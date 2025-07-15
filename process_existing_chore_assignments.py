#!/usr/bin/env python3

import pandas as pd
from param import *
from maitri_db import db
import pygsheets
import sqlite3
import re

task_name_map = {
    'Landscaping (Mow lawn)': 'Lawn Maintenance',
    'Daily empty N Basement room Dehumidifier': 'Empty N Basement Room Dehumidifier',
    'Vacuum Basement Stairwell': 'Vacuum Basement Stairwell and Landing',
    'Vacuum Entryway and top 2 Stairs': 'Vacuum Entryway and Top 2 Stairs',
    'Sweep and Mop Main Fl': 'Sweep/Mop Main Fl',
    'Shopping/ Refill Empty Food Containers': 'Refill Empty Food Containers',
    'Maintain new vacuum': 'Maintain New Vacuum',
    'Maintain pressure cooker': 'Maintain Pressure Cooker',
    'Clean Mini-Split filters': 'Clean Mini-Split Filters',
    'Kitchen Hood Filters': 'Clean Kitchen Hood Filters',
}

def process_date(date_str, year):
    if '/' not in date_str:
        return
    month, day = date_str.split('/')
    if not (month.isnumeric() or day.isnumeric()):
        return
    date = pd.Timestamp(f'{year}-{month}-{day}')
    if date.weekday() != 0:
        print(f'{date_str} is not a Monday')
        return
    return str(date.date())

def propagate_value(column: pd.Series) -> pd.Series:
    prev_value = None
    for idx in column.index:
        if (not column[idx] or pd.isnull(column[idx])) and prev_value is not None:
            column[idx] = prev_value
        if column[idx]:
            prev_value = column[idx]
    return column

def process_task_name(task_name, duplicate: bool):
    # clean up the task names and map onto the task names in the
    # Maitri database
    if 'am' in task_name:
        task_name = 'Unload Dishes AM'
    if 'pm' in task_name:
        task_name = 'Unload Dishes PM'
    if 'night swee' in task_name.lower():
        task_name = 'Night Cleanup'
    if 'House Meal' in task_name:
        task_name = 'House Meal'
    if 'sous' in task_name.lower():
        task_name = 'Sous Chef for House Meal'
    if 'Meal Cleanup' in task_name:
        if duplicate:
            task_name = 'Meal Cleanup Helper'
        else:
            task_name = 'Meal Cleanup Lead'
    # now map the task names that differ
    if task_name in task_name_map:
        task_name = task_name_map[task_name]
    return task_name

def get_weekday(task_name):
    task_name = task_name.lower().replace(' am', '').replace(' pm', '')
    day = task_name.split()[-1]
    if day.startswith('m'): return 0
    if day.startswith('tu'): return 1
    if day.startswith('w'): return 2
    if day.startswith('th'): return 3
    if day.startswith('f'): return 4
    if day.startswith('sa'): return 5
    if day.startswith('su'): return 6

class ChoreChartReader:
    def __init__(self, year):
        self.con = sqlite3.connect(db)
        self.cur = self.con.cursor()
        self.year = year
        self.people = pd.read_sql(con=self.con, sql='SELECT * FROM people').set_index('first_name')
        self.daily = pd.read_sql(con=self.con, sql='SELECT * FROM daily_tasks')
        self.weekly = pd.read_sql(con=self.con, sql='SELECT * FROM weekly_tasks')
        self.seasonal = pd.read_sql(con=self.con, sql='SELECT * FROM seasonal_tasks')
        self.occasional = pd.read_sql(con=self.con, sql='SELECT * FROM occasional_tasks')

    def connect_sheet(self):
        gc = pygsheets.authorize(service_file=service_file)
        self.sheets = gc.open(f'CSS {self.year}').worksheets()
        
    def match_person(self, first_name):
        if first_name not in self.people.index:
            return
        return self.people.loc[first_name, 'id']

    def process_hours(self, cell_value):
        hours = []
        people = []
        for chunk in cell_value.split(':')[1].split(','):
            if 'hr' not in chunk: continue
            person_id = self.match_person(chunk.split()[0])
            if person_id is None: continue
            hours.append(re.search('\((.*)hr', chunk).groups()[0])
            people.append(person_id)
        return pd.Series(hours, index = people).rename('hours_worked').astype(float)

    def process_intown(self, cell_value):
        days = []
        people = []
        for chunk in cell_value.split(':')[1].split(','):
            if 'd' not in chunk: continue
            person_id = self.match_person(chunk.split()[0])
            if person_id is None: continue
            days.append(re.search('\((.*)d', chunk).groups()[0])
            people.append(person_id)
        return pd.Series(days, index = people).rename('days_in_town').astype(float)

    def calc_target_hours(self, days_in_town):
        people_copy = self.people.reset_index().set_index('id').copy()
        fraction = (days_in_town/7*people_copy.load_fraction).dropna()
        # sum the fraction to get the effective number of people
        total_effective_people = fraction.sum()
        # the per-person hours is the total weekly hours divided by the
        # effective number of people
        total_hours = target_weekly_hours
        target_per_person_hours = total_hours/total_effective_people
        # assign hours to people by fraction
        people_copy['chore_hours'] = target_per_person_hours*fraction
        # this is the reduction factor that will assure that nobody's
        # total is greater than the max_weekly_person_hours configures in
        # param.py
        reduction_factor = max_weekly_person_hours/target_per_person_hours
        # if the factor is 1 or greater, don't need to do anything
        people_copy['chore_hours'] *= reduction_factor if reduction_factor < 1 else 1
        return people_copy.chore_hours.fillna(0)

    def match_task(self, task_name):
        for table in ['daily', 'weekly', 'seasonal', 'occasional']:
            data = eval(f'self.{table}')
            row = data[data.task == task_name].squeeze()
            if not row.empty:
                return table, row.id
        return None, None

    def main(self):
        self.connect_sheet()
        for sheet in self.sheets:
            date = process_date(sheet.title, self.year)
            if date is None:
                print('Skipping', sheet.title)
                continue
            print('Processing', date, 'chores')
            chores = sheet.get_as_df(
                has_header = False,
                start = 'C3',
                end = 'E89'
            )
            # get the hours and days in town
            hours = self.process_hours(sheet.get_value('B98'))
            days_in_town = self.process_intown(sheet.get_value('B96'))

            # propagate chore names
            chores[0] = propagate_value(chores[0])
            # remove rows without name
            chores = chores[chores[2].astype(bool)]
            prev_task_name = ''
            # update the hours table
            self.cur.execute(
                f"DELETE FROM hours WHERE week_start_date = '{date}'"
            )
            hours = pd.concat((hours, days_in_town), axis = 1).fillna(0)
            hours['target_hours'] = self.calc_target_hours(days_in_town)
            hours['leftover_hours'] = hours.target_hours - hours.hours_worked
            hours = hours.reset_index().rename(columns = {'index': 'person_id'})
            hours.insert(0, 'week_start_date', date)
            hours.to_sql(con=self.con, name='hours', index=False, if_exists='append')        
            # clear the assignments for this week first
            self.cur.execute(
                f"DELETE FROM assignments_timed WHERE week_start_date = '{date}'"
            )
            self.cur.execute(
                f"DELETE FROM assignments WHERE week_start_date = '{date}'"
            )
            for _, row in chores.iterrows():
                chore_name = process_task_name(row[0], row[0] == prev_task_name)
                prev_task_name = row[0]
                task_type, task_id = self.match_task(chore_name)
                person_id = self.match_person(row[2])
                if task_id is None or person_id is None: continue
                if task_type == 'daily':
                    weekday = get_weekday(row[0])
                    if weekday is None: continue
                    self.cur.execute(
                        f"""INSERT INTO assignments_timed VALUES
                        ('{date}', {person_id}, {weekday}, {task_id})"""
                    )
                else:
                    # print('Inserting', date, person_id, task_id, 'into assignments')
                    self.cur.execute(
                        f"""INSERT INTO assignments VALUES
                        ('{date}', {person_id}, '{task_type}', {task_id})"""
                    )

if __name__ == '__main__':
    reader = ChoreChartReader(2025)
    reader.main()
