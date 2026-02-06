That makes sense. Given that im going to be doing this across many different symptoms (and maybe it's a good idea to do it across the noise fragments as well), then perhaps i can think of a way of doing it through code or even a simple excel macro or something. I take some of the common sentence structures and use the code to replace parts of the sentence:
E.g.
I [verb] [adjective] high temperature
Verb list: have had, have got, 've got, have etc
Adjective list: a really, a very, a slightly, a bit of a, a raging etc

This is superior to using an LLM for this specific task because:
 * Zero Hallucination Risk: You know exactly what words are going in.
 * Label Safety: You guarantee the label remains True (whereas an LLM might accidentally rewrite "I have a fever" to "I might have a fever", flipping the label to Null).
 * Auditability: You can see the exact combinatorics in your code.

 * Pipeline Integration: You want your data generation to be part of your build pipeline. Running a Python script is automated; opening Excel is manual.
The Architectural Solution: A "Mad Libs" Generator
Build a simple Python generator using itertools.product. This allows you to define your templates in code (or a config file) and generate the variations programmatically.
Here is the "Senior Dev" way to implement your idea, including a safety mechanism to prevent nonsense like "I have a slightly raging fever" (semantic clash).
1. The Configuration Structure
Instead of hardcoding, define your "slots" and "templates".
# templates.py

# Define the interchangeable parts
SLOTS = {
    "verbs_past": ["have had", "had", "suffered from", "experienced"],
    "verbs_present": ["have", "'ve got", "am suffering from"],
    "intensity_high": ["raging", "very high", "burning", "severe"],
    "intensity_mild": ["slight", "mild", "bit of a"],
    "noun_fever": ["temperature", "fever", "feverishness"],
    "time_indicator": ["since last night", "today", "all day", "recently"]
}

# Define valid sentence structures
TEMPLATES = [
    # Structure 1: Standard statement
    "{verbs_present} a {intensity_high} {noun_fever}",
    
    # Structure 2: Time-first
    "{time_indicator} I {verbs_past} a {intensity_mild} {noun_fever}",
    
    # Structure 3: Short/Colloquial
    "got a {intensity_high} {noun_fever}"
]

2. The Generator Logic
This script generates your 1000 variations instantly.
import itertools

def generate_variations(template, slots):
    # 1. Identify which slots are in this template (e.g. "{verbs_present}")
    needed_keys = [k for k in slots.keys() if f"{{{k}}}" in template]
    
    # 2. Get the lists of words for those slots
    word_lists = [slots[k] for k in needed_keys]
    
    # 3. Create every possible combination (Cartesian product)
    for combination in itertools.product(*word_lists):
        # Map keys to the chosen words
        format_dict = dict(zip(needed_keys, combination))
        
        # Fill the template
        yield template.format(**format_dict)

# Usage
all_examples = []
for t in TEMPLATES:
    for variation in generate_variations(t, SLOTS):
        all_examples.append(variation)

print(f"Generated {len(all_examples)} unique fragments.")
# Output: "have a raging temperature", "have a burning fever", etc.