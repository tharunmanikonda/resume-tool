/**
 * Resume Parser - JavaScript Version
 * Ported from manual_resume_parser.py for frontend processing
 * Reduces server load by parsing locally in the browser
 */

const COMPANIES = [
    { company: "Role 1", location: "", dates: "" },
    { company: "Role 2", location: "", dates: "" },
    { company: "Role 3", location: "", dates: "" },
    { company: "Role 4", location: "", dates: "" },
];

const cleanBullet = (line) => {
    line = line.trim();
    line = line.replace(/^[•\-*●]\s*/, "");
    return line.trim();
};

const isSeparator = (line) => {
    const s = line.trim();
    return !s || ["---", "—", "–", "⸻", "|", "||"].includes(s);
};

const removeUnknownSections = (text) => {
    const lines = text.split("\n");
    const result = [];
    for (const line of lines) {
        const stripped = line.trim();
        if (/^[A-Z][A-Z\s]*(\([^)]*\))?:\s*\d+%?\s*$/.test(stripped)) continue;
        if (/^[A-Z][A-Z\s]+$/.test(stripped) && stripped.length > 10 && !["•", "-", "*", "**"].some(c => stripped.includes(c))) {
            if (!["PROFESSIONAL EXPERIENCE", "MODIFIED EXPERIENCE", "UPDATED TITLE", "UPDATED SUMMARY", "UPDATED SKILLS"].includes(stripped)) continue;
        }
        result.push(line);
    }
    return result.join("\n");
};

const markerPattern = (marker) => {
    const normalized = marker.replace(/:$/, "").trim();
    const escaped = normalized.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const prefix = ["PROFESSIONAL EXPERIENCE", "MODIFIED EXPERIENCE"].includes(normalized)
        ? "(?:UPDATED\\s+)?"
        : "";
    return new RegExp("^\\s*" + prefix + escaped + "\\s*:?\\s*$", "im");
};

const between = (text, start, end) => {
    const startMatch = text.match(markerPattern(start));
    if (!startMatch) return "";
    let extracted = text.substring(startMatch.index + startMatch[0].length);
    if (end) {
        const endMatch = extracted.match(markerPattern(end));
        if (endMatch) extracted = extracted.substring(0, endMatch.index);
    }
    extracted = extracted.trim();
    if (end) extracted = removeUnknownSections(extracted);
    return extracted;
};

const parseSkills = (skillsBlock) => {
    const skills = [];
    for (const raw of skillsBlock.split("\n")) {
        const line = cleanBullet(raw);
        if (isSeparator(line)) continue;
        if (line.includes(":")) {
            const [category, items] = line.split(":", 2);
            const cat = category.trim();
            const itm = items.trim();
            if (/^[A-Z\s]*(\([^)]*\))?$/.test(cat) && itm && /^\d/.test(itm)) continue;
            if (cat && itm) skills.push({ category: cat, items: itm });
        }
    }
    return skills;
};

const cleanTitle = (title) => {
    title = title.replace(/\s*\|\s*\w+\s+\d{4}.*/, "");
    title = title.replace(/\s*[\–\-]\s*\w+\s+\d{4}.*/, "");
    return title.trim();
};

