#!/usr/bin/env python3

from flask import Flask, redirect, request
from flask import render_template
from flask import url_for
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, timedelta
from maitri_db import db
import assign_chores

app = Flask(__name__)

def int_to_bits(number: int):
    return list(np.binary_repr(number, 7))

@app.route("/")
def landing_page():
    return render_template("index.html")

@app.route("/people")
def people():
    with sqlite3.connect(db) as con:
        people = pd.read_sql(
            con = con,
            sql = "SELECT * FROM people"
        )
    return render_template("people.html", people = people)

@app.route("/update_person", methods=["POST"])
def update_person():
    person_id = request.form["id"]
    load_fraction = float(request.form["frac"])
    if load_fraction < 0: load_fraction = 0
    if load_fraction > 1: load_fraction = 1
    parent = 1 if "parent" in request.form else 0
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        cursor.execute(
            f"""UPDATE people SET load_fraction = {load_fraction}
            WHERE id = {person_id}"""
        )
        cursor.execute(
            f"UPDATE people SET parent = {parent} WHERE id = {person_id}"
        )        
        con.commit()            

    return redirect(url_for("people"))


@app.route("/add_person", methods=["POST"])
def add_person():
    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    frac = float(request.form["frac"])
    parent = 1 if "parent" in request.form else 0
    deficit = 0
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        cursor.execute("SELECT MAX(id) FROM people")
        person_id = 1 + cursor.fetchone()[0]
        cursor.execute(
            f"""INSERT INTO people
            VALUES ('{person_id}', '{first_name}', '{last_name}',
            {frac}, {parent}, {deficit})"""
        )
        con.commit()
        # create default chore preferences for this person
        prefs = pd.read_sql(
            con = con,
            sql = "SELECT DISTINCT task, task_type FROM preferences"
        )
        prefs["person_id"] = person_id
        prefs["preference"] = 3
        # reindex to make sure no duplicate ids exist
        cursor.execute("SELECT MAX(id) FROM preferences")
        min_new_idx = 1 + cursor.fetchone()[0]
        prefs.index = np.arange(min_new_idx, min_new_idx + len(prefs))
        prefs.to_sql(
            con = con,
            name = "preferences",
            if_exists = "append",
            index_label = "id"
        )

    return redirect(url_for("people"))

@app.route("/delete_person", methods=["POST"])
def delete_person():
    person_id = request.form["id"]
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        cursor.execute(
            f"DELETE FROM people WHERE id = {person_id}"
        )
        cursor.execute(
            f"DELETE FROM preferences WHERE person_id = {person_id}"
        )
        cursor.execute(
            f"DELETE FROM requests WHERE person_id = {person_id}"
        )
        con.commit()
    return redirect(url_for("people"))

@app.route("/tasks")
def tasks():
    with sqlite3.connect(db) as con:
        daily_tasks = pd.read_sql(con=con, sql="SELECT * FROM daily_tasks")
        weekly_tasks = pd.read_sql(con=con, sql="SELECT * FROM weekly_tasks")
        occasional_tasks = pd.read_sql(
            con=con, sql="SELECT * FROM occasional_tasks",
            parse_dates = 'date_last_performed'
        )
        seasonal_tasks = pd.read_sql(
            con=con, sql="SELECT * FROM seasonal_tasks",
            parse_dates = 'date_last_performed'
        )
    return render_template(
        "tasks.html",
        daily_chores = daily_tasks,
        weekly_chores = weekly_tasks,
        occasional_chores = occasional_tasks,
        seasonal_chores = seasonal_tasks
    )

@app.route("/add_occasional_task", methods=["POST"])
def add_occasional_task():
    name = request.form["name"]
    description = request.form["description"]
    duration = request.form["duration"]
    frequency = request.form["frequency"]
    date = pd.Timestamp.today() - pd.Timedelta(weeks = 52)
    date = date.strftime("%m/%d/%Y")
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        # get the MAX preference_id
        cursor.execute("SELECT MAX(id) FROM preferences")
        pref_id = cursor.fetchone()[0]
        # get all person ids
        cursor.execute("SELECT id FROM people")
        for person_id in cursor.fetchall():
            pref_id += 1
            cursor.execute(
                f"""INSERT INTO preferences VALUES
                ({pref_id}, '{name}', 'occasional', {person_id[0]}, 3)"""
            )
        # get the new task id
        cursor.execute("SELECT MAX(id) FROM occasional_tasks")
        task_id = 1 + cursor.fetchone()[0]
        cursor.execute(
            f"""INSERT INTO occasional_tasks VALUES
            ('{task_id}', '{name}', 'Occasional Tasks',
            '{description}', {duration}, {frequency}, '{date}')"""
        )
        con.commit()
    return redirect(url_for("tasks"))

