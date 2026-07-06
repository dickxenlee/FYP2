/**
 * workspace.js — Phase 3 Enterprise QA Redesign + Multi-User Collaboration
 *
 * Renders a 6-section professional QA report:
 *   1. Requirement Analysis
 *   2. Test Conditions        (description editable)
 *   3. Quality Assessment     (strengths / warnings editable)
 *   4. Requirement Review Findings (description / clarification editable)
 *   5. Traceable Test Scenarios    (description / preconditions / expected result editable)
 *   6. Detailed Test Cases (on demand)
 *   7. Team Notes (shared freeform notes, auto-saved)
 */

// ─────────────────────────────────────────────
// DOM References
// ─────────────────────────────────────────────
const requirementsInput = document.getElementById('requirementsInput');
const submitBtn         = document.getElementById('submitBtn');
const chatMessages      = document.getElementById('chatMessages');
const historyList       = document.getElementById('historyList');
const historySearch     = document.getElementById('historySearch');
const sidebar           = document.getElementById('sidebar');
const toggleSidebarBtn  = document.getElementById('toggleSidebar');
const newSessionBtn     = document.getElementById('newSession');
const csrfToken         = document.getElementById('csrfToken').value;
const workspaceId       = (document.getElementById('workspaceId') || {}).value || '';
const canDeleteChats    = ((document.getElementById('canDeleteChats') || {}).value || '1') === '1';

let currentSessionId = null;

// Live-refresh state for the open session's content.
let lastContentSig    = null;   // signature of what's currently rendered
let myLastEditAt      = 0;      // timestamp of my own last edit (suppress self-toast)
let detailedGenerating = false; // true while I'm generating detailed cases


// ─────────────────────────────────────────────
// Sidebar controls
// ─────────────────────────────────────────────
toggleSidebarBtn.addEventListener('click', function () {
    sidebar.classList.toggle('collapsed');
});

newSessionBtn.addEventListener('click', function () {
    clearChat();
    requirementsInput.value = '';
    currentSessionId = null;
    document.querySelectorAll('.history-item').forEach(function (el) {
        el.classList.remove('active');
    });
});


// ─────────────────────────────────────────────
// History search
// ─────────────────────────────────────────────
historySearch.addEventListener('input', function () {
    var query = this.value.toLowerCase();
    document.querySelectorAll('.history-item').forEach(function (item) {
        var title = item.querySelector('.history-title').textContent.toLowerCase();
        item.style.display = title.includes(query) ? '' : 'none';
    });
});


// ─────────────────────────────────────────────
// History list — three-dot menu, rename, delete, pin, load
// ─────────────────────────────────────────────
document.addEventListener('click', function () {
    document.querySelectorAll('.item-menu.open').forEach(function (m) {
        m.classList.remove('open');
    });
});

historyList.addEventListener('click', function (e) {
    if (e.target.closest('.btn-item-menu')) {
        e.stopPropagation();
        var menu = e.target.closest('.item-menu');
        var isOpen = menu.classList.contains('open');
        document.querySelectorAll('.item-menu.open').forEach(function (m) { m.classList.remove('open'); });
        if (!isOpen) menu.classList.add('open');
        return;
    }

    if (e.target.closest('.btn-pin-item')) {
        e.stopPropagation();
        var item = e.target.closest('.history-item');
        item.querySelector('.item-menu').classList.remove('open');
        handleTogglePin(parseInt(item.dataset.sessionId), item);
        return;
    }

    if (e.target.closest('.btn-rename-item')) {
        e.stopPropagation();
        var item = e.target.closest('.history-item');
        item.querySelector('.item-menu').classList.remove('open');
        startInlineRename(item);
        return;
    }

    if (e.target.closest('.btn-delete-item')) {
        e.stopPropagation();
        var item = e.target.closest('.history-item');
        item.querySelector('.item-menu').classList.remove('open');
        if (!confirm('Delete this chat? This cannot be undone.')) return;
        handleDeleteItem(parseInt(item.dataset.sessionId), item);
        return;
    }

    var item = e.target.closest('.history-item');
    if (!item) return;
    var sessionId = item.dataset.sessionId;
    if (!sessionId) return;
    document.querySelectorAll('.history-item').forEach(function (el) { el.classList.remove('active'); });
    item.classList.add('active');
    loadSession(sessionId);
});

function loadSession(sessionId) {
    fetch('/workspace/session/' + sessionId + '/')
        .then(function (res) { return res.json(); })
        .then(function (data) {
            clearChat();
            currentSessionId = data.session_id;
            appendUserMessage(data.requirements_text);
            appendAnalysisResult(data, true);  // saved session — show scenarios right away
        })
        .catch(function (err) { console.error('Failed to load session:', err); });
}


// ─────────────────────────────────────────────
// Submit / command router
// ─────────────────────────────────────────────
submitBtn.addEventListener('click', handleSubmit);

requirementsInput.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit();
});

function handleSubmit() {
    var text = requirementsInput.value.trim();
    if (!text) return;

    if (text === '/delete_history') {
        requirementsInput.value = '';
        handleDeleteHistory();
        return;
    }

    var renameCmdPrefix = 'rename chat to:';
    if (text.toLowerCase().startsWith(renameCmdPrefix)) {
        var newTitle = text.substring(renameCmdPrefix.length).trim();
        requirementsInput.value = '';
        if (!currentSessionId) { appendErrorMessage('No active session to rename.'); return; }
        var activeItem = historyList.querySelector('.history-item[data-session-id="' + currentSessionId + '"]');
        handleRenameChat(currentSessionId, newTitle, activeItem);
        return;
    }

    if (text === '/delete_current_chat') {
        requirementsInput.value = '';
        if (!currentSessionId) { appendErrorMessage('No active session to delete.'); return; }
        if (!confirm('Delete this chat? This cannot be undone.')) return;
        var activeItem = historyList.querySelector('.history-item[data-session-id="' + currentSessionId + '"]');
        handleDeleteItem(currentSessionId, activeItem);
        return;
    }

    // Regular analysis
    submitBtn.disabled = true;
    requirementsInput.disabled = true;

    var welcomeMsg = document.getElementById('welcomeMsg');
    if (welcomeMsg) welcomeMsg.remove();

    appendUserMessage(text);
    var loadingEl = appendLoading();

    var body = { requirements_text: text };
    if (workspaceId) body.workspace_id = workspaceId;

    fetch('/analyze/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(body),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('The server took too long or is waking up (free hosting sleeps after inactivity). Please wait about 30 seconds and try again.');
        }
        if (!res.ok) return res.json().then(function (err) { throw new Error(err.error || 'Server error'); });
        return res.json();
    })
    .then(function (data) {
        loadingEl.remove();
        requirementsInput.value = '';

        if (data.requires_user_decision && data.suggested_requirement) {
            appendSuggestionConfirmBox(data);
        } else {
            currentSessionId = data.session_id;
            addSessionToHistory(data);
            appendAnalysisResult(data);
        }
    })
    .catch(function (err) {
        loadingEl.remove();
        appendErrorMessage('Error: ' + err.message);
    })
    .finally(function () {
        submitBtn.disabled = false;
        requirementsInput.disabled = false;
        requirementsInput.focus();
    });
}


