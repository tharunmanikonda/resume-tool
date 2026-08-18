/**
 * Resume Generator Application
 * Auto-validation with modern UX
 */

class ResumeGenerator {
    constructor() {
        this.contentInput = document.getElementById("contentInput");
        this.companyNameInput = document.getElementById("companyName");
        this.folderNameInput = document.getElementById("folderName");
        this.generateBtn = document.getElementById("generateBtn");
        this.jobDescriptionInput = document.getElementById("jobDescriptionInput");
        this.aiInstructionInput = document.getElementById("aiInstructionInput");
        this.aiGenerateBtn = document.getElementById("aiGenerateBtn");
        this.aiResetBtn = document.getElementById("aiResetBtn");
        this.jdVoiceBtn = document.getElementById("jdVoiceBtn");
        this.refineVoiceBtn = document.getElementById("refineVoiceBtn");
        this.aiStatusBadge = document.getElementById("aiStatusBadge");
        this.aiMemoryBadge = document.getElementById("aiMemoryBadge");
        this.aiError = document.getElementById("aiError");
        this.aiResultArea = document.getElementById("aiResultArea");
        this.aiThread = document.getElementById("aiThread");
        this.generatedArtifact = document.getElementById("generatedArtifact");
        this.generatedContentEditor = document.getElementById("generatedContentEditor");
        this.downloadBtn = document.getElementById("downloadBtn");
        this.openFolderBtn = document.getElementById("openFolderBtn");
        this.refreshBtn = document.getElementById("refreshBtn");
        this.retryBtn = document.getElementById("retryBtn");

        // Validation
        this.validationDisplay = document.getElementById("validationDisplay");
        this.validationStatus = document.getElementById("validationStatus");
        this.errorsList = document.getElementById("errorsList");
        this.warningsList = document.getElementById("warningsList");

        // States
        this.initialState = document.getElementById("initialState");
        this.loadingState = document.getElementById("loadingState");
        this.successState = document.getElementById("successState");
        this.errorState = document.getElementById("errorState");
        this.parsedTabBtn = document.getElementById("parsedTabBtn");
        this.pdfTabBtn = document.getElementById("pdfTabBtn");
        this.parsedTab = document.getElementById("parsedTab");
        this.pdfTab = document.getElementById("pdfTab");

        // Modal - Instructions
        this.instructionsModal = document.getElementById("instructionsModal");
        this.instructionsBtn = document.getElementById("instructionsBtn");
        this.closeModalBtn = document.getElementById("closeModal");
        this.modalOverlay = document.getElementById("modalOverlay");

        // Modal - Settings
        this.settingsModal = document.getElementById("settingsModal");
        this.settingsBtn = document.getElementById("settingsBtn");
        this.settingsClose = document.getElementById("settingsClose");
        this.settingsCancel = document.getElementById("settingsCancel");
        this.settingsSave = document.getElementById("settingsSave");
        this.settingsModalOverlay = document.getElementById("settingsModalOverlay");
        this.outputDirInput = document.getElementById("outputDirInput");
        this.browseBtn = document.getElementById("browseBtn");
        this.dirPickerInput = document.getElementById("dirPickerInput");

        // Modal - Profile
        this.profileModal = document.getElementById("profileModal");
        this.profileBtn = document.getElementById("profileBtn");
        this.profileClose = document.getElementById("profileClose");
        this.profileCancel = document.getElementById("profileCancel");
        this.profileSave = document.getElementById("profileSave");
        this.profileModalOverlay = document.getElementById("profileModalOverlay");
        this.profileName = document.getElementById("profileName");
        this.profileLocation = document.getElementById("profileLocation");
        this.profilePhone = document.getElementById("profilePhone");
        this.profileEmail = document.getElementById("profileEmail");
        this.profileCertifications = document.getElementById("profileCertifications");
        this.profileProjects = document.getElementById("profileProjects");

        // Inline contact editor
        this.previewLocation = document.getElementById("previewLocation");
        this.previewPhone = document.getElementById("previewPhone");
        this.previewEmail = document.getElementById("previewEmail");
        this.contactSaveStatus = document.getElementById("contactSaveStatus");
        this.outlookIdentityBtn = document.getElementById("outlookIdentityBtn");
        this.gmailIdentityBtn = document.getElementById("gmailIdentityBtn");
        this.identityPresets = {
            outlook: null,
            gmail: null,
        };
        this.selectedIdentity = "outlook";

        // Base resume for local parsing
        this.baseResume = null;
        this.currentProfile = null;
        this.contactSaveTimeout = null;
        this.loadBaseResume();
        this.loadProfile();

        // Event listeners
        this.contentInput.addEventListener("input", () => this.onContentChange());
        this.jobDescriptionInput.addEventListener("input", () => this.onJobDescriptionChange());
        this.contentInput.addEventListener("keydown", (e) => this.handleContentKeydown(e));
        this.generatedContentEditor.addEventListener("input", () => this.onGeneratedContentEdit());
        this.folderNameInput.addEventListener("keydown", (e) => this.handleFolderKeydown(e));
        this.generateBtn.addEventListener("click", () => this.generate());
        this.aiGenerateBtn.addEventListener("click", () => this.generateFromJobDescription());
        this.aiResetBtn.addEventListener("click", () => this.resetAiMemory());
        this.jdVoiceBtn.addEventListener("click", () => this.startVoiceInput(this.jobDescriptionInput, this.jdVoiceBtn));
        this.refineVoiceBtn.addEventListener("click", () => this.startVoiceInput(this.aiInstructionInput, this.refineVoiceBtn));
        this.downloadBtn.addEventListener("click", () => this.download());
        this.openFolderBtn.addEventListener("click", () => this.openGeneratedFolder());
        this.refreshBtn.addEventListener("click", () => this.checkStatus());
        this.retryBtn.addEventListener("click", () => this.reset());
        this.instructionsBtn.addEventListener("click", () => this.openModal());
        this.closeModalBtn.addEventListener("click", () => this.closeModal());
        this.modalOverlay.addEventListener("click", () => this.closeModal());

        this.settingsBtn.addEventListener("click", () => this.openSettings());
        this.settingsClose.addEventListener("click", () => this.closeSettings());
        this.settingsCancel.addEventListener("click", () => this.closeSettings());
        this.settingsModalOverlay.addEventListener("click", () => this.closeSettings());
        this.settingsSave.addEventListener("click", () => this.saveSettings());
        this.browseBtn.addEventListener("click", () => this.browseDirectory());
        this.dirPickerInput.addEventListener("change", (e) => this.handleDirectorySelection(e));

        this.profileBtn.addEventListener("click", () => this.openProfile());
        this.profileClose.addEventListener("click", () => this.closeProfile());
        this.profileCancel.addEventListener("click", () => this.closeProfile());
        this.profileModalOverlay.addEventListener("click", () => this.closeProfile());
        this.profileSave.addEventListener("click", () => this.saveProfile());
        this.parsedTabBtn.addEventListener("click", () => this.showTab("parsed"));
        this.pdfTabBtn.addEventListener("click", () => this.showTab("pdf"));

        [this.previewLocation, this.previewPhone, this.previewEmail].forEach((input) => {
            input.addEventListener("input", () => this.onContactChange());
            input.addEventListener("blur", () => this.saveInlineContact());
        });
        this.outlookIdentityBtn.addEventListener("click", () => this.applyIdentity("outlook"));
        this.gmailIdentityBtn.addEventListener("click", () => this.applyIdentity("gmail"));

        // Drag and drop support for directory input
        this.outputDirInput.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.outputDirInput.style.borderColor = "var(--primary)";
            this.outputDirInput.style.backgroundColor = "#f0f7ff";
        });

        this.outputDirInput.addEventListener("dragleave", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.outputDirInput.style.borderColor = "var(--gray-300)";
            this.outputDirInput.style.backgroundColor = "white";
        });

        this.outputDirInput.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.outputDirInput.style.borderColor = "var(--gray-300)";
            this.outputDirInput.style.backgroundColor = "white";
            this.handleDirectoryDrop(e);
        });

        this.statusPath = null;
        this.pdfPath = null;
        this.outputDir = null;
        this.statusCheckInterval = null;
        this.validationTimeout = null;
        this.isGenerating = false;
        this.isAiGenerating = false;
        this.aiSessionId = null;
        this.lastGeneratedJobDescription = "";
        this.speechRecognition = null;

        // Initial state
        this.showState("initial");
        this.loadAiStatus();
    }

    async loadBaseResume() {
        try {
            const response = await fetch("/config/base_resume.json");
            this.baseResume = await response.json();
            if (this.baseResume?.contact) {
                this.identityPresets.outlook = { ...this.baseResume.contact };
            }
            this.populateContactEditor();
        } catch (error) {
            console.error("Failed to load base resume:", error);
            this.baseResume = {};
        }
    }

    async loadProfile() {
        try {
            const response = await fetch("/api/profile");
            this.currentProfile = await response.json();
            this.populateContactEditorFromProfile(true);
        } catch (error) {
            console.error("Failed to load profile:", error);
            this.currentProfile = null;
        }
    }

    getCurrentContact() {
        return {
            location: this.previewLocation?.value.trim() || "",
            phone: this.previewPhone?.value.trim() || "",
            email: this.previewEmail?.value.trim() || "",
        };
    }

    setCurrentContact(contact) {
        this.previewLocation.value = contact.location || "";
        this.previewPhone.value = contact.phone || "";
        this.previewEmail.value = contact.email || "";
    }

    updateIdentityButtons(identity) {
        this.selectedIdentity = identity;
        this.outlookIdentityBtn.classList.toggle("active", identity === "outlook");
        this.gmailIdentityBtn.classList.toggle("active", identity === "gmail");
    }

    rememberOutlookPreset(contact, force = false) {
        if (force || !this.identityPresets.outlook) {
            this.identityPresets.outlook = { ...contact };
        }
    }

    applyIdentity(identity) {
        if (identity === "outlook") {
            const contact = this.identityPresets.outlook || this.currentProfile?.contact || this.baseResume?.contact || {};
            this.setCurrentContact(contact);
        } else {
            const contact = this.identityPresets.gmail || this.currentProfile?.contact || this.baseResume?.contact || {};
            this.setCurrentContact(contact);
        }

        this.updateIdentityButtons(identity);
        this.onContactChange();
        this.saveInlineContact();
    }

    populateContactEditor() {
        const contact = this.currentProfile?.contact || this.baseResume?.contact;
        if (!contact || !this.previewLocation || this.previewLocation.value || this.previewPhone.value || this.previewEmail.value) {
            return;
        }

        this.rememberOutlookPreset(contact);
        this.setCurrentContact(contact);
        this.updateIdentityButtons("outlook");
    }

    applyProfileToPreview(preview) {
        const contact = this.getCurrentContact();
        return {
            ...preview,
            name: this.currentProfile?.name || preview.name || this.baseResume?.name || "",
            contact: {
                ...(preview.contact || this.baseResume?.contact || {}),
                ...contact,
            },
            projects: this.currentProfile?.projects || preview.projects,
            certifications: this.currentProfile?.certifications || preview.certifications,
        };
    }

    onContactChange() {
        const content = this.contentInput.value.trim();
        if (content) {
            this.loadPreview(content);
        }

        clearTimeout(this.contactSaveTimeout);
        this.contactSaveStatus.textContent = "Unsaved";
        this.contactSaveTimeout = setTimeout(() => this.saveInlineContact(), 800);
    }

    async saveInlineContact() {
        clearTimeout(this.contactSaveTimeout);
        if (!this.currentProfile) return;

        const payload = {
            ...this.currentProfile,
            contact: {
                ...(this.currentProfile.contact || {}),
                ...this.getCurrentContact(),
            },
        };

        this.contactSaveStatus.textContent = "Saving...";
        try {
            const response = await fetch("/api/profile", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (data.success) {
                this.currentProfile = data.profile;
                this.updateIdentityButtons(this.identityPresets.gmail?.email && this.previewEmail.value === this.identityPresets.gmail.email ? "gmail" : "outlook");
                this.contactSaveStatus.textContent = "Saved";
                setTimeout(() => {
                    if (this.contactSaveStatus.textContent === "Saved") {
                        this.contactSaveStatus.textContent = "";
                    }
                }, 1200);
            } else {
                this.contactSaveStatus.textContent = "Save failed";
            }
        } catch (error) {
            console.error("Contact save error:", error);
            this.contactSaveStatus.textContent = "Save failed";
        }
    }

    showTab(tab) {
        const showPdf = tab === "pdf";
        this.parsedTabBtn.classList.toggle("active", !showPdf);
        this.pdfTabBtn.classList.toggle("active", showPdf);
        this.parsedTab.classList.toggle("active", !showPdf);
        this.pdfTab.classList.toggle("active", showPdf);
    }

    async loadAiStatus() {
        try {
            const response = await fetch("/api/ai/status");
            const data = await response.json();
            this.aiStatusBadge.textContent = data.ready ? "AI Ready" : "AI Error";
            this.aiStatusBadge.classList.toggle("status-ok", !!data.ready);
            this.aiStatusBadge.classList.toggle("status-error", !data.ready);
            this.updateAiMemoryBadge(0, data.memory_limit || 2);
        } catch (error) {
            console.error("AI status error:", error);
            this.aiStatusBadge.textContent = "AI Error";
            this.aiStatusBadge.classList.add("status-error");
        }
    }

    updateAiMemoryBadge(count = 0, limit = 2) {
        this.aiMemoryBadge.textContent = `Memory ${count}/${limit}`;
        this.aiMemoryBadge.style.display = count > 0 ? "inline-block" : "none";
    }

    onJobDescriptionChange() {
        const current = this.jobDescriptionInput.value.trim();
        if (this.lastGeneratedJobDescription && current !== this.lastGeneratedJobDescription) {
            this.aiSessionId = null;
            this.updateAiMemoryBadge(0, 2);
        }
    }

    showAiError(message) {
        if (!message) {
            this.aiError.style.display = "none";
            this.aiError.textContent = "";
            return;
        }
        this.aiError.style.display = "block";
        this.aiError.textContent = message;
    }

    escapeHtml(value) {
        return (value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    renderThreadEmpty() {
        this.aiThread.innerHTML = '<div class="thread-empty">Paste a JD and generate. The soul of the role and the generated resume content will show here.</div>';
    }

    appendThreadCard(kind, title, bodyHtml) {
        if (!this.aiThread) return;
        const empty = this.aiThread.querySelector(".thread-empty");
        if (empty) empty.remove();

        const card = document.createElement("div");
        card.className = `thread-card ${kind}`;
        card.innerHTML = `
            <div class="thread-card-header">${kind === "user" ? "You" : "Resume Engine"}</div>
            <div class="thread-card-body">
                <span class="thread-card-title">${this.escapeHtml(title)}</span>
                ${bodyHtml}
            </div>
        `;
        this.aiThread.appendChild(card);
        this.aiThread.scrollTop = this.aiThread.scrollHeight;
    }

    renderSoulMessage(analysis) {
        if (!analysis) return;
        const keySignals = (analysis.core_skills || []).slice(0, 6);
        const pivot = (analysis.build_strategy || []).slice(0, 3);
        const body = `
            <div><strong>Soul of the role:</strong> ${this.escapeHtml(analysis.core_problem || "")}</div>
            <div style="margin-top:6px;"><strong>System focus:</strong> ${this.escapeHtml(analysis.system_description || "")}</div>
            <div style="margin-top:6px;"><strong>Pivot plan:</strong></div>
            <ul class="thread-card-list">${pivot.map((item) => `<li>${this.escapeHtml(item)}</li>`).join("")}</ul>
            <div style="margin-top:6px;"><strong>Key signals:</strong> ${this.escapeHtml(keySignals.join(", "))}</div>
        `;
        this.appendThreadCard("assistant", analysis.target_role || "Role read", body);
    }

    onGeneratedContentEdit() {
        const content = this.generatedContentEditor.value;
        this.contentInput.value = content;
        this.onContentChange();
    }

    startVoiceInput(targetInput, triggerButton) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            this.showAiError("Voice input is not supported in this browser.");
            return;
        }

        if (this.speechRecognition) {
            this.speechRecognition.stop();
            this.speechRecognition = null;
        }

        const recognition = new SpeechRecognition();
        recognition.lang = "en-US";
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        this.speechRecognition = recognition;
        triggerButton.textContent = "Listening...";
        this.showAiError("");

        recognition.onresult = (event) => {
            const transcript = event.results?.[0]?.[0]?.transcript || "";
            if (!transcript) return;
            const existing = targetInput.value.trim();
            targetInput.value = existing ? `${existing} ${transcript}` : transcript;
            targetInput.dispatchEvent(new Event("input", { bubbles: true }));
        };

        recognition.onerror = () => {
            this.showAiError("Voice input failed. Try again.");
        };

        recognition.onend = () => {
            triggerButton.textContent = triggerButton === this.jdVoiceBtn ? "Voice to JD" : "Voice";
            this.speechRecognition = null;
        };

        recognition.start();
    }

    async resetAiMemory() {
        const sessionId = this.aiSessionId;
        this.aiSessionId = null;
        this.lastGeneratedJobDescription = "";
        this.updateAiMemoryBadge(0, 2);
        this.showAiError("");
        this.aiInstructionInput.value = "";
        this.generatedContentEditor.value = "";
        this.aiResultArea.style.display = "none";
        this.contentInput.value = "";
        this.jobDescriptionInput.value = "";
        this.onContentChange();
        this.renderThreadEmpty();

        if (!sessionId) return;

        try {
            await fetch("/api/ai/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId }),
            });
        } catch (error) {
            console.error("AI reset error:", error);
        }
    }

    async generateFromJobDescription() {
        const jobDescription = this.jobDescriptionInput.value.trim();
        const revisionRequest = this.aiInstructionInput.value.trim();

        if (!jobDescription) {
            this.showAiError("Paste a job description first.");
            return;
        }

        const resetMemory = !this.aiSessionId || (this.lastGeneratedJobDescription && this.lastGeneratedJobDescription !== jobDescription);

        this.isAiGenerating = true;
        this.aiGenerateBtn.disabled = true;
        this.aiResetBtn.disabled = true;
        this.jdVoiceBtn.disabled = true;
        this.refineVoiceBtn.disabled = true;
        this.showAiError("");
        this.aiStatusBadge.textContent = "Generating...";

        try {
            if (resetMemory) {
                this.renderThreadEmpty();
                this.appendThreadCard("user", "New job description", `<div>${this.escapeHtml(jobDescription.slice(0, 600))}</div>`);
            } else if (revisionRequest) {
                this.appendThreadCard("user", "Refinement request", `<div>${this.escapeHtml(revisionRequest)}</div>`);
            }

            const response = await fetch("/api/ai/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    job_description: jobDescription,
                    revision_request: revisionRequest,
                    current_resume_content: this.contentInput.value.trim(),
                    session_id: this.aiSessionId,
                    reset_memory: resetMemory,
                }),
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || "Failed to generate resume content");
            }

            this.aiSessionId = data.session_id || null;
            this.lastGeneratedJobDescription = jobDescription;
            this.updateAiMemoryBadge(data.memory_count || 0, data.memory_limit || 2);
            this.aiStatusBadge.textContent = "AI Ready";
            this.aiStatusBadge.classList.add("status-ok");
            this.aiStatusBadge.classList.remove("status-error");
            this.renderSoulMessage(data.analysis);

            this.aiResultArea.style.display = "flex";
            this.generatedContentEditor.value = data.content || "";
            this.contentInput.value = data.content || "";
            this.onContentChange();
            this.showTab("parsed");
        } catch (error) {
            console.error("AI generate error:", error);
            this.aiStatusBadge.textContent = "AI Error";
            this.aiStatusBadge.classList.add("status-error");
            this.aiStatusBadge.classList.remove("status-ok");
            this.showAiError(error.message || "Failed to generate resume content.");
        } finally {
            this.isAiGenerating = false;
            this.aiGenerateBtn.disabled = false;
            this.aiResetBtn.disabled = false;
            this.jdVoiceBtn.disabled = false;
            this.refineVoiceBtn.disabled = false;
        }
    }

    // Auto-validate and preview with debounce
    onContentChange() {
        const content = this.contentInput.value.trim();
        this.updateCharCount();

        // Clear previous timeout
        clearTimeout(this.validationTimeout);

        // Show preview immediately if there's content
        if (content) {
            this.showTab("parsed");
            // Load preview immediately
            this.loadPreview(content);

            // Debounce validation
            this.validationTimeout = setTimeout(() => this.validate(), 500);
        } else {
            this.showTab("parsed");
            this.validationDisplay.style.display = "none";
            this.generateBtn.disabled = true;
            document.getElementById("previewContainer").style.display = "none";
        }
    }

    handleContentKeydown(e) {
        // Shift+Enter from content input -> focus company name
        if (e.shiftKey && e.key === "Enter") {
            if (this.isGenerating) return;
            e.preventDefault();
            this.companyNameInput.focus();
        }
    }

    handleFolderKeydown(e) {
        // Shift+Enter from folder name input -> generate
        if (e.shiftKey && e.key === "Enter") {
            if (this.isGenerating) return;
            e.preventDefault();
            this.generate();
        }
    }

    updateCharCount() {
        const count = this.contentInput.value.length;
        document.getElementById("charCount").textContent = count;
    }

    async validate() {
        const content = this.contentInput.value.trim();

        if (!content) {
            this.generateBtn.disabled = true;
            return;
        }

        try {
            const response = await fetch("/api/validate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content }),
            });

            const data = await response.json();

            // Update validation display
            this.showValidationStatus(data.valid, data.errors, data.warnings);

            // Enable/disable generate button based on validation
            this.generateBtn.disabled = !data.valid;
        } catch (error) {
            console.error("Validation error:", error);
            this.generateBtn.disabled = true;
        }
    }

    async loadPreview(content) {
        if (!this.baseResume) return;
        const preview = this.applyProfileToPreview(parseUpdatedContentToResume(content, this.baseResume));
        const validation = validateUpdatedContent(content);
        this.displayPreview(preview);
        if (validation.errors.length > 0) {
            this.showValidationStatus(false, validation.errors, validation.warnings);
        }
    }

    displayPreview(preview) {
        const container = document.getElementById("previewContainer");
        console.log("Display preview called, container:", container);
        console.log("Preview data:", preview);

        // Helper function to apply bold formatting
        const applyBold = (text) => {
            return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        };

        let html = '<div class="preview-content">';

        // Title
        if (preview.title) {
            const boldTitle = applyBold(preview.title);
            const contact = preview.contact || {};
            const contactLine = [contact.location, contact.phone, contact.email].filter(Boolean).join(" | ");
            html += `<div class="preview-section"><h3 class="preview-title">${boldTitle}</h3>`;
            if (contactLine) {
                html += `<div class="preview-contact">${contactLine}</div>`;
            }
            html += `</div>`;
        }

        // Summary
        if (preview.summary) {
            const boldSummary = applyBold(preview.summary);
            html += `<div class="preview-section">
                <h4 class="preview-heading">SUMMARY</h4>
                <p class="preview-text">${boldSummary}</p>
            </div>`;
        }

        // Skills
        if (preview.technical_skills && preview.technical_skills.length > 0) {
            html += `<div class="preview-section">
                <h4 class="preview-heading">TECHNICAL SKILLS</h4>
                <div class="preview-skills">`;
            preview.technical_skills.forEach(skill => {
                const boldItems = applyBold(skill.items);
                html += `<div class="skill-item"><strong>${skill.category}:</strong> ${boldItems}</div>`;
            });
            html += '</div></div>';
        }

        // Experience
        if (preview.experience && preview.experience.length > 0) {
            html += '<div class="preview-section"><h4 class="preview-heading">PROFESSIONAL EXPERIENCE</h4>';
            preview.experience.forEach(exp => {
                if (exp.company || exp.title) {
                    html += `<div class="preview-experience">
                        <div class="exp-header">
                            <strong>${exp.company}</strong> | ${exp.dates}
                        </div>
                        <div class="exp-title">${exp.title}</div>
                        <div class="exp-bullets">`;

                    if (exp.bullets && exp.bullets.length > 0) {
                        // Show ALL bullets, with **bold** support
                        exp.bullets.forEach(bullet => {
                            const boldBullet = applyBold(bullet);
                            html += `<div class="bullet">• ${boldBullet}</div>`;
                        });
                    } else {
                        html += '<div class="bullet-none">⚠️ No bullets found for this company</div>';
                    }

                    html += '</div></div>';
                }
            });
            html += '</div>';
        }

        html += '</div>';

        container.innerHTML = html;
        container.style.display = "block";
    }

    openModal() {
        this.instructionsModal.style.display = "flex";
        document.body.style.overflow = "hidden";
    }

    closeModal() {
        this.instructionsModal.style.display = "none";
        document.body.style.overflow = "auto";
    }

    async openSettings() {
        try {
            const response = await fetch("/api/settings");
            const settings = await response.json();
            this.outputDirInput.value = settings.output_directory || "";
            this.settingsModal.style.display = "flex";
            document.body.style.overflow = "hidden";
        } catch (error) {
            console.error("Failed to load settings:", error);
        }
    }

    closeSettings() {
        this.settingsModal.style.display = "none";
        document.body.style.overflow = "auto";
    }

    formatProjects(projects) {
        return (projects || [])
            .map((project) => {
                const bullets = (project.bullets || [])
                    .map((bullet) => `- ${bullet}`)
                    .join("\n");
                return [project.name || "", bullets].filter(Boolean).join("\n");
            })
            .filter(Boolean)
            .join("\n\n");
    }

    parseProjects(text) {
        const blocks = text
            .split(/\n\s*\n/)
            .map((block) => block.trim())
            .filter(Boolean);

        return blocks
            .map((block) => {
                const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
                const name = lines.shift() || "";
                const bullets = lines
                    .map((line) => line.replace(/^[-•●]\s*/, "").trim())
                    .filter(Boolean);
                return { name, bullets };
            })
            .filter((project) => project.name);
    }

    async openProfile() {
        try {
            const response = await fetch("/api/profile");
            const profile = await response.json();
            this.currentProfile = profile;
            this.profileName.value = profile.name || "";
            this.profileLocation.value = profile.contact?.location || "";
            this.profilePhone.value = profile.contact?.phone || "";
            this.profileEmail.value = profile.contact?.email || "";
            this.profileCertifications.value = (profile.certifications || []).join("\n");
            this.profileProjects.value = this.formatProjects(profile.projects || []);
            this.profileModal.style.display = "flex";
            document.body.style.overflow = "hidden";
        } catch (error) {
            console.error("Failed to load profile:", error);
            alert("Could not load profile settings.");
        }
    }

    closeProfile() {
        this.profileModal.style.display = "none";
        document.body.style.overflow = "auto";
    }

    async saveProfile() {
        const payload = {
            name: this.profileName.value.trim(),
            contact: {
                location: this.profileLocation.value.trim(),
                phone: this.profilePhone.value.trim(),
                email: this.profileEmail.value.trim(),
            },
            certifications: this.profileCertifications.value
                .split("\n")
                .map((line) => line.trim())
                .filter(Boolean),
            projects: this.parseProjects(this.profileProjects.value),
        };

        this.profileSave.disabled = true;
        try {
            const response = await fetch("/api/profile", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (data.success) {
                this.currentProfile = data.profile;
                this.populateContactEditorFromProfile(true);
                this.closeProfile();
            } else {
                alert(`Error: ${data.error || "Failed to save profile"}`);
            }
        } catch (error) {
            console.error("Profile save error:", error);
            alert("Failed to save profile.");
        } finally {
            this.profileSave.disabled = false;
        }
    }

    populateContactEditorFromProfile(force = false) {
        const contact = this.currentProfile?.contact;
        if (!contact) return;
        if (force || !this.previewLocation.value) this.previewLocation.value = contact.location || "";
        if (force || !this.previewPhone.value) this.previewPhone.value = contact.phone || "";
        if (force || !this.previewEmail.value) this.previewEmail.value = contact.email || "";
        this.updateIdentityButtons(this.identityPresets.gmail?.email && this.previewEmail.value === this.identityPresets.gmail.email ? "gmail" : "outlook");
        const content = this.contentInput.value.trim();
        if (content) {
            this.loadPreview(content);
        }
    }

    async saveSettings() {
        const outputDirectory = this.outputDirInput.value.trim();

        if (!outputDirectory) {
            alert("Please enter a valid output directory path");
            return;
        }

        this.settingsSave.disabled = true;

        try {
            const response = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ output_directory: outputDirectory }),
            });

            const data = await response.json();

            if (data.success) {
                alert("Settings saved successfully!");
                this.closeSettings();
            } else {
                alert(`Error: ${data.error || "Failed to save settings"}`);
            }
        } catch (error) {
            console.error("Error saving settings:", error);
            alert("Failed to save settings. Please try again.");
        } finally {
            this.settingsSave.disabled = false;
        }
    }

    async browseDirectory() {
        try {
            const response = await fetch("/api/select-output-directory", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            const data = await response.json();
            if (data.success) {
                this.outputDirInput.value = data.output_directory;
            } else if (!data.cancelled) {
                alert(`Could not open folder picker: ${data.error || "Unknown error"}`);
            }
        } catch (error) {
            console.error("Directory picker error:", error);
            alert("Could not open the folder picker. Enter the full folder path manually.");
        }
    }

    handleDirectorySelection(event) {
        const files = event.target.files;

        if (files.length === 0) {
            return;
        }

        // webkitRelativePath gives us paths like "folder-name/file1.txt"
        // Extract the root folder name from the first file's path
        const firstFilePath = files[0].webkitRelativePath || files[0].name;
        const pathParts = firstFilePath.split('/');

        if (pathParts.length > 0) {
            const dirName = pathParts[0];
            // Show alert with the directory name found
            alert(`Found directory: "${dirName}"\n\nPlease enter the FULL absolute path to this directory.\n\nExample: /Users/yourname/Documents/${dirName}`);
            console.log("Selected directory name:", dirName, `(containing ${files.length} files)`);
        } else {
            alert("Please select a directory, not a file");
        }

        // Reset the file input so the same directory can be selected again
        this.dirPickerInput.value = "";
    }

    handleDirectoryDrop(event) {
        const items = event.dataTransfer.items;

        if (!items || items.length === 0) {
            return;
        }

        // Get the first dropped item
        const item = items[0];

        if (item.kind === "file") {
            const entry = item.webkitGetAsEntry();

            if (entry && entry.isDirectory) {
                // Try to get the full path from the directory entry
                const fullPath = entry.fullPath;

                if (fullPath && fullPath !== "/") {
                    this.outputDirInput.value = fullPath;
                    console.log("Dropped directory path:", fullPath);
                } else {
                    // Fallback to just showing the name
                    const dirName = entry.name;
                    alert(`Dropped directory: "${dirName}"\n\nPlease enter the FULL absolute path to this directory.\n\nExample: /Users/yourname/Documents/${dirName}`);
                    this.outputDirInput.value = dirName;
                }
            } else {
                alert("Please drop a folder, not a file");
            }
        }
    }

    showValidationStatus(valid, errors, warnings) {
        // Update status badge
        this.validationStatus.className = valid ? "status-badge valid" : "status-badge invalid";
        this.validationStatus.textContent = valid ? "✓ Valid" : "✕ Invalid";

        // Update errors
        if (errors.length > 0) {
            this.errorsList.innerHTML = errors
                .map((err) => `<div>${err}</div>`)
                .join("");
            this.validationDisplay.style.display = "block";
        } else {
            this.validationDisplay.style.display = "none";
        }
    }

    async generate() {
        const content = this.contentInput.value.trim();
        const companyName = this.companyNameInput.value.trim();
        const folderName = this.folderNameInput.value.trim();

        if (!content) {
            this.showError("Please paste resume content first");
            return;
        }

        this.isGenerating = true;
        this.generateBtn.disabled = true;
        this.contentInput.disabled = true;
        this.companyNameInput.disabled = true;
        this.folderNameInput.disabled = true;
        this.showState("loading");

        try {
            const payload = {
                content,
                contact_override: this.getCurrentContact(),
                identity: this.selectedIdentity || "outlook",
            };
            if (companyName) {
                payload.company_name = companyName;
            }
            if (folderName) {
                payload.folder_name = folderName;
            }

            const response = await fetch("/api/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            const data = await response.json();

            if (data.success) {
                this.statusPath = data.status_path;
                this.pdfPath = data.pdf;
                this.outputDir = data.output_dir;

                // Show success state and start polling
                this.showTab("pdf");
                this.showState("success");
                this.startStatusPolling();
            } else {
                this.showError(data.error || "Generation failed");
                this.showState("error");
            }
        } catch (error) {
            this.showError(error.message);
            this.showState("error");
        } finally {
            this.isGenerating = false;
            this.generateBtn.disabled = false;
            this.contentInput.disabled = false;
            this.companyNameInput.disabled = false;
            this.folderNameInput.disabled = false;
        }
    }

    startStatusPolling() {
        let pollCount = 0;
        const maxPolls = 150;
        const startTime = Date.now();

        // Show proper loading UI
        const previewSection = document.getElementById("previewSection");
        const statusPDF = document.getElementById("statusPDF");

        if (previewSection) previewSection.style.display = "flex";
        if (statusPDF) {
            statusPDF.innerHTML = '<span class="spinner"></span> Generating PDF... Please wait';
        }

        const pdfPreview = document.getElementById("pdfPreview");
        if (pdfPreview) {
            pdfPreview.src = "";
            pdfPreview.style.display = "none";
        }

        this.statusCheckInterval = setInterval(async () => {
            pollCount++;
            const elapsedSec = Math.floor((Date.now() - startTime) / 1000);

            // Update elapsed time
            if (statusPDF) {
                statusPDF.innerHTML = `<span class="spinner"></span> Generating PDF... ${elapsedSec}s`;
            }

            if (pollCount > maxPolls) {
                clearInterval(this.statusCheckInterval);
                this.showRefreshOption();
                return;
            }

            try {
                const response = await fetch(
                    `/api/status?path=${encodeURIComponent(this.statusPath)}`
                );
                const status = await response.json();

                if (status.state === "success") {
                    clearInterval(this.statusCheckInterval);
                    this.pdfPath = status.pdf;

                    // Show loading message
                    if (statusPDF) {
                        statusPDF.innerHTML = '<span class="spinner"></span> Loading PDF...';
                    }

                    // Load the real PDF
                    this.loadPdfPreview();

                    // After PDF loads, show ready
                    setTimeout(() => {
                        if (statusPDF) statusPDF.textContent = "✓ Ready";
                        this.showDownloadOption();
                    }, 500);
                }
            } catch (error) {
                console.error("Status check error:", error);
            }
        }, 200);
    }

    loadPdfPreview() {
        const previewSection = document.getElementById("previewSection");
        const pdfPreview = document.getElementById("pdfPreview");

        console.log("loadPdfPreview called, pdfPath:", this.pdfPath);
        if (!this.pdfPath) {
            console.log("No pdfPath, returning");
            return;
        }

        const url = `/api/download?path=${encodeURIComponent(this.pdfPath)}&preview=true#view=FitH&toolbar=0&navpanes=0`;
        console.log("Setting iframe src to:", url);
        pdfPreview.src = url;
        pdfPreview.style.display = "block";
        previewSection.style.display = "flex";
        console.log("Preview section shown");
    }

    showDownloadOption() {
        const downloadSection = document.getElementById("downloadSection");
        const refreshSection = document.getElementById("refreshSection");
        console.log("showDownloadOption called, downloadSection:", downloadSection);
        if (downloadSection) {
            downloadSection.style.display = "flex";
            console.log("Download section shown");
        }
        if (refreshSection) refreshSection.style.display = "none";
    }

    showRefreshOption() {
        const downloadSection = document.getElementById("downloadSection");
        const refreshSection = document.getElementById("refreshSection");
        if (downloadSection) downloadSection.style.display = "none";
        if (refreshSection) refreshSection.style.display = "block";
    }

    async checkStatus() {
        if (!this.statusPath) return;

        try {
            const response = await fetch(
                `/api/status?path=${encodeURIComponent(this.statusPath)}`
            );
            const status = await response.json();

            if (status.state === "success") {
                clearInterval(this.statusCheckInterval);
                this.pdfPath = status.pdf;
                document.getElementById("statusPDF").textContent = "✓ Ready";
                this.showDownloadOption();
                this.loadPdfPreview();
            }
        } catch (error) {
            console.error("Status check error:", error);
        }
    }

    download() {
        if (!this.pdfPath) return;

        const link = document.createElement("a");
        link.href = `/api/download?path=${encodeURIComponent(this.pdfPath)}`;
        link.download = "resume.pdf";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    async openGeneratedFolder() {
        if (!this.outputDir) return;

        try {
            const response = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: this.outputDir }),
            });
            const data = await response.json();
            if (!data.success) {
                alert(`Could not open folder: ${data.error || "Unknown error"}`);
            }
        } catch (error) {
            console.error("Open folder error:", error);
            alert("Could not open the generated folder.");
        }
    }

    showError(message) {
        document.getElementById("errorMessage").textContent = message;
    }

    showState(state) {
        // Hide all states
        this.initialState.style.display = "none";
        this.loadingState.style.display = "none";
        this.successState.style.display = "none";
        this.errorState.style.display = "none";

        // Show selected state
        switch (state) {
            case "initial":
                this.initialState.style.display = "flex";
                break;
            case "loading":
                this.showTab("pdf");
                this.loadingState.style.display = "flex";
                break;
            case "success":
                this.showTab("pdf");
                this.successState.style.display = "flex";
                break;
            case "error":
                this.showTab("pdf");
                this.errorState.style.display = "flex";
                break;
        }
    }

    reset() {
        this.contentInput.value = "";
        this.companyNameInput.value = "";
        this.folderNameInput.value = "";
        this.validationDisplay.style.display = "none";
        this.generateBtn.disabled = true;
        this.showState("initial");
        this.statusPath = null;
        this.pdfPath = null;
        this.outputDir = null;
        clearInterval(this.statusCheckInterval);
        this.showTab("parsed");

        // Revoke object URLs to free memory
        const pdfPreview = document.getElementById("pdfPreview");
        if (pdfPreview.src) {
            URL.revokeObjectURL(pdfPreview.src);
            pdfPreview.src = "";
        }
    }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    new ResumeGenerator();
});
