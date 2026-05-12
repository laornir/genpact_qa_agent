-- Example: list all students enrolled in a specific course
SELECT s.name
FROM students s
JOIN enrollments e      ON e.student_id  = s.id
JOIN course_offerings o ON o.id          = e.offering_id
JOIN courses c          ON c.id          = o.course_id
WHERE c.name = 'Algorithms';

-- Example: count students per course in a given semester
SELECT c.name AS course, COUNT(e.id) AS student_count
FROM courses c
JOIN course_offerings o ON o.course_id   = c.id
JOIN semesters sem       ON sem.id        = o.semester_id
JOIN enrollments e       ON e.offering_id = o.id
WHERE sem.name = 'Fall 2024'
GROUP BY c.name
ORDER BY student_count DESC;

-- Example: teacher with the highest average grade across all offerings
SELECT t.name, AVG(e.grade) AS avg_grade
FROM teachers t
JOIN course_offerings o ON o.teacher_id  = t.id
JOIN enrollments e      ON e.offering_id = o.id
WHERE e.grade IS NOT NULL
GROUP BY t.id, t.name
ORDER BY avg_grade DESC
LIMIT 1;

-- Example: students with no grades yet (ungraded enrollments)
SELECT s.name AS student, c.name AS course
FROM students s
JOIN enrollments e      ON e.student_id  = s.id
JOIN course_offerings o ON o.id          = e.offering_id
JOIN courses c          ON c.id          = o.course_id
WHERE e.grade IS NULL;
