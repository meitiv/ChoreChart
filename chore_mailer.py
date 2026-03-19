import pandas as pd
import mailtrap as mt
import dotenv
import os
    
class ChoreMailer:
    def __init__(self, people, monday):
        if not dotenv.load_dotenv():
            raise ValueError("Could not load .env")
        self.sender = '251manorcircle@gmail.com'
        token = os.environ.get('mailtrap_token')
        if not token:
            raise ValueError("Cound not get Mailtrap token")
        self.people = people
        self.monday = monday
        self.server = mt.MailtrapClient(token)

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
        message += '''
  <tr>
    <td>Total hours:</td>
    <td>{chores.duration_hours.sum()}</td>
  </tr>
</table>
</body>
</html>'''
        return message
        
    def send_chores_to(self, person, chores):
        message = mt.Mail(
            sender = mt.Address(email = '251manorcircle@gmail', name = 'Maitri Chores'),
            to = [mt.Address(email = person.email, name = f'{person.first_name} {person.last_name}')],
            subject = f'Your chores for week starting {self.monday}',
            html = self.compose_message(chores)
        )
        return self.server.send(message)

    def mail_chores(self, assignments: dict):
        for name, chores in assignments.items():
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
