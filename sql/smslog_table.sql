drop table if exists smslog;

create table smslog (
    id integer primary key autoincrement,
    smsdate datetime not null,
    statementid integer not null references fawaheader (id),
    memberno integer not null references member (memberno),
    sms text not null
);