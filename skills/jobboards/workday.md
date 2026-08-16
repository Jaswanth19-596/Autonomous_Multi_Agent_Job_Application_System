

# Reusable workflow notes
- NVIDIA-style Workday flows may require Google SSO before the resume-upload step; after SSO, upload through the visible `data-automation-id="select-files"` button, then continue.
- Some Workday footer buttons can be obstructed by browser overlays even when enabled; if a normal click times out, use the uniquely identified `data-automation-id="pageFooterNextButton"` with a forced Playwright click once the page has been scanned.
- Review the parsed Work Experience carefully: autofill may add historical roles not present in the supplied resume; retain only profile-supported entries when possible.

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
