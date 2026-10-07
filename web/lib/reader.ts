import type { Lang } from "./types";

export interface ReaderSegment {
  ref: string;                 // e.g. "Genesis.1.1" or "Berakhot.2a.1"
  label: string;               // e.g. "א", "1", "פסוק א"
  text_he: string;             // Hebrew text (vocalized or plain)
  text_en?: string | null;     // English translation if available
  commentary_count?: number;   // Number of commentaries available on this segment
}

export interface ReaderUnit {
  ref: string;                 // e.g. "Genesis.1" or "Berakhot.2a"
  book: string;                // e.g. "Genesis", "Berakhot"
  book_he?: string;            // e.g. "בראשית", "ברכות"
  category: string;            // e.g. "tanakh", "gemara", "תנ\"ך", "תלמוד בבלי"
  category_path?: string;      // e.g. "Tanakh / Torah / Genesis"
  section_name: string;        // e.g. "פרק א׳" or "דף ב׳ ע״א"
  segments: ReaderSegment[];
  prev_ref: string | null;     // Previous unit ref or null
  next_ref: string | null;     // Next unit ref or null
  version_he?: string | null;
  version_en?: string | null;
  license_he?: string | null;
  license_en?: string | null;
}

export interface CommentaryItem {
  id: string;
  commentator: string;         // e.g. "רש\"י", "רמב\"ן", "אבן עזרא", "ספורנו", "תוספות"
  commentator_en?: string;
  ref: string;                 // e.g. "Rashi on Genesis 1:1:1"
  type: "commentary" | "parallel" | "halacha" | "midrash" | "other";
  text_he: string;
  text_en?: string | null;
  license?: string | null;
  version?: string | null;
}

export interface ReaderLinksResponse {
  ref: string;
  commentaries: CommentaryItem[];
  parallels: CommentaryItem[];
}

export const HE_BOOK_NAMES: Record<string, string> = {
  // Tanakh - Torah
  Genesis: "בראשית",
  Exodus: "שמות",
  Leviticus: "ויקרא",
  Numbers: "במדבר",
  Deuteronomy: "דברים",
  // Tanakh - Nevi'im
  Joshua: "יהושע",
  Judges: "שופטים",
  "I Samuel": "שמואל א׳",
  "II Samuel": "שמואל ב׳",
  I_Samuel: "שמואל א׳",
  II_Samuel: "שמואל ב׳",
  "I Kings": "מלכים א׳",
  "II Kings": "מלכים ב׳",
  I_Kings: "מלכים א׳",
  II_Kings: "מלכים ב׳",
  Isaiah: "ישעיהו",
  Jeremiah: "ירמיהו",
  Ezekiel: "יחזקאל",
  Hosea: "הושע",
  Joel: "יואל",
  Amos: "עמוס",
  Obadiah: "עובדיה",
  Jonah: "יונה",
  Micah: "מיכה",
  Nahum: "נחום",
  Habakkuk: "חבקוק",
  Zephaniah: "צפניה",
  Haggai: "חגי",
  Zechariah: "זכריה",
  Malachi: "מלאכי",
  // Tanakh - Ketuvim
  Psalms: "תהילים",
  Proverbs: "משלי",
  Job: "איוב",
  "Song of Songs": "שיר השירים",
  Song_of_Songs: "שיר השירים",
  Ruth: "רות",
  Lamentations: "איכה",
  Ecclesiastes: "קהלת",
  Esther: "אסתר",
  Daniel: "דניאל",
  Ezra: "עזרא",
  Nehemiah: "נחמיה",
  "I Chronicles": "דברי הימים א׳",
  "II Chronicles": "דברי הימים ב׳",
  I_Chronicles: "דברי הימים א׳",
  II_Chronicles: "דברי הימים ב׳",
  // Bavli Tractates
  Berakhot: "ברכות",
  Shabbat: "שבת",
  Eruvin: "עירובין",
  Pesachim: "פסחים",
  Shekalim: "שקלים",
  Yoma: "יומא",
  Sukkah: "סוכה",
  Beitzah: "ביצה",
  "Rosh Hashanah": "ראש השנה",
  Rosh_Hashanah: "ראש השנה",
  Taanit: "תענית",
  Megillah: "מגילה",
  "Moed Katan": "מועד קטן",
  Moed_Katan: "מועד קטן",
  Chagigah: "חגיגה",
  Yevamot: "יבמות",
  Ketubot: "כתובות",
  Nedarim: "נדרים",
  Nazir: "נזיר",
  Sotah: "סוטה",
  Gittin: "גיטין",
  Kiddushin: "קידושין",
  "Bava Kamma": "בבא קמא",
  Bava_Kamma: "בבא קמא",
  "Bava Metzia": "בבא מציעא",
  Bava_Metzia: "בבא מציעא",
  "Bava Batra": "בבא בתרא",
  Bava_Batra: "בבא בתרא",
  Sanhedrin: "סנהדרין",
  Makkot: "מכות",
  Shevuot: "שבועות",
  "Avodah Zarah": "עבודה זרה",
  Avodah_Zarah: "עבודה זרה",
  Horayot: "הוריות",
  Zevachim: "זבחים",
  Menachot: "מנחות",
  Chullin: "חולין",
  Bekhorot: "בכורות",
  Arakhin: "ערכין",
  Temurah: "תמורה",
  Keritot: "כריתות",
  Meilah: "מעילה",
  Niddah: "נדה",
};

