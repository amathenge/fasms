drop table if exists uploads;

create table uploads (
    id integer primary key autoincrement,
    filename varchar(265) not null unique
);

drop table if exists payuploads;

create table payuploads (
    id integer primary key autoincrement,
    filename varchar(265) not null unique
);