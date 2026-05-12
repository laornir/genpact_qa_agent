-- Debug seed data mirroring the university schema from 001_initial.sql.
-- Explicit IDs are used for reproducibility; sequences are reset at the end.

INSERT INTO teachers (id, name, email) VALUES
    (1, 'Alice Smith', 'alice@university.edu'),
    (2, 'Bob Jones',   'bob@university.edu');

INSERT INTO students (id, name, email, enrollment_year) VALUES
    (1, 'Charlie Brown', 'charlie@student.edu', 2022),
    (2, 'Diana Prince',  'diana@student.edu',   2023),
    (3, 'Eve Adams',     'eve@student.edu',      2022);

INSERT INTO courses (id, name, credits, syllabus) VALUES
    (1, 'Algorithms', 3, NULL),
    (2, 'Databases',  4, NULL);

INSERT INTO semesters (id, name, year, season) VALUES
    (1, 'Fall 2024',   2024, 'fall'),
    (2, 'Spring 2025', 2025, 'spring');

-- Offerings: Alice teaches Algorithms both semesters; Bob teaches Databases in Fall 2024.
INSERT INTO course_offerings (id, course_id, teacher_id, semester_id, syllabus_url, room, max_capacity) VALUES
    (1, 1, 1, 1, NULL, 'Room 101', 30),
    (2, 2, 2, 1, NULL, 'Room 202', 25),
    (3, 1, 1, 2, NULL, 'Room 101', 30);

-- Enrollments: Charlie and Diana in Algorithms Fall 2024; Eve in Algorithms Fall 2024;
--              Charlie in Databases Fall 2024; Diana in Algorithms Spring 2025 (grade pending).
INSERT INTO enrollments (id, student_id, offering_id, grade, enrolled_at) VALUES
    (1, 1, 1, 95.5, '2024-09-01 10:00:00'),
    (2, 2, 1, 88.0, '2024-09-01 10:00:00'),
    (3, 3, 1, 72.5, '2024-09-01 10:00:00'),
    (4, 1, 2, 91.0, '2024-09-01 10:00:00'),
    (5, 2, 3, NULL, '2025-01-15 10:00:00');

-- Advance sequences past the inserted IDs so future INSERTs don't collide.
SELECT setval('teachers_id_seq',        (SELECT MAX(id) FROM teachers));
SELECT setval('students_id_seq',        (SELECT MAX(id) FROM students));
SELECT setval('courses_id_seq',         (SELECT MAX(id) FROM courses));
SELECT setval('semesters_id_seq',       (SELECT MAX(id) FROM semesters));
SELECT setval('course_offerings_id_seq',(SELECT MAX(id) FROM course_offerings));
SELECT setval('enrollments_id_seq',     (SELECT MAX(id) FROM enrollments));
