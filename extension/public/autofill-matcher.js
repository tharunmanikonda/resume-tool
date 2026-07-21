(() => {
  const config = globalThis.ResumeAutofillConfig;

  function detectPlatform() {
    const host = location.hostname.toLowerCase();
    for (const [platform, suffixes] of Object.entries(config.platformHosts)) {
      if (suffixes.some((suffix) => host === suffix || host.endsWith(`.${suffix}`))) return platform;
    }
    return "generic";
  }

  function rootsFrom(root = document) {
    const roots = [root];
    const visit = (scope) => {
      scope.querySelectorAll?.("*").forEach((element) => {
        if (element.shadowRoot && !roots.includes(element.shadowRoot)) {
          roots.push(element.shadowRoot);
          visit(element.shadowRoot);
        }
      });
    };
    visit(root);
    return roots;
  }

  function queryDeep(selector) {
    const results = [];
    const seen = new Set();
    for (const root of rootsFrom()) {
      root.querySelectorAll(selector).forEach((element) => {
        if (!seen.has(element)) {
          seen.add(element);
          results.push(element);
        }
      });
    }
    return results;
  }

  function text(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function visible(element) {
    if (!element || element.disabled || element.readOnly || element.type === "hidden") return false;
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && !element.closest("[aria-hidden='true']");
  }

  function labelFor(element) {
    const labelledBy = text(element.getAttribute("aria-labelledby"));
    if (labelledBy) {
      const value = labelledBy.split(/\s+/).map((id) => text(document.getElementById(id)?.textContent)).filter(Boolean).join(" ");
      if (value) return value;
    }
    const aria = text(element.getAttribute("aria-label"));
    if (aria) return aria;
    if (element.id) {
      for (const root of rootsFrom(element.getRootNode())) {
        const label = root.querySelector?.(`label[for="${CSS.escape(element.id)}"]`);
        if (text(label?.textContent)) return text(label.textContent);
      }
    }
    const wrapping = element.closest("label");
    if (text(wrapping?.textContent)) return text(wrapping.textContent);
    let parent = element.parentElement;
    for (let depth = 0; parent && depth < 5; depth += 1, parent = parent.parentElement) {
      const label = parent.querySelector?.(":scope > label, :scope > legend, :scope > [data-automation-id*='label'], :scope > [class*='label']");
      if (text(label?.textContent)) return text(label.textContent);
    }
    return text(element.placeholder || element.getAttribute("aria-placeholder") || element.name || element.id || element.getAttribute("data-automation-id") || "Field");
  }

  function optionsFor(element) {
    if (element.tagName === "SELECT") return Array.from(element.options).map((option) => ({ value: option.value, label: text(option.textContent) }));
    if (element.type === "radio") {
      return queryDeep("input[type='radio']").filter((item) => item.name === element.name).map((item) => ({ value: item.value, label: labelFor(item) }));
    }
    const controls = text(element.getAttribute("aria-controls"));
    const owner = controls ? document.getElementById(controls) : null;
    return owner ? Array.from(owner.querySelectorAll("[role='option']")).map((option) => ({ value: text(option.getAttribute("data-value") || option.textContent), label: text(option.textContent) })) : [];
  }

  function typeFor(element) {
    if (element.type === "file") return "file";
    if (element.type === "radio") return "radio";
    if (element.type === "checkbox") return "checkbox";
    if (element.tagName === "SELECT") return "select";
    if (element.getAttribute("role") === "combobox") return "combobox";
    return "text";
  }

  function fields() {
    const elements = queryDeep("input:not([type='hidden']), textarea, select, [role='combobox'], [contenteditable='true']").filter(visible);
    const result = [];
    const radioNames = new Set();
    for (const element of elements) {
      const type = typeFor(element);
      if (type === "radio") {
        const key = element.name || labelFor(element);
        if (radioNames.has(key)) continue;
        radioNames.add(key);
      }
      result.push({
        element,
        type,
        label: labelFor(element),
        name: text(element.name || element.id || element.getAttribute("data-automation-id")),
        placeholder: text(element.placeholder || element.getAttribute("aria-placeholder")),
        options: optionsFor(element),
        required: element.required || element.getAttribute("aria-required") === "true",
        accept: text(element.accept),
        multiline: element.tagName === "TEXTAREA" || element.isContentEditable,
        maxLength: Number(element.maxLength) > 0 ? Number(element.maxLength) : 0,
      });
    }
    return result;
  }

  function confidence(pattern, searchText) {
    const match = searchText.match(pattern);
    if (!match) return 0;
    const ratio = match[0].length / Math.max(searchText.length, 1);
    return ratio > 0.8 ? 0.96 : ratio > 0.5 ? 0.86 : 0.72;
  }

  function matchField(field, profile) {
    const labelText = text(field.label).toLowerCase();
    const nameText = text(field.name).toLowerCase().replace(/[_-]+/g, " ");
    const placeholderText = text(field.placeholder).toLowerCase();
    const searchText = text(`${labelText} ${nameText} ${placeholderText}`).toLowerCase();
    const candidates = [
      { value: labelText, weight: 0.04 },
      { value: nameText, weight: 0.02 },
      { value: placeholderText, weight: 0.01 },
      { value: searchText, weight: 0 },
    ].filter((candidate) => candidate.value);
    const matches = [];
    for (const [dataField, patterns] of Object.entries(config.fieldPatterns)) {
      for (const pattern of patterns) {
        for (const candidate of candidates) {
          if (pattern.test(candidate.value)) {
            matches.push({ dataField, confidence: Math.min(0.99, confidence(pattern, candidate.value) + candidate.weight), value: profile[dataField] ?? "" });
          }
        }
      }
    }
    for (const [question, answer] of Object.entries(profile.customAnswers || {})) {
      if (question && searchText.includes(question.toLowerCase())) matches.push({ dataField: `custom:${question}`, confidence: 0.98, value: answer });
    }
    return matches.sort((left, right) => right.confidence - left.confidence)[0] || null;
  }

  function normalized(value) {
    return text(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function optionValue(field, value) {
    const target = normalized(value);
    if (!target) return "";
    const aliases = config.dropdownMappings[target] || [target];
    const ranked = field.options.map((option) => {
      const optionText = normalized(`${option.label} ${option.value}`);
      let score = 0;
      if (optionText === target) score = 100;
      else if (aliases.some((alias) => optionText === normalized(alias))) score = 95;
      else if (aliases.some((alias) => optionText.includes(normalized(alias)))) score = 80;
      else if (optionText.includes(target) || target.includes(optionText)) score = 60;
      return { ...option, score };
    }).sort((left, right) => right.score - left.score);
    return ranked[0]?.score >= 60 ? ranked[0].value : "";
  }

  function valueFor(field, profile, dataField) {
    const raw = dataField.startsWith("custom:") ? (profile.customAnswers || {})[dataField.slice(7)] : profile[dataField];
    if (raw === undefined || raw === null || raw === "") return "";
    if (field.element.type === "date") {
      const parsed = new Date(raw);
      if (!Number.isNaN(parsed.getTime())) return parsed.toISOString().slice(0, 10);
    }
    if (["select", "radio", "combobox"].includes(field.type)) return optionValue(field, raw) || String(raw);
    return String(raw);
  }

  function filled(field) {
    const element = field.element;
    if (field.type === "checkbox" || field.type === "radio") return Boolean(element.checked);
    if (field.type === "file") return Boolean(element.files?.length);
    if (field.type === "select" || field.type === "combobox") return Boolean(text(element.value || element.getAttribute("data-value")));
    return Boolean(text(element.isContentEditable ? element.textContent : element.value));
  }

  globalThis.ResumeAutofillMatcher = { detectPlatform, queryDeep, fields, matchField, valueFor, filled, labelFor };
})();
