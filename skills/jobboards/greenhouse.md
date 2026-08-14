# Greenhouse Applications

- Greenhouse job-board forms often use React Select custom comboboxes (`#question_XXXX`).
- **Filling React Select comboboxes:** Type the desired value directly into the combobox input or click the target option element directly by text (`:has-text('...')`). Do NOT open dropdowns and press `Escape` in a loop to pre-scan options.
- External Air applications can require citizenship-status, onsite availability, office-location, prior-application, employer-agreement, compensation, and start-date questions.
- Resume upload is enforced at submission (`#resume`); use local file path `/Users/jaswanth/mydocs/myprojects/langgraph/user_details/resume.pdf`.
- Voluntary demographic fields can be left unanswered or set to the appropriate decline/no-answer option.
- Location (City) is a Google-places style autocomplete: type slowly, wait for the suggestion list, then click the matching option (e.g. 'City, State, United States') to commit; a stale 'Please enter your location' message can linger but clears once the option is selected.
- Country field is a phone-dial-code combobox; selecting the country also formats the Phone number with the correct country code automatically.
- Resume upload can be done by setting the file on the #resume input directly via page.setInputFiles before the page shows it; the uploaded filename is then shown with a Remove button.
- Some Greenhouse forms use a shared role=option menu containing phone-country entries plus application choices; after opening a custom dropdown, select the exact visible application option by text and avoid reopening completed fields.
- Impact.com Greenhouse applications may present a required relocation question as a React-Select combobox. Typing text alone can leave the field invalid; open the menu and click the exact `role=option` (for example, Yes) to commit the selection before submitting.
- On this Greenhouse layout, Simplify can prefill contact details and upload a saved resume. Required free-text questions may include a role-specific hiring rationale and compensation expectations; the form can be submitted directly after required custom fields are committed.
- Preferred First Name, Cover Letter, Website, and LinkedIn are optional fields; only fields marked with * are required.
- Greenhouse may display a Simplify banner stating that the job was already applied to; treat that as an existing successful application and avoid submitting a duplicate.
- The 'Autofill my application' (Simplify) button may open a separate MyGreenhouse tab for authentication; you can proceed filling the Greenhouse form manually in the original tab.
- On Greenhouse forms with a required Location (City) React Select, clear any autofill text completely, type the city slowly, then choose the exact `City, State, United States` option from the visible role=option list before submitting.
