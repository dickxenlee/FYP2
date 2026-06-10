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
            appendAnalysisResult(data);
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
    .then(function (res) { return res.json(); })
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
    .then(function (res) { return res.json(); })
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
    html += '<div class="suggestion-title">&#9650; Suggested Improvement</div>';
    html += '<p class="suggestion-label">The system detected quality issues. Here\'s an improved version &mdash; would you like to use it?</p>';
    html += '<div class="suggestion-preview">' + escapeHtml(suggestedText) + '</div>';
    html += '<div class="decision-prompt">Use the suggested input?</div>';
    html += '<div class="decision-buttons">';
    html += '<button class="btn-decision btn-yes">&#10003;&nbsp; Yes, use suggested input</button>';
    html += '<button class="btn-decision btn-no">&#10007;&nbsp; No, use my original input</button>';
    html += '</div></div>';
    block.innerHTML = html;
    chatMessages.appendChild(block);
    scrollToBottom();

    block.querySelector('.btn-yes').addEventListener('click', function () {
        block.querySelectorAll('button').forEach(function (el) { el.disabled = true; });
        handleGenerateFromEdited(suggestedText, block);
    });
    block.querySelector('.btn-no').addEventListener('click', function () {
        block.querySelectorAll('button').forEach(function (el) { el.disabled = true; });
        block.querySelector('.decision-buttons').innerHTML = '<span class="decision-confirmed">&#10007; Using your original input</span>';
        currentSessionId = data.session_id;
        addSessionToHistory(data);
        appendAnalysisResult(data);
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

function appendAnalysisResult(data) {
    var block = document.createElement('div');
    block.className = 'qa-report';
    var html = '';

    if (data.requirement_info) {
        html += buildRequirementInfoSection(data.requirement_info);
    }
    if (data.test_conditions && data.test_conditions.length > 0) {
        html += buildTestConditionsSection(data.test_conditions);
    }
    if (data.quality_assessment) {
        html += buildQualityAssessmentSection(data.quality_assessment);
    }
    if (data.gaps && data.gaps.length > 0) {
        html += buildGapsSection(data.gaps);
    }
    if (data.scenarios && data.scenarios.length > 0) {
        html += buildTestScenariosSection(data.scenarios);
    }

    // Section 6: Detailed Test Cases (button-triggered)
    if (data.session_id && data.scenarios && data.scenarios.length > 0) {
        html += '<div class="qa-section">';
        html += '<div class="qa-section-header"><span class="section-num">6</span>Detailed Test Cases</div>';
        html += '<div style="padding:0.8rem 1rem 0;">';
        html += '<p style="font-size:0.83rem;color:var(--color-muted);margin-bottom:0.6rem;">Expand each scenario into full test data, step-by-step instructions, and postconditions.</p>';
        html += '<button class="btn-generate-detailed">&#9654;&nbsp; Generate Detailed Test Cases</button>';
        html += '</div><div class="detailed-cases-container"></div></div>';
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
    chatMessages.appendChild(block);
    scrollToBottom();

    // Section 6 button
    var detailBtn = block.querySelector('.btn-generate-detailed');
    if (detailBtn) {
        detailBtn.addEventListener('click', function () {
            handleGenerateDetailedCases(data.session_id, block);
        });
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

    // Rating buttons
    attachRatingHandlers(block);
}


// ── Section builders ──────────────────────────

function buildRequirementInfoSection(info) {
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
    html += '<div class="qa-section-header"><span class="section-num">1</span>Requirement Analysis</div>';
    html += '<div style="padding:0.8rem 1rem 0.2rem;">';
    html += '<span class="req-id-badge">&#128196;&nbsp; ' + escapeHtml(info.requirement_id || 'REQ-001') + '</span>';
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
    return html;
}

function buildTestConditionsSection(conditions) {
    var html = '<div class="qa-section">';
    html += '<div class="qa-section-header"><span class="section-num">2</span>Test Conditions';
    html += '<span class="edit-hint">&#9998; click a cell to edit</span></div>';
    html += '<div class="qa-table-wrapper"><table class="qa-table"><thead><tr>';
    html += '<th>Condition ID</th><th>Test Condition</th><th>Type</th><th>Priority</th>';
    html += '</tr></thead><tbody>';

    conditions.forEach(function (c) {
        var typeSlug = (c.type || 'positive').toLowerCase().replace(/\s+/g, '');
        var priSlug  = (c.priority || 'medium').toLowerCase();
        var dbId     = c.db_id || '';
        html += '<tr>';
        html += '<td><strong>' + escapeHtml(c.condition_id) + '</strong></td>';
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
    html += '<span class="section-num">3</span>Requirement Quality Assessment';
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
    html += '<div class="qa-section-header"><span class="section-num">4</span>Requirement Review Findings';
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
    html += '<th>ID</th><th>Req</th><th>Cond</th><th>Description</th><th>Preconditions</th><th>Expected Result</th><th>Priority</th><th>Rating</th><th></th>';
    html += '</tr></thead><tbody>';

    scenarios.forEach(function (s) {
        var priSlug   = (s.priority || 'medium').toLowerCase();
        var dbId      = s.db_id || '';
        var rating    = s.user_rating || '';
        var usefulCls = rating === 'useful'     ? ' rate-active' : '';
        var notUseCls = rating === 'not_useful' ? ' rate-active' : '';

        html += '<tr data-scenario-db-id="' + dbId + '">';
        html += '<td><strong>' + escapeHtml(s.id || s.scenario_id || '') + '</strong></td>';
        html += '<td><span class="qa-badge badge-ref">' + escapeHtml(s.requirement_ref || '') + '</span></td>';
        html += '<td><span class="qa-badge badge-ref">' + escapeHtml(s.condition_ref || '') + '</span></td>';
        html += '<td class="editable-item" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="description">' + escapeHtml(s.description) + '</td>';
        html += '<td class="editable-item text-muted" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="preconditions">' + escapeHtml(s.preconditions) + '</td>';
        html += '<td class="editable-item" contenteditable="true" data-model="scenario" data-db-id="' + dbId + '" data-field="expected_result">' + escapeHtml(s.expected_result) + '</td>';
        html += '<td><span class="qa-badge badge-priority-' + priSlug + '">' + escapeHtml(s.priority || 'Medium') + '</span></td>';
        html += '<td class="rating-cell">';
        if (dbId) {
            html += '<button class="btn-rate' + usefulCls + '" data-db-id="' + dbId + '" data-rating="useful" title="Useful">&#128077;</button>';
            html += '<button class="btn-rate' + notUseCls + '" data-db-id="' + dbId + '" data-rating="not_useful" title="Not useful">&#128078;</button>';
        }
        html += '</td>';
        html += '<td><button class="btn-save-row" data-db-id="' + dbId + '" title="Save this row">&#128190;</button></td>';
        html += '</tr>';
    });

    html += '</tbody></table></div></div>';
    return html;
}


// ── Section 6: Generate Detailed Test Cases ───

function handleGenerateDetailedCases(sessionId, reportBlock) {
    var btn       = reportBlock.querySelector('.btn-generate-detailed');
    var container = reportBlock.querySelector('.detailed-cases-container');
    if (btn) btn.disabled = true;
    if (container) container.innerHTML =
        '<p style="padding:0.5rem 1rem;font-size:0.83rem;color:var(--color-muted);">Generating detailed test cases…</p>';

    fetch('/generate_detailed_cases/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ session_id: sessionId }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (container) container.innerHTML = buildDetailedCasesHtml(data.detailed_cases);
    })
    .catch(function (err) {
        if (container) container.innerHTML =
            '<span style="color:#e74c3c;padding:0.5rem 1rem;display:block;">Error: ' + escapeHtml(err.message) + '</span>';
        if (btn) btn.disabled = false;
    });
}

function buildDetailedCasesHtml(cases) {
    if (!cases || cases.length === 0) return '<p class="text-muted" style="padding:0.5rem 1rem;">No detailed cases generated.</p>';
    return cases.map(function (c) {
        var card = '<div class="detailed-case-card">';
        card += '<div class="detailed-case-id">&#128196;&nbsp; ' + escapeHtml(c.scenario_id) + '</div>';
        if (c.test_data) card += detailRow('Test Data', escapeHtml(c.test_data));
        if (c.steps && c.steps.length > 0) {
            var stepsHtml = '<ol style="margin:0;padding-left:1.2rem;">' +
                c.steps.map(function (s) { return '<li>' + escapeHtml(s) + '</li>'; }).join('') + '</ol>';
            card += detailRow('Test Steps', stepsHtml, true);
        }
        if (c.expected_results) card += detailRow('Expected Results', escapeHtml(c.expected_results));
        if (c.postconditions)   card += detailRow('Postconditions',   escapeHtml(c.postconditions));
        card += '</div>';
        return card;
    }).join('');
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
        '<button class="btn-export btn-csv" onclick="exportFile(' + sessionId + ', \'csv\')">CSV</button>' +
        '<button class="btn-export btn-reanalyze" data-session-id="' + sessionId + '">&#8635; Re-analyze</button>' +
        '</div>';
}

function exportFile(sessionId, format) {
    var urls = {
        pdf:   '/export/pdf/' + sessionId + '/',
        excel: '/export/excel/' + sessionId + '/',
        csv:   '/export/csv/' + sessionId + '/',
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
// Scenario rating
// ─────────────────────────────────────────────
function attachRatingHandlers(block) {
    block.querySelectorAll('.btn-rate').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var dbId   = parseInt(btn.dataset.dbId);
            var rating = btn.dataset.rating;
            if (!dbId) return;
            handleRateScenario(dbId, rating, btn.closest('tr'));
        });
    });
}

function handleRateScenario(dbId, rating, rowEl) {
    fetch('/rate_scenario/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ db_id: dbId, rating: rating }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (!rowEl) return;
        var usefulBtn    = rowEl.querySelector('.btn-rate[data-rating="useful"]');
        var notUsefulBtn = rowEl.querySelector('.btn-rate[data-rating="not_useful"]');
        if (usefulBtn)    usefulBtn.classList.toggle('rate-active', data.rating === 'useful');
        if (notUsefulBtn) notUsefulBtn.classList.toggle('rate-active', data.rating === 'not_useful');
        var label = data.rating === 'useful' ? 'Marked useful' : data.rating === 'not_useful' ? 'Marked not useful' : 'Rating cleared';
        showToast(label, 'info');
    })
    .catch(function (err) { showToast('Rating failed: ' + err.message, 'error'); });
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

function pollAll() {
    pollWorkspaceState();   // self-guards: returns early outside a workspace
    pollMyWorkspaces();
    pollTeamNotes();        // self-guards: only in a workspace with an open session
}

setInterval(pollAll, 8000);
pollMyWorkspaces();
