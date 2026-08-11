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
