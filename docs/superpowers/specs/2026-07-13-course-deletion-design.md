# Course Deletion Design

## Goal

Allow the learner to permanently delete an unwanted course from the course list, including every piece of learning data and every imported file owned by that course.

## User experience

- Each course card has a dedicated `删除课程` button in its top-right corner.
- The delete control is separate from the link that opens the course, so deleting never navigates into the course.
- Clicking it opens a native confirmation that names the course and warns that courseware, lessons, questions, answers, and review history will also be deleted.
- On success, the course disappears immediately and a short success message is shown.
- On cancellation or failure, the course remains unchanged. A failure message is shown without exposing internal errors.

## Data behavior

`DELETE /api/courses/{course_id}` deletes only data owned by the selected course:

1. lessons, knowledge points, questions, attempts, and affected review sessions;
2. pages and documents;
3. NotebookLM imports;
4. the course itself;
5. document directories under local application storage.

Review sessions containing questions from multiple courses keep unrelated questions and attempts. If a review session becomes empty, it is deleted. Database changes are committed once after the complete cascade is prepared.

Before that commit, owned document directories are moved into a local staging area. A database failure restores them to their original paths; after a successful commit, the staged files are purged. This prevents a failed delete from leaving the database pointed at missing courseware.

## Testing

- Backend integration tests create two courses and mixed review data, delete one course, and verify all owned data is gone while unrelated data remains.
- API tests verify a missing course returns the standard 404 problem response.
- Frontend tests verify confirmation copy, DELETE request, list removal, cancellation, and failure behavior.
- Playwright covers deleting a course from the visible course list.
