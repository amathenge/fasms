# utilities for sending SMS via Uwazii Mobile
import requests
import json
import cred
from datetime import datetime

# get some credentials and end-points from the cred.py file.

username = cred.uwazii_username
password = cred.uwazii_password
senderID = cred.uwazii_senderID

# function to get the authorization code from Uwazii.
# this needs username/password authentication
def getAuthorizationCode():
    url = cred.uwazii_auth_url
    payload = json.dumps({
        'username': username,
        'password': password
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', url, headers=headers, data=payload)
    data = json.loads(response.text)
    authorization_code = data['data']['authorization_code']
    return authorization_code

# function to get an Access Token from Uwazii
# this needs an authorization code
def getAccessToken():
    url = cred.uwazii_token_url
    payload = json.dumps({
        'authorization_code': getAuthorizationCode()
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', url, headers=headers, data=payload)
    data = json.loads(response.text)
    access_token = data['data']['access_token']
    return access_token

# function to send the SMS via Uwazii
# needs an access token
# msg = message to send
# recipients = list of recipients (254...)
def sendSMS(msg, recipients):
    url = cred.uwazii_send_url
    now = datetime.now()
    now_date = now.strftime('%Y-%m-%d')
    now_time = now.strftime('%H:%M')
    msg = {
        'number': recipients,
        'senderID': senderID,
        'text': msg,
        'type': 'sms',
        'beginDate': now_date,
        'beginTime': now_time,
        'lifetime': 86400,
        'delivery': False
    }
    payload = json.dumps([msg])
    headers = {
        'X-Access-Token': getAccessToken(),
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', url, headers=headers, data=payload)
    return response.text