/** Convert integer number to Hebrew Gematria letters (1..999) */
export function toGematria(num: number): string {
  if (num <= 0) return String(num);

  const thousands = Math.floor(num / 1000);
  const remainder = num % 1000;

  const letterVals: [number, string][] = [
    [400, "ת"],
    [300, "ש"],
    [200, "ר"],
    [100, "ק"],
    [90, "צ"],
    [80, "פ"],
    [70, "ע"],
    [60, "ס"],
    [50, "נ"],
    [40, "מ"],
    [30, "ל"],
    [20, "כ"],
    [10, "י"],
    [9, "ט"],
    [8, "ח"],
    [7, "ז"],
    [6, "ו"],
    [5, "ה"],
    [4, "ד"],
    [3, "ג"],
    [2, "ב"],
    [1, "א"],
  ];

  let n = remainder;
  let str = "";

  // Special traditional replacements for 15 and 16
  while (n > 0) {
    if (n === 15) {
      str += "טו";
      n = 0;
      break;
    }
    if (n === 16) {
      str += "טז";
      n = 0;
      break;
    }
    for (const [val, char] of letterVals) {
      if (n >= val) {
        str += char;
        n -= val;
        break;
      }
    }
  }

  // Geresh or Gershayim punctuation
  if (thousands > 0) {
    str = toGematria(thousands) + "׳" + str;
  }
  if (str.length === 1) {
    return str + "׳";
  } else if (str.length > 1 && !str.includes("״")) {
    return str.slice(0, -1) + "״" + str.slice(-1);
  }
  return str;
}

/** Parse Talmud daf like "2a", "14b" into Hebrew string like "דף ב׳ ע״א" */
export function formatTalmudDaf(dafStr: string): string {
  const match = dafStr.match(/^(\d+)([ab])$/i);
  if (!match) return dafStr;
  const num = parseInt(match[1], 10);
  const amud = match[2].toLowerCase() === "a" ? 'ע"א' : 'ע"ב';
  return `דף ${toGematria(num)} ${amud}`;
}

/** Human-readable Hebrew label from canonical ref */
export function formatHebrewRef(ref: string): string {
  if (!ref) return "";
  const parts = ref.split(".");
  const bookKey = parts[0] ? parts[0].replace(/_/g, " ") : "";
  const bookHe = HE_BOOK_NAMES[parts[0]] || HE_BOOK_NAMES[bookKey] || bookKey;

  if (parts.length === 1) {
    return bookHe;
  }

  // Check if second part is a daf (Talmud)
  const isDaf = /^\d+[ab]$/i.test(parts[1]);

  if (isDaf) {
    const dafHe = formatTalmudDaf(parts[1]);
    if (parts.length === 2) {
      return `${bookHe} ${dafHe}`;
    }
    const segNum = parseInt(parts[2], 10);
    const segHe = !isNaN(segNum) ? `אות ${toGematria(segNum)}` : parts[2];
    return `${bookHe} ${dafHe}, ${segHe}`;
  }

  // Tanakh / Halacha chapter & verse
  const chNum = parseInt(parts[1], 10);
  const chHe = !isNaN(chNum) ? `פרק ${toGematria(chNum)}` : parts[1];

  if (parts.length === 2) {
    return `${bookHe} ${chHe}`;
  }

  const vsNum = parseInt(parts[2], 10);
  const vsHe = !isNaN(vsNum) ? `פסוק ${toGematria(vsNum)}` : parts[2];

  return `${bookHe} ${chHe}, ${vsHe}`;
}

