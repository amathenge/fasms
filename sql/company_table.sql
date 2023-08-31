drop table if exists company;

create table company (
    id integer primary key,
    company varchar(32) not null
);

-- if run from reset_env.sh which is one level down.
.read sql/company_data.sql

