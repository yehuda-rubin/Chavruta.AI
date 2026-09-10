"""generate_en_templates.py — Generate English companion templates for all 53 templates.

Creates:
- TEMPLATE_lesson_flow_en.md
- TEMPLATE_full_lesson_en.md
- (and TEMPLATE_source_sheet.md / TEMPLATE_answer_en.md for shut templates if needed)
Updates manifest.yaml to include:
  title_en: "..."
  files_en:
    source_sheet: TEMPLATE_source_sheet.md
    lesson_flow: TEMPLATE_lesson_flow_en.md
    full_lesson: TEMPLATE_full_lesson_en.md
"""

import os
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO / "lessons" / "templates"

BAND_INFO_EN = {
    "a-c": {
        "title_suffix": "Grades 1–3 (Early Elementary)",
        "grade_header": "Grades 1–3",
        "age_range": "Grades 1–3 (ages 6–9 · early elementary)",
        "duration": "30 min",
        "developmental_stage": (
            "Concrete thinking and short attention span; learning through storytelling, "
            "imagery, movement, and role-play. One key idea per lesson."
        ),
        "pedagogy_note": (
            "- **Language:** Very simple English; translate and define any Hebrew/Aramaic or difficult terms; short sentences.\n"
            "- **Sources in this lesson:** [S1], [S2], [S3] (see source sheet).\n"
            "- The lesson flow was composed by the model from retrieved sources — **without an external model API**. "
            "Adjust pacing and level to your classroom."
        ),
        "hook_desc": (
            "Experiential opening — a short story, a large visual, a concrete object, or an intriguing question "
            '("What would you do if...?").'
        ),
        "i_do_desc": (
            "Teacher narrates or reads the source aloud, translates each term, and paints a vivid picture with words; "
            "one core key phrase is repeated together."
        ),
        "we_do_desc": (
            "All together: short skit or gesture, finger following the text, choral completion of key words — "
            "lots of repetition and movement."
        ),
        "you_do_desc": (
            'Every child individually: drawing the central idea, completing a key sentence, or "tell your partner '
            'in one word what we learned."'
        ),
        "formative_desc": (
            'Oral and visual check: "Show me through role-play," "Which color best matches this idea?", '
            "three quick yes/no questions."
        ),
    },
    "d-f": {
        "title_suffix": "Grades 4–6 (Upper Elementary)",
        "grade_header": "Grades 4–6",
        "age_range": "Grades 4–6 (ages 9–12 · upper elementary)",
        "duration": "45 min",
        "developmental_stage": (
            "Emerging abstract thinking; able to analyze a source with one commentary and compare two opinions simply."
        ),
        "pedagogy_note": (
            "- **Language:** Clear, accessible English; define new terms; encourage students to formulate ideas in their own words.\n"
            "- **Sources in this lesson:** [S1], [S2], [S3], [S4] (see source sheet).\n"
            "- The lesson flow was composed by the model from retrieved sources — **without an external model API**. "
            "Adjust pacing and level to your classroom."
        ),
        "hook_desc": (
            'Opening puzzle or question presenting a real dilemma ("How could it be that...?") or connecting to the child\'s daily life.'
        ),
        "i_do_desc": (
            'Teacher demonstrates a "worked example": reads the source, poses the guiding question, and shows how the commentary resolves it step by step.'
        ),
        "we_do_desc": (
            "Guided practice in pairs (early chavruta): analyze a second source together using a graphic organizer (table: source / question / answer)."
        ),
        "you_do_desc": (
            "Independent task: worksheet matching commentary to text, comparing two opinions in a chart, or summarizing the main takeaway in 1–2 sentences."
        ),
        "formative_desc": (
            "Exit ticket (one written reflection question) + quick retrieval-practice check at the start of the next lesson."
        ),
    },
    "g-i": {
        "title_suffix": "Grades 7–9 (Middle School)",
        "grade_header": "Grades 7–9",
        "age_range": "Grades 7–9 (ages 12–15 · middle school)",
        "duration": "45 min",
        "developmental_stage": (
            "Developing abstract reasoning; personal relevance and identity are paramount; able to trace a debate to its conceptual root and construct a reasoned argument."
        ),
        "pedagogy_note": (
            "- **Language:** Full academic English; introduce core talmudic/halachic terms (Machloket, Sevara, Nafka Mina) with clear definitions.\n"
            "- **Sources in this lesson:** [S1], [S2], [S3], [S4] (see source sheet).\n"
            "- The lesson flow was composed by the model from retrieved sources — **without an external model API**. "
            "Adjust pacing and level to your classroom."
        ),
        "hook_desc": (
            'Opening dilemma or dispute ("Two sides disagree — who is correct and why?") or an ethical question touching their world.'
        ),
        "i_do_desc": (
            "Teacher presents the dispute or core inquiry with two clear sides (Side A vs. Side B), demonstrating how to dissect a primary source and extract its argument."
        ),
        "we_do_desc": (
            "Chavruta study: each pair takes one perspective and finds textual evidence in the sources, followed by a structured class debate."
        ),
        "you_do_desc": (
            'Independent argumentative writing: "Choose a position and defend it using two distinct sources"; analyze a fresh related source independently.'
        ),
        "formative_desc": (
            "Written argument or debate assessment; rubric: clear claim + two cited sources [S#] + reasoned conclusion."
        ),
    },
    "j-l": {
        "title_suffix": "Grades 10–12 (High School)",
        "grade_header": "Grades 10–12",
        "age_range": "Grades 10–12 (ages 15–18 · high school)",
        "duration": "45–60 min",
        "developmental_stage": (
            "Near-adult analytical thinking; source-based textual analysis, sustained inquiry, and primary text competence; "
            "bridge to beit-midrash iyun with supportive scaffolding and existential relevance."
        ),
        "pedagogy_note": (
            "- **Language:** Precise analytical English with lamdanic terminology; fostering independent textual interpretation.\n"
            "- **Sources in this lesson:** [S1], [S2], [S3], [S4], [S5] (see source sheet).\n"
            "- The lesson flow was composed by the model from retrieved sources — **without an external model API**. "
            "Adjust pacing and level to your classroom."
        ),
        "hook_desc": (
            'Principled inquiry or sharp test-case forcing deep thought ("What is the law here — and why is it doubtful in the first place?").'
        ),
        "i_do_desc": (
            "Teacher articulates a conceptual inquiry with two rigorous analytical sides, modeling how to dissect a primary text and align it with a theoretical stance."
        ),
        "we_do_desc": (
            "In-depth chavruta: analyzing early commentators (Rishonim) and introducing later authorities (Acharonim), mapping each source to its underlying premise with guiding questions."
        ),
        "you_do_desc": (
            "Independent work: analyzing an unfamiliar source, writing a concise analytical essay/synthesis, or preparing a passage for peer presentation."
        ),
        "formative_desc": (
            "Analytical essay / sugya summary / source-analysis exam; rubric: formulation of the inquiry, mapping opinions, practical distinction (nafka mina), and conclusion."
        ),
    },
}

