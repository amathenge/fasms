from flask import Flask, url_for, render_template, request, session, g, redirect
from database import get_db, hashpass, onetime, otp_ontime
from datetime import datetime
from sendEmail import send_otp_email
from sms import sendSMS
import os
from werkzeug.utils import secure_filename
from fawa import importdata, buildDateString
import cred

app = Flask(__name__)
# required when you use sessions.
app.config['SECRET_KEY'] = os.urandom(24)
# facility to upload files - the upload_folder is relative to the home of the application.
upload_folder = 'files'
app.config['UPLOAD_FOLDER'] = upload_folder
# max file size to upload is 10 MB
app.config['MAX_CONTENT_PATH'] = 10 * 1024 * 1024
# allowed extensions (only Excel files)
ALLOWED_EXTENSIONS = set(['xlsx', 'xlsm', 'xls'])

# import helper templates (e.g., chang  e '\n' to '<br>'...)
from access import *

# close db
@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'fawa_db'):
        g.fawa_db.close()


# file upload helpers
# check if the file being uploaded is one of the allowed extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/', methods=['GET', 'POST'])
def login():
    # if user is already logged in, then handle that here. Redirect to home page
    if 'user' in session:
        return redirect(url_for('home'))
    
    message = None
    # process POST
    if request.method == 'POST':
        email = request.form['email']
        password = hashpass(request.form['password'])
        # open onetime.db->users and check email/password combination
        db = get_db()
        sql = '''
            select id, firstname, lastname, email, password, phone, auth, locked from users
            where email = ? and password = ?
        '''
        cur = db.cursor()
        cur.execute(sql, [email, password])
        data = cur.fetchone()
        if data is None:
            # nothing returned from database, so send back to the login page.
            message = 'Invalid user or password'
            return render_template('login.html', message=message)
        elif data['locked']:
            # this user is locked.
            message = 'Account locked.'
            return render_template('login.html', message=message)
        else:
            # get user information, save to session
            auth = tuple([int(x) for x in data['auth']])
            user = {
                'id': data['id'],
                'firstname': data['firstname'],
                'lastname': data['lastname'],
                'email': data['email'],
                'phone': data['phone'],
                'auth': auth,
                'locked': data['locked']
            }
            session['user'] = user

            # DEBUG CODE - REMOVE THE LINE BELOW TO GET OTP AUTH
            return redirect(url_for('home'))
            # END OF DEBUG
            
            # on successful password, send a PIN to the phone number.
            otp = onetime()
            # invalidate existing tokens
            sql = 'update otp set valid = false where userid = ?'
            cur.execute(sql, [user['id']])
            db.commit()
            # get current date/time for authentication
            now = datetime.now()
            # insert otp into database
            sql = 'insert into otp (userid, otp, otp_time, valid) values (?, ?, ?, ?)'
            cur.execute(sql, [user['id'], otp, now, True])
            db.commit()
            # send OTP to user phone + email.
            message = f"Your OTP to login to the application is {otp}"
            sendSMS(message, user['phone'])
            send_otp_email(message, user['email'])
            return render_template('otp.html')
        
    return render_template('login.html', message=message)

# this method will check the OTP sent to the user via email and SMS
@app.route('/check_otp', methods=['GET', 'POST'])
def check_otp():
    # no need to check for OTP if the user is already logged in
    if 'user' in session:
        return redirect(url_for('home'))
    
    # define a default return message
    message = "Invalid Data"
    if request.method == 'POST':
        otp = request.form['otp']
        userid = session['user']['id']
        now = datetime.now()
        # get OTP saved in database.
        db = get_db()
        cur = db.cursor()
        sql = 'select id, userid, userid, otp, otp_time, valid from otp where userid = ? and otp = ? and valid = true'
        cur.execute(sql, [userid, otp])
        data = cur.fetchone()
        if data is None:
            # if nothing is returned from the database, wrong OTP. Go back to login page.
            message = "Invalid OTP - try again"
        else:
            # OTP was correct for this user, and is valid. Check time returned.
            if otp_ontime(data['otp_time'], now, 2):
                # response time is OK. Show the home page
                return redirect(url_for('home'))
            else:
                message = 'Timeout... try again'

    return render_template('login.html', message=message)

@app.route('/home', methods=['GET', 'POST'])
def home():
    # check if logged in, then continue.
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # user is logged in, now just send a stub page.
    return render_template('home.html')


@app.route('/fawastatements', methods=['GET', 'POST'])
def fawastatements():
    # check if logged in, then continue.
    if 'user' not in session:
        return redirect(url_for('login'))
    
    return render_template('fawastatements.html')

@app.route('/sendsms', methods=['GET','POST'])
def sendsms():
    # check if logged in, then continue.
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # user is logged in, now just send a stub page.
    return render_template('under_construction.html', page='Send SMS')

@app.route('/payroll', methods=['GET', 'POST'])
def payroll():
    # check if logged in, then continue.
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # user is logged in, now just send a stub page.
    return render_template('under_construction.html', page='Payroll')

# logout from system. 
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    # clear session information and send user to the login page.
    if 'user' in session:
        del session['user']
    return redirect(url_for('login'))

# upload a file
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if 'callform' in request.form:
        return render_template('upload.html', message=None)
    
    message = None
    if request.method == "POST":
        # get the file
        if 'file' in request.files:
            file = request.files['file']
        else:
            file = None
            message = "Invalid filename"
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            db = get_db()
            sql = 'select distinct filename from uploads where lower(filename) = ?'
            cur = db.cursor()
            cur.execute(sql, [filename.lower()])
            data = cur.fetchone()
            if data is None:
                sql = 'insert into uploads (filename) values (?)'
                cur.execute(sql, [filename])
                db.commit()
                fileid = cur.lastrowid
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                message = "File uploaded"
                # import data from the file (xlsx) into the database.
                result = importdata(fileid, os.path.join(app.config['UPLOAD_FOLDER'], filename))
                if result is None:
                    message += ' - DATA NOT IMPORTED'
                else:
                    message += f' DATA IMPORTED {result} rows'
            else:
                # file has already been uploaded.
                message = f"File <b><u>{data['filename']}</u></b> exists - uploaded previously."
    # not in post mode - show the upload form
    return render_template('upload.html', message=message)

@app.route('/checkstatements', methods=['GET', 'POST'])
def checkstatements():
    if 'user' not in session:
        return redirect(url_for('login'))

    # show table of all statements in the database.
    db = get_db()
    cur = db.cursor()
    sql = 'select id, fileid, statementday, statementmonth, statementyear, processed from fawaheader'
    cur.execute(sql)    
    data = cur.fetchall()
    statements = []
    for row in data:
        statements.append({
            'id': row['id'],
            'fileid': row['fileid'],
            'statementdate': buildDateString(row['statementday'], row['statementmonth'], row['statementyear']),
            'processed': row['processed']
        })
    return render_template('checkstatements.html', statements=statements)

@app.route('/managefiles', methods=['GET', 'POST'])
def managefiles():
    if 'user' not in session:
        return redirect(url_for('login'))
    

    # user is logged in, now just send a stub page.
    return render_template('under_construction.html', page='Manage Files')
