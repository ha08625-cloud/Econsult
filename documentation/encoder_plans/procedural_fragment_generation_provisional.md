# Provisional plan for procedural fragment generation

## Scope

Instead of trying to tackle arch_training.md 12.1 as a single step, it will be easier to break it down into small manageable tickets and iterate to improve.  
Suggested first step pairs well with multi-symptom fragment generation

## Design Decisions

### DD1 Symptom grouping

So far all the fragment libraries are LLM generated. 
Once we start to include more than one symptom, the number of fragment libraries starts to grow exponentially:
For two fragments we can have A, B, or A&B, 
For three fragments we can have A, B, C, A&B, A&C, B&C or A&B&C each with boolean true/false states
We simply dont have the time to use a LLM to create that many permutations of fragment libraries for 50 conditions, each with ~6 symptoms

Proposed first small step is create sentences that are simple declarative sentences without any confounding element:
"I have had [SYMPTOM A] and [SYMPTOM B]"
"I have had [SYMPTOM A] but not [SYMPTOM B]"
"I have had [SYMPTOM A], [SYMPTOM B] and [SYMPTOM C]"
"I have had [SYMPTOM A] and [SYMPTOM B] but not [SYMPTOM C]"
etc
Let's do it up to four fragments - I think someone writing 5 or 6 symptoms in a single sentence is unrealistic and by the time we get to 5, the exponential growth of combinations becomes a real headache for minimal gain

Superficially it looks like we would need boolean states for all symptoms e.g.:
1 Symptom: 2 combinations (True, False)
2 Symptoms: 4 combinations (e.g., True/True, True/False, False/True, False/False)
3 Symptoms: 8 combinations
4 Symptoms: 16 combinations

In reality the ones that have or or two sequential blocks of true and false sound natural, for example:
"I haven't had any pain peeing or fever, but I have had nocturia"

but the ones that switch between true and false more than once are unnatural:
I have had dysuria (true), but not fever (false) and urinary frequency (true)

So for three symptoms, these would be correct:
1. TTT
2. TTF
3. TFF
4. FFF
5. FFT
6. FTT
But not FTF or TFT which sound odd

An easier method is that the generation engine should simply group by boolean state before constructing the sentence.
This reduces the template count entirely. Instead of tracking sequence permutations (TTTF, TTFF, FTTT), you only need to build templates based on the Count of Trues vs. Count of Falses. 
For 3 symptoms, you only have 4 logical states one way: 3T/0F, 2T/1F, 1T/2F, 0T/3F, and 4 logical states the other way 3F/0T, 2F/1T, 1F/2T, 0F/3T (and of course 3F/0T and 0T/3F are the same and can be deduplicated)
Permutations starting with false clauses are necessary as patients do speak like that, so we shouldnt aim to deduplicate 2T/1F and 1F/2T - both are useful for training purposes

### DD2 Part-of-Speech Matching: 

Slotted fragments must cleanly follow the chosen declarative opener ("I have had..."). Nouns ("a fever") and gerunds ("vomiting") work perfectly. 
Adjectives ("feverish") or full clauses ("it burns when I pee") will break the sentence structure if they aren't standardized and may require a new sentence template (see out of scope section)

### DD3 Conjunction Rules: The templates must dynamically adapt conjunctions based on the boolean states. Positive lists require "and" (A, B, and C), purely negative lists require "or" (not A, B, or C), and mixed states require adversative structures (A and B, but not C).

The engine will also need a tiny logic block to handle the Oxford comma and conjunctions correctly based on array length:
Array length 1: [0]
Array length 2: [0] and [1] (or [0] or [1] for negatives)
Array length 3+: [0], [1], and [2]

### DD4 Bases

"I have had..." works for sentences starting with T. However, sentences starting F: "I have had not symptom A, B, or C" are incorrect. 
The template engine must also support a Positive Base ("I have had...") and a Negative Base ("I have not had..." / "I haven't had..."). If the grouped list starts with Falses, it must use the Negative Base.

## Phase 1: Boolean State Grouping & Template Mapping

The engine will sort the selected symptoms to group all `True` values together and all `False` values together. This leaves us with two bases and a strict set of transitions.

**Group 1: Positive Base ("I have had...")**

* **1 Symptom (1T):** "I have had A."
* **2 Symptoms (2T):** "I have had A and B."
* **3 Symptoms (3T):** "I have had A, B, and C."
* **4 Symptoms (4T):** "I have had A, B, C, and D."
* **Mixed (T $\rightarrow$ F):** "I have had [Positive List], but not [Negative List]."
* *Examples:* 1T/1F, 2T/1F, 1T/2F, 3T/1F, 2T/2F, 1T/3F.



**Group 2: Negative Base ("I have not had...")**

* **1 Symptom (1F):** "I have not had A."
* **2 Symptoms (2F):** "I have not had A or B."
* **3 Symptoms (3F):** "I have not had A, B, or C."
* **4 Symptoms (4F):** "I have not had A, B, C, or D."
* **Mixed (F $\rightarrow$ T):** "I have not had [Negative List], but I have had [Positive List]."
* *Examples:* 1F/1T, 2F/1T, 1F/2T, 3F/1T, 2F/2T, 1F/3T.



## Phase 2: Array Conjunction & Punctuation Engine

Lightweight utility function to format the arrays before they are injected into the templates. The function must accept the array of strings and a boolean indicating whether it is a positive or negative list.
* **Length 1:** `return array[0]`
* **Length 2:** `return f"{array[0]} {conjunction} {array[1]}"`
* *(If positive, conjunction = "and". If negative, conjunction = "or".)*

* **Length 3+:** `return f"{', '.join(array[:-1])}, {conjunction} {array[-1]}"`

## Phase 3: Lexical Constraints (Part-of-Speech)

To ensure the slotted fragments do not break the declarative structure, create a strict validation step for the symptom dictionaries used in this step.

* **Allowed:** Nouns (e.g., "a fever", "nocturia") and Gerunds (e.g., "vomiting", "pain peeing").
* **Excluded for now:** Adjectives ("feverish"), full clauses ("it burns when I pee"), and null states.
* **Action:** Audit the existing 40 examples generated by the LLM for the target conditions and isolate only the noun/gerund variants into a specific `v1_declarative` fragment library.

## Phase 4: Execution Flow

1. **Select:** Randomly select $N$ symptoms (1 to 4) for a specific condition.
2. **Assign:** Assign T/F values to each symptom.
3. **Sort:** Order the symptoms so that all `True` values are clustered and all `False` values are clustered (either T $\rightarrow$ F, or F $\rightarrow$ T).
4. **Format:** Pass the T cluster to the Array Engine (with `is_positive=True`) and the F cluster to the Array Engine (with `is_positive=False`).
5. **Inject:** Inject the formatted strings into the corresponding Base Template from Phase 1.

## Open questions
* Labelling policy
* Is now the time to switch from txt files to json or jsonl files to make labelling easier?

## Out of scope
* Templates that use adjectives instead of nouns e.g. I've been feverish or I havent been urinating frequently
* Using existing fragment libraries as templates (this might remove the need for cluster marking)
* Swapping out the first part "I have had" for "I've had" or "I've been having" or "I've got" etc
* Adding openers like "For the last three days" or "Since I got back from holiday"
* Null states are also out of scope for now and may be more complex
* Round robin selection - once a fragment is used, the next time the generation engine picks it up, an altered fragment is used.  e.g. first time round "I have had a fever and dysuria"+"TANGENT", second time round "I've had a high temperature and pain urinating"+"EXPECTATION"