// ─────────────────────────────────────────────
// Delete all history
// ─────────────────────────────────────────────
function handleDeleteHistory() {
    var body = workspaceId ? { workspace_id: workspaceId } : {};
    fetch('/delete_history/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(body),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('Your session may have expired. Please refresh the page and sign in again.');
        }
        return res.json();
    })
    .then(function (data) {
        if (data.error) { appendErrorMessage(data.error); return; }
        historyList.innerHTML = '<li class="history-empty" id="historyEmpty">No history yet.</li>';
        clearChat();
        currentSessionId = null;
        showToast(data.message, 'success');
    })
    .catch(function (err) { appendErrorMessage('Error clearing history: ' + err.message); });
}


// ─────────────────────────────────────────────
// Pin / rename / delete individual chat item
// ─────────────────────────────────────────────
function handleTogglePin(sessionId, itemEl) {
    fetch('/toggle_pin/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.system_action !== 'chat_pinned') return;
        var isPinned = data.chat_metadata.is_pinned;
        itemEl.dataset.pinned = isPinned ? 'true' : 'false';
        itemEl.classList.toggle('pinned', isPinned);
        itemEl.querySelector('.btn-pin-item').innerHTML = '&#128204;&nbsp; ' + (isPinned ? 'Unpin' : 'Pin');
        var titleSpan = itemEl.querySelector('.history-title');
        var existingIcon = titleSpan.querySelector('.pin-indicator');
        if (isPinned && !existingIcon) {
            var icon = document.createElement('span');
            icon.className = 'pin-indicator';
            icon.innerHTML = '&#128204;';
            titleSpan.insertBefore(icon, titleSpan.firstChild);
        } else if (!isPinned && existingIcon) {
            existingIcon.remove();
        }
        if (isPinned) {
            historyList.insertBefore(itemEl, historyList.firstChild);
        } else {
            var lastPinned = getLastPinnedItem();
            if (lastPinned) lastPinned.after(itemEl);
            else historyList.insertBefore(itemEl, historyList.firstChild);
        }
    })
    .catch(function (err) { appendErrorMessage('Error toggling pin: ' + err.message); });
}

function getLastPinnedItem() {
    var pinned = historyList.querySelectorAll('.history-item.pinned');
    return pinned.length > 0 ? pinned[pinned.length - 1] : null;
}

function startInlineRename(item) {
    var titleSpan = item.querySelector('.history-title');
    var originalTitle = titleSpan.textContent.trim();
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'history-title-input';
    input.value = originalTitle;
    titleSpan.replaceWith(input);
    input.focus();
    input.select();
    var done = false;
    function finish(save) {
        if (done) return;
        done = true;
        var newTitle = input.value.trim();
        var newSpan = document.createElement('span');
        newSpan.className = 'history-title';
        if (save && newTitle && newTitle !== originalTitle) {
            newSpan.textContent = newTitle;
            input.replaceWith(newSpan);
            handleRenameChat(parseInt(item.dataset.sessionId), newTitle, item);
        } else {
            newSpan.textContent = originalTitle;
            input.replaceWith(newSpan);
        }
    }
    input.addEventListener('blur', function () { finish(true); });
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter')  { e.preventDefault(); finish(true); }
        if (e.key === 'Escape') { e.preventDefault(); finish(false); }
    });
}

function handleRenameChat(sessionId, newTitle, itemEl) {
    if (!newTitle) return;
    fetch('/rename_chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId, new_title: newTitle }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.system_action !== 'chat_renamed') return;
        if (itemEl) itemEl.querySelector('.history-title').textContent = data.chat_title;
        showToast('Renamed to: ' + data.chat_title, 'success');
    })
    .catch(function (err) { appendErrorMessage('Error renaming: ' + err.message); });
}

function handleDeleteItem(sessionId, itemEl) {
    fetch('/delete_current_chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId }),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('Your session may have expired. Please refresh the page and sign in again.');
        }
        return res.json();
    })
    .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        if (data.system_action !== 'chat_deleted') return;
        if (itemEl) itemEl.remove();
        if (historyList.querySelectorAll('.history-item').length === 0) {
            historyList.innerHTML = '<li class="history-empty" id="historyEmpty">No history yet.</li>';
        }
        if (currentSessionId == data.session_id) {
            clearChat();
            currentSessionId = null;
        }
        showToast('Chat deleted', 'success');
    })
    .catch(function (err) { appendErrorMessage('Error deleting: ' + err.message); });
}


// ─────────────────────────────────────────────
// Suggestion confirm box
// ─────────────────────────────────────────────
function appendSuggestionConfirmBox(data) {
    var block = document.createElement('div');
    block.className = 'response-block';
    var suggestedText = data.suggested_requirement;
    var html = '<div class="suggestion-box">';
    html += '<div class="suggestion-title">&#9650; Improve Your Requirement</div>';
    html += '<p class="suggestion-label">The requirement looks weak, so its quality score is low. Here is an improved version &mdash; you can edit it or add more details before generating.</p>';
    html += '<textarea class="suggestion-edit" rows="6">' + escapeHtml(suggestedText) + '</textarea>';
    html += '<div class="suggestion-hint">Tip: add any missing rules, limits, or error handling to raise the quality.</div>';
    html += '<div class="decision-buttons">';
    html += '<button class="btn-decision btn-yes">&#10003;&nbsp; Generate with this requirement</button>';
    html += '<button class="btn-decision btn-no">&#10007;&nbsp; Use my original input</button>';
    html += '</div></div>';
    block.innerHTML = html;
    chatMessages.appendChild(block);
    scrollToBottom();

    var editArea = block.querySelector('.suggestion-edit');
    block.querySelector('.btn-yes').addEventListener('click', function () {
        var edited = (editArea.value || '').trim();
        if (!edited) { showToast('Please enter a requirement first.', 'error'); return; }
        block.querySelectorAll('button, textarea').forEach(function (el) { el.disabled = true; });
        handleGenerateFromEdited(edited, block);
    });
    block.querySelector('.btn-no').addEventListener('click', function () {
        block.querySelectorAll('button, textarea').forEach(function (el) { el.disabled = true; });
        block.querySelector('.decision-buttons').innerHTML = '<span class="decision-confirmed">&#10007; Using your original input</span>';
        handleGenerateFromOriginal(data.session_id);
    });
}

// Scenarios are not generated for weak input until the user decides,
// so "use my original input" asks the server to generate them now.
function handleGenerateFromOriginal(sessionId) {
    var loadingEl = appendLoading();
    loadingEl.querySelector('span').textContent = 'Generating test scenarios for your original input…';

    fetch('/analyze/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ keep_session_id: sessionId }),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('The server took too long or is waking up (free hosting sleeps after inactivity). Please wait about 30 seconds and try again.');
        }
        if (!res.ok) return res.json().then(function (err) { throw new Error(err.error || 'Server error'); });
        return res.json();
    })
    .then(function (data) {
        loadingEl.remove();
        currentSessionId = data.session_id;
        addSessionToHistory(data);
        appendAnalysisResult(data);
    })
    .catch(function (err) {
        loadingEl.remove();
        appendErrorMessage('Error: ' + err.message);
    });
}

