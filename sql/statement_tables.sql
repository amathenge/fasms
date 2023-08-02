drop table if exists fawaheader;

create table fawaheader (
    id integer primary key autoincrement,
    fileid integer not null references uploads(id),
    statementday integer not null,
    statementyear integer not null,
    statementmonth integer not null,
    unique (statementday, statementyear, statementmonth)
);


drop table if exists fawastatement;

create table fawastatement (
    id integer primary key autoincrement,
    statementid integer not null REFERENCES fawaheader(id),
    memberno varchar(4) not null,
    membername varchar(128) not null,
    totaldeposit varchar(16),
    monthlydeposit varchar(16),
    totalloan_principal varchar(16),
    totalloanpaid varchar(16),
    outstandingloan varchar(16),
    loanrepayment varchar(16),
    guaranteed varchar(16),
    loanroom_noguarantee varchar(16),
    loanroom_guarantee varchar(16),
    phone varchar(16),
    unique (memberno, statementid)
);

