# Safety design decisions

## Overview
This document details all of the specific design decisions that have been made for safety purposes, whether that is clinical safety or auditability

### Practice name visible on every page
For accessibility reasons, we have minimal patient ID verification on the online consultation form: a name, DOB and postcode.  A small number of patients may use the NHS login which has stronger verification

Patients will not access the online consultation form directly, they will access it through a link on their surgery's webpage, so the risk of accidentally sending a form to the wrong surgery is low but it exists

For that reason, we will display the name of the sugery in the page header on every page and ask patients to confirm that they are sending the form to the correct surgery at the start of the form

### Universal safety warning (contractual obligation)
A universal safety warning is displayed at the start of the form with emergency symptoms e.g. chest pain.  The patient must confirm that they do have these symptoms before continuing

### Condition specific safety warnings
For each condition specified, there are follow up questions that must be answered.  Some of these questions are flag symptoms e.g. fever with urinary symptoms indicating a possible pyelonephritis.  If the patient clicks yes to one of these questions, they are directed to call the duty doctor instead of continuing with the online form
