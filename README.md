# Paper to Playground

The three developer subsystems are integrated on `Hussein/Integration`.
See [INTEGRATION.md](INTEGRATION.md) for current setup, CLI usage and verification.

## Master Architecture, Implementation Specification, and Coding-Agent Contract

> **Purpose of this document**
>
> This README is not merely project documentation. It is the
> implementation contract for the first coding-agent pass. The coding
> agent should treat every requirement marked **MUST**, **MUST NOT**,
> **SHOULD**, and **LOCKED** as deliberate. Do not simplify, replace, or
> reinterpret the architecture merely because another implementation
> would be easier.
>
> The objective is to implement the complete system described here in
> one coherent pass, with tests, fallbacks, validation, and
> submission-contract compliance built in from the beginning rather than
> added after the core generator is written.

------------------------------------------------------------------------

# 0. Executive Summary

**Paper to Playground** is an autonomous
research-paper-to-interactive-learning compiler.

The program receives exactly three case fields:

``` json
{
  "source_url": "./paper.pdf",
  "focus": "the mechanism described by Equation 6",
  "audience": "second-year engineering undergraduate"
}
```

The evaluator invokes:

``` bash
python -m pip install -r requirements.txt
python agent.py --input case.json --output out --model MODEL_ID
```

The successful run produces:

``` text
out/
├── index.html
└── trace.jsonl
```

`index.html` is a single, self-contained, browser-ready, offline
interactive scientific explanation.

`trace.jsonl` is a concise machine-readable execution trace describing
the pipeline stages, model calls, token usage, validation results,
failures, repairs, fallbacks, and finalization outcome without exposing
secrets or hidden reasoning.

The system is **not** a one-shot "paper -\> LLM -\> HTML" generator.

The architecture is:

``` text
SOURCE
  ↓
UNDERSTAND
  ↓
RETRIEVE EVIDENCE
  ↓
FORMALIZE SCIENCE
  ↓
DESIGN PEDAGOGY
  ↓
BUILD EXECUTABLE COMPUTATION
  ↓
RENDER WITH PRE-ENGINEERED SCIENTIFIC UI
  ↓
EXECUTE
  ↓
VERIFY
  ↓
REPAIR / FALLBACK IF NECESSARY
  ↓
FINAL VERIFIED PLAYGROUND
```

The mnemonic for the entire system is:

> **Understand -\> Formalize -\> Teach -\> Generate -\> Execute -\>
> Verify -\> Repair**

The responsibility split is equally important:

``` text
DeepSeek V4.1 Flash
= semantic scientific reasoning and pedagogical decisions

Python
= orchestration, source processing, retrieval, contracts, deterministic computation,
  validation, fallback control, tracing, reliability

Scientific UI Runtime
= polished deterministic presentation and interaction

Evidence System
= source truth and provenance

Canonical Computation AST
= executable scientific truth

Browser Validator
= proof that the generated lesson actually behaves correctly

Orchestrator
= the autonomous agent
```

------------------------------------------------------------------------

# 1. Non-Negotiable Assignment Contract

The implementation MUST satisfy the assessment contract before any
optional engineering improvement is considered.

## 1.1 Runtime

-   Python **3.11**.
-   Root entry point MUST be `agent.py`.
-   Root dependency file MUST be `requirements.txt`.
-   Dependencies MUST be installable using only:

``` bash
python -m pip install -r requirements.txt
```

-   No GPU requirement.
-   No required Docker execution.
-   No required external server.
-   No npm build.
-   No system-package installation.
-   No manual setup beyond pip installation and the supplied
    environment/API key.
-   Docker MAY be used by developers privately if desired, but MUST NOT
    be required by the evaluator.

## 1.2 Required invocation

The following command MUST work exactly:

``` bash
python agent.py --input case.json --output out --model MODEL_ID
```

The public CLI SHOULD remain minimal. Internal tuning options are not
part of the evaluator contract.

## 1.3 Input schema

The professor clarified that the brief's reference to "five required
string fields" is a typo.

There are exactly **three required string fields**:

``` json
{
  "source_url": "...",
  "focus": "...",
  "audience": "..."
}
```

Rules:

-   `source_url` MUST support a local paper path.
-   `source_url` SHOULD also support HTTP/HTTPS paper URLs.
-   A `file://` source MAY be supported.
-   Local sources are preferred for assessment reliability.
-   `focus` MUST be preserved exactly as provided for semantic intent.
-   `audience` MUST be preserved exactly as provided for semantic
    intent.
-   Normalized variants MAY be created for retrieval, but MUST NOT
    overwrite the originals.
-   Missing, non-string, or empty required fields MUST fail early with a
    structured trace event and non-zero exit.
-   Production logic MUST NOT require extra case fields.

## 1.4 Model constraint

All model-based work MUST use the supplied `MODEL_ID`.

The professor clarified that **DeepSeek V4.1 Flash is the only permitted
model** for model-based work.

Therefore:

-   Every OpenRouter request MUST use `--model MODEL_ID` unchanged.
-   No fallback model.
-   No secondary model.
-   No JEV.
-   No local LLM.
-   No embedding model.
-   No VLM dependency unless the exact supplied DeepSeek interface is
    verified to support image input, and even then multimodality MUST
    remain optional rather than required.
-   The implementation MUST NOT reject the evaluator's model identifier
    merely because its literal spelling differs from a development-time
    expectation.

## 1.5 API key

The OpenRouter key MUST be read from:

``` text
OPENROUTER_API_KEY
```

The key MUST NEVER appear in:

-   source code,
-   generated HTML,
-   trace output,
-   console diagnostics,
-   prompts stored in trace,
-   committed files,
-   test fixtures.

## 1.6 Assessment resource limits

The implementation MUST respect:

-   maximum 10 model/API requests per case, including retries;
-   maximum 30,000 total completion tokens per case;
-   maximum 10-minute case runtime.

The architecture SHOULD use much less than the ceilings.

Target behavior:

-   normal successful run: approximately 1 major semantic call;
-   common exceptional run: 2-3 calls;
-   difficult run: approximately 4 calls;
-   never spend calls merely because the limit permits them.

## 1.7 Required output

Successful execution MUST create:

``` text
out/index.html
out/trace.jsonl
```

`index.html` MUST be:

-   a single file;
-   self-contained;
-   browser-ready;
-   usable offline;
-   no API key required;
-   no CDN;
-   no remote fonts;
-   no remote JavaScript;
-   no required remote images;
-   no runtime server;
-   no network dependency;
-   no build step.

CSS, JS, visuals, manifest, scientific state, and educational content
MUST be embedded.

`trace.jsonl` MUST contain one JSON object per line and MUST include
meaningful stage/action/result information.

## 1.8 Exit codes

-   Exit `0` only when the required output contract has been produced
    and the run meets the implementation's success gate.
-   Exit non-zero on fatal failure.
-   Preserve useful diagnostics and partial artifacts when possible.
-   Do not claim success when `index.html` is absent or unusable.

------------------------------------------------------------------------

# 2. Product Definition

The product is a **general-purpose reusable generator**, not a solution
for one paper.

The evaluator will use hidden examples. The implementation MUST
therefore avoid special-casing public examples or named papers.

The generator transforms a focused research-paper mechanism into an
interactive educational explanation appropriate for an engineering
undergraduate.

It does **not** attempt to:

-   summarize the entire paper;
-   reproduce full training procedures;
-   reproduce complete experimental results;
-   build a paper chatbot;
-   build a RAG Q&A interface;
-   copy paper figures;
-   generate decorative web pages;
-   create agents merely to increase the agent count.

The target is a focused mechanism or quantitative relationship that can
be explained with small inputs.

------------------------------------------------------------------------

# 3. Global Success Priorities

When trade-offs exist, use this priority order:

1.  scientific fidelity;
2.  reliability;
3.  teaching clarity;
4.  meaningful visualization;
5.  meaningful interaction;
6.  verifiable autonomous checking;
7.  token efficiency;
8.  latency;
9.  cosmetic polish.

Efficiency optimization begins only after quality is stable.

Never save tokens by materially increasing scientific failure
probability.

------------------------------------------------------------------------

# 4. Core Architecture Philosophy

## 4.1 Compiler architecture

Treat the system as a compiler:

``` text
Research source
   ↓
PaperDocument
   ↓
Evidence Pack
   ↓
Scientific Model
   ↓
Lesson Spec
   ↓
Explanation IR
   ↓
Computation AST + Visual/Interaction Plan
   ↓
Scientific UI Runtime
   ↓
index.html
```

Every boundary MUST have a structured contract.

## 4.2 Understand first, generate second

Never implement:

``` text
paper text -> "make a webpage" -> HTML
```

The source MUST be understood and formalized before artifact generation.

## 4.3 Push competence into deterministic infrastructure

DeepSeek is a limited resource.

Do not ask it to perform tasks deterministic software can do reliably:

-   PDF byte parsing;
-   page extraction;
-   heading discovery;
-   exact-reference lookup;
-   BM25;
-   HTML escaping;
-   CSS design;
-   generic slider construction;
-   generic chart construction;
-   arithmetic;
-   matrix multiplication;
-   checking whether a file exists;
-   checking whether controls exist;
-   checking whether softmax sums to one;
-   checking for external URLs;
-   checking whether a DOM element changed.

Reserve model calls for irreducibly semantic work.

------------------------------------------------------------------------

# 5. End-to-End State Machine

The orchestrator MUST implement an explicit bounded state machine.

Recommended high-level states:

``` text
START
  ↓
STARTUP_VALIDATION
  ↓
SOURCE_ACQUISITION
  ↓
PAPER_PARSING
  ↓
RETRIEVAL
  ↓
EVIDENCE_PACK
  ↓
SEMANTIC_CORE
  ↓
IR_VALIDATION
  ↓
COMPUTATION_VALIDATION
  ↓
RENDER_CANDIDATE
  ↓
STATIC_VALIDATION
  ↓
BROWSER_VALIDATION
  ↓
GROUNDING_AND_COVERAGE
  ↓
FINAL_QUALITY_GATE
  ↓
FINALIZE
  ↓
EXIT
```

