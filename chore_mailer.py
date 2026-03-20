import pandas as pd
import os
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
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
        self.service = build("gmail", "v1", credentials = creds)

    def compose_message(self, chores):
        message = '''
<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
</head>
<body style="font-family: sans-serif;">
  <table>
  <tr>
    <th>Chore</th>
    <th>Hours</th>
    <th>Day</th>
  </tr>'''
        for _, chore in chores.iterrows():
            message += f'''
  <tr>
    <td>{chore.task.replace(' Lead', '').replace(' Helper', '')}</td>
    <td>{chore.duration_hours}</td>
    <td>{chore.weekday}</td>
  </tr>'''
        message += f'''
  <tr>
    <td>Total hours:</td>
    <td>{chores.duration_hours.sum()}</td>
  </tr>
</table>
</body>
</html>'''
        return message
        
    def send_chores_to(self, person, chores):
        message = EmailMessage()
        message.set_content(f'Dear {person.first_name}!\n')
        message.add_alternative(self.compose_message(chores), subtype = 'html')
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