SUBJECT_DETAILS = {
    "aggada": {
        "title_en_base": "Aggadah and Midrash",
        "subject_en": "Aggadah and Midrash",
        "bm_title": "Aggadah and Midrash — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Puzzling Aggadah / Midrash",
        "bm_stages": [
            ("0. Opening — The Puzzling Narrative", "≈5 min",
             "- **Hook:** [Present the aggadic narrative briefly — highlight how bizarre or unexpected it sounds at face value. Spark curiosity.]\n"
             "- **Objective:** Uncover the profound conceptual idea Chazal encoded within the imagery."),
            ("1. Textual Examination of the Narrative", "≈8 min",
             "- Read **[S1]** in full — [Pay close attention to every detail, phrasing, and character action; the nuances are the key to decoding the story.]"),
            ("2. Formulating the Core Difficulty", "≈8 min",
             "- **[S2]** — [Articulate the difficulty: what is impossible or deeply perplexing here if read literally? Chazal never spoke superfluously.]"),
            ("3. Classical Rabbinic Commentaries", "≈13 min",
             "- **[S3]** and **[S4]** (Rashi / Maharsha / Ein Yaakov) — [How the classic commentators decipher the narrative.]\n"
             "  - *Chavruta Pause:* [What is the parable (mashal), and what is the underlying moral or theological reality (nimshal)?]"),
            ("4. Philosophical and Conceptual Deepening", "≈8 min",
             "- **[S5]** (Maharal / Jewish Thought) — [The overarching theological or psychological principle behind the imagery — why did the Sages clothe it specifically in this motif?]"),
            ("5. Moral Takeaway and Life Application", "≈5 min",
             "- **[S6]** — [What the aggadah demands of our personal character, faith, and daily conduct.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The primary difficulty in the literal reading of the aggadah]\n"
             "  2. [The relationship between the mashal and nimshal]\n"
             "  3. [The timeless ethical and existential lesson]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Flowing paragraph introducing the narrative and emphasizing how startling it appears at first glance. Raise the curiosity: Chazal did not mean for this to be understood superficially — so what is the deeper intent?]"),
            ("Part I — The Narrative and Textual Nuance", "[Present the aggadic text **[S1]** completely within the narrative prose, highlighting specific phrases and linguistic subtleties that hold clues to its interpretation.]"),
            ("Part II — The Underlying Difficulty", "[Articulate the fundamental difficulty **[S2]**: what breaks down if we understand this literally? Demonstrate how this very question compels us to look beyond the surface.]"),
            ("Part III — The Sages and Commentators", "[Explore the commentaries **[S3]**, **[S4]** (Rashi, Maharsha, Ein Yaakov): show how they unlock the parable, identifying what each character or element represents.]"),
            ("Part IV — Conceptual Elevation", "[Develop the profound philosophical insight **[S5]** (Maharal / Jewish Philosophy): why did the Sages express this truth through narrative rather than abstract doctrine?]"),
            ("Part V — Living the Message", "[Translate the theological insight into practical character development and personal guidance **[S6]**. Conclude with a flowing paragraph connecting the enigmatic tale to its living moral heartbeat.]")
        ],
        "school_deepen_title": "Deepening — Unpacking the Parable and Meaning",
        "school_deepen_desc": "[Introduce **[S3]** and complementary source; analyze the difference between the surface story and its inner meaning; ask comprehension and application questions.]",
        "school_summary_theme": "the moral message and inner wisdom of the story"
    },
    "chassidut": {
        "title_en_base": "Chassidut and Inwardness",
        "subject_en": "Chassidut and Inwardness",
        "bm_title": "Chassidut and Inwardness — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Chassidic Concept / Ma'amar",
        "bm_stages": [
            ("0. Opening — The Spiritual Core and Inner Yearning", "≈5 min",
             "- **Hook:** [Present the existential or spiritual longing that lies at the heart of this teaching — the soul's yearning for connection.]\n"
             "- **Objective:** Illuminate how divine oneness and inner service (Avodat Hashem) transform our daily consciousness."),
            ("1. The Foundational Text / Ma'amar", "≈10 min",
             "- Study **[S1]** — [Examine the core passage from the Torah, Zohar, or early Chassidic master; identify the central spiritual question.]"),
            ("2. The Spiritual Paradox / Inner Tension", "≈10 min",
             "- **[S2]** — [Define the paradox (e.g. ratzo v'shov, bitul vs. yeshut, concealment vs. revelation). How does this tension manifest in the human heart?]"),
            ("3. Illuminating the Concept — Chassidic Masters", "≈12 min",
             "- **[S3]** and **[S4]** (Baal Shem Tov / Maggid / Tanya / Sfat Emet) — [Trace how the masters elucidate the light hidden within the concept.]\n"
             "  - *Chavruta Pause:* [How does this perspective transform our view of our own challenges and spiritual obstacles?]"),
            ("4. The Inner Dimension of Divine Service", "≈8 min",
             "- **[S5]** — [Deepening into internal contemplation (Hitbonenut) and prayer (Avodat HaTefilah); elevating mundane reality.]"),
            ("5. Practical Spiritual Guidance & Daily Life", "≈5 min",
             "- **[S6]** — [Translating the mystical light into practical warmth, joy, humility, and love of one's fellow Jew (Ahavat Yisrael).]\n"
             "- **Three Review Questions:**\n"
             "  1. [The spiritual paradox formulated in the teaching]\n"
             "  2. [How the Chassidic masters resolve or sweeten this tension]\n"
             "  3. [Practical application in everyday personal service]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening prose capturing the soul's inner yearning and the spiritual context of the teaching. Set the atmosphere of warmth, awe, and contemplation.]"),
            ("Part I — The Foundational Light", "[Present the core text **[S1]** in flowing prose, elucidating the biblical or kabbalistic anchor upon which the Chassidic teaching is built.]"),
            ("Part II — The Paradox of the Heart", "[Articulate the spiritual tension **[S2]**: the encounter between divine infinity and human limitation. Show how this paradox is felt in daily life.]"),
            ("Part III — The Teachings of the Masters", "[Unfold the insights of the Chassidic luminaries **[S3]**, **[S4]**: how their novel interpretations reveal the divine presence within the concealment.]"),
            ("Part IV — Avodat Hashem — Inward Transformation", "[Explore the internal soul-work **[S5]**: prayer, joy, breaking personal boundaries, and awakening unconditional love.]"),
            ("Part V — Living the Teaching in Daily Action", "[Synthesize the spiritual teaching **[S6]** into concrete guidance for interpersonal relationships, prayer, and sanctifying the physical world. End with an inspiring reflection.]")
        ],
        "school_deepen_title": "Deepening — Serving Hashem with Joy and Heart",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to discover how this idea helps us feel close to Hashem, love our friends, and perform mitzvot with joy.]",
        "school_summary_theme": "serving Hashem with heart, joy, and warmth"
    },
    "gemara-iyun": {
        "title_en_base": "Talmudic Analysis (Iyun)",
        "subject_en": "Talmudic Analysis (Lamdanut)",
        "bm_title": "Talmudic Analysis (Lamdanut) — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Sugya in Depth",
        "bm_stages": [
            ("0. Introduction — Framing the Sugya", "≈7 min",
             "- **Setting the Stage:** [Identify the location of the sugya within the tractate and introduce the central legal mechanism under discussion.]\n"
             "- **Objective:** [State the analytical inquiry (chakira) we will clarify and the halachic ramifications hanging upon it.]"),
            ("1. Textual Study of the Sugya", "≈12 min",
             "- Read and dissect **[S1]** — [Break down the Gemara's flow step-by-step: challenge, resolution, textual proof, and dialectic progression.]"),
            ("2. Formulating the Core Inquiry (Chakira)", "≈13 min",
             "- **[S2]** — [Present the textual contradiction or logical tension that sparks the inquiry.]\n"
             "- **The Chakira:** [Sharply formulate the two conceptual sides — Side A vs. Side B. Guide the learners to weigh the merits of each side.]"),
            ("3. Early Authorities (Rishonim)", "≈15 min",
             "- **[S3]** (Rashi / Tosafot) and **[S4]** (Ramban / Ritva / Rosh) — [Demonstrate how each Rishon aligns with a distinct side of the chakira.]\n"
             "  - *Chavruta Pause:* [Guiding question: What fundamental premise compels each Rishon to adopt their stance?]"),
            ("4. Later Authorities (Acharonim) — Conceptual Refinement", "≈15 min",
             "- **[S5]** and **[S6]** (Ktzot HaChoshen / R. Chaim Brisker / Sha'arei Yosher / Even HaEzel) — [How the Acharonim crystallized the debate using precise conceptual categories (e.g. Gavra vs. Cheftza, Din vs. Geder, Cause vs. Indicator).]\n"
             "- **The Core Insight:** [The central theoretical principle (yesod) that unites the sugya.]"),
            ("5. Halachic & Conceptual Resolution (Nafka Mina)", "≈8 min",
             "- **[S7]** — [How the chakira resolves disputes among the early authorities, and the practical distinctions that emerge.]\n"
             "- **Three Review Questions:**\n"
             "  1. [Formulation of the two sides of the chakira]\n"
             "  2. [Alignment of the Rishonim and Acharonim with each side]\n"
             "  3. [The practical and theoretical nafka mina]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Flowing opening paragraph situating the sugya in its tractate and introducing the central legal question. Hint at the analytical inquiry that will guide our study.]"),
            ("Part I — Dissecting the Sugya", "[Trace the Gemara's dialectic **[S1]** step-by-step within the prose: the question, answer, and biblical or logical proof. Ensure the text is firmly grasped before proceeding.]"),
            ("Part II — Formulating the Chakira", "[Introduce the textual difficulty or internal tension **[S2]**, and sharply delineate the two possible conceptual understandings. Elaborate both sides fully without premature resolution.]"),
            ("Part III — The Perspectives of the Rishonim", "[Examine the opinions of the Rishonim **[S3]**, **[S4]** in depth. Demonstrate how their disagreement is the direct embodiment of the conceptual chakira.]"),
            ("Part IV — The Lamdanut of the Acharonim", "[Unpack the analytical frameworks of the Acharonim **[S5]**, **[S6]** (e.g. person vs. object, intrinsic obligation vs. external condition). This is the analytical heart of the shiur.]"),
            ("Part V — Resolution and Practical Distinctions (Nafka Mina)", "[Demonstrate how the analytical principle resolves the sugya and impacts practical cases **[S7]**. Conclude with a cohesive synthesis leaving the learner with a versatile conceptual tool.]")
        ],
        "school_deepen_title": "Deepening — Perspectives of the Commentators",
        "school_deepen_desc": "[Introduce **[S3]** and additional commentary; explore the underlying reasons for the disagreement; guide students to compare both views in a structured manner.]",
        "school_summary_theme": "the central Talmudic principle and its lesson"
    },
    "general": {
        "title_en_base": "General Talmud Sugya and Halacha",
        "subject_en": "Talmud Sugya and Halacha",
        "bm_title": "Talmudic Sugya and Halacha — General Scaffold",
        "bm_topic_placeholder": "The Sugya and Its Halachic Development",
        "bm_stages": [
            ("0. Opening — Setting the Scene & The Central Question", "≈5 min",
             "- **Setting the Stage:** [Introduce the topic and the fundamental legal or conceptual question it raises.]\n"
             "- **Objective:** Trace the development of the topic from the Talmudic source through the early commentators to practical halacha."),
            ("1. The Talmudic Foundation", "≈10 min",
             "- Read **[S1]** — [Analyze the primary Gemara passage, establishing the dispute, the case, and the initial reasoning.]"),
            ("2. Conflicting Interpretations of the Rishonim", "≈15 min",
             "- **[S2]** and **[S3]** — [Examine how the classic Rishonim interpret the passage and where their core disagreement lies.]\n"
             "  - *Chavruta Pause:* [What textual or logical consideration leads each commentator to their conclusion?]"),
            ("3. From Talmud to Codification", "≈10 min",
             "- **[S4]** and **[S5]** (Rambam / Shulchan Aruch) — [How the halachic codifiers rule on this sugya, noting variations between traditions.]"),
            ("4. Conceptual Insights & Modern Ramifications", "≈10 min",
             "- **[S6]** — [How later authorities apply this principle to contemporary questions or border cases.]"),
            ("5. Summary & Key Takeaways", "≈5 min",
             "- Synthesize the progression from source to practice.\n"
             "- **Three Review Questions:**\n"
             "  1. [The core premise of the Talmudic sugya]\n"
             "  2. [The central dispute among the Rishonim]\n"
             "  3. [The halachic ruling and its application]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening prose presenting the topic, framing why this sugya is vital, and previewing the journey from Talmudic origin to practical observance.]"),
            ("Part I — The Talmudic Source", "[Present and explain the foundational Talmudic passage **[S1]** in clean, lucid prose, clarifying its context and terminology.]"),
            ("Part II — The Debate Among the Early Authorities", "[Detail the differing interpretations of the Rishonim **[S2]**, **[S3]**, explaining the logic underpinning each approach.]"),
            ("Part III — Codification in Halacha", "[Examine the rulings of the major codes **[S4]**, **[S5]** (Rambam, Shulchan Aruch), explaining how the dispute was weighed and settled.]"),
            ("Part IV — Application to Contemporary Situations", "[Explore modern applications **[S6]**, demonstrating how the ancient text continues to govern real-life circumstances today.]"),
            ("Part V — Synthesis and Conclusion", "[Bring together the textual, conceptual, and halachic threads into a unified summary, reinforcing the core enduring idea.]")
        ],
        "school_deepen_title": "Deepening — Comparing Perspectives and Ideas",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to compare two approaches and identify what makes each unique.]",
        "school_summary_theme": "the overarching lesson and its halachic application"
    },
    "halacha": {
        "title_en_base": "Practical Halacha (Pesak)",
        "subject_en": "Halacha and Mitzvot",
        "bm_title": "Practical Halacha (Pesak) — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Halachic Question in Practice",
        "bm_stages": [
            ("0. Opening — Real-World Scenario", "≈5 min",
             "- **The Case:** [Present a concrete, everyday situation that anyone might encounter — setting up the halachic dilemma.]\n"
             "- **Objective:** Reach a clear practical ruling alongside understanding its underlying rationale, to apply to analogous cases."),
            ("1. Defining the Question & Legal Scope", "≈7 min",
             "- **[S1]** — [What is the underlying prohibition or obligation, and why is this case not straightforward?]"),
            ("2. Foundational Source (Mishnah / Gemara)", "≈8 min",
             "- **[S2]** — [Where the law originated in primary rabbinic sources and what the base ruling established.]"),
            ("3. Early Authorities (Rishonim)", "≈8 min",
             "- **[S3]** — [How the Rishonim understood and defined the scope of the rule; delineate any foundational dispute.]"),
            ("4. Codification — Shulchan Aruch & Poskim", "≈12 min",
             "- **[S4]** (Shulchan Aruch & Rama) — [The normative codification, noting Ashkenazic and Sephardic distinctions.]\n"
             "- **[S5]** (Mishnah Berurah / Classic Acharonim) — [Further nuances, exceptions, and boundaries.]\n"
             "- **[S6]** (Contemporary Responsa: Igrot Moshe / Yabia Omer / Peninei Halacha) — [Application to modern technology or conditions.]\n"
             "  - *Chavruta Pause:* [Where exactly does the boundary between permissible and prohibited fall, and why?]"),
            ("5. Practical Ruling (Halacha LeMa'aseh) & Summary", "≈5 min",
             "- **[S7]** — [The clear conclusion: what should one do in practice, including conditions, safeguards, and customs.]\n"
             "- **Border Case (Nafka Mina):** [A test-case that illustrates the boundary of the ruling.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The underlying category of the law]\n"
             "  2. [The primary dispute among codifiers]\n"
             "  3. [The practical halacha and its boundary lines]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Flowing paragraph introducing a relatable real-world dilemma that triggers the halachic inquiry. Set up the tension: it might seem straightforward, but upon closer look...]"),
            ("Part I — Defining the Halachic Category", "[Clarify the exact scope of the mitzvah or prohibition **[S1]**, showing why our specific case enters a gray area requiring investigation.]"),
            ("Part II — The Talmudic Root", "[Present the primary source **[S2]** (Mishnah/Gemara): what was explicitly established in antiquity, and what questions were left open?]"),
            ("Part III — The Perspectives of the Rishonim", "[Examine the rulings of the Rishonim **[S3]**; where a dispute exists, formulate both sides clearly as they directly shape the later codes.]"),
            ("Part IV — The Shulchan Aruch and Later Authorities", "[Unfold the decisions of the Shulchan Aruch and Rama **[S4]**, the elaborations of the classic commentators **[S5]**, and contemporary poskim **[S6]**. Show how the ancient law applies to modern life.]"),
            ("Part V — Practical Ruling and Boundaries", "[Articulate the practical ruling with clarity **[S7]**: what is permitted, what is prohibited, and where the boundaries lie. Note community customs and edge cases.]"),
            ("Summary and Rabbinic Advisory", "[Concluding summary tracing the arc from life scenario to codified halacha. Note that this study aims to understand the sugya, but a qualified rabbi should be consulted for binding personal rulings.]")
        ],
        "school_deepen_title": "Deepening — What Do the Poskim Say?",
        "school_deepen_desc": "[Introduce **[S3]**; explore the reasoning behind the ruling and how it guides our everyday behavior.]",
        "school_summary_theme": "how we practice this mitzvah in daily life"
    },
    "machshava": {
        "title_en_base": "Jewish Thought and Philosophy",
        "subject_en": "Jewish Thought and Philosophy",
        "bm_title": "Jewish Thought and Philosophy — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Philosophical / Theological Topic",
        "bm_stages": [
            ("0. Opening — The Theological Dilemma", "≈5 min",
             "- **Hook:** [Present a profound question about human existence, divine providence, suffering, or faith that resonates deeply.]\n"
             "- **Objective:** Gain conceptual clarity by examining how the great Jewish thinkers grappled with this core issue."),
            ("1. Biblical and Talmudic Roots", "≈10 min",
             "- Examine **[S1]** — [Analyze the biblical verses and rabbinic statements that anchor the dilemma in Jewish tradition.]"),
            ("2. Classical Medieval Formulations", "≈15 min",
             "- **[S2]** and **[S3]** (Rambam / Kuzari / Saadia Gaon / Ralbag) — [Present two major classical schools of thought.]\n"
             "  - *Chavruta Pause:* [What fundamental view of humanity and the cosmos drives each thinker's perspective?]"),
            ("3. Modern and Contemporary Perspectives", "≈10 min",
             "- **[S4]** and **[S5]** (Maharal / Ramchal / Rav Kook / Rav Soloveitchik) — [How modern thinkers articulated or synthesized these concepts for the modern condition.]"),
            ("4. Synthesis & Conceptual Clarity", "≈8 min",
             "- Distill the central insights: resolving apparent contradictions and defining our spiritual reality."),
            ("5. Existential Meaning and Daily Faith", "≈7 min",
             "- **[S6]** — [How this philosophical understanding reshapes our personal relationship with Hashem and moral choices.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The theological dilemma and its textual anchor]\n"
             "  2. [Comparison of the two main philosophical approaches]\n"
             "  3. [The existential takeaway for personal faith and life]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening prose introducing the philosophical question, acknowledging its emotional and intellectual weight for anyone seeking truth.]"),
            ("Part I — The Biblical and Rabbinic Foundation", "[Present the foundational sources **[S1]** in rich prose, showing where this timeless dilemma is first voiced in Tanakh or the Talmud.]"),
            ("Part II — The Medieval Thinkers", "[Explore the contrasting approaches of classical thinkers **[S2]**, **[S3]** (e.g. rationalism vs. experiential faith, free will vs. providence). Articulate each view with philosophical rigour.]"),
            ("Part III — Modern Horizons and Synthesis", "[Unfold the insights of modern thinkers **[S4]**, **[S5]**: how they deepen the discussion, bridge dualities, and address the human psyche.]"),
            ("Part IV — Integrating the Conceptual Architecture", "[Synthesize the core arguments into a harmonious conceptual whole, clarifying what the Torah demands of our intellect and heart.]"),
            ("Part V — Faith as a Living Reality", "[Translate abstract theology into living faith **[S6]**: how this perspective guides us through uncertainty, grief, joy, and daily service of Hashem.]")
        ],
        "school_deepen_title": "Deepening — Exploring Our Questions of Faith",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to examine why Hashem gave us this mitzvah or what it teaches us about our role in the world.]",
        "school_summary_theme": "strengthening our emunah and understanding our values"
    },
    "moadim": {
        "title_en_base": "Festivals and Holidays",
        "subject_en": "Festivals and Holidays",
        "bm_title": "Festivals and Holidays — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Festival / Holiday Theme",
        "bm_stages": [
            ("0. Opening — The Spiritual Essence of the Moed", "≈5 min",
             "- **Setting the Stage:** [Evoke the special atmosphere and unique spiritual energy that enters time during this festival.]\n"
             "- **Objective:** Understand both the halachic structure and the inner message of the holiday."),
            ("1. Biblical Origin & The Mitzvah of the Day", "≈8 min",
             "- Study **[S1]** — [Analyze the Torah verses commanding the festival and defining its central commandment.]"),
            ("2. Rabbinic Dimensions & Talmudic Framework", "≈10 min",
             "- **[S2]** — [How Chazal expanded and structured the observance of the day through the Oral Tradition.]"),
            ("3. Halachic Structure & Sacred Customs", "≈12 min",
             "- **[S3]** and **[S4]** (Rishonim / Shulchan Aruch / Minhag) — [The precise requirements, blessings, and customs that shape the holiday experience.]\n"
             "  - *Chavruta Pause:* [How does this specific halachic detail reflect the deeper purpose of the day?]"),
            ("4. Philosophical & Spiritual Depth", "≈10 min",
             "- **[S5]** (Maharal / Sfat Emet / Rav Kook) — [The inner spiritual renewal offered by the holiday — historical memory transformed into personal elevation.]"),
            ("5. Living the Festival Today", "≈5 min",
             "- **[S6]** — [How the festival equips us with renewed energy, faith, and joy for the entire year.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The biblical root and central mitzvah of the holiday]\n"
             "  2. [Key halachic elements and distinctive customs]\n"
             "  3. [The inner spiritual message for our contemporary life]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening paragraph setting the tone of the upcoming or discussed holiday, capturing its spiritual flavor and historical resonance.]"),
            ("Part I — The Biblical Commandment", "[Present the scriptural text **[S1]** commanding the holiday, examining the key terms and historical context of the exodus or wilderness journey.]"),
            ("Part II — The Oral Law and Halachic Blueprint", "[Examine the Talmudic sources **[S2]** that unpack the laws, demonstrating how rabbinic legislation protects and enriches the sacred day.]"),
            ("Part III — Codification, Law, and Custom", "[Trace the laws in the Rishonim and Shulchan Aruch **[S3]**, **[S4]**, explaining both Ashkenazic and Sephardic customs that enrich the celebration.]"),
            ("Part IV — The Inner Soul of the Moed", "[Delve into the philosophical and mystical depths **[S5]**: how time itself becomes a vehicle for spiritual rebirth, joy, or repentance.]"),
            ("Part V — Carrying the Light Forward", "[Concluding reflections **[S6]** connecting the ritual observances to interpersonal warmth, charity, and lasting spiritual growth.]")
        ],
        "school_deepen_title": "Deepening — The Mitzvot and Customs of the Holiday",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to connect the physical symbols and mitzvot of the holiday to their meaningful message.]",
        "school_summary_theme": "celebrating the holiday with meaning and joy"
    },
    "mussar": {
        "title_en_base": "Mussar and Character Development",
        "subject_en": "Mussar and Character Development",
        "bm_title": "Mussar and Character Development — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Trait (Middah) in Focus",
        "bm_stages": [
            ("0. Opening — The Human Condition & The Trait in Conflict", "≈5 min",
             "- **Hook:** [Describe a realistic internal dilemma or interpersonal conflict where this character trait is severely tested.]\n"
             "- **Objective:** Uncover the roots of the trait and construct practical tools for personal transformation."),
            ("1. Foundational Wisdom of the Sages", "≈8 min",
             "- Study **[S1]** — [Analyze primary sayings in Pirkei Avot, the Talmud, or Tanakh that praise this trait or warn against its corruption.]"),
            ("2. The Psychological Obstacle & Self-Deception", "≈10 min",
             "- **[S2]** — [Identify the rationalizations and emotional traps that prevent a person from rectifying this trait.]"),
            ("3. Classic Mussar Masters", "≈12 min",
             "- **[S3]** and **[S4]** (Mesillat Yesharim / Orchat Tzaddikim / Chovot HaLevavot) — [How the classic masters diagnose the soul's inclinations and outline a path of refinement.]\n"
             "  - *Chavruta Pause:* [What subtle distinction separates the genuine practice of this trait from its counterfeit?]"),
            ("4. Deepening the Diagnosis & Strategy", "≈10 min",
             "- **[S5]** (R. Yisrael Salanter / Alter of Slobodka / Rav Dessler) — [Psychological insights and systematic methods to overcome subconscious resistance.]"),
            ("5. Practical Soul-Work (Kabbalot) & Summary", "≈5 min",
             "- **[S6]** — [Formulate a concrete, manageable daily practice to cultivate this middah in real life.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The definition and scope of the middah according to Chazal]\n"
             "  2. [The primary obstacle or self-deception identified by the Mussar masters]\n"
             "  3. [A concrete practical step to strengthen this trait in daily life]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening prose examining the trait in focus, honestly depicting the struggles and pitfalls that every person faces when striving for growth.]"),
            ("Part I — The Biblical and Rabbinic Ideal", "[Present the words of the Sages **[S1]** in clear, inspiring prose, establishing the lofty standard of character to which the Torah calls us.]"),
            ("Part II — Diagnosing the Inner Struggle", "[Analyze the root causes of failure **[S2]**: pride, fear, habit, or rationalization. Show how honest self-reflection is the indispensable first step.]"),
            ("Part III — Guidance from the Classic Masters", "[Unpack the teachings of the classic ethical works **[S3]**, **[S4]** (Mesillat Yesharim, Orchat Tzaddikim), explaining the sequential stages of personal refinement.]"),
            ("Part IV — Deepening the Method", "[Explore the psychological tools of the Mussar Movement **[S5]** (awakening emotional engagement, micro-habits, and cognitive reframing).]"),
            ("Part V — Living the Transformed Life", "[Translate the insight into concrete action **[S6]**: relationships with family, friends, colleagues, and Hashem. Conclude with an inspiring call to continuous growth.]")
        ],
        "school_deepen_title": "Deepening — Growing in Our Character (Middot)",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to reflect on a time they faced a similar choice and how choosing goodness helps us and others.]",
        "school_summary_theme": "improving our middot and treating others with kindness"
    },
    "parasha": {
        "title_en_base": "Chumash and Weekly Parasha",
        "subject_en": "Chumash and Weekly Parasha",
        "bm_title": "Torah Portion (Parashat HaShavua) — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Parasha / Chumash Theme",
        "bm_stages": [
            ("0. Opening — The Central Narrative Arc & Theme", "≈5 min",
             "- **Setting the Stage:** [Situate the section within the weekly portion and articulate the overarching theme or moral challenge.]\n"
             "- **Objective:** Unpack the text's deeper layers through the eyes of the classic commentators and discover its living relevance."),
            ("1. Textual Anchor & Biblical Verses", "≈10 min",
             "- Read **[S1]** — [Carefully examine the biblical verses, noting unusual wording, repetitive phrasing, or apparent discrepancies.]"),
            ("2. The Classical Textual Difficulty", "≈8 min",
             "- **[S2]** — [Articulate the core question that demands explanation: why did the Torah express it in this manner?]"),
            ("3. The Great Commentators (Rishonim)", "≈12 min",
             "- **[S3]** and **[S4]** (Rashi / Ramban / Ibn Ezra / Sforno) — [Contrast the peshat-oriented, midrashic, or theological answers of the great commentators.]\n"
             "  - *Chavruta Pause:* [How does each commentator's reading change our understanding of the biblical figures' motivations?]"),
            ("4. Thematic & Ethical Synthesis", "≈10 min",
             "- **[S5]** (Kli Yakar / Or HaChaim / Malbim / Netziv) — [Unite the commentaries into a cohesive ethical, psychological, or national insight.]"),
            ("5. Timeless Message for the Shabbat Table", "≈5 min",
             "- **[S6]** — [A clear, memorable message that speaks directly to our lives today.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The textual anomaly highlighted in the verses]\n"
             "  2. [How the differing commentators resolve the difficulty]\n"
             "  3. [The moral or spiritual takeaway for the Shabbat table]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening paragraph introducing the parasha and framing the specific narrative episode or legal section we will explore.]"),
            ("Part I — Reading the Torah Text with Precision", "[Present the biblical verses **[S1]** within the prose, illuminating the nuances of language, context, and dramatic tension.]"),
            ("Part II — The Question That Demands an Answer", "[Formulate the textual or conceptual difficulty **[S2]** that caught the attention of Chazal and the commentators. Make the problem felt.]"),
            ("Part III — The Approaches of the Classic Commentators", "[Explore the distinct solutions of the commentators **[S3]**, **[S4]** (e.g. Rashi's fidelity to text and midrash vs. Ramban's psychological and historical depth).]"),
            ("Part IV — The Deeper Lesson of the Episode", "[Draw out the broader ethical or theological principle **[S5]**, showing how the Torah uses historical events as archetypes for human destiny.]"),
            ("Part V — Living the Parasha", "[Synthesize the insight into a resonant lesson **[S6]** suitable for personal contemplation and sharing at the family Shabbat table. Conclude with an uplifting summary.]")
        ],
        "school_deepen_title": "Deepening — What the Torah Teaches Us",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to discover the lesson the Torah teaches through this story and how it applies to our lives today.]",
        "school_summary_theme": "the eternal lesson of the Torah portion"
    },
    "tefila": {
        "title_en_base": "Tefilah and Blessings",
        "subject_en": "Tefilah and Blessings",
        "bm_title": "Prayer and Blessings — Beit Midrash Scaffold",
        "bm_topic_placeholder": "The Tefilah / Blessing in Depth",
        "bm_stages": [
            ("0. Opening — Standing Before the Creator", "≈5 min",
             "- **Setting the Stage:** [Awaken the mindset of prayer — the vulnerability, gratitude, and awe of communicating with Hashem.]\n"
             "- **Objective:** Understand the origin, halachic parameters, and inner spiritual kavvanah of this prayer/blessing."),
            ("1. Origin & Formulation of the Prayer", "≈8 min",
             "- Study **[S1]** — [Trace the biblical root and the Men of the Great Assembly's exact formulation of the text.]"),
            ("2. Halachic Structure & Essential Requirements", "≈12 min",
             "- **[S2]** and **[S3]** (Mishnah, Gemara, Shulchan Aruch) — [The core halachic guidelines: proper intention (kavvanah), posture, timing, and omissions.]\n"
             "  - *Chavruta Pause:* [What is the minimal requirement for fulfilling the mitzvah, and what constitutes its ideal fulfillment?]"),
            ("3. The Meaning of the Words (Perush HaMilim)", "≈10 min",
             "- **[S4]** (Classic Commentaries: Abudarham / Iyun Tefilah / Rav Kook) — [Dissect the exact phraseology, imagery, and poetic structure.]"),
            ("4. The Inner Dimension & Kabbalistic Horizons", "≈10 min",
             "- **[S5]** (Arizal / Chassidut / Ramchal) — [The spiritual world elevated by this blessing; aligning human desire with the divine will.]"),
            ("5. Cultivating an Elevated Prayer Experience", "≈5 min",
             "- **[S6]** — [Practical guidance for preventing rote recitation and praying with presence of heart.]\n"
             "- **Three Review Questions:**\n"
             "  1. [The historical origin and primary theme of the prayer/blessing]\n"
             "  2. [Key halachic guidelines for proper recitation]\n"
             "  3. [The deeper inner intention (kavvanah) that elevates the words]")
        ],
        "bm_full_sections": [
            ("Introduction", "[Opening prose reflecting on the sublime opportunity of Tefilah, setting the mood of introspection and reverence.]"),
            ("Part I — The Biblical and Rabbinic Origins", "[Examine the text **[S1]** in clean prose, exploring why the Sages instituted this specific formula and where its words originate.]"),
            ("Part II — The Halachic Framework", "[Review the requirements in the Shulchan Aruch **[S2]**, **[S3]**, explaining the mechanics of the blessing, interruptions, and the role of kavvanah.]"),
            ("Part III — Illuminating the Words", "[Unpack the rich meaning behind each phrase **[S4]**, helping the reader connect intellectual comprehension to emotional devotion.]"),
            ("Part IV — The Deeper Spiritual Dimensions", "[Explore the mystical and philosophical insights **[S5]**: how prayer refines the character and attunes the soul to divine goodness.]"),
            ("Part V — Bringing Life to the Siddur", "[Conclude with inspiring guidance **[S6]** on overcoming distraction, infusing vitality into familiar prayers, and bringing prayer into daily action.]")
        ],
        "school_deepen_title": "Deepening — Understanding What We Say in Prayer",
        "school_deepen_desc": "[Introduce **[S3]**; guide students to explore what the words mean and why we say them with kavvanah (heart).]",
        "school_summary_theme": "speaking to Hashem with love, gratitude, and kavvanah"
    }
}