function handleGenerateFromEdited(editedText, suggestionBlock) {
    suggestionBlock.querySelectorAll('button, textarea').forEach(function (el) { el.disabled = true; });
    appendUserMessage(editedText);
    var loadingEl = appendLoading();
    loadingEl.querySelector('span').textContent = 'Regenerating QA report from edited requirement…';

    var body = { requirements_text: 'EDITED: ' + editedText };
    if (workspaceId) body.workspace_id = workspaceId;

    fetch('/analyze/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(body),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('The server took too long or is waking up (free hosting sleeps after inactivity). Please wait about 30 seconds and try again.');
        }
        if (!res.ok) return res.json().then(function (err) { throw new Error(err.error || 'Server error'); });
        return res.json();
    })
    .then(function (data) {
        loadingEl.remove();
        currentSessionId = data.session_id;
        addSessionToHistory(data);
        appendAnalysisResult(data);
    })
    .catch(function (err) {
        loadingEl.remove();
        appendErrorMessage('Error: ' + err.message);
        suggestionBlock.querySelectorAll('button, textarea').forEach(function (el) { el.disabled = false; });
    });
}


// ═════════════════════════════════════════════
// QA Report — 6-section renderer
// ═════════════════════════════════════════════

function appendAnalysisResult(data, revealScenarios) {
    var block = document.createElement('div');
    block.className = 'qa-report';
    if (data.session_id) block.dataset.sessionId = data.session_id;
    populateReport(block, data, revealScenarios);
    chatMessages.appendChild(block);
    scrollToBottom();
    lastContentSig = contentSignature(data);
}

// Build the report HTML into `block` and wire up all of its handlers.
// Shared by the first render and the live teammate-edit refresh, so a
// re-render restores every button, checkbox, and editable cell.
function populateReport(block, data, revealScenarios) {
    // Staged QA flow: show the quality review, findings, requirement analysis
    // and test conditions first; the traceable test scenarios stay behind a
    // "Generate Test Scenarios" gate until the reviewer is ready. Opening an
    // already-saved session reveals the scenarios right away.
    var hasScenarios = data.scenarios && data.scenarios.length > 0;
    var reveal = revealScenarios || block.dataset.scenariosRevealed === '1';

    var html = '';

    // 1. Requirement Quality Assessment
    if (data.quality_assessment) {
        html += buildQualityAssessmentSection(data.quality_assessment);
    }
    // 2. Requirement Review Findings
    if (data.gaps && data.gaps.length > 0) {
        html += buildGapsSection(data.gaps);
    }
    // 3. Requirement Analysis
    if (data.requirements && data.requirements.length > 0) {
        html += buildRequirementsSection(data.requirements);
    }
    // 4. Test Conditions
    if (data.test_conditions && data.test_conditions.length > 0) {
        html += buildTestConditionsSection(data.test_conditions);
    }

    // 5. Traceable Test Scenarios (+ 6. Detailed Test Cases) — behind the gate.
    if (hasScenarios && !reveal) {
        html += buildScenarioGateHtml();
    } else if (hasScenarios) {
        html += buildTestScenariosSection(data.scenarios);
        html += buildDetailedSectionHtml(data);
        block.dataset.scenariosRevealed = '1';
    }

    // Team Notes (collaborative freeform notes) — only inside a Team Workspace,
    // not in personal/normal chats.
    if (data.session_id && workspaceId) {
        html += '<div class="qa-section">';
        html += '<div class="qa-section-header"><span class="section-num">&#128221;</span>Team Notes</div>';
        html += '<div style="padding:0.8rem 1rem;">';
        html += '<textarea class="team-notes-area" data-session-id="' + data.session_id + '" placeholder="Add team notes, observations, or review decisions here…" rows="4">' + escapeHtml(data.team_notes || '') + '</textarea>';
        html += '<div class="notes-save-hint">Auto-saved when you click outside the box.</div>';
        html += '</div></div>';
    }

    // Export bar
    if (data.session_id) {
        html += buildExportBarHtml(data.session_id);
    }

    block.innerHTML = html;

    // Scenario gate — reveal the traceable scenarios (and detailed cases) on click.
    var genScenariosBtn = block.querySelector('.btn-generate-scenarios');
    if (genScenariosBtn) {
        genScenariosBtn.addEventListener('click', function () {
            block.dataset.scenariosRevealed = '1';
            populateReport(block, data, true);
            scrollToBottom();
        });
    }

    // Section 6 button + any already-saved detailed cases (with per-step checkboxes)
    var detailBtn = block.querySelector('.btn-generate-detailed');
    if (detailBtn) {
        detailBtn.addEventListener('click', function () {
            handleGenerateDetailedCases(data.session_id, block);
        });
    }
    if (data.detailed_cases && data.detailed_cases.length > 0) {
        var dContainer = block.querySelector('.detailed-cases-container');
        if (dContainer) {
            dContainer.innerHTML = buildDetailedCasesHtml(data.detailed_cases);
            attachDetailedStepHandlers(dContainer);
        }
        if (detailBtn) detailBtn.innerHTML = '&#8635;&nbsp; Regenerate Detailed Test Cases';
    }

    // Re-analyze button
    var reanalyzeBtn = block.querySelector('.btn-reanalyze');
    if (reanalyzeBtn) {
        reanalyzeBtn.addEventListener('click', function () {
            handleReanalyze(parseInt(reanalyzeBtn.dataset.sessionId));
        });
    }

    // Team notes auto-save
    var notesArea = block.querySelector('.team-notes-area');
    if (notesArea) {
        notesArea.addEventListener('blur', function () {
            saveTeamNotes(parseInt(notesArea.dataset.sessionId), notesArea.value);
        });
    }

    // Editable output fields
    attachEditableHandlers(block);

    // Scenario "done" checkboxes
    attachScenarioDoneHandlers(block);
}

// A short fingerprint of the open session's editable content. Two renders with
// the same signature are visually identical, so we only re-render when it
// changes — avoiding a needless redraw every poll tick. Team notes are excluded
// (they have their own in-place poll) so notes edits don't trigger a full redraw.
function contentSignature(data) {
    try {
        var p = [];
        (data.requirements || []).forEach(function (r) {
            p.push(r.requirement_id, r.clarity_score, r.completeness_score, r.testability_score);
        });
        var qa = data.quality_assessment || {};
        p.push(qa.clarity_score, qa.completeness_score, qa.testability_score, qa.overall_score);
        (qa.positive_aspects || []).forEach(function (f) { p.push('s', f.text != null ? f.text : f); });
        (qa.warnings || []).forEach(function (f) { p.push('w', f.text != null ? f.text : f); });
        (data.test_conditions || []).forEach(function (c) { p.push(c.db_id, c.description, c.type, c.priority); });
        (data.gaps || []).forEach(function (g) { p.push(g.db_id, g.description, g.suggested_clarification); });
        (data.scenarios || []).forEach(function (s) {
            p.push(s.db_id, s.description, s.preconditions, s.expected_result, s.priority, s.is_done ? 1 : 0);
        });
        (data.detailed_cases || []).forEach(function (dc) { p.push('d', dc.db_id, (dc.steps_done || []).join(',')); });
        return p.join('|');
    } catch (e) {
        return String(Math.random());  // on any oddity, force a refresh
    }
}

