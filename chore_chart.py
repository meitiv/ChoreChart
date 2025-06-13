#!/usr/bin/env python3

from flask import Flask, redirect, request
from flask import render_template
from flask import url_for
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, timedelta

app = Flask(__name__)
db = "maitri_chores.db"

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

@app.route("/prefs/<int:person_id>", methods=["GET", "POST"])
def prefs(person_id):
    with sqlite3.connect(db) as con:
        person = pd.read_sql(
            con = con,
            sql = f"SELECT * FROM people WHERE id = {person_id}"
        ).squeeze()
        # get the original preferences
        prefs = pd.read_sql(
            con = con,
            sql = f"SELECT * FROM preferences WHERE person_id = {person_id}"
        )
        # if the request is post, modify the preferences
        cur = con.cursor()
        if request.method == 'POST':
            for pref_id, new_pref_value in request.form.items():
                # only if the old_pref_value is different, change it
                row = prefs.query(f'id == {pref_id}').squeeze()
                old_pref_value = int(row.preference)
                new_pref_value = int(new_pref_value)
                idx = row.name
                if old_pref_value != new_pref_value:
                    prefs.loc[idx,'preference'] = new_pref_value
                    cur.execute(
                        f"""UPDATE preferences SET
                        preference = {new_pref_value}
                        WHERE id = {pref_id}"""
                    )
            con.commit()
        
    return render_template("prefs.html", person_id = person_id,
                           person = person, prefs = prefs)

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
            intown = int(''.join(
                '1' if f"intown_{b}" in request.form else '0'
                for b in range(7)), 2)
            am = int(''.join(
                '1' if f"am_{b}" in request.form else '0'
                for b in range(7)), 2)
            pm = int(''.join(
                '1' if f"pm_{b}" in request.form else '0'
                for b in range(7)), 2)
            cook = int(''.join(
                '1' if f"meal_{b}" in request.form else '0'
                for b in range(7)), 2)
            clean = int(''.join(
                '1' if f"cleanup_{b}" in request.form else '0'
                for b in range(7)), 2)
            cur = con.cursor()
            cur.execute(
                f"""UPDATE requests SET
                days_in_town = {intown},
                dishes_am = {am},
                dishes_pm = {pm},
                cook_meal = {cook},
                meal_cleanup = {clean}
                WHERE person_id = {person_id}"""
            )
            con.commit()
        # get the requests oroginal or modified
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

if __name__ == '__main__':
    app.run(debug = True)