# The 3 She'elot U'Teshuvot templates
SHUT_TEMPLATES = {
    "shut-pesak": {
        "title_en": "Responsa — Source, Opinions, and Ruling",
        "desc_en": (
            "A rabbinic responsa template for questions requiring a clear, reasoned practical ruling. "
            "Progression: opening with legal foundation and scope, surveying early authorities (Rishonim), "
            "codification in Shulchan Aruch and commentators, and final practical determination."
        ),
        "flow_stages": [
            ("0. Opening — Setting the Question", "≈5 min",
             "- Present the real-life question submitted to the rabbinic authority.\n"
             "- Define the scope of the inquiry and immediate concerns."),
            ("1. Foundational Source (Biblical / Talmudic)", "≈10 min",
             "- **[S1]** — Cite and analyze the primary Talmudic sugya or verse establishing the principle."),
            ("2. Perspectives of the Early Authorities (Rishonim)", "≈12 min",
             "- **[S2]** and **[S3]** — Survey the main interpretations and disputes among Rishonim regarding the definition and scope."),
            ("3. Codification & Poskim (Shulchan Aruch & Commentators)", "≈12 min",
             "- **[S4]** — Ruling of the Shulchan Aruch, Rama, and major deciders (Acharonim), noting Ashkenazic vs. Sephardic practice."),
            ("4. Practical Determination (Halacha LeMa'aseh) & Summary", "≈6 min",
             "- **[S5]** — Clear, actionable halachic guidance with qualifications and border conditions.\n"
             "- **Three Review Questions:**\n"
             "  1. [The core legal issue]\n"
             "  2. [Key consensus or dispute among authorities]\n"
             "  3. [The final practical ruling]")
        ],
        "full_sections": [
            ("Introduction — The Inquiry", "[State the practical question submitted, framing the real-world situation and the halachic uncertainty involved.]"),
            ("Part I — The Biblical and Talmudic Foundation", "[Present the primary source **[S1]** (Mishnah/Gemara) that forms the basis of the discussion, explaining what it established.]"),
            ("Part II — The Opinions of the Rishonim", "[Analyze the interpretations of the Rishonim **[S2]**, **[S3]**, clearly contrasting the differing views and their rationales.]"),
            ("Part III — Codification in Shulchan Aruch and Deciders", "[Trace the ruling in Shulchan Aruch **[S4]**, noting subsequent debates among the classic and contemporary Poskim.]"),
            ("Part IV — Final Ruling and Practical Application", "[Formulate the clear halachic conclusion **[S5]**: what is permitted, what is restricted, and under what conditions.]"),
            ("Rabbinic Advisory Notice", "[Standard halachic disclaimer: this study reflects text retrieval and analysis; binding practical rulings require direct consultation with a qualified rabbi.]")
        ],
        "answer_template": """<!--
Template: Responsa (She'elot U'Teshuvot) — Source, Opinions, and Ruling (shut-pesak) | Chavruta.AI
Single output — complete written responsa text. Grounded strictly in retrieved sources; no external API.
Cites sources with inline tags [S#]. Concludes with an advisory disclaimer.
-->

# Responsa — [Topic / The Question]

**Opening: Foundational Source and Definition of the Matter.**
[Paragraph: Present the root of the law and define the scope of inquiry. Where does it originate — Torah verse, Mishnah, or Gemara passage. Cite the primary source [S1].]

**Opinions of the Early Authorities (Rishonim).**
[Paragraph: Present the approaches of the Rishonim. If there is a dispute, delineate the opposing sides and their respective rationales, citing the sources [S2], [S3]. If there is consensus, establish the agreed-upon foundation.]

**Codification by the Deciders (Poskim).**
[Paragraph: How the law was codified in the Shulchan Aruch and its primary commentators (Magen Avraham, Taz, Mishnah Berurah) and contemporary authorities. Note any variations between Sephardic and Ashkenazic customs [S4].]

**Practical Determination (Halacha LeMa'aseh).**
[Paragraph: State the practical ruling clearly — what should be done in practice, including boundary cases, conditions, and reservations. If the retrieved sources do not suffice for a definitive ruling, state this honestly and refer to a qualified Posek [S5].]

---
> **Rabbinic Advisory Disclaimer:** This responsa was generated for study purposes from sources retrieved by Chavruta.AI and does not constitute a binding halachic ruling (pesak halacha). For binding decisions in practice, consult a qualified rabbi.
"""
    },
    "shut-tzdadim": {
        "title_en": "Responsa — Arguments for Prohibition and Permission",
        "desc_en": (
            "A rabbinic responsa template for questions involving competing legal arguments between stringency "
            "and leniency. Progression: defining the case, presenting the side of prohibition, presenting the side "
            "of permission, weighing the authorities, and arriving at the normative conclusion."
        ),
        "flow_stages": [
            ("0. Opening — The Conflict between Leniency and Stringency", "≈5 min",
             "- Present the case where compelling arguments exist for both prohibition and permission.\n"
             "- Define the exact point of tension."),
            ("1. Foundational Context & The Core Issue", "≈8 min",
             "- **[S1]** — Trace the legal category in primary sources and why it gives rise to dual arguments."),
            ("2. The Side of Prohibition (Tzad Ha'Issur)", "≈12 min",
             "- **[S2]** — Detail the strict arguments, proofs from Rishonim, and protective safeguards."),
            ("3. The Side of Permission (Tzad HaHeter)", "≈12 min",
             "- **[S3]** — Detail the lenient arguments, mitigating factors, and proofs supporting permissibility.\n"
             "  - *Chavruta Pause:* [Which argument addresses the underlying reality more compellingly?]"),
            ("4. Weighing the Deciders & Normative Conclusion", "≈8 min",
             "- **[S4]** — How the major Poskim balanced these competing considerations, and the accepted practice.\n"
             "- **Three Review Questions:**\n"
             "  1. [The primary rationale for stringency]\n"
             "  2. [The primary rationale for leniency]\n"
             "  3. [How the Poskim resolved the tension]")
        ],
        "full_sections": [
            ("Introduction — The Dilemma", "[State the inquiry, clearly articulating why this scenario stands at the crossroads between permission and prohibition.]"),
            ("Part I — The Root of the Dilemma", "[Examine the foundational source **[S1]**, establishing why the case is subject to conflicting interpretations.]"),
            ("Part II — The Argument for Stringency", "[Present the comprehensive arguments for prohibition **[S2]**, drawing upon the Rishonim and Poskim who rule strictly.]"),
            ("Part III — The Argument for Leniency", "[Develop the grounds for permissibility **[S3]**, explaining the logic and precedents upon which the lenient authorities rely.]"),
            ("Part IV — The Decision of the Deciders", "[Analyze how the Shulchan Aruch and later authorities **[S4]** weighed the two sides, noting conditions where leniency or stringency prevails.]"),
            ("Rabbinic Advisory Notice", "[Standard halachic disclaimer: this analysis is educational; direct consultation with an authoritative posek is required for practical guidance.]")
        ],
        "answer_template": """<!--
Template: Responsa (She'elot U'Teshuvot) — Arguments for Prohibition and Permission (shut-tzdadim) | Chavruta.AI
Single output — complete written responsa text. Grounded strictly in retrieved sources; no external API.
Weighs competing arguments with inline tags [S#] and concludes with an advisory disclaimer.
-->

# Responsa — [Topic / The Question]

**Opening: Framing the Dilemma.**
[Paragraph: Present the question and show why it generates opposing viewpoints. Identify the primary legal category and the source from which it derives [S1].]

**The Side of Prohibition (Tzad Ha'Issur).**
[Paragraph: Detail the arguments, textual proofs, and sevarot that support a strict ruling. Cite the Rishonim and Poskim who rule that this is prohibited and explain their reasoning [S2].]

**The Side of Permission (Tzad HaHeter).**
[Paragraph: Detail the arguments, textual distinctions, and precedents that support a lenient ruling. Cite the authorities who permit the action and explain the conditions under which they do so [S3].]

**Weighing the Authorities and Practical Determination.**
[Paragraph: Evaluate how the normative halachic codes (Shulchan Aruch, Rama, Mishnah Berurah, contemporary Poskim) rule on this balance. Clarify what is permitted, what is forbidden, and in which circumstances leniency may be relied upon [S4].]

---
> **Rabbinic Advisory Disclaimer:** This responsa was generated for study purposes from sources retrieved by Chavruta.AI and does not constitute a binding halachic ruling (pesak halacha). For binding decisions in practice, consult a qualified rabbi.
"""
    },
    "shut-birur-din": {
        "title_en": "Responsa — Legal Clarification and Definition",
        "desc_en": (
            "A rabbinic responsa template for analytical questions seeking deep conceptual definition and clarification "
            "of a halachic principle or legal status (e.g. geder, safeik, kavvanah). Progression: origin and definition, "
            "Rishonim formulations, Poskim applications, and theoretical conclusion."
        ),
        "flow_stages": [
            ("0. Opening — The Conceptual Inquiry", "≈5 min",
             "- Present the analytical question regarding the precise definition (geder) of a halachic concept.\n"
             "- Define why clarification is essential for determining related cases."),
            ("1. Origin and Fundamental Definition", "≈10 min",
             "- **[S1]** — Examine the primary biblical or rabbinic passage where the principle is first established."),
            ("2. Formulations of the Rishonim", "≈15 min",
             "- **[S2]** and **[S3]** — Contrast how the early commentators define the essential mechanism of the law.\n"
             "  - *Chavruta Pause:* [Is this mechanism an intrinsic property (cheftza) or a personal obligation (gavra)?]"),
            ("3. Practical Application in the Poskim", "≈10 min",
             "- **[S4]** — How the Shulchan Aruch and Acharonim apply this exact definition to borderline situations."),
            ("4. Synthesis & Conceptual Conclusion", "≈5 min",
             "- **[S5]** — Precise formulation of the legal definition and its enduring implications.\n"
             "- **Three Review Questions:**\n"
             "  1. [The core definition of the concept]\n"
             "  2. [The analytical divergence among Rishonim]\n"
             "  3. [Practical implications of the definition]")
        ],
        "full_sections": [
            ("Introduction — The Conceptual Question", "[Frame the inquiry: not merely asking what to do, but probing what the halachic concept truly is at its core.]"),
            ("Part I — The Talmudic Origin of the Concept", "[Examine the primary source **[S1]**, explaining how the principle emerged in the Talmudic discussions.]"),
            ("Part II — The Early Commentators and the Definition", "[Unpack the precise conceptual definitions formulated by the Rishonim **[S2]**, **[S3]**, clarifying their distinct analytical lenses.]"),
            ("Part III — Application in the Halachic Codes", "[Demonstrate how subsequent deciders **[S4]** applied this conceptual boundary to diverse practical questions.]"),
            ("Part IV — Synthesis and Enduring Clarity", "[Conclude with a sharp, unified definition **[S5]** that equips the student to understand related sugyot across Shas.]"),
            ("Rabbinic Advisory Notice", "[Standard halachic disclaimer: this analytical clarification is educational; practical questions require direct rabbinic guidance.]")
        ],
        "answer_template": """<!--
Template: Responsa (She'elot U'Teshuvot) — Legal Clarification and Definition (shut-birur-din) | Chavruta.AI
Single output — complete written responsa text. Grounded strictly in retrieved sources; no external API.
Clarifies the legal definition with inline tags [S#] and concludes with an advisory disclaimer.
-->

# Responsa — [Topic / Clarification of the Law]

**Opening: The Origin and Fundamental Definition.**
[Paragraph: State the concept under investigation and cite its primary Talmudic or biblical source. Formulate the precise question: what is the true mechanism and legal boundary of this rule? Cite [S1].]

**The Formulations of the Early Authorities (Rishonim).**
[Paragraph: Examine the differing definitions offered by the Rishonim. Clarify whether they view the concept as an intrinsic status (cheftza) or an individual obligation (gavra), or other analytical categories, citing [S2], [S3].]

**Application by the Deciders (Poskim).**
[Paragraph: Show how the Shulchan Aruch, its commentators, and the responsa literature apply these precise definitions to resolve novel or ambiguous cases, citing [S4].]

**Halachic and Conceptual Conclusion.**
[Paragraph: Summarize the definitive legal boundary of the concept, crystallizing the insight so that it can be applied to other relevant areas of halacha [S5].]

---
> **Rabbinic Advisory Disclaimer:** This responsa was generated for study purposes from sources retrieved by Chavruta.AI and does not constitute a binding halachic ruling (pesak halacha). For binding decisions in practice, consult a qualified rabbi.
"""
    }
}


