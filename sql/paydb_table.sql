-- recreate the pay.db tables

drop table if exists payroll;

CREATE TABLE payroll (
    id integer primary key autoincrement,
    payrollid integer not null,
    paymonth integer not null,
    payyear integer not null,
    company varchar(32),
    employeeno varchar(8) not null,
    fullname varchar(128) not null,
    phone varchar(16) not null,
    nationalid varchar(16) not null,
    krapin varchar(16),
    jobdescription varchar(32),
    grosspay varchar(16),
    houseallowance  varchar(16),
    otherpay varchar(16),
    overtime varchar(16),
    benefits varchar(16),
    nssf varchar(16),
    taxableincome varchar(16),
    nhif varchar(16),
    paye1 varchar(16),
    paye2 varchar(16),
    paye3 varchar(16),
    paye varchar(16),
    housinglevy varchar(16),
    fawaloan varchar(16),
    payadvance varchar(16),
    absent varchar(16),
    fawacontribution varchar(16),
    housingbenefit varchar(16),
    otherdeductions varchar(16),
    netpay varchar(16),
    unique (payrollid, employeeno, nationalid)
);

drop table if exists payrollheader;

CREATE TABLE payrollheader (
    payid integer primary key autoincrement,
    companyid integer not null references company(id),
    paydate date not null,
    payyear integer not null,
    paymonth integer not null,
    processed boolean default 0,
    UNIQUE (companyid, paymonth, payyear)
);
