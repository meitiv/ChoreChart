#!/usr/bin/env python3
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from email.utils import formataddr
import base64
from datetime import date, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
sender = '251manorcircle@gmail.com'
creds = Credentials.from_authorized_user_file('secret/token.json', SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        # Automatic refresh using the refresh_token
        creds.refresh(Request())
    else:
        raise ValueError('Need to manually reauthenticate')
    
service = build("gmail", "v1", credentials = creds)
monday = date.today() + timedelta(days = 7 - date.today().weekday())
saturday = monday - timedelta(days = 2)
content = f'''
<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
</head>
<body style="font-family: sans-serif;">
<p>Hi Folks,</p>

<p>I will be working on the next week's chore chart on Sunday.<br>
Please send me by midnight Saturday, {saturday}:
</p>
<ol>
<li>What days will you be in town?</li>
<li>When are you available to cook a meal?</li>
<li>When are you available for meal cleanup?</li>
<li>When can you unload the dishwasher?</li>
</ol>

<p>If I don't hear from you, I will assume that:</p>
<ol>
<li>You will be here all week</li>
<li>You do not want to cook a meal</li>
<li>You do not have any restrictions on cleanup/dishes schedule</li>
</ol>
<p>
Warmly,<br>
Sasha
</p>
</body>
</html>
'''

message = EmailMessage()
message.set_content('')
message.add_alternative(content, subtype = 'html')
message['From'] = formataddr(('Maitri Chore Manager', sender))
message['To'] = formataddr(('Maitri House', 'maitrihouse@eml.cc'))
message['Subject'] = f'Chore requests for the week starting on {monday}'
message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
service.users().messages().send(userId = 'me', body = message).execute()
