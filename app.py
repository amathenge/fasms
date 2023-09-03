from flask import Flask, url_for, render_template, request, session, g, redirect, send_file
from database import get_db, hashpass, onetime, otp_ontime, log
from datetime import datetime
from sendEmail import send_otp_email
from sms import sendSMS
import os
from werkzeug.utils import secure_filename
from fawa import importdata, buildPayrollDate, buildDateString
from payimport import importpaydata, printSlip
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
    if 'user' in session and session['user']['otp']:
        return redirect(url_for('home'))
    
    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    message = None
    # process POST
    if request.method == 'POST':
        email = request.form['email']
        password = hashpass(request.form['password'])
        # open onetime.db->users and check email/password combination
        db = get_db()
        sql = '''
            select id, firstname, lastname, email, password, phone, auth, passauth, tfaauth, locked, lastlogin from users
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
            log(f"Login attempt, locked={data['email']}")
            return render_template('login.html', message=message)
        else:
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
            # DEBUG CODE - REMOVE THE LINES BELOW TO GET OTP AUTH
            #
            # userid = session['user']['id']
            # now = datetime.now()
            # sql = 'update users set lastlogin = ? where id = ?'
            # cur.execute(sql, [now, userid])
            # db.commit()
            # session['modified'] = True
            # session['user']['otp'] = '000000'
            # return redirect(url_for('home'))
            #
            # END OF DEBUG
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
                return render_template('otp.html')
                # return redirect(url_for('check_otp'))
            else:
                userid = session['user']['id']
                now = datetime.now()
                sql = 'update users set lastlogin = ? where id = ?'
                cur.execute(sql, [now, userid])
                db.commit()
                session.modified = True
                session['user']['otp'] = '000000'
                log(f'Login successful for user id={userid} at {now_string}')
                return redirect(url_for('home'))
        
    return render_template('login.html', message=message)

# this method will check the OTP sent to the user via email and SMS
@app.route('/check_otp', methods=['GET', 'POST'])
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
                session['modified'] = True
                session['user']['otp'] = otp
                userid = session['user']['id']
                log(f"OTP successful for user id={userid} at {now_string}")
                return redirect(url_for('home'))
            else:
                log(f"OTP timeout user={session['user']['email']}")
                message = 'Timeout... try again'

    return render_template('login.html', message=message)

@app.route('/home', methods=['GET', 'POST'])
def home():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))
    
    # user is logged in, now just send a stub page.
    return render_template('home.html')

@app.route('/fawastatements', methods=['GET', 'POST'])
def fawastatements():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('fawastatements.html')

# send all SMS based on fawaheader->id and mark fawaheader->processed as true.
@app.route('/sendallsms/<sid>', methods=['GET','POST'])
def sendallsms(sid):
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select id, statementday, statementmonth, statementyear, processed from fawaheader where id = ?'
    cur.execute(sql, [sid])
    data = cur.fetchone()
    if data['processed'] != 0:
        # already processed.
        return render_template('smsresult.html', sid=data['id'], message='Already Processed')
    
    # update fawaheader->processed = true
    sql = 'update fawaheader set processed = 1 where id = ?'
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
        smsrecipient = row['phone']
        smsresult = sendSMS(sms, [smsrecipient])
        # smsresult = sendSMS(sms, ['254759614127'])
        sql = 'update smslog set smsresult = ? where id = ?'
        cur.execute(sql, [smsresult, lastinsertid])
        db.commit()
        smscount += 1

    return render_template('smsresult.html', sid=sid, message=f"{smscount} messages sent")

# send an individual FAWA sms
@app.route('/sendfawasms/<uid>', methods=['GET', 'POST'])
def sendfawasms(uid):
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, statementid, memberno, membername, totaldeposit, monthlydeposit, totalloan_principal, totalloanpaid,
        outstandingloan, loanrepayment, guaranteed, phone
        from fawastatement
        where id = ?
    '''
    cur.execute(sql, [uid])
    data = cur.fetchone()
    if data is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    statementid = data['statementid']
    sql = 'select id, statementday, statementmonth, statementyear, processed from fawaheader where id = ?'
    cur.execute(sql, [statementid])
    data2 = cur.fetchone()
    if data2 is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
    statementdate = buildDateString(data2['statementday'], data2['statementmonth'], data2['statementyear'])
    # -------- BUILD THE SMS 
    sms = 'FAWA Statement\n'
    sms += f'Statement Date: {statementdate}\n'
    sms += f"Full Name: {data['membername']}\n"
    sms += "Total Deposit: {:,.2f}\n".format(float(data['totaldeposit']))
    sms += "Monthly Deposit: {:,.2f}\n".format(float(data['monthlydeposit']))
    if data['totalloan_principal'] is not None:
        if float(data['totalloan_principal']) > 0:
            sms += "Total Loan: {:,.2f}\n".format(float(data['totalloan_principal']))
        if data['outstandingloan'] is not None:
            if float(data['outstandingloan']) > 0:
                sms += "Outstanding Loan: {:,.2f}\n".format(float(data['outstandingloan']))
        if data['loanrepayment'] is not None:
            if float(data['loanrepayment']) > 0:
                sms += "Monthly Repayment: {:,.2f}\n".format(float(data['loanrepayment']))
    if data['guaranteed'] is not None:
        if float(data['guaranteed']) > 0:
            sms += "Amount Guaranteed to others: {:,.2f}\n".format(float(data['guaranteed']))
    sms += f"Phone: {data['phone']}\n"
    sms += "Thank you for saving with FAWA"
    # -------- END OF SMS BUILD

    smsdate = datetime.now()
    sql = 'insert into smslog (smsdate, statementid, memberno, phone, sms) values (?, ?, ?, ?, ?)'
    cur.execute(sql, [smsdate, statementid, data['memberno'], data['phone'], sms])
    db.commit()
    lastinsertid = cur.lastrowid
    # now send the SMS.
    smsrecipient = data['phone']
    smsresult = sendSMS(sms, [smsrecipient])
    # smsresult = sendSMS(sms, ['254759614127'])
    sql = 'update smslog set smsresult = ? where id = ?'
    cur.execute(sql, [smsresult, lastinsertid])
    db.commit()

    # display a page with the result of this SMS send.
    message = smsresult
    return render_template('fawasmsresult.html', message=message, sms=sms)