const parseExperienceTitlesAndBullets = (text) => {
    const result = {};
    for (let i = 0; i < COMPANIES.length; i++) {
        const company = COMPANIES[i].company;
        const pattern = new RegExp("(?:^|\\n)\\s*" + company.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:\\s|$|[\\|\\-])", "i");
        const match = text.match(pattern);
        if (!match) {
            result[company] = { title: "", bullets: [] };
            continue;
        }
        const idx = match.index;
        const sectionStart = idx + match[0].length - 1;
        let nextIdx = text.length;
        for (let j = i + 1; j < COMPANIES.length; j++) {
            const otherPattern = new RegExp("(?:^|\\n)\\s*" + COMPANIES[j].company.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:\\s|$|[\\|\\-])", "i");
            const otherMatch = text.substring(sectionStart).match(otherPattern);
            if (otherMatch) nextIdx = Math.min(nextIdx, sectionStart + otherMatch.index);
        }
        const section = text.substring(sectionStart, nextIdx).trim();
        const lines = section.split("\n");
        let title = "";
        const bullets = [];
        let firstLine = true;
        for (const line of lines) {
            const cleaned = cleanBullet(line);
            if (!cleaned || isSeparator(cleaned)) continue;
            if (!title && firstLine) {
                firstLine = false;
                if (cleaned.includes("|")) {
                    const parts = cleaned.split("|").map(part => part.trim());
                    const nonEmptyParts = parts.filter(Boolean);
                    let titlePart = "";
                    if (!parts[0]) {
                        if (nonEmptyParts.length >= 2) {
                            titlePart = nonEmptyParts[0];
                        } else {
                            firstLine = true;
                            continue;
                        }
                    } else {
                        titlePart = parts.length >= 3 ? parts[1] : parts[0];
                    }
                    title = cleanTitle(titlePart);
                } else {
                    title = cleanTitle(cleaned);
                }
            } else {
                bullets.push(cleaned);
            }
        }
        result[company] = { title, bullets };
    }
    return result;
};

const parseUpdatedContentToResume = (updatedText, baseResume) => {
    const resume = JSON.parse(JSON.stringify(baseResume));
    if (!updatedText) return resume;
    const text = updatedText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let title = between(text, "UPDATED TITLE", "UPDATED SUMMARY");
    if (!title) title = between(text, "UPDATED TITLE:", "UPDATED SUMMARY");
    let summary = between(text, "UPDATED SUMMARY", "UPDATED SKILLS");
    if (!summary) summary = between(text, "UPDATED SUMMARY:", "UPDATED SKILLS");
    let skillsText = between(text, "UPDATED SKILLS", "PROFESSIONAL EXPERIENCE");
    if (!skillsText) skillsText = between(text, "UPDATED SKILLS:", "PROFESSIONAL EXPERIENCE");
    if (!skillsText) skillsText = between(text, "UPDATED SKILLS", "MODIFIED EXPERIENCE");
    if (!skillsText) skillsText = between(text, "UPDATED SKILLS:", "MODIFIED EXPERIENCE");
    let expText = between(text, "PROFESSIONAL EXPERIENCE", null);
    if (!expText) expText = between(text, "MODIFIED EXPERIENCE", null);
    const skills = skillsText ? parseSkills(skillsText) : [];
    const companyData = expText ? parseExperienceTitlesAndBullets(expText) : {};
    if (title) resume.title = title.split(/\s+/).join(" ");
    if (summary) resume.summary = summary.split(/\s+/).join(" ");
    if (skills) resume.technical_skills = skills;
    if (companyData) {
        for (const exp of resume.experience || []) {
            const data = companyData[exp.company];
            if (data) {
                if (data.title) exp.title = data.title;
                if (data.bullets.length) exp.bullets = data.bullets;
            }
        }
    }
    return resume;
};

const validateUpdatedContent = (updatedText) => {
    const errors = [], warnings = [];
    if (!updatedText || !updatedText.trim()) {
        errors.push("No content provided");
        return { errors, warnings };
    }
    const text = updatedText.toLowerCase();
    const has = { title: text.includes("updated title"), summary: text.includes("updated summary"), skills: text.includes("updated skills"), exp: text.includes("professional experience") || text.includes("modified experience") };
    if (!Object.values(has).every(Boolean)) {
        const missing = [];
        if (!has.title) missing.push("UPDATED TITLE");
        if (!has.summary) missing.push("UPDATED SUMMARY");
        if (!has.skills) missing.push("UPDATED SKILLS");
        if (!has.exp) missing.push("PROFESSIONAL EXPERIENCE");
        errors.push(`Missing sections: ${missing.join(", ")}`);
    }
    return { errors, warnings };
};
