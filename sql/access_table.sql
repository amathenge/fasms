-- the access table determines access to various parts of the system.
-- the roles can be combined into a tuple (1, 2, ...) that is entered into
-- the session table as a list of privileges

drop table if exists access;

create table access (
    id integer primary key autoincrement,
    auth integer not null,
    access varchar(8),
    notes text
);

insert into access (id, auth, access, notes) values
    (1, 1, 'admin', 'administrative user, full access'),
    (2, 2, 'usermgr', 'user administrator - can add, edit and delete users'),
    (3, 3, 'fawa', 'can use the FAWA sms system'),
    (4, 4, 'sms', 'can send sms but cannot change anything'),
    (5, 5, 'payroll', 'can use the payslip features'),
    (6, 6, 'readonly', 'has only readonly access - cannot commit to database');

