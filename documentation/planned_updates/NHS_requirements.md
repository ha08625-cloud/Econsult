## DAPB3051: Identity Verification and Authentication Standard for Health and Care Digital, Data, Analytics and Technology Use
## Submission Data Collection: NHS England collects monthly statistics on OC submissions (clinical vs. administrative). System suppliers are expected to provide this data automatically on behalf of the practices
## Usability and Accessibility: This is a scored section of the DTAC (Digital Technology Assessment Criteria). You are required to meet WCAG 2.2 Level AA standards at a minimum. For an OC form, this means high-contrast modes, screen-reader compatibility, and easy keyboard navigation
## Data protection
## Digital Clinical Safety
## MHRA registration

## DFOCVC (Digital First Online Consultation and Video Consultation) Framework
### 1. Mandatory Operational Availability
* No Capping of Requests: Online consultation systems are explicitly forbidden from capping the number of requests a patient can submit.
* Core Hours "Always On": Systems must remain open for the entire duration of core hours (typically 8:00 AM to 6:30 PM, Monday to Friday) for all request types—clinical, administrative, and medication.
* Urgent Care Safeguards: Your system must display clear banners/messages stating it is not for urgent medical needs and providing instructions on how to access emergency support (e.g., 999 or A&E).

### 2. Technical Capabilities & Interoperability
* Identity Verification (NHS Login): Integration with NHS Login is the mandated standard for verifying patient identity
* Behind this, systems are expected to link to the Personal Demographics Service (PDS) to ensure the patient's NHS Number is captured.
* Clinical Coding (SNOMED CT): To avoid manual data entry by GP staff, clinical outputs should ideally be mapped to SNOMED CT codes
* GP System Integration: While PDF-to-email is a common starting point, the framework pushes toward structured data integration into core clinical systems (like EMIS or SystmOne).

### 3. National Reporting Requirements
* As of early 2026, there is a new contractual requirement for system suppliers to provide "timely data" to NHS England. Your architecture will need to automate the reporting of:
* Access Metrics: This includes data on the volume of clinical vs. administrative submissions, weekday/time distributions, and the rate of submissions per 1,000 registered patients.
* Inequality Monitoring: Data must be provided to help NHS England identify inequalities in access and system performance.

### 4. Usability and Accessibility
* The DTAC Version 2 (published February 2024 with a compliance deadline of April 6, 2026) places heavy emphasis on:
* WCAG 2.2 Compliance: You must meet WCAG 2.2 Level AA standards at a minimum to ensure the tool is usable by all patient groups, including those with disabilities.
* User-Centred Design: Suppliers must demonstrate evidence of user testing and that the tool does not introduce "unwarranted variation" in how care is accessed.
