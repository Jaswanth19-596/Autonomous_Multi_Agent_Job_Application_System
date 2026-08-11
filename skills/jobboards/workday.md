PAGE SCAN
   ↓
Identify all visible dropdowns
   ↓
Classify:
   ├── Independent dropdowns
   └── Dependent/cascading dropdowns
   ↓
Discover options for independent dropdowns
   ↓
Discover parent options for cascading dropdowns
   ↓
Select parent
   ↓
WAIT FOR CHILD DROPDOWN TO APPEAR/UPDATE
   ↓
SCAN ONLY THE NEWLY REVEALED CHILD FIELD
   ↓
Discover child's options
   ↓
Select child
   ↓
DONE


Parent:
Where did you hear about us?

Options:
- LinkedIn
- Indeed
- Employee Referral
- Company Website
- Other

Suppose the user's answer is:

LinkedIn

The agent selects LinkedIn once.

Workday may then reveal:

Which LinkedIn source?
[Recruiter
 LinkedIn Job Search
 LinkedIn Post
 Other]

Additional reusable learnings:
- External LinkedIn applications may open a Workday "Start Your Application" page with Autofill with Resume, Apply Manually, Use My Last Application, and Apply With LinkedIn.
- Workday manual applications can require account creation before the seven-step wizard (Create Account/Sign In → My Information → My Experience → Application Questions → Voluntary Disclosures → Self Identify → Review).
- Apply With LinkedIn opens LinkedIn OAuth in a new tab; when already authenticated, use the Google-backed "Continue as [name]" option if shown, then explicitly click LinkedIn's "Allow" consent button to return to Workday.
- A Workday account-creation attempt may redirect back to Sign In without a usable session; verify login before proceeding. The Forgot Password page only confirms that reset instructions will be sent if an account exists.