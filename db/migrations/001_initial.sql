CREATE TYPE season_type AS ENUM ('spring', 'summer', 'fall');

CREATE TABLE teachers (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL
);

CREATE TABLE students (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR NOT NULL,
    email           VARCHAR UNIQUE NOT NULL,
    enrollment_year INT NOT NULL
);

CREATE TABLE courses (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR NOT NULL,
    credits  INT NOT NULL,
    syllabus VARCHAR
);

CREATE TABLE semesters (
    id     SERIAL PRIMARY KEY,
    name   VARCHAR NOT NULL,
    year   INT NOT NULL,
    season season_type NOT NULL
);

CREATE TABLE course_offerings (
    id           SERIAL PRIMARY KEY,
    course_id    INT NOT NULL REFERENCES courses(id),
    teacher_id   INT NOT NULL REFERENCES teachers(id),
    semester_id  INT NOT NULL REFERENCES semesters(id),
    syllabus_url VARCHAR,
    room         VARCHAR,
    max_capacity INT
);

CREATE TABLE enrollments (
    id          SERIAL PRIMARY KEY,
    student_id  INT NOT NULL REFERENCES students(id),
    offering_id INT NOT NULL REFERENCES course_offerings(id),
    grade       NUMERIC(5, 2),
    enrolled_at TIMESTAMP NOT NULL
);
