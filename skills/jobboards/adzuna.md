# Adzuna job-board skill
- Adzuna Easy Apply redirects through its own login/register; clicking 'Continue with Google' proceeds to the application form without creating a new account.
- Resume is auto-selected from the stored Adzuna profile (cvId select), so no manual upload is needed if a resume already exists.
- Employer screening questions are rendered as inputs with name attributes like screeningQuestionAnswers["<id>"]; select YES/NO dropdowns use those same ids and are best matched by exact name.
- The application page includes a reCAPTCHA 'I'm not a robot' checkbox; it auto-verifies in a trusted browser and does not necessarily require a manual image challenge.
- Success is confirmed by a page heading 'Application submitted: <job title>' after clicking Submit Application.
