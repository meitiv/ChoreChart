from maitri_db import tables
from maitri_db import db
from param import *
import pandas as pd
import numpy as np
import sqlite3
from typing import List
import re
import sys
from collections import defaultdict
from datetime import timedelta, datetime

def get_max_gap(days: List[int]) -> int:
    # calculate the largest circular gap between days
    days = sorted(days)
    num_days = len(days)
    days.append(days[0] + 7)
    return max(days[i+1] - days[i] for i in range(num_days))

def count_avail_days(request: int) -> int:
    return np.binary_repr(request, 7).count('1')

def get_weekdays(request: int) -> List[int]:
    # request int is the integer value of the binary representation of
    # availablility, e.g. 0101101 is the binary for 45 and means
    # available on Tue, Thu, Fri, and Sun
    # this function returns a list of day integers Monday is 0
    return [match.span()[0] for match in
            re.finditer('1', np.binary_repr(request, 7))]

def get_table(con, table, parse_dates = None):
    return pd.read_sql(con=con, sql=f"SELECT * FROM {table}",
                       parse_dates=parse_dates)

def get_people_and_days(column, requests):
    # returns a pd.Series with person_id as index and days as values
    # column argument is the name of the requests column to use
    df = requests[['person_id', column]].copy()
    df['day'] = df[column].apply(get_weekdays)
    df = df.drop(columns = [column]).explode('day').dropna()
    df = df.groupby('person_id')['day'].apply(list).reset_index()
    df['num_days'] = df.day.apply(len)
    return df.set_index('person_id').sort_values('num_days')

def merge_prefs(avail_df, pref_df, task_name):
    return avail_df.merge(
        pref_df[pref_df.task == task_name][["person_id", "preference"]],
        left_index = True,
        right_on = "person_id",
        how = "left"
    ).sort_values(
        ["preference", "num_days"], ascending = [False, True]
    ).set_index('person_id')

def append_timed_rows(assign_dict, task_id, monday, rows):
    for person_id, days in assign_dict.items():
        for day in days:
            rows.append({
                'week_start_date': monday,
                'person_id': person_id,
                'weekday': day,
                'task_id': task_id
            })
    return rows

def append_chore_rows(assign_dict, task_type, monday, rows):
    for person_id, task_ids in assign_dict.items():
        for task_id in task_ids:
            rows.append({
                'week_start_date': monday,
                'person_id': person_id,
                'task_type': task_type,
                'task_id': task_id
            })
    return rows

def get_hours_worked(monday, assignments, assignments_timed,
                     daily, weekly, seasonal, occasional):
    timed = assignments_timed.query(
        f'week_start_date == "{monday}"'
    ).merge(
        daily[['id', 'duration_hours']],
        left_on = 'task_id', right_on = 'id'
    )
    hours_timed = timed.groupby('person_id').duration_hours.sum()
    frames = []
    for task_type in ['daily', 'weekly', 'seasonal', 'occasional']:
        df = eval(task_type)[['id', 'duration_hours']].copy()
        df['task_type'] = task_type
        frames.append(df)
    chores = assignments.query(
        f'week_start_date == "{monday}"'
    ).merge(
        pd.concat(frames)[['id', 'task_type', 'duration_hours']],
        left_on = ['task_id', 'task_type'],
        right_on = ['id', 'task_type']
    )
    hours = chores.groupby('person_id').duration_hours.sum()
    return pd.concat((hours, hours_timed), axis = 1).fillna(0).sum(axis = 1)