@app.route("/add_seasonal_task", methods=["POST"])
def add_seasonal_task():
    name = request.form["name"]
    description = request.form["description"]
    duration = request.form["duration"]
    frequency = request.form["frequency"]
    start = request.form["season_start"] + "/01"
    end = request.form["season_end"] + "/01"
    date = pd.Timestamp.today() - pd.Timedelta(weeks = 52)
    date = date.strftime("%m/%d/%Y")
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        # get the MAX preference_id
        cursor.execute("SELECT MAX(id) FROM preferences")
        pref_id = cursor.fetchone()[0]
        # get all person ids
        cursor.execute("SELECT id FROM people")
        for person_id in cursor.fetchall():
            pref_id += 1
            cursor.execute(
                f"""INSERT INTO preferences VALUES
                ({pref_id}, '{name}', 'seasonal', {person_id[0]}, 3)"""
            )
        cursor.execute("SELECT MAX(id) FROM seasonal_tasks")
        task_id = 1 + cursor.fetchone()[0]
        cursor.execute(
            f"""INSERT INTO occasional_tasks VALUES
            ('{task_id}', '{name}', 'Occasional Tasks',
            '{description}', {duration}, {frequency},
            '{start}', '{end}', '{date}')"""
        )
        con.commit()
    return redirect(url_for("tasks"))

@app.route("/delete_occasional_task", methods=["POST"])
def delete_occasional_task():
    task_id = request.form["id"]
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        cursor.execute(
            f"DELETE FROM occasional_tasks WHERE id = {task_id}"
        )
        cursor.execute(
            f"""DELETE FROM preferences
            WHERE task_type = "occasional" AND task = {task_name}"""
        )
        con.commit()
    return redirect(url_for("tasks"))

@app.route("/delete_seasonal_task", methods=["POST"])
def delete_seasonal_task():
    task_id = request.form["id"]
    with sqlite3.connect(db) as con:
        cursor = con.cursor()
        cursor.execute(
            f"SELECT task FROM seasonal_tasks WHERE id = {task_id}"
        )
        task_name = cursor.fetchone()[0]
        cursor.execute(
            f"DELETE FROM seasonal_tasks WHERE id = {task_id}"
        )
        cursor.execute(
            f"""DELETE FROM preferences
            WHERE task_type = "seasonal" AND task = {task_name}"""
        )
        con.commit()
    return redirect(url_for("tasks"))

@app.route("/prefs", methods=["GET", "POST"])
def prefs():
    with sqlite3.connect(db) as con:
        # if the request is post, modify the preferences
        cur = con.cursor()
        if request.method == 'POST':
            for pref_id, value in request.form.items():
                cur.execute(f"UPDATE preferences SET preference = {value} WHERE id = {pref_id}")
            con.commit()

        people = pd.read_sql(con=con, sql = f"SELECT * FROM people")
        people = people.rename(columns = {'id': 'person_id'})
        prefs = pd.read_sql(con=con, sql = f"SELECT * FROM preferences")
        prefs = prefs.merge(people[['person_id','first_name']], on = 'person_id')
        prefs = prefs.sort_values(['task','first_name']).set_index(['task','first_name'])

    return render_template("prefs.html", prefs = prefs)

