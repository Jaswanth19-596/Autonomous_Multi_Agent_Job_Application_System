# Paylocity Recruiting (ATS) - Application Skills

Paylocity runs its own ATS at `https://<customer>.paylocity.com/Recruiting/...` (e.g. job detail `/Recruiting/Jobs/Details/{id}`, apply `/Recruiting/Jobs/Apply/{id}`). It is a custom ATS, NOT Workday/Greenhouse/Lever.

## Application flow: 4-step wizard

1. **Information** - contact info, address, availability, salary, "how did you hear", plus Resume upload, Work History, Education.
2. **Additional Questions** - typically radio questions (previously interviewed, sponsorship, non-compete, US residence).
3. **Optional Identity Questions** - voluntary EEO/demographics. Can be skipped entirely.
4. **Review & Submit** - summary of everything, then EEO (optional), Work Authorization (REQUIRED Yes/No), acknowledgement checkbox (REQUIRED), Submit.

## Key mechanics

- **Resume upload**: click "Select Resume to Upload". The "Fill out application with my resume" checkbox (checked by default) triggers resume parsing that auto-fills name, email, phone, city/state, work history, education. A file chooser still must be handled with the upload tool.
- **Address autocomplete**: Address Line 1 is a Google-Places-like autocomplete combobox. After typing, WAIT for the suggestion listbox, then click the suggested option - this populates address, city, county, state and ZIP together. Do not skip the suggestion.
- **Custom dropdowns are NOT `<select>` elements** (React Widgets `rw-dropdownlist`). Click the combobox to open the listbox, then click the desired `option`. Selecting via native select-option APIs fails.
- **Date fields**: "Available to Start" and month/year fields use masked inputs. The stored input value for the date is ISO (`YYYY-MM-DD`). Reliable approach: open the calendar button, choose month/year from the dropdowns, then click the day. Programmatic value setting requires the native setter + input/change dispatch, and stale "required" validation messages may persist until you trigger a form action (e.g. click Next).
- **Auto-parsed email** may show a spurious "invalid email" warning; re-enter the value to clear it.
- **Step 4 required fields**: Work Authorization (Yes/No) and the acknowledgement checkbox must be set before Submit.
- **Success**: submitting navigates to `/Recruiting/Jobs/Success/{id}` with "Your application has been received!".

## Notes
- A cookie/privacy dialog ("Accept All Cookies") appears on load; dismiss it first.
- "Country" default is United States; mobile number formatted `(219) 466-5564` works.
- Optional demographic selects on steps 3-4 can be left at "--" (prefer not to answer).

## Field-level mechanics (verified)
- **Address autocomplete**: The address input (`#public-site-address-address-1`) only shows the suggestion listbox if text is typed with key events. `page.fill()` does NOT trigger it - use `pressSequentially()` (slow typing). The suggestion listbox is `#public-site-address-address-1-autocomplete-list`; click its `[role="option"]` (e.g. "6719 Schneider Ave, Hammond, IN 46323") to populate address-1, city, county (Lake), state (IN) and ZIP (46323-1407) in one shot. It is NOT Google Places `.pac-container`.
- **Input IDs contain dots** (e.g. `info.dateAvailableToStart`, `info.haveYouWorkedWithUsBefore`). `document.querySelector('#info.dateAvailableToStart')` returns null because the dots are read as class selectors - always use the attribute selector `[id="info.dateAvailableToStart"]`.
- **Date fields (e.g. Available to Start)**: reacts to the native value setter. Set ISO value `YYYY-MM-DD` (date of choice) via `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set`, then dispatch `input`, `change`, and `blur`. It renders correctly (e.g. `08/16/2026`) on the Step 4 review page.
- **"This appears to be an invalid email" warning** sometimes shows after resume auto-parse even for valid addresses; re-typing the email clears it.
- **Acknowledgement checkbox**: after checking, a stale "Please accept the acknowledgement" inline warning may linger even though the checkbox state is truly `checked`; clicking Submit still succeeds (navigates to `/Recruiting/Jobs/Success/{id}`).
- **Certifications & Awards** is a tag input: type text and press Enter for each award; tags appear as removable chips.
- **Step 2 extra questions** are all plain radio lists (previously interviewed, sponsorship, non-compete, US residency) - use confirmed profile details only; ask the user for any unknown answer.
- Old findings confirmed: custom dropdowns are React Widgets (open the combobox, click `role=option`), and Step 3 demographics can be skipped entirely.
