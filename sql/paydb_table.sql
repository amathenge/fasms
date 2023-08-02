# recreate the pay.db tables

drop table if exists payroll;

CREATE TABLE payroll (
    id integer primary key autoincrement,
    payrollid integer not null,
    paymonth integer not null,
    payyear integer not null,
    employeeid varchar(8) not null,
    nationalid varchar(16) not null,
    company varchar(32),
    grosspay varchar(16),
    houseallowance  varchar(16),
    bonus varchar(16),
    overtime varchar(16),
    benefits varchar(16),
    nssf varchar(16),
    taxableincome varchar(16),
    nhif varchar(16),
    paye1 varchar(16),
    paye2 varchar(16),
    paye3 varchar(16),
    paye varchar(16),
    leavepay varchar(16),
    fawaloan varchar(16),
    payadvance varchar(16),
    absent varchar(16),
    fawacontribution varchar(16),
    housingbenefit varchar(16),
    netpay varchar(16),
    unique (payrollid, employeeid, nationalid)
);

drop table if exists payrollheader;

CREATE TABLE payrollheader (
    payid integer primary key autoincrement,
    paydate date not null,
    payyear integer not null,
    paymonth integer not null,
    UNIQUE (paymonth, payyear)
);
