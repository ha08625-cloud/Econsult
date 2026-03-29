# Safety design decisions

## Overview
This document details all of the specific design decisions that have been made for safety purposes, whether that is clinical safety or auditability

### Practice name visible on every page
For accessibility reasons, we only have light patient ID verification on the online consultation form: a name, DOB and postcode.  A small number of patients may use the NHS login which has stronger verification

Patients will not access the online consultation form directly, they will access it through a link on their surgery's webpage, so the risk of accidentally sending a form to the wrong surgery is low but it exists

For that reason, we will display the name of the surgery in the page header on every page and ask patients to confirm that they are sending the form to the correct surgery at the start of the form

### Universal safety warning (contractual obligation)
A universal safety warning is displayed at the start of the form with emergency symptoms e.g. chest pain.  The patient must confirm that they do have these symptoms before continuing

### Condition specific safety warnings
For each condition specified, there are follow up questions that must be answered.  Some of these questions are flag symptoms e.g. fever with urinary symptoms indicating a possible pyelonephritis.  If the patient clicks yes to one of these questions, they are directed to call the duty doctor instead of continuing with the online form

### Form delivery failure
If a form is completed but cannot be sent (for example email server is temporarily down), then there will be mitigations to make sure that the form is not lost and is available to the practice in a timely manner:
1. Firstly the form is kept in a database and will only be deleted once delivery has been confirmed
2. The system will attempt to resend the form at intervals of 1, 10 and 60 minutes
3. If the email delivery continues to fail, then the system will attempt to send the email through an alternative delivery system
4. If that is also unavailable, then the form will be accessible by manual download through the admin portal

Backup photo processing
1. If patients upload images, they are larger files and require more memory to process
2. If several patients try to upload pictures at the exact same time, the memory requirement can exceed what thevsustem is capable of, leading to a crash (OOM)
3. So we will implement a queueing system to prevent the system trying to work on multiple files at the same time