drop table if exists member;

create table member (
    id integer primary key,
    memberid integer not null,
    firstname varchar(64) not null,
    middlename varchar(64),
    surname varchar(64) not null,
    phone varchar(16) not null
);

-- add the member data (assume we are running this from application home)

.read sql/memberdata.sql
