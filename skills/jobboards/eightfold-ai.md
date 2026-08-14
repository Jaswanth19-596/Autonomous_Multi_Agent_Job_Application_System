# Eightfold AI job-board skill
- Eightfold AI custom comboboxes render their option list only after the field is clicked and text is typed; the semantic fill_dropdowns tool may return option_not_found because options are not statically available. Fill by clicking the combobox, typing/selecting, then clicking the exact option in the opened listbox.
- Selecting a parent combobox can reveal a dependent/child required combobox (e.g., the 'Source' option reveals a required 'Source Detail' field), which must also be filled before the page validates.
- YesNo 'radiogroups' render option labels as spans overlaid by an actual radio input. Clicking the visible label text is intercepted, so select by checking the underlying input[type=radio] with force and matching on its aria-label prefix.
- fill_application_page can report radio answers as filled_and_verified even when they were not actually selected; re-inspect validation after submit (look for 'Select a value' errors) and select the radios directly.
- Resume upload: setInputFiles on the hidden file input resets to 0 after processing and may not persist; instead trigger the file chooser (click the file input element) and complete it with chooser.setFiles, then verify the uploaded filename appears in the upload-list item.
- The application is a single-page form; final submission is via the 'Submit application' button and an invisible reCAPTCHA runs automatically on submit without a visible challenge.
- Submission success is confirmed by navigation to /careers/apply/success with a 'Thank you for your application' message.
