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
- Ashby forms may prefill the candidate's current city while separately requiring a relocation/office willingness Yes/No control; select the visible Yes button within the exact question container so the hidden checkbox state commits before submission.
- On long single-page forms, the required Location control may be a separate `Start typing...` combobox even when another optional location-like text field is present. Type the candidate's city, wait for the listbox, and select the exact city/state/country option. Hidden segmented Yes/No inputs are not directly clickable; use the visible Yes/No buttons and verify checked state before submitting.
- Ashby forms may have a required hub-location radio group for candidates outside listed hubs. If the candidate is open to relocation, select the exact option stating they are outside the hubs but able to relocate; also select a valid source checkbox such as LinkedIn. Resume autofill can populate legal name, email, phone, LinkedIn URL, and current location, but still verify required preferred-name fields.
- On Edra's Ashby form, Simplify autofill populated contact/resume data but left the office-availability segmented Yes/No control uncommitted. A normal click could time out; a forced click on the visible Yes button committed the hidden checkbox (verify `input[type=checkbox].checked`) before submitting. The form then showed the standard success confirmation.
- Coframe's Ashby application used a single-page form with Simplify-prefilled contact details and resume, a required location autocomplete, and one required narrative question. Select the exact location suggestion before submitting; a concise, truthful project-focused answer is sufficient for the impressive-build prompt. Confirm the inline “Your application was successfully submitted” status.
- Ashby forms can expose hard eligibility gates (for example, U.S. citizenship, security clearance, or application-frequency limits) alongside the normal fields. Scan the role description and application questions first; if the candidate is truthfully ineligible for a stated mandatory requirement, do not submit or misrepresent eligibility.
