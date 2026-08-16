# LinkedIn Applications (Easy Apply & External)

## Overview
LinkedIn job listings can either be applied via:
1. **Easy Apply** (modal overlay directly on LinkedIn).
2. **External Apply** (redirects to company ATS e.g. Greenhouse, Lever, Workday, Ashby, etc.).

## Easy Apply Workflow
1. Locate and click the **"Easy Apply"** button on the job page.
2. For Easy apply, DO NOT CALL SIMPLIFY AUTOFILL. It is not needed.
2. An overlay modal opens with multi-step sections (Contact info, Resume, Work experience, Custom questions).
3. **Contact info**: Pre-filled from profile. Verify phone number and email (`madhajaswanth@gmail.com`).
4. **Resume**: Select the existing resume or upload `user_details/resume.pdf` if requested.
5. **Form fields / Questions**: Match questions against the user profile. If unknown, call `ask_for_profile_answer` with the exact question and available options, then use the user's response.
6. **Next / Review**: Click "Next" to navigate through wizard pages.
7. **Submit**: On final page ("Review your application"), require explicit user confirmation before submitting if configured as dangerous, then click "Submit application".

## Reusable Learnings

- LinkedIn Easy Apply can route to a Workable-powered six-page wizard: Contact info, Resume, Work experience, Education, Additional Questions, and Review. Uploading `/Users/jaswanth/mydocs/myprojects/langgraph/user_details/resume.pdf` works; city fields may require selecting an autocomplete suggestion before Next.
- Workable LinkedIn forms may render long-form custom questions as textboxes even when the prompt lists answer choices or multi-select requirements. Fill the textbox with the exact selected answer(s), separated by commas for multi-select, then use Review.
- Some LinkedIn external-apply links route to a company-branded custom form rather than Easy Apply or a standard ATS. The Roku form required contact details, resume upload, LinkedIn/website URLs, source, work authorization, sponsorship, location autocomplete/text, and a truthfulness acknowledgment. The form's Apply toggle may need to be clicked twice when the CTA is initially collapsed; after upload and exact required selections, confirmation text appears inline.
- Some LinkedIn external-apply links embed a legacy ASP.NET application form in an iframe; if the form endpoint returns HTTP 500 with a database connection-pool timeout on repeated loads, the application is blocked by the external system and should be reported as failed rather than retried indefinitely.
- LinkedIn Easy Apply can terminate the wizard immediately after a required export-control/ITAR eligibility answer; answer US-person questions truthfully and stop when the candidate is ineligible.

- LinkedIn Easy Apply single-step forms may require selecting the US phone country code and uploading the resume; after successful upload, Submit application can complete the application directly without additional questions.
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
- A Qualis1 AI Engineer Easy Apply flow contained only one required additional question (years of AI experience) after Contact info, Resume, and optional Top Choice; the Review page showed the saved PDF and answer before submission.
- Some external LinkedIn redirects use Bain's Taleo-style portal and require resume-based registration before the application form. Upload the resume, then review parsed personal, education, work-history, skills, recruitment-source, affinity-group, password, and privacy-consent fields.
- In that portal, autocomplete school fields may need selecting a close institution match or “School not listed”; selecting an option such as the parent university can satisfy the required field when the exact campus is unavailable.
- Bain external applications may use a multi-step wizard: job-specific narrative questions, location selection, work authorization, then optional EEO questions. Select a single intended US office (or multiple if appropriate), answer US authorization and sponsorship consistently with the candidate's visa status, and acknowledge required certifications. The EEO page requires country of residence and a voluntary-response acknowledgment; demographic questions can be left unanswered.
- Bain career links may route through a job-summary page to a careers.bain.com Login/ApplicationConfirmation flow. If the confirmation page says the applicant account was created and returning to the job summary shows “You have already applied for this job,” treat the application as submitted; no further form completion is needed.
- Deloitte external applications may use the apply.deloitte.com multi-step wizard. When already signed in, the Apply link can route through RegisterEdit. The wizard may prefill profile data and resume; verify required contact, education, work-history, immigration, location, EEO, and disability pages. Remove any blank duplicate work-history row before continuing. A successful submission lands on /careers/Success with “Thank you for applying.”
- Capgemini external job pages may offer a manual “Apply now” route and a LinkedIn apply option; if the application endpoint redirects immediately to the Capgemini homepage, treat the application as unavailable rather than attempting repeated clicks.
- LinkedIn external-apply links may redirect to a job-aggregator detail page rather than the employer ATS. Verify that the redirected company and role match the requested posting before applying; if the page lists an explicit work-authorization restriction incompatible with the candidate, do not submit.