// Re-render the open report in place, keeping the user's scroll position.
function refreshReportBlock(block, data) {
    var prevScroll = chatMessages.scrollTop;
    populateReport(block, data);
    chatMessages.scrollTop = prevScroll;
}

// Poll the open session and re-render it when a teammate changed its content.
// Skips entirely while you are editing inside it or while something is loading,
// so it never interrupts your own work.
function pollSessionContent() {
    if (!workspaceId || !currentSessionId || document.hidden) return;
    if (detailedGenerating) return;
    if (chatMessages.querySelector('.loading-block')) return;  // a generation is in flight

    var block = chatMessages.querySelector('.qa-report[data-session-id="' + currentSessionId + '"]');
    if (!block) return;
    if (block.contains(document.activeElement)) return;        // you are editing — don't touch

    fetch('/workspace/session/' + currentSessionId + '/')
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data) return;
            var sig = contentSignature(data);
            if (sig === lastContentSig) return;                // nothing changed
            refreshReportBlock(block, data);
            lastContentSig = sig;
            // Only announce when it wasn't my own recent edit echoing back.
            if (Date.now() - myLastEditAt > 10000) {
                showToast('Updated with teammate changes', 'info');
            }
        })
        .catch(function () { /* transient error — retry next tick */ });
}


// ── Section builders ──────────────────────────

function buildRequirementsSection(requirements) {
    var fields = [
        { label: 'Actors',                      key: 'actors' },
        { label: 'Actions',                     key: 'actions' },
        { label: 'Business Rules',              key: 'business_rules' },
        { label: 'Constraints',                 key: 'constraints' },
        { label: 'Validation Rules',            key: 'validation_rules' },
        { label: 'Error Handling',              key: 'error_handling' },
        { label: 'Non-Functional Requirements', key: 'non_functional' },
    ];
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">3</span>Requirement Analysis';
    if (requirements.length > 1) {
        html += '<span class="edit-hint">' + requirements.length + ' requirements found</span>';
    }
    html += '</div>';

    requirements.forEach(function (info) {
        html += '<div class="req-block">';
        html += '<div style="padding:0.8rem 1rem 0.2rem;">';
        html += '<span class="req-id-badge">&#128196;&nbsp; ' + escapeHtml(info.requirement_id || 'REQ-001') + '</span>';
        if (info.title) html += ' <span class="req-title">' + escapeHtml(info.title) + '</span>';
        if (typeof info.overall_score === 'number') {
            var sevCls = (info.severity || 'Medium').toLowerCase();
            html += '<div class="req-scores">Clarity ' + info.clarity_score + '% &middot; Completeness ' +
                info.completeness_score + '% &middot; Testability ' + info.testability_score +
                '% &middot; <strong>Overall ' + info.overall_score + '%</strong> ' +
                '<span class="req-sev req-sev-' + sevCls + '">' + escapeHtml(info.severity || 'Medium') + '</span></div>';
        }
        html += '</div><div class="req-info-grid">';
        fields.forEach(function (field) {
            var items = info[field.key] || [];
            if (items.length === 0) return;
            html += '<div class="req-info-row">';
            html += '<div class="req-info-label">' + field.label + '</div>';
            html += '<ul class="req-info-list">';
            items.forEach(function (item) {
                html += '<li>' + escapeHtml(String(item)) + '</li>';
            });
            html += '</ul></div>';
        });
        html += '</div></div>';
    });

    html += '</div>';
    return html;
}

function buildTestConditionsSection(conditions) {
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">4</span>Test Conditions';
    html += '<span class="edit-hint">&#9998; click a cell to edit</span></div>';
    html += '<div class="qa-table-wrapper"><table class="qa-table"><thead><tr>';
    html += '<th>Condition ID</th><th>Req</th><th>Test Condition</th><th>Type</th><th>Priority</th>';
    html += '</tr></thead><tbody>';

    conditions.forEach(function (c) {
        var typeSlug = (c.type || 'positive').toLowerCase().replace(/\s+/g, '');
        var priSlug  = (c.priority || 'medium').toLowerCase();
        var dbId     = c.db_id || '';
        html += '<tr>';
        html += '<td><strong>' + escapeHtml(c.condition_id) + '</strong></td>';
        html += '<td><span class="qa-badge badge-ref">' + escapeHtml(c.requirement_ref || '') + '</span></td>';
        html += '<td class="editable-item" contenteditable="true" data-model="condition" data-db-id="' + dbId + '" data-field="description">' + escapeHtml(c.description) + '</td>';
        html += '<td><span class="qa-badge badge-type-' + typeSlug + '">' + escapeHtml(c.type) + '</span></td>';
        html += '<td><span class="qa-badge badge-priority-' + priSlug + '">' + escapeHtml(c.priority) + '</span></td>';
        html += '</tr>';
    });

    html += '</tbody></table></div></div>';
    return html;
}

function buildQualityAssessmentSection(qa) {
    var sevSlug = (qa.severity || 'medium').toLowerCase();

    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header">';
    html += '<span class="section-num">1</span>Requirement Quality Assessment';
    html += '<span class="severity-badge severity-' + sevSlug + '">' + escapeHtml(qa.severity || 'Medium') + ' Severity</span>';
    html += '<span class="edit-hint">&#9998; click text to edit</span>';
    html += '</div>';

    html += '<div class="score-cards">';
    html += buildScoreCard('Clarity',       qa.clarity_score,       false);
    html += buildScoreCard('Completeness',  qa.completeness_score,  false);
    html += buildScoreCard('Testability',   qa.testability_score,   false);
    html += buildScoreCard('Overall',       qa.overall_score,       true);
    html += '</div>';

    if (qa.positive_aspects && qa.positive_aspects.length > 0) {
        html += '<div class="qa-findings positive-findings">';
        html += '<div class="findings-label">&#10004;&nbsp; Strengths</div><ul>';
        qa.positive_aspects.forEach(function (a) {
            var text  = (typeof a === 'object') ? a.text : a;
            var dbId  = (typeof a === 'object' && a.db_id) ? a.db_id : '';
            html += '<li class="editable-item" contenteditable="true" data-model="feedback" data-db-id="' + dbId + '" data-field="message">' + escapeHtml(text) + '</li>';
        });
        html += '</ul></div>';
    }

    if (qa.warnings && qa.warnings.length > 0) {
        html += '<div class="qa-findings warning-findings">';
        html += '<div class="findings-label">&#9650;&nbsp; Quality Warnings</div><ul>';
        qa.warnings.forEach(function (w) {
            var text  = (typeof w === 'object') ? w.text : w;
            var dbId  = (typeof w === 'object' && w.db_id) ? w.db_id : '';
            html += '<li class="editable-item" contenteditable="true" data-model="feedback" data-db-id="' + dbId + '" data-field="message">' + escapeHtml(text) + '</li>';
        });
        html += '</ul></div>';
    }

    html += '</div>';
    return html;
}