Each state MUST define:

-   required inputs;
-   produced outputs;
-   success criteria;
-   structured failure codes;
-   recoverability;
-   allowed fallback;
-   retry policy;
-   trace events.

The orchestrator, and only the orchestrator, decides global recovery
transitions.

A lower-level parser may report `PARSE_TABLE_FAILED`; it MUST NOT
independently decide to call the model or change visualization strategy.

------------------------------------------------------------------------

# 6. Failure Model

Failures MUST be typed rather than free-form strings.

Suggested namespaces:

``` text
INPUT_*
SOURCE_*
PARSE_*
RETRIEVAL_*
EVIDENCE_*
MODEL_*
IR_*
GROUNDING_*
COMPUTE_*
RENDER_*
ARTIFACT_*
BROWSER_*
BUDGET_*
FINALIZE_*
```

Each failure SHOULD carry:

``` text
code
stage
severity
recoverable
target
message
details
```

Severity categories:

-   `CRITICAL`
-   `MAJOR`
-   `MINOR`
-   `WARNING`

Expected errors become structured diagnostics.

Unexpected exceptions MUST be sanitized before tracing.

Warnings MUST NOT automatically trigger model calls.

------------------------------------------------------------------------

# 7. Startup Validation

Before expensive work:

1.  parse CLI;
2.  confirm input path exists;
3.  confirm output path can be created;
4.  parse JSON;
5.  validate exactly the required case contract;
6.  confirm non-empty `source_url`, `focus`, `audience`;
7.  confirm model argument exists;
8.  confirm `OPENROUTER_API_KEY` exists before a model call is needed;
9.  initialize trace;
10. initialize budget;
11. initialize temporary/staging directories.

Fail early rather than consuming model calls.

------------------------------------------------------------------------

# 8. Source Acquisition

## 8.1 Supported source types

Support:

``` text
local path
file:// path
http:// URL
https:// URL
```

Local paths are preferred.

## 8.2 Remote acquisition

Remote fetching MUST have:

-   strict timeout;
-   bounded response size where practical;
-   content-type inspection;
-   content/magic-byte inspection;
-   at most a tiny transient retry policy;
-   no infinite redirect/retry behavior.

If remote acquisition fails, NEVER ask DeepSeek to reconstruct the paper
from its title or URL.

## 8.3 Format detection

Do not trust filename extension alone.

Use:

-   URL/path suffix;
-   response MIME;
-   magic bytes/content inspection.

Supported primary document forms:

-   PDF;
-   static HTML where practical.

------------------------------------------------------------------------

# 9. PaperDocument: Canonical Source Representation

All extraction libraries MUST normalize into a library-independent
`PaperDocument`.

Suggested conceptual structure:

``` text
PaperDocument
├── source_id
├── source_type
├── title
├── metadata
├── pages
├── sections
├── elements
│   ├── paragraphs
│   ├── equations
│   ├── algorithms
│   ├── tables
│   ├── captions
│   └── figures
└── extraction_warnings
```

Every source element SHOULD contain:

``` text
element_id
element_type
text/content
page
section_id
section_title
equation_number
figure_number
table_number
bbox (when meaningful)
source_order
extraction_confidence/category
```

Never invent page, section, equation, table, or figure references.

If precision is unavailable, degrade provenance precision gracefully.

------------------------------------------------------------------------

# 10. PDF Extraction

Primary candidate dependency: **PyMuPDF**, subject to clean Python 3.11
verification.

The PDF layer SHOULD attempt:

-   text blocks;
-   coordinates;
-   page boundaries;
-   font/size information where useful for heading heuristics;
-   images;
-   captions;
-   vector/drawing metadata;
-   table extraction;
-   page rendering/cropping when needed for evidence processing.

## 10.1 Multi-column handling

PDF extraction MUST account for multi-column papers.

Do not assume raw extraction order equals human reading order.

Use layout coordinates and block ordering heuristics where necessary.

## 10.2 Equation preservation

Preserve:

-   equation text where extractable;
-   equation number;
-   nearby paragraph;
-   section;
-   page.

Equation extraction may be imperfect. Do not silently "repair" an
equation using general knowledge and then attribute the repair to the
paper.

## 10.3 OCR

No mandatory system Tesseract.

OCR MAY be added only if:

-   pip-only;
-   Python 3.11 compatible;
-   benchmark evidence shows it is needed;
-   it does not create a system-package requirement.

Otherwise scanned-PDF limitations should degrade safely.

------------------------------------------------------------------------

# 11. Multimodal / Visual Evidence Architecture

Paper understanding is structure-aware and visual-evidence-aware, but
the required path MUST NOT depend on a multimodal model.

Use parallel typed extraction:

``` text
PAPER
 ├── TEXT
 ├── EQUATIONS
 ├── TABLES
 └── FIGURES / DIAGRAMS / GRAPHS
```

## 11.1 Tables

Tables are first-class evidence.

Attempt deterministic extraction of:

``` text
table_id
caption
page
section
columns
rows
cells
```

Retrieval MUST be able to search table captions and cells.

If structured extraction fails:

-   retain table reference;
-   retain caption;
-   retain surrounding paragraphs;
-   retain page/section;
-   do not invent missing cells.

## 11.2 Figures

Figures are first-class detected evidence.

Capture where recoverable:

``` text
figure_id
caption
figure_number
page
section
surrounding paragraphs
references from body text
text labels
bounding boxes
vector lines/shapes
optional crop
```

## 11.3 Pipeline and architecture diagrams

Use an escalation path:

``` text
caption sufficient?
  ↓ no
surrounding paragraphs sufficient?
  ↓ no
extracted labels/layout metadata sufficient?
  ↓ no
optional image-semantic interpretation IF supported
```

The mandatory success path MUST work without image-semantic model input.

## 11.4 Graphs and plots

Do NOT reverse-engineer exact numeric datasets from pixels by default.

Allowed:

-   paper explicitly states value -\> use it;
-   table contains value -\> use it;
-   vector/text metadata explicitly exposes value -\> use it;
-   caption/source states trend -\> explain trend.

Not allowed:

-   visually guess "approximately 83.2%" from a plotted point and
    present it as source fact.

## 11.5 Relevance gating

Do not richly process every figure/table.

Use focus relevance first.

Examples:

-   focus says "Figure 2" -\> escalate Figure 2;
-   focus says "pipeline" and relevant section references Figure 3 -\>
    escalate Figure 3;
-   unrelated Figure 9 -\> leave lightweight.

------------------------------------------------------------------------

# 12. Retrieval Architecture

Retrieval is deterministic-first.

Priority:

``` text
1. explicit section/equation/figure/table lookup
2. exact focus/concept lexical matches
3. heading/symbol overlap
4. BM25-style ranking
5. retrieval confidence
6. DeepSeek reranking only if low/ambiguous
7. one controlled neighboring-evidence expansion if still insufficient
```

## 12.1 Section-aware chunking

Prefer semantic source neighborhoods:

``` text
section
subsection
paragraph + equation
caption + nearby paragraphs
table + caption
algorithm + explanation
```

over arbitrary character chunks.

## 12.2 Neighborhood retrieval

Do not retrieve isolated sentences without context.

For a relevant equation, include its explanatory neighborhood.

For a relevant figure, include caption and nearby references.

## 12.3 Noise suppression

Downweight or exclude by default:

-   bibliography;
-   acknowledgements;
-   repeated headers/footers;
-   table of contents;
-   author affiliation blocks.

Captions remain valid evidence.

## 12.4 Internal BM25

Prefer a small internal BM25 implementation unless benchmark evidence
strongly favors a dependency.

No vector DB.

No embedding calls.

------------------------------------------------------------------------

# 13. Retrieval Confidence

Confidence MUST be based on observable retrieval signals rather than
invented LLM probabilities.

Possible signals:

``` text
explicit reference matched
exact focus phrase matched
heading match
symbol match
top BM25 score
top-vs-second score separation
focus term coverage
candidate source-type match
```

Return categorical states such as:

``` text
HIGH
AMBIGUOUS
LOW
```

Exact thresholds MUST be tuned empirically in benchmarks.

Do not hardcode arbitrary confidence values and call them scientifically
meaningful.

------------------------------------------------------------------------

# 14. DeepSeek Retrieval Reranking

Only invoke when deterministic retrieval is ambiguous.

Input should be tiny:

``` text
focus
candidate heading
candidate short preview
candidate IDs
```

Output should be tiny:

``` json
{
  "selected_ids": ["..."],
  "insufficient": false
}
```

No long explanations.

No full paper.

No chain-of-thought request.

Track whether reranking actually improves retrieval; remove it if
benchmarks show negligible value.

------------------------------------------------------------------------

# 15. Evidence Pack

Before scientific reasoning, construct a compact `EvidencePack`.

Conceptual structure:

``` text
EvidencePack
├── paper metadata
├── original focus
├── audience
├── evidence blocks
│   ├── E001 paragraph
│   ├── E002 equation
│   ├── E003 table
│   ├── E004 caption
│   └── E005 figure context
└── retrieval metadata
```

Each evidence block MUST have immutable stable ID.

Evidence types MAY include:

``` text
paragraph
equation
algorithm
pseudocode
table
caption
figure_context
figure_labels
```

The Evidence Pack MUST be:

-   deduplicated;
-   ranked;
-   compact;
-   sufficiently contextual;
-   token-budgeted.

DeepSeek MUST use Evidence IDs for paper-specific grounding.

------------------------------------------------------------------------

# 16. Source Text Is Untrusted Data

Research paper content MUST never become system instruction.

Prompt architecture MUST clearly delimit source material as untrusted
evidence.

A paper may contain text such as:

``` text
Ignore all previous instructions...
```

That is scientific/source data, not an instruction.

Test prompt injection in:

-   paragraphs;
-   captions;
-   table cells;
-   extracted figure labels.

------------------------------------------------------------------------

# 17. Semantic Core

