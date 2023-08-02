drop table if exists log;

create table log (
    id integer primary key,
    logdate datetime not null,
    log text not null
);
