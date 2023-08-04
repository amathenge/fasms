from flask import Flask, url_for, render_template, request, session, g, redirect
from database import get_db, hashpass, onetime, otp_ontime, log
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

# send all SMS based on fawaheader->id and mark fawaheader->processed as true.
@app.route('/sendallsms/<sid>', methods=['GET','POST'])
def sendallsms(sid):
    # check if logged in, then continue.
    if 'user' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    cur = db.cursor()
    sql = 'select id, statementday, statementmonth, statementyear, processed from fawaheader where id = ?'
    cur.execute(sql, [sid])
    data = cur.fetchone()
    if data['processed'] != 0:
        # already processed.
        return render_template('smsresult.html', sid=data['id'], message='Already Processed')
    
    # update fawaheader->processed = true
    sql = 'update fawaheader set processed = true where id = ?'
    cur.execute(sql, [sid])
    db.commit()

    # send the statements for fawaheader->id == sid
    statementid = data['id']
    statementdate = buildDateString(data['statementday'], data['statementmonth'], data['statementyear'])
    sql = '''
        select id, statementid, memberno, membername, totaldeposit, monthlydeposit, totalloan_principal, totalloanpaid,
        outstandingloan, loanrepayment, guaranteed, phone
        from fawastatement
        where statementid = ?
    '''
    cur.execute(sql, [sid])
    data = cur.fetchall()
    smsdate = datetime.now()
    smscount = 0
    for row in data:
        sms = 'FAWA Statement\n'
        sms += f'Statement Date: {statementdate}\n'
        sms += f"Full Name: {row['membername']}\n"
        sms += "Total Deposit: {:,.2f}\n".format(float(row['totaldeposit']))
        sms += "Monthly Deposit: {:,.2f}\n".format(float(row['monthlydeposit']))
        if row['totalloan_principal'] is not None:
            if float(row['totalloan_principal']) > 0:
                sms += "Total Loan: {:,.2f}\n".format(float(row['totalloan_principal']))
            if row['outstandingloan'] is not None:
                if float(row['outstandingloan']) > 0:
                    sms += "Outstanding Loan: {:,.2f}\n".format(float(row['outstandingloan']))
            if row['loanrepayment'] is not None:
                if float(row['loanrepayment']) > 0:
                    sms += "Monthly Repayment: {:,.2f}\n".format(float(row['loanrepayment']))
        if row['guaranteed'] is not None:
            if float(row['guaranteed']) > 0:
                sms += "Amount Guaranteed to others: {:,.2f}\n".format(float(row['guaranteed']))
        sms += f"Phone: {row['phone']}\n"
        sms += "Thank you for saving with FAWA"

        sql = 'insert into smslog (smsdate, statementid, memberno, phone, sms) values (?, ?, ?, ?, ?)'
        cur.execute(sql, [smsdate, sid, row['memberno'], row['phone'], sms])
        db.commit()
        lastinsertid = cur.lastrowid
        # now send the SMS.
        smsresult = sendSMS(sms, ['254759614127'])
        sql = 'update smslog set smsresult = ? where id = ?'
        cur.execute(sql, [smsresult, lastinsertid])
        db.commit()
        smscount += 1

    return render_template('smsresult.html', sid=sid, message=f"{smscount} messages sent")


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

# send a single SMS statement.
@app.route('/sendonesms/<uid>', methods=['GET', 'POST'])
def sendonesms(uid):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    return render_template('under_construction.html', page="Send SMS")

# generic form for sending an SMS
@app.route('/sendgenericsms', methods=['GET', 'POST'])
def sendgenericsms():
    if 'user' not in session:
        return redirect(url_for('login'))

    # use member table for recipients.
    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, memberno, firstname, surname, phone from member
    '''
    cur.execute(sql)
    data = cur.fetchall()

    message = None
    recipientsdata = None
    if request.method == "POST":
        # get list of members to send message to. From the form, a list of ID's
        recipientslist = request.form.getlist('recipientlist')
        recipientslist2 = [int(x) for x in recipientslist]
        # the following line fixed and issue with the tuple when there's only one item (1,)
        # the SQL command does not like this, so for all I append -1 to the end of the list
        # there are no members with that ID
        recipientslist2.append(-1)
        recipientslist = tuple(recipientslist2)
        sql = f'select id, memberno, firstname, surname, phone from member where id in {format(recipientslist)}'
        cur.execute(sql)
        recipientsdata = cur.fetchall()

    return render_template('genericsms_form.html', members=data, recipients=recipientsdata)

@app.route('/reviewstatements/<sid>', methods=['GET', 'POST'])
def reviewstatements(sid):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    cur = db.cursor()
    sql = 'select id, statementday, statementmonth, statementyear, processed from fawaheader where id = ?'
    cur.execute(sql, [sid])
    data = cur.fetchone()
    if data is None:
        return redirect(request.referrer)
    
    statementdate = buildDateString(data['statementday'], data['statementmonth'], data['statementyear'])
    header = {
        'id': data['id'],
        'statementdate': statementdate,
        'processed': data['processed']
    }
    sql = '''
        select id, statementid, memberno, membername, totaldeposit, monthlydeposit, totalloan_principal,
        totalloanpaid, outstandingloan, loanrepayment, guaranteed, loanroom_noguarantee, loanroom_guarantee,
        phone from fawastatement where statementid = ?
    '''
    cur.execute(sql, [sid])
    data = cur.fetchall()
    if data is None:
        return redirect(request.referrer)
    
    return render_template('reviewstatements.html', header=header, statements=data)

# md = message date (date that the SMS was sent)
@app.route('/showsmslogbyid/<sid>', methods=['GET', 'POST'])
def showsmslogbyid(sid):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # md = messagedate
    # table = smslog
    db = get_db()
    cur = db.cursor()
    sql = 'select statementid from smslog where statementid = ?'
    cur.execute(sql, [sid])
    data = cur.fetchone()
    if data is None:
        return redirect(request.referrer)
    
    sql = 'select statementday, statementmonth, statementyear from fawaheader where id = ?'
    cur.execute(sql, [data['statementid']])
    data = cur.fetchone()
    if data is None:
        return redirect(request.referrer)
    
    statementdate = buildDateString(data['statementday'], data['statementmonth'], data['statementyear'])

    sql = 'select sms, smsresult from smslog where statementid = ?'
    cur.execute(sql, [sid])
    data = cur.fetchall()
    if data is None:
        return redirect(request.referrer)
    

    return render_template('smslog.html', log=data, statementdate=statementdate)