def build_school_lesson_flow(folder_name: str, genre: str, band: str, subject_info: dict) -> str:
    binfo = BAND_INFO_EN[band]
    subj = subject_info["subject_en"]
    title_suffix = binfo["title_suffix"]
    grade_hdr = binfo["grade_header"]

    flow = f"""<!--
Template: Lesson Flow — {subj} · {title_suffix} | Chavruta.AI
Accompanies the source sheet and cites sources via [S#] tags. Explicit instruction arc (I Do → We Do → You Do).
-->

# Lesson Flow — [Lesson Topic]  ·  {grade_hdr}

| | |
|---|---|
| **Accompanying Source Sheet** | [source_sheet.md](source_sheet.md) |
| **Estimated Duration** | {binfo['duration']} |
| **Target Audience** | {binfo['age_range']} |
| **Developmental Stage** | {binfo['developmental_stage']} |

> **Learning Objectives:** [1–2 measurable objectives — "The student will explain...", "The student will demonstrate...".]

---

## 0. Opening — Hook & Objective  *(≈5–7 min)*
- **Hook:** {binfo['hook_desc']}
- **Prior Knowledge / Retrieval Practice:** [Short question on the previous lesson — activate prior knowledge before introducing new content.]
- **Today's Goal:** [The lesson objective in one student-friendly sentence.]

## 1. Direct Instruction — Teacher Modeling (I Do)  *(≈7–10 min)*
- **[S1]** — {binfo['i_do_desc']}

## 2. Guided Practice — Collaborative Learning (We Do)  *(≈8–12 min)*
- **[S2]** — {binfo['we_do_desc']}
- *Check for Understanding (CFU):* [Quick class-wide question or thumbs-up/down to verify comprehension before moving on.]

## 3. {subject_info['school_deepen_title']}  *(≈6–10 min)*
- **[S3]** — {subject_info['school_deepen_desc']}

## 4. Independent Practice (You Do)  *(≈7–10 min)*
- **The Task:** {binfo['you_do_desc']}
- **Differentiation:** [Core task for all students + Extension challenge for advanced learners + Scaffolding support for struggling learners.]

## 5. Summary & Formative Assessment  *(≈5 min)*
- **Student-Friendly Summary:** [Core takeaway in one clear sentence, linking back to the opening objective.]
- **Formative Assessment:** {binfo['formative_desc']}
- **Three Review Questions:**
  1. [Recall: Basic factual recall of the source]
  2. [Understanding: Conceptual explanation of the core idea]
  3. [Personal Connection / Application: How this applies in our own life]

---

### Pedagogical Note ({grade_hdr})
{binfo['pedagogy_note']}
"""
    return flow