@app.route('/payroll', methods=['GET', 'POST'])
def payroll():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))
    
    # user is logged in - show payroll management options.
    return render_template('paystubs.html')

# payroll processing files. For sending payroll sms.
@app.route('/payupload', methods=['GET', 'POST'])
def payupload():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
    if 'callform' in request.form:
        return render_template('payupload.html', message=None)
    
    message = None
    if request.method == "POST":
        # get the file
        if 'file' in request.files:
            file = request.files['file']
        else:
            file = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            db = get_db()
            sql = 'select distinct filename from payuploads where filename = ?'
            cur = db.cursor()
            cur.execute(sql, [os.path.join(app.config['UPLOAD_FOLDER'],filename)])
            data = cur.fetchone()
            if data is None:
                sql = 'insert into payuploads (filename) values (?)'
                cur.execute(sql, [os.path.join(app.config['UPLOAD_FOLDER'], filename)])
                db.commit()
                fileid = cur.lastrowid
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                message = "File uploaded"
                log(f'/payupload - uploaded file id = {fileid} name = {filename}')
                # import data from the file (xlsx) into the database.
                result = importpaydata(fileid)
                if not result:
                    log('/payupload - nothing uploaded')
                    message += ' - DATA NOT IMPORTED'
                else:
                    log('/payupload - data uploaded')
                    message += f' DATA IMPORTED {result} rows'
            else:
                # file has already been uploaded.
                message = f"File <b><u>{data['filename']}</u></b> exists - uploaded previously."
    # not in post mode - show the upload form
    return render_template('payupload.html', message=message)   

# logout from system. 
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    now = datetime.now()
    now_string = now.strftime('%d%b%Y_%H:%M:%S').upper()
    # clear session information and send user to the login page.
    if 'user' in session:
        userid = session['user']['id']
        log(f"user id={userid} logged out at: {now_string}")
        del session['user']
    return redirect(url_for('login'))

# upload a file
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

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