@app.route("/requests/<int:person_id>", methods=["GET", "POST"])
def requests(person_id):
    with sqlite3.connect(db) as con:
        # get people and chore requests
        person = pd.read_sql(
            con = con,
            sql = f"SELECT * FROM people WHERE id = {person_id}"
        ).squeeze()
        # get the date of the monday, the following week
        today = date.today()
        days_to_add = 7 - today.weekday()
        date_week_starts = today + timedelta(days = days_to_add)
        date_week_starts = date_week_starts.strftime('%m/%d/%Y')

        # if method is POST, modify the requests
        if request.method == "POST":
            if "reset_intown" in request.form:
                intown = 0
            else:
                intown = int(''.join(
                    '1' if f"intown_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_am" in request.form:
                am = 0
            else:
                am = int(''.join(
                    '1' if f"am_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_pm" in request.form:
                pm = 0
            else:
                pm = int(''.join(
                    '1' if f"pm_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_cook" in request.form:
                cook = 0
            else:
                cook = int(''.join(
                    '1' if f"meal_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_sous" in request.form:
                sous = 0
            else:
                sous = int(''.join(
                    '1' if f"sous_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_clean" in request.form:
                clean = 0
            else:
                clean = int(''.join(
                    '1' if f"cleanup_{b}" in request.form else '0'
                    for b in range(7)), 2)
            if "reset_sweep" in request.form:
                sweep = 0
            else:
                sweep = int(''.join(
                    '1' if f"sweep_{b}" in request.form else '0'
                    for b in range(7)), 2)
            cur = con.cursor()
            cur.execute(
                f"""UPDATE requests SET
                days_in_town = {intown},
                dishes_am = {am},
                dishes_pm = {pm},
                cook_meal = {cook},
                sous_chef = {sous},
                meal_cleanup = {clean},
                night_sweep = {sweep}
                WHERE person_id = {person_id}"""
            )
            con.commit()
        # get the requests original or modified
        requests = pd.read_sql(
            con = con,
            sql = f"SELECT * FROM requests WHERE person_id = {person_id}"
        )

        # make bit lists from each integer attribute
        for col in requests.columns:
            if "id" in col: continue
            requests[col] = requests[col].apply(int_to_bits)
        requests = requests.squeeze()
        return render_template("requests.html", person_id = person_id,
                               date = date_week_starts, person = person,
                               requests = requests)

@app.route("/assignments")
def current_assignment():
    with sqlite3.connect(db) as con:
        mondays = pd.read_sql(
            con=con, sql="SELECT DISTINCT week_start_date FROM assignments"
        ).week_start_date.values
    return render_template("assignments.html", mondays=mondays)

@app.route("/assign-chores")
def make_chore_chart():
    monday = assign_chores.assign_chores()
    return redirect(url_for("display_assignment", monday = monday))

@app.route("/assignment/<monday>")
def display_assignment(monday):
    with sqlite3.connect(db) as con:
        people = pd.read_sql(con=con, sql="SELECT * FROM people").set_index('id')
        daily = pd.read_sql(con=con, sql="SELECT * FROM daily_tasks").set_index('id')
        weekly = pd.read_sql(con=con, sql="SELECT * FROM weekly_tasks").set_index('id')
        seasonal = pd.read_sql(con=con, sql="SELECT * FROM seasonal_tasks").set_index('id')
        occasional = pd.read_sql(con=con, sql="SELECT * FROM occasional_tasks").set_index('id')
        assign = pd.read_sql(con=con, sql="SELECT * FROM assignments").query(f'week_start_date == "{monday}"')
        assign_timed = pd.read_sql(con=con, sql="SELECT * FROM assignments_timed").query(f'week_start_date == "{monday}"')
        hours = pd.read_sql(con=con, sql="SELECT * FROM hours").query(f'week_start_date == "{monday}"').set_index('person_id')
    people['hours'] = hours.target_hours - hours.leftover_hours
    # construct the dict of assignments with names as keys
    people_ids = pd.concat((assign.person_id, assign_timed.person_id)).unique()
    chores = {}
    hours = {} # total number of hours
    for person_id in people_ids:
        person_name = ' '.join((
            people.loc[person_id, 'first_name'], people.loc[person_id, 'last_name']
        ))
        hours[person_name] = people.loc[person_id, 'hours']
        rows = []
        for _, chore in assign_timed.query(f'person_id == {person_id}').sort_values('weekday').iterrows():
            task = daily.loc[chore.task_id]
            ts = pd.Timestamp(chore.week_start_date) + pd.Timedelta(days = chore.weekday)
            rows.append({
                'task': task.task,
                'duration_hours': task.duration_hours,
                'weekday': ts.strftime("%A")
            })
        for _, chore in assign.query(f'person_id == {person_id}').iterrows():
            task = eval(f'{chore.task_type}.loc[{chore.task_id}]')
            rows.append({
                'task': task.task,
                'duration_hours': task.duration_hours,
                'weekday': ''
            })
        chores[person_name] = pd.DataFrame(rows)
    return render_template("assignment.html", monday=monday, chores=chores, hours=hours)

if __name__ == '__main__':
    app.run(debug = True)
