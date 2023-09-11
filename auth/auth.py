from flask import Blueprint, render_template, redirect, g, request, session, url_for
from datetime import datetime
import os
from database import get_db, hashpass, checkpass, otp_ontime, log, onetime
from sms import sendSMS
from sendEmail import send_otp_email
from werkzeug.security import generate_password_hash

auth = Blueprint("auth", __name__, static_folder="static", template_folder="templates")

@auth.route('/', methods=['GET', 'POST'])
def login():
    # if user is already logged in, then handle that here. Redirect to home page
    if 'user' in session and session['user']['otp']:
        return redirect(url_for('home'))
    
    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    message = None
    # process POST
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # open onetime.db->users and check email/password combination
        db = get_db()
        sql = '''
            select id, firstname, lastname, email, password, phone, auth, passauth, tfaauth, locked, lastlogin from users
            where email = ?
        '''
        cur = db.cursor()
        cur.execute(sql, [email])
        data = cur.fetchone()
        if data is None:
            # nothing returned from database, so send back to the login page.
            message = 'Invalid user or password'
            return render_template('auth/login.html', message=message)
        elif data['locked']:
            # this user is locked.
            message = 'Account locked.'
            log(f"Login attempt, locked={data['email']}")
            return render_template('auth/login.html', message=message)
        else:
            pwd_hash = generate_password_hash(data['password'])
            if checkpass(pwd_hash, data['password']):
                # get user information, save to session = password was correct.
                auth = tuple([int(x) for x in data['auth']])
                user = {
                    'id': data['id'],
                    'firstname': data['firstname'],
                    'lastname': data['lastname'],
                    'email': data['email'],
                    'phone': data['phone'],
                    'passauth': data['passauth'],
                    'tfaauth': data['tfaauth'],
                    'auth': auth,
                    'locked': data['locked'],
                    'lastlogin': data['lastlogin'],
                    'otp': None
                }
                session['user'] = user
                session.modified = True
                # if 2FA is enabled for this user, send OTP to SMS and email
                if user['tfaauth']:
                    # on successful password, send a PIN to the phone number.
                    otp = onetime()
                    # invalidate existing tokens
                    sql = 'update otp set valid = 0 where userid = ?'
                    cur.execute(sql, [user['id']])
                    db.commit()
                    # get current date/time for authentication
                    now = datetime.now()
                    # insert otp into database
                    sql = 'insert into otp (userid, otp, otp_time, valid) values (?, ?, ?, ?)'
                    cur.execute(sql, [user['id'], otp, now, 1])
                    db.commit()
                    # send OTP to user phone + email.
                    message = f"Your OTP to login to the application is {otp}"
                    sendSMS(message, user['phone'])
                    send_otp_email(message, user['email'])
                    # log(f"OTP sent to {user['phone']} and {user['email']}")
                    return render_template('auth/otp.html')
                    # return redirect(url_for('check_otp'))
                else:
                    userid = session['user']['id']
                    now = datetime.now()
                    sql = 'update users set lastlogin = ? where id = ?'
                    cur.execute(sql, [now, userid])
                    db.commit()
                    session['user']['otp'] = '000000'
                    session.modified = True
                    log(f'Login successful for user id={userid} at {now_string}')
                    return redirect(url_for('home'))
            else:
                message = 'Invalid user or password'
                return render_template('auth/login.html', message=message)
        
    return render_template('auth/login.html', message=message)

# this method will check the OTP sent to the user via email and SMS
@auth.route('/auth/check_otp', methods=['GET', 'POST'])
def check_otp():
    # no need to check for OTP if the user is already logged in
    if 'user' in session and session['user']['otp']:
        return redirect(url_for('home'))

    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    # define a default return message
    message = "Invalid Data"
    if request.method == 'POST':
        otp = request.form['otp']
        userid = session['user']['id']
        now = datetime.now()
        # get OTP saved in database.
        db = get_db()
        cur = db.cursor()
        sql = 'select id, userid, userid, otp, otp_time, valid from otp where userid = ? and otp = ? and valid = 1'
        cur.execute(sql, [userid, otp])
        data = cur.fetchone()
        if data is None:
            # if nothing is returned from the database, wrong OTP. Go back to login page.
            log(f"OTP fail user={session['user']['email']}")
            message = "Invalid OTP - try again"
        else:
            # OTP was correct for this user, and is valid. Check time returned.
            if otp_ontime(data['otp_time'], now, 2):
                # response time is OK. Update login time and show the home page
                db = get_db()
                cur = db.cursor()
                sql = 'update users set lastlogin = ? where id = ?'
                cur.execute(sql, [now, userid])
                db.commit()
                log(f"OTP Success user={session['user']['email']}")
                session['user']['otp'] = otp
                session['modified'] = True
                userid = session['user']['id']
                log(f"OTP successful for user id={userid} at {now_string}")
                return redirect(url_for('home'))
            else:
                log(f"OTP timeout user={session['user']['email']}")
                message = 'Timeout... try again'

    return render_template('auth/login.html', message=message)

# logout from system. 
@auth.route('/auth/logout', methods=['GET', 'POST'])
def logout():
    now = datetime.now()
    now_string = now.strftime('%d%b%Y_%H:%M:%S').upper()
    # clear session information and send user to the login page.
    if 'user' in session:
        userid = session['user']['id']
        log(f"user id={userid} logged out at: {now_string}")
        del session['user']
    return redirect(url_for('auth.login'))
