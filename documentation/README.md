### Overview
### What this system is

This is an improved online medical consultation form system

What exists now:
- An e-consultation form accessed through the GP surgery website
- Patient picks a presenting complaint
- Once confirmed, system asks the user to type a free text response
- That response is added to the output verbatim, not processed further in any way
- The system then asks a series of questions, even if answered in the free text response

Planned improvements
- Based on the presenting complaint, our system will have a series of questions or data points that are required (overlapping but different for each presenting complaint)
- For example for urinary symptoms, it will want to know whether there is fever, dysuria, abdominal or pelvic pain, flank pain, shivers/rigors, recent infections etc
- The patient can write a short blurb explaining their presenting complaint
- That blurb is then run through a fast encoder model
- The encoder model will have a series of heads which are boolean classifiers for each required symptom e.g. fever: yes or no and then pre-fills the form based on those answers
- This is about reducing redundancy in forms, not AI driven decisions or conversation

### Documentation 
- Architecture.md - High level architecture decisions
- current_version.md - Overall plan for current phase (currently MVP/V1)
- planned_updates.md - Planned improvements for later versions