function buildScoreCard(label, score, isOverall) {
    var s = score || 0;
    var color = s >= 80 ? '#27ae60' : s >= 60 ? '#f39c12' : '#e74c3c';
    var cls = isOverall ? 'score-card score-card-overall' : 'score-card';
    return '<div class="' + cls + '">' +
        '<div class="score-label">' + label + '</div>' +
        '<div class="score-value" style="color:' + (isOverall ? 'white' : color) + '">' + s + '%</div>' +
        '<div class="score-bar-track">' +
        '<div class="score-bar-fill" style="width:' + s + '%;background:' + (isOverall ? 'rgba(255,255,255,0.85)' : color) + '"></div>' +
        '</div></div>';
}

function buildGapsSection(gaps) {
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">2</span>Requirement Review Findings';
    html += '<span class="edit-hint">&#9998; click a cell to edit</span></div>';
    html += '<div class="qa-table-wrapper"><table class="qa-table"><thead><tr>';
    html += '<th>Issue ID</th><th>Issue Type</th><th>Description</th><th>Suggested Clarification</th>';
    html += '</tr></thead><tbody>';

    gaps.forEach(function (g) {
        var typeSlug = (g.issue_type || '').toLowerCase().replace(/[\s-]+/g, '');
        var dbId     = g.db_id || '';
        html += '<tr>';
        html += '<td><strong>' + escapeHtml(g.issue_id) + '</strong></td>';
        html += '<td><span class="qa-badge badge-issue-' + typeSlug + '">' + escapeHtml(g.issue_type) + '</span></td>';
        html += '<td class="editable-item" contenteditable="true" data-model="gap" data-db-id="' + dbId + '" data-field="description">' + escapeHtml(g.description) + '</td>';
        html += '<td class="editable-item text-muted" contenteditable="true" data-model="gap" data-db-id="' + dbId + '" data-field="suggested_clarification">' + escapeHtml(g.suggested_clarification) + '</td>';
        html += '</tr>';
    });

    html += '</tbody></table></div></div>';
    return html;
}

function buildTestScenariosSection(scenarios) {
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">5</span>Traceable Test Scenarios';
    html += '<span class="edit-hint">&#9998; click a cell to edit &mdash; &#128190; to save row</span></div>';
    html += '<div class="qa-table-wrapper"><table class="qa-table"><thead><tr>';
    html += '<th>ID</th><th>Req</th><th>Cond</th><th>Description</th><th>Preconditions</th><th>Expected Result</th><th>Priority</th><th>Done</th><th></th>';
    html += '</tr></thead><tbody>';

    scenarios.forEach(function (s) {
        var priSlug = (s.priority || 'medium').toLowerCase();
        var dbId    = s.db_id || '';
        var doneCls = s.is_done ? ' scenario-done' : '';

        html += '<tr data-scenario-db-id="' + dbId + '"' + (s.is_done ? ' class="scenario-done-row"' : '') + '>';
        html += '<td><strong>' + escapeHtml(s.id || s.scenario_id || '') + '</strong></td>';
        html += '<td><span class="qa-badge badge-ref">' + escapeHtml(s.requirement_ref || '') + '</span></td>';
        html += '<td><span class="qa-badge badge-ref">' + escapeHtml(s.condition_ref || '') + '</span></td>';
        html += '<td class="editable-item" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="description">' + escapeHtml(s.description) + '</td>';
        html += '<td class="editable-item text-muted" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="preconditions">' + escapeHtml(s.preconditions) + '</td>';
        html += '<td class="editable-item" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="expected_result">' + escapeHtml(s.expected_result) + '</td>';
        html += '<td><span class="qa-badge badge-priority-' + priSlug + '">' + escapeHtml(s.priority || 'Medium') + '</span></td>';
        html += '<td class="done-cell">';
        if (dbId) {
            html += '<input type="checkbox" class="scenario-done-input" data-db-id="' + dbId + '"' + (s.is_done ? ' checked' : '') + ' title="Mark this scenario as done">';
        }
        html += '</td>';
        html += '<td><button class="btn-save-row" data-db-id="' + dbId + '" title="Save this row">&#128190;</button></td>';
        html += '</tr>';
    });

    html += '</tbody></table></div></div>';
    return html;
}


// Gate shown before the traceable scenarios. The reviewer generates them after
// checking the quality, findings, analysis and conditions above.
function buildScenarioGateHtml() {
    var html = '<div class="qa-section scenario-gate-section">';
    html += '<div class="qa-section-header"><span class="section-num">5</span>Traceable Test Scenarios</div>';
    html += '<div class="scenario-gate">';
    html += '<p class="scenario-gate-text">Review the quality assessment, review findings, requirement analysis and test conditions above. When you are ready, generate the traceable test scenarios.</p>';
    html += '<button class="btn-generate-scenarios">&#9889;&nbsp; Generate Test Scenarios</button>';
    html += '</div></div>';
    return html;
}

// Section 6 (Detailed Test Cases) — rendered once the scenarios are revealed.
function buildDetailedSectionHtml(data) {
    if (!(data.session_id && data.scenarios && data.scenarios.length > 0)) return '';
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">6</span>Detailed Test Cases</div>';
    html += '<div style="padding:0.8rem 1rem 0;">';
    html += '<p style="font-size:0.83rem;color:var(--color-muted);margin-bottom:0.6rem;">Expand each scenario into full test data, step-by-step instructions, and postconditions.</p>';
    html += '<button class="btn-generate-detailed">&#9654;&nbsp; Generate Detailed Test Cases</button>';
    html += '</div><div class="detailed-cases-container"></div></div>';
    return html;
}


// ── Section 6: Generate Detailed Test Cases ───

function handleGenerateDetailedCases(sessionId, reportBlock) {
    var btn       = reportBlock.querySelector('.btn-generate-detailed');
    var container = reportBlock.querySelector('.detailed-cases-container');
    if (btn) btn.disabled = true;
    detailedGenerating = true;  // pause the live-refresh poll while we build these
    if (container) container.innerHTML =
        '<p style="padding:0.5rem 1rem;font-size:0.83rem;color:var(--color-muted);">Generating detailed test cases…</p>';

    fetch('/generate_detailed_cases/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId }),
    })
    .then(function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('The server took too long or your session expired. Please wait a moment, refresh if needed, and try again.');
        }
        return res.json();
    })
    .then(function (data) {
        if (data.error) {
            if (container) container.innerHTML =
                '<span style="color:#e74c3c;padding:0.5rem 1rem;display:block;">' + escapeHtml(data.error) + '</span>';
            if (btn) btn.disabled = false;
            return;
        }
        if (container) {
            container.innerHTML = buildDetailedCasesHtml(data.detailed_cases);
            attachDetailedStepHandlers(container);
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '&#8635;&nbsp; Regenerate Detailed Test Cases'; }
        // My own action — let the next poll adopt it quietly (no "teammate" toast).
        myLastEditAt = Date.now();
    })
    .catch(function (err) {
        if (container) container.innerHTML =
            '<span style="color:#e74c3c;padding:0.5rem 1rem;display:block;">Error: ' + escapeHtml(err.message) + '</span>';
        if (btn) btn.disabled = false;
    })
    .finally(function () { detailedGenerating = false; });
}