@app.route('/fawafiledownload/<fid>', methods=['GET', 'POST'])
def fawafiledownload(fid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from uploads where id = ?'
    cur.execute(sql, [fid])
    data = cur.fetchone()
    if data is None:
        return redirect(url_for('managefiles'))
    
    filename = os.path.join(app.config['UPLOAD_FOLDER'], data['filename'])
    return send_file(filename, as_attachment=True)

@app.route('/fawafiledelete/<fid>', methods=['GET', 'POST'])
def fawafiledelete(fid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from uploads where id = ?'
    cur.execute(sql, [fid])
    data = cur.fetchone()
    if data is None:
        return redirect(url_for('managefiles'))
    
    filename = os.path.join(app.config['UPLOAD_FOLDER'], data['filename'])
    if os.path.exists(filename):
        os.remove(filename)
        sql = 'delete from uploads where id = ?'
        cur.execute(sql, [fid])
        db.commit()

    return redirect(url_for('managefiles'))

@app.route('/checkstatements', methods=['GET', 'POST'])
def checkstatements():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # show table of all statements in the database.
    db = get_db()
    cur = db.cursor()
    sql = '''
        select h.id, h.fileid, h.statementday, h.statementmonth, h.statementyear, h.processed,
        count(f.id) as rcount from fawaheader h left join fawastatement f
        on (h.id = f.statementid) group by h.id, h.fileid, h.statementday, h.statementmonth,
        h.statementyear, h.processed
    '''
    cur.execute(sql)    
    data = cur.fetchall()
    statements = []
    for row in data:
        statements.append({
            'id': row['id'],
            'fileid': row['fileid'],
            'recordcount': row['rcount'],
            'statementdate': buildDateString(row['statementday'], row['statementmonth'], row['statementyear']),
            'processed': row['processed']
        })
    return render_template('checkstatements.html', statements=statements)

# manage uploaded FAWA statement files.
# can delete or download a file. Downloading will allow the user to make some changes
# and then upload it again.
@app.route('/managefiles', methods=['GET', 'POST'])
def managefiles():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 should use this page.
    auth = (1,)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # table = uploads.
    # fields id (pk unique), filename (varchar(256))
    db = get_db()
    cur = db.cursor()
    sql = 'select id, filename from uploads'
    cur.execute(sql)
    data = cur.fetchall()

    return render_template('fawafiles.html', files=data)

# send a single SMS statement - this will present a form.
@app.route('/sendonesms', methods=['GET', 'POST'])
def sendonesms():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1, fawa=3 and sms=4 should use this page.
    auth = (1, 3, 4)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('under_construction.html', page="Send SMS")

# send HR SMS
@app.route('/sendhrsms/<uid>', methods=['GET', 'POST'])
def sendhrsms(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and sms=4 should use this page.
    auth = (1, 4)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('under_construction.html', page="Send HR SMS")

# generic form for sending an SMS
@app.route('/sendgenericsms', methods=['GET', 'POST'])
def sendgenericsms():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and sms=4 should use this page.
    auth = (1, 4)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

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
    phonelist = None
    txt = None
    if request.method == "POST":
        # get list of members to send message to. From the form, a list of ID's
        recipientslist = request.form.getlist('recipientlist')
        if len(recipientslist) > 0:
            recipientslist2 = [int(x) for x in recipientslist]
            # the following line fixed and issue with the tuple when there's only one item (1,)
            # the SQL command does not like this, so for all I append -1 to the end of the list
            # there are no members with that ID
            recipientslist2.append(-1)
            recipientslist = tuple(recipientslist2)
            sql = f'select id, memberno, firstname, surname, phone from member where id in {format(recipientslist)}'
            cur.execute(sql)
            recipientsdata = cur.fetchall()
            if recipientsdata is not None:
                phonelist = []
                for item in recipientsdata:
                    phonelist.append(item['phone'])
            # get the text to send.
            txt = request.form['genericsms'].strip()
            if len(txt) == 0:
                txt = None
        # if there are recipients and text is not blank, then send.
        if phonelist and txt:
            smsresult = sendSMS(txt, phonelist)
            # log result into database
            smsresult = f'text={txt} | ' + smsresult
            log(smsresult)
    return render_template('genericsms_form.html', members=data, recipients=recipientsdata, sms=txt)

@app.route('/reviewstatements/<sid>', methods=['GET', 'POST'])
def reviewstatements(sid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

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

# review a single FAWA statement detail.
# uid = unique statement data in fawastatement table.
@app.route('/reviewonefawastatement/<uid>', methods=['GET', 'POST'])
def reviewonefawastatement(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, statementid, memberno, membername, totaldeposit, monthlydeposit, totalloan_principal,
        totalloanpaid, outstandingloan, loanrepayment, guaranteed, loanroom_noguarantee, loanroom_guarantee,
        phone from fawastatement where id = ?
    '''
    cur.execute(sql, [uid])
    data = cur.fetchone()
    if data is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
        
    # get statement date information.
    statementid = data['statementid']
    sql = 'select id, statementday, statementmonth, statementyear, processed from fawaheader where id = ?'
    cur.execute(sql, [statementid])
    data2 = cur.fetchone()
    if data2 is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    statementdate = buildDateString(data2['statementday'], data2['statementmonth'], data2['statementyear'])
    header = {
        'id': data2['id'],
        'statementdate': statementdate,
        'processed': data2['processed']
    }

    return render_template('fawastatementdetail.html', header=header, statement=data)        

# md = message date (date that the SMS was sent)
@app.route('/showsmslogbyid/<sid>', methods=['GET', 'POST'])
def showsmslogbyid(sid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

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

@app.route('/usermgmt', methods=['GET', 'POST'])
def usermgmt():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))
    
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
        return redirect(url_for('login'))
    
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


    return redirect(url_for('staff'))

@app.route('/paystatements', methods=['GET', 'POST'])
def paystatements():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # show table of all statements in the database.
    db = get_db()
    cur = db.cursor()
    sql = '''
        select p.payid, c.company, p.paymonth, p.payyear, p.processed, count(d.id) as recordcount
        from payrollheader p
        join company c on (p.companyid = c.id) 
        join payroll d on (p.payid = d.payrollid)
        group by p.payid, c.company, p.paymonth, p.payyear, p.processed
        order by p.payid desc
    '''
    cur.execute(sql)    
    data = cur.fetchall()
    payrolls = []
    for row in data:
        payrolls.append({
            'payid': row['payid'],
            'company': row['company'],
            'recordcount': row['recordcount'],
            'payrolldate': buildPayrollDate(int(row['paymonth']), int(row['payyear'])),
            'processed': row['processed']
        })
    return render_template('checkpayroll.html', payrolls=payrolls)

@app.route('/reviewpayroll/<pid>', methods=['GET', 'POST'])
def reviewpayroll(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select p.payid, c.company, p.paymonth, p.payyear, p.processed from payrollheader p
        join company c on (c.id = p.companyid) 
        where p.payid = ?
    '''
    cur.execute(sql, [pid])
    data = cur.fetchone()
    if data is None:
        return redirect(request.referrer)
    
    payrolldate = buildPayrollDate(int(data['paymonth']), int(data['payyear']))
    header = {
        'id': data['payid'],
        'company': data['company'],
        'payrolldate': payrolldate,
        'processed': data['processed']
    }
    sql = '''
        select id, company, employeeno, fullname, phone, nationalid, krapin, jobdescription,
        grosspay, houseallowance, otherpay, overtime, benefits, nssf, taxableincome, nhif, paye,
        housinglevy, fawaloan, payadvance, absent, fawacontribution, housingbenefit,
        otherdeductions, netpay from payroll where payrollid = ?
    '''
    cur.execute(sql, [pid])
    data = cur.fetchall()
    if data is None:
        return redirect(request.referrer)
    
    return render_template('reviewpayroll.html', header=header, payroll=data)

@app.route('/reviewonepayrollstatement/<uid>', methods=['GET', 'POST'])
def reviewonepayrollstatement(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, payrollid, paymonth, payyear, company, employeeno, fullname, phone, nationalid,
        krapin, jobdescription, grosspay, houseallowance, otherpay, overtime, benefits, nssf, 
        taxableincome, nhif, paye, housinglevy, fawaloan, payadvance, absent, fawacontribution, 
        housingbenefit, otherdeductions, netpay from payroll where id = ?
    '''
    cur.execute(sql, [uid])
    data = cur.fetchone()
    if data is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # header
    payrolldate = buildPayrollDate(int(data['paymonth']), int(data['payyear']))
    header = {
        'id': data['payrollid'],
        'company': data['company'],
        'payrolldate': payrolldate
    }

    return render_template('reviewpayrolldetail.html', header=header, payroll=data)
    

@app.route('/sendpaystubsms/<pid>', methods=['GET', 'POST'])
def sendpaystubsms(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    # check if processed already
    db = get_db()
    cur = db.cursor()
    sql = 'select payid, companyid, paydate, paymonth, payyear, processed from payrollheader where payid = ?'
    cur.execute(sql, [pid])
    data = cur.fetchone()
    if data is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
        
    if data['processed'] == 1:
        # already processed.
        return render_template('paysmsresult.html', pid=data['payid'], message="Already Processed")
    
    payid = data['payid']
    payrolldate = buildPayrollDate(int(data['paymonth']), int(data['payyear']))

    # update payrollheader->processed = True
    sql = 'update payrollheader set processed = 1 where payid = ?'
    cur.execute(sql, [pid])
    db.commit()

    # send all paystubs for payrollheader->payid = pid
    sql = '''
        select id, payrollid, paymonth, payyear, company, employeeno, fullname, phone,
        nationalid, krapin, jobdescription, grosspay, houseallowance, otherpay, overtime,
        benefits, nssf, taxableincome, nhif, paye1, paye2, paye3, paye, housinglevy, 
        fawaloan, payadvance, absent, fawacontribution, housingbenefit, otherdeductions,
        netpay from payroll where payrollid = ?
    '''
    cur.execute(sql, [pid])
    data = cur.fetchall()
    smsdate = datetime.now()
    smscount = 0
    for row in data:
        slip = {
            'id': row['id'],
            'payrollid': row['payrollid'],
            'paymonth': row['paymonth'],
            'payyear': row['payyear'],
            'company': row['company'],
            'employeeno': row['employeeno'],
            'fullname': row['fullname'],
            'phone': row['phone'],
            'nationalid': row['nationalid'],
            'krapin': row['krapin'],
            'jobdescription': row['jobdescription'],
            'grosspay': row['grosspay'],
            'houseallowance': row['houseallowance'],
            'otherpay': row['otherpay'],
            'overtime': row['overtime'],
            'benefits': row['benefits'],
            'nssf': row['nssf'],
            'taxableincome': row['taxableincome'],
            'nhif': row['nhif'],
            'paye1': row['paye1'],
            'paye2': row['paye2'],
            'paye3': row['paye3'],
            'paye': row['paye'],
            'housinglevy': row['housinglevy'],
            'fawaloan': row['fawaloan'],
            'payadvance': row['payadvance'],
            'absent': row['absent'],
            'fawacontribution': row['fawacontribution'],
            'housingbenefit': row['housingbenefit'],
            'otherdeductions': row['otherdeductions'],
            'netpay': row['netpay']
        }
        sms_string = printSlip(slip, payrolldate)
        sql = '''
            insert into paysmslog (smsdate, payrollid, employeeno, phone, sms)
            values (?, ?, ?, ?, ?)
        '''
        cur.execute(sql, [smsdate, payid, row['employeeno'], row['phone'], sms_string])
        db.commit()
        lastinsertid = cur.lastrowid

        # send SMS
        if '000000' not in row['phone']:
            smsrecipient = row['phone']
            smsresult = sendSMS(sms_string, [smsrecipient])
            sql = 'update paysmslog set smsresult = ? where id = ?'
            cur.execute(sql, [smsresult, lastinsertid])
            db.commit()
            smscount += 1

    return render_template('paysmsresult.html', pid=pid, message=f'{smscount} messages sent')
    
@app.route('/showpaysmslogbyid/<pid>', methods=['GET', 'POST'])
def showpaysmslogbyid(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select p.paymonth, p.payyear, c.company from payrollheader p
        join company c on (p.companyid = c.id) and p.payid = ?
    '''
    cur.execute(sql, [pid])
    data = cur.fetchone()
    if data is None:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
        
    payrolldate = buildPayrollDate(int(data['paymonth']), int(data['payyear']))
    company = data['company']
    sql = '''
        select s.firstname || ' ' || s.lastname as fullname, l.phone, l.sms, l.smsresult
        from paysmslog l join staff s on (l.employeeno = s.employeeno)
        and l.payrollid = ?
    '''
    cur.execute(sql, [pid])
    data = cur.fetchall()
    if len(data) == 0:
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))


    return render_template('paysmslog.html', log=data, company=company, payrolldate=payrolldate)

@app.route('/payfiles', methods=['GET', 'POST'])
def payfiles():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select id, filename from payuploads'
    cur.execute(sql)
    data = cur.fetchall()

    return render_template('payfiles.html', files=data)

@app.route('/payrollfiledownload/<pid>', methods=['GET', 'POST'])
def payrollfiledownload(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from payuploads where id = ?'
    cur.execute(sql, [pid])
    data = cur.fetchone()
    if data is None:
        return redirect(url_for('payfiles'))
    
    filename = data['filename']
    log(f"pay file = {filename}")
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)

    return redirect(url_for('payfiles'))

@app.route('/payrollfiledelete/<pid>', methods=['GET', 'POST'])
def payrollfiledelete(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from payuploads where id = ?'
    cur.execute(sql, [pid])
    data = cur.fetchone()
    if data is None:
        return redirect(url_for('payfiles'))
    
    filename = data['filename']
    if os.path.exists(filename):
        os.remove(filename)
        sql = 'delete from payuploads where id = ?'
        cur.execute(sql, [pid])
        db.commit()

    return redirect(url_for('payfiles'))

@app.route('/sendonepayrollsms/<uid>', methods=['GET', 'POST'])
def sendonepayrollsms(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, payrollid, paymonth, payyear, company, employeeno, fullname, phone,
        nationalid, krapin, jobdescription, grosspay, houseallowance, otherpay, overtime,
        benefits, nssf, taxableincome, nhif, paye1, paye2, paye3, paye, housinglevy, 
        fawaloan, payadvance, absent, fawacontribution, housingbenefit, otherdeductions,
        netpay from payroll where id = ?
    '''
    cur.execute(sql, [uid])
    data = cur.fetchone()
    smsdate = datetime.now()

    payrolldate = buildPayrollDate(int(data['paymonth']), int(data['payyear']))

    slip = {
        'id': data['id'],
        'payrollid': data['payrollid'],
        'paymonth': data['paymonth'],
        'payyear': data['payyear'],
        'company': data['company'],
        'employeeno': data['employeeno'],
        'fullname': data['fullname'],
        'phone': data['phone'],
        'nationalid': data['nationalid'],
        'krapin': data['krapin'],
        'jobdescription': data['jobdescription'],
        'grosspay': data['grosspay'],
        'houseallowance': data['houseallowance'],
        'otherpay': data['otherpay'],
        'overtime': data['overtime'],
        'benefits': data['benefits'],
        'nssf': data['nssf'],
        'taxableincome': data['taxableincome'],
        'nhif': data['nhif'],
        'paye1': data['paye1'],
        'paye2': data['paye2'],
        'paye3': data['paye3'],
        'paye': data['paye'],
        'housinglevy': data['housinglevy'],
        'fawaloan': data['fawaloan'],
        'payadvance': data['payadvance'],
        'absent': data['absent'],
        'fawacontribution': data['fawacontribution'],
        'housingbenefit': data['housingbenefit'],
        'otherdeductions': data['otherdeductions'],
        'netpay': data['netpay']
    }
    sms_string = printSlip(slip, payrolldate)
    sql = '''
        insert into paysmslog (smsdate, payrollid, employeeno, phone, sms)
        values (?, ?, ?, ?, ?)
    '''
    cur.execute(sql, [smsdate, data['payrollid'], data['employeeno'], data['phone'], sms_string])
    db.commit()
    lastinsertid = cur.lastrowid
    smsrecipient = data['phone']
    smsresult = sendSMS(sms_string, [smsrecipient])
    sql = 'update paysmslog set smsresult = ? where id = ?'
    cur.execute(sql, [smsresult, lastinsertid])
    db.commit()

    # display a page with the result of this SMS send.
    message = smsresult
    return render_template('payrollsmsresult.html', message=message, sms=sms_string)
