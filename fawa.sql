drop table if exists access;

create table access (
    id integer primary key,
    auth integer not null,
    access varchar(8),
    notes text
);

-- foreign key constraint. need to drop this first.
drop table if exists otp;
drop table if exists users;

CREATE TABLE users (
    id integer primary key,
    firstname varchar(32) not null, 
    lastname varchar(32) not null,
    email varchar(128) not null,
    password varchar(32) not null,
    phone varchar(32) not null,
    auth varchar(8) not null default '6',
    locked boolean not null default false
);

drop table if exists otp;

create table otp (
    id integer primary key,
    userid integer not null references users (id),
    otp varchar(6) not null,
    otp_time datetime not null,
    valid boolean not null default false
);

-- add some sample data

.read sampledata.sql


drop table if exists member;

create table member (
    id integer primary key,
    memberid integer not null,
    firstname varchar(64) not null,
    middlename varchar(64),
    surname varchar(64) not null,
    phone varchar(16) not null
);

-- add the member data

.read memberdata.sql