function buildDetailedCasesHtml(cases) {
    if (!cases || cases.length === 0) return '<p class="text-muted" style="padding:0.5rem 1rem;">No detailed cases generated.</p>';
    return cases.map(function (c) {
        var steps = c.steps || [];
        var done  = c.steps_done || [];
        var doneCount = done.filter(Boolean).length;
        var card = '<div class="detailed-case-card">';
        card += '<div class="detailed-case-id">&#128196;&nbsp; ' + escapeHtml(c.scenario_id);
        if (steps.length > 0) {
            card += ' <span class="step-progress">' + doneCount + '/' + steps.length + ' done</span>';
        }
        card += '</div>';
        if (c.test_data) card += detailRow('Test Data', escapeHtml(c.test_data));
        if (steps.length > 0) {
            var stepsHtml = '<div class="step-list">';
            steps.forEach(function (step, i) {
                var isDone = !!done[i];
                stepsHtml += '<label class="step-check' + (isDone ? ' step-done' : '') + '">' +
                    '<input type="checkbox" class="step-check-input" data-case-id="' + c.db_id +
                    '" data-step-index="' + i + '"' + (isDone ? ' checked' : '') + '>' +
                    '<span>' + (i + 1) + '. ' + escapeHtml(step) + '</span></label>';
            });
            stepsHtml += '</div>';
            card += detailRow('Test Steps', stepsHtml, true);
        }
        if (c.expected_results) card += detailRow('Expected Results', escapeHtml(c.expected_results));
        if (c.postconditions)   card += detailRow('Postconditions',   escapeHtml(c.postconditions));
        card += '</div>';
        return card;
    }).join('');
}

// Per-step "done" checkboxes — saved to the DB and shared with the team.
function attachDetailedStepHandlers(scope) {
    scope.querySelectorAll('.step-check-input').forEach(function (cb) {
        cb.addEventListener('change', function () {
            toggleStepDone(parseInt(cb.dataset.caseId), parseInt(cb.dataset.stepIndex), cb);
        });
    });
}

function toggleStepDone(caseId, stepIndex, cb) {
    fetch('/toggle_step_done/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ case_id: caseId, step_index: stepIndex }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); cb.checked = !cb.checked; return; }
        myLastEditAt = Date.now();
        var label = cb.closest('.step-check');
        if (label) label.classList.toggle('step-done', cb.checked);
        var card = cb.closest('.detailed-case-card');
        var badge = card && card.querySelector('.step-progress');
        if (badge) badge.textContent = data.done_count + '/' + data.total + ' done';
    })
    .catch(function (err) { showToast('Save failed: ' + err.message, 'error'); cb.checked = !cb.checked; });
}

function detailRow(label, content, isHtml) {
    return '<div class="detailed-case-row">' +
        '<div class="detailed-case-label">' + label + '</div>' +
        '<div class="detailed-case-content">' + content + '</div>' +
        '</div>';
}


// ─────────────────────────────────────────────
// Editable output fields — auto-save on blur
// ─────────────────────────────────────────────

function attachEditableHandlers(block) {
    block.querySelectorAll('.editable-item').forEach(function (el) {
        el.dataset.original = el.textContent.trim();

        el.addEventListener('blur', function () {
            var current = el.textContent.trim();
            if (!current || current === el.dataset.original) return;
            var model = el.dataset.model;
            var dbId  = el.dataset.dbId;
            var field = el.dataset.field;
            if (!model || !dbId || !field) return;
            saveOutputField(model, parseInt(dbId), field, current, el)
                .then(function (ok) { if (ok) el.dataset.original = current; });
        });
    });

    // Per-row save buttons (scenario table)
    block.querySelectorAll('.btn-save-row').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var dbId = parseInt(btn.dataset.dbId);
            if (!dbId) return;
            var row = btn.closest('tr');
            btn.disabled = true;
            var promises = [];
            row.querySelectorAll('.editable-item').forEach(function (cell) {
                var current = cell.textContent.trim();
                if (!current) return;
                var p = saveOutputField(cell.dataset.model, parseInt(cell.dataset.dbId), cell.dataset.field, current, cell)
                    .then(function (ok) { if (ok) cell.dataset.original = current; });
                promises.push(p);
            });
            if (promises.length === 0) {
                btn.disabled = false;
                showToast('Nothing changed', 'info');
            } else {
                Promise.all(promises).then(function () {
                    btn.disabled = false;
                    showToast('Scenario saved', 'success');
                });
            }
        });
    });
}

// Returns a Promise that resolves true on success, false on failure (toast already shown).
function saveOutputField(model, dbId, field, value, el) {
    return fetch('/update_output_field/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ model: model, db_id: dbId, field: field, value: value }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return false; }
        myLastEditAt = Date.now();
        if (el) {
            el.classList.add('save-flash');
            setTimeout(function () { el.classList.remove('save-flash'); }, 1200);
        }
        return true;
    })
    .catch(function (err) {
        showToast('Save failed: ' + err.message, 'error');
        return false;
    });
}

function saveTeamNotes(sessionId, notes) {
    fetch('/update_team_notes/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId, notes: notes }),
    })
    .then(function (res) { return res.json(); })
    .then(function () { showToast('Team notes saved', 'success'); })
    .catch(function (err) { showToast('Notes save failed: ' + err.message, 'error'); });
}


// ─────────────────────────────────────────────
// History sidebar helpers
// ─────────────────────────────────────────────
// Build one history sidebar <li>. Shared by the submit flow and live polling.
function buildHistoryItem(sessionId, title, scoreColor, score, active) {
    var li = document.createElement('li');
    li.className = 'history-item' + (active ? ' active' : '');
    li.dataset.sessionId = sessionId;
    var deleteOption = canDeleteChats
        ? '<button class="menu-option btn-delete-item">&#128465;&nbsp; Delete</button>'
        : '';
    li.innerHTML =
        '<span class="history-title">' + escapeHtml(title) + '</span>' +
        '<div class="history-item-right">' +
        '<span class="history-score score-' + scoreColor + '">' + score + '%</span>' +
        '<div class="item-menu">' +
        '<button class="btn-item-menu" title="Options">&#8943;</button>' +
        '<div class="item-menu-dropdown">' +
        '<button class="menu-option btn-pin-item">&#128204;&nbsp; Pin</button>' +
        '<button class="menu-option btn-rename-item">&#9998;&nbsp; Rename</button>' +
        deleteOption +
        '</div></div></div>';
    return li;
}

function addSessionToHistory(data) {
    var emptyMsg = document.getElementById('historyEmpty');
    if (emptyMsg) emptyMsg.remove();
    document.querySelectorAll('.history-item').forEach(function (el) { el.classList.remove('active'); });

    var li = buildHistoryItem(data.session_id, getShortTitle(), data.score_color, data.score, true);
    historyList.insertBefore(li, historyList.firstChild);
}

function getShortTitle() {
    var text = requirementsInput.value
        || (document.querySelector('.message-bubble') && document.querySelector('.message-bubble').textContent)
        || 'Analysis';
    return text.substring(0, 28);
}


// ─────────────────────────────────────────────
// Export + Re-analyze bar
// ─────────────────────────────────────────────
function buildExportBarHtml(sessionId) {
    return '<div class="export-bar">' +
        '<span>Export:</span>' +
        '<button class="btn-export btn-pdf" onclick="exportFile(' + sessionId + ', \'pdf\')">PDF</button>' +
        '<button class="btn-export btn-excel" onclick="exportFile(' + sessionId + ', \'excel\')">Excel</button>' +
        '<button class="btn-export btn-reanalyze" data-session-id="' + sessionId + '">&#8635; Re-analyze</button>' +
        '</div>';
}

