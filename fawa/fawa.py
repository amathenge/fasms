from flask import Blueprint, render_template, redirect, g, request, session, url_for, current_app, send_file
from datetime import datetime
import os
from database import get_db, hashpass, otp_ontime, log, onetime, allowed_file
from sms import sendSMS
from sendEmail import send_otp_email
from fawa.fawautils import importdata, buildDateString, hasauth
from werkzeug.utils import secure_filename

fawa = Blueprint("fawa", __name__, static_folder="static", template_folder="templates")

@fawa.route('/fawastatements', methods=['GET', 'POST'])
def fawastatements():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('fawa/fawastatements.html')

# send all SMS based on fawaheader->id and mark fawaheader->processed as true.
@fawa.route('/sendallsms/<sid>', methods=['GET','POST'])
def sendallsms(sid):
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        return render_template('fawa/smsresult.html', sid=data['id'], message='Already Processed')
    
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

    return render_template('fawa/smsresult.html', sid=sid, message=f"{smscount} messages sent")

# send an individual FAWA sms
@fawa.route('/sendfawasms/<uid>', methods=['GET', 'POST'])
def sendfawasms(uid):
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
    return render_template('fawa/fawasmsresult.html', message=message, sms=sms)

# upload a file
@fawa.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    user = session['user']
    # only admin=1 and fawa=3 should use this page.
    auth = (1, 3)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    if 'callform' in request.form:
        log("upload: not processing - presenting form only")
        return render_template('fawa/upload.html', message=None)
    
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
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                message = "File uploaded"
                # import data from the file (xlsx) into the database.
                result = importdata(fileid, os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                log(f'upload: importdata() called on {filename}')
                if result is None:
                    message += f' - DATA NOT IMPORTED from file: {filename}'
                else:
                    message += f' DATA IMPORTED {result} rows from file {filename}'
            else:
                # file has already been uploaded.
                message = f"File <b><u>{data['filename']}</u></b> exists - uploaded previously."
    # not in post mode - show the upload form
    return render_template('fawa/upload.html', message=message)

@fawa.route('/fawafiledownload/<fid>', methods=['GET', 'POST'])
def fawafiledownload(fid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('fawa.managefiles'))
    
    filename = os.path.join(current_app.config['UPLOAD_FOLDER'], data['filename'])
    return send_file(filename, as_attachment=True)

@fawa.route('/fawafiledelete/<fid>', methods=['GET', 'POST'])
def fawafiledelete(fid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('fawa.managefiles'))
    
    filename = os.path.join(current_app.config['UPLOAD_FOLDER'], data['filename'])
    if os.path.exists(filename):
        os.remove(filename)
        sql = 'delete from uploads where id = ?'
        cur.execute(sql, [fid])
        db.commit()

    return redirect(url_for('fawa.managefiles'))

@fawa.route('/checkstatements', methods=['GET', 'POST'])
def checkstatements():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        order by h.id desc
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
    return render_template('fawa/checkstatements.html', statements=statements)

# manage uploaded FAWA statement files.
# can delete or download a file. Downloading will allow the user to make some changes
# and then upload it again.
@fawa.route('/managefiles', methods=['GET', 'POST'])
def managefiles():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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

    return render_template('fawa/fawafiles.html', files=data)

# send a single SMS statement - this will present a form.
@fawa.route('/sendonesms', methods=['GET', 'POST'])
def sendonesms():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    user = session['user']
    # only admin=1, fawa=3 and sms=4 should use this page.
    auth = (1, 3, 4)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))

    return render_template('under_construction.html', page="Send SMS")

# generic form for sending an SMS
@fawa.route('/sendgenericsms', methods=['GET', 'POST'])
def sendgenericsms():
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
    return render_template('fawa/genericsms_form.html', members=data, recipients=recipientsdata, sms=txt)

@fawa.route('/reviewstatements/<sid>', methods=['GET', 'POST'])
def reviewstatements(sid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
    
    return render_template('fawa/reviewstatements.html', header=header, statements=data)

# review a single FAWA statement detail.
# uid = unique statement data in fawastatement table.
@fawa.route('/reviewonefawastatement/<uid>', methods=['GET', 'POST'])
def reviewonefawastatement(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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

    return render_template('fawa/fawastatementdetail.html', header=header, statement=data)        

# md = message date (date that the SMS was sent)
@fawa.route('/showsmslogbyid/<sid>', methods=['GET', 'POST'])
def showsmslogbyid(sid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
    

    return render_template('fawa/smslog.html', log=data, statementdate=statementdate)