def build_school_full_lesson(folder_name: str, genre: str, band: str, subject_info: dict) -> str:
    binfo = BAND_INFO_EN[band]
    subj = subject_info["subject_en"]
    title_suffix = binfo["title_suffix"]
    grade_hdr = binfo["grade_header"]

    full = f"""<!--
Template: Full Lesson — {subj} · {title_suffix} | Chavruta.AI
Complete written lesson text calibrated for the grade band's developmental stage, following an explicit instruction arc.
Brackets [ ] = to be filled with rich, age-appropriate prose from the retrieved sources.
-->

# [Lesson Topic] — Lesson for {grade_hdr}

**Target Audience:** {binfo['age_range']} · **Estimated Duration:** {binfo['duration']} · **Subject:** {subj}

---

## Introduction & Hook
{binfo['hook_desc']}
[Open with a concrete story, question, or visual connecting directly to the student's daily world. Conclude with: "Today we will discover that...".]

## Direct Instruction — Introducing the Concept  *(Teacher Models)*
{binfo['i_do_desc']}
[Introduce **[S1]**, read it aloud, and explain step-by-step what the text says and the guiding question it raises.]

## Guided Practice — Interactive Exploration  *(Class Together)*
{binfo['we_do_desc']}
[Introduce **[S2]**; the class analyzes the passage together with the teacher, comparing insights and verifying understanding with a checking question.]

## {subject_info['school_deepen_title']}
{subject_info['school_deepen_desc']}
[Explore **[S3]** and additional perspectives; guide students through comparison, discussion, and discovering deeper meaning.]

## Independent Practice  *(Every Student)*
{binfo['you_do_desc']}
[Short, structured task applying the central idea. Include differentiation: base task for all, extension for advanced students, and support scaffolds for those who need guidance.]

## Summary and Key Message
[Restate the core idea in one resonant sentence in student-friendly language, connecting to {subject_info['school_summary_theme']} that stays with us.]

**Three Review Questions:**
1. [Recall: Key fact or detail from the source]
2. [Understanding: Explanation of the central concept]
3. [Personal Connection / Application: How we live this idea today]

---

### Pedagogical & Transparency Note
The lesson was written by the model from sources retrieved by Chavruta.AI — **without using an external model API**.
Calibrated for {grade_hdr}; teachers should adjust pacing and depth to fit their students.
"""
    return full


def build_bm_lesson_flow(folder_name: str, subject_info: dict) -> str:
    topic_placeholder = subject_info.get("bm_topic_placeholder", "Topic")
    stages_text = []
    for title, duration, body in subject_info["bm_stages"]:
        stages_text.append(f"## {title}  *({duration})*\n{body}")

    stages_str = "\n\n".join(stages_text)

    flow = f"""<!--
Template: Lesson Flow — {subject_info['bm_title']} | Chavruta.AI
Accompanies the source sheet and cites sources via [S#] tags. The model is the instructor; no external API.
-->

# Lesson Flow — [{topic_placeholder}]

| | |
|---|---|
| **Accompanying Source Sheet** | [source_sheet.md](source_sheet.md) |
| **Estimated Duration** | [45 min / 60 min / 90 min] |
| **Target Audience** | Beit Midrash / Advanced Study |

---

{stages_str}

---

### Transparency & Pedagogical Note
Sources were retrieved from the Chavruta.AI RAG (bge-m3 + Qdrant, retrieval only). The lesson flow was composed
by the model strictly from these sources — **without any external model API calls**.
"""
    return flow


def build_bm_full_lesson(folder_name: str, subject_info: dict) -> str:
    topic_placeholder = subject_info.get("bm_topic_placeholder", "Topic")
    sections_text = []
    for title, body in subject_info["bm_full_sections"]:
        sections_text.append(f"## {title}\n{body}")

    sections_str = "\n\n".join(sections_text)

    full = f"""<!--
Template: Full Lesson — {subject_info['bm_title']} | Chavruta.AI
Complete written-out lesson text from start to finish — flowing prose with integrated and explained sources.
The model is the instructor; no external API. Fill in / adapt fields in [ ].
-->

# Full Lesson — [{topic_placeholder}]

*Fully written lesson text. Accompanying source sheet: [source_sheet.md](source_sheet.md) · Lesson flow: [lesson_flow.md](lesson_flow.md)*

---

{sections_str}

---

### Transparency Note
Sources were retrieved from the Chavruta.AI RAG (retrieval only). The lesson was composed by the model
strictly from the retrieved texts — **without using an external model API**. Every quotation must be verified
against its original source.
"""
    return full


def build_shut_lesson_flow(folder_name: str, shut_info: dict) -> str:
    stages_text = []
    for title, duration, body in shut_info["flow_stages"]:
        stages_text.append(f"## {title}  *({duration})*\n{body}")

    stages_str = "\n\n".join(stages_text)

    flow = f"""<!--
Template: Lesson Flow — {shut_info['title_en']} | Chavruta.AI
Accompanies the source sheet and cites sources via [S#] tags. The model is the instructor; no external API.
-->

# Lesson Flow — [Responsa Inquiry / Topic]

| | |
|---|---|
| **Accompanying Source Sheet** | [source_sheet.md](source_sheet.md) |
| **Estimated Duration** | 45 min |
| **Target Audience** | Beit Midrash / Halachic Inquiry |

---

{stages_text}

---

### Transparency & Rabbinic Advisory Note
Sources were retrieved from the Chavruta.AI RAG (retrieval only). The lesson flow was composed by the model
strictly from these sources — **without any external model API calls**. Does not constitute a binding ruling.
"""
    return flow


def build_shut_full_lesson(folder_name: str, shut_info: dict) -> str:
    sections_text = []
    for title, body in shut_info["full_sections"]:
        sections_text.append(f"## {title}\n{body}")

    sections_str = "\n\n".join(sections_text)

    full = f"""<!--
Template: Full Lesson — {shut_info['title_en']} | Chavruta.AI
Complete written-out lesson text structured along responsa methodology — flowing prose with integrated sources.
The model is the instructor; no external API. Fill in / adapt fields in [ ].
-->

# Full Lesson — [Responsa Inquiry / Topic]

*Fully written lesson text. Accompanying source sheet: [source_sheet.md](source_sheet.md) · Lesson flow: [lesson_flow.md](lesson_flow.md)*

---

{sections_str}

---

### Transparency & Advisory Note
Sources were retrieved from the Chavruta.AI RAG (retrieval only). The lesson was composed by the model
strictly from the retrieved texts — **without using an external model API**. Does not replace direct consultation with a qualified rabbi.
"""
    return full