function exportFile(sessionId, format) {
    var urls = {
        pdf:   '/export/pdf/' + sessionId + '/',
        excel: '/export/excel/' + sessionId + '/',
    };
    window.location.href = urls[format];
}

function handleReanalyze(sessionId) {
    var loadingEl = appendLoading();
    loadingEl.querySelector('span').textContent = 'Re-analyzing requirement…';

    fetch('/reanalyze/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId }),
    })
    .then(function (res) {
        if (!res.ok) return res.json().then(function (e) { throw new Error(e.error || 'Server error'); });
        return res.json();
    })
    .then(function (data) {
        loadingEl.remove();
        currentSessionId = data.session_id;
        appendAnalysisResult(data);
        var sidebarItem = historyList.querySelector('.history-item[data-session-id="' + data.session_id + '"]');
        if (sidebarItem) {
            var badge = sidebarItem.querySelector('.history-score');
            if (badge) {
                badge.textContent = data.score + '%';
                badge.className = 'history-score score-' + data.score_color;
            }
        }
        showToast('Re-analysis complete', 'success');
    })
    .catch(function (err) {
        loadingEl.remove();
        appendErrorMessage('Re-analysis failed: ' + err.message);
    });
}


// ─────────────────────────────────────────────
// Scenario "done" checkboxes — saved to the DB and shared with the team
// ─────────────────────────────────────────────
function attachScenarioDoneHandlers(block) {
    block.querySelectorAll('.scenario-done-input').forEach(function (cb) {
        cb.addEventListener('change', function () {
            var dbId = parseInt(cb.dataset.dbId);
            if (!dbId) return;
            toggleScenarioDone(dbId, cb);
        });
    });
}

function toggleScenarioDone(dbId, cb) {
    fetch('/toggle_scenario_done/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ db_id: dbId }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); cb.checked = !cb.checked; return; }
        myLastEditAt = Date.now();
        var row = cb.closest('tr');
        if (row) row.classList.toggle('scenario-done-row', data.is_done);
        showToast(data.is_done ? 'Marked done' : 'Marked not done', 'info');
    })
    .catch(function (err) { showToast('Save failed: ' + err.message, 'error'); cb.checked = !cb.checked; });
}



// ─────────────────────────────────────────────
// Toast notifications
// ─────────────────────────────────────────────
function showToast(message, type) {
    var container = document.getElementById('toastContainer');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + (type || 'info');
    var icon = type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ';
    toast.innerHTML = '<span class="toast-icon">' + icon + '</span><span>' + escapeHtml(message) + '</span>';
    container.appendChild(toast);
    setTimeout(function () {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
}


// ─────────────────────────────────────────────
// Shared UI helpers
// ─────────────────────────────────────────────
function clearChat() { chatMessages.innerHTML = ''; }

function appendUserMessage(text) {
    var div = document.createElement('div');
    div.className = 'message-bubble';
    div.textContent = text;
    chatMessages.appendChild(div);
    scrollToBottom();
}

function appendLoading() {
    var div = document.createElement('div');
    div.className = 'loading-block';
    div.innerHTML = '<div class="spinner"></div><span>Analyzing requirements…</span>';
    chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function appendErrorMessage(message) {
    var div = document.createElement('div');
    div.className = 'response-block';
    div.innerHTML = '<span style="color:#e74c3c;">&#9888; ' + escapeHtml(message) + '</span>';
    chatMessages.appendChild(div);
    scrollToBottom();
}

function scrollToBottom() { chatMessages.scrollTop = chatMessages.scrollHeight; }

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text)));
    return div.innerHTML;
}


// ─────────────────────────────────────────────
// Live workspace auto-refresh (polling)
// Only runs inside a Team Workspace. Updates the sidebar history list and the
// member count without disturbing the open chat, the active item, or typing.
// ─────────────────────────────────────────────
function pollWorkspaceState() {
    if (!workspaceId || document.hidden) return;

    fetch('/workspace/' + workspaceId + '/state/')
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data) return;

            // 1. Insert any sessions that aren't already in the sidebar.
            if (data.sessions && data.sessions.length) {
                var emptyMsg = document.getElementById('historyEmpty');
                if (emptyMsg) emptyMsg.remove();
                // Walk newest-last so insertBefore(first) keeps server order on top.
                for (var i = data.sessions.length - 1; i >= 0; i--) {
                    var s = data.sessions[i];
                    if (historyList.querySelector('.history-item[data-session-id="' + s.id + '"]')) {
                        continue; // already shown
                    }
                    var li = buildHistoryItem(s.id, s.title, s.color, s.score, false);
                    if (s.pinned) {
                        li.dataset.pinned = 'true';
                        li.classList.add('pinned');
                        historyList.insertBefore(li, historyList.firstChild);
                    } else {
                        // Keep sidebar order (-is_pinned, -created_at): a new
                        // unpinned session goes below pinned items, not above them.
                        var lastPinned = getLastPinnedItem();
                        if (lastPinned) lastPinned.after(li);
                        else historyList.insertBefore(li, historyList.firstChild);
                    }
                }
            }

            // 1b. Reconcile existing rows against the server: refresh each score,
            // and remove any session a teammate deleted (so it can't linger or be
            // clicked into a 404). A row being renamed inline is left untouched.
            var serverById = {};
            (data.sessions || []).forEach(function (s) { serverById[String(s.id)] = s; });
            historyList.querySelectorAll('.history-item').forEach(function (item) {
                var s = serverById[String(item.dataset.sessionId)];
                if (!s) {
                    if (String(currentSessionId) === String(item.dataset.sessionId)) {
                        clearChat();
                        currentSessionId = null;
                    }
                    item.remove();
                    return;
                }
                if (item.querySelector('.history-title-input')) return;  // mid-rename
                var badge = item.querySelector('.history-score');
                if (badge && badge.textContent !== s.score + '%') {
                    badge.textContent = s.score + '%';
                    badge.className = 'history-score score-' + s.color;
                }
            });
            if (!historyList.querySelector('.history-item') && !document.getElementById('historyEmpty')) {
                historyList.innerHTML = '<li class="history-empty" id="historyEmpty">No history yet.</li>';
            }

            // 2. Refresh the member list/count in the collaboration bar.
            var membersEl = document.querySelector('.collab-bar .ws-members');
            if (membersEl && data.members) {
                var plural = data.member_count === 1 ? '' : 's';
                membersEl.innerHTML = '&#128101; ' + data.member_count +
                    ' member' + plural + ': ' + data.members.map(escapeHtml).join(', ');
            }
        })
        .catch(function () { /* transient network error — ignore, try again next tick */ });
}

