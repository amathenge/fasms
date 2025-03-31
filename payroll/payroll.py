from flask import Blueprint, render_template, redirect, g, request, session, url_for, current_app, send_file
from datetime import datetime
import os
from database import get_db, hashpass, otp_ontime, log, onetime, allowed_file
from werkzeug.utils import secure_filename
from sms import sendSMS
from sendEmail import send_otp_email
from auth.auth import auth
from payroll.payimport import importpaydata, buildPayrollDate, printSlip

payroll = Blueprint("payroll", __name__, static_folder="static", template_folder="templates")

def hasauth(item, check):
    # "item" and "check" are lists. The correct authorization categories are in "check"
    # if an item in "item" corresponds to an item in "check" then return True
    # example item=(3,4) and check=(2,4) --> return True
    # example item=(2,4,5) and check=(3,6) --> return False
    # example item=(1,) and check=(2,3) --> return True (because 1=admin)
    if 1 in item:
        return True
    auth = False
    for element in item:
        if element in check:
            auth = True
    return auth

@payroll.route('/payslips', methods=['GET', 'POST'])
def payslips():
    # check if logged in, then continue.
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    # user is logged in - show payroll management options.
    return render_template('payroll/paystubs.html')

# payroll processing files. For sending payroll sms.
@payroll.route('/payupload', methods=['GET', 'POST'])
def payupload():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

    user = session['user']
    # only admin=1 and payroll=5 should use this page.
    auth = (1, 5)
    if not hasauth(list(user['auth']), auth):
        if request.referrer:
            return redirect(request.referrer)
        else:
            return redirect(url_for('home'))
    if 'callform' in request.form:
        return render_template('payroll/payupload.html', message=None)

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
            cur.execute(sql, [os.path.join(current_app.config['UPLOAD_FOLDER'],filename)])
            data = cur.fetchone()
            if data is None:
                sql = 'insert into payuploads (filename) values (?)'
                cur.execute(sql, [os.path.join(current_app.config['UPLOAD_FOLDER'], filename)])
                db.commit()
                fileid = cur.lastrowid
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                message = "File uploaded"
                log(f'/payupload - uploaded file id = {fileid} name = {filename}')
                # import data from the file (xlsx) into the database.
                result = importpaydata(fileid)
                if not result:
                    log('/payupload - nothing uploaded')
                    message += ' - DATA NOT IMPORTED'
                else:
                    log('/payupload - data uploaded')
                    message += f' DATA IMPORTED {result} rows from file {filename}'
            else:
                # file has already been uploaded.
                message = f"File <b><u>{data['filename']}</u></b> exists - uploaded previously."
    # not in post mode - show the upload form
    return render_template('payroll/payupload.html', message=message)

@payroll.route('/paystatements', methods=['GET', 'POST'])
def paystatements():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
    return render_template('payroll/checkpayroll.html', payrolls=payrolls)

@payroll.route('/reviewpayroll/<pid>', methods=['GET', 'POST'])
def reviewpayroll(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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

    return render_template('payroll/reviewpayroll.html', header=header, payroll=data)

@payroll.route('/reviewonepayrollstatement/<uid>', methods=['GET', 'POST'])
def reviewonepayrollstatement(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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

    return render_template('payroll/reviewpayrolldetail.html', header=header, payroll=data)

@payroll.route('/sendpaystubsms/<pid>', methods=['GET', 'POST'])
def sendpaystubsms(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        # print the slip
        if '254000' not in slip['phone']:
            sms_string = printSlip(slip, payrolldate)
            sql = '''
                insert into paysmslog (smsdate, payrollid, employeeno, phone, sms)
                values (?, ?, ?, ?, ?)
            '''
            cur.execute(sql, [smsdate, payid, row['employeeno'], row['phone'], sms_string])
            db.commit()
            lastinsertid = cur.lastrowid
        else:
            # send the error SMS to Tony
            sms_string = 'Payslip [phone] Err: ['+ row['phone'] + ']'
            row['phone'] = '254759614127'

        # send SMS
        if '254000' not in slip['phone']:
            smsrecipient = slip['phone']
            smsresult = sendSMS(sms_string, [smsrecipient])
            sql = 'update paysmslog set smsresult = ? where id = ?'
            cur.execute(sql, [smsresult, lastinsertid])
            db.commit()
            smscount += 1

    return render_template('payroll/paysmsresult.html', pid=pid, message=f'{smscount} messages sent')

@payroll.route('/showpaysmslogbyid/<pid>', methods=['GET', 'POST'])
def showpaysmslogbyid(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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


    return render_template('payroll/paysmslog.html', log=data, company=company, payrolldate=payrolldate)

@payroll.route('/payfiles', methods=['GET', 'POST'])
def payfiles():
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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

    return render_template('payroll/payfiles.html', files=data)

@payroll.route('/payrollfiledownload/<pid>', methods=['GET', 'POST'])
def payrollfiledownload(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('payroll.payfiles'))

    filename = data['filename']
    log(f"pay file = {filename}")
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)

    return redirect(url_for('payroll.payfiles'))

@payroll.route('/payrollfiledelete/<pid>', methods=['GET', 'POST'])
def payrollfiledelete(pid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('payroll.payfiles'))

    filename = data['filename']
    if os.path.exists(filename):
        os.remove(filename)
        sql = 'delete from payuploads where id = ?'
        cur.execute(sql, [pid])
        db.commit()

    return redirect(url_for('payroll.payfiles'))

@payroll.route('/sendonepayrollsms/<uid>', methods=['GET', 'POST'])
def sendonepayrollsms(uid):
    if 'user' not in session or not session['user']['otp']:
        return redirect(url_for('auth.login'))

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
    try:
        sms_string = printSlip(slip, payrolldate)
    except:
        return redirect(request.referrer)

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
    return render_template('payroll/payrollsmsresult.html', message=message, sms=sms_string)