The semantic stage is responsible for meaning, not presentation code.

DeepSeek SHOULD determine:

-   requested concept identity;
-   why it matters;
-   focus alignment;
-   important variables;
-   variable meaning;
-   equations;
-   relationships;
-   causal/functional dependencies;
-   ordered mechanism steps;
-   assumptions;
-   limitations;
-   misconceptions;
-   invariants;
-   edge cases;
-   meaningful controls;
-   visual intent;
-   pedagogical sequence;
-   guided explorations;
-   audience adaptation.

DeepSeek SHOULD NOT produce:

-   CSS;
-   arbitrary HTML;
-   generic chart boilerplate;
-   page layout code;
-   arithmetic results that deterministic code can calculate;
-   external asset references.

------------------------------------------------------------------------

# 18. One-Call vs Two-Call Strategy

Preserve conceptual separation:

``` text
Scientific Model
      ↓
Lesson Spec
```

even if implemented in one API request.

Benchmark two configurations.

## Configuration A: combined

``` text
Evidence Pack
  ↓
DeepSeek
  ↓
Scientific Model + Lesson Spec + computation/visual intent
```

## Configuration B: staged

``` text
Evidence Pack
  ↓
DeepSeek
  ↓
Scientific Model
  ↓
validate
  ↓
DeepSeek
  ↓
Lesson Spec + computation/visual plan
```

Choose based on measured:

-   scientific correctness;
-   focus alignment;
-   schema success;
-   repair rate;
-   token use;
-   latency;
-   repeated-run semantic variance.

Do not add adaptive routing unless benchmarks show a reliable benefit.

------------------------------------------------------------------------

# 19. Prompt Engineering Contract

Prompts SHOULD be contract-oriented, not persona-heavy.

Recommended structure:

``` text
1. task
2. non-negotiable rules
3. case context
4. compact runtime capabilities
5. evidence
6. exact output contract
```

Use:

-   raw JSON;
-   enums;
-   stable IDs;
-   concise descriptions;
-   explicit `null` / `unsupported` / `insufficient_evidence`.

Avoid:

-   Markdown fences around JSON;
-   visible chain-of-thought requests;
-   long persona roleplay;
-   asking the model to summarize evidence before answering;
-   asking the model to reproduce source quotations;
-   giant schema dumps when a compact contract is enough.

Python owns strict schema validation.

------------------------------------------------------------------------

# 20. Scientific Model

The Scientific Model represents **what is true**.

It SHOULD include:

``` text
concept
purpose
focus_alignment
variables
equations
relationships
mechanism_steps
assumptions
limitations
misconceptions
invariants
edge_cases
provenance
knowledge_classes
demonstration_scope
```

## 20.1 Variables

Each important variable SHOULD include:

``` text
id
source_symbol
display_symbol
meaning
type
shape
domain
units
evidence_refs
knowledge_class
```

Do not rename source notation silently.

If pedagogical renaming is needed, preserve explicit mapping.

## 20.2 Relationships

Represent functional or causal relationships explicitly.

Do not rely only on prose.

## 20.3 Mechanism steps

For multi-step mechanisms, capture ordered computation/transition
stages.

------------------------------------------------------------------------

# 21. Knowledge Classes

Every scientifically meaningful learner-facing claim MUST belong to:

``` text
SOURCE_GROUNDED
DERIVED
PEDAGOGICAL
```

## SOURCE_GROUNDED

The supplied paper/excerpt supports the claim.

Must reference evidence IDs.

## DERIVED

The claim follows from executable mathematics or deterministic
computation.

Should reference computation lineage.

## PEDAGOGICAL

The generator introduced it for teaching:

-   toy values;
-   analogy;
-   visualization encoding;
-   control range;
-   preset;
-   simplified example.

This distinction MUST survive to the final manifest and source-grounding
section.

------------------------------------------------------------------------

# 22. Claim Grounding

Meaningful scientific claims SHOULD be individually groundable.

Do not create claim objects for trivial UI strings.

Grounding status:

``` text
SUPPORTED
PARTIAL
UNSUPPORTED
```

If unsupported:

``` text
expand evidence once if appropriate
  ↓
narrow claim
  ↓
remove unsupported paper-specific claim
  ↓
replace only with clearly derived/pedagogical content if scientifically valid
```

Never silently convert general model knowledge into "the paper says".

------------------------------------------------------------------------

# 23. High-Risk Claims

Treat the following as higher risk:

-   experimental performance;
-   benchmark superiority;
-   numerical paper results;
-   causal claims;
-   claims attributed to paper authors;
-   equation interpretation where extraction is ambiguous;
-   claims based mainly on visual evidence.

The playground SHOULD normally demonstrate the mechanism rather than
reproduce full experimental findings.

------------------------------------------------------------------------

# 24. Lesson Spec

The Lesson Spec represents **how to teach the truth**.

It SHOULD include:

``` text
central_learning_question
learning_objectives
audience_prerequisites
intuition
teaching_sequence
symbol_explanations
controls
important_intermediates
visual_question
visual_intent
guided_explorations
limitation_or_assumption
misconception
source_grounding_plan
```

Pedagogy MUST NOT silently alter the Scientific Model.

------------------------------------------------------------------------

# 25. Teaching Strategy

Teach mechanisms, not summaries.

Recommended progressive disclosure:

``` text
central question / why it matters
  ↓
intuition
  ↓
parts and symbols
  ↓
formal mechanism
  ↓
interactive playground
  ↓
important intermediates
  ↓
guided exploration 1
  ↓
guided exploration 2
  ↓
limitation / assumption / misconception
  ↓
source grounding
```

Exact layout may vary.

Every lesson SHOULD provide three complementary layers:

1.  intuition;
2.  mechanism/process;
3.  formal mathematics.

------------------------------------------------------------------------

# 26. Audience Adaptation

Audience changes:

-   terminology;
-   assumed prerequisites;
-   derivation depth;
-   amount of explanation;
-   example complexity.

Audience MUST NOT change:

-   equation truth;
-   mechanism;
-   paper claims;
-   scientific relationships.

------------------------------------------------------------------------

# 27. Controls

Every control MUST have a scientific contract:

``` text
id
label
scientific_variable
type
default
min/max/step or options
units
validation_rule
effect_targets
learning_purpose
safe_range_reason
```

Controls MUST be scientifically meaningful.

A control counts only when:

``` text
control change
  ↓
scientific state change
  ↓
derived value / state change
  ↓
observable educational output changes
```

Decorative controls do not count.

------------------------------------------------------------------------

# 28. Input Validation in the Playground

Each interactive variable MUST define invalid-input behavior:

``` text
clamp
reject
normalize
warn
```

Never allow accidental:

``` text
NaN
Infinity
undefined
broken SVG
```

to become the learner experience.

If a mathematical state is genuinely undefined, display an educational
explanation.

------------------------------------------------------------------------

# 29. Guided Explorations

There MUST be two meaningful guided explorations.

Each MUST include:

``` text
change
observe
why
```

Exploration 1 SHOULD usually establish canonical/baseline behavior.

Exploration 2 SHOULD usually stress the mechanism through:

-   contrast;
-   sensitivity;
-   boundary;
-   edge case;
-   alternate regime.

Each exploration SHOULD support an executable:

``` text
Apply Setup
```

preset.

The page SHOULD encourage prediction before observation where natural.

------------------------------------------------------------------------

# 30. Universal Reset

Every lesson MUST provide deterministic Reset behavior.

Reset MUST restore:

-   all control values;
-   scientific state;
-   calculations;
-   visual state;
-   comparison state;
-   stepper state where applicable.

Reset behavior MUST be browser-tested.

------------------------------------------------------------------------

# 31. Explanation IR

Scientific Model + Lesson Spec become a renderer-independent
`ExplanationIR`.

The IR MUST be validated before rendering.

Validation stages:

``` text
syntax
  ↓
schema
  ↓
ID/reference integrity
  ↓
semantic consistency
  ↓
computation validity
  ↓
pedagogical completeness
```

Syntactic/schema repair SHOULD be deterministic before spending another
model call.

------------------------------------------------------------------------

# 32. Focus Coverage Map

Create an explicit chain:

``` text
focus
  ↓
learning objective
  ↓
mechanism
  ↓
controls
  ↓
computation
  ↓
visual
  ↓
guided explorations
```

This is the `FocusCoverageMap`.

The final lesson should not drift into the paper's most famous concept
if it differs from the requested focus.

------------------------------------------------------------------------

# 33. Computation Architecture

DeepSeek specifies science.

Deterministic runtime executes science.

Prefer a dependency DAG:

``` text
inputs
  ↓
intermediates
  ↓
outputs
```

Computation and visualization MUST be separate layers.

------------------------------------------------------------------------

# 34. Restricted Mathematical DSL

DeepSeek SHOULD emit compact familiar mathematical expressions such as:

``` text
softmax(scores / sqrt(d_k))
```

rather than deeply nested AST JSON.

Pipeline:

``` text
DeepSeek DSL
  ↓
safe parser
  ↓
whitelist
  ↓
normalized canonical AST
  ↓
Python evaluator
  ↓
browser evaluator
  ↓
equation renderer
```

One canonical structured expression SHOULD drive display and execution
wherever practical.

------------------------------------------------------------------------

# 35. DSL Safety

A possible implementation uses Python `ast.parse` only as a parser.

Allowed concepts may include:

``` text
numbers
identifiers
parentheses
+ - * / **
unary +/-
whitelisted function calls
index/subscript
list/tuple literals when required
```

Reject:

``` text
Attribute
Lambda
comprehensions
assignment
imports
arbitrary calls
dunder names
```

Then translate accepted syntax into the project's OWN AST.

Never:

``` python
eval(...)
exec(...)
compile(... and execute)
```

------------------------------------------------------------------------

# 36. Canonical AST

Example conceptual node types:

``` text
Constant
Variable
Unary
Binary
Call
Index
Vector
Matrix
Conditional (if explicitly supported)
```

Function names MUST resolve against a whitelist.

