# Ashby (jobs.ashbyhq.com)

General notes for applying on Ashby-hosted job boards.

- Job list is at `https://jobs.ashbyhq.com/<company>`; each role links to `/sea12/<role-id>` or
  `.../<role-id>/application` for the application form directly.
- The apply button is "Apply for this Job", which navigates to the `/application` URL.
- Application form fields are standard: Name*, Email*, Resume* (file upload), plus optional
  employer-specific questions (e.g. "When can you start?", "Additional Information").
- Resume upload: clicking "Upload File" opens a native file chooser; use the browser file-upload
  tool against that chooser (must click the button first to create the modal state).
- Fields are cheap to fill via the role-based textbox selectors.
- "When can you start?" date field accepts MM/DD/YYYY typed directly.
- Success is confirmed inline via a "Success — Your application was successfully submitted"
  status message after clicking "Submit Application". Requires explicit user approval before
  clicking Submit (irreversible).
- Embedded Ashby forms may be hosted inside an iframe on an employer careers page; scope inspection and interaction to the Ashby frame.
- Location autocomplete fields require selecting a returned suggestion, and required multi-select relocation fields must be explicitly selected before submission.
- For custom segmented Yes/No controls and hidden checkbox/radio inputs, clicking the associated label or visible option may be more reliable than interacting with the input directly.
- Ashby application pages may have required custom yes/no questions for U.S. work authorization, future sponsorship, and willingness to meet an onsite schedule; inspect the hidden checkbox state and select the visible Yes/No button directly.
- For AI/agent roles, concise responses that distinguish production LLM/agent deployment from formal customer-facing experience can accurately address prompt/agent and customer-solution narrative questions.
- Ashby applications may include required role-specific certification questions plus optional EEO radio groups. Verify the prefilled EEO selections, answer certification questions only from the candidate profile, and use the site's exact Yes/No segmented controls.
- A resume may already be attached from prior autofill; verify the filename and avoid replacing it unnecessarily. Required work-authorization, sponsorship, certification, and compensation fields can appear on a single-page form.
- LangChain's Ashby form used a location autocomplete and segmented sponsorship Yes/No buttons; select the exact location suggestion before submitting, and target the segmented No/Yes button by its accessible role when duplicate text exists elsewhere on the page.
