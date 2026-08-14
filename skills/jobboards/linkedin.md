# LinkedIn Applications (Easy Apply & External)

## Overview
LinkedIn job listings can either be applied via:
1. **Easy Apply** (modal overlay directly on LinkedIn).
2. **External Apply** (redirects to company ATS e.g. Greenhouse, Lever, Workday, Ashby, etc.).

## Easy Apply Workflow
1. Locate and click the **"Easy Apply"** button on the job page.
2. An overlay modal opens with multi-step sections (Contact info, Resume, Work experience, Custom questions).
3. **Contact info**: Pre-filled from profile. Verify phone number and email (`madhajaswanth@gmail.com`).
4. **Resume**: Select the existing resume or upload `user_details/resume.pdf` if requested.
5. **Form fields / Questions**: Match questions against user Q&A. If unknown, add to `user_details/qna.md` with `# NEEDS ANSWER` status and fill with a reasonable fallback.
6. **Next / Review**: Click "Next" to navigate through wizard pages.
7. **Submit**: On final page ("Review your application"), require explicit user confirmation before submitting if configured as dangerous, then click "Submit application".

## Reusable Learnings
- LinkedIn Easy Apply flow for AI engineering roles may consist of Contact info, Resume upload, optional Top Choice, Review, and Submit; verify phone and upload the resume before reviewing.
- For LinkedIn Easy Apply postings with a simple single-page form, contact information and a saved resume may be prefilled; verify the country code and phone, select the appropriate resume, and submit directly when no additional questions are present.
- When a LinkedIn job URL initially loads the requested title but the SPA subsequently redirects to a different job listing and no job content or Easy Apply controls become available, treat the requested posting as unavailable and do not apply to the redirected listing.
- TCS iBegin external applications may require creating a TCS Careers profile before applying; the registration form includes a CAPTCHA that must be solved interactively and may block automation.
- LinkedIn Easy Apply may present the saved resume list; the most recently dated GenAI/ML Engineer PDF was preselected and suitable for AI Engineer roles.
- Application wizard sequence observed: Contact info -> Resume -> Additional Questions -> Work authorization -> Review.
- Use `getByTestId('dialog-content')` to scope wizard controls because page-level buttons may have duplicate names (for example, Next).
- Easy Apply questions for AI/ML roles can include years of PyTorch, LLM Application Development, hybrid comfort, commuting, work authorization, and sponsorship.
- Another observed flow: Contact info -> Resume upload -> optional Top Choice -> Additional Questions -> Review -> Submit. Uploading `/Users/jaswanth/mydocs/myprojects/langgraph/user_details/resume.pdf` triggers a successful-upload notification; resume selection is then accepted by Next.
- Additional Questions may ask free-text years of experience for Python, Large Language Models (LLM), and Artificial Intelligence (AI); enter concise numeric years based on the profile.
- Some external LinkedIn redirects use Bain's Taleo-style portal and require resume-based registration before the application form. Upload the resume, then review parsed personal, education, work-history, skills, recruitment-source, affinity-group, password, and privacy-consent fields.
- In that portal, autocomplete school fields may need selecting a close institution match or “School not listed”; selecting an option such as the parent university can satisfy the required field when the exact campus is unavailable.
- Bain external applications may use a multi-step wizard: job-specific narrative questions, location selection, work authorization, then optional EEO questions. Select a single intended US office (or multiple if appropriate), answer US authorization and sponsorship consistently with the candidate's visa status, and acknowledge required certifications. The EEO page requires country of residence and a voluntary-response acknowledgment; demographic questions can be left unanswered.
- Bain career links may route through a job-summary page to a careers.bain.com Login/ApplicationConfirmation flow. If the confirmation page says the applicant account was created and returning to the job summary shows “You have already applied for this job,” treat the application as submitted; no further form completion is needed.

## External Redirect Workflow
1. If the job page has an **"Apply"** button that opens a new tab or redirects to an external site:
2. Identify the external ATS platform (Greenhouse, Lever, Ashby, Workday, etc.).
3. Read the relevant skill file `skills/jobboards/<platform>.md` if available and proceed with standard web application filling.
- When a LinkedIn job posting page displays 'No longer accepting applications' and no Apply/Easy Apply button is rendered, the posting is closed and unapplicable; do not attempt to apply or redirect to similar live listings.
- Always scan the job detail page for the application status message before attempting Apply; a closed posting will show an explicit status banner in place of the Apply control.
