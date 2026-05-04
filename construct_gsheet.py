#!/usr/bin/env python3

import pygsheets
import sqlite3
import pandas as pd
from param import *
from maitri_db import db
from datetime import timedelta
import time
import argparse
import yaml
from collections import defaultdict

class GsheetConstructor:
    def __init__(self, monday):
        self.monday = str(monday)
        self.monday_dt = pd.to_datetime(monday).date()
        # error out if monday is not a monday
        if self.monday_dt.weekday() != 0:
            raise ValueError('{} is not a Monday'.format(monday))
        self.gc = pygsheets.authorize(service_file=service_file)
        self.con = sqlite3.connect(db)
        self.separator_rows = []

    def load_data(self):
        self.people = pd.read_sql(con=self.con, sql="SELECT * FROM people").rename(columns = {'id': 'person_id'})
        for task_type in ('daily', 'weekly', 'seasonal', 'occasional'):
            df = pd.read_sql(con=self.con, sql=f"SELECT * FROM {task_type}_tasks").rename(columns = {'id': 'task_id'})
            if task_type != 'daily': df['task_type'] = task_type
            exec(f"self.{task_type} = df.copy()")
        self.chores = pd.read_sql(
            con=self.con, sql="SELECT * FROM assignments"
        ).query(f'week_start_date == "{self.monday}"')
        self.chores_timed = pd.read_sql(
            con=self.con, sql="SELECT * FROM assignments_timed"
        ).query(f'week_start_date == "{self.monday}"')
        self.hours = pd.read_sql(
            con=self.con, sql="SELECT * FROM hours"
        ).query(f'week_start_date == "{self.monday}"')
        # merge the tasks into the chores
        self.chores_timed = self.chores_timed.merge(self.daily, on = 'task_id')
        cols = ['task_id', 'task_type', 'task', 'category', 'description', 'duration_hours']
        self.tasks = pd.concat(
            (self.weekly[cols], self.seasonal[cols], self.occasional[cols])
        )
        self.chores = self.chores.merge(self.tasks, on = ['task_type', 'task_id'])
        # merge people's first name
        self.chores = self.chores.merge(self.people[['person_id', 'first_name']], on = 'person_id')
        self.chores_timed = self.chores_timed.merge(self.people[['person_id', 'first_name']], on = 'person_id')
        self.hours = self.hours.merge(self.people[['person_id', 'first_name', 'parent']], on = 'person_id')
        # replace the task duration with the custom duration from
        # fixed_chores.yaml
        fixed_chores = yaml.safe_load(open('fixed_chores.yaml'))
        custom_duration = defaultdict(dict) # keys are the first names,
        # values are dictionaries with
        # task names as keys
        for task_type, assignments in fixed_chores.items():
            for assnmt in assignments:
                if 'credit' in assnmt:
                    custom_duration[assnmt['person']][assnmt['chore']] = assnmt['credit']
        for idx, row in self.chores.iterrows():
            if row.first_name in custom_duration and \
               row.task in custom_duration[row.first_name]:
                self.chores.loc[idx, 'duration_hours'] = custom_duration[row.first_name][row.task]

    def create_sheet(self):
        wbk = self.gc.open_by_key(gsheet_key)
        # delete existing sheets that match the monday
        for sheet in wbk.worksheets():
            if sheet.title == self.monday:
                wbk.del_worksheet(sheet)
        self.sheet = wbk.add_worksheet(self.monday, index = 0)

    def add_header(self):
        # add the header
        self.sheet.get_values('B1', 'E1', returnas = 'range').merge_cells()
        self.sheet.update_value('B1', header_text)
        self.sheet.cell('B1').wrap_strategy = 'WRAP'
        self.sheet.get_values('B2', 'C2', returnas = 'range').merge_cells()
        self.sheet.get_values('D2', 'E2', returnas = 'range').merge_cells()
        self.sheet.cell('B2').set_text_format('bold', True).value = f'Week of {self.monday}'
        self.sheet.cell('D2').set_text_format('bold', True).value = f'Total hours: {self.hours.hours_worked.sum()}'
        self.separator_rows.append(3)
        self.current_row = 4
        rows = [['Name', 'Days in town', 'Hours', 'Accept']]
        for _, row in self.hours.query('hours_worked > 0').iterrows():
            name = row.first_name
            hours_worked = row.hours_worked
            if row.parent == 1:
                name += f' (parental credit of {parent_credit_hours} hour)'
                hours_worked += parent_credit_hours
            rows.append([name, f'{round(row.days_in_town)}d', f'{hours_worked} hrs', '☐'])
            self.current_row += 1
        self.sheet.update_values('B3', rows)
        self.separator_rows.append(self.current_row)

    def get_day_name(self, weekday):
        return (self.monday_dt + timedelta(days = weekday)).strftime("%a")

    def set_description_cell_props(self):
        self.sheet.cell(f'B{self.current_row}').wrap_strategy = 'WRAP'
        self.sheet.cell(f'B{self.current_row}').set_vertical_alignment(pygsheets.custom_types.VerticalAlignment.TOP)

    def set_category_cell_props(self):
        cell = self.sheet.cell(f'A{self.current_row}')
        cell.wrap_strategy = 'WRAP'
        cell.set_vertical_alignment(pygsheets.custom_types.VerticalAlignment.MIDDLE)
        cell.set_horizontal_alignment(pygsheets.custom_types.HorizontalAlignment.CENTER)
        cell.set_text_rotation('angle', 90)
        cell.set_text_format('fontSize', 12)

    def add_meal(self):
        meals = self.chores_timed.query('category == "Meals"')
        self.num_meals = len(meals)
        self.merge_and_set_text('A', self.num_meals - 1, "Meals")
        self.set_category_cell_props()        
        if self.num_meals > 1:
            rng = self.sheet.get_values(
                f'B{self.current_row}',
                f'B{self.current_row + self.num_meals - 1}',
                returnas = 'range'
            )
            rng.merge_cells()
            rng.update_borders(top = True, style = border_thickness)
        self.sheet.update_value(f'B{self.current_row}', meals.description.iloc[0])
        self.set_description_cell_props()
        # iterate over meals
        for _, chore in meals.sort_values('weekday').iterrows():
            self.sheet.update_value(
                f'C{self.current_row}',
                f'{chore.task} {self.get_day_name(chore.weekday)}'
            )
            self.sheet.cell(f'C{self.current_row}').set_text_format('bold', True)
            self.fill_chore_info(chore)
        self.separator_rows.append(self.current_row)

    def fill_full_chore_info(self, chore):
        self.sheet.update_value(f'B{self.current_row}', chore.description)
        self.sheet.cell(f'B{self.current_row}').wrap_strategy = 'WRAP'
        self.fill_chore_name(chore)
        self.fill_chore_info(chore)

    def fill_chore_name(self, chore):
        self.sheet.update_value(f'C{self.current_row}', chore.task)
        self.sheet.cell(f'C{self.current_row}').set_text_format('bold', True)

    def fill_chore_info(self, chore):
        self.sheet.update_value(f'D{self.current_row}', chore.duration_hours)
        self.sheet.update_value(f'E{self.current_row}', chore.first_name)
        check_addr = f'F{self.current_row}'
        self.sheet.update_value(check_addr, '☐')
        #self.sheet.set_data_validation(start = check_addr, end = check_addr, condition_type = 'CHECKBOX')
        self.current_row += 1

    def draw_separators(self):
        for row in self.separator_rows:
            self.sheet.get_values(
                f'A{row}', f'F{row}',returnas = 'range'
            ).update_borders(top = True, style = border_thickness)

    def merge_and_set_text(self, column, num_rows, text):
        self.sheet.get_values(
            f'{column}{self.current_row}', f'{column}{self.current_row + num_rows}', returnas = 'range'
        ).merge_cells()
        self.sheet.update_value(f'{column}{self.current_row}', text)

    def add_cleanup(self):
        self.merge_and_set_text('B', self.num_meals + 6, meal_description)
        self.set_description_cell_props()
        self.merge_and_set_text('A', self.num_meals + 6, "Night Cleanup")
        self.set_category_cell_props()        
        # iterate over days
        chores = self.chores_timed.query('category == "Meal Cleanup"')
        for day in range(7):
            for _, chore in chores.query(f'weekday == {day}').iterrows():
                task_name = chore.task.replace('Helper', '').replace('Lead', '')
                self.sheet.update_value(
                    f'C{self.current_row}', f'{task_name} {self.get_day_name(day)}'
                )
                self.sheet.cell(f'C{self.current_row}').set_text_format('bold', True)
                self.fill_chore_info(chore)
        self.separator_rows.append(self.current_row)

    def add_dishes(self):
        num_dishes = self.chores_timed.task.str.contains('Unload Dishes').sum() - 1
        self.merge_and_set_text('B', num_dishes,
                                self.daily.query('task == "Unload Dishes AM"').description.unique()[0])
        self.set_description_cell_props()
        self.merge_and_set_text('A', num_dishes, "Dishes")
        self.set_category_cell_props()        
        for day in range(7):
            for period in ('AM', 'PM'):
                chore = self.chores_timed.loc[
                    (self.chores_timed.weekday == day) &
                    (self.chores_timed.task == f"Unload Dishes {period}")
                ].squeeze()
                if chore.empty: continue
                self.sheet.update_value(
                    f'C{self.current_row}', f'{chore.task} {self.get_day_name(day)}'
                )
                self.sheet.cell(f'C{self.current_row}').set_text_format('bold', True)
                self.fill_chore_info(chore)
        self.separator_rows.append(self.current_row)

    def add_category_chores(self, category, collapse_description = False):
        chores = self.chores.query(f'category == "{category}"')
        if chores.empty: return
        self.merge_and_set_text('A', len(chores) - 1, category)
        self.set_category_cell_props()
        if collapse_description:
            self.merge_and_set_text('B', len(chores) - 1, chores.description.unique()[0])
            self.set_description_cell_props()
        for _, chore in chores.iterrows():
            if collapse_description:
                self.fill_chore_name(chore)
                self.fill_chore_info(chore)
            else:
                self.fill_full_chore_info(chore)
        self.separator_rows.append(self.current_row)

    def adjust_column_widths(self):
        for col_idx, width in gsheet_column_widths.items():
            self.sheet.adjust_column_width(col_idx, pixel_size = width)

    def change_font_size(self, size = 12):
        all_cells = self.sheet.range(f'A1:F{self.current_row}')
        for cell in all_cells:
            if c.value:
                cell.text_format['fontSize'] = size

    def delete_unused_cells(self):
        self.sheet.delete_columns(7, 20)
        num_rows = 100 - self.current_row
        row_start = self.current_row + 1
        self.sheet.delete_rows(row_start, num_rows)

    def main(self):
        self.load_data()
        self.create_sheet()
        self.add_header()
        self.add_meal()
        time.sleep(sleep_sec)
        self.add_cleanup()
        time.sleep(sleep_sec)
        self.add_dishes()
        time.sleep(sleep_sec)
        self.add_category_chores("Main Kitchen")
        self.add_category_chores("Bathrooms", collapse_description = True)
        time.sleep(sleep_sec)
        self.add_category_chores("Other Common Areas")
        self.add_category_chores("Occasional Tasks")
        self.add_category_chores("Support Roles")
        #self.delete_unused_cells()
        self.draw_separators()
        self.adjust_column_widths()
        #self.change_font_size()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('monday', type = str,
                        help = 'monday date in YYYY-MM-DD format')
    monday = parser.parse_args().monday
    constructor = GsheetConstructor(monday)
    constructor.main()