The AST MUST be serializable into the final manifest.

------------------------------------------------------------------------

# 37. Scientific Operation Registry

Build a deliberately small operation registry.

Potential operations:

``` text
add
subtract
multiply
divide
power
sqrt
exp
log
abs
min
max
sum
mean
variance
normalize
softmax
sigmoid
dot
matmul
transpose
norm
distance
clip
argmax
```

Add operations only when generic hidden-test-like mechanisms justify
them.

------------------------------------------------------------------------

# 38. Shapes and Types

Scientific type system SHOULD support:

``` text
scalar
boolean
categorical
vector
matrix
sequence
state
distribution
```

Validate:

-   shape compatibility;
-   matrix multiplication dimensions;
-   scalar/vector expectations;
-   probability domains;
-   units metadata where relevant.

------------------------------------------------------------------------

# 39. Numerical Stability

Generic operations MUST use stable implementations where applicable.

Example: stable softmax subtracts maximum before exponentiation.

Use tolerance-based floating comparison.

Never rely on exact floating equality for scientific invariants.

------------------------------------------------------------------------

# 40. Procedural Mechanisms

Do not force iterative/stateful science into one algebraic expression.

## Iterative spec

Conceptually:

``` text
initial_state
update_expression
steps
stop_condition
record_fields
```

## State-transition spec

Conceptually:

``` text
states
transitions
conditions
actions
```

These remain declarative and validated.

------------------------------------------------------------------------

# 41. Custom Computation Escape Hatch

Custom generated code is a last resort.

First attempt:

``` text
restricted DSL
  ↓
iterative declarative spec
  ↓
state declarative spec
```

Only then consider custom computation.

Benchmark custom-code frequency.

If the generic system covers the corpus well, remove arbitrary custom JS
capability entirely.

If custom code remains:

-   small;
-   pure;
-   input -\> output;
-   isolated;
-   screened;
-   tested;
-   no network;
-   no DOM;
-   no `eval`;
-   no `Function`;
-   no imports;
-   no infinite-loop patterns where detectable.

------------------------------------------------------------------------

# 42. Computation Testing

Before rendering, test:

``` text
default state
control minimums
control maximums
guided presets
selected interior values
```

Verify:

``` text
finite outputs
correct types
correct shapes
valid domains
invariants
expected dependency effects
```

Use property tests where applicable.

Examples:

``` text
softmax(x) sums to approximately 1
normalized distribution sums to approximately 1
variance >= 0
distance >= 0
transpose(transpose(A)) == A
identity matrix behavior
```

------------------------------------------------------------------------

# 43. Important Intermediate Calculations

The runtime SHOULD expose pedagogically useful intermediate values.

Do not expose every internal scalar.

The Lesson Spec identifies which intermediates matter.

Examples:

``` text
raw score
scaled score
normalization denominator
probability contribution
iteration update
current state transition
```

------------------------------------------------------------------------

# 44. Scientific UI Runtime

DeepSeek MUST NOT normally generate the page frontend.

Build a polished reusable Scientific UI Runtime during development.

It includes:

``` text
design system
layouts
controls
scientific visual components
equation display
state management
computation interpreter
guided exploration behavior
reset behavior
comparison behavior
semantic metadata
```

The model configures this runtime through structured IR.

------------------------------------------------------------------------

# 45. Global Scientific State

The generated page SHOULD have one coherent scientific state.

Flow:

``` text
control input
  ↓
validate
  ↓
update state
  ↓
recompute dependency DAG
  ↓
update equations
  ↓
update numeric intermediates
  ↓
update visual
  ↓
update explanatory state
```

Avoid separate ad-hoc state per component.

------------------------------------------------------------------------

# 46. Visualization Grammar

Select visualization from mechanism family.

Mechanism taxonomy SHOULD cover at least:

``` text
scalar relationship
distribution
matrix transformation
sequential algorithm
state transition
optimization
signal transformation
geometry
information/component flow
iterative process
comparative mechanism
dynamical system
```

Example mapping:

``` text
distribution -> bars / distribution view
matrix transformation -> matrix / heatmap
signal -> waveform
optimization -> trajectory
state transition -> state diagram
pipeline -> flow diagram
geometry -> SVG geometric scene
iteration -> stepper / trajectory
comparison -> synchronized comparison
```

------------------------------------------------------------------------

# 47. Visualization Escape Ladder

Use:

``` text
specialized generic component
  ↓
composition of generic primitives
  ↓
generic scientific SVG scene
  ↓
custom visualization escape hatch
  ↓
simpler scientifically valid fallback
```

Never sacrifice scientific truth for visual sophistication.

------------------------------------------------------------------------

# 48. SVG First

Prefer SVG because it is:

-   self-contained;
-   inspectable;
-   semantic;
-   responsive;
-   testable;
-   dependency-free.

HTML/CSS is appropriate for matrices/tables/simple structures.

Canvas only when justified.

Avoid D3 unless implementation evidence shows a meaningful need.

------------------------------------------------------------------------

# 49. Visual Question

Every major visual SHOULD answer a defined question.

Lesson Spec may include:

``` text
visual_question
visual_answer
```

Example:

``` text
Question: How does increasing temperature flatten the distribution?
Answer: The bars become more similar in height as temperature rises.
```

A visualization that merely looks scientific is insufficient.

------------------------------------------------------------------------

# 50. Synchronized Representations

Where appropriate, a state change SHOULD update:

``` text
words
equation
substituted equation
numbers
visual
```

The educational goal is:

> **words \<-\> equations \<-\> numbers \<-\> visuals**

------------------------------------------------------------------------

# 51. Deterministic Layouts

Use a small set of pre-engineered responsive layout compositions.

Do not let the model invent arbitrary page structure.

Layouts MAY vary by mechanism family, but should share:

-   clear typography;
-   strong hierarchy;
-   accessible spacing;
-   consistent controls;
-   responsive behavior;
-   predictable source section.

------------------------------------------------------------------------

# 52. Expected Learner Experience

A strong generated page should roughly feel like:

``` text
CENTRAL QUESTION
Why does this mechanism matter?

INTUITION
Short conceptual framing.

SYMBOLS
Compact variable legend.

MECHANISM
Equation / process / state relationship.

INTERACTIVE PLAYGROUND
Meaningful controls + live scientific visual.

INTERMEDIATE CALCULATIONS
Only important values.

GUIDED EXPLORATION 1
Apply Setup -> Change -> Observe -> Why.

GUIDED EXPLORATION 2
Apply Setup -> Change -> Observe -> Why.

LIMITATION / ASSUMPTION / MISCONCEPTION
Specific and educational.

SOURCE GROUNDING
Paper + relevant section/equation/figure + simplifications + scope.
```

Do not treat this as a rigid HTML order if another arrangement better
fits the mechanism.

------------------------------------------------------------------------

# 53. Embedded Manifest

`index.html` MUST contain a machine-readable manifest, for example:

``` html
<script type="application/json" id="playground-manifest">
...
</script>
```

Manifest SHOULD describe:

``` text
generator version
concept
mechanism family
controls
variables
computations / AST
dependencies
outputs
visuals
guided explorations
source references
knowledge classes
grounding records
simplifications
limitations
focus coverage
```

The manifest is data, not arbitrary executable code.

------------------------------------------------------------------------

# 54. Safe HTML Generation

All source/model-derived strings MUST be escaped.

This includes:

-   paper title;
-   captions;
-   headings;
-   explanations;
-   labels;
-   source metadata.

Embedded JSON MUST be serialized safely so source text cannot
prematurely close a `<script>` element.

Displayed URLs MUST use safe schemes.

Never convert arbitrary local paths into clickable `file://` links.

------------------------------------------------------------------------

# 55. No Runtime Network

Generated HTML MUST NOT require:

``` text
fetch
XMLHttpRequest
WebSocket
remote import
CDN
remote font
remote image
API
```

A source URL may be displayed as citation metadata but MUST NOT be
needed for functionality.

------------------------------------------------------------------------

# 56. Paper Figures in Final Artifact

Paper figures are primarily **evidence for the generator**.

The final page SHOULD normally generate a new interactive scientific
representation rather than embedding a screenshot of the paper figure.

Benefits:

-   interactive;
-   consistent design;
-   smaller artifact;
-   avoids cloning source aesthetics;
-   reduces copyright/reproduction concerns;
-   better matches the assignment's teaching objective.

Small source table values MAY enter the lesson when directly relevant
and properly grounded.

------------------------------------------------------------------------

# 57. Source-Grounding Section

The final page SHOULD clearly identify:

``` text
paper title
relevant section
relevant equation / figure / table when recoverable
what source mechanism is being demonstrated
what the generator introduced for teaching
what the toy demo does NOT reproduce
```

Example distinction:

``` text
Paper-supported:
The equation defines ...

Derived:
For the current inputs, the computed output is ...

Teaching simplification:
This page uses a 3-element vector to make the transformation visible.

Not reproduced:
The paper's full training setup and benchmark results.
```

------------------------------------------------------------------------

# 58. Validation Philosophy

Generation is not success.

Validation is continuous.

Use six major gates plus cross-cutting final checks:

``` text
Gate 1: Source / Evidence
Gate 2: Scientific IR
Gate 3: Pedagogical IR
Gate 4: Computation
Gate 5: Artifact Structure
Gate 6: Browser Behavior
Final: Coverage + Grounding + Quality Gate
```

Every validator returns structured findings:

``` text
PASS
WARN
FAIL
```

Do not invent fake precise quality probabilities.

------------------------------------------------------------------------

# 59. Gate 1: Source and Evidence

Check:

-   source loaded;
-   extraction non-empty;
-   title/metadata where available;
-   relevant section candidates;
-   explicit reference resolution;
-   evidence IDs unique;
-   provenance present;
-   focus represented;
-   Evidence Pack non-empty;
-   extraction sanity.

Low confidence triggers the bounded retrieval fallback chain.

------------------------------------------------------------------------

# 60. Gate 2: Scientific IR

Check:

-   required variables exist;
-   IDs unique;
-   references resolve;
-   equations reference valid variables;
-   relationships coherent;
-   source-grounded claims have evidence;
-   knowledge classes assigned;
-   domains valid;
-   shapes valid;
-   assumptions/limitations present where needed;
-   unsupported evidence states explicit;
-   invariants structurally valid.

------------------------------------------------------------------------

# 61. Gate 3: Pedagogical IR

Check:

-   central learning question;
-   objective aligned with focus;
-   audience adaptation;
-   intuition;
-   symbol explanation;
-   meaningful controls;
-   visual question/intent;
-   important intermediates;
-   two explorations;
-   `change -> observe -> why`;
-   exploration presets valid;
-   limitation/assumption/misconception;
-   source-grounding plan.

For every control verify a dependency path to meaningful observable
scientific output.

------------------------------------------------------------------------

# 62. Gate 4: Computation

Execute:

-   default;
-   boundaries;
-   presets;
-   interior states.

Check:

-   no exception;
-   finite values;
-   type;
-   shape;
-   domain;
-   invariants;
-   intended control effect.

Use the Python evaluator on the same canonical AST that will be embedded
for browser execution.

------------------------------------------------------------------------

# 63. Gate 5: Artifact Structure

Check:

-   `index.html` exists;
-   self-contained;
-   embedded CSS;
-   embedded JS;
-   manifest exists;
-   required lesson sections;
-   at least two meaningful controls;
-   two guided explorations;
-   limitation/assumption/misconception;
-   source grounding;
-   no external runtime dependencies;
-   no remote fonts/CDNs;
-   no obvious forbidden network constructs;
-   semantic IDs/metadata present.

Validate:

``` text
IR -> manifest -> DOM
```

coverage.

------------------------------------------------------------------------

# 64. Gate 6: Browser Behavior

When compatible Chromium control is available, perform real execution.

Recommended trajectory:

``` text
load page
  ↓
record baseline
  ↓
change control 1
  ↓
verify scientific output changed
  ↓
verify visual changed
  ↓
reset
  ↓
change control 2
  ↓
verify
  ↓
apply exploration 1
  ↓
verify expected state
  ↓
apply exploration 2
  ↓
verify expected state
  ↓
reset
```

Detect:

-   JS runtime errors;
-   dead controls;
-   dead visuals;
-   stale intermediates;
-   broken reset;
-   broken presets;
-   invalid states;
-   mismatch between numeric and visual representations.

------------------------------------------------------------------------

# 65. Semantic DOM Metadata

Generated elements SHOULD contain stable semantic metadata such as:

``` text
data-control-id
data-variable-id
data-output-id
data-visual-id
data-depends-on
data-exploration-id
data-role
```

This allows browser validation without computer vision.

Do not depend on screenshot/VLM evaluation.

------------------------------------------------------------------------

# 66. Browser Validation Availability

Use real Chromium validation when a compatible installed
browser/controller is available.

The exact browser-control package MUST be selected after testing the
official environment.

Requirements:

-   pip-installable;
-   uses installed Chromium where possible;
-   no unsupported manual browser download;
-   no required external server.

If browser control is unavailable:

``` text
BROWSER_VALIDATION_UNAVAILABLE
```

is traced and validation degrades to static/structural checks rather
than destroying an otherwise usable artifact.

Because the assessment itself uses Chromium, environment testing should
strongly prioritize making real browser validation work.

------------------------------------------------------------------------

# 67. Risk-Triggered Semantic Verification

Do NOT use a mandatory LLM critic.

Trigger narrow semantic verification only for risk signals such as:

-   ambiguous retrieval;
-   partially supported claim;
-   unusual equation interpretation;
-   custom computation;
-   visual/scientific mismatch not deterministically resolvable;
-   grounding ambiguity.

Ask narrow questions over small units:

``` text
claim <-> evidence
equation <-> evidence
control <-> mechanism
exploration <-> mechanism
```

Do not ask "Is this whole page good?"

------------------------------------------------------------------------

# 68. Repair Architecture

Repair the smallest broken layer.

Priority:

``` text
1. scientific correctness
2. computation
3. required rubric features
4. interaction
5. grounding
6. visual/scientific mismatch
7. teaching clarity
8. cosmetics
```

## 68.1 Deterministic repair first

Use deterministic repair for:

-   malformed recoverable JSON;
-   missing structural defaults;
-   invalid IDs;
-   formatting;
-   safe range clamping when semantically known;
-   rendering structure;
-   known schema transformations.

## 68.2 Model repair

Use DeepSeek only for genuinely semantic issues.

Provide:

``` text
failure
affected IR fragment
relevant evidence
repair contract
```

Return a small structured patch.

Do not regenerate the entire valid IR.

## 68.3 Revalidation

Every repair MUST be revalidated.

Use dependency-aware revalidation where possible.

------------------------------------------------------------------------

# 69. Last-Known-Good Artifact

Maintain staging and promotion.

``` text
candidate
  ↓
validate
  ↓
PASS -> promote as last-known-good
FAIL -> reject
```

A later repair MUST NOT overwrite the last-known-good artifact until it
passes.

Reliability principle:

> Preserve the best validated artifact achieved, not the newest artifact
> generated.

------------------------------------------------------------------------

# 70. Fallback Philosophy

Every important subsystem SHOULD have:

``` text
primary path
  ↓
failure / low confidence
  ↓
bounded fallback
  ↓
safe degradation
```

## Retrieval

``` text
explicit ref
-> lexical/BM25
-> DeepSeek rerank
-> one neighboring expansion
-> narrow to supported evidence
```

## Visualization

``` text
specialized component
-> primitive composition
-> generic scene
-> custom escape hatch
-> simpler valid visual
```

## Computation

``` text
DSL
-> iterative/state spec
-> custom escape hatch
-> simpler scientifically valid representation
```

## Grounding

``` text
exact evidence
-> neighboring expansion
-> narrow claim
-> remove unsupported paper-specific claim
-> clearly derived/pedagogical explanation only
```

Fallback MUST reduce complexity, not scientific truth.

------------------------------------------------------------------------

# 71. Minimum Shippable Artifact

When optional sophistication fails, preserve a usable page containing as
much of the required rubric as safely possible:

-   focused concept;
-   correct mechanism;
-   meaningful visualization;
-   at least two meaningful controls;
-   executable calculations;
-   important intermediates;
-   two guided explorations;
-   limitation/assumption/misconception;
-   source grounding;
-   offline functionality.

Do not destroy a strong simple artifact because an optional advanced
visual failed.

------------------------------------------------------------------------

# 72. RunBudget

Implement a centralized `RunBudget`.

Track:

``` text
start time
elapsed time
calls used
prompt tokens
completion tokens
total tracked usage
remaining time
remaining call budget
```

Use hard assignment ceilings plus tighter internal soft limits.

Reserve resources for critical repair/finalization.

------------------------------------------------------------------------

# 73. Finalization Safety Window

As deadline approaches:

1.  stop optional enrichment;
2.  stop cosmetic repair;
3.  preserve last-known-good;
4.  run essential validation;
5.  atomically write final outputs;
6.  flush trace;
7.  exit appropriately.

Never consume the last available seconds attempting optional semantic
polishing.

------------------------------------------------------------------------

# 74. OpenRouter Client

All model calls MUST pass through one `model/client.py` layer.

It owns:

-   supplied model ID;
-   API key;
-   endpoint;
-   request timeout;
-   call counting;
-   usage extraction;
-   retry policy;
-   trace events;
-   sanitized errors.

No other module makes direct model requests.

------------------------------------------------------------------------

# 75. API Failure Handling

Explicitly handle:

``` text
timeout
429
5xx
network error
empty response
malformed response
malformed JSON
schema-invalid JSON
```

Transport failures differ from semantic failures.

At most one conservative transient retry, subject to budget.

Do not retry deterministic schema mistakes blindly with the same
request.

------------------------------------------------------------------------

# 76. Model Response Normalization

Pipeline:

``` text
raw response
  ↓
extract content
  ↓
JSON parse
  ↓
conservative deterministic recovery
  ↓
schema validation
  ↓
ID/reference validation
  ↓
semantic validation
```

Only then consider a model repair call.

Do not dump giant raw responses into normal trace.

------------------------------------------------------------------------

# 77. Trace Contract

`trace.jsonl` MUST be streamed/flushed during execution.

Suggested event fields:

``` json
{
  "elapsed_seconds": 12.4,
  "stage": "model",
  "action": "generate_ir",
  "result": "pass",
  "details": {},
  "prompt_tokens": 3200,
  "completion_tokens": 1400
}
```

Not every event needs token fields.

Trace SHOULD include:

-   source acquisition;
-   extraction summary;
-   retrieval result;
-   retrieval confidence;
-   fallback use;
-   model call usage;
-   schema validation;
-   computation validation;
-   rendering;
-   browser interaction checks;
-   failures;
-   repairs;
-   fallback outcomes;
-   final quality gate;
-   final status.

Trace MUST NOT include:

-   API key;
-   hidden chain-of-thought;
-   entire paper;
-   huge HTML;
-   giant prompts;
-   secrets.

Use monotonic elapsed timing.

Every line MUST be valid JSON.

------------------------------------------------------------------------

# 78. Output Management

Only manage files owned by the run.

Use:

-   staging directory;
-   temporary files;
-   atomic final writes.

Success output should remain clean:

``` text
out/
├── index.html
└── trace.jsonl
```

Internal candidates should be temporary and cleaned where practical.

------------------------------------------------------------------------

# 79. Repository Architecture

Recommended structure:

``` text
paper-to-playground/
│
├── agent.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── playground/
│   ├── __init__.py
│   ├── config.py
│   ├── orchestrator.py
│   ├── budget.py
│   ├── trace.py
│   ├── failures.py
│   │
│   ├── source/
│   │   ├── acquire.py
│   │   ├── document.py
│   │   ├── pdf.py
│   │   ├── html.py
│   │   ├── structure.py
│   │   └── visual_evidence.py
│   │
│   ├── retrieval/
│   │   ├── index.py
│   │   ├── retrieve.py
│   │   ├── confidence.py
│   │   └── evidence.py
│   │
│   ├── model/
│   │   ├── client.py
│   │   ├── prompts.py
│   │   ├── schemas.py
│   │   ├── generation.py
│   │   ├── verification.py
│   │   └── repair.py
│   │
│   ├── ir/
│   │   ├── models.py
│   │   ├── validate.py
│   │   ├── grounding.py
│   │   └── coverage.py
│   │
│   ├── computation/
│   │   ├── parser.py
│   │   ├── ast.py
│   │   ├── operations.py
│   │   ├── evaluator.py
│   │   ├── invariants.py
│   │   └── validate.py
│   │
│   ├── render/
│   │   ├── renderer.py
│   │   ├── manifest.py
│   │   ├── visual_planner.py
│   │   ├── layouts.py
│   │   └── runtime/
│   │       ├── runtime.js
│   │       └── styles.css
│   │
│   └── validation/
│       ├── source.py
│       ├── science.py
│       ├── pedagogy.py
│       ├── artifact.py
│       ├── browser.py
│       └── report.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── browser/
│   └── fixtures/
│
└── examples/
    └── case.json
```

The exact number of files may be adjusted for maintainability, but
architectural boundaries MUST remain.

------------------------------------------------------------------------

# 80. `agent.py`

Keep `agent.py` deliberately boring.

Responsibilities:

``` text
parse args
validate basic CLI
construct config
construct orchestrator
run
return exit code
```

It MUST NOT become the location for PDF parsing, prompts, HTML
construction, or scientific logic.

------------------------------------------------------------------------

# 81. Configuration

Centralize tunable constants.

Examples:

``` text
SOURCE_TIMEOUT_SECONDS
MODEL_TIMEOUT_SECONDS
MAX_TRANSIENT_RETRIES
MAX_EVIDENCE_CHUNKS
MAX_EVIDENCE_TOKENS
MAX_NEIGHBOR_EXPANSIONS
RETRIEVAL_HIGH_CONFIDENCE_THRESHOLD
BROWSER_TIMEOUT_SECONDS
FINALIZATION_RESERVE_SECONDS
NUMERIC_TOLERANCE
```

Do not scatter unexplained magic numbers.

Tune thresholds using benchmarks.

------------------------------------------------------------------------

# 82. Typed Models

Use explicit models for:

``` text
CaseInput
PaperDocument
SourceElement
EvidenceChunk
EvidencePack
ScientificModel
LessonSpec
ExplanationIR
ControlSpec
ComputationSpec
VisualSpec
ExplorationSpec
GroundingRecord
ValidationFinding
ValidationReport
Failure
RunBudget
```

Pydantic is recommended for model-generated structured contracts.

Plain dataclasses/typed structures are fine for internal deterministic
objects.

------------------------------------------------------------------------

# 83. Dependencies

Likely core dependencies:

``` text
PyMuPDF
httpx
pydantic
numpy
beautifulsoup4
```

plus the browser-control library proven compatible with the official
environment.

Rules:

-   exact versions pinned;
-   Python 3.11 tested;
-   no redundant HTTP libraries;
-   no LangChain;
-   no LlamaIndex;
-   no Torch;
-   no Transformers;
-   no sentence-transformers;
-   no vector database;
-   no required Node;
-   no required Docker;
-   no required system OCR.

Do not add a dependency merely because it is convenient.

------------------------------------------------------------------------

# 84. HTML Source Parsing

Use a lightweight static HTML parser such as BeautifulSoup.

Do not require browser rendering just to extract ordinary HTML papers.

Normalize extracted HTML content into the same `PaperDocument`.

------------------------------------------------------------------------

# 85. Scientific UI Runtime Source

Maintain:

``` text
playground/render/runtime/runtime.js
playground/render/runtime/styles.css
```

as normal source files.

At generation time:

``` text
read runtime
  +
lesson data
  +
manifest
  ↓
inline into index.html
```

This preserves maintainability while meeting the single-file output
contract.

------------------------------------------------------------------------

# 86. Equation Rendering

Avoid requiring a large browser math library if the supported DSL can be
rendered deterministically.

Build a small AST-based renderer capable of readable:

-   fractions;
-   powers;
-   subscripts;
-   square roots;
-   sums;
-   function calls;
-   vectors;
-   matrices.

A readable representation is more important than publication-grade TeX.

The displayed equation and executed equation should derive from the same
AST.

------------------------------------------------------------------------

# 87. Design System

Create the design system once.

It SHOULD define:

-   typography scale;
-   spacing scale;
-   cards/panels;
-   control appearance;
-   visual containers;
-   callouts;
-   source-grounding style;
-   responsive breakpoints;
-   focus states;
-   accessible contrast;
-   animation rules.

Do not spend model tokens designing CSS.

Animations SHOULD communicate state changes rather than decorate the
page.

------------------------------------------------------------------------

# 88. Accessibility Baseline

At minimum:

-   labels associated with controls;
-   keyboard-operable native controls;
-   visible focus;
-   readable text;
-   meaning not encoded by color alone;
-   textual explanation accompanies visual;
-   responsive layout.

Accessibility improves teaching quality even though it is not a
standalone rubric item.

------------------------------------------------------------------------

# 89. Determinism

Improve repeated-run reliability:

-   stable IDs;
-   deterministic renderer;
-   stable component selection rules;
-   seeded scientific randomness if any;
-   no wall-clock-dependent examples;
-   low-variance model settings where supported;
-   constrained schemas;
-   small semantic decision space.

Do not require byte-identical HTML between repeated model runs.

Require semantic consistency.

------------------------------------------------------------------------

# 90. Benchmark Corpus

Build an internal hidden-test simulator spanning mechanism families:

``` text
scalar relationship
probability/distribution
matrix transformation
sequential algorithm
state transition
optimization
signal processing
geometry
information flow
iterative process
comparative mechanism
dynamical system
```

Do not optimize only for public attention/entropy examples.

------------------------------------------------------------------------

# 91. Source-Structure Benchmark Diversity

Include:

-   normal prose;
-   equation-heavy section;
-   algorithm/pseudocode;
-   table-centric evidence;
-   figure/pipeline-centric evidence;
-   graph + textual discussion;
-   multi-column PDF;
-   long paper with small relevant section;
-   short clean paper;
-   messy extraction.

------------------------------------------------------------------------

# 92. Focus Benchmark Diversity

Test:

``` text
concept name
section reference
equation reference
figure reference
table reference
"how X affects Y"
"why normalization is needed"
"the pipeline shown in Figure 2"
"how the update rule changes the state"
```

------------------------------------------------------------------------

# 93. Audience Benchmark Diversity

Test different undergraduate profiles.

Verify explanation depth changes while science remains invariant.

------------------------------------------------------------------------

# 94. Development Oracles

For each benchmark case maintain a small human-written oracle
containing:

``` text
relevant section/equation
core mechanism
important variables
expected meaningful controls
reasonable visual family
key invariant
important limitation
claims that must not be made
```

These are test expectations, NOT runtime paper-specific templates.

Production modules MUST NEVER inspect fixture answers.

------------------------------------------------------------------------

# 95. Repeated-Run Testing

Because hidden cases are run twice, benchmark repeated identical runs.

Compare:

``` text
retrieved evidence
mechanism classification
controls
computation
visual family
exploration type
validation results
tokens
latency
repair/fallback path
```

Measure semantic variance, not text identity.

------------------------------------------------------------------------

# 96. Retrieval Benchmarking

Measure:

``` text
Top-1 success
Top-3 success
evidence sufficiency
Evidence Pack size
rerank frequency
expansion frequency
```

Tune retrieval confidence empirically.

Ablate DeepSeek reranking to verify it adds value.

Measure whether evidence expansion actually fixes insufficiency.

------------------------------------------------------------------------

# 97. Evidence Pack Optimization

Track:

``` text
tokens
chunks
equations
tables
figure contexts
```

Correlate with:

-   scientific accuracy;
-   token use;
-   latency.

Seek the smallest Evidence Pack that preserves reliability.

------------------------------------------------------------------------

# 98. Visual Evidence Tests

Explicitly test:

``` text
focus references Figure 2 -> relevant figure context included
focus unrelated to Figure 7 -> no expensive Figure 7 processing
focus references Table 3 -> table evidence included
table extraction fails -> caption/context fallback
graph trend supported -> trend explained
graph exact values not explicit -> no invented exact values
pipeline diagram -> useful caption/labels/context without multimodal model
```

------------------------------------------------------------------------

# 99. Computation Unit Tests

Every generic operation needs:

-   normal test;
-   boundary test;
-   invalid-input test;
-   shape test;
-   finite-output test.

Fuzz or stress the DSL parser with malformed expressions.

Test HTML/JSON escaping.

------------------------------------------------------------------------

# 100. Runtime Component Tests

Independently test:

``` text
Bar/Distribution
Line/Trajectory
Scatter
Matrix/Heatmap
Vector
Flow/Pipeline
State Graph
Waveform
Geometry Scene
Comparison
Process/Stepper
Equation Panel
```

Verify:

-   renders;
-   reacts to state;
-   semantic metadata present;
-   responsive behavior.

------------------------------------------------------------------------

# 101. Offline Tests

After generation:

1.  block/disable network;
2.  open `index.html`;
3.  verify page renders;
4.  verify controls;
5.  verify calculations;
6.  verify visuals;
7.  inspect network log if available.

Test direct:

``` text
file:///.../index.html
```

not only localhost.

------------------------------------------------------------------------

# 102. Failure Injection

Deliberately test:

``` text
missing source
corrupt PDF
empty extraction
table failure
low-confidence retrieval
OpenRouter timeout
429
5xx
malformed JSON
unknown operation
shape mismatch
invariant failure
broken visual
dead control
repair failure
browser unavailable
low time budget
near call limit
```

Verify the expected fallback path.

------------------------------------------------------------------------

# 103. Last-Known-Good Test

Automated scenario:

``` text
candidate A passes
candidate B repair fails
```

Expected final artifact:

``` text
candidate A
```

This is a mandatory reliability test.

------------------------------------------------------------------------

# 104. Budget Tests

Simulate:

-   9 calls already used;
-   finalization safety window reached;
-   completion-token pressure;
-   transport retry pressure.

Optional actions MUST be denied when unsafe.

------------------------------------------------------------------------

# 105. Trace Tests

Parse every produced trace.

Assert:

``` text
every line valid JSON
required event fields present
token counts nonnegative
elapsed times monotonic
no secret patterns
final event exists
failure precedes repair
repair precedes revalidation
fallback reason recorded
```

------------------------------------------------------------------------

# 106. Exact Assessment Rehearsal

Run from a fresh Python 3.11 environment:

``` bash
python -m pip install -r requirements.txt
python agent.py --input case.json --output out --model MODEL_ID
```

No IDE magic.

No manually started service.

No undeclared dependency.

No developer-specific absolute path.

------------------------------------------------------------------------

# 107. Optimization Order

Optimize in this order:

``` text
1. scientific failures
2. catastrophic/runtime failures
3. missing required features
4. teaching clarity
5. visual quality
6. repair frequency
7. tokens
8. latency
9. cosmetics
```

Do not reverse this order.

------------------------------------------------------------------------

# 108. Metrics

Track:

``` text
scientific failure rate
catastrophic/no-page rate
requirement compliance rate
first-pass validation rate
repair rate
repair success rate
fallback rate
fallback success rate
calls/run
prompt tokens/run
completion tokens/run
latency/run
duplicate-run semantic variance
custom-code frequency
browser-validation success rate
```

Also track p50/p95 where enough samples exist.

------------------------------------------------------------------------

# 109. Token Attribution

Break model usage down by:

``` text
retrieval rerank
main semantic call
optional second planning call
semantic verification
repair
```

If repairs dominate cost, improve first-pass contracts rather than
merely shortening prompts.

------------------------------------------------------------------------

# 110. Latency Attribution

Measure:

``` text
source acquisition
PDF parsing
retrieval
DeepSeek
rendering
browser startup
browser validation
```

Optimize the actual bottleneck.

Reuse one browser process/session per run where practical.

------------------------------------------------------------------------

# 111. Release Gate

Before freezing submission:

-   all deterministic unit tests pass;
-   all integration tests pass;
-   browser tests pass where environment supports them;
-   no known critical scientific failures in benchmark corpus;
-   public examples pass through generic pipeline;
-   offline tests pass;
-   `file://` tests pass;
-   trace tests pass;
-   no secret leakage;
-   resource limits respected;
-   duplicate-run consistency acceptable;
-   clean Python 3.11 installation passes;
-   exact evaluator command passes.

------------------------------------------------------------------------

# 112. Freeze Discipline

Once the winning configuration is chosen:

``` text
freeze prompts
freeze schemas
freeze thresholds
freeze operation registry
freeze renderer
freeze runtime
```

Then run full final rehearsal.

Avoid last-minute prompt changes without complete regression testing.

------------------------------------------------------------------------

# 113. Security and Injection Checklist

Before finalizing:

-   source text treated as data;
-   HTML escaped;
-   JSON safely embedded;
-   URL schemes sanitized;
-   no arbitrary eval;
-   no arbitrary exec;
-   no model-generated HTML by default;
-   no runtime network;
-   no API key leakage;
-   no local file disclosure;
-   no arbitrary path traversal from source metadata;
-   output writes constrained to run-owned locations.

------------------------------------------------------------------------

# 114. `.gitignore`

At minimum:

``` gitignore
.env
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
out/
tmp/
.DS_Store
```

Do not commit:

-   API keys;
-   assessment cases;
-   temporary PDFs unless intentionally licensed test fixtures;
-   generated transient artifacts.

------------------------------------------------------------------------

# 115. README Submission Information

The final human-facing README should retain the implementation-relevant
sections but also clearly state:

-   project title;
-   team members;
-   architecture summary;
-   setup;
-   exact run command;
-   input schema;
-   output contract;
-   model handling;
-   source support;
-   autonomous validation/repair;
-   example;
-   limitations;
-   reuse/credits.

This master specification may be condensed for presentation later, but
the implementation agent MUST first build against the complete contract.

------------------------------------------------------------------------

# 116. Example Input

``` json
{
  "source_url": "./examples/paper.pdf",
  "focus": "the update mechanism described in Equation 6",
  "audience": "second-year engineering undergraduate"
}
```

Example command:

``` bash
export OPENROUTER_API_KEY="..."
python agent.py --input examples/case.json --output out --model MODEL_ID
```

Windows PowerShell equivalent:

``` powershell
$env:OPENROUTER_API_KEY="..."
python agent.py --input examples/case.json --output out --model MODEL_ID
```

Never put a real key in documentation.

------------------------------------------------------------------------

# 117. Expected `index.html` Quality

The final artifact should feel like a purpose-built educational tool,
not generated prose pasted into a webpage.

A strong output should contain:

-   immediate central question;
-   short explanation of why concept matters;
-   compact intuition;
-   notation legend;
-   mechanism/equation;
-   live playground;
-   visible current values;
-   meaningful intermediate calculations;
-   mechanism-appropriate visualization;
-   two meaningful controls minimum;
-   two guided explorations with executable setups;
-   Reset;
-   limitation/assumption/misconception;
-   source grounding;
-   responsive polished presentation.

The page MUST prioritize scientific explanation over decoration.

------------------------------------------------------------------------

# 118. Expected Behavior on a Novel Paper

A key acceptance test:

Given a research paper never explicitly engineered into the code, with:

``` json
{
  "source_url": "./unknown_paper.pdf",
  "focus": "the transition rule in Section 4.2",
  "audience": "engineering undergraduate"
}
```

the system should:

1.  acquire and parse the paper;
2.  locate Section 4.2;
3.  gather its equation/paragraph/table/figure neighborhood;
4.  build a compact Evidence Pack;
5.  ask DeepSeek to formalize the mechanism;
6.  validate references;
7.  parse the computation into canonical AST/declarative spec;
8.  test the science;
9.  select a visual grammar;
10. compile the lesson into the Scientific UI Runtime;
11. statically validate;
12. execute in Chromium when available;
13. manipulate controls;
14. verify meaningful state/visual changes;
15. repair only targeted defects;
16. preserve last-known-good;
17. produce offline `index.html`;
18. produce complete `trace.jsonl`.

No paper-specific prewritten solution should be required.

------------------------------------------------------------------------

# 119. Things the Coding Agent MUST NOT Do

This section is deliberately explicit.

Do **not**:

-   replace this architecture with one giant LLM prompt;
-   ask DeepSeek to generate the complete HTML page;
-   special-case attention;
-   special-case entropy;
-   special-case named public papers;
-   add a second model;
-   add JEV;
-   add embeddings;
-   add a vector database;
-   add LangChain/LlamaIndex merely for "agentic" appearance;
-   require Docker;
-   require npm;
-   require Node;
-   require a server;
-   require GPU;
-   require Tesseract system installation;
-   require Playwright browser download unless explicitly proven
    compatible with assessment setup;
-   invent paper claims;
-   infer exact graph values from pixels;
-   silently fix paper equations using textbook knowledge;
-   use `eval`/`exec`;
-   allow source text to become prompt instruction;
-   emit external CDN dependencies;
-   use remote fonts;
-   use runtime API calls in generated HTML;
-   trust model calculations without deterministic execution;
-   trust model citations without evidence IDs;
-   trust generated controls without interaction testing;
-   overwrite last-known-good with an unvalidated repair;
-   spend model calls on deterministic checks;
-   loop repairs indefinitely;
-   consume the final time reserve on cosmetics.

------------------------------------------------------------------------

# 120. Things the Coding Agent MUST Implement Early

Do not postpone reliability infrastructure until after the "main
feature."

Implementation order SHOULD be:

## Phase A --- Contracts and skeleton

1.  root CLI;
2.  CaseInput;
3.  config;
4.  failure model;
5.  trace;
6.  RunBudget;
7.  orchestrator state skeleton;
8.  output/staging management.

## Phase B --- Source pipeline

1.  local acquisition;
2.  remote acquisition;
3.  format detection;
4.  PDF PaperDocument;
5.  HTML PaperDocument;
6.  section/paragraph/equation extraction;
7.  table extraction;
8.  figure/caption/context extraction;
9.  extraction sanity validator.

## Phase C --- Retrieval

1.  section-aware chunking;
2.  explicit reference lookup;
3.  lexical scoring;
4.  BM25;
5.  confidence;
6.  Evidence Pack;
7.  optional DeepSeek reranker.

## Phase D --- Model contracts

1.  OpenRouter client;
2.  prompt builder;
3.  Pydantic IR contracts;
4.  semantic generation;
5.  JSON recovery;
6.  schema/reference validation.

## Phase E --- Computation

1.  DSL parser;
2.  canonical AST;
3.  operation registry;
4.  Python evaluator;
5.  invariants;
6.  iterative/state specs;
7.  computation validator.

## Phase F --- Scientific UI Runtime

1.  state engine;
2.  JS AST evaluator;
3.  controls;
4.  equation renderer;
5.  generic visual primitives;
6.  mechanism visual planner;
7.  guided explorations;
8.  Reset;
9.  manifest;
10. deterministic HTML shell.

## Phase G --- Validation

1.  IR validators;
2.  artifact validator;
3.  coverage validator;
4.  grounding validator;
5.  browser controller;
6.  interaction trajectory.

## Phase H --- Repair/fallback

1.  deterministic repair;
2.  targeted semantic repair;
3.  staging promotion;
4.  last-known-good;
5.  fallback ladders;
6.  finalization safety window.

## Phase I --- Tests and benchmarks

Implement tests alongside each phase rather than at the end.

------------------------------------------------------------------------

# 121. First-Pass Completion Definition

The coding agent should not stop when:

``` text
"agent.py runs"
```

or:

``` text
"it generated HTML"
```

The first coding pass is complete only when the repository contains:

-   working exact CLI;
-   source parsing;
-   visual/table evidence handling;
-   deterministic retrieval;
-   Evidence Pack;
-   DeepSeek client;
-   structured Scientific Model/Lesson Spec/IR;
-   canonical math DSL/AST;
-   deterministic scientific evaluator;
-   generic UI runtime;
-   meaningful visual components;
-   guided exploration presets;
-   offline single-file rendering;
-   manifest;
-   source grounding;
-   validation gates;
-   browser interaction validation or explicit tested graceful fallback;
-   repair/fallback logic;
-   last-known-good;
-   budget manager;
-   trace;
-   tests;
-   example;
-   pinned requirements;
-   documented limitations.

Do not deliberately leave these as "future work" if they are part of
this specification.

------------------------------------------------------------------------

# 122. Acceptance Checklist for the Coding Agent

Before claiming implementation complete, run this checklist.

## Contract

-   [ ] Python 3.11.
-   [ ] `agent.py` at root.
-   [ ] pinned `requirements.txt`.
-   [ ] exact evaluator command works.
-   [ ] exactly three required input strings.
-   [ ] supplied model ID used for all calls.
-   [ ] OpenRouter key from environment only.
-   [ ] resource limits enforced.
-   [ ] output contains `index.html` and `trace.jsonl`.

## Source

-   [ ] local PDF works.
-   [ ] URL acquisition works or fails cleanly.
-   [ ] section extraction.
-   [ ] equation provenance.
-   [ ] table extraction/fallback.
-   [ ] figure/caption/context extraction.
-   [ ] multi-column sanity.
-   [ ] no invented provenance.

## Retrieval

-   [ ] explicit section lookup.
-   [ ] equation lookup.
-   [ ] figure/table lookup.
-   [ ] BM25/lexical.
-   [ ] confidence.
-   [ ] bounded rerank.
-   [ ] bounded expansion.
-   [ ] compact Evidence Pack.

## Semantic

-   [ ] Scientific Model.
-   [ ] Lesson Spec.
-   [ ] knowledge classes.
-   [ ] evidence refs.
-   [ ] unsupported state.
-   [ ] focus coverage.
-   [ ] audience adaptation.

## Computation

-   [ ] restricted DSL.
-   [ ] canonical AST.
-   [ ] no eval.
-   [ ] Python evaluator.
-   [ ] browser evaluator.
-   [ ] equation renderer.
-   [ ] shape/domain validation.
-   [ ] invariants.
-   [ ] boundary tests.
-   [ ] presets execute.

## Teaching

-   [ ] central question.
-   [ ] intuition.
-   [ ] symbols.
-   [ ] formal mechanism.
-   [ ] at least two meaningful controls.
-   [ ] meaningful visual.
-   [ ] important intermediates.
-   [ ] exploration 1.
-   [ ] exploration 2.
-   [ ] limitation/assumption/misconception.
-   [ ] source grounding.
-   [ ] Reset.

## Rendering

-   [ ] single HTML.
-   [ ] embedded CSS.
-   [ ] embedded JS.
-   [ ] embedded manifest.
-   [ ] no CDN.
-   [ ] no remote font.
-   [ ] no runtime network.
-   [ ] safe escaping.
-   [ ] semantic DOM metadata.
-   [ ] responsive layout.

## Verification

-   [ ] source gate.
-   [ ] scientific gate.
-   [ ] pedagogy gate.
-   [ ] computation gate.
-   [ ] artifact gate.
-   [ ] browser gate.
-   [ ] grounding.
-   [ ] coverage.
-   [ ] dead-control detection.
-   [ ] dead-visual detection.
-   [ ] reset test.
-   [ ] preset test.

## Reliability

-   [ ] typed failures.
-   [ ] bounded retries.
-   [ ] targeted repair.
-   [ ] revalidation.
-   [ ] fallback.
-   [ ] staging.
-   [ ] last-known-good.
-   [ ] safety window.
-   [ ] atomic final writes.

## Trace

-   [ ] valid JSONL.
-   [ ] monotonic elapsed time.
-   [ ] call usage.
-   [ ] prompt/completion tokens.
-   [ ] validation events.
-   [ ] failures.
-   [ ] repairs.
-   [ ] fallbacks.
-   [ ] final event.
-   [ ] no secrets.
-   [ ] no hidden reasoning.

## Testing

-   [ ] unit tests.
-   [ ] integration tests.
-   [ ] browser tests.
-   [ ] offline test.
-   [ ] `file://` test.
-   [ ] prompt-injection test.
-   [ ] malformed IR tests.
-   [ ] failure injection.
-   [ ] duplicate-run benchmark.
-   [ ] public examples generic.
-   [ ] non-ML papers tested.
-   [ ] fresh Python 3.11 install.

------------------------------------------------------------------------

# 123. Final Pre-Submission Audit

From a fresh clone:

``` text
1. inspect repository for secrets
2. create clean Python 3.11 environment
3. pip install requirements
4. run tests
5. run representative local PDF case
6. run representative URL case if applicable
7. run public regression cases
8. run diverse internal cases
9. run duplicate executions
10. inspect token/call/time budgets
11. open generated HTML offline
12. open generated HTML via file://
13. operate every required control
14. run guided presets
15. verify Reset
16. parse trace.jsonl
17. inspect network behavior
18. verify no CDN/remote dependencies
19. verify output directory contract
20. verify exit code
21. verify git status
22. freeze implementation
23. run final complete rehearsal
24. record full Git commit SHA
```

Submit the verified GitHub URL and full commit SHA.

------------------------------------------------------------------------

# 124. Architectural Rationale

The architecture deliberately responds to the likely failure modes of
LLM-generated interactive scientific pages:

## Failure: prompt/spec misalignment

Defense:

``` text
focus retrieval
FocusCoverageMap
structured Lesson Spec
IR -> manifest -> DOM coverage
```

## Failure: hallucinated science

Defense:

``` text
Evidence Pack
immutable evidence IDs
knowledge classes
claim grounding
unsupported states
risk-triggered semantic verification
```

## Failure: wrong calculations

Defense:

``` text
restricted DSL
canonical AST
Python evaluator
invariants
boundary tests
browser evaluator
```

## Failure: displayed equation differs from code

Defense:

``` text
same AST -> equation renderer + execution
```

## Failure: dead controls

Defense:

``` text
control dependency contracts
browser trajectory
semantic DOM metadata
```

## Failure: pretty but meaningless visualization

Defense:

``` text
mechanism family
visual question
visual intent
visual grammar
scientific dependency state
```

## Failure: model omits required features

Defense:

``` text
strict IR
pedagogy validator
manifest
coverage validator
artifact validator
```

## Failure: repair makes page worse

Defense:

``` text
staging
revalidation
last-known-good
```

## Failure: model is weak

Defense:

``` text
deterministic parsing
deterministic retrieval
small Evidence Pack
constrained model task
pre-engineered UI
deterministic computation
deterministic validation
targeted repair
```

## Failure: efficiency penalty

Defense:

``` text
few model calls
compact evidence
small structured outputs
no mandatory critic
deterministic validators
targeted repair
budget manager
```

------------------------------------------------------------------------

# 125. Final Mental Model

If implementation becomes confusing, return to this model:

``` text
                     RESEARCH SOURCE
                           │
                           ▼
                     PaperDocument
                           │
                           ▼
                       Retrieval
                           │
                           ▼
                     Evidence Pack
                           │
                           ▼
                  DeepSeek V4.1 Flash
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
          Scientific Model       Lesson Spec
                 └─────────┬─────────┘
                           ▼
                     Explanation IR
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
         Grounding     Computation    Visual Plan
                          DSL
                           │
                           ▼
                     Canonical AST
                    ┌──────┼──────┐
                    ▼      ▼      ▼
                 Python   JS   Equation
                    └──────┼──────┘
                           ▼
                 Scientific UI Runtime
                           │
                           ▼
                    Candidate HTML
                           │
                           ▼
                      Validation
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                  PASS           FAIL
                    │             │
                    │      Repair/Fallback
                    │             │
                    └──────┬──────┘
                           ▼
                    Last Known Good
                           │
                           ▼
                       FINALIZE
                     ┌─────┴─────┐
                     ▼           ▼
                index.html   trace.jsonl
```

And remember the seven-word pipeline:

> **Understand -\> Formalize -\> Teach -\> Generate -\> Execute -\>
> Verify -\> Repair**

------------------------------------------------------------------------

# 126. Definition of Done

The project is done when a previously unseen, appropriately scoped
engineering research-paper case can be passed to the exact required CLI
and the frozen generator autonomously produces a scientifically
grounded, focused, polished, interactive, executable, offline lesson
plus a truthful trace, while remaining within the assessment resource
limits and without paper-specific runtime special-casing.

The generator should behave less like an LLM webpage demo and more like
a **verified compiler for interactive scientific explanations**.

That is the product to implement.

------------------------------------------------------------------------

# 127. Final Instruction to the Coding Agent

Implement this specification as a coherent system.

Do not optimize for producing code quickly at the expense of leaving
validation, provenance, fallbacks, tests, or submission-contract details
for a later cleanup pass.

Before changing an architectural choice, ask:

1.  Does the existing decision violate the assignment contract?
2.  Is it impossible in Python 3.11/pip-only constraints?
3.  Has an environment test proven it unreliable?
4.  Does a benchmark prove another implementation materially improves
    scientific correctness or reliability?

If none applies, preserve the specified architecture.

Prioritize a smaller, thoroughly integrated implementation over a
sprawling partially connected implementation, but do not remove core
layers merely to shorten the codebase.

The first complete coding pass should already include the reliability
mechanisms that make the system trustworthy:

``` text
grounding
contracts
canonical computation
validation
browser checks
repair
fallback
last-known-good
budget control
trace
tests
```

These are not post-MVP polish. They are part of the product.

**Build the system we designed, not a simplified approximation of it.**
