from flask import Flask, url_for, render_template, request, session, g, redirect
from auth.auth import auth
from payroll.payroll import payroll
from fawa.fawa import fawa
from database import get_db, hashpass, onetime, otp_ontime, log, allowed_file
from datetime import datetime
from sendEmail import send_otp_email
from sms import sendSMS
import os
from fawa.fawautils import importdata, buildDateString
from payroll.payimport import importpaydata, printSlip
import cred

app = Flask(__name__)
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(payroll, url_prefix="/payroll")
app.register_blueprint(fawa, url_prefix="/fawa")

# required when you use sessions.
app.config['SECRET_KEY'] = os.urandom(24)
# facility to upload files - the upload_folder is relative to the home of the application.
upload_folder = 'files'
app.config['UPLOAD_FOLDER'] = upload_folder
# max file size to upload is 10 MB
app.config['MAX_CONTENT_PATH'] = 10 * 1024 * 1024

# import helper templates (e.g., chang  e '\n' to '<br>'...)
from access import *

# FAWA processes.

# close db
@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'fawa_db'):
        g.fawa_db.close()

# this route redirects to the auth login route.
@app.route('/', methods=['GET', 'POST'])
def auth_login():
    return redirect(url_for('auth.login'))

@app.route('/home', methods=['GET', 'POST'])
def home():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))
    
    # user is logged in, now just send a stub page.
    return render_template('home.html')

# send HR SMS
@app.route('/sendhrsms/<uid>', methods=['GET', 'POST'])
def sendhrsms(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    user = session['user']
    # only admin=1 and sms=4 should use this page.
    auth = (1, 4)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('under_construction.html', page="Send HR SMS")

@app.route('/usermgmt', methods=['GET', 'POST'])
def usermgmt():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))
    
    # check if authorized to be here.
    user = session['user']
    # only admin=1 and usermgr=2 should do user management.
    auth = (1, 2)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # collect user data from fawa.db->users and display the form.
    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, firstname, lastname, email, phone, email, phone, auth, lastlogin
        from users
    '''
    cur.execute(sql)
    data = cur.fetchall()
    # data returns 'auth' as a string. need to convert to a tuple() for this form
    # to display them properly.
    contacts = []
    temp = {}
    for item in data:
        temp = dict(item)
        temp['auth'] = tuple([int(x) for x in temp['auth']])
        contacts.append(temp)

    # log(f"usrmgr = {contacts}")
    
    return render_template('usermgmt.html', contacts=contacts)

@app.route('/edituser/<uid>', methods=['GET', 'POST'])
def edituser(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))
    
    user = session['user']
    auth = (1,2)

    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # for now, user cannot add/remove their own privileges.
    if user['id'] == uid:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    if request.method == 'POST':
        if request.form['submit'] == 'cancel':
            return redirect(url_for('usermgmt'))
        
        firstname = request.form['txtFirst']
        lastname = request.form['txtLast']
        email = request.form['txtEmail']
        auth = ''
        # auth = checkbox data. admin, usrmgr, fawa, sms, payroll, readonly
        authlist = request.form.getlist('chkauth')
        if 'admin' in authlist:
            auth += '1'
        if 'usrmgr' in authlist:
            auth += '2'
        if 'fawa' in authlist:
            auth += '3'
        if 'sms' in authlist:
            auth += '4'
        if 'payroll' in authlist:
            auth += '5'
        if 'readonly' in authlist:
            # if readonly has been flagged, remove all others, unless this is an admin then
            # don't change.
            if 'admin' not in authlist:
                auth = '6'
        authtype = request.form.getlist('authtype')
        passauth = 'passauth' in authtype
        tfaauth = 'tfaauth' in authtype
        locked = 'locked' in authtype
        # one of the authtypes must be there, or we lock the account
        if not passauth and not tfaauth:
            locked = 1
        password = request.form['txtPassword']
        if len(password) == 0:
            sql = 'update users set firstname = ?, lastname = ?, email = ?, auth = ?, passauth = ?, tfaauth = ?, locked = ? where id = ?'
            params = [firstname, lastname, email, auth, passauth, tfaauth, locked, uid]
        else:
            sql = 'update users set firstname = ?, lastname = ?, email = ?, auth = ?, passauth = ?, tfaauth = ?, locked = ?, password = ? where id = ?'
            params = [firstname, lastname, email, auth, passauth, tfaauth, locked, hashpass(password), uid]

        db = get_db()
        cur = db.cursor()
        cur.execute(sql, params)
        db.commit()
        return redirect(url_for('usermgmt'))

    db = get_db()
    cur = db.cursor()
    sql = 'select id, firstname, lastname, email, auth, passauth, tfaauth, locked from users where id = ?'
    cur.execute(sql, [uid])
    result = cur.fetchone()
    auth = tuple([int(x) for x in result['auth']])
    return render_template('edituser.html', contact=result, auth=auth)

@app.route('/deluser/<uid>')
def deluser(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))
    user = session['user']
    auth = (1,2)

    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
    # if 'user' not in session:
    #     return redirect(url_for('login'))
    # if 'admin' not in session:
    #     return redirect(request.referrer)


    # don't delete logged in user. -- should also probably not delete admin users...
    # but that can be fixed later.
    if int(uid) != int(user['id']):
        sql = 'delete from users where id = ?'
        db = get_db()
        cur = db.cursor()
        cur.execute(sql,[uid])
        db.commit()


    return redirect(url_for('usermgmt'))
