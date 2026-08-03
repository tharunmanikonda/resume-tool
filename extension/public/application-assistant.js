(() => {
  let version = "development";
  let runtimeId = "";
  try {
    version = chrome.runtime.getManifest?.().version || version;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }

  const previous = globalThis.__resumeApplicationAssistantLifecycle;
  if (
    previous?.version === version
    && previous?.runtimeId === runtimeId
    && previous?.isActive?.()
  ) return;
  previous?.shutdown?.();

  const hostId = "resume-generator-application-assistant";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  let stopped = false;
  let observer = null;
  let detectionTimer = null;
  let lastUrl = location.href;
  let lastCandidateFingerprint = "";
  let dismissedFingerprint = "";
  let currentStatus = null;
  let expanded = false;
  let busy = false;
  let resultMessage = "";
  let questionBusy = "";
  let questionAnswers = {};
  let questionErrors = {};
  let copiedQuestionId = "";
  let copyTimer = null;
  let attachBusy = false;
  let attachmentMessage = "";
  let attachmentError = false;
  let recentResumes = [];
  let selectedResumeId = "";
  let resumesLoading = false;
  let resumesLoaded = false;

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

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function fieldLabel(element) {
    const aria = clean(element.getAttribute("aria-label"));
    if (aria) return aria;
    const name = clean(element.getAttribute("name") || element.id || element.getAttribute("data-automation-id"));
    if (element.id) {
      const linked = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
      if (clean(linked?.textContent)) return clean(linked.textContent);
    }
    const wrapped = element.closest("label");
    return clean(wrapped?.textContent || element.placeholder || name);
  }

  function lightweightCandidate() {
    const urlText = `${location.href} ${document.title}`.toLowerCase();
    const urlSignal = /\b(apply|application|candidate|careers?|jobs?)\b/.test(urlText);
    const controls = [...document.querySelectorAll("input:not([type='hidden']), textarea, select")]
      .filter((element) => !element.disabled)
      .slice(0, 120);
    const descriptors = controls.map((element) => clean(
      `${element.tagName}:${element.type || ""}:${element.name || ""}:${element.id || ""}:${fieldLabel(element)}:${element.accept || ""}`,
    ));
    const fieldText = descriptors.join(" ").toLowerCase();
    const hasIdentity = /\b(first name|last name|full name|e-?mail|phone|telephone)\b/.test(fieldText);
    const hasApplication = /\b(resume|curriculum|cv|cover letter|linkedin|work authorization|sponsorship|current company|experience)\b/.test(fieldText);
    const hasResumeFile = controls.some((element) => element.type === "file" && /resume|cv|pdf|document/i.test(
      `${fieldLabel(element)} ${element.name || ""} ${element.accept || ""}`,
    ));
    const shouldProbe = urlSignal || controls.length >= 3 && hasIdentity && (hasApplication || hasResumeFile);
    const fingerprint = `${location.origin}${location.pathname}|${descriptors.join("|")}`;
    let hash = 2166136261;
    for (const character of fingerprint) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return {
      shouldProbe,
      fingerprint: `application-${(hash >>> 0).toString(16)}`,
      controlCount: controls.length,
    };
  }

  function counts(status) {
    const fields = status?.fields || [];
    const pending = fields.filter((field) => field.type !== "file" && !field.filled);
    return {
      ready: pending.filter((field) => field.matched && !field.reviewRequired && Number(field.confidence || 0) >= 0.6).length,
      review: pending.filter((field) => field.reviewRequired || field.matched && Number(field.confidence || 0) < 0.6).length,
      unmatched: pending.filter((field) => !field.matched && !field.applicationQuestion).length,
      questions: pending.filter((field) => field.applicationQuestion).length,
      files: fields.filter((field) => field.type === "file" && !field.filled).length,
      filled: fields.filter((field) => field.type !== "file" && field.filled).length,
      total: fields.filter((field) => field.type !== "file").length,
    };
  }

  function attentionFields(status) {
    return (status?.fields || [])
      .filter((field) => (
        field.type !== "file"
        && !field.filled
        && !field.applicationQuestion
        && (
          field.reviewRequired
          || !field.matched
          || Number(field.confidence || 0) < 0.6
        )
      ))
      .map((field) => ({
        label: clean(field.label || field.name || "Unrecognized field"),
        reason: field.applicationQuestion
          ? "written answer"
          : field.reviewRequired
            ? "review"
            : "unmatched",
      }));
  }

  function applicationQuestions(status) {
    const seen = new Set();
    return (status?.fields || []).filter((field) => {
      if (!field.applicationQuestion || field.filled || seen.has(field.questionId)) return false;
      seen.add(field.questionId);
      return true;
    });
  }

  function removeWidget() {
    document.getElementById(hostId)?.remove();
  }

  function button(label, className, onClick) {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.className = className;
    element.addEventListener("click", onClick);
    return element;
  }

  async function confirmFill(mode) {
    if (busy) return;
    busy = true;
    resultMessage = "";
    render();
    const response = await send({ type: "AUTOFILL_CONFIRM_FILL", mode });
    busy = false;
    if (!response?.success && !response?.filledCount) {
      resultMessage = response?.error || "No safe empty fields could be filled.";
    } else {
      const filledCount = Number(response.filledCount || 0);
      resultMessage = filledCount
        ? `Filled ${filledCount} safe field${filledCount === 1 ? "" : "s"}. Review before submitting.`
        : "No additional safe fields were ready.";
      currentStatus = response.status || currentStatus;
    }
    render();
  }

  async function askQuestion(question) {
    if (!question?.questionId || !question.aiEligible || questionBusy) return;
    questionBusy = question.questionId;
    delete questionErrors[question.questionId];
    render();
    const response = await send({
      type: "AUTOFILL_ANSWER_QUESTION",
      questionId: question.questionId,
      question: question.label,
      maxLength: question.maxLength || 0,
      draftId: selectedResumeId,
    });
    questionBusy = "";
    if (!response?.success) {
      questionErrors = {
        ...questionErrors,
        [question.questionId]: response?.error || "The answer could not be generated.",
      };
    } else {
      questionAnswers = {
        ...questionAnswers,
        [question.questionId]: {
          answer: response.answer,
          draft: response.draft || null,
        },
      };
    }
    render();
  }

  async function copyAnswer(questionId) {
    const answer = String(questionAnswers[questionId]?.answer || "");
    if (!answer) return;
    let copied = false;
    try {
      await navigator.clipboard.writeText(answer);
      copied = true;
    } catch (_) {
      const textarea = document.createElement("textarea");
      textarea.value = answer;
      textarea.setAttribute("readonly", "");
      Object.assign(textarea.style, {
        position: "fixed",
        left: "-9999px",
        top: "0",
        opacity: "0",
      });
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      copied = document.execCommand("copy");
      textarea.remove();
    }
    if (!copied) {
      questionErrors = { ...questionErrors, [questionId]: "Clipboard access was blocked." };
      render();
      return;
    }
    copiedQuestionId = questionId;
    render();
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => {
      copiedQuestionId = "";
      render();
    }, 1400);
  }

  async function attachResume() {
    if (attachBusy || !selectedResumeId) return;
    attachBusy = true;
    attachmentMessage = "";
    attachmentError = false;
    render();
    const response = await send({
      type: "AUTOFILL_ATTACH_RESUME",
      draftId: selectedResumeId,
    });
    attachBusy = false;
    if (!response?.success) {
      attachmentError = true;
      attachmentMessage = response?.error || "The resume could not be attached.";
    } else {
      attachmentMessage = `${response.filename} was attached. Confirm the file name on the application.`;
      currentStatus = response.status || currentStatus;
    }
    render();
  }

  async function loadRecentResumes(force = false) {
    if (resumesLoading || resumesLoaded && !force) return;
    resumesLoading = true;
    attachmentError = false;
    if (force) attachmentMessage = "";
    render();
    const response = await send({ type: "AUTOFILL_GET_RECENT_RESUMES" });
    resumesLoading = false;
    if (!response?.success) {
      recentResumes = [];
      resumesLoaded = false;
      attachmentError = true;
      attachmentMessage = response?.error || "Recent resumes could not be loaded.";
    } else {
      recentResumes = Array.isArray(response.drafts) ? response.drafts : [];
      resumesLoaded = true;
      if (!recentResumes.some((draft) => draft.id === selectedResumeId)) {
        selectedResumeId = recentResumes[0]?.id || "";
      }
    }
    render();
  }

  function generatedAgo(value) {
    const generatedAt = new Date(value || "").getTime();
    if (!Number.isFinite(generatedAt)) return "";
    const minutes = Math.max(0, Math.round((Date.now() - generatedAt) / 60000));
    if (minutes < 60) return `${minutes || 1}m ago`;
    const hours = Math.round(minutes / 60);
    return `${hours}h ago`;
  }

  function render() {
    removeWidget();
    if (
      !currentStatus?.applicationPage
      || !(Number(currentStatus.totalFields || 0) + Number(currentStatus.fileFields || 0))
    ) return;
    const candidate = lightweightCandidate();
    if (dismissedFingerprint && dismissedFingerprint === candidate.fingerprint) return;

    const summary = counts(currentStatus);
    const host = document.createElement("div");
    host.id = hostId;
    host.dataset.resumeGeneratorInstance = instanceId;
    Object.assign(host.style, {
      all: "initial",
      position: "fixed",
      right: "clamp(10px, 6vw, 76px)",
      bottom: "16px",
      zIndex: "2147483646",
    });
    const shadow = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      * { box-sizing: border-box; }
      .assistant { width: 320px; border: 1px solid #b7c4bf; border-radius: 8px; background: #fff; color: #17201d; box-shadow: 0 10px 28px rgba(0,0,0,.2); font: 13px/1.35 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; overflow: hidden; }
      button { font: inherit; letter-spacing: 0; cursor: pointer; }
      .chip { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 10px; border: 0; background: #087f5b; color: #fff; padding: 11px 12px; text-align: left; }
      .chip strong { display: block; font-size: 13px; }
      .chip span { font-size: 11px; opacity: .9; }
      .panel { display: grid; gap: 10px; max-height: min(640px, calc(100vh - 32px)); overflow-y: auto; padding: 12px; }
      .heading { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
      .heading strong { font-size: 14px; }
      .dismiss { border: 0; background: transparent; color: #58645f; padding: 0 2px; font-size: 16px; }
      .counts { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #d9dfdc; border-radius: 6px; }
      .count { min-width: 0; padding: 8px; border-right: 1px solid #d9dfdc; }
      .count:last-child { border-right: 0; }
      .count b { display: block; font-size: 15px; color: #075f46; }
      .count span { display: block; color: #64706b; font-size: 10px; }
      .details { display: grid; gap: 5px; margin: 0; padding: 0; list-style: none; color: #48534f; font-size: 11px; }
      .details li { display: flex; justify-content: space-between; gap: 12px; }
      .attention { display: grid; gap: 5px; border-top: 1px solid #e1e5e3; padding-top: 8px; }
      .attention > strong { font-size: 11px; }
      .attention-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; color: #48534f; font-size: 10px; }
      .attention-row span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .attention-row span:last-child { color: #7a4545; }
      .questions { display: grid; gap: 7px; border-top: 1px solid #e1e5e3; padding-top: 8px; }
      .questions > strong { font-size: 11px; }
      .question { display: grid; gap: 5px; border: 1px solid #d9dfdc; border-radius: 6px; padding: 8px; }
      .question-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: start; }
      .question-head span { min-width: 0; font-size: 10px; font-weight: 600; }
      .question button { min-height: 28px; border: 1px solid #087f5b; border-radius: 5px; background: #fff; color: #075f46; padding: 4px 7px; font-size: 10px; }
      .question button:disabled { cursor: default; opacity: .55; }
      .question-meta, .question-error { color: #6a746f; font-size: 9px; }
      .question-error { color: #9c2f2f; }
      .answer { display: grid; gap: 5px; border-left: 3px solid #0ca678; background: #effaf6; padding: 7px; }
      .answer p { max-height: 96px; overflow-y: auto; margin: 0; color: #173f33; font-size: 10px; white-space: pre-wrap; }
      .answer-actions { display: flex; justify-content: space-between; gap: 8px; align-items: center; color: #587068; font-size: 9px; }
      .attachment { display: grid; gap: 6px; border-top: 1px solid #e1e5e3; padding-top: 8px; }
      .attachment-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .attachment-head strong { font-size: 11px; }
      .attachment-head button { min-height: auto; border: 0; background: transparent; padding: 2px; font-size: 10px; font-weight: 600; }
      .attachment select { width: 100%; min-height: 34px; border: 1px solid #b7c4bf; border-radius: 6px; background: #fff; color: #17201d; padding: 5px 7px; font: inherit; letter-spacing: 0; }
      .selected-resume { display: grid; gap: 2px; color: #56625d; font-size: 9px; }
      .selected-resume strong { overflow: hidden; color: #26322e; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
      .attachment button { min-height: 34px; border: 1px solid #087f5b; border-radius: 6px; background: #fff; color: #075f46; padding: 6px 9px; font-weight: 700; }
      .attachment button:disabled { cursor: default; opacity: .55; }
      .attachment-message { border-left: 3px solid #0ca678; background: #effaf6; padding: 7px; color: #075f46; font-size: 10px; }
      .attachment-message.error { border-left-color: #c92a2a; background: #fff1f1; color: #9c2f2f; }
      .actions { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
      .action { min-height: 36px; border: 1px solid #9da8a3; border-radius: 6px; background: #fff; color: #17201d; padding: 7px 9px; }
      .action.primary { border-color: #087f5b; background: #0ca678; color: #fff; font-weight: 700; }
      .action:disabled { cursor: default; opacity: .55; }
      .message { border-left: 3px solid #0ca678; background: #effaf6; padding: 8px; color: #075f46; font-size: 11px; }
      .note { margin: 0; color: #66716d; font-size: 10px; }
      @media (max-width: 390px) { .assistant { width: min(320px, calc(100vw - 20px)); } }
    `;
    shadow.append(style);

    const shell = document.createElement("section");
    shell.className = "assistant";
    if (!expanded) {
      const chip = button("", "chip", () => {
        expanded = true;
        render();
        loadRecentResumes();
      });
      const label = document.createElement("span");
      label.innerHTML = `<strong>Application found</strong><span>${summary.ready} ready · ${summary.unmatched + summary.review + summary.questions} need attention</span>`;
      const total = document.createElement("strong");
      total.textContent = `${summary.filled + summary.ready}/${summary.total}`;
      chip.append(label, total);
      shell.append(chip);
      shadow.append(shell);
      document.documentElement.appendChild(host);
      return;
    }

    const panel = document.createElement("div");
    panel.className = "panel";
    const heading = document.createElement("div");
    heading.className = "heading";
    const headingText = document.createElement("div");
    headingText.innerHTML = "<strong>Application Autofill</strong><div>Review the match before filling.</div>";
    const dismiss = button("×", "dismiss", () => {
      dismissedFingerprint = candidate.fingerprint;
      removeWidget();
    });
    dismiss.setAttribute("aria-label", "Dismiss application autofill");
    heading.append(headingText, dismiss);

    const countGrid = document.createElement("div");
    countGrid.className = "counts";
    for (const [value, label] of [[summary.ready, "ready"], [summary.review, "review"], [summary.unmatched + summary.questions, "unmatched"]]) {
      const item = document.createElement("div");
      item.className = "count";
      item.innerHTML = `<b>${value}</b><span>${label}</span>`;
      countGrid.append(item);
    }

    const details = document.createElement("ul");
    details.className = "details";
    for (const [label, value] of [
      ["Already filled", summary.filled],
      ["Written questions", summary.questions],
      ["File uploads", summary.files],
    ]) {
      const item = document.createElement("li");
      item.innerHTML = `<span>${label}</span><b>${value}</b>`;
      details.append(item);
    }

    const attention = attentionFields(currentStatus);
    const attentionList = document.createElement("div");
    attentionList.className = "attention";
    const attentionHeading = document.createElement("strong");
    attentionHeading.textContent = "Needs attention";
    attentionList.append(attentionHeading);
    for (const field of attention.slice(0, 4)) {
      const row = document.createElement("div");
      row.className = "attention-row";
      const label = document.createElement("span");
      label.textContent = field.label;
      label.title = field.label;
      const reason = document.createElement("span");
      reason.textContent = field.reason;
      row.append(label, reason);
      attentionList.append(row);
    }
    if (attention.length > 4) {
      const remaining = document.createElement("div");
      remaining.className = "attention-row";
      remaining.textContent = `+${attention.length - 4} more`;
      attentionList.append(remaining);
    }

    const questions = applicationQuestions(currentStatus);
    const questionList = document.createElement("div");
    questionList.className = "questions";
    const questionHeading = document.createElement("strong");
    questionHeading.textContent = "Application questions";
    questionList.append(questionHeading);
    for (const question of questions) {
      const item = document.createElement("div");
      item.className = "question";
      const head = document.createElement("div");
      head.className = "question-head";
      const label = document.createElement("span");
      label.textContent = question.label;
      label.title = question.label;
      head.append(label);
      if (question.aiEligible) {
        const answer = questionAnswers[question.questionId];
        const action = button(
          questionBusy === question.questionId ? "Writing..." : answer ? "Regenerate" : "Ask AI",
          "",
          () => askQuestion(question),
        );
        action.disabled = !selectedResumeId || resumesLoading || Boolean(questionBusy);
        head.append(action);
      } else {
        const manual = document.createElement("span");
        manual.className = "question-meta";
        manual.textContent = "Manual";
        head.append(manual);
      }
      item.append(head);
      if (question.maxLength) {
        const meta = document.createElement("div");
        meta.className = "question-meta";
        meta.textContent = `Limit: ${question.maxLength} characters`;
        item.append(meta);
      }
      const saved = questionAnswers[question.questionId];
      if (saved?.answer) {
        const answer = document.createElement("div");
        answer.className = "answer";
        const text = document.createElement("p");
        text.textContent = saved.answer;
        const answerActions = document.createElement("div");
        answerActions.className = "answer-actions";
        const source = document.createElement("span");
        source.textContent = saved.draft?.company_name
          ? `Using ${saved.draft.company_name}`
          : `${saved.answer.length} characters`;
        const copy = button(copiedQuestionId === question.questionId ? "Copied" : "Copy", "", () => copyAnswer(question.questionId));
        answerActions.append(source, copy);
        answer.append(text, answerActions);
        item.append(answer);
      }
      if (questionErrors[question.questionId]) {
        const error = document.createElement("div");
        error.className = "question-error";
        error.textContent = questionErrors[question.questionId];
        item.append(error);
      }
      if (!question.aiEligible && question.aiBlockedReason) {
        const manualReason = document.createElement("div");
        manualReason.className = "question-error";
        manualReason.textContent = question.aiBlockedReason;
        item.append(manualReason);
      }
      questionList.append(item);
    }

    const actions = document.createElement("div");
    actions.className = "actions";
    const stepButton = button(busy ? "Working..." : "Fill this step", "action", () => confirmFill("step"));
    const applicationButton = button(busy ? "Working..." : "Fill this application", "action primary", () => confirmFill("application"));
    stepButton.disabled = busy || summary.ready === 0;
    applicationButton.disabled = busy || summary.ready === 0 || currentStatus.continueEnabled === false;
    actions.append(stepButton, applicationButton);

    const attachment = document.createElement("div");
    attachment.className = "attachment";
    if (summary.files > 0) {
      const attachmentHead = document.createElement("div");
      attachmentHead.className = "attachment-head";
      const attachmentLabel = document.createElement("strong");
      attachmentLabel.textContent = "Resume";
      const refreshResumes = button(resumesLoading ? "Loading..." : "Refresh list", "", () => loadRecentResumes(true));
      refreshResumes.disabled = resumesLoading || attachBusy;
      attachmentHead.append(attachmentLabel, refreshResumes);
      attachment.append(attachmentHead);

      const selector = document.createElement("select");
      selector.setAttribute("aria-label", "Resume to attach and answer with");
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = resumesLoading
        ? "Loading recent resumes..."
        : recentResumes.length
          ? "Choose a resume"
          : "No current PDF available";
      selector.append(emptyOption);
      for (const draft of recentResumes) {
        const option = document.createElement("option");
        option.value = draft.id;
        option.textContent = [
          draft.company_name || draft.filename || "Resume",
          draft.role_title,
          generatedAgo(draft.pdf_generated_at),
        ].filter(Boolean).join(" - ");
        selector.append(option);
      }
      selector.value = selectedResumeId;
      selector.disabled = resumesLoading || attachBusy;
      selector.addEventListener("change", () => {
        selectedResumeId = selector.value;
        attachmentMessage = "";
        attachmentError = false;
        render();
      });
      attachment.append(selector);

      const selectedResume = recentResumes.find((draft) => draft.id === selectedResumeId);
      if (selectedResume) {
        const selected = document.createElement("div");
        selected.className = "selected-resume";
        const filename = document.createElement("strong");
        filename.textContent = selectedResume.filename || "resume.pdf";
        filename.title = selectedResume.filename || "resume.pdf";
        const context = document.createElement("span");
        context.textContent = [selectedResume.company_name, selectedResume.role_title].filter(Boolean).join(" · ");
        selected.append(filename, context);
        attachment.append(selected);
      }

      const attach = button(attachBusy ? "Attaching..." : "Attach selected resume", "", attachResume);
      attach.disabled = !selectedResumeId || resumesLoading || attachBusy || Boolean(questionBusy) || busy;
      attachment.append(attach);
    }
    if (attachmentMessage) {
      const message = document.createElement("div");
      message.className = `attachment-message${attachmentError ? " error" : ""}`;
      message.textContent = attachmentMessage;
      attachment.append(message);
    }

    panel.append(heading, countGrid, details);
    if (attention.length) panel.append(attentionList);
    if (questions.length) panel.append(questionList);
    if (summary.files > 0 || attachmentMessage) panel.append(attachment);
    panel.append(actions);
    if (resultMessage) {
      const message = document.createElement("div");
      message.className = "message";
      message.textContent = resultMessage;
      panel.append(message);
    }
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = currentStatus.continueEnabled === false
      ? "Continued filling is disabled in your Autofill profile. This step can still be filled."
      : "Only safe, empty, high-confidence fields are filled. Sensitive questions, written answers, and files stay manual.";
    panel.append(note);
    shell.append(panel);
    shadow.append(shell);
    document.documentElement.appendChild(host);
  }

  async function detect() {
    if (stopped || !runtimeAvailable()) return;
    const urlChanged = lastUrl !== location.href;
    if (urlChanged) {
      lastUrl = location.href;
      lastCandidateFingerprint = "";
      dismissedFingerprint = "";
      currentStatus = null;
      resultMessage = "";
      removeWidget();
    }
    const candidate = lightweightCandidate();
    if (!candidate.shouldProbe) {
      if (lastCandidateFingerprint) {
        lastCandidateFingerprint = "";
        currentStatus = null;
        removeWidget();
        await send({ type: "AUTOFILL_APPLICATION_GONE", url: location.href });
      }
      return;
    }
    if (candidate.fingerprint === lastCandidateFingerprint && !urlChanged) return;
    lastCandidateFingerprint = candidate.fingerprint;
    const response = await send({
      type: "AUTOFILL_APPLICATION_CANDIDATE",
      url: location.href,
      fingerprint: candidate.fingerprint,
      controlCount: candidate.controlCount,
    });
    if (response?.status) {
      currentStatus = response.status;
      render();
      if (expanded) loadRecentResumes();
    }
  }

  function scheduleDetection(delay = 650) {
    clearTimeout(detectionTimer);
    clearTimeout(copyTimer);
    detectionTimer = setTimeout(() => detect().catch(() => {}), delay);
  }

  function handleMessage(message, _sender, sendResponse) {
    if (message?.type === "AUTOFILL_PAGE_STATUS") {
      currentStatus = message.status || null;
      render();
      sendResponse({ success: true });
      return false;
    }
    if (message?.type === "AUTOFILL_NAVIGATION_CHANGED") {
      scheduleDetection(250);
      sendResponse({ success: true });
      return false;
    }
    return false;
  }

  function shutdown() {
    stopped = true;
    clearTimeout(detectionTimer);
    observer?.disconnect();
    removeWidget();
    try { chrome.runtime.onMessage.removeListener(handleMessage); } catch (_) {}
  }

  globalThis.__resumeApplicationAssistantLifecycle = {
    version,
    runtimeId,
    instanceId,
    isActive: runtimeAvailable,
    shutdown,
  };
  chrome.runtime.onMessage.addListener(handleMessage);
  observer = new MutationObserver(() => scheduleDetection());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("popstate", () => scheduleDetection(200));
  window.addEventListener("hashchange", () => scheduleDetection(200));
  scheduleDetection(350);
})();
