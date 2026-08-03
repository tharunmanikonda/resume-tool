(() => {
  let version = "development";
  let runtimeId = "";
  try {
    version = chrome.runtime.getManifest?.().version || version;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }
  const previous = globalThis.__resumeAutofillLifecycle;
  if (
    previous?.version === version
    && previous?.runtimeId === runtimeId
    && previous?.isActive?.()
  ) return;
  previous?.shutdown?.();

  const matcher = globalThis.ResumeAutofillMatcher;
  const config = globalThis.ResumeAutofillConfig;
  if (!matcher || !config) return;

  let stopped = false;
  let observer = null;
  let scanTimer = null;
  let lastAutoFillSignature = "";
  let lastStatusSignature = "";

  function runtimeAvailable() {
    try {
      return !stopped && Boolean(chrome?.runtime?.id);
    } catch (_) {
      return false;
    }
  }

  function send(message) {
    if (!runtimeAvailable()) return Promise.resolve(null);
    try {
      return chrome.runtime.sendMessage(message).catch(() => null);
    } catch (_) {
      stopped = true;
      return Promise.resolve(null);
    }
  }

  function applicationPage() {
    const value = `${location.href} ${document.title} ${(document.body?.innerText || "").slice(0, 5000)}`.toLowerCase();
    if (["apply", "application", "candidate", "resume", "cover letter", "work authorization", "sponsorship", "submit application"].some((signal) => value.includes(signal))) {
      return true;
    }
    const fields = matcher.fields();
    const fieldText = fields.map((field) => `${field.label} ${field.name}`).join(" ").toLowerCase();
    const hasIdentity = /\b(first name|last name|full name|e-?mail|phone)\b/.test(fieldText);
    const hasApplicationField = fields.some((field) => field.type === "file" && /resume|cv|pdf|document/i.test(`${field.label} ${field.name} ${field.accept}`))
      || /\b(linkedin|work authorization|sponsorship|current company|years of experience|cover letter)\b/.test(fieldText);
    return fields.length >= 3 && hasIdentity && hasApplicationField;
  }

  function fieldSignature(fields) {
    return [location.href, ...fields.map((field) => `${field.type}:${field.name}:${field.label}`)].join("|");
  }

  async function profile(identityId = "") {
    const result = await send({ type: "AUTOFILL_GET_PROFILE", identityId });
    return result?.success ? result.profile : null;
  }

  function stableQuestionId(value) {
    let hash = 2166136261;
    for (const character of String(value || "")) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return `question-${(hash >>> 0).toString(16)}`;
  }

  function applicationQuestion(field, match) {
    if (field.type !== "text" || match) return { detected: false, eligible: false, blockedReason: "" };
    const label = String(field.label || "").replace(/\s+/g, " ").trim();
    const normalized = label.toLowerCase();
    const ordinaryField = /^(name|full name|first name|last name|email|phone|telephone|address|city|state|province|country|zip|postal code|linkedin|github|portfolio|website|current company|current title)$/i.test(label);
    const writtenPrompt = field.multiline || label.length >= 18 && (
      label.includes("?") || /\b(why|how|what|describe|explain|tell us|share|experience|interested|interest|challenge|example|additional information|cover letter)\b/.test(normalized)
    );
    if (ordinaryField || !writtenPrompt) return { detected: false, eligible: false, blockedReason: "" };
    const sensitive = /\b(work authorization|authorized to work|sponsor|sponsorship|visa|salary|compensation|pay range|desired pay|start date|available to start|availability|security clearance|criminal|felony|conviction|disability|veteran|race|ethnicity|gender|sexual orientation|demographic|eeo|equal employment)\b/i.test(label);
    return {
      detected: true,
      eligible: !sensitive,
      blockedReason: sensitive ? "Answer this manually because it requires personal or legal confirmation." : "",
    };
  }

  function fieldSummary(field, userProfile) {
    const match = matcher.matchField(field, userProfile || {});
    const value = match ? matcher.valueFor(field, userProfile || {}, match.dataField) : "";
    const question = applicationQuestion(field, match);
    return {
      label: field.label,
      name: field.name,
      type: field.type,
      required: field.required,
      filled: matcher.filled(field),
      matched: Boolean(match && value),
      dataField: match?.dataField || "",
      confidence: match?.confidence || 0,
      reviewRequired: Boolean(match && config.sensitiveFields.has(match.dataField)),
      fileKind: field.type === "file" ? (/resume|cv/i.test(field.label) ? "resume" : "document") : "",
      multiline: Boolean(field.multiline),
      maxLength: Number(field.maxLength || 0),
      applicationQuestion: question.detected,
      aiEligible: question.eligible,
      aiBlockedReason: question.blockedReason,
      questionId: stableQuestionId(`${location.href}|${field.name}|${field.label}`),
      frameUrl: location.href,
    };
  }

  async function scan({ identityId = "", announce = true } = {}) {
    const userProfile = await profile(identityId);
    const allFields = applicationPage() ? matcher.fields() : [];
    const fields = allFields.map((field) => fieldSummary(field, userProfile));
    const status = {
      success: true,
      platform: matcher.detectPlatform(),
      url: location.href,
      frameUrl: location.href,
      topFrame: window === window.top,
      applicationPage: applicationPage(),
      continueEnabled: userProfile?.autoFillEnabled !== false,
      totalFields: fields.filter((field) => field.type !== "file").length,
      filledFields: fields.filter((field) => field.type !== "file" && field.filled).length,
      matchedFields: fields.filter((field) => field.type !== "file" && field.matched).length,
      fileFields: fields.filter((field) => field.type === "file").length,
      fields,
    };
    const signature = JSON.stringify([status.url, status.totalFields, status.filledFields, status.matchedFields, status.fileFields]);
    if (announce && signature !== lastStatusSignature) {
      lastStatusSignature = signature;
      send({ type: "AUTOFILL_STATUS_CHANGED", status });
    }
    return { status, allFields, userProfile };
  }

  function dispatchEvents(element, previousValue = "") {
    if (element._valueTracker?.setValue) element._valueTracker.setValue(previousValue);
    try {
      element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: String(element.value || "") }));
    } catch (_) {
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
  }

  function setNativeValue(element, value) {
    const previous = element.value;
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    element.focus();
    if (descriptor?.set) descriptor.set.call(element, value);
    else element.value = value;
    dispatchEvents(element, previous);
  }

  function normalized(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  async function fillCombobox(element, value) {
    element.focus();
    element.click();
    await new Promise((resolve) => setTimeout(resolve, 120));
    const target = normalized(value);
    const options = matcher.queryDeep("[role='option'], [role='listbox'] li, [data-value]").filter((option) => {
      const optionText = normalized(`${option.getAttribute("data-value") || ""} ${option.textContent || ""}`);
      return optionText === target || optionText.includes(target) || target.includes(optionText);
    });
    const option = options.find((item) => item.getAttribute("aria-disabled") !== "true");
    if (option) {
      option.click();
      dispatchEvents(element);
      return true;
    }
    if (element instanceof HTMLInputElement) {
      setNativeValue(element, value);
      return true;
    }
    return false;
  }

  async function fillField(field, value) {
    const element = field.element;
    if (!element || !value || matcher.filled(field)) return false;

    if (field.type === "text") {
      if (element.isContentEditable) {
        element.focus();
        element.textContent = value;
        dispatchEvents(element);
      } else {
        setNativeValue(element, value);
      }
    } else if (field.type === "select") {
      const target = normalized(value);
      const option = Array.from(element.options).find((item) => {
        const candidate = normalized(`${item.value} ${item.textContent}`);
        return candidate === target || candidate.includes(target) || target.includes(candidate);
      });
      if (!option) return false;
      const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
      descriptor?.set ? descriptor.set.call(element, option.value) : (element.value = option.value);
      dispatchEvents(element);
    } else if (field.type === "combobox") {
      return fillCombobox(element, value);
    } else if (field.type === "radio") {
      const target = normalized(value);
      const option = matcher.queryDeep("input[type='radio']").find((item) => item.name === element.name && (() => {
        const candidate = normalized(`${item.value} ${matcher.labelFor(item)}`);
        return candidate === target || candidate.includes(target) || target.includes(candidate);
      })());
      if (!option) return false;
      if (!option.checked) option.click();
      dispatchEvents(option);
    } else if (field.type === "checkbox") {
      const desired = ["true", "yes", "1", "checked"].includes(normalized(value));
      if (element.checked !== desired) element.click();
      dispatchEvents(element);
    } else {
      return false;
    }
    element.dataset.resumeAutofill = "filled";
    element.style.outline = "2px solid #0ca678";
    element.style.outlineOffset = "1px";
    return true;
  }

  async function fill({
    identityId = "",
    automatic = false,
    approved = false,
    safeOnly = true,
  } = {}) {
    if (!approved) {
      return {
        success: false,
        error: "Confirm this application before filling it.",
        filledCount: 0,
        skippedCount: 0,
      };
    }
    const { allFields, userProfile } = await scan({ identityId, announce: false });
    if (!userProfile) return { success: false, error: "The local resume profile is unavailable.", filledCount: 0, skippedCount: 0 };
    let filledCount = 0;
    let skippedCount = 0;
    const errors = [];
    for (const field of allFields) {
      if (field.type === "file" || matcher.filled(field)) continue;
      const match = matcher.matchField(field, userProfile);
      const value = match ? matcher.valueFor(field, userProfile, match.dataField) : "";
      if (!match || match.confidence < 0.6 || !value) {
        skippedCount += 1;
        continue;
      }
      if (safeOnly && config.sensitiveFields.has(match.dataField)) {
        skippedCount += 1;
        continue;
      }
      try {
        if (await fillField(field, value)) filledCount += 1;
        else skippedCount += 1;
      } catch (error) {
        errors.push(`${field.label}: ${error.message}`);
      }
      await new Promise((resolve) => setTimeout(resolve, automatic ? 45 : 70));
    }
    const { status } = await scan({ identityId, announce: true });
    return { success: filledCount > 0, filledCount, skippedCount, errors, status };
  }

  function decodeBase64(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  }

  async function attachResume(message) {
    const candidates = matcher.fields().filter((field) => field.type === "file" && /resume|cv|curriculum/i.test(`${field.label} ${field.name} ${field.accept}`));
    const field = candidates[0];
    if (!field) return { success: false, error: "No resume file field was found in this frame." };
    const file = new File([decodeBase64(message.base64)], message.filename || "resume.pdf", { type: message.mimeType || "application/pdf" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    field.element.files = transfer.files;
    dispatchEvents(field.element);
    field.element.dataset.resumeAutofill = "resume";
    field.element.style.outline = "2px solid #0ca678";
    return { success: true, filename: file.name };
  }

  async function maybeAutoFill() {
    const { status, allFields, userProfile } = await scan({ announce: true });
    if (!status.applicationPage || !allFields.length || userProfile?.autoFillEnabled === false) return;
    const approvalResponse = await send({ type: "AUTOFILL_GET_APPROVAL" });
    const approval = approvalResponse?.success ? approvalResponse.approval : null;
    if (approval?.mode !== "application") return;
    const signature = fieldSignature(allFields);
    if (signature === lastAutoFillSignature) return;
    lastAutoFillSignature = signature;
    await fill({
      identityId: approval.identityId || userProfile.identityId,
      automatic: true,
      approved: true,
      safeOnly: true,
    });
  }

  function scheduleScan(delay = 450) {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(() => maybeAutoFill().catch(() => {}), delay);
  }

  function handleMessage(message, _sender, sendResponse) {
    let operation = null;
    if (message?.type === "AUTOFILL_SCAN_FRAME") operation = scan({ identityId: message.identityId, announce: false }).then(({ status }) => status);
    if (message?.type === "AUTOFILL_FILL_FRAME") {
      operation = fill({
        identityId: message.identityId,
        automatic: Boolean(message.automatic),
        approved: Boolean(message.approved),
        safeOnly: message.safeOnly !== false,
      });
    }
    if (message?.type === "AUTOFILL_APPROVAL_CHANGED") {
      lastAutoFillSignature = "";
      scheduleScan(100);
      sendResponse({ success: true });
      return false;
    }
    if (message?.type === "AUTOFILL_ATTACH_FRAME") operation = attachResume(message);
    if (!operation) return false;
    operation.then(sendResponse).catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  function shutdown() {
    stopped = true;
    clearTimeout(scanTimer);
    observer?.disconnect();
    try { chrome.runtime.onMessage.removeListener(handleMessage); } catch (_) {}
  }

  globalThis.__resumeAutofillLifecycle = { version, runtimeId, isActive: runtimeAvailable, shutdown };
  chrome.runtime.onMessage.addListener(handleMessage);
  observer = new MutationObserver(() => scheduleScan(500));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("popstate", () => { lastAutoFillSignature = ""; scheduleScan(250); });
  scheduleScan(300);
})();
