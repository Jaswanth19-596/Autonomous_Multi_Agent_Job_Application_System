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
- LinkedIn Easy Apply may present the saved resume list; the most recently dated GenAI/ML Engineer PDF was preselected and suitable for AI Engineer roles.
- Application wizard sequence observed: Contact info -> Resume -> Additional Questions -> Work authorization -> Review.
- Use `getByTestId('dialog-content')` to scope wizard controls because page-level buttons may have duplicate names (for example, Next).
- Easy Apply questions for AI/ML roles can include years of PyTorch, LLM Application Development, hybrid comfort, commuting, work authorization, and sponsorship.

## External Redirect Workflow
1. If the job page has an **"Apply"** button that opens a new tab or redirects to an external site:
2. Identify the external ATS platform (Greenhouse, Lever, Ashby, Workday, etc.).
3. Read the relevant skill file `skills/jobboards/<platform>.md` if available and proceed with standard web application filling.