// ─────────────────────────────────────────────
// Live "My Team Workspaces" sidebar list
// Rebuilds the list so newly created/joined workspaces and changing member
// counts appear without a page reload. Runs in both personal and workspace views.
// ─────────────────────────────────────────────
function buildWsListItem(ws) {
    var li = document.createElement('li');
    li.className = 'ws-list-item' + (ws.workspace_id === workspaceId ? ' active' : '');
    var name = ws.name.length > 20 ? ws.name.substring(0, 20) + '…' : ws.name;
    li.innerHTML =
        '<a href="/workspace/' + encodeURIComponent(ws.workspace_id) + '/">' +
        '<span class="ws-list-icon">&#127962;</span>' +
        '<span class="ws-list-name">' + escapeHtml(name) + '</span>' +
        '<span class="ws-list-members">&#128101; ' + ws.member_count + '</span>' +
        '<span class="ws-list-badge">' + escapeHtml(ws.workspace_id) + '</span>' +
        '</a>';
    return li;
}

function pollMyWorkspaces() {
    if (document.hidden) return;

    fetch('/workspaces/state/')
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data || !data.workspaces) return;
            var list = document.getElementById('myWorkspacesList');
            if (!list) return;

            list.innerHTML = '';
            if (data.workspaces.length === 0) {
                list.innerHTML = '<li class="ws-empty">No team workspaces yet.</li>';
                return;
            }
            data.workspaces.forEach(function (ws) {
                list.appendChild(buildWsListItem(ws));
            });
        })
        .catch(function () { /* transient network error — ignore, retry next tick */ });
}

// Live-refresh the open session's team notes so a teammate's edits appear
// without a reload. Skips while you are typing in the box (so it never
// overwrites your own unsaved text).
function pollTeamNotes() {
    if (!workspaceId || !currentSessionId || document.hidden) return;
    var area = document.querySelector('.team-notes-area[data-session-id="' + currentSessionId + '"]');
    if (!area || area === document.activeElement) return;

    fetch('/session/' + currentSessionId + '/notes/')
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data) return;
            var incoming = data.team_notes || '';
            if (incoming !== area.value && area !== document.activeElement) {
                area.value = incoming;
            }
        })
        .catch(function () { /* transient error — try again next tick */ });
}

// ─────────────────────────────────────────────
// Team input draft — members contribute, owner generates
// Members type into their own box (auto-saved); everyone's text shows in a
// combined preview color-coded by author. Only the owner sees Generate.
// ─────────────────────────────────────────────
var DRAFT_COLORS = ['#5dade2', '#e67e22', '#2ecc71', '#af7ac5', '#ec7063', '#48c9b0', '#f4d03f', '#ec8fd0'];
function draftColorFor(name) {
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return DRAFT_COLORS[h % DRAFT_COLORS.length];
}

var myDraftInput     = document.getElementById('myDraftInput');
var draftSavedHint   = document.getElementById('draftSavedHint');
var teamDraftPreview = document.getElementById('teamDraftPreview');
var generateDraftBtn = document.getElementById('generateFromDraftBtn');

function renderTeamDraft(data) {
    if (!teamDraftPreview || !data.inputs) return;
    // Don't redraw while a teammate's box is being edited here (avoids clobber).
    if (teamDraftPreview.contains(document.activeElement)) return;

    var withText = data.inputs.filter(function (it) { return (it.text || '').trim(); });
    if (!withText.length) {
        teamDraftPreview.innerHTML = '<span class="ti-empty">No input yet.</span>';
    } else {
        teamDraftPreview.innerHTML = withText.map(function (it) {
            var col = draftColorFor(it.username);
            var name = '<div class="ti-author" style="color:' + col + '">' +
                escapeHtml(it.username) + (it.is_me ? ' (you)' : '') + '</div>';
            if (it.is_me) {
                // Your own input is edited via the "Your input" box on the left.
                return '<div class="ti-contribution">' + name +
                    '<div class="ti-text" style="color:' + col + '">' + escapeHtml(it.text) + '</div></div>';
            }
            // Any member can edit a teammate's input inline.
            return '<div class="ti-contribution">' + name +
                '<textarea class="ti-edit-other" data-username="' + escapeHtml(it.username) +
                '" style="color:' + col + '" rows="4">' + escapeHtml(it.text) + '</textarea></div>';
        }).join('');

        teamDraftPreview.querySelectorAll('.ti-edit-other').forEach(function (ta) {
            ta.addEventListener('blur', function () {
                saveOtherDraft(ta.dataset.username, ta.value);
            });
        });
    }
    // Keep my own box in sync across devices, but never while I'm typing.
    if (myDraftInput && myDraftInput !== document.activeElement) {
        var mine = data.inputs.filter(function (it) { return it.is_me; })[0];
        var mineText = mine ? (mine.text || '') : '';
        if (mineText !== myDraftInput.value) myDraftInput.value = mineText;
    }
}

function saveOtherDraft(username, text) {
    fetch('/workspace/' + workspaceId + '/draft/save/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ username: username, text: text }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        showToast("Updated " + username + "'s input", 'info');
    })
    .catch(function (err) { showToast('Save failed: ' + err.message, 'error'); });
}

function pollTeamDraft() {
    if (!workspaceId || document.hidden || !teamDraftPreview) return;
    fetch('/workspace/' + workspaceId + '/draft/')
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) { if (data) renderTeamDraft(data); })
        .catch(function () { /* transient error — retry next tick */ });
}

function saveMyDraft() {
    if (!myDraftInput) return;
    fetch('/workspace/' + workspaceId + '/draft/save/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ text: myDraftInput.value }),
    })
    .then(function (res) { return res.json(); })
    .then(function () {
        if (draftSavedHint) {
            draftSavedHint.textContent = '✓ Saved';
            setTimeout(function () { draftSavedHint.textContent = ''; }, 1500);
        }
    })
    .catch(function () { /* ignore; will save again on next edit */ });
}

if (myDraftInput) {
    var draftTimer = null;
    myDraftInput.addEventListener('input', function () {
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(saveMyDraft, 800);
    });
    myDraftInput.addEventListener('blur', saveMyDraft);
    pollTeamDraft();  // initial load: show my saved text + teammates' input
}

if (generateDraftBtn) {
    generateDraftBtn.addEventListener('click', function () {
        generateDraftBtn.disabled = true;
        var welcome = document.getElementById('welcomeMsg');
        if (welcome) welcome.remove();
        var loadingEl = appendLoading();
        fetch('/workspace/' + workspaceId + '/draft/generate/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({}),
        })
        .then(function (res) {
            if (!res.ok) return res.json().then(function (e) { throw new Error(e.error || 'Server error'); });
            return res.json();
        })
        .then(function (data) {
            loadingEl.remove();
            appendUserMessage(data.requirements_text);
            if (data.requires_user_decision && data.suggested_requirement) {
                appendSuggestionConfirmBox(data);
            } else {
                currentSessionId = data.session_id;
                addSessionToHistory(data);
                appendAnalysisResult(data);
            }
        })
        .catch(function (err) {
            loadingEl.remove();
            appendErrorMessage('Error: ' + err.message);
        })
        .finally(function () { generateDraftBtn.disabled = false; });
    });
}

function pollAll() {
    pollWorkspaceState();   // self-guards: returns early outside a workspace
    pollMyWorkspaces();
    pollTeamNotes();        // self-guards: only in a workspace with an open session
    pollTeamDraft();        // self-guards: only in a workspace with the input panel
    pollSessionContent();   // self-guards: only in a workspace with an open session
}

setInterval(pollAll, 8000);
pollMyWorkspaces();
