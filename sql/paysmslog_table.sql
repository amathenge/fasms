drop table if exists paysmslog;

create table paysmslog (
    id integer primary key autoincrement,
    smsdate datetime not null,
    payrollid integer not null references payrollheader (payid),
    employeeno varchar(8) not null references staff (employeeno),
    phone varchar(16) not null,
    sms text not null,
    smsresult text
);