def build_shut_source_sheet(folder_name: str, shut_info: dict) -> str:
    return f"""<!--
Template: Source Sheet — {shut_info['title_en']} | Chavruta.AI
Sources retrieved from the RAG. The model organizes; no external API.
-->

# Source Sheet — [Topic / Responsa Inquiry]

| | |
|---|---|
| **Topic** | [Subject — e.g. "Practical Halacha"] |
| **Primary Source** | [Tractate / Shulchan Aruch Section] |
| **Field** | Responsa (She'elot U'Teshuvot) |
| **Audience** | Beit Midrash / Halachic Inquiry |

> **Objective:** [One sentence summarizing the legal question and the foundational sources examined.]

---

## Part I — Foundational Source
*(Torah verse, Mishnah, or Gemara passage)*

**[S1]** **[Primary Talmudic / Biblical Reference]**
> [Text]
>
> 🔗 [deep_link]

---

## Part II — Early Authorities (Rishonim)
*(Rambam, Rashi, Tosafot, Rosh, Rashba)*

**[S2]** **[Rishon — Core Stance]**
> [Text]
>
> 🔗 [deep_link]

**[S3]** **[Rishon — Competing Stance]**
> [Text]
>
> 🔗 [deep_link]

---

## Part III — Codifiers and Commentators
*(Shulchan Aruch, Rama, Classic Commentaries)*

**[S4]** **[Shulchan Aruch & Commentators]**
> [Text]
>
> 🔗 [deep_link]

---

## Part IV — Practical Ruling and Responsa
*(Contemporary Deciders: Igrot Moshe, Yabia Omer, Minchat Yitzchak, Tzitz Eliezer)*

**[S5]** **[Contemporary Decider]**
> [Text]
>
> 🔗 [deep_link]

---

### Source Map Summary
`Foundational Source → Rishonim → Shulchan Aruch → Contemporary Poskim → Practical Conclusion`
"""


def main():
    templates = sorted([d for d in TEMPLATES_DIR.iterdir() if d.is_dir()])
    print(f"Found {len(templates)} template folders.")

    processed = 0

    for d in templates:
        manifest_path = d / "manifest.yaml"
        if not manifest_path.exists():
            print(f"Skipping {d.name} (no manifest.yaml)")
            continue

        raw_manifest = manifest_path.read_text(encoding="utf-8")
        m = yaml.safe_load(raw_manifest)
        tid = m.get("id") or d.name
        aud = m.get("audience", "yeshiva")
        band = m.get("grade_band", "")
        mode = m.get("mode", "lesson")
        genre = m.get("genre", "")

        # 1. Determine title_en and English file contents
        if mode == "shut" or tid.startswith("shut-"):
            shut_info = SHUT_TEMPLATES.get(tid, SHUT_TEMPLATES["shut-pesak"])
            title_en = shut_info["title_en"]

            flow_en = build_shut_lesson_flow(tid, shut_info)
            full_en = build_shut_full_lesson(tid, shut_info)
            ans_en = shut_info["answer_template"]

            # Write answer_en
            (d / "TEMPLATE_answer_en.md").write_text(ans_en, encoding="utf-8")

            # If TEMPLATE_source_sheet.md doesn't exist, create it
            ss_path = d / "TEMPLATE_source_sheet.md"
            if not ss_path.exists():
                ss_path.write_text(build_shut_source_sheet(tid, shut_info), encoding="utf-8")

            files_en = {
                "source_sheet": "TEMPLATE_source_sheet.md",
                "lesson_flow": "TEMPLATE_lesson_flow_en.md",
                "full_lesson": "TEMPLATE_full_lesson_en.md",
                "answer": "TEMPLATE_answer_en.md"
            }
        elif aud == "school":
            # Extract subject key
            subj_key = m.get("subject") or genre.replace("school-", "")
            subject_info = SUBJECT_DETAILS.get(subj_key, SUBJECT_DETAILS["gemara-iyun"])
            binfo = BAND_INFO_EN.get(band, BAND_INFO_EN["d-f"])
            title_en = f"{subject_info['title_en_base']} — {binfo['title_suffix']}"

            flow_en = build_school_lesson_flow(tid, genre, band, subject_info)
            full_en = build_school_full_lesson(tid, genre, band, subject_info)

            files_en = {
                "source_sheet": "TEMPLATE_source_sheet.md",
                "lesson_flow": "TEMPLATE_lesson_flow_en.md",
                "full_lesson": "TEMPLATE_full_lesson_en.md"
            }
        else:
            # Beit Midrash / Yeshiva lesson template
            # Map folder name to subject key
            subj_key = tid
            if subj_key not in SUBJECT_DETAILS:
                for k in SUBJECT_DETAILS:
                    if k in subj_key:
                        subj_key = k
                        break
            subject_info = SUBJECT_DETAILS.get(subj_key, SUBJECT_DETAILS["general"])
            title_en = subject_info["bm_title"]

            flow_en = build_bm_lesson_flow(tid, subject_info)
            full_en = build_bm_full_lesson(tid, subject_info)

            files_en = {
                "source_sheet": "TEMPLATE_source_sheet.md",
                "lesson_flow": "TEMPLATE_lesson_flow_en.md",
                "full_lesson": "TEMPLATE_full_lesson_en.md"
            }

        # Write English companion template files
        (d / "TEMPLATE_lesson_flow_en.md").write_text(flow_en, encoding="utf-8")
        (d / "TEMPLATE_full_lesson_en.md").write_text(full_en, encoding="utf-8")

        # Update manifest.yaml cleanly
        m["title_en"] = title_en
        m["files_en"] = files_en

        # Preserve comments or cleanly dump YAML
        dumped = yaml.dump(m, allow_unicode=True, sort_keys=False, default_flow_style=False)
        manifest_path.write_text(dumped, encoding="utf-8")
        processed += 1
        print(f"[{processed}/53] Processed {tid:25s} -> {title_en}")

    print(f"\nSuccessfully generated English companions and updated manifests for {processed} templates.")


if __name__ == "__main__":
    main()