def assign_chores():
    # read the data
    with sqlite3.connect(db) as con:
        people = get_table(con, "people").set_index('id')
        requests = get_table(con, "requests")
        preferences = get_table(con, "preferences")
        daily = get_table(con, "daily_tasks")
        weekly = get_table(con, "weekly_tasks")
        occasional = get_table(con, "occasional_tasks")
        seasonal = get_table(con, "seasonal_tasks")
        today = datetime.today().date()
        monday = today + timedelta(days = 7 - today.weekday())
        this_monday = monday - timedelta(days = 7)
        year = monday.year 
        seasonal['start_date'] = pd.to_datetime(seasonal.start_date + f"/{year}")
        seasonal['end_date'] = pd.to_datetime(seasonal.end_date + f"/{year}")
        seasonal['end_date'] = seasonal.apply(
            lambda row: row.end_date if row.end_date > row.start_date
            else row.end_date + timedelta(days = 365),
            axis = 1
        )
        # get last week's hourly deficit
        deficit = pd.read_sql(
            con=con,
            sql=f"""
            SELECT person_id, leftover_hours FROM hours
            WHERE week_start_date = '{this_monday}'"""
        ).set_index('person_id').squeeze()

    # compute target hours
    days_in_town = requests.query(
        f'week_start_date == "{monday}"'
    ).set_index('person_id').days_in_town.apply(count_avail_days)
    fraction = days_in_town/7*people.load_fraction
    # effective number of people
    total_people = fraction.sum()
    # hours per person
    target_per_person_hours = target_weekly_hours/total_people
    # assign hours to people by fraction
    for person_id, person in people.iterrows():
        people.loc[person_id, 'chore_hours'] = (
            target_per_person_hours*fraction.get(person_id, 0)
            - parent_credit_hours*person.parent
            + deficit.get(person_id, 0)
        )
        # decrease the target hours if above configured max
        if people.loc[person_id, 'chore_hours'] > max_weekly_person_hours:
           people.loc[person_id, 'chore_hours'] = max_weekly_person_hours 
    # save target hours
    hours_this_week = pd.DataFrame(index = people.index)
    hours_this_week.insert(0, 'week_start_date', monday)
    hours_this_week['days_in_town'] = days_in_town
    hours_this_week['target_hours'] = people.chore_hours
    hours_this_week = hours_this_week.fillna(0)
    
    # people available to cook the house meal, cleanup, sweep
    requests = requests.query(f'week_start_date == "{monday}"')
    intown = get_people_and_days('days_in_town', requests)
    meal = get_people_and_days('cook_meal', requests)
    clean = get_people_and_days('meal_cleanup', requests)
    sweep = get_people_and_days('night_sweep', requests)
    dishes_am = get_people_and_days('dishes_am', requests)
    dishes_pm = get_people_and_days('dishes_pm', requests)

    # get the task data
    meal_task = daily.query('task == "House Meal"').squeeze()
    clean_lead_task = daily.query('task == "Meal Cleanup Lead"').squeeze()
    clean_help_task = daily.query('task == "Meal Cleanup Helper"').squeeze()
    night_sweep_task = daily.query('task == "Night Cleanup"').squeeze()
    dishes_am_task = daily.query('task == "Unload Dishes AM"').squeeze()
    dishes_pm_task = daily.query('task == "Unload Dishes PM"').squeeze()

    cook = defaultdict(list)
    max_gap = 7
    for person_id, row in meal.iterrows():
        # make sure the cook has enough remaining hours
        if people.loc[person_id, 'chore_hours'] < meal_task.duration_hours:
            continue

        for day in row.day:
            # skip days that already have a cook
            if day in sum(cook.values(), []):
                continue

            # make sure that two cleaners (other than the cooks) are
            # available on this day
            clean = clean[~clean.index.isin(cook.keys())]
            num_cleaners = clean.day.apply(lambda l: day in l).sum()
            if num_cleaners < 2:
                continue

            days = sum(cook.values(), [day])
            putative_max_gap = get_max_gap(days)
            if putative_max_gap <= max_gap:
                max_gap = putative_max_gap
                best_day = day

        cook[person_id].append(best_day)
        # subtract 2.5h from chore_hours for this cook
        people.loc[person_id, 'chore_hours'] -= meal_task.duration_hours

    # assign clean lead
    clean_pref = merge_prefs(clean, preferences, "Meal Cleanup Lead")
    clean_lead = defaultdict(list)
    clean_days = sum(cook.values(), [])
    for person_id, row in clean_pref.iterrows():
        if not clean_days: break
        for day in clean_days:
            if day in row.day:
                # make sure there is enough hours
                if people.loc[person_id, 'chore_hours'] < clean_lead_task.duration_hours:
                    continue
                clean_lead[person_id].append(day)
                clean_days.remove(day)
                row.day.remove(day)
                people.loc[person_id, 'chore_hours'] -= clean_lead_task.duration_hours

    # assing clean_help
    clean_pref = merge_prefs(clean, preferences, "Meal Cleanup Helper")
    clean_help = defaultdict(list)
    clean_days = sum(cook.values(), [])
    for person_id, row in clean_pref.iterrows():
        if not clean_days: break
        for day in clean_days:
            # make sure this person is not the lead
            if day in clean_lead.get(person_id, []):
                continue
            if day in row.day:
                # make sure there is enough hours
                if people.loc[person_id, 'chore_hours'] < clean_help_task.duration_hours:
                    continue
                clean_help[person_id].append(day)
                clean_days.remove(day)
                row.day.remove(day)
                people.loc[person_id, 'chore_hours'] -= clean_help_task.duration_hours

    # assign night sweep to all days that do not have a meal
    clean_days = sum(cook.values(), [])
    sweep_days = [d for d in range(7) if d not in clean_days]
    clean_pref = merge_prefs(clean, preferences, "Night Cleanup")
    sweep = defaultdict(list)
    for person_id, row in clean_pref.iterrows():
        if not sweep_days: break
        for day in sweep_days:
            if day in row.day:
                # make sure there is enough hours
                if people.loc[person_id, 'chore_hours'] < night_sweep_task.duration_hours:
                    continue
                sweep[person_id].append(day)
                sweep_days.remove(day)
                row.day.remove(day)
                people.loc[person_id, 'chore_hours'] -= night_sweep_task.duration_hours

    # assign the weekly chores
    # the main bathroom chore needs to be assigned at random with
    # probabilities proportional to the preference
    weekly_chores = defaultdict(list) # keys are person_id, values are
                                      # lists of weekly task_ids
    task = weekly.query('task == "Bathrm, Main"').squeeze()
    intown_avail = merge_prefs(intown, preferences, 'Bathrm, Main')
    # add a column with boolean enough hours
    intown_avail['enough_hours'] = people.chore_hours >= task.duration_hours
    intown_avail = intown_avail.query(
        'num_days > 0 & preference > 0 & enough_hours'
    ).copy()
    intown_avail['prob'] = intown_avail.preference/intown_avail.preference.sum()
    person_id = int(intown_avail.sample(weights = 'prob').squeeze().name)
    weekly_chores[person_id].append(int(task.name))
    people.loc[person_id, 'chore_hours'] -= task.duration_hours
    weekly = weekly[~(weekly.index == task.name)]

    # the rest of the tasks are assigned by availability and
    # preference
    for task_id, task in weekly.iterrows():
        print('Assigning', task.task)
        intown_avail = merge_prefs(intown, preferences, task.task)
        intown_avail['enough_hours'] = people.chore_hours >= task.duration_hours
        intown_avail = intown_avail.query(
            'num_days > 0 & enough_hours & preference > 0'
        )
        if intown_avail.empty:
            print("Not enough hours for weekly task: " + task.task)
            continue
        person_id = int(intown_avail.iloc[0].name)
        weekly_chores[person_id].append(int(task_id))
        people.loc[person_id, 'chore_hours'] -= task.duration_hours
    
    # assign AM/PM dishwasher emptying
    empty_dishes_am = defaultdict(list)
    am_pref = merge_prefs(dishes_am, preferences, 'Unload Dishes AM')
    for day in range(7):
        for person_id, row in am_pref.iterrows():
            if day not in row.day:
                continue
            if people.loc[person_id, 'chore_hours'] < dishes_am_task.duration_hours:
                continue
            empty_dishes_am[person_id].append(day)
            people.loc[person_id, 'chore_hours'] -= dishes_am_task.duration_hours
            break

    empty_dishes_pm = defaultdict(list)
    pm_pref = merge_prefs(dishes_pm, preferences, 'Unload Dishes PM')
    for day in range(7):
        for person_id, row in pm_pref.iterrows():
            if day not in row.day:
                continue
            if people.loc[person_id, 'chore_hours'] < dishes_pm_task.duration_hours:
                continue
            empty_dishes_pm[person_id].append(day)
            people.loc[person_id, 'chore_hours'] -= dishes_pm_task.duration_hours
            break

    # construct the assignments_timed dataframe with
    # week_start_date,person_id,weekday,task_id columns
    rows = append_timed_rows(cook, meal_task.name, monday, [])
    rows = append_timed_rows(clean_lead, clean_lead_task.name, monday, rows)
    rows = append_timed_rows(clean_help, clean_help_task.name, monday, rows)
    rows = append_timed_rows(sweep, night_sweep_task.name, monday, rows)
    rows = append_timed_rows(empty_dishes_am, dishes_am_task.name, monday, rows)
    rows = append_timed_rows(empty_dishes_pm, dishes_pm_task.name, monday, rows)
    assignments_timed = pd.DataFrame(rows)
    
    # add the urgency column to the seasonal task definitions
    date_last_performed = pd.read_sql(
        con=con,
        sql="""SELECT task_id as id, MAX(week_start_date) as date_last_performed
        FROM assignments WHERE task_type = 'seasonal' GROUP BY task_id"""
    )
    seasonal = seasonal.merge(
        date_last_performed, on = 'id', how = 'left'
    ).fillna(monday - timedelta(days = 365))
    # remove tasks with negative urgency (they don't have to be done yet)
    seasonal['urgency'] = (pd.to_datetime(monday) - pd.to_datetime(seasonal.date_last_performed)).dt.days - seasonal.frequency_days
    seasonal = seasonal[seasonal.urgency > 0]
    # seasonal assignments
    seasonal_chores = defaultdict(list)
    for task_id, task in seasonal.sort_values('urgency', ascending = False).iterrows():
        if monday > task.end_date.date() or monday < task.start_date.date():
            print('Skipping seasonal', task.task, ': out of season')
            continue
        print('Assigning', task.task)
        intown_avail = merge_prefs(intown, preferences, task.task)
        intown_avail['enough_hours'] = people.chore_hours >= task.duration_hours
        intown_avail = intown_avail.query(
            'num_days > 0 & enough_hours & preference > 0'
        )
        if intown_avail.empty:
            print("Not enough hours for seasonal task: " + task.task)
            continue
        person_id = int(intown_avail.iloc[0].name)
        seasonal_chores[person_id].append(int(task_id))
        people.loc[person_id, 'chore_hours'] -= task.duration_hours

    # add the urgency column to the occasional task definitions
    date_last_performed = pd.read_sql(
        con=con,
        sql="""SELECT task_id as id, MAX(week_start_date) as date_last_performed
        FROM assignments WHERE task_type = 'occasional' GROUP BY task_id"""
    )
    occasional = occasional.merge(
        date_last_performed, on = 'id', how = 'left'
    ).fillna(monday - timedelta(days = 365))
    occasional['urgency'] = (pd.to_datetime(monday) - pd.to_datetime(occasional.date_last_performed)).dt.days/7 - occasional.frequency_weeks
    # remove tasks with negative urgency (they don't have to be done yet)
    occasional = occasional[occasional.urgency > 0]
    # occasional assignments
    occasional_chores = defaultdict(list)
    for task_id, task in occasional.sort_values('urgency', ascending = False).iterrows():
        print('Assigning', task.task)
        intown_avail = merge_prefs(intown, preferences, task.task)
        intown_avail['enough_hours'] = people.chore_hours >= task.duration_hours
        intown_avail = intown_avail.query(
            'num_days > 0 & enough_hours & preference > 0'
        )
        if intown_avail.empty:
            print("Not enough hours for occasional task: " + task.task)
            continue
        person_id = int(intown_avail.iloc[0].name)
        occasional_chores[person_id].append(int(task_id))
        people.loc[person_id, 'chore_hours'] -= task.duration_hours

    # create the assignments dataframe with week_start_date,person_id,task_type,chore_id columns
    rows = append_chore_rows(weekly_chores, 'weekly', monday, [])
    rows = append_chore_rows(seasonal_chores, 'seasonal', monday, rows)
    rows = append_chore_rows(occasional_chores, 'occasional', monday, rows)
    assignments = pd.DataFrame(rows)

    # update the database: assignments and people (deficit column)
    with sqlite3.connect(db) as con:
        cur = con.cursor()
        con.execute(f'DELETE FROM assignments WHERE week_start_date = "{monday}"')
        con.execute(f'DELETE FROM assignments_timed WHERE week_start_date = "{monday}"')
        con.execute(f'DELETE FROM hours WHERE week_start_date = "{monday}"')
        con.commit()
        assignments.to_sql(con=con, name='assignments', index=False, if_exists='append')
        assignments_timed.to_sql(con=con, name='assignments_timed', index=False, if_exists='append')
        # update the hours table
        hours_this_week['leftover_hours'] = people.chore_hours
        hours_this_week = hours_this_week.fillna(0)
        hours_this_week['hours_worked'] = hours_this_week.target_hours - hours_this_week.leftover_hours
        hours_this_week['person_id'] = hours_this_week.index
        hours_this_week.to_sql(con=con, name="hours", index=False, if_exists="append")

    # return the monday of the constructed chore chart
    return str(monday)
