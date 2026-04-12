import pandas as pd
import os
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from email.utils import formataddr
import base64

class ChoreMailer:
    def __init__(self, people, monday, assignments):
        SCOPES = ['https://www.googleapis.com/auth/gmail.send']
        self.sender = '251manorcircle@gmail.com'
        self.people = people
        self.monday = monday
        self.assignments = assignments
        creds = Credentials.from_authorized_user_file('secret/token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # Automatic refresh using the refresh_token
                creds.refresh(Request())
            else:
                raise ValueError('Need to manually reauthenticate')
        self.service = build("gmail", "v1", credentials = creds)

    def compose_message(self, person, chores):
        message = f'''
<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
</head>
<body style="font-family: sans-serif;">
  <h3>Dear {person.first_name}:<h3>
  <h4>Here are your chores for the week starting on {self.monday}</h4>
  <table style="border-collapse: collapse; border: solid 1px #cccccc;">
  <tr>
    <th style="border: 1px solid black;">Chore</th>
    <th style="border: 1px solid black;">Hours</th>
    <th style="border: 1px solid black;">Day</th>
  </tr>'''
        for _, chore in chores.iterrows():
            message += f'''
  <tr>
    <td style="border: 1px solid black;">{chore.task.replace(' Lead', '').replace(' Helper', '')}</td>
    <td style="border: 1px solid black;">{chore.duration_hours}</td>
    <td style="border: 1px solid black;">{chore.weekday}</td>
  </tr>'''
        message += f'''
  <tr>
    <td style="border: 1px solid black;">Total hours:</td>
    <td style="border: 1px solid black;">{chores.duration_hours.sum()}</td>
  </tr>
</table>

<h4>The chore chart can be found <a href="https://docs.google.com/spreadsheets/d/1hKq59QTjSGwQ_KJCQYrmaIxy9SgYx_-8ehbzG0gWHHg">here</a></h4>
</body>
</html>'''
        return message
        
    def send_chores_to(self, person, chores):
        message = EmailMessage()
        message.set_content(f'Dear {person.first_name}!\n')
        message.add_alternative(self.compose_message(person, chores), subtype = 'html')
        message['From'] = formataddr(('Maitri Chore Manager', self.sender))
        message['To'] = formataddr((person.first_name, person.email))
        message['Subject'] = f'Your chores for the week starting on {self.monday}'
        message = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
        return self.service.users().messages().send(userId = 'me', body = message).execute()

    def mail_chores(self):
        for name, chores in self.assignments.items():
            # find the person
            person = self.people.query(f'first_name == "{name}"')
            if person.empty:
                message = "Could not find " + name
                raise ValueError(message)
            if len(person) > 1:
                message = "More than one person with first name ", name
                raise ValueError(message)
            person = person.squeeze()
            self.send_chores_to(person, chores)
