

# Reusable workflow notes
- NVIDIA-style Workday flows may require Google SSO before the resume-upload step; after SSO, upload through the visible `data-automation-id="select-files"` button, then continue.
- Some Workday footer buttons can be obstructed by browser overlays even when enabled; if a normal click times out, use the uniquely identified `data-automation-id="pageFooterNextButton"` with a forced Playwright click once the page has been scanned.
- Review the parsed Work Experience carefully: autofill may add historical roles not present in the supplied resume; retain only profile-supported entries when possible.

# Additional reusable learnings
- Philips Workday variant: after resume autofill, review Work Experience and remove unsupported entries; mark current employment with the visible “I currently work here” checkbox to avoid invalid end-date validation. Degree dropdown may use broad options such as “Master” rather than “Master of Science”. Resume upload requires clicking “Select files” first to open the file chooser. Review page can show duplicate resume entries; verify the intended PDF is present before submitting.

- Proofpoint Workday application flow used seven steps: Autofill with Resume, My Information, My Experience, Application Questions, Voluntary Disclosures, Self Identify, and Review. Resume parsing can add unsupported prior work experience; remove entries not present in the supplied profile before continuing.
- On this Workday variant, the source field may already be prefilled as LinkedIn; the source helper can fail to expand an already-selected control, but the existing selection is acceptable. Required custom dropdown options may use long exact labels rather than a simple Yes/No (for example, non-compete questions).
- Self-identification may have required terms consent and disability form fields. Simplify may prefill language, demographic selections, the current date, and the correct disability response; inspect the checkbox states before advancing.

# 1. Use Simplify as much as possible

Workday applications are very complex. Use simplify autofill as much as possible. It will fill most of the fields of the application, only for fields which are not filled, you can fill them manually. Make sure to use the simplify tool on every new page. This is very important. 

If Simplify's panel shows **"Select skills to autofill"**, call
`simplify_autofill_all_skills`. It selects the panel's **Select all** option,
starts **Autofill N Skills**, and waits for Simplify; do not manually click
individual skills or continue interacting with Workday until the tool returns.

# 2. How did you hear about us

When **"How did you hear about us?"** or **"Where did you hear about us?"**
is visible, call `select_workday_hear_about_us`. It chooses the first usable
option, then follows and completes any dependent dropdown or radio hierarchy.
Do not manually select the source options or request a user answer for this
question.

# 3. Account creation in Workday 

Sometimes when you click on Apply, it will ask you to create an account. In that case, create an account and fill the application.

Additional reusable learnings:
- On Huron-style Workday flows, account creation may redirect immediately to Sign In without establishing a session. Verify credentials once; if sign-in fails, use Forgot Password once and check for the reset email. If no email arrives, stop rather than repeatedly retrying.

- If Workday account creation redirects to the generic sign-in page, verify the new credentials before proceeding; if sign-in fails and no activation/reset email arrives, stop rather than repeatedly retrying to avoid account lockout.
- External LinkedIn applications may open a Workday "Start Your Application" page with Autofill with Resume, Apply Manually, Use My Last Application, and Apply With LinkedIn.
- Workday manual applications can require account creation before the seven-step wizard (Create Account/Sign In → My Information → My Experience → Application Questions → Voluntary Disclosures → Self Identify → Review).
- Apply With LinkedIn opens LinkedIn OAuth in a new tab; when already authenticated, use the Google-backed "Continue as [name]" option if shown, then explicitly click LinkedIn's "Allow" consent button to return to Workday.
- A Workday account-creation attempt may redirect back to Sign In without a usable session; verify login before proceeding. The Forgot Password page only confirms that reset instructions will be sent if an account exists.
- On Huron's manual wizard, the prior-employment radio must be explicitly clicked; attempting to pass `false` through a generic form-fill call can leave the required radio unanswered.
- Simplify may create language rows with incomplete proficiency values. Complete any required blank proficiency dropdowns before continuing; otherwise the wizard may appear to advance but retain validation errors.
- On Huron applications, resume upload may complete through the custom upload widget even when the generic file-upload tool does not detect a modal; verify the uploaded filename in the DOM before proceeding.
- Huron's Self Identify step may prefill the current date and disability choice; inspect checkbox state and only complete missing required fields before advancing.
- Some Workday forms render later-step required fields in the same DOM and block Save and Continue from My Information until those fields are completed. Education school controls may be multiselect-backed and return “No Items” even for a valid profile institution; do not replace the school with an invented value—report the blocking validation if no supported option is available.
- Workday voluntary disability forms may use custom checkbox controls whose input IDs begin with digits; click the associated `label[for="..."]` rather than the input selector directly, then verify the checkbox is checked. The date field validates against the site's current date, so correct the date if “Enter today's date” appears.
- PURE Workday application questions may validate salary as a plain numeric value; enter a single reasonable number such as `90000` rather than a formatted range, because punctuation and ranges can be concatenated and trigger a “number too large” error.
- On review pages, Simplify may inject a duplicate “Submit Application” proxy button. Target Workday’s exact `button[data-automation-id="pageFooterNextButton"]` to submit and verify the “Application Submitted” confirmation dialog.
- Vanguard's Workday My Information page may render “How Did You Hear About Us?” as a multiselect with a Search textbox. The automated source helper can report success while leaving the field invalid/at 0 items selected; inspect the field after helper completion, and if it remains invalid, treat the form as blocked rather than repeatedly reopening it.
- Some Workday education school multiselects return only “No Items” even when the candidate's supported university is valid. Try each supported campus once; if both return no items, treat the application as blocked rather than entering an invented school.
- Resume autofill may alter supported education values (for example, campus naming or GPA) and add unsupported work history; compare every parsed entry against the profile before proceeding, remove unsupported roles, and correct school/GPA.
- Workday disability self-identification choices may be custom checkbox/label controls rather than radios; target the exact label's `for` attribute when a text click does not commit the selection.