/** Strip Hebrew vocalization / cantillation marks */
export function stripHebrewVowels(text: string): string {
  return text.replace(/[\u0591-\u05BD\u05BF-\u05C2\u05C4-\u05C7]/g, "");
}

/** Fetch a study unit (chapter or daf) from the backend */
export async function fetchReaderUnit(ref: string): Promise<ReaderUnit> {
  const cleanRef = ref.trim().replace(/\//g, ".");
  const sp = new URLSearchParams();
  sp.set("ref", cleanRef);

  try {
    const res = await fetch(`/reader/unit?${sp.toString()}`, {
      headers: { Accept: "application/json" },
    });

    if (res.ok) {
      return (await res.json()) as ReaderUnit;
    }
  } catch {}

  // Fallback generation for local testing / offline development
  return generateFallbackUnit(cleanRef);
}

/** Fetch commentary and parallel links for a specific segment */
export async function fetchReaderLinks(segmentRef: string): Promise<ReaderLinksResponse> {
  const cleanRef = segmentRef.trim();
  const sp = new URLSearchParams();
  sp.set("ref", cleanRef);

  try {
    const res = await fetch(`/reader/links?${sp.toString()}`, {
      headers: { Accept: "application/json" },
    });

    if (res.ok) {
      return (await res.json()) as ReaderLinksResponse;
    }
  } catch {}

  // Fallback commentary links for local testing
  return generateFallbackLinks(cleanRef);
}

/** Robust fallback unit generator when offline or in dev testing */
function generateFallbackUnit(ref: string): ReaderUnit {
  const parts = ref.split(".");
  const rawBook = parts[0] || "Genesis";
  const bookKey = rawBook.replace(/_/g, " ");
  const bookHe = HE_BOOK_NAMES[rawBook] || HE_BOOK_NAMES[bookKey] || bookKey;
  const sectionPart = parts[1] || "1";

  const isDaf = /^\d+[ab]$/i.test(sectionPart);
  const sectionName = isDaf
    ? formatTalmudDaf(sectionPart)
    : `פרק ${toGematria(parseInt(sectionPart, 10) || 1)}`;

  // Default sample texts based on well-known opening units
  const isBerakhot = rawBook.toLowerCase().includes("berakhot");
  const isGenesis = rawBook.toLowerCase().includes("genesis");

  let segments: ReaderSegment[] = [];

  if (isGenesis && sectionPart === "1") {
    segments = [
      {
        ref: "Genesis.1.1",
        label: "א",
        text_he: "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃",
        text_en: "In the beginning God created the heaven and the earth.",
        commentary_count: 7,
      },
      {
        ref: "Genesis.1.2",
        label: "ב",
        text_he: "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם וְר֣וּחַ אֱלֹהִ֔ים מְרַחֶ֖פֶת עַל־פְּנֵ֥י הַמָּֽיִם׃",
        text_en: "Now the earth was unformed and void, and darkness was upon the face of the deep; and the spirit of God hovered over the face of the waters.",
        commentary_count: 5,
      },
      {
        ref: "Genesis.1.3",
        label: "ג",
        text_he: "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃",
        text_en: "And God said: 'Let there be light'; and there was light.",
        commentary_count: 4,
      },
      {
        ref: "Genesis.1.4",
        label: "ד",
        text_he: "וַיַּ֧רְא אֱלֹהִ֛ים אֶת־הָא֖וֹר כִּי־ט֑וֹב וַיַּבְדֵּ֣ל אֱלֹהִ֔ים בֵּ֥ין הָא֖וֹר וּבֵ֥ין הַחֹֽשֶךְ׃",
        text_en: "And God saw the light, that it was good; and God divided the light from the darkness.",
        commentary_count: 3,
      },
      {
        ref: "Genesis.1.5",
        label: "ה",
        text_he: "וַיִּקְרָ֨א אֱלֹהִ֤ים ׀ לָאוֹר֙ י֔וֹם וְלַחֹ֖שֶׁךְ קָ֣רָא לָ֑יְלָה וַֽיְהִי־עֶ֥רֶב וַֽיְהִי־בֹ֖קֶר י֥וֹם אֶחָֽד׃",
        text_en: "And God called the light Day, and the darkness He called Night. And there was evening and there was morning, one day.",
        commentary_count: 4,
      },
    ];
  } else if (isBerakhot && sectionPart === "2a") {
    segments = [
      {
        ref: "Berakhot.2a.1",
        label: "א",
        text_he: "מַתְנִי׳ מֵאֵימָתַי קוֹרִין אֶת שְׁמַע בְּעַרְבִית? מִשָּׁעָה שֶׁהַכֹּהֲנִים נִכְנָסִים לֶאֱכוֹל בִּתְרוּמָתָן, עַד סוֹף הָאַשְׁמוּרָה הָרִאשׁוֹנָה, דִּבְרֵי רַבִּי אֱלִיעֶזֶר.",
        text_en: "MISHNAH: From when may one recite the Shema in the evening? From the time when the priests enter to partake of their Terumah until the end of the first watch — these are the words of Rabbi Eliezer.",
        commentary_count: 6,
      },
      {
        ref: "Berakhot.2a.2",
        label: "ב",
        text_he: "וַחֲכָמִים אוֹמְרִים: עַד חֲצוֹת. רַבַּן גַּמְלִיאֵל אוֹמֵר: עַד שֶׁיַּעֲלֶה עַמּוּד הַשָּׁחַר.",
        text_en: "And the Sages say: Until midnight. Rabban Gamliel says: Until the break of dawn.",
        commentary_count: 4,
      },
      {
        ref: "Berakhot.2a.3",
        label: "ג",
        text_he: "מַעֲשֶׂה שֶׁבָּאוּ בָנָיו מִבֵּית הַמִּשְׁתֶּה, אָמְרוּ לוֹ: לֹא קָרִינוּ אֶת שְׁמַע. אָמַר לָהֶם: אִם לֹא עָלָה עַמּוּד הַשַּׁחַר, חַיָּיבִין אַתֶּם לִקְרוֹת.",
        text_en: "An incident occurred where his sons arrived from a wedding banquet; they said to him: We have not yet recited the Shema. He said to them: If dawn has not yet arrived, you are obligated to recite it.",
        commentary_count: 5,
      },
      {
        ref: "Berakhot.2a.4",
        label: "ד",
        text_he: "גְּמָ׳ תַּנָּא הֵיכָא קָאֵי דְּקָתָנֵי ״מֵאֵימָתַי״? וְתוּ, מַאי שְׁנָא דְּתָנֵי בְּעַרְבִית בְּרֵישָׁא, לִיתְנֵי דְּשַׁחֲרִית בְּרֵישָׁא!",
        text_en: "GEMARA: On what basis does the Tanna begin by asking: From when? And furthermore, what is the reason that he teaches the evening Shema first — let him teach the morning Shema first!",
        commentary_count: 8,
      },
    ];
  } else {
    // Generic fallback for any other chapter
    const count = 5;
    for (let i = 1; i <= count; i++) {
      segments.push({
        ref: `${ref}.${i}`,
        label: toGematria(i),
        text_he: `טקסט לימודי עבור ${bookHe} ${sectionName}, קטע ${toGematria(i)}. המקור נטען ברצף לעיון ולימוד מעמיק בספריית חברותא.`,
        text_en: `Study text for ${bookKey} ${sectionPart}, segment ${i}. Loaded continuously for learning in the Chavruta Library.`,
        commentary_count: Math.floor(Math.random() * 5) + 1,
      });
    }
  }

  // Calculate prev and next refs
  let prevRef: string | null = null;
  let nextRef: string | null = null;

  if (isDaf) {
    const dafMatch = sectionPart.match(/^(\d+)([ab])$/i);
    if (dafMatch) {
      const dNum = parseInt(dafMatch[1], 10);
      const amud = dafMatch[2].toLowerCase();
      if (amud === "b") {
        prevRef = `${rawBook}.${dNum}a`;
        nextRef = `${rawBook}.${dNum + 1}a`;
      } else {
        if (dNum > 2) prevRef = `${rawBook}.${dNum - 1}b`;
        nextRef = `${rawBook}.${dNum}b`;
      }
    }
  } else {
    const ch = parseInt(sectionPart, 10) || 1;
    if (ch > 1) prevRef = `${rawBook}.${ch - 1}`;
    nextRef = `${rawBook}.${ch + 1}`;
  }

  return {
    ref,
    book: rawBook,
    book_he: bookHe,
    category: isDaf ? "gemara" : "tanakh",
    category_path: isDaf ? `תלמוד בבלי / ${bookHe}` : `תנ"ך / ${bookHe}`,
    section_name: sectionName,
    segments,
    prev_ref: prevRef,
    next_ref: nextRef,
    version_he: "מהדורת ספריא / תורת אמת",
    version_en: "English Translation",
    license_he: "Public Domain",
    license_en: "CC-BY-SA",
  };
}

/** Robust fallback commentary links generator */
function generateFallbackLinks(segmentRef: string): ReaderLinksResponse {
  const isGenesis11 = segmentRef.includes("Genesis.1.1");
  const isBerakhot2a1 = segmentRef.includes("Berakhot.2a.1");

  if (isGenesis11) {
    return {
      ref: segmentRef,
      commentaries: [
        {
          id: "rashi_gen_1_1",
          commentator: 'רש"י',
          commentator_en: "Rashi",
          ref: "Rashi on Genesis 1:1:1",
          type: "commentary",
          text_he: "בְּרֵאשִׁית — אָמַר רַבִּי יִצְחָק: לֹא הָיָה צָרִיךְ לְהַתְחִיל אֶת הַתּוֹרָה אֶלָּא מֵ״הַחֹדֶשׁ הַזֶּה לָכֶם״, שֶׁהִיא מִצְוָה רִאשׁוֹנָה שֶׁנִּצְטַוּוּ בָהּ יִשְׂרָאֵל, וּמַה טַּעַם פָּתַח בִּבְרֵאשִׁית? מִשּׁוּם ״כֹּחַ מַעֲשָׂיו הִגִּיד לְעַמּוֹ לָתֵת לָהֶם נַחֲלַת גּוֹיִם״.",
          text_en: "IN THE BEGINNING — Rabbi Isaac said: It was not necessary to begin the Torah except from 'This month shall be to you' (Exodus 12:2), which is the first commandment commanded to Israel. What is the reason it opened with Bereishit? Because 'He declared the power of His works to His people, to give them the inheritance of nations' (Psalms 111:6).",
          license: "Public Domain",
          version: "Vocalized Rashi",
        },
        {
          id: "ramban_gen_1_1",
          commentator: 'רמב"ן',
          commentator_en: "Ramban",
          ref: "Ramban on Genesis 1:1:1",
          type: "commentary",
          text_he: "בְּרֵאשִׁית בָּרָא אֱלֹהִים — יֵשׁ לִשְׁאוֹל בָּזֶה, כִּי הָיָה הַצֹּרֶךְ לְהַתְחִיל ״בָּרָא אֱלֹהִים בָּרִאשׁוֹנָה״, כִּי לְעוֹלָם אֵין ״בְּרֵאשִׁית״ בַּמִּקְרָא אֶלָּא סָמוּךְ. וְדַע כִּי מַעֲשֵׂה בְרֵאשִׁית סוֹד עָמוֹק הוּא וְאֵינוֹ מוּבָן מִפְּשׁוּטֵיהֶם שֶׁל כְּתוּבִים.",
          text_en: "IN THE BEGINNING GOD CREATED — One must ask regarding this, for the text should have read 'God created in the first instance', since 'Bereishit' in Scripture is always in the construct state. Know that the Creation narrative is a deep secret not fully comprehensible from the plain text.",
          license: "Public Domain",
          version: "Chavel Edition",
        },
        {
          id: "ibn_ezra_gen_1_1",
          commentator: "אבן עזרא",
          commentator_en: "Ibn Ezra",
          ref: "Ibn Ezra on Genesis 1:1:1",
          type: "commentary",
          text_he: "דַּע כִּי הַבְּרִיאָה הוֹצָאַת יֵשׁ מֵאַיִן לְדַעַת הַקַּדְמוֹנִים, וּלְדַעַת הַמְדַקְדְּקִים הוּא גְזִירַת צוּרָה וְתִקּוּן, כְּמוֹ ״וּבָרָא אֹתְהֶן״.",
          text_en: "Know that creation denotes bringing existence out of nothingness according to the ancients, whereas according to the grammarians it signifies cutting out and fashioning a form.",
          license: "Public Domain",
        },
      ],
      parallels: [
        {
          id: "par_psalms_111",
          commentator: "תהילים קי״א:ו׳",
          ref: "Psalms.111.6",
          type: "parallel",
          text_he: "כֹּ֣חַ מַ֭עֲשָׂיו הִגִּ֣יד לְעַמּ֑וֹ לָתֵ֥ת לָ֝הֶ֗ם נַחֲלַ֥ת גּוֹיִֽם׃",
          text_en: "He hath declared to His people the power of His works, in giving them the heritage of the nations.",
          license: "Public Domain",
        },
        {
          id: "par_midrash_rabbah_1_1",
          commentator: "בראשית רבה א׳:א׳",
          ref: "Genesis Rabbah 1:1",
          type: "midrash",
          text_he: "רַבִּי אוֹשַׁעְיָא פָּתַח: ״וָאֶהְיֶה אֶצְלוֹ אָמוֹן״ — הַתּוֹרָה אוֹמֶרֶת: אֲנִי הָיִיתִי כְּלִי אֻמָּנוּתוֹ שֶׁל הַקָּדוֹשׁ בָּרוּךְ הוּא.",
          text_en: "Rabbi Oshaya opened: 'Then I was by Him as a nursling' (Proverbs 8:30) — The Torah says: I was the master-plan instrument of the Holy One, blessed be He.",
          license: "Public Domain",
        },
      ],
    };
  }

  if (isBerakhot2a1) {
    return {
      ref: segmentRef,
      commentaries: [
        {
          id: "rashi_ber_2a_1",
          commentator: 'רש"י',
          commentator_en: "Rashi",
          ref: "Rashi on Berakhot 2a:1",
          type: "commentary",
          text_he: "מֵאֵימָתַי קוֹרִין — תַּנָּא אַקְּרָא קָאֵי, דִּכְתִיב: ״בְּשָׁכְבְּךָ וּבְקוּמֶךָ״, וְהָכִי קָתָנֵי: זְמַן קְרִיאַת שְׁמַע שֶׁל שְׁכִיבָה מֵאֵימָתַי.",
          text_en: "From when may one recite — the Tanna is basing himself upon Scripture, as it is written: 'When you lie down and when you rise up', and teaches: from when is the time of the recitation of the evening Shema?",
          license: "Public Domain",
          version: "Vilna",
        },
        {
          id: "tosafot_ber_2a_1",
          commentator: "תוספות",
          commentator_en: "Tosafot",
          ref: "Tosafot on Berakhot 2a:1",
          type: "commentary",
          text_he: "מֵאֵימָתַי קוֹרִין אֶת שְׁמַע בְּעַרְבִית — תֵּימַהּ, לָמָּה לֹא פֵּרַשׁ בְּשַׁחֲרִית תְּחִלָּה, כְּדִתְנַן בְּפֶרֶק תְּפִלַּת הַשַּׁחַר? וְיֵשׁ לוֹמַר: מִשּׁוּם דִּכְתִיב ״וַיְהִי עֶרֶב וַיְהִי בֹקֶר״.",
          text_en: "From when may one recite the Shema in the evening — It is surprising: why did he not explain the morning recitation first? And one may answer: because it is written 'And there was evening and there was morning'.",
          license: "Public Domain",
          version: "Vilna",
        },
      ],
      parallels: [
        {
          id: "par_rambam_kriat_shema",
          commentator: 'רמב"ם, הלכות קריאת שמע א׳:ט׳',
          ref: "Mishneh Torah, Reading of Shema 1:9",
          type: "halacha",
          text_he: "קְרִיאַת שְׁמַע שֶׁל עַרְבִית מִצְוָתָהּ מִשֶּׁיֵּצְאוּ הַכּוֹכָבִים עַד חֲצוֹת הַלַּיְלָה, וְאִם עָבַר וְלֹא קָרָא קוֹרֵא עַד שֶׁיַּעֲלֶה עַמּוּד הַשָּׁחַר.",
          text_en: "The commandment of the evening Shema is from when stars appear until midnight; if one passed this time, he may recite until dawn.",
          license: "Public Domain",
        },
      ],
    };
  }

  // Generic fallback
  return {
    ref: segmentRef,
    commentaries: [
      {
        id: `rashi_${segmentRef}`,
        commentator: 'רש"י',
        commentator_en: "Rashi",
        ref: `Rashi on ${segmentRef}`,
        type: "commentary",
        text_he: `ביאור רש"י על מקרא/קטע זה (${formatHebrewRef(segmentRef)}). פירוש קצר ומאיר עיניים על פי פשוטו של מקרא ודברי רבותינו.`,
        text_en: `Rashi's explanation on this passage (${segmentRef}). Lucid commentary following the plain meaning and rabbinic tradition.`,
        license: "Public Domain",
        version: "Standard",
      },
    ],
    parallels: [
      {
        id: `par_${segmentRef}`,
        commentator: "מקבילה תלמודית / מדרשית",
        ref: segmentRef,
        type: "parallel",
        text_he: `מקור מקביל מספרות חז"ל הנוגע לעניין הנדון ב${formatHebrewRef(segmentRef)}.`,
        text_en: `Parallel rabbinic source discussing the theme in ${segmentRef}.`,
        license: "Public Domain",
      },
    ],
  };
}