## External Redirect Workflow
1. If the job page has an **"Apply"** button that opens a new tab or redirects to an external site:
2. Identify the external ATS platform (Greenhouse, Lever, Ashby, Workday, etc.).
3. Read the relevant skill file `skills/jobboards/<platform>.md` if available and proceed with standard web application filling.
- When a LinkedIn job posting page displays 'No longer accepting applications' and no Apply/Easy Apply button is rendered, the posting is closed and unapplicable; do not attempt to apply or redirect to similar live listings.
- Always scan the job detail page for the application status message before attempting Apply; a closed posting will show an explicit status banner in place of the Apply control.
- Easy Apply may use a five-page wizard: contact info, resume selection, optional Top Choice, and additional questions followed by review; saved resumes can be selected directly. Verify phone country code and number, answer experience questions concisely, and submit from the final review page.
- Some LinkedIn Easy Apply flows ask years of experience for a named technology (including one the candidate has not used); enter 0 when accurate rather than leaving the required field blank, and record the question for future Q&A maintenance.
- O2 AI AI Engineer flow used five pages: contact info with required phone number, saved-resume selection, optional Top Choice, US work authorization, and review. The saved resume was preselected; leaving Top Choice unchecked and selecting Yes for US work authorization allowed submission.
- A LinkedIn Easy Apply flow for a hybrid AI Engineer role used six pages: contact info, resume upload, optional Top Choice, hybrid-setting question, US work authorization and future sponsorship, then review. For an F-1 OPT candidate, answer authorized to work Yes and future sponsorship Yes.
- A Saragossa Easy Apply flow used four pages: Contact info, Resume, Work authorization, and Review. The saved resume may be preselected; uploading the provided PDF is also supported and produces a successful-upload notification. For candidates on F-1 OPT who will need future employment sponsorship, answer Yes to the sponsorship question, then review and submit.
- Staffing Spot Easy Apply flow via PyjamaHR consisted of four pages: Contact info (phone and city autocomplete), saved resume selection, work experience review, and final review. The saved AI/ML resume was preselected; selecting the city autocomplete suggestion and proceeding through Review led to successful submission.
- VBeyond Easy Apply flow used four pages: Contact info, resume upload, Additional Questions, and Review. Required experience questions accepted concise numeric text answers; uploading the PDF produced a successful-upload notification, and the final confirmation stated the application was sent.
- Top Stack Group external applications use a short Boostie-hosted flow: email, contact information with resume upload, eligibility/sponsorship questions, availability date, onsite preference, review, and submit.
- Alight external applications use a multi-step portal: personal information and resume upload, work/education, application questions, voluntary EEO, disability, and review. The portal can parse the uploaded PDF into experience and education fields, but verify dates, degree, GPA, location, and social URLs. For F-1 OPT, answer US work authorization Yes and future sponsorship Yes. Required background/drug screening, prior employment, relative, EEO, and disability questions may need explicit profile answers; select the portal's exact option values. On review, target the application submit button by its distinguishing attribute (such as `atm-id="submit-button"`) because Simplify may inject a second similarly named submit control. For F-1 OPT candidates, answer US/Canada work eligibility Yes, future sponsorship Yes, and onsite preference according to the candidate profile.
