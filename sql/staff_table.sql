drop table if exists staff;

create table staff (
    employeeno varchar(8) primary key,
    company integer not null references company(id),
    firstname varchar(16) not null,
    middlename varchar(16),
    lastname varchar(16) not null,
    nationalid varchar(16) not null,
    krapin varchar(16),
    jobdescription varchar(16) not null,
    email varchar(16),
    phone varchar(16) not null
);
-- if run from reset_env.sh which is one level down.
.read sql/staff_data.sql
