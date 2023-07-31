drop table if exists uploads;

create table uploads (
    id integer primary key autoincrement,
    filename varchar(265) not null unique
);

