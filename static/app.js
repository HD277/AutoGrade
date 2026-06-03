document.addEventListener('DOMContentLoaded', () => {
    const problemsList = document.getElementById('problems-list');
    const refreshProblemsBtn = document.getElementById('btn-refresh-problems');
    
    const probTitle = document.getElementById('prob-title');
    const probDesc = document.getElementById('prob-desc');
    const metaTime = document.getElementById('meta-time');
    const metaMemory = document.getElementById('meta-memory');
    
    const codeEditor = document.getElementById('code-editor');
    const lineNumbers = document.getElementById('line-numbers');
    const submitBtn = document.getElementById('btn-submit');
    
    const gradingBadge = document.getElementById('grading-badge');
    const badgeText = document.getElementById('badge-text');
    const outputPlaceholder = document.getElementById('output-placeholder');
    const outputContent = document.getElementById('output-content');
    
    const statsScore = document.getElementById('stats-score');
    const statsPassed = document.getElementById('stats-passed');
    const statsFailed = document.getElementById('stats-failed');
    const statsTotal = document.getElementById('stats-total');
    const testResultsList = document.getElementById('test-results-list');
    
    const createModal = document.getElementById('create-modal');
    const openCreateBtn = document.getElementById('btn-open-create');
    const closeCreateBtn = document.getElementById('btn-close-create');
    const cancelCreateBtn = document.getElementById('btn-cancel-create');
    const createProblemForm = document.getElementById('create-problem-form');
    const addTestBtn = document.getElementById('btn-add-test');
    const modalTestCasesList = document.getElementById('modal-test-cases-list');

    let problems = [];
    let selectedProblem = null;
    let pollingInterval = null;

    fetchProblems();
    setupEventListeners();

    function setupEventListeners() {
        refreshProblemsBtn.addEventListener('click', fetchProblems);

        codeEditor.addEventListener('input', updateLineNumbers);
        codeEditor.addEventListener('scroll', () => {
            lineNumbers.scrollTop = codeEditor.scrollTop;
        });

        submitBtn.addEventListener('click', submitSolution);

        openCreateBtn.addEventListener('click', () => {
            resetCreateModal();
            createModal.classList.remove('hide');
        });
        const closeModal = () => createModal.classList.add('hide');
        closeCreateBtn.addEventListener('click', closeModal);
        cancelCreateBtn.addEventListener('click', closeModal);

        addTestBtn.addEventListener('click', () => addTestCaseRow());

        createProblemForm.addEventListener('submit', handleCreateProblem);
    }

    function updateLineNumbers() {
        const lines = codeEditor.value.split('\n').length;
        let numbers = '';
        for (let i = 1; i <= lines; i++) {
            numbers += `${i}<br>`;
        }
        lineNumbers.innerHTML = numbers;
    }

    async function fetchProblems() {
        showProblemsLoader();
        try {
            const res = await fetch('/api/problems');
            if (!res.ok) throw new Error("Failed to fetch problems");
            problems = await res.ok ? await res.json() : [];
            renderProblems();
        } catch (err) {
            console.error(err);
            problemsList.innerHTML = `<div class="text-danger" style="padding:16px; font-size:14px;"><i class="fa-solid fa-triangle-exclamation"></i> Error loading problems.</div>`;
        }
    }

    function renderProblems() {
        problemsList.innerHTML = '';
        if (problems.length === 0) {
            problemsList.innerHTML = `<div class="text-muted" style="padding:16px; font-size:14px;"><i class="fa-solid fa-info-circle"></i> No problems found. Create one!</div>`;
            return;
        }

        problems.forEach(prob => {
            const item = document.createElement('div');
            item.className = 'problem-item';
            if (selectedProblem && selectedProblem.id === prob.id) {
                item.classList.add('active');
            }
            item.innerHTML = `
                <span class="problem-item-title">${prob.title}</span>
                <i class="fa-solid fa-chevron-right"></i>
            `;
            item.addEventListener('click', () => selectProblem(prob));
            problemsList.appendChild(item);
        });
    }

    function selectProblem(prob) {
        selectedProblem = prob;
        document.querySelectorAll('.problem-item').forEach(item => {
            const title = item.querySelector('.problem-item-title').textContent;
            if (title === prob.title) item.classList.add('active');
            else item.classList.remove('active');
        });

        probTitle.textContent = prob.title;
        probDesc.textContent = prob.description;
        metaTime.textContent = `${prob.time_limit_ms}ms`;
        metaMemory.textContent = `${prob.memory_limit_mb}MB`;

        codeEditor.removeAttribute('disabled');
        codeEditor.value = "# Write your python solution here\n# Input is received via stdin, output must be printed to stdout\n\n";
        updateLineNumbers();
        submitBtn.removeAttribute('disabled');

        resetConsole();
    }

    function showProblemsLoader() {
        problemsList.innerHTML = `
            <div class="loader-container">
                <div class="spinner"></div>
            </div>
        `;
    }

    async function submitSolution() {
        if (!selectedProblem) return;
        
        const code = codeEditor.value.trim();
        if (!code) return;

        setSubmittingState(true);

        try {
            const res = await fetch('/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    problem_id: selectedProblem.id,
                    code: code
                })
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.error || "Submission failed");
            }

            const data = await res.json();
            startPolling(data.submission_id);

        } catch (err) {
            console.error(err);
            setSubmittingState(false);
            showErrorConsole(err.message);
        }
    }

    function startPolling(subId) {
        if (pollingInterval) clearInterval(pollingInterval);
        
        showGradingState("pending");

        pollingInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${subId}`);
                if (!res.ok) throw new Error("Failed to check status");
                
                const data = await res.json();
                showGradingState(data.status);

                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(pollingInterval);
                    setSubmittingState(false);
                    renderResults(data);
                }
            } catch (err) {
                console.error(err);
                clearInterval(pollingInterval);
                setSubmittingState(false);
                showErrorConsole("Status polling encountered an error: " + err.message);
            }
        }, 1000);
    }

    function renderResults(subData) {
        outputPlaceholder.classList.add('hide');
        outputContent.classList.remove('hide');

        const summary = subData.summary || { total: 0, passed: 0, failed: 0, score: 0 };
        statsScore.textContent = `${summary.score}%`;
        statsPassed.textContent = summary.passed;
        statsFailed.textContent = summary.failed;
        statsTotal.textContent = summary.total;
        const scoreRing = document.querySelector('.score-card');
        if (summary.score === 100) {
            scoreRing.style.borderColor = 'var(--success-color)';
            scoreRing.style.boxShadow = '0 0 12px var(--success-glow)';
        } else if (summary.score === 0) {
            scoreRing.style.borderColor = 'var(--danger-color)';
            scoreRing.style.boxShadow = '0 0 12px var(--danger-glow)';
        } else {
            scoreRing.style.borderColor = 'var(--warning-color)';
            scoreRing.style.boxShadow = '0 0 12px var(--warning-glow)';
        }

        testResultsList.innerHTML = '';
        const results = subData.results || [];
        
        if (results.length === 0) {
            testResultsList.innerHTML = `<div class="text-danger"><i class="fa-solid fa-triangle-exclamation"></i> No test results returned. Subprocess may have crashed during initialization.</div>`;
            return;
        }

        results.forEach((r, idx) => {
            const card = document.createElement('div');
            card.className = 'test-card';
            
            const isPassed = r.passed;
            const statusClass = isPassed ? 'passed' : 'failed';
            const icon = isPassed ? 'fa-circle-check' : 'fa-circle-xmark';
            
            card.innerHTML = `
                <div class="test-card-header" data-index="${idx}">
                    <div class="test-info">
                        <i class="fa-solid ${icon} test-status-icon ${statusClass}"></i>
                        <span class="test-title">${r.test_name}</span>
                        <span class="test-time">${r.execution_time_ms}ms</span>
                    </div>
                    <div class="test-actions">
                        <span class="test-badge ${statusClass}">${isPassed ? 'Passed' : r.error_type || 'Failed'}</span>
                        <i class="fa-solid fa-chevron-down" style="color:var(--text-dark); transition:transform 0.2s;"></i>
                    </div>
                </div>
                <div class="test-details hide">
                    <div class="test-details-grid">
                        <div class="data-block">
                            <h4>Expected Output</h4>
                            <pre>${escapeHtml(r.expected_output || "")}</pre>
                        </div>
                        <div class="data-block">
                            <h4>Actual Output</h4>
                            <pre>${escapeHtml(r.actual_output || "")}</pre>
                        </div>
                    </div>
                    ${r.stderr ? `
                    <div class="data-block test-stderr">
                        <h4>Execution Error Logs (stderr)</h4>
                        <pre>${escapeHtml(r.stderr)}</pre>
                    </div>
                    ` : ''}
                </div>
            `;

            const header = card.querySelector('.test-card-header');
            const details = card.querySelector('.test-details');
            const chevron = card.querySelector('.fa-chevron-down');
            header.addEventListener('click', () => {
                const isHidden = details.classList.contains('hide');
                if (isHidden) {
                    details.classList.remove('hide');
                    chevron.style.transform = 'rotate(180deg)';
                } else {
                    details.classList.add('hide');
                    chevron.style.transform = 'rotate(0deg)';
                }
            });

            testResultsList.appendChild(card);
        });
    }

    function resetCreateModal() {
        createProblemForm.reset();
        modalTestCasesList.innerHTML = '';
        addTestCaseRow("Test Case 1");
        addTestCaseRow("Test Case 2");
    }

    function addTestCaseRow(nameVal = "") {
        const rowCount = modalTestCasesList.children.length + 1;
        const defaultName = nameVal || `Test Case ${rowCount}`;
        
        const row = document.createElement('div');
        row.className = 'modal-test-row';
        row.innerHTML = `
            <div class="form-group">
                <label>Name</label>
                <input type="text" class="tc-name" required value="${defaultName}">
            </div>
            <div class="form-group">
                <label>Input (stdin)</label>
                <textarea class="tc-input" rows="1" placeholder="e.g. 5" style="resize: vertical; min-height: 38px; height: 38px; padding: 8px 12px;"></textarea>
            </div>
            <div class="form-group">
                <label>Expected Output</label>
                <textarea class="tc-output" rows="1" required placeholder="e.g. 10" style="resize: vertical; min-height: 38px; height: 38px; padding: 8px 12px;"></textarea>
            </div>
            <button type="button" class="btn-icon btn-remove-test" style="color:var(--danger-color); margin-bottom:8px;" title="Remove Test Case">
                <i class="fa-solid fa-trash"></i>
            </button>
        `;

        const removeBtn = row.querySelector('.btn-remove-test');
        removeBtn.addEventListener('click', () => {
            if (modalTestCasesList.children.length > 1) {
                row.remove();
            } else {
                alert("At least one test case is required!");
            }
        });

        modalTestCasesList.appendChild(row);
    }

    async function handleCreateProblem(e) {
        e.preventDefault();

        const id = document.getElementById('new-prob-id').value.trim();
        const title = document.getElementById('new-prob-title').value.trim();
        const description = document.getElementById('new-prob-desc').value.trim();
        const timeLimit = parseInt(document.getElementById('new-prob-time').value);
        const memoryLimit = parseInt(document.getElementById('new-prob-memory').value);

        const testRows = modalTestCasesList.querySelectorAll('.modal-test-row');
        const testCases = [];
        testRows.forEach(row => {
            testCases.push({
                name: row.querySelector('.tc-name').value.trim(),
                input: row.querySelector('.tc-input').value.trim(),
                expected_output: row.querySelector('.tc-output').value.trim()
            });
        });

        const payload = {
            id, title, description,
            time_limit_ms: timeLimit,
            memory_limit_mb: memoryLimit,
            test_cases: testCases
        };

        try {
            const res = await fetch('/api/problems', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Failed to create problem");
            }

            const newProb = await res.json();
            createModal.classList.add('hide');
            await fetchProblems();
            selectProblem(newProb);

        } catch (err) {
            alert("Error: " + err.message);
        }
    }

    function setSubmittingState(isSubmitting) {
        if (isSubmitting) {
            submitBtn.setAttribute('disabled', 'true');
            submitBtn.innerHTML = `<span>Grading</span> <i class="fa-solid fa-rotate spin"></i>`;
            codeEditor.setAttribute('disabled', 'true');
        } else {
            submitBtn.removeAttribute('disabled');
            submitBtn.innerHTML = `<span>Run Tests</span> <i class="fa-solid fa-play"></i>`;
            codeEditor.removeAttribute('disabled');
        }
    }

    function showGradingState(status) {
        gradingBadge.className = `grading-badge ${status}`;
        gradingBadge.classList.remove('hide');
        badgeText.textContent = status;
        
        if (status === 'pending') {
            badgeText.innerHTML = `<i class="fa-solid fa-hourglass-start"></i> Pending`;
        } else if (status === 'running') {
            badgeText.innerHTML = `<i class="fa-solid fa-rotate spin"></i> Running`;
        } else if (status === 'completed') {
            badgeText.innerHTML = `<i class="fa-solid fa-circle-check"></i> Completed`;
        } else if (status === 'failed') {
            badgeText.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Failed`;
        }
    }

    function resetConsole() {
        gradingBadge.classList.add('hide');
        outputPlaceholder.classList.remove('hide');
        outputContent.classList.add('hide');
    }

    function showErrorConsole(msg) {
        outputPlaceholder.classList.add('hide');
        outputContent.classList.remove('hide');
        testResultsList.innerHTML = `
            <div class="text-danger" style="padding:16px;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size:24px; margin-bottom:8px;"></i>
                <h4>Submission Error</h4>
                <pre style="background:hsla(355, 85%, 55%, 0.05); border:1px solid rgba(235,64,52,0.2); padding:12px; margin-top:8px; border-radius:6px; font-family:var(--font-mono); font-size:13px; color:hsl(355, 85%, 75%);">${escapeHtml(msg)}</pre>
            </div>
        `;
    }

    function escapeHtml(text) {
        return text
            